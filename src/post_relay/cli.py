from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from post_relay.approvals import (
    DraftNotFound as ApprovalDraftNotFound,
    DraftNotReadyForApproval,
    approve_draft_content,
    edit_draft_content,
    submit_draft_for_review,
)
from post_relay.candidates import build_candidate_groups
from post_relay.config import load_config
from post_relay.context_questions import (
    DraftNotFound as ContextDraftNotFound,
    generate_context_questions_for_draft,
)
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import CandidateNotFound, create_draft_from_candidate
from post_relay.discord_preview import DraftNotFound as DiscordPreviewDraftNotFound
from post_relay.discord_preview import build_discord_preview_payload
from post_relay.indexer import index_photo_sources
from post_relay.meta_graph import (
    MetaGraphClient,
    MetaGraphConfigError,
    MetaGraphRequestError,
    load_meta_graph_config,
)
from post_relay.publishing import (
    DraftNotFound as PublishDraftNotFound,
    DraftNotReadyForImagePublish,
    PublishValidationError,
    UnsupportedPublishDraft,
    execute_carousel_publish_validation,
    execute_single_image_publish_validation,
    prepare_carousel_publish_validation,
    prepare_single_image_publish_validation,
)
from post_relay.repository import (
    get_library_stats,
    list_active_approvals,
    list_candidate_groups,
    list_context_questions,
    list_drafts,
)
from post_relay.review_artifacts import DraftNotFound as ArtifactDraftNotFound
from post_relay.review_artifacts import UnsafeArtifactRoot, render_review_artifacts_for_draft
from post_relay.review_package import DraftNotFound, build_draft_review_package
from post_relay.scheduling import (
    DraftNotFound as SchedulingDraftNotFound,
    DraftNotReadyForPublishApproval,
    DraftNotReadyForScheduling,
    approve_draft_for_publishing,
    request_publish_approval,
    schedule_draft,
)

app = typer.Typer(help="Post Relay local-first Instagram content workflow.")
db_app = typer.Typer(help="Database commands.")
index_app = typer.Typer(help="Media indexing commands.")
library_app = typer.Typer(help="Library inspection commands.")
meta_app = typer.Typer(help="Meta Graph validation commands.")
candidates_app = typer.Typer(help="Candidate post group commands.")
drafts_app = typer.Typer(help="Draft record commands.")
draft_questions_app = typer.Typer(help="Draft context question commands.")
draft_artifacts_app = typer.Typer(help="Draft review artifact commands.")
app.add_typer(db_app, name="db")
app.add_typer(index_app, name="index")
app.add_typer(library_app, name="library")
app.add_typer(meta_app, name="meta")
app.add_typer(candidates_app, name="candidates")
app.add_typer(drafts_app, name="drafts")
drafts_app.add_typer(draft_questions_app, name="questions")
drafts_app.add_typer(draft_artifacts_app, name="artifacts")

DEFAULT_DB_PATH = Path("data/post_relay.sqlite")


@app.command()
def version() -> None:
    """Print the current Post Relay version."""
    typer.echo("post-relay 0.1.0")


@db_app.command("init")
def db_init(db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path.")) -> None:
    """Initialize the SQLite database."""
    connection = connect_db(db)
    initialize_db(connection)
    typer.echo(f"Initialized database at {db}")


@index_app.command("scan")
def index_scan(
    config: Path = typer.Option(..., "--config", help="Path to photo_sources.yaml."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Scan configured photo sources and persist discovered media."""
    loaded_config = load_config(config)
    connection = connect_db(db)
    initialize_db(connection)
    result = index_photo_sources(connection, loaded_config)
    source_plural = "" if result.source_count == 1 else "s"
    typer.echo(
        f"Indexed {result.scanned_count} photos from {result.source_count} source{source_plural}."
    )


@library_app.command("stats")
def library_stats(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print basic library statistics."""
    connection = connect_db(db)
    initialize_db(connection)
    stats = get_library_stats(connection)
    typer.echo(f"Total photos: {stats.total_photos}")
    if stats.by_source:
        typer.echo("By source:")
        for source_name, count in stats.by_source.items():
            typer.echo(f"  {source_name}: {count}")
    if stats.by_year:
        typer.echo("By year:")
        for year, count in stats.by_year.items():
            year_label: Optional[int | str] = year if year is not None else "unknown"
            typer.echo(f"  {year_label}: {count}")


@meta_app.command("validate-readonly")
def meta_validate_readonly(
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print sanitized planned read-only requests without calling Meta."),
) -> None:
    """Validate read-only Meta Graph account visibility without publishing."""
    try:
        config = load_meta_graph_config(env_file=env_file)
    except MetaGraphConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error

    client = MetaGraphClient(config)
    if dry_run:
        typer.echo("Meta Graph read-only validation (dry run)")
        typer.echo(config.safe_summary())
        typer.echo("Read-only requests:")
        for url in client.dry_run_urls():
            typer.echo(f"  - {url}")
        typer.echo("No publishing endpoints will be called.")
        return

    try:
        result = client.validate_readonly_access()
    except MetaGraphRequestError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error
    typer.echo(result.to_text())


@meta_app.command("validate-image-publish")
def meta_validate_image_publish(
    draft_id: int = typer.Option(..., "--draft-id", help="Ready-to-publish single-image draft id."),
    image_url: str = typer.Option(..., "--image-url", help="Public HTTPS image URL for Meta container creation."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Record and print the sanitized plan without calling Meta."),
    execute: bool = typer.Option(False, "--execute", help="Actually create, poll, and publish through Meta Graph."),
) -> None:
    """Validate a controlled single-image publish after explicit publish approval."""
    connection = connect_db(db)
    initialize_db(connection)
    if dry_run or not execute:
        try:
            result = prepare_single_image_publish_validation(connection, draft_id, image_url=image_url)
        except (PublishDraftNotFound, DraftNotReadyForImagePublish, UnsupportedPublishDraft) as error:
            raise typer.BadParameter(str(error), param_hint="--draft-id") from error
        typer.echo(result.to_text())
        typer.echo("No Meta publishing endpoints were called.")
        return

    try:
        config = load_meta_graph_config(env_file=env_file)
    except MetaGraphConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error

    try:
        result = execute_single_image_publish_validation(
            connection,
            draft_id,
            image_url=image_url,
            client=MetaGraphClient(config),
        )
    except (PublishDraftNotFound, DraftNotReadyForImagePublish, UnsupportedPublishDraft) as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except PublishValidationError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error
    typer.echo(result.to_text())


@meta_app.command("validate-carousel-publish")
def meta_validate_carousel_publish(
    draft_id: int = typer.Option(..., "--draft-id", help="Ready-to-publish carousel draft id."),
    image_urls: list[str] = typer.Option(
        ..., "--image-url", help="Public HTTPS image URL for each carousel image, in draft order."
    ),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Record and print the sanitized plan without calling Meta."),
    execute: bool = typer.Option(False, "--execute", help="Actually create, poll, and publish through Meta Graph."),
) -> None:
    """Validate a controlled carousel publish after explicit publish approval."""
    connection = connect_db(db)
    initialize_db(connection)
    if dry_run or not execute:
        try:
            result = prepare_carousel_publish_validation(connection, draft_id, image_urls=image_urls)
        except (PublishDraftNotFound, DraftNotReadyForImagePublish, UnsupportedPublishDraft) as error:
            raise typer.BadParameter(str(error), param_hint="--draft-id") from error
        typer.echo(result.to_text())
        typer.echo("No Meta publishing endpoints were called.")
        return

    try:
        config = load_meta_graph_config(env_file=env_file)
    except MetaGraphConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error

    try:
        result = execute_carousel_publish_validation(
            connection,
            draft_id,
            image_urls=image_urls,
            client=MetaGraphClient(config),
        )
    except (PublishDraftNotFound, DraftNotReadyForImagePublish, UnsupportedPublishDraft) as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except PublishValidationError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error
    typer.echo(result.to_text())


@candidates_app.command("build")
def candidates_build(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Build reviewable candidate groups from indexed photos."""
    connection = connect_db(db)
    initialize_db(connection)
    result = build_candidate_groups(connection)
    group_plural = "" if result.created_count == 1 else "s"
    typer.echo(
        f"Created {result.created_count} candidate group{group_plural} from {result.considered_photo_count} indexed photos."
    )


@candidates_app.command("list")
def candidates_list(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """List candidate groups ready for review."""
    connection = connect_db(db)
    initialize_db(connection)
    groups = list_candidate_groups(connection)
    if not groups:
        typer.echo("No candidate groups found.")
        return
    for group in groups:
        photo_plural = "" if group.photo_count == 1 else "s"
        typer.echo(
            f"#{group.id} {group.title} — {group.post_type_recommendation}, {group.photo_count} photo{photo_plural}, confidence {group.confidence:.2f}"
        )


@drafts_app.command("create")
def drafts_create(
    candidate_id: int = typer.Option(..., "--candidate-id", help="Candidate group id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Create an initial draft record from a candidate group."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        draft = create_draft_from_candidate(connection, candidate_id)
    except CandidateNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--candidate-id") from error
    typer.echo(f"Created draft #{draft.id} from candidate #{draft.candidate_group_id}.")


@drafts_app.command("list")
def drafts_list(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """List draft records."""
    connection = connect_db(db)
    initialize_db(connection)
    drafts = list_drafts(connection)
    if not drafts:
        typer.echo("No drafts found.")
        return
    for draft in drafts:
        typer.echo(
            f"#{draft.id} candidate #{draft.candidate_group_id} — {draft.post_type}, {draft.status}"
        )


@drafts_app.command("preview")
def drafts_preview(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print a structured local review package for a draft."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        package = build_draft_review_package(connection, draft_id)
    except DraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(package.to_text())


@drafts_app.command("discord-preview")
def drafts_discord_preview(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print a dry-run Discord preview payload with ordered image paths."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        payload = build_discord_preview_payload(connection, draft_id)
    except DiscordPreviewDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(payload.to_text())


@drafts_app.command("submit")
def drafts_submit(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Submit a draft for content-direction review."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        draft = submit_draft_for_review(connection, draft_id)
    except (ApprovalDraftNotFound, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(f"Submitted draft #{draft.id} for review; status is {draft.status}.")


@drafts_app.command("approve")
def drafts_approve(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    approved_by: Optional[str] = typer.Option(None, "--approved-by", help="Approver name."),
    notes: Optional[str] = typer.Option(None, "--notes", help="Approval notes."),
    source_message_ref: Optional[str] = typer.Option(None, "--source-message-ref", help="Source message reference."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Record explicit draft approval for queueing."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        approval = approve_draft_content(
            connection,
            draft_id,
            approved_by=approved_by,
            notes=notes,
            source_message_ref=source_message_ref,
        )
    except ApprovalDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except DraftNotReadyForApproval as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(f"Approved draft #{approval.draft_id} for queue with approval #{approval.id}.")


@drafts_app.command("edit")
def drafts_edit(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    caption: Optional[str] = typer.Option(None, "--caption", help="Draft caption text."),
    hashtags: Optional[str] = typer.Option(None, "--hashtags", help="Comma-separated hashtags."),
    location_text: Optional[str] = typer.Option(None, "--location", help="Location text."),
    alt_text: Optional[str] = typer.Option(None, "--alt-text", help="Alt text."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Edit draft content placeholders and invalidate prior approvals on material changes."""
    connection = connect_db(db)
    initialize_db(connection)
    active_before = len(list_active_approvals(connection, draft_id))
    try:
        draft = edit_draft_content(
            connection,
            draft_id,
            caption=caption,
            hashtags=_split_hashtags(hashtags),
            location_text=location_text,
            alt_text=alt_text,
        )
    except ApprovalDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    invalidated_count = active_before - len(list_active_approvals(connection, draft_id))
    message = f"Updated draft #{draft.id}; status is {draft.status}."
    if invalidated_count:
        message += f" Material edit invalidated active approvals: {invalidated_count}."
    typer.echo(message)


@drafts_app.command("schedule")
def drafts_schedule(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    scheduled_for: str = typer.Option(..., "--scheduled-for", help="Scheduled publish time/window."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Schedule a queue-approved draft without publishing."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        draft = schedule_draft(connection, draft_id, scheduled_for=scheduled_for)
    except (SchedulingDraftNotFound, DraftNotReadyForScheduling) as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(f"Scheduled draft #{draft.id} for {draft.scheduled_for}; status is {draft.status}.")


@drafts_app.command("request-publish-approval")
def drafts_request_publish_approval(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Move a scheduled draft into final publish-approval review."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        draft = request_publish_approval(connection, draft_id)
    except (SchedulingDraftNotFound, DraftNotReadyForPublishApproval) as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(f"Requested publish approval for draft #{draft.id}; status is {draft.status}.")


@drafts_app.command("approve-publish")
def drafts_approve_publish(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    approved_by: Optional[str] = typer.Option(None, "--approved-by", help="Approver name."),
    notes: Optional[str] = typer.Option(None, "--notes", help="Approval notes."),
    source_message_ref: Optional[str] = typer.Option(None, "--source-message-ref", help="Source message reference."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Record final publish approval without calling any publish API."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        approval = approve_draft_for_publishing(
            connection,
            draft_id,
            approved_by=approved_by,
            notes=notes,
            source_message_ref=source_message_ref,
        )
    except (SchedulingDraftNotFound, DraftNotReadyForPublishApproval) as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(f"Approved draft #{approval.draft_id} for publishing with approval #{approval.id}.")


@draft_artifacts_app.command("render")
def draft_artifacts_render(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and artifact config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render local thumbnails and a contact sheet for draft review."""
    config = load_config(config_path)
    connection = connect_db(db)
    initialize_db(connection)
    try:
        package = render_review_artifacts_for_draft(
            connection,
            draft_id,
            config.review_artifacts,
            protected_source_roots=[source.root for source in config.photo_sources],
        )
    except ArtifactDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except UnsafeArtifactRoot as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    typer.echo(package.to_text())


@draft_questions_app.command("generate")
def draft_questions_generate(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Generate lightweight missing-context questions for a draft."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        questions = generate_context_questions_for_draft(connection, draft_id)
    except ContextDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(
        f"Generated {len(questions)} unresolved context questions for draft #{draft_id}."
    )


@draft_questions_app.command("list")
def draft_questions_list(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """List context questions for a draft."""
    connection = connect_db(db)
    initialize_db(connection)
    questions = list_context_questions(connection, draft_id)
    if not questions:
        typer.echo("No context questions found.")
        return
    for question in questions:
        typer.echo(f"[{question.field_name}] {question.question_text} — {question.status}")


def _split_hashtags(hashtags: Optional[str]) -> Optional[list[str]]:
    if hashtags is None:
        return None
    return [tag.strip() for tag in hashtags.split(",") if tag.strip()]

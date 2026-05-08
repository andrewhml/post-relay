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
from post_relay.discord_preview import (
    DraftNotFound as DiscordPreviewDraftNotFound,
    build_discord_preview_payload,
    build_discord_selection_payload,
)
from post_relay.discord_selection import (
    DraftNotFound as DiscordSelectionDraftNotFound,
    InvalidDiscordSelection,
    apply_discord_photo_selection,
    build_discord_selection_request,
)
from post_relay.indexer import index_photo_sources
from post_relay.meta_graph import (
    MetaGraphClient,
    MetaGraphConfigError,
    MetaGraphRequestError,
    load_meta_graph_config,
)
from post_relay.media_selection import (
    DraftNotFound as MediaSelectionDraftNotFound,
    InvalidMediaSelection,
    apply_draft_media_selection,
    build_draft_media_plan,
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
    resolve_staged_r2_publish_image_urls,
)
from post_relay.repository import (
    get_library_stats,
    list_active_approvals,
    list_candidate_groups,
    list_context_questions,
    list_drafts,
)
from post_relay.r2_staging import (
    DraftNotFound as R2StagingDraftNotFound,
    R2StagingConfigError,
    plan_r2_staging_for_draft,
)
from post_relay.r2_staging_upload import (
    R2CleanupSafetyError,
    R2StagingUploadError,
    cleanup_r2_staged_objects_for_draft,
    upload_r2_staging_for_draft,
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
    image_url: Optional[str] = typer.Option(None, "--image-url", help="Public HTTPS image URL for Meta container creation."),
    from_staged_r2: bool = typer.Option(False, "--from-staged-r2", help="Resolve the publish image URL from uploaded R2 staged media records."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Record and print the sanitized plan without calling Meta."),
    execute: bool = typer.Option(False, "--execute", help="Actually create, poll, and publish through Meta Graph."),
) -> None:
    """Validate a controlled single-image publish after explicit publish approval."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        resolved_image_url = _resolve_single_publish_image_url(
            connection,
            draft_id,
            image_url=image_url,
            from_staged_r2=from_staged_r2,
            config_path=config_path,
        )
    except (PublishDraftNotFound, UnsupportedPublishDraft, R2StagingConfigError) as error:
        raise typer.BadParameter(str(error), param_hint="--image-url/--from-staged-r2") from error
    if dry_run or not execute:
        try:
            result = prepare_single_image_publish_validation(connection, draft_id, image_url=resolved_image_url)
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
            image_url=resolved_image_url,
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
    image_urls: Optional[list[str]] = typer.Option(
        None, "--image-url", help="Public HTTPS image URL for each carousel image, in draft order."
    ),
    from_staged_r2: bool = typer.Option(False, "--from-staged-r2", help="Resolve ordered publish image URLs from uploaded R2 staged media records."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Record and print the sanitized plan without calling Meta."),
    execute: bool = typer.Option(False, "--execute", help="Actually create, poll, and publish through Meta Graph."),
) -> None:
    """Validate a controlled carousel publish after explicit publish approval."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        resolved_image_urls = _resolve_publish_image_urls(
            connection,
            draft_id,
            image_urls=image_urls or [],
            from_staged_r2=from_staged_r2,
            config_path=config_path,
        )
    except (PublishDraftNotFound, UnsupportedPublishDraft, R2StagingConfigError) as error:
        raise typer.BadParameter(str(error), param_hint="--image-url/--from-staged-r2") from error
    if dry_run or not execute:
        try:
            result = prepare_carousel_publish_validation(connection, draft_id, image_urls=resolved_image_urls)
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
            image_urls=resolved_image_urls,
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


@drafts_app.command("media-plan")
def drafts_media_plan(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print numbered draft media for contact-sheet review instructions."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = build_draft_media_plan(connection, draft_id)
    except MediaSelectionDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    typer.echo(plan.to_text())


@drafts_app.command("media-edit")
def drafts_media_edit(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    lead: int = typer.Option(..., "--lead", help="Review media number to make lead/cover."),
    keep: Optional[str] = typer.Option(None, "--keep", help="Comma-separated review media numbers to keep."),
    remove: Optional[str] = typer.Option(None, "--remove", help="Comma-separated review media numbers to exclude."),
    post_type: Optional[str] = typer.Option(None, "--post-type", help="Optional post type: single_image, carousel, or reel."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Apply explicit keep/remove/lead media choices to a draft."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = apply_draft_media_selection(
            connection,
            draft_id,
            lead=lead,
            keep=_split_ints(keep),
            remove=_split_ints(remove),
            post_type=post_type,
        )
    except MediaSelectionDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except InvalidMediaSelection as error:
        raise typer.BadParameter(str(error), param_hint="--lead/--keep/--remove") from error
    typer.echo(result.to_text())


@drafts_app.command("discord-selection-plan")
def drafts_discord_selection_plan(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    target_count: int = typer.Option(..., "--target-count", help="Number of photos Andrew should select."),
    post_type: Optional[str] = typer.Option(None, "--post-type", help="Optional post type: single_image, carousel, or reel."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print a local Discord-style X-from-Y photo selection request."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        request = build_discord_selection_request(
            connection,
            draft_id,
            target_count=target_count,
            post_type=post_type,
        )
    except DiscordSelectionDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except InvalidDiscordSelection as error:
        raise typer.BadParameter(str(error), param_hint="--target-count/--post-type") from error
    typer.echo(request.to_text())


@drafts_app.command("discord-selection-preview")
def drafts_discord_selection_preview(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    target_count: int = typer.Option(..., "--target-count", help="Number of photos Andrew should select."),
    post_type: Optional[str] = typer.Option(None, "--post-type", help="Optional post type: single_image, carousel, or reel."),
    artifact_paths: Optional[list[Path]] = typer.Option(None, "--artifact-path", help="Optional local review artifact path, such as a contact sheet."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print a dry-run Discord X-from-Y selection payload without sending messages."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        payload = build_discord_selection_payload(
            connection,
            draft_id,
            target_count=target_count,
            post_type=post_type,
            artifact_paths=artifact_paths or [],
        )
    except DiscordSelectionDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except InvalidDiscordSelection as error:
        raise typer.BadParameter(str(error), param_hint="--target-count/--post-type") from error
    typer.echo(payload.to_text())


@drafts_app.command("discord-selection-apply")
def drafts_discord_selection_apply(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    selected: str = typer.Option(..., "--select", help="Comma-separated suggested photo numbers to keep, in Andrew's chosen order."),
    lead: int = typer.Option(..., "--lead", help="Selected suggested photo number to make lead/cover."),
    target_count: int = typer.Option(..., "--target-count", help="Expected selected photo count."),
    post_type: Optional[str] = typer.Option(None, "--post-type", help="Optional post type: single_image, carousel, or reel."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Apply a Discord-style X-from-Y photo selection locally without calling Discord."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = apply_discord_photo_selection(
            connection,
            draft_id,
            selected_numbers=_split_ints(selected) or [],
            lead=lead,
            target_count=target_count,
            post_type=post_type,
        )
    except DiscordSelectionDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except InvalidDiscordSelection as error:
        raise typer.BadParameter(str(error), param_hint="--select/--lead/--target-count") from error
    typer.echo(result.to_text())


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


@drafts_app.command("r2-stage-plan")
def drafts_r2_stage_plan(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print a no-network R2 staging plan for draft media and review artifacts."""
    config = load_config(config_path)
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = plan_r2_staging_for_draft(
            connection,
            draft_id,
            config.r2_staging,
            review_artifact_root=config.review_artifacts.root,
        )
    except R2StagingDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except R2StagingConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    typer.echo(plan.to_text())


@drafts_app.command("r2-stage-upload")
def drafts_r2_stage_upload(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    execute: bool = typer.Option(False, "--execute", help="Upload staged objects to R2 and record them."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Upload the R2 staging plan only when --execute is provided."""
    config = load_config(config_path)
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = upload_r2_staging_for_draft(
            connection,
            draft_id,
            config.r2_staging,
            review_artifact_root=config.review_artifacts.root,
            execute=execute,
        )
    except R2StagingDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--draft-id") from error
    except (R2StagingConfigError, R2StagingUploadError) as error:
        raise typer.BadParameter(str(error), param_hint="--config/--execute") from error
    typer.echo(result.to_text())


@drafts_app.command("r2-cleanup")
def drafts_r2_cleanup(
    draft_id: int = typer.Option(..., "--draft-id", help="Draft id."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    execute: bool = typer.Option(False, "--execute", help="Delete recorded staged R2 objects and mark them cleaned up."),
    reason: Optional[str] = typer.Option(None, "--reason", help="Cleanup reason stored with deleted records."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Clean up only recorded Post Relay staged R2 objects."""
    config = load_config(config_path)
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = cleanup_r2_staged_objects_for_draft(
            connection,
            draft_id,
            config.r2_staging,
            execute=execute,
            reason=reason,
        )
    except (R2CleanupSafetyError, R2StagingUploadError) as error:
        raise typer.BadParameter(str(error), param_hint="--config/--execute") from error
    typer.echo(result.to_text())


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


def _resolve_single_publish_image_url(
    connection,
    draft_id: int,
    *,
    image_url: Optional[str],
    from_staged_r2: bool,
    config_path: Path,
) -> str:
    urls = _resolve_publish_image_urls(
        connection,
        draft_id,
        image_urls=[image_url] if image_url else [],
        from_staged_r2=from_staged_r2,
        config_path=config_path,
    )
    if len(urls) != 1:
        raise UnsupportedPublishDraft("Single-image publish validation requires exactly one image URL")
    return urls[0]


def _resolve_publish_image_urls(
    connection,
    draft_id: int,
    *,
    image_urls: list[str],
    from_staged_r2: bool,
    config_path: Path,
) -> list[str]:
    if from_staged_r2:
        if image_urls:
            raise UnsupportedPublishDraft("Use either --from-staged-r2 or explicit --image-url values, not both")
        config = load_config(config_path)
        return resolve_staged_r2_publish_image_urls(connection, draft_id, config.r2_staging)
    if not image_urls:
        raise UnsupportedPublishDraft("Provide --image-url values or use --from-staged-r2")
    return image_urls


def _split_hashtags(hashtags: Optional[str]) -> Optional[list[str]]:
    if hashtags is None:
        return None
    return [tag.strip() for tag in hashtags.split(",") if tag.strip()]


def _split_ints(value: Optional[str]) -> Optional[list[int]]:
    if value is None:
        return None
    result: list[int] = []
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError as error:
            raise typer.BadParameter(
                f"Expected comma-separated integers, got {value!r}",
                param_hint="--keep/--remove",
            ) from error
    return result

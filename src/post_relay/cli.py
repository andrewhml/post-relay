from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import secrets
from typing import Optional

import typer

from post_relay.approvals import (
    DraftNotFound as ApprovalDraftNotFound,
    DraftNotReadyForApproval,
    approve_draft_content,
    edit_draft_content,
    submit_draft_for_review,
)
from post_relay.analytics_feedback import (
    DEFAULT_INSIGHT_METRICS,
    PublishedPostSnapshotNotReady,
    build_analytics_cadence_plan,
    build_feedback_summary,
    build_follower_growth_plan,
    build_follower_growth_summary,
    build_insights_collection_plan,
    collect_and_store_due_analytics,
    collect_and_store_follower_metrics,
    collect_and_store_media_insights,
    record_published_post_snapshot,
    render_analytics_cadence_plan,
    render_due_analytics_collection_result,
    render_due_analytics_dry_run,
    render_feedback_summary,
    render_follower_fetch_dry_run,
    render_follower_growth_summary,
    render_follower_metric_snapshot,
    render_insights_fetch_dry_run,
    render_insights_fetch_error,
    render_media_insight_snapshot,
    render_published_post_snapshot,
)
from post_relay.candidates import build_candidate_groups
from post_relay.config import load_config
from post_relay.context_questions import (
    DraftNotFound as ContextDraftNotFound,
    generate_context_questions_for_draft,
)
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import CandidateNotFound, create_draft_from_candidate
from post_relay.dm_guided_review import DmGuidedReviewError, handle_dm_guided_review_reply
from post_relay.dm_intake import DmIntakeError, handle_dm_intake
from post_relay.dm_operating_loop import DmNextActionError, build_dm_next_action_plan
from post_relay.dm_scheduling import (
    DmSchedulingError,
    handle_dm_publish_approval_reply,
    handle_dm_schedule_reply,
    poll_dm_publish_approval_reply,
    poll_dm_schedule_reply,
    send_dm_publish_approval_prompt,
    send_dm_schedule_prompt,
)
from post_relay.discord_dm import (
    DiscordDmError,
    DiscordSelectionParseError,
    DiscordRestTransport,
    handle_dm_selection_reply,
    load_discord_dm_config_from_env,
    poll_dm_guided_review_reply,
    poll_dm_intake_reply,
    poll_dm_selection_reply,
    send_dm_guided_review_prompt,
    send_dm_selection_prompt,
)
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
from post_relay.guided_draft import (
    DraftNotFound as GuidedDraftNotFound,
    InvalidGuidedDraftPackage,
    accept_guided_draft_package,
    build_guided_draft_package,
)
from post_relay.final_post_artifacts import render_final_post_preview_artifact
from post_relay.final_publish_preview import build_final_publish_preview
from post_relay.indexer import index_photo_sources
from post_relay.location_tags import (
    DraftNotFound as LocationTagDraftNotFound,
    build_location_candidate_review,
    set_draft_location_tag,
    skip_draft_location_tag,
)
from post_relay.meta_graph import (
    AccountDiscoveryResult,
    DiscoveredMetaAccount,
    MetaGraphClient,
    MetaGraphConfig,
    MetaGraphConfigError,
    MetaGraphRequestError,
    TokenExtensionResult,
    build_meta_oauth_authorization_url,
    load_meta_graph_config,
    load_meta_oauth_config,
    update_meta_graph_access_token_env_file,
    update_meta_graph_account_ids_env_file,
    update_meta_graph_oauth_env_file,
)
from post_relay.media_selection import (
    DraftNotFound as MediaSelectionDraftNotFound,
    InvalidMediaSelection,
    apply_draft_crop_feedback,
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
from post_relay.opportunity_checks import execute_opportunity_checks, plan_opportunity_checks
from post_relay.publish_exports import (
    DraftNotFound as PublishExportDraftNotFound,
    UnsupportedLandscapeTreatment,
    UnsupportedPublishExportProfile,
    render_publish_exports_for_draft,
)
from post_relay.post_opportunities import (
    PostOpportunityError,
    convert_post_opportunity_to_draft,
    create_post_opportunity_result,
    dismiss_post_opportunity,
    mark_post_opportunity_dm_sent,
    plan_proactive_opportunity_dm,
    snooze_post_opportunity,
)
from post_relay.repository import (
    get_library_stats,
    list_active_approvals,
    list_candidate_groups,
    list_context_questions,
    list_drafts,
    list_post_opportunities,
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
from post_relay.recommendations import (
    record_caption_feedback,
    render_candidate_rankings,
    render_caption_feedback_result,
    render_caption_style_recommendations,
    render_schedule_recommendations,
    render_signal_baseline,
)
from post_relay.review_artifacts import DraftNotFound as ArtifactDraftNotFound
from post_relay.review_artifacts import (
    OversizedReviewArtifactSet,
    UnsafeArtifactRoot,
    render_review_artifacts_for_draft,
)
from post_relay.review_package import DraftNotFound, build_draft_review_package
from post_relay.scheduled_publish_runner import (
    ScheduledPublishNotReady,
    build_scriptless_scheduled_publish_plan,
    execute_due_scheduled_publish,
    preflight_due_scheduled_publish,
)
from post_relay.scheduled_posts import build_scheduled_post_feedback
from post_relay.scheduling import (
    DraftNotFound as SchedulingDraftNotFound,
    DraftNotReadyForPublishApproval,
    DraftNotReadyForScheduling,
    approve_draft_for_publishing,
    request_publish_approval,
    schedule_draft,
)
from post_relay.setup_doctor import build_setup_doctor_report, render_setup_doctor_report
from post_relay.setup_wizard import render_setup_wizard_result, run_setup_wizard
from post_relay.user_goals import (
    get_active_user_goal,
    list_user_goal_versions,
    render_user_goal,
    render_user_goal_agent_brief,
    upsert_active_user_goal,
)

app = typer.Typer(help="Post Relay local-first Instagram content workflow.")
db_app = typer.Typer(help="Database commands.")
index_app = typer.Typer(help="Media indexing commands.")
library_app = typer.Typer(help="Library inspection commands.")
meta_app = typer.Typer(help="Meta Graph validation commands.")
candidates_app = typer.Typer(help="Candidate post group commands.")
drafts_app = typer.Typer(help="Post lifecycle commands; records still use the existing drafts CLI namespace.")
dm_app = typer.Typer(help="Private DM simulation commands.")
discord_app = typer.Typer(help="Discord DM integration commands.")
opportunities_app = typer.Typer(help="Local post opportunity commands.")
analytics_app = typer.Typer(help="Post-publish analytics and feedback commands.")
goals_app = typer.Typer(help="User/agent goal artifact commands.")
recommendations_app = typer.Typer(help="Local advisory recommendation commands.")
draft_questions_app = typer.Typer(help="Post context question commands.")
draft_artifacts_app = typer.Typer(help="Post review artifact commands.")
draft_final_preview_artifact_app = typer.Typer(help="Post final preview artifact commands.")
draft_publish_exports_app = typer.Typer(help="Post publish export commands.")
app.add_typer(db_app, name="db")
app.add_typer(index_app, name="index")
app.add_typer(library_app, name="library")
app.add_typer(meta_app, name="meta")
app.add_typer(candidates_app, name="candidates")
app.add_typer(drafts_app, name="drafts")
app.add_typer(dm_app, name="dm")
app.add_typer(discord_app, name="discord")
app.add_typer(opportunities_app, name="opportunities")
app.add_typer(analytics_app, name="analytics")
app.add_typer(goals_app, name="goals")
app.add_typer(recommendations_app, name="recommendations")
drafts_app.add_typer(draft_questions_app, name="questions")
drafts_app.add_typer(draft_artifacts_app, name="artifacts")
drafts_app.add_typer(draft_final_preview_artifact_app, name="final-preview-artifact")
drafts_app.add_typer(draft_publish_exports_app, name="publish-exports")

DEFAULT_DB_PATH = Path("data/post_relay.sqlite")


@app.command()
def version() -> None:
    """Print the current Post Relay version."""
    typer.echo("post-relay 0.1.0")


@app.command("doctor")
def setup_doctor(
    config: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Path to photo_sources.yaml."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to private .env file."),
) -> None:
    """Check local setup readiness without making network calls."""
    report = build_setup_doctor_report(config_path=config, db_path=db, env_file=env_file)
    typer.echo(render_setup_doctor_report(report))


@app.command("setup")
def setup_wizard(
    photo_root: Optional[Path] = typer.Option(
        None,
        "--photo-root",
        help="Processed/exported photo folder to use as the first local source.",
    ),
    config: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Path to write photo_sources.yaml."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path to initialize if missing."),
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to write private .env if missing."),
    env_template: Path = typer.Option(Path(".env.example"), "--env-template", help="Template to copy for .env."),
    config_template: Path = typer.Option(
        Path("config/photo_sources.example.yaml"),
        "--config-template",
        help="Template to copy and customize for photo_sources.yaml.",
    ),
    initialize_database: bool = typer.Option(True, "--init-db/--no-init-db", help="Initialize the SQLite database if it is missing."),
) -> None:
    """Create a non-destructive local-first setup without network calls."""
    selected_photo_root = photo_root or Path(typer.prompt("Processed/exported photo folder"))
    result = run_setup_wizard(
        photo_root=selected_photo_root,
        env_file=env_file,
        config_path=config,
        db_path=db,
        env_template=env_template,
        config_template=config_template,
        initialize_database=initialize_database,
    )
    typer.echo(render_setup_wizard_result(result))
    if not result.success:
        raise typer.Exit(code=1)


@goals_app.command("init")
def goals_init(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    title: str = typer.Option(..., "--title", help="Short name for the active user goal."),
    statement: str = typer.Option(..., "--statement", help="North-star goal statement for the user and agent."),
    target_audience: Optional[str] = typer.Option(None, "--target-audience", help="Audience the account is trying to serve."),
    pillar: Optional[list[str]] = typer.Option(None, "--pillar", help="Repeatable content pillar for recommendations."),
    cadence: Optional[str] = typer.Option(None, "--cadence", help="Desired posting cadence."),
    metric: Optional[list[str]] = typer.Option(None, "--metric", help="Repeatable success metric."),
    strategy_note: Optional[str] = typer.Option(None, "--strategy-note", help="Current strategy note for agent behavior."),
    constraint: Optional[list[str]] = typer.Option(None, "--constraint", help="Repeatable safety/product constraint."),
    reviewed_by: Optional[str] = typer.Option(None, "--reviewed-by", help="Person who reviewed/agreed to this goal."),
    change_note: Optional[str] = typer.Option(None, "--change-note", help="Audit note for this version."),
) -> None:
    """Create or update the active local user/agent goal artifact."""
    connection = connect_db(db)
    initialize_db(connection)
    goal = upsert_active_user_goal(
        connection,
        title=title,
        goal_statement=statement,
        target_audience=target_audience,
        content_pillars=pillar or [],
        desired_cadence=cadence,
        success_metrics=metric or [],
        strategy_notes=strategy_note,
        constraints=constraint or [],
        reviewed_by=reviewed_by,
        change_note=change_note,
    )
    versions = list_user_goal_versions(connection, goal.id)
    typer.echo(f"Saved active user goal #{goal.id} ({goal.title}) version {versions[-1].version_number}.")
    typer.echo("This goal is advisory and local-first; it does not mutate posts, approvals, schedules, or publish state.")
    typer.echo("No Discord, R2, or Meta network calls were made.")


@goals_app.command("show")
def goals_show(db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path.")) -> None:
    """Show the active user/agent goal artifact."""
    connection = connect_db(db)
    initialize_db(connection)
    typer.echo(render_user_goal(get_active_user_goal(connection)))


@goals_app.command("agent-brief")
def goals_agent_brief(db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path.")) -> None:
    """Render a compact active-goal brief for future agent recommendations."""
    connection = connect_db(db)
    initialize_db(connection)
    typer.echo(render_user_goal_agent_brief(connection))


@recommendations_app.command("signals")
def recommendations_signals(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Summarize local recommendation signal coverage without side effects."""
    connection = connect_db(db)
    initialize_db(connection)
    typer.echo(render_signal_baseline(connection))


@recommendations_app.command("candidates")
def recommendations_candidates(
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum number of candidate groups to rank."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Rank candidate groups using deterministic local advisory signals."""
    connection = connect_db(db)
    initialize_db(connection)
    typer.echo(render_candidate_rankings(connection, limit=limit))


@recommendations_app.command("schedule")
def recommendations_schedule(
    limit: int = typer.Option(3, "--limit", min=1, help="Maximum number of schedule windows to suggest."),
    now: Optional[str] = typer.Option(None, "--now", help="ISO timestamp to anchor deterministic schedule suggestions."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Suggest schedule windows using local advisory signals without scheduling posts."""
    connection = connect_db(db)
    initialize_db(connection)
    typer.echo(render_schedule_recommendations(connection, now=now, limit=limit))



@recommendations_app.command("caption-feedback")
def recommendations_caption_feedback(
    post_id: int = typer.Option(..., "--post-id", help="Post id to attach qualitative caption feedback to."),
    sentiment: str = typer.Option(..., "--sentiment", help="Short sentiment label, e.g. positive or needs_work."),
    signal: str = typer.Option(..., "--signal", help="Short feedback signal label, e.g. hook_first or too_generic."),
    note: str = typer.Option(..., "--note", help="Short human feedback note."),
    reviewed_by: Optional[str] = typer.Option(None, "--reviewed-by", help="Reviewer name or handle."),
    db_path: Path = typer.Option(Path("data/post_relay.sqlite"), "--db", help="SQLite database path."),
):
    """Record lightweight qualitative caption feedback for future advisory recommendations."""
    connection = connect_db(db_path)
    initialize_db(connection)
    try:
        result = record_caption_feedback(
            connection,
            post_id=post_id,
            sentiment=sentiment,
            signal=signal,
            note=note,
            reviewed_by=reviewed_by,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(render_caption_feedback_result(result))

@recommendations_app.command("caption-style")
def recommendations_caption_style(
    post_id: Optional[int] = typer.Option(None, "--post-id", "--draft-id", help="Optional post id to compare against local caption feedback."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Advise caption style from local approvals, revisions, and published feedback without rewriting copy."""
    connection = connect_db(db)
    initialize_db(connection)
    typer.echo(render_caption_style_recommendations(connection, post_id=post_id))


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
    photo_plural = "" if result.enriched_count == 1 else "s"
    typer.echo(f"Enriched local metadata for {result.enriched_count} photo{photo_plural}.")
    typer.echo("No network calls were made.")


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


@analytics_app.command("snapshot")
def analytics_snapshot(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    actual_published_at: Optional[str] = typer.Option(
        None,
        "--actual-published-at",
        help="Actual publish timestamp to persist; defaults to current local time.",
    ),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Persist and render a local post-publish audit snapshot without network calls."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        snapshot = record_published_post_snapshot(
            connection,
            draft_id,
            actual_published_at=actual_published_at,
        )
    except PublishedPostSnapshotNotReady as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(render_published_post_snapshot(snapshot))


@analytics_app.command("insights-plan")
def analytics_insights_plan(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render a read-only Meta insights collection plan without network calls."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = build_insights_collection_plan(connection, draft_id)
    except PublishedPostSnapshotNotReady as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(plan.to_text())


@analytics_app.command("feedback-summary")
def analytics_feedback_summary(
    draft_id: Optional[int] = typer.Option(None, "--post-id", "--draft-id", help="Optional post id to summarize (legacy --draft-id alias)."),
    limit: int = typer.Option(10, "--limit", help="Recent published snapshots to summarize when --post-id is omitted."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render local-only recommendation feedback from stored snapshots and insights."""
    connection = connect_db(db)
    initialize_db(connection)
    summary = build_feedback_summary(connection, draft_id=draft_id, limit=limit)
    typer.echo(render_feedback_summary(summary))


@analytics_app.command("cadence-plan")
def analytics_cadence_plan(
    now: Optional[str] = typer.Option(None, "--now", help="Deterministic current timestamp for due-window planning."),
    instagram_account_id: Optional[str] = typer.Option(None, "--instagram-account-id", help="Instagram professional account id for weekly account analytics planning."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render a no-network analytics cadence plan for due post/account read-only checks."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = build_analytics_cadence_plan(
            connection,
            now=now,
            instagram_account_id=instagram_account_id,
            db_cli_path=db.as_posix(),
        )
    except ValueError as error:
        typer.echo(f"Invalid analytics cadence timestamp: {error}")
        raise typer.Exit(code=1) from error
    typer.echo(render_analytics_cadence_plan(plan))


@analytics_app.command("collect-due")
def analytics_collect_due(
    now: Optional[str] = typer.Option(None, "--now", help="Deterministic collection timestamp and due-window clock."),
    instagram_account_id: Optional[str] = typer.Option(None, "--instagram-account-id", help="Instagram professional account id for weekly account analytics collection."),
    metric: list[str] = typer.Option(None, "--metric", help="Insight metric to collect for due posts; repeat for multiple metrics."),
    execute: bool = typer.Option(False, "--execute", help="Actually call read-only Meta endpoints and store due analytics."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
) -> None:
    """Collect due read-only post/account analytics only when --execute is explicit."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = build_analytics_cadence_plan(
            connection,
            now=now,
            instagram_account_id=instagram_account_id,
            db_cli_path=db.as_posix(),
        )
    except ValueError as error:
        typer.echo(f"Invalid analytics collection timestamp: {error}")
        raise typer.Exit(code=1) from error
    if not execute:
        typer.echo(render_due_analytics_dry_run(plan))
        return
    config = None
    try:
        config = load_meta_graph_config(env_file=env_file)
        client = MetaGraphClient(config)
        result = collect_and_store_due_analytics(
            connection,
            now=now,
            instagram_account_id=instagram_account_id,
            metrics=metric or DEFAULT_INSIGHT_METRICS,
            client=client,
        )
    except (MetaGraphConfigError, MetaGraphRequestError, PublishedPostSnapshotNotReady) as error:
        token = config.access_token if config is not None else None
        typer.echo(render_insights_fetch_error(error, token=token))
        raise typer.Exit(code=1) from error
    typer.echo(render_due_analytics_collection_result(result))


@analytics_app.command("follower-summary")
def analytics_follower_summary(
    target_followers: int = typer.Option(5000, "--target-followers", help="Follower goal for progress reporting."),
    limit: int = typer.Option(10, "--limit", help="Recent account metric snapshots to summarize."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render local follower-growth progress from stored account metric snapshots."""
    connection = connect_db(db)
    initialize_db(connection)
    summary = build_follower_growth_summary(connection, target_followers=target_followers, limit=limit)
    typer.echo(render_follower_growth_summary(summary))


@analytics_app.command("follower-fetch")
def analytics_follower_fetch(
    instagram_account_id: Optional[str] = typer.Option(None, "--instagram-account-id", help="Instagram professional account id to inspect."),
    collected_at: Optional[str] = typer.Option(None, "--collected-at", help="Collection timestamp to persist; defaults to current local time."),
    execute: bool = typer.Option(False, "--execute", help="Actually call the read-only Meta account endpoint and store follower metrics."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
) -> None:
    """Fetch/store read-only follower metrics only when --execute is explicit."""
    connection = connect_db(db)
    initialize_db(connection)
    config = None
    if instagram_account_id is None:
        try:
            config = load_meta_graph_config(env_file=env_file)
        except MetaGraphConfigError as error:
            typer.echo(render_insights_fetch_error(error))
            raise typer.Exit(code=1) from error
        instagram_account_id = config.instagram_account_id
    if not instagram_account_id:
        typer.echo("Instagram account id is required via --instagram-account-id or POST_RELAY_INSTAGRAM_ACCOUNT_ID.")
        raise typer.Exit(code=1)
    plan = build_follower_growth_plan(instagram_account_id)
    if not execute:
        typer.echo(render_follower_fetch_dry_run(plan))
        return
    try:
        if config is None:
            config = load_meta_graph_config(env_file=env_file)
        client = MetaGraphClient(config)
        record = collect_and_store_follower_metrics(
            connection,
            instagram_account_id,
            client=client,
            collected_at=collected_at,
        )
    except (MetaGraphConfigError, MetaGraphRequestError) as error:
        token = config.access_token if config is not None else None
        typer.echo(render_insights_fetch_error(error, token=token))
        raise typer.Exit(code=1) from error
    typer.echo(render_follower_metric_snapshot(record))


@analytics_app.command("insights-fetch")
def analytics_insights_fetch(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    metric: list[str] = typer.Option(None, "--metric", help="Insight metric to collect; repeat for multiple metrics."),
    collected_at: Optional[str] = typer.Option(None, "--collected-at", help="Collection timestamp to persist; defaults to current local time."),
    execute: bool = typer.Option(False, "--execute", help="Actually call the read-only Meta insights endpoint and store results."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
) -> None:
    """Fetch/store read-only Meta insights only when --execute is explicit."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = build_insights_collection_plan(connection, draft_id)
    except PublishedPostSnapshotNotReady as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    metrics = metric or plan.metrics
    if not execute:
        typer.echo(render_insights_fetch_dry_run(plan))
        return
    config = None
    try:
        config = load_meta_graph_config(env_file=env_file)
        client = MetaGraphClient(config)
        record = collect_and_store_media_insights(
            connection,
            draft_id,
            client=client,
            metrics=metrics,
            collected_at=collected_at,
        )
    except (MetaGraphConfigError, MetaGraphRequestError, PublishedPostSnapshotNotReady) as error:
        token = config.access_token if config is not None else None
        typer.echo(render_insights_fetch_error(error, token=token))
        raise typer.Exit(code=1) from error
    typer.echo(render_media_insight_snapshot(record))


@meta_app.command("oauth-login")
def meta_oauth_login(
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    redirect_uri: str = typer.Option("http://localhost:8765/callback", "--redirect-uri", help="OAuth redirect URI configured for the Meta app."),
    state: Optional[str] = typer.Option(None, "--state", help="OAuth state value. Generated automatically when omitted."),
    code: Optional[str] = typer.Option(None, "--code", help="Authorization code copied from the redirect callback URL."),
    execute: bool = typer.Option(False, "--execute", help="Exchange the authorization code for a user token."),
    update_env: bool = typer.Option(False, "--update-env", help="Save the returned user token and optional account IDs in the env file."),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Discovered Facebook Page ID to save with --update-env."),
    instagram_account_id: Optional[str] = typer.Option(None, "--instagram-account-id", help="Discovered Instagram account ID to save with --update-env."),
) -> None:
    """Guide trusted testers through Meta OAuth login while keeping tokens local."""
    try:
        config = load_meta_oauth_config(env_file=env_file)
    except MetaGraphConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error

    resolved_state = state or secrets.token_urlsafe(24)
    login_url = build_meta_oauth_authorization_url(
        config,
        redirect_uri=redirect_uri,
        state=resolved_state,
    )
    if not execute:
        typer.echo("Meta OAuth login (dry run)")
        typer.echo(f"Authorization URL: {login_url}")
        typer.echo(f"Redirect URI: {redirect_uri}")
        typer.echo(f"State: {resolved_state}")
        typer.echo("Requested scopes: pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish")
        typer.echo("App secret: <redacted>")
        typer.echo("No network calls were made.")
        typer.echo("No env file was changed.")
        typer.echo("Publishing endpoints called: no")
        return

    if not code:
        raise typer.BadParameter("--execute requires --code from the OAuth redirect", param_hint="--code")
    if update_env and env_file is None:
        raise typer.BadParameter("--update-env requires an --env-file path", param_hint="--env-file")
    if update_env and ((page_id and not instagram_account_id) or (instagram_account_id and not page_id)):
        raise typer.BadParameter(
            "Saving account IDs requires both --page-id and --instagram-account-id",
            param_hint="--page-id/--instagram-account-id",
        )

    client = MetaGraphClient(config)
    try:
        token_result = client.exchange_oauth_authorization_code(
            code=code,
            redirect_uri=redirect_uri,
        )
        discovery_result = MetaGraphClient(
            MetaGraphConfig(
                access_token=token_result.access_token,
                page_id=page_id,
                instagram_account_id=instagram_account_id,
                app_id=config.app_id,
                app_secret=config.app_secret,
                base_url=config.base_url,
                api_version=config.api_version,
            )
        ).discover_accounts()
    except (MetaGraphConfigError, MetaGraphRequestError) as error:
        raise typer.BadParameter(str(error), param_hint="--code") from error

    env_updated = False
    if update_env:
        assert env_file is not None
        update_meta_graph_oauth_env_file(
            env_file,
            access_token=token_result.access_token,
            page_id=page_id,
            instagram_account_id=instagram_account_id,
        )
        env_updated = True

    typer.echo("Meta OAuth login completed")
    typer.echo(token_result.to_text(env_updated=env_updated))
    typer.echo(discovery_result.to_text(env_updated=env_updated))


@meta_app.command("token-extend")
def meta_token_extend(
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    execute: bool = typer.Option(False, "--execute", help="Call Meta Graph OAuth token exchange endpoint."),
    update_env: bool = typer.Option(False, "--update-env", help="Replace POST_RELAY_USER_ACCESS_TOKEN in the env file with the extended token."),
) -> None:
    """Exchange a valid short-lived Meta user token for a long-lived token."""
    try:
        config = load_meta_graph_config(env_file=env_file)
    except MetaGraphConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error

    client = MetaGraphClient(config)
    if not execute:
        typer.echo("Meta Graph user token extension (dry run)")
        typer.echo(config.safe_summary())
        typer.echo(
            f"Endpoint: {config.base_url.rstrip('/')}/{config.api_version}/oauth/access_token"
        )
        typer.echo("Grant type: fb_exchange_token")
        typer.echo("Access token and app secret: <redacted>")
        typer.echo("No network calls were made.")
        typer.echo("No env file was changed.")
        typer.echo("Publishing endpoints called: no")
        return
    if update_env and env_file is None:
        raise typer.BadParameter("--update-env requires an --env-file path", param_hint="--env-file")
    try:
        result = client.exchange_long_lived_user_token()
    except (MetaGraphConfigError, MetaGraphRequestError) as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error
    env_updated = False
    if update_env:
        if env_file is None:
            raise typer.BadParameter("--update-env requires an --env-file path", param_hint="--env-file")
        update_meta_graph_access_token_env_file(env_file, result.access_token)
        env_updated = True
    typer.echo(result.to_text(env_updated=env_updated))


@meta_app.command("discover-accounts")
def meta_discover_accounts(
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print sanitized planned read-only requests without calling Meta."),
    execute: bool = typer.Option(False, "--execute", help="Call read-only Meta Graph account discovery endpoints."),
    update_env: bool = typer.Option(False, "--update-env", help="Update non-secret Page and Instagram account IDs in the env file."),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Discovered Facebook Page ID to save with --update-env."),
    instagram_account_id: Optional[str] = typer.Option(None, "--instagram-account-id", help="Discovered Instagram account ID to save with --update-env."),
) -> None:
    """Discover visible Facebook Pages and linked Instagram accounts."""
    try:
        config = load_meta_graph_config(env_file=env_file)
    except MetaGraphConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error

    client = MetaGraphClient(config)
    if dry_run or not execute:
        typer.echo("Meta Graph account discovery (dry run)")
        typer.echo(config.safe_summary())
        typer.echo("Read-only requests:")
        for url in client.discovery_dry_run_urls():
            typer.echo(f"  - {url}")
        typer.echo("No network calls were made.")
        typer.echo("No env file was changed.")
        typer.echo("Publishing endpoints called: no")
        return

    if update_env:
        if env_file is None:
            raise typer.BadParameter("--update-env requires an --env-file path", param_hint="--env-file")
        if not page_id or not instagram_account_id:
            raise typer.BadParameter(
                "--update-env requires --page-id and --instagram-account-id",
                param_hint="--page-id/--instagram-account-id",
            )
    try:
        result = client.discover_accounts()
    except MetaGraphRequestError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error

    env_updated = False
    if update_env:
        assert env_file is not None
        update_meta_graph_account_ids_env_file(
            env_file,
            page_id=str(page_id),
            instagram_account_id=str(instagram_account_id),
        )
        env_updated = True
    typer.echo(result.to_text(env_updated=env_updated))


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
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Ready-to-publish single-image post id (legacy --draft-id alias)."),
    image_url: Optional[str] = typer.Option(None, "--image-url", help="Public HTTPS image URL for Meta container creation."),
    from_staged_r2: bool = typer.Option(False, "--from-staged-r2", help="Resolve the publish image URL from uploaded R2 staged media records."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Record and print the sanitized plan without calling Meta."),
    execute: bool = typer.Option(False, "--execute", help="Actually create, poll, and publish through Meta Graph."),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic schedule enforcement checks."),
    publish_now: bool = typer.Option(False, "--publish-now", help="Explicitly bypass scheduled_for and publish immediately; use only with active-session authorization."),
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
            raise typer.BadParameter(str(error), param_hint="--post-id") from error
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
            now=now,
            publish_now=publish_now,
        )
    except (PublishDraftNotFound, DraftNotReadyForImagePublish, UnsupportedPublishDraft) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except PublishValidationError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error
    typer.echo(result.to_text())


@meta_app.command("validate-carousel-publish")
def meta_validate_carousel_publish(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Ready-to-publish carousel post id (legacy --draft-id alias)."),
    image_urls: Optional[list[str]] = typer.Option(
        None, "--image-url", help="Public HTTPS image URL for each carousel image, in post order."
    ),
    from_staged_r2: bool = typer.Option(False, "--from-staged-r2", help="Resolve ordered publish image URLs from uploaded R2 staged media records."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Record and print the sanitized plan without calling Meta."),
    execute: bool = typer.Option(False, "--execute", help="Actually create, poll, and publish through Meta Graph."),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic schedule enforcement checks."),
    publish_now: bool = typer.Option(False, "--publish-now", help="Explicitly bypass scheduled_for and publish immediately; use only with active-session authorization."),
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
            raise typer.BadParameter(str(error), param_hint="--post-id") from error
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
            now=now,
            publish_now=publish_now,
        )
    except (PublishDraftNotFound, DraftNotReadyForImagePublish, UnsupportedPublishDraft) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except PublishValidationError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error
    typer.echo(result.to_text())


@meta_app.command("final-publish-preview")
def meta_final_publish_preview(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Ready-to-publish post id (legacy --draft-id alias)."),
    from_staged_r2: bool = typer.Option(False, "--from-staged-r2", help="Resolve ordered publish image URLs from uploaded R2 staged media records."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print the exact Meta-bound caption/media preview plus local-only metadata."""
    if not from_staged_r2:
        raise typer.BadParameter("Final publish preview currently requires --from-staged-r2", param_hint="--from-staged-r2")
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_config(config_path)
        result = build_final_publish_preview(connection, draft_id, r2_config=config.r2_staging)
    except R2StagingConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    except (PublishDraftNotFound, UnsupportedPublishDraft) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(result.to_text())


@meta_app.command("publish-scheduled")
def meta_publish_scheduled(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Ready-to-publish scheduled post id (legacy --draft-id alias)."),
    from_staged_r2: bool = typer.Option(False, "--from-staged-r2", help="Resolve ordered publish image URLs from uploaded R2 staged media records."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path for execute mode."),
    execute: bool = typer.Option(False, "--execute", help="Actually publish through Meta Graph after due preflight passes."),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic schedule runner checks."),
) -> None:
    """Preflight or execute a due scheduled publish using uploaded staged R2 media."""
    if not from_staged_r2:
        raise typer.BadParameter("Scheduled publish runner currently requires --from-staged-r2", param_hint="--from-staged-r2")
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_config(config_path)
    except R2StagingConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    if not execute:
        try:
            result = preflight_due_scheduled_publish(
                connection,
                draft_id,
                r2_config=config.r2_staging,
                now=now,
            )
        except ScheduledPublishNotReady as error:
            raise typer.BadParameter(str(error), param_hint="--post-id") from error
        typer.echo(result.to_text())
        return

    try:
        meta_config = load_meta_graph_config(env_file=env_file)
    except MetaGraphConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--env-file") from error
    try:
        result = execute_due_scheduled_publish(
            connection,
            draft_id,
            r2_config=config.r2_staging,
            client=MetaGraphClient(meta_config),
            now=now,
        )
    except ScheduledPublishNotReady as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(result.to_text())


@meta_app.command("unattended-publish-plan")
def meta_unattended_publish_plan(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Ready-to-publish scheduled post id (legacy --draft-id alias)."),
    from_staged_r2: bool = typer.Option(False, "--from-staged-r2", help="Resolve ordered publish image URLs from uploaded R2 staged media records."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Private .env file path for scheduled execute mode."),
) -> None:
    """Verify a scheduled post is ready for unattended publish and print a scriptless scheduled-job command."""
    if not from_staged_r2:
        raise typer.BadParameter("Unattended publish planning currently requires --from-staged-r2", param_hint="--from-staged-r2")
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_config(config_path)
        result = build_scriptless_scheduled_publish_plan(
            connection,
            draft_id,
            r2_config=config.r2_staging,
            config_path=config_path,
            db_path=db,
            env_file=env_file,
        )
    except R2StagingConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    except ScheduledPublishNotReady as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
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


@opportunities_app.command("check")
def opportunities_check(
    execute: bool = typer.Option(False, "--execute", help="Persist planned local opportunities."),
    now: Optional[str] = typer.Option(None, "--now", help="ISO timestamp for deterministic local checks."),
    cadence_due_after_days: int = typer.Option(3, "--cadence-due-after-days", help="Days after last scheduled/posted item before cadence is due."),
    inactivity_after_days: int = typer.Option(14, "--inactivity-after-days", help="Days threshold for no local posting history."),
    include_new_media: bool = typer.Option(True, "--include-new-media/--no-new-media", help="Include indexed candidate media checks."),
    max_new_media_candidates: int = typer.Option(5, "--max-new-media-candidates", help="Maximum undrafted candidate media opportunities to plan."),
    manual_trigger_type: Optional[str] = typer.Option(None, "--manual-trigger-type", help="Optional manual opportunity trigger type."),
    manual_trigger_key: Optional[str] = typer.Option(None, "--manual-trigger-key", help="Optional manual opportunity trigger key."),
    manual_title: Optional[str] = typer.Option(None, "--manual-title", help="Optional manual opportunity title."),
    manual_summary: Optional[str] = typer.Option(None, "--manual-summary", help="Optional manual opportunity summary."),
    manual_rationale: Optional[str] = typer.Option(None, "--manual-rationale", help="Optional manual opportunity rationale."),
    manual_suggested_next_action: Optional[str] = typer.Option(None, "--manual-suggested-next-action", help="Optional manual opportunity next action."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Run safe local opportunity trigger checks without sending DMs."""
    connection = connect_db(db)
    initialize_db(connection)
    check_now = now or datetime.now(timezone.utc).isoformat()
    try:
        if execute:
            result = execute_opportunity_checks(
                connection,
                now=check_now,
                cadence_due_after_days=cadence_due_after_days,
                inactivity_after_days=inactivity_after_days,
                include_new_media=include_new_media,
                max_new_media_candidates=max_new_media_candidates,
                manual_trigger_type=manual_trigger_type,
                manual_trigger_key=manual_trigger_key,
                manual_title=manual_title,
                manual_summary=manual_summary,
                manual_rationale=manual_rationale,
                manual_suggested_next_action=manual_suggested_next_action,
            )
        else:
            result = plan_opportunity_checks(
                connection,
                now=check_now,
                cadence_due_after_days=cadence_due_after_days,
                inactivity_after_days=inactivity_after_days,
                include_new_media=include_new_media,
                max_new_media_candidates=max_new_media_candidates,
                manual_trigger_type=manual_trigger_type,
                manual_trigger_key=manual_trigger_key,
                manual_title=manual_title,
                manual_summary=manual_summary,
                manual_rationale=manual_rationale,
                manual_suggested_next_action=manual_suggested_next_action,
            )
    except (ValueError, PostOpportunityError) as error:
        raise typer.BadParameter(str(error), param_hint="--manual-trigger-type/--now") from error
    typer.echo(result.to_text())


@opportunities_app.command("create")
def opportunities_create(
    trigger_type: str = typer.Option(..., "--trigger-type", help="Opportunity trigger type."),
    trigger_key: str = typer.Option(..., "--trigger-key", help="Stable dedupe key for the trigger."),
    title: str = typer.Option(..., "--title", help="Human-readable opportunity title."),
    summary: str = typer.Option(..., "--summary", help="Sanitized summary of the opportunity."),
    rationale: str = typer.Option(..., "--rationale", help="Why this opportunity is worth considering."),
    suggested_next_action: str = typer.Option(..., "--suggested-next-action", help="Concrete next action to offer Andrew."),
    candidate_id: Optional[int] = typer.Option(None, "--candidate-id", help="Optional candidate group to link."),
    due_at: Optional[str] = typer.Option(None, "--due-at", help="Optional due time/window."),
    expires_at: Optional[str] = typer.Option(None, "--expires-at", help="Optional expiration time/window."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Create or dedupe a local post opportunity without sending DMs."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = create_post_opportunity_result(
            connection,
            trigger_type=trigger_type,
            trigger_key=trigger_key,
            title=title,
            summary=summary,
            rationale=rationale,
            suggested_next_action=suggested_next_action,
            candidate_group_id=candidate_id,
            due_at=due_at,
            expires_at=expires_at,
        )
    except PostOpportunityError as error:
        raise typer.BadParameter(str(error), param_hint="--trigger-type/--trigger-key") from error
    connection.commit()
    typer.echo(result.to_text())


@opportunities_app.command("list")
def opportunities_list(
    status: Optional[str] = typer.Option(None, "--status", help="Optional opportunity status filter."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """List local post opportunities."""
    connection = connect_db(db)
    initialize_db(connection)
    opportunities = list_post_opportunities(connection, status=status)
    if not opportunities:
        typer.echo("No post opportunities found. No Discord or Meta network calls were made.")
        return
    for opportunity in opportunities:
        candidate = f", candidate #{opportunity.candidate_group_id}" if opportunity.candidate_group_id else ""
        draft = f", post #{opportunity.draft_id}" if opportunity.draft_id else ""
        typer.echo(
            f"#{opportunity.id} {opportunity.title} — {opportunity.trigger_type}, {opportunity.status}{candidate}{draft}"
        )
    typer.echo("No Discord or Meta network calls were made.")


@opportunities_app.command("dm-plan")
def opportunities_dm_plan(
    opportunity_id: int = typer.Option(..., "--opportunity-id", help="Opportunity id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render an operator-approved proactive DM plan without sending Discord."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = plan_proactive_opportunity_dm(connection, opportunity_id)
    except PostOpportunityError as error:
        raise typer.BadParameter(str(error), param_hint="--opportunity-id") from error
    typer.echo(plan.to_text())


@opportunities_app.command("mark-dm-sent")
def opportunities_mark_dm_sent(
    opportunity_id: int = typer.Option(..., "--opportunity-id", help="Opportunity id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Mark an opportunity as proactively DM-sent after an explicitly authorized send."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        opportunity = mark_post_opportunity_dm_sent(connection, opportunity_id)
    except PostOpportunityError as error:
        raise typer.BadParameter(str(error), param_hint="--opportunity-id") from error
    connection.commit()
    typer.echo(
        f"Post opportunity #{opportunity.id} marked DM sent. No Discord, R2, or Meta network calls were made."
    )


@opportunities_app.command("dismiss")
def opportunities_dismiss(
    opportunity_id: int = typer.Option(..., "--opportunity-id", help="Opportunity id."),
    reason: Optional[str] = typer.Option(None, "--reason", help="Dismissal reason."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Dismiss a local post opportunity without sending DMs."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        opportunity = dismiss_post_opportunity(connection, opportunity_id, reason=reason)
    except PostOpportunityError as error:
        raise typer.BadParameter(str(error), param_hint="--opportunity-id") from error
    connection.commit()
    typer.echo(f"Post opportunity #{opportunity.id} dismissed. No Discord or Meta network calls were made.")


@opportunities_app.command("snooze")
def opportunities_snooze(
    opportunity_id: int = typer.Option(..., "--opportunity-id", help="Opportunity id."),
    snoozed_until: str = typer.Option(..., "--until", help="When to revisit this opportunity."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Snooze a local post opportunity without sending DMs."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        opportunity = snooze_post_opportunity(connection, opportunity_id, snoozed_until=snoozed_until)
    except PostOpportunityError as error:
        raise typer.BadParameter(str(error), param_hint="--opportunity-id/--until") from error
    connection.commit()
    typer.echo(
        f"Post opportunity #{opportunity.id} snoozed until {opportunity.snoozed_until}. No Discord or Meta network calls were made."
    )


@opportunities_app.command("convert-to-draft")
def opportunities_convert_to_draft(
    opportunity_id: int = typer.Option(..., "--opportunity-id", help="Opportunity id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Convert a candidate-linked opportunity into a local draft."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        opportunity = convert_post_opportunity_to_draft(connection, opportunity_id)
    except PostOpportunityError as error:
        raise typer.BadParameter(str(error), param_hint="--opportunity-id") from error
    connection.commit()
    typer.echo(
        f"Post opportunity #{opportunity.id} converted to post #{opportunity.draft_id}. No Discord or Meta network calls were made."
    )


@dm_app.command("intake")
def dm_intake(
    message: str = typer.Option(..., "--message", help="DM-style text from Andrew."),
    discord_channel_id: Optional[str] = typer.Option(None, "--discord-channel-id", help="Sanitized Discord DM/channel id for local thread reuse."),
    draft_id: Optional[int] = typer.Option(None, "--post-id", "--draft-id", help="Optional active post id to attach context to (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Simulate user-initiated private DM intake without calling Discord."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = handle_dm_intake(
            connection,
            message,
            discord_channel_id=discord_channel_id,
            draft_id=draft_id,
        )
    except DmIntakeError as error:
        raise typer.BadParameter(str(error), param_hint="--message/--post-id") from error
    typer.echo(result.to_text())


@dm_app.command("next-action")
def dm_next_action(
    draft_id: Optional[int] = typer.Option(None, "--post-id", "--draft-id", help="Optional post id to plan from (legacy --draft-id alias)."),
    discord_channel_id: Optional[str] = typer.Option(None, "--discord-channel-id", help="Optional private DM channel id to resume an active local thread."),
    target_count: int = typer.Option(5, "--target-count", help="Preferred photo-selection count when the next step is media selection."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render the next safe private-DM operating-loop action without network calls."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = build_dm_next_action_plan(
            connection,
            draft_id=draft_id,
            discord_channel_id=discord_channel_id,
            target_count=target_count,
        )
    except DmNextActionError as error:
        raise typer.BadParameter(str(error), param_hint="--post-id/--discord-channel-id") from error
    typer.echo(plan.to_text())


@discord_app.command("dm-intake-poll")
def discord_dm_intake_poll(
    after_message_id: Optional[str] = typer.Option(
        None,
        "--after-message-id",
        help="Only inspect Discord DMs after this message id. Optional for user-initiated intake.",
    ),
    draft_id: Optional[int] = typer.Option(None, "--post-id", "--draft-id", help="Optional active post id to attach context to (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Poll Andrew's private Discord DM for a natural user-initiated Post Relay message."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = poll_dm_intake_reply(
            connection,
            target_user_id=config.target_user_id,
            after_message_id=after_message_id,
            draft_id=draft_id,
            transport=DiscordRestTransport(config.bot_token, api_base_url=config.api_base_url),
        )
    except DiscordDmError as error:
        raise typer.BadParameter(str(error), param_hint="--after-message-id/--post-id") from error
    typer.echo(result.confirmation_text)


@discord_app.command("dm-selection-send")
def discord_dm_selection_send(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    target_count: int = typer.Option(..., "--target-count", help="Number of photos Andrew should select."),
    post_type: Optional[str] = typer.Option(None, "--post-type", help="Optional post type: single_image, carousel, or reel."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Send a live private Discord DM selection prompt using env-configured bot credentials."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = send_dm_selection_prompt(
            connection,
            draft_id,
            target_count=target_count,
            post_type=post_type,
            config=config,
        )
    except (DiscordDmError, DiscordSelectionDraftNotFound, InvalidDiscordSelection) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id/--target-count") from error
    typer.echo(result.to_text())


@discord_app.command("dm-selection-poll")
def discord_dm_selection_poll(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    channel_id: str = typer.Option(..., "--channel-id", help="Discord DM channel id returned by dm-selection-send."),
    target_count: int = typer.Option(..., "--target-count", help="Expected selected photo count."),
    after_message_id: Optional[str] = typer.Option(None, "--after-message-id", help="Only inspect Discord replies after this message id."),
    post_type: Optional[str] = typer.Option(None, "--post-type", help="Optional post type: single_image, carousel, or reel."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Poll a private Discord DM for Andrew's selection reply and send a confirmation."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = poll_dm_selection_reply(
            connection,
            draft_id,
            channel_id=channel_id,
            target_count=target_count,
            target_user_id=config.target_user_id,
            after_message_id=after_message_id,
            post_type=post_type,
            transport=DiscordRestTransport(config.bot_token, api_base_url=config.api_base_url),
        )
    except (DiscordDmError, DiscordSelectionParseError) as error:
        raise typer.BadParameter(str(error), param_hint="--channel-id/--post-id") from error
    typer.echo(result.confirmation_text)


@discord_app.command("dm-selection-apply")
def discord_dm_selection_apply(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    message: str = typer.Option(..., "--message", help="Andrew's DM reply, e.g. 'select 3,1,5 lead 3'."),
    target_count: int = typer.Option(..., "--target-count", help="Expected selected photo count."),
    post_type: Optional[str] = typer.Option(None, "--post-type", help="Optional post type: single_image, carousel, or reel."),
    discord_channel_id: Optional[str] = typer.Option(None, "--discord-channel-id", help="Sanitized Discord DM channel id for local thread update."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Apply a private-DM selection reply locally without calling Discord or Meta."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = handle_dm_selection_reply(
            connection,
            draft_id,
            message,
            target_count=target_count,
            post_type=post_type,
            discord_channel_id=discord_channel_id,
        )
    except (DiscordDmError, DiscordSelectionParseError) as error:
        raise typer.BadParameter(str(error), param_hint="--message") from error
    typer.echo(result.to_text())


@discord_app.command("dm-schedule-send")
def discord_dm_schedule_send(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Approved post id (legacy --draft-id alias)."),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic local testing."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Send a live private Discord DM schedule prompt using env-configured bot credentials."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = send_dm_schedule_prompt(
            connection,
            draft_id,
            now=now,
            config=config,
            transport=DiscordRestTransport(config.bot_token, api_base_url=config.api_base_url),
        )
    except (DiscordDmError, DmSchedulingError) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(result.to_text())


@discord_app.command("dm-schedule-poll")
def discord_dm_schedule_poll(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    channel_id: str = typer.Option(..., "--channel-id", help="Discord DM channel id returned by dm-schedule-send."),
    after_message_id: str = typer.Option(..., "--after-message-id", help="Only inspect Discord replies after this prompt message id."),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic local testing."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Poll a private Discord DM for Andrew's schedule reply and send a confirmation."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = poll_dm_schedule_reply(
            connection,
            draft_id,
            channel_id=channel_id,
            target_user_id=config.target_user_id,
            after_message_id=after_message_id,
            now=now,
            transport=DiscordRestTransport(config.bot_token, api_base_url=config.api_base_url),
        )
    except (DiscordDmError, DmSchedulingError) as error:
        raise typer.BadParameter(str(error), param_hint="--channel-id/--post-id") from error
    typer.echo(result.confirmation_text)


@discord_app.command("dm-schedule-apply")
def discord_dm_schedule_apply(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    message: str = typer.Option(..., "--message", help="Andrew's DM schedule reply."),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic local testing."),
    discord_channel_id: Optional[str] = typer.Option(None, "--discord-channel-id", help="Sanitized Discord DM channel id for local thread update."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Apply a private-DM schedule reply locally without calling Discord or Meta."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = handle_dm_schedule_reply(
            connection,
            draft_id,
            message,
            now=now,
            discord_channel_id=discord_channel_id,
        )
    except DmSchedulingError as error:
        raise typer.BadParameter(str(error), param_hint="--message/--post-id") from error
    typer.echo(result.to_text())


@discord_app.command("dm-publish-approval-send")
def discord_dm_publish_approval_send(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Scheduled post id (legacy --draft-id alias)."),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic local testing."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Send a live private Discord DM final publish approval prompt using env-configured bot credentials."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = send_dm_publish_approval_prompt(
            connection,
            draft_id,
            now=now,
            config=config,
            transport=DiscordRestTransport(config.bot_token, api_base_url=config.api_base_url),
        )
    except (DiscordDmError, DmSchedulingError) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(result.to_text())


@discord_app.command("dm-publish-approval-poll")
def discord_dm_publish_approval_poll(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    channel_id: str = typer.Option(..., "--channel-id", help="Discord DM channel id returned by dm-publish-approval-send."),
    after_message_id: str = typer.Option(..., "--after-message-id", help="Only inspect Discord replies after this prompt/confirmation message id."),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic local testing."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Poll a private Discord DM for final publish approval and send a confirmation."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = poll_dm_publish_approval_reply(
            connection,
            draft_id,
            channel_id=channel_id,
            target_user_id=config.target_user_id,
            after_message_id=after_message_id,
            now=now,
            transport=DiscordRestTransport(config.bot_token, api_base_url=config.api_base_url),
        )
    except (DiscordDmError, DmSchedulingError) as error:
        raise typer.BadParameter(str(error), param_hint="--channel-id/--post-id") from error
    typer.echo(result.confirmation_text)


@discord_app.command("dm-publish-approval-apply")
def discord_dm_publish_approval_apply(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Scheduled post id (legacy --draft-id alias)."),
    message: str = typer.Option(
        ...,
        "--message",
        help="Andrew's final approval reply, e.g. 'confirm publish approval for post #1'.",
    ),
    now: Optional[str] = typer.Option(None, "--now", help="Override current time for deterministic local testing."),
    discord_channel_id: Optional[str] = typer.Option(None, "--discord-channel-id", help="Sanitized Discord DM channel id for local thread update."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Apply a private-DM final publish approval locally without calling Discord or Meta."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = handle_dm_publish_approval_reply(
            connection,
            draft_id,
            message,
            now=now,
            discord_channel_id=discord_channel_id,
        )
    except DmSchedulingError as error:
        raise typer.BadParameter(str(error), param_hint="--message/--post-id") from error
    typer.echo(result.to_text())


@discord_app.command("dm-guided-review-send")
def discord_dm_guided_review_send(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    location_text: Optional[str] = typer.Option(None, "--location", help="Confirmed location/place text."),
    story_angle: Optional[str] = typer.Option(None, "--story-angle", help="Story or memory to center."),
    mood: Optional[str] = typer.Option(None, "--mood", help="Caption tone or mood."),
    audience_hook: Optional[str] = typer.Option(None, "--audience-hook", help="First-line audience hook."),
    include: Optional[str] = typer.Option(None, "--include", help="Details to include."),
    avoid: Optional[str] = typer.Option(None, "--avoid", help="Things to avoid."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Send a live private Discord DM guided-review prompt using env-configured bot credentials."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = send_dm_guided_review_prompt(
            connection,
            draft_id,
            location_text=location_text,
            story_angle=story_angle,
            mood=mood,
            audience_hook=audience_hook,
            include=include,
            avoid=avoid,
            config=config,
            transport=DiscordRestTransport(config.bot_token, api_base_url=config.api_base_url),
        )
    except DiscordDmError as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(result.to_text())


@discord_app.command("dm-guided-review-poll")
def discord_dm_guided_review_poll(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    channel_id: str = typer.Option(..., "--channel-id", help="Discord DM channel id returned by dm-guided-review-send."),
    after_message_id: str = typer.Option(..., "--after-message-id", help="Only inspect Discord replies after this prompt message id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Poll a private Discord DM for Andrew's guided-review reply and send a confirmation."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        config = load_discord_dm_config_from_env()
        result = poll_dm_guided_review_reply(
            connection,
            draft_id,
            channel_id=channel_id,
            target_user_id=config.target_user_id,
            after_message_id=after_message_id,
            transport=DiscordRestTransport(config.bot_token, api_base_url=config.api_base_url),
        )
    except DiscordDmError as error:
        raise typer.BadParameter(str(error), param_hint="--channel-id/--post-id") from error
    typer.echo(result.confirmation_text)


@discord_app.command("dm-guided-review-apply")
def discord_dm_guided_review_apply(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    message: str = typer.Option(..., "--message", help="Andrew's DM guided-review reply."),
    discord_channel_id: Optional[str] = typer.Option(None, "--discord-channel-id", help="Sanitized Discord DM channel id for local thread update."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Apply a private-DM guided-review reply locally without calling Discord or Meta."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = handle_dm_guided_review_reply(
            connection,
            draft_id,
            message,
            discord_channel_id=discord_channel_id,
        )
    except DmGuidedReviewError as error:
        raise typer.BadParameter(str(error), param_hint="--message/--post-id") from error
    typer.echo(result.to_text())


@drafts_app.command("create")
def drafts_create(
    candidate_id: int = typer.Option(..., "--candidate-id", help="Candidate group id."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Create an initial post record from a candidate group."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        draft = create_draft_from_candidate(connection, candidate_id)
    except CandidateNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--candidate-id") from error
    typer.echo(f"Created post #{draft.id} from candidate #{draft.candidate_group_id}; initial status is {draft.status}.")


@drafts_app.command("list")
def drafts_list(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """List post records."""
    connection = connect_db(db)
    initialize_db(connection)
    drafts = list_drafts(connection)
    if not drafts:
        typer.echo("No posts found.")
        return
    for draft in drafts:
        typer.echo(
            f"#{draft.id} candidate #{draft.candidate_group_id} — {draft.post_type}, {draft.status}"
        )


@drafts_app.command("preview")
def drafts_preview(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print a structured local review package for a post."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        package = build_draft_review_package(connection, draft_id)
    except DraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(package.to_text())


@drafts_app.command("media-plan")
def drafts_media_plan(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print numbered post media for contact-sheet review instructions."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = build_draft_media_plan(connection, draft_id)
    except MediaSelectionDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(plan.to_text())


@drafts_app.command("media-edit")
def drafts_media_edit(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
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
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except InvalidMediaSelection as error:
        raise typer.BadParameter(str(error), param_hint="--lead/--keep/--remove") from error
    typer.echo(result.to_text())


@drafts_app.command("crop-feedback")
def drafts_crop_feedback(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    shift: Optional[list[str]] = typer.Option(None, "--shift", help="Crop anchor as REVIEW_NUMBER:A1-E5, e.g. 3:B2."),
    center: Optional[list[int]] = typer.Option(None, "--center", help="Review media number to recenter to C3; repeatable."),
    tighten: Optional[list[int]] = typer.Option(None, "--tighten", help="Review media number to make one step tighter; repeatable."),
    loosen: Optional[list[int]] = typer.Option(None, "--loosen", help="Review media number to make one step wider; repeatable."),
    ratio: Optional[list[str]] = typer.Option(None, "--ratio", help="Crop ratio as REVIEW_NUMBER:RATIO, e.g. 3:4:5 or 3:1:1."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Apply chat-style crop/center feedback to post media without network calls."""
    edits = _build_crop_feedback_edits(shift or [], center or [], tighten or [], loosen or [], ratio or [])
    connection = connect_db(db)
    initialize_db(connection)
    try:
        result = apply_draft_crop_feedback(connection, draft_id, crop_edits=edits)
    except MediaSelectionDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except InvalidMediaSelection as error:
        raise typer.BadParameter(str(error), param_hint="--shift/--center/--tighten/--loosen/--ratio") from error
    typer.echo(result.to_text())


@draft_final_preview_artifact_app.command("render")
def drafts_final_preview_artifact_render(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    ratio: str = typer.Option("4:5", "--ratio", help="Locked preview ratio, e.g. 4:5 or 1:1."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and review artifact config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render a local final carousel/post preview artifact without network calls."""
    from post_relay.contact_sheet_design import ratio_from_label

    config = load_config(config_path)
    connection = connect_db(db)
    initialize_db(connection)
    try:
        package = render_final_post_preview_artifact(
            connection,
            draft_id,
            config.review_artifacts,
            ratio=ratio_from_label(ratio),
        )
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--post-id/--ratio") from error
    typer.echo(package.to_text())


@draft_publish_exports_app.command("render")
def drafts_publish_exports_render(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    profile: str = typer.Option("feed_portrait_3x4", "--profile", help="Publish export profile."),
    landscape_treatment: str = typer.Option("clean_mat", "--landscape-treatment", help="Landscape-in-portrait treatment."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and publish export config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render Instagram-optimized publish assets without mutating source media."""
    config = load_config(config_path)
    connection = connect_db(db)
    initialize_db(connection)
    try:
        package = render_publish_exports_for_draft(
            connection,
            draft_id,
            config.publish_exports,
            profile_name=profile,
            landscape_treatment=landscape_treatment,
            protected_source_roots=[source.root for source in config.photo_sources],
        )
    except PublishExportDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except (UnsupportedPublishExportProfile, UnsupportedLandscapeTreatment, UnsafeArtifactRoot) as error:
        raise typer.BadParameter(str(error), param_hint="--profile/--landscape-treatment/--config") from error
    typer.echo(package.to_text())


@drafts_app.command("guided-package-plan")
def drafts_guided_package_plan(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    location_text: Optional[str] = typer.Option(None, "--location", help="Confirmed location/place text."),
    story_angle: Optional[str] = typer.Option(None, "--story-angle", help="Story or memory to center."),
    mood: Optional[str] = typer.Option(None, "--mood", help="Caption tone or mood."),
    audience_hook: Optional[str] = typer.Option(None, "--audience-hook", help="First-line audience hook."),
    include: Optional[str] = typer.Option(None, "--include", help="Details to include."),
    avoid: Optional[str] = typer.Option(None, "--avoid", help="Things to avoid."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    connection = connect_db(db_path)
    initialize_db(connection)
    try:
        package = build_guided_draft_package(
            connection,
            draft_id,
            location_text=location_text,
            story_angle=story_angle,
            mood=mood,
            audience_hook=audience_hook,
            include=include,
            avoid=avoid,
        )
    except GuidedDraftNotFound as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(package.to_text())


@drafts_app.command("guided-package-accept")
def drafts_guided_package_accept(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    caption_index: int = typer.Option(1, "--caption-index", help="Generated caption option to accept."),
    location_text: Optional[str] = typer.Option(None, "--location", help="Confirmed location/place text."),
    story_angle: Optional[str] = typer.Option(None, "--story-angle", help="Story or memory to center."),
    mood: Optional[str] = typer.Option(None, "--mood", help="Caption tone or mood."),
    audience_hook: Optional[str] = typer.Option(None, "--audience-hook", help="First-line audience hook."),
    include: Optional[str] = typer.Option(None, "--include", help="Details to include."),
    avoid: Optional[str] = typer.Option(None, "--avoid", help="Things to avoid."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    connection = connect_db(db_path)
    initialize_db(connection)
    try:
        package = build_guided_draft_package(
            connection,
            draft_id,
            location_text=location_text,
            story_angle=story_angle,
            mood=mood,
            audience_hook=audience_hook,
            include=include,
            avoid=avoid,
        )
        accepted = accept_guided_draft_package(connection, package, caption_index=caption_index)
    except (GuidedDraftNotFound, InvalidGuidedDraftPackage) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(accepted.to_text())


@drafts_app.command("discord-selection-plan")
def drafts_discord_selection_plan(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
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
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except InvalidDiscordSelection as error:
        raise typer.BadParameter(str(error), param_hint="--target-count/--post-type") from error
    typer.echo(request.to_text())


@drafts_app.command("discord-selection-preview")
def drafts_discord_selection_preview(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
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
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except InvalidDiscordSelection as error:
        raise typer.BadParameter(str(error), param_hint="--target-count/--post-type") from error
    typer.echo(payload.to_text())


@drafts_app.command("discord-selection-apply")
def drafts_discord_selection_apply(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
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
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except InvalidDiscordSelection as error:
        raise typer.BadParameter(str(error), param_hint="--select/--lead/--target-count") from error
    typer.echo(result.to_text())


@drafts_app.command("discord-preview")
def drafts_discord_preview(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print a dry-run Discord preview payload with ordered image paths."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        payload = build_discord_preview_payload(connection, draft_id)
    except DiscordPreviewDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(payload.to_text())


@drafts_app.command("r2-stage-plan")
def drafts_r2_stage_plan(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print a no-network R2 staging plan for post media and review artifacts."""
    config = load_config(config_path)
    connection = connect_db(db)
    initialize_db(connection)
    try:
        plan = plan_r2_staging_for_draft(
            connection,
            draft_id,
            config.r2_staging,
            review_artifact_root=config.review_artifacts.root,
            publish_export_root=config.publish_exports.root,
        )
    except R2StagingDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except R2StagingConfigError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    typer.echo(plan.to_text())


@drafts_app.command("r2-stage-upload")
def drafts_r2_stage_upload(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and R2 staging config path."),
    execute: bool = typer.Option(False, "--execute", help="Upload staged objects to R2 and record them."),
    include_review_artifacts: bool = typer.Option(False, "--include-review-artifacts", help="Also upload generated review thumbnails and contact sheet."),
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
            publish_export_root=config.publish_exports.root,
            include_review_artifacts=include_review_artifacts,
            execute=execute,
        )
    except R2StagingDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except (R2StagingConfigError, R2StagingUploadError) as error:
        raise typer.BadParameter(str(error), param_hint="--config/--execute") from error
    typer.echo(result.to_text())


@drafts_app.command("r2-cleanup")
def drafts_r2_cleanup(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
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
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Submit a post for content-direction review."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        draft = submit_draft_for_review(connection, draft_id)
    except (ApprovalDraftNotFound, ValueError) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(f"Submitted post #{draft.id} for content review; status is {draft.status}.")


@drafts_app.command("approve")
def drafts_approve(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    approved_by: Optional[str] = typer.Option(None, "--approved-by", help="Approver name."),
    notes: Optional[str] = typer.Option(None, "--notes", help="Approval notes."),
    source_message_ref: Optional[str] = typer.Option(None, "--source-message-ref", help="Source message reference."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Record explicit content approval for queueing."""
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
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except DraftNotReadyForApproval as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(f"Approved post #{approval.draft_id} for queue with approval #{approval.id}.")


@drafts_app.command("edit")
def drafts_edit(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    caption: Optional[str] = typer.Option(None, "--caption", help="Post caption text."),
    hashtags: Optional[str] = typer.Option(None, "--hashtags", help="Comma-separated hashtags."),
    location_text: Optional[str] = typer.Option(None, "--location", help="Location text."),
    alt_text: Optional[str] = typer.Option(None, "--alt-text", help="Alt text."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Edit post content placeholders and invalidate prior approvals on material changes."""
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
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    invalidated_count = active_before - len(list_active_approvals(connection, draft_id))
    message = f"Updated post #{draft.id}; status is {draft.status}."
    if invalidated_count:
        message += f" Material edit invalidated active approvals: {invalidated_count}."
    typer.echo(message)


@drafts_app.command("location-candidates")
def drafts_location_candidates(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    query: Optional[str] = typer.Option(None, "--query", help="Confirmed place query to search with Meta Pages."),
    max_candidates: int = typer.Option(5, "--max-candidates", help="Maximum Meta Page candidates to show."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan or clarify without calling Meta."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Private .env file path for Meta read-only search."),
) -> None:
    """Suggest reviewed Meta location Page candidates without setting a tag."""
    connection = connect_db(db)
    initialize_db(connection)
    client = None
    if not dry_run and query:
        try:
            config = load_meta_graph_config(env_file=env_file)
        except MetaGraphConfigError as error:
            raise typer.BadParameter(str(error), param_hint="--env-file") from error
        client = MetaGraphClient(config)
    try:
        review = build_location_candidate_review(
            connection,
            draft_id,
            query=query,
            client=client,
            max_candidates=max_candidates,
        )
    except LocationTagDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    if not dry_run and query and client is None:
        typer.echo("No Meta network calls were made.")
    typer.echo(review.to_text())


@drafts_app.command("location-tag-set")
def drafts_location_tag_set(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    page_id: str = typer.Option(..., "--page-id", help="Resolved Facebook Page id to send as Meta location_id."),
    name: str = typer.Option(..., "--name", help="Human-readable location Page name."),
    source: str = typer.Option("pages/search", "--source", help="Resolution source/audit note."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Persist a reviewed Meta location Page id separately from freeform location text."""
    connection = connect_db(db)
    initialize_db(connection)
    active_before = len(list_active_approvals(connection, draft_id))
    try:
        tag = set_draft_location_tag(
            connection,
            draft_id,
            page_id=page_id,
            name=name,
            source=source,
        )
    except LocationTagDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    invalidated_count = active_before - len(list_active_approvals(connection, draft_id))
    typer.echo(
        f"Resolved Meta location tag for post #{tag.draft_id}: location_id={tag.page_id} ({tag.name})."
    )
    if invalidated_count:
        typer.echo(
            f"Prior approvals were invalidated: {invalidated_count}. Re-submit/reapprove before publishing with this location tag."
        )
    typer.echo("Freeform location_text remains local/review-only and was not changed.")


@drafts_app.command("location-tag-skip")
def drafts_location_tag_skip(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    reason: str = typer.Option(..., "--reason", help="Why the Meta location tag is being skipped."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Record an explicit choice to publish without a Meta location tag."""
    connection = connect_db(db)
    initialize_db(connection)
    active_before = len(list_active_approvals(connection, draft_id))
    try:
        tag = skip_draft_location_tag(connection, draft_id, reason=reason)
    except LocationTagDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    invalidated_count = active_before - len(list_active_approvals(connection, draft_id))
    typer.echo(f"Skipped Meta location tag for post #{tag.draft_id}.")
    typer.echo(f"Reason: {tag.skip_reason or '<none>'}")
    typer.echo("No location_id will be sent to Meta; the user can add a location manually after publishing.")
    if invalidated_count:
        typer.echo(
            f"Prior approvals were invalidated: {invalidated_count}. Re-submit/reapprove before publishing with this location decision."
        )


@drafts_app.command("schedule")
def drafts_schedule(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    scheduled_for: str = typer.Option(..., "--scheduled-for", help="Scheduled publish time/window."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Schedule a queue-approved post without publishing."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        draft = schedule_draft(connection, draft_id, scheduled_for=scheduled_for)
    except (SchedulingDraftNotFound, DraftNotReadyForScheduling) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(f"Scheduled post #{draft.id} for {draft.scheduled_for}; status is {draft.status}.")
    feedback = build_scheduled_post_feedback(connection)
    if feedback.items:
        typer.echo(feedback.to_text())


@drafts_app.command("request-publish-approval")
def drafts_request_publish_approval(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Legacy no-op: final publish approval can be recorded directly for scheduled posts."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        draft = request_publish_approval(connection, draft_id)
    except (SchedulingDraftNotFound, DraftNotReadyForPublishApproval) as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(
        f"Post #{draft.id} is scheduled; no separate publish-approval request gate is required. "
        "Use `drafts approve-publish` to record final publish approval."
    )


@drafts_app.command("approve-publish")
def drafts_approve_publish(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
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
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(f"Approved post #{approval.draft_id} for publishing with approval #{approval.id}.")


@draft_artifacts_app.command("render")
def draft_artifacts_render(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    config_path: Path = typer.Option(Path("config/photo_sources.yaml"), "--config", help="Photo source and artifact config path."),
    stage: str = typer.Option("select", "--stage", help="Artifact stage to render: select, crop, or all."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Render local thumbnails and staged contact sheets for post review."""
    config = load_config(config_path)
    connection = connect_db(db)
    initialize_db(connection)
    try:
        package = render_review_artifacts_for_draft(
            connection,
            draft_id,
            config.review_artifacts,
            protected_source_roots=[source.root for source in config.photo_sources],
            stage=stage,
        )
    except ArtifactDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    except OversizedReviewArtifactSet as error:
        typer.echo(error.plan.to_text())
        return
    except UnsafeArtifactRoot as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--stage") from error
    typer.echo(package.to_text())


@draft_questions_app.command("generate")
def draft_questions_generate(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Generate lightweight missing-context questions for a post."""
    connection = connect_db(db)
    initialize_db(connection)
    try:
        questions = generate_context_questions_for_draft(connection, draft_id)
    except ContextDraftNotFound as error:
        raise typer.BadParameter(str(error), param_hint="--post-id") from error
    typer.echo(
        f"Generated {len(questions)} unresolved context questions for post #{draft_id}."
    )


@draft_questions_app.command("list")
def draft_questions_list(
    draft_id: int = typer.Option(..., "--post-id", "--draft-id", help="Post id (legacy --draft-id alias)."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """List context questions for a post."""
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


def _build_crop_feedback_edits(
    shifts: list[str],
    centers: list[int],
    tightens: list[int],
    loosens: list[int],
    ratios: list[str],
) -> dict[int, dict]:
    edits: dict[int, dict] = {}
    for number in centers:
        edits.setdefault(number, {})["center"] = True
    for number in tightens:
        edit = edits.setdefault(number, {})
        edit["tightness_delta"] = edit.get("tightness_delta", 0) - 0.15
    for number in loosens:
        edit = edits.setdefault(number, {})
        edit["tightness_delta"] = edit.get("tightness_delta", 0) + 0.15
    for raw_shift in shifts:
        try:
            number_text, anchor = raw_shift.split(":", 1)
            number = int(number_text)
        except ValueError as error:
            raise typer.BadParameter("Expected --shift REVIEW_NUMBER:A1-E5, e.g. 3:B2", param_hint="--shift") from error
        edits.setdefault(number, {})["anchor"] = anchor
    for raw_ratio in ratios:
        parts = raw_ratio.split(":")
        if len(parts) < 2:
            raise typer.BadParameter("Expected --ratio REVIEW_NUMBER:RATIO, e.g. 3:4:5", param_hint="--ratio")
        try:
            number = int(parts[0])
        except ValueError as error:
            raise typer.BadParameter("Expected --ratio REVIEW_NUMBER:RATIO, e.g. 3:4:5", param_hint="--ratio") from error
        edits.setdefault(number, {})["ratio"] = ":".join(parts[1:])
    if not edits:
        raise typer.BadParameter("Provide at least one crop edit: --shift, --center, --tighten, --loosen, or --ratio")
    return edits

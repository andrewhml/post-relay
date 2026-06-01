from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_STATEMENTS = [
    """
    create table if not exists photo_sources (
        id integer primary key,
        name text not null unique,
        root text not null,
        source_type text not null,
        reliability_score real not null default 1.0,
        enabled integer not null default 1,
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists photos (
        id integer primary key,
        source_id integer,
        source_name text not null,
        local_file_path text not null unique,
        source_type text not null,
        source_confidence real not null default 1.0,
        inferred_year integer,
        date_taken text,
        camera_model text,
        lens_model text,
        width integer,
        height integer,
        perceptual_hash text,
        thumbnail_path text,
        processed_status text not null default 'processed',
        indexed_at text not null default current_timestamp,
        foreign key(source_id) references photo_sources(id)
    )
    """,
    """
    create table if not exists candidate_groups (
        id integer primary key,
        title text not null,
        theme text,
        source_name text,
        source_folder text,
        source_year integer,
        location text,
        post_type_recommendation text,
        confidence real,
        reason text,
        status text not null default 'candidate',
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        unique(source_name, source_folder)
    )
    """,
    """
    create table if not exists candidate_group_items (
        group_id integer not null,
        photo_id integer not null,
        sort_order integer not null,
        role text not null default 'support',
        include_status text not null default 'included',
        reason text,
        primary key(group_id, photo_id),
        foreign key(group_id) references candidate_groups(id),
        foreign key(photo_id) references photos(id)
    )
    """,
    """
    create table if not exists drafts (
        id integer primary key,
        candidate_group_id integer unique,
        post_type text not null,
        caption text,
        hashtags_json text,
        location_text text,
        alt_text text,
        status text not null default 'drafting',
        scheduled_for text,
        media_selection_confirmed_at text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        foreign key(candidate_group_id) references candidate_groups(id)
    )
    """,
    """
    create table if not exists approvals (
        id integer primary key,
        draft_id integer not null,
        approval_type text not null,
        approved_by text,
        approved_at text not null default current_timestamp,
        source_message_ref text,
        notes text,
        invalidated_at text,
        invalidation_reason text,
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists context_questions (
        id integer primary key,
        draft_id integer not null,
        field_name text not null,
        question_text text not null,
        status text not null default 'unresolved',
        answer_text text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        unique(draft_id, field_name),
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists publish_attempts (
        id integer primary key,
        draft_id integer not null,
        post_type text not null,
        image_url text,
        caption text,
        container_id text,
        published_media_id text,
        status text not null,
        status_code text,
        status_message text,
        image_urls_json text,
        child_container_ids_json text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists r2_staged_objects (
        id integer primary key,
        draft_id integer not null,
        kind text not null,
        source_path text not null,
        bucket text not null,
        object_key text not null unique,
        public_url text not null,
        status text not null default 'uploaded',
        staged_at text not null default current_timestamp,
        deleted_at text,
        cleanup_reason text,
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists guided_draft_packages (
        id integer primary key,
        draft_id integer not null,
        post_type_recommendation text not null,
        post_type_rationale text not null,
        caption_options_json text not null,
        hashtag_suggestions_json text not null,
        location_text text,
        alt_text text not null,
        growth_rationale text not null,
        context_questions_json text not null,
        accepted_caption_index integer,
        accepted_at text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists conversation_threads (
        id integer primary key,
        draft_id integer,
        discord_channel_id text,
        status text not null default 'active',
        last_prompt_summary text not null,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists conversation_context_notes (
        id integer primary key,
        thread_id integer not null,
        draft_id integer,
        summary text not null,
        created_at text not null default current_timestamp,
        foreign key(thread_id) references conversation_threads(id),
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists post_opportunities (
        id integer primary key,
        trigger_type text not null,
        trigger_key text not null,
        title text not null,
        summary text not null,
        rationale text not null,
        suggested_next_action text not null,
        status text not null default 'new',
        candidate_group_id integer,
        draft_id integer,
        due_at text,
        expires_at text,
        snoozed_until text,
        dismissed_reason text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        foreign key(candidate_group_id) references candidate_groups(id),
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists draft_location_tags (
        id integer primary key,
        draft_id integer not null unique,
        page_id text not null,
        name text not null,
        source text not null,
        status text not null default 'resolved',
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists published_post_snapshots (
        id integer primary key,
        draft_id integer not null unique,
        publish_attempt_id integer not null unique,
        published_media_id text not null,
        post_type text not null,
        final_caption text,
        media_urls_json text not null,
        media_dimensions_json text not null,
        scheduled_for text,
        actual_published_at text not null,
        location_page_id text,
        location_name text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        foreign key(draft_id) references drafts(id),
        foreign key(publish_attempt_id) references publish_attempts(id)
    )
    """,
    """
    create table if not exists media_insight_snapshots (
        id integer primary key,
        draft_id integer not null,
        published_post_snapshot_id integer not null,
        published_media_id text not null,
        metrics_json text not null,
        raw_payload_json text not null,
        collected_at text not null,
        created_at text not null default current_timestamp,
        foreign key(draft_id) references drafts(id),
        foreign key(published_post_snapshot_id) references published_post_snapshots(id)
    )
    """,
    """
    create table if not exists account_metric_snapshots (
        id integer primary key,
        instagram_account_id text not null,
        username text,
        follower_count integer,
        follows_count integer,
        media_count integer,
        raw_payload_json text not null,
        collected_at text not null,
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists caption_feedback (
        id integer primary key,
        draft_id integer not null,
        sentiment text not null,
        signal text not null,
        note text not null,
        reviewed_by text,
        created_at text not null default current_timestamp,
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists user_media_usage (
        id integer primary key,
        user_key text not null default 'default',
        photo_id integer not null,
        usage_status text not null,
        source text not null default 'manual_mark',
        draft_id integer,
        used_at text not null default current_timestamp,
        note text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        unique(user_key, photo_id),
        foreign key(photo_id) references photos(id),
        foreign key(draft_id) references drafts(id)
    )
    """,
    """
    create table if not exists user_goals (
        id integer primary key,
        title text not null,
        goal_statement text not null,
        target_audience text,
        content_pillars_json text not null default '[]',
        desired_cadence text,
        success_metrics_json text not null default '[]',
        strategy_notes text,
        constraints_json text not null default '[]',
        reviewed_by text,
        status text not null default 'active',
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists user_goal_versions (
        id integer primary key,
        goal_id integer not null,
        version_number integer not null,
        snapshot_json text not null,
        changed_by text,
        change_note text,
        created_at text not null default current_timestamp,
        unique(goal_id, version_number),
        foreign key(goal_id) references user_goals(id)
    )
    """,
    """
    create table if not exists account_preferences (
        id integer primary key,
        account_key text not null default 'default',
        review_flow_order_json text not null default '["selection_sheet", "crop_sheet", "copy_collaboration", "final_preview"]',
        require_goal_and_audience_for_copy integer not null default 1,
        copy_collaboration_required integer not null default 1,
        final_preview_requires_locked_copy integer not null default 1,
        writing_style_notes_json text not null default '[]',
        goal_type text,
        growth_mode text,
        primary_success_metric text,
        target_monthly_reels integer,
        target_monthly_carousels integer,
        target_weekly_posts integer,
        agent_checkin_cadence text,
        comfort_zone_push_enabled integer not null default 0,
        max_push_level text,
        preferred_growth_experiments_json text not null default '[]',
        blocked_growth_experiments_json text not null default '[]',
        checkin_delivery_destination text,
        checkin_trigger_policy text,
        checkin_timezone text,
        checkin_working_hours_start text,
        checkin_working_hours_end text,
        checkin_run_planners integer not null default 0,
        reviewed_by text,
        status text not null default 'active',
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        unique(account_key, status)
    )
    """,
    """
    create table if not exists account_preference_versions (
        id integer primary key,
        account_preference_id integer not null,
        version_number integer not null,
        snapshot_json text not null,
        changed_by text,
        change_note text,
        created_at text not null default current_timestamp,
        unique(account_preference_id, version_number),
        foreign key(account_preference_id) references account_preferences(id)
    )
    """,
]


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("pragma foreign_keys = on")
    return connection


def initialize_db(connection: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    _ensure_column(connection, "approvals", "invalidated_at", "text")
    _ensure_column(connection, "approvals", "invalidation_reason", "text")
    _ensure_column(connection, "photos", "date_taken", "text")
    _ensure_column(connection, "photos", "camera_model", "text")
    _ensure_column(connection, "photos", "lens_model", "text")
    _ensure_column(connection, "photos", "width", "integer")
    _ensure_column(connection, "photos", "height", "integer")
    _ensure_column(connection, "photos", "perceptual_hash", "text")
    _ensure_column(connection, "photos", "thumbnail_path", "text")
    _ensure_column(connection, "drafts", "media_selection_confirmed_at", "text")
    _ensure_column(connection, "publish_attempts", "image_urls_json", "text")
    _ensure_column(connection, "publish_attempts", "child_container_ids_json", "text")
    _ensure_column(connection, "candidate_group_items", "role", "text not null default 'support'")
    _ensure_column(connection, "candidate_group_items", "include_status", "text not null default 'included'")
    _ensure_column(connection, "candidate_group_items", "reason", "text")
    _ensure_column(connection, "candidate_group_items", "crop_ratio", "real")
    _ensure_column(connection, "candidate_group_items", "crop_anchor_x", "real")
    _ensure_column(connection, "candidate_group_items", "crop_anchor_y", "real")
    _ensure_column(connection, "candidate_group_items", "crop_tightness", "real")
    _ensure_column(connection, "r2_staged_objects", "deleted_at", "text")
    _ensure_column(connection, "r2_staged_objects", "cleanup_reason", "text")
    _ensure_column(connection, "draft_location_tags", "skip_reason", "text")
    _ensure_column(connection, "account_preferences", "goal_type", "text")
    _ensure_column(connection, "account_preferences", "growth_mode", "text")
    _ensure_column(connection, "account_preferences", "primary_success_metric", "text")
    _ensure_column(connection, "account_preferences", "target_monthly_reels", "integer")
    _ensure_column(connection, "account_preferences", "target_monthly_carousels", "integer")
    _ensure_column(connection, "account_preferences", "target_weekly_posts", "integer")
    _ensure_column(connection, "account_preferences", "agent_checkin_cadence", "text")
    _ensure_column(connection, "account_preferences", "comfort_zone_push_enabled", "integer not null default 0")
    _ensure_column(connection, "account_preferences", "max_push_level", "text")
    _ensure_column(connection, "account_preferences", "preferred_growth_experiments_json", "text not null default '[]'")
    _ensure_column(connection, "account_preferences", "blocked_growth_experiments_json", "text not null default '[]'")
    _ensure_column(connection, "account_preferences", "checkin_delivery_destination", "text")
    _ensure_column(connection, "account_preferences", "checkin_trigger_policy", "text")
    _ensure_column(connection, "account_preferences", "checkin_timezone", "text")
    _ensure_column(connection, "account_preferences", "checkin_working_hours_start", "text")
    _ensure_column(connection, "account_preferences", "checkin_working_hours_end", "text")
    _ensure_column(connection, "account_preferences", "checkin_run_planners", "integer not null default 0")
    connection.commit()


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    existing_columns = {
        row[1] for row in connection.execute(f"pragma table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        connection.execute(f"alter table {table_name} add column {column_name} {column_definition}")

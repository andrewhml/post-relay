from pathlib import Path

from typer.testing import CliRunner

from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.recommendations import (
    build_schedule_recommendations,
    build_signal_baseline,
    render_schedule_recommendations,
    render_signal_baseline,
)
from post_relay.user_goals import upsert_active_user_goal


runner = CliRunner()


def test_build_signal_baseline_counts_local_recommendation_coverage(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Grow with saveable route carousels.",
        target_audience="Travelers planning city walks.",
        content_pillars=["city guides"],
        desired_cadence="2 posts per week",
        success_metrics=["saves", "shares"],
        strategy_notes="Recommend one best next post.",
        constraints=["avoid places not pictured"],
        reviewed_by="andrew",
        change_note="initial agreement",
    )
    _seed_signal_rows(connection)

    baseline = build_signal_baseline(connection)

    assert baseline.has_active_goal is True
    assert baseline.active_goal_title == "Travel account north star"
    assert baseline.counts["candidate_groups"] == 2
    assert baseline.counts["posts_total"] == 3
    assert baseline.posts_by_status == {"drafting": 1, "ready_to_publish": 1, "scheduled": 1}
    assert baseline.counts["selected_media"] == 3
    assert baseline.counts["accepted_guided_packages"] == 1
    assert baseline.counts["published_snapshots"] == 1
    assert baseline.counts["insight_snapshots"] == 1
    assert baseline.counts["follower_snapshots"] == 1
    assert baseline.counts["approvals_total"] == 2
    assert baseline.counts["approval_invalidations"] == 1
    assert baseline.counts["scheduled_posts"] == 1
    assert baseline.counts["opportunities"] == 1
    assert baseline.counts["dm_threads"] == 1
    assert "Performance history is sparse" in baseline.warnings
    assert baseline.mutation_statement == (
        "No Discord, R2, or Meta network calls were made. No posts, approvals, "
        "schedules, opportunities, publish attempts, or analytics rows were mutated."
    )


def test_render_signal_baseline_reports_warnings_and_next_safe_commands(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    rendered = render_signal_baseline(connection)

    assert "Recommendation signal baseline" in rendered
    assert "Active goal: missing" in rendered
    assert "candidate_groups: 0" in rendered
    assert "Sparse-signal warnings:" in rendered
    assert "Active goal is missing" in rendered
    assert "Not enough candidate groups" in rendered
    assert "Next safe commands:" in rendered
    assert "post-relay goals init" in rendered
    assert "post-relay candidates build" in rendered
    assert "post-relay analytics feedback-summary" in rendered
    assert "No Discord, R2, or Meta network calls were made." in rendered
    assert "No posts, approvals, schedules, opportunities, publish attempts, or analytics rows were mutated." in rendered


def test_cli_recommendations_signals_is_local_advisory_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_signal_rows(connection)

    result = runner.invoke(app, ["recommendations", "signals", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Recommendation signal baseline" in result.output
    assert "Active goal: missing" in result.output
    assert "posts_total: 3" in result.output
    assert "Post lifecycle states:" in result.output
    assert "ready_to_publish: 1" in result.output
    assert "No Discord, R2, or Meta network calls were made." in result.output


def test_build_schedule_recommendations_surfaces_queue_and_avoids_conflicts(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Grow with saveable route carousels.",
        target_audience="Travelers planning city walks.",
        content_pillars=["city guides"],
        desired_cadence="2 posts per week",
        success_metrics=["saves", "shares"],
        strategy_notes="Recommend one best next post.",
        constraints=["avoid places not pictured"],
        reviewed_by="andrew",
        change_note="initial agreement",
    )
    _seed_signal_rows(connection)

    plan = build_schedule_recommendations(
        connection,
        now="2026-05-30T08:00:00-07:00",
        limit=3,
    )

    assert plan.active_goal_title == "Travel account north star"
    assert len(plan.scheduled_posts) == 1
    assert plan.scheduled_posts[0].post_id == 2
    assert plan.scheduled_posts[0].scheduled_for == "2026-06-01T09:00:00-07:00"
    assert len(plan.recommendations) == 3
    assert all(not slot.scheduled_for.startswith("2026-06-01") for slot in plan.recommendations)
    assert plan.recommendations[0].next_safe_command.startswith("post-relay drafts schedule --post-id")
    assert any("existing scheduled queue" in rationale for rationale in plan.recommendations[0].rationale)
    assert any("Performance/follower timing data is sparse" in warning for warning in plan.warnings)
    assert plan.mutation_statement == (
        "No Discord, R2, or Meta network calls were made. No posts, approvals, "
        "schedules, opportunities, publish attempts, or analytics rows were mutated."
    )


def test_render_schedule_recommendations_is_advisory_and_queue_first(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_signal_rows(connection)

    rendered = render_schedule_recommendations(
        connection,
        now="2026-05-30T08:00:00-07:00",
        limit=2,
    )

    assert "Schedule recommendations" in rendered
    assert "Existing scheduled queue:" in rendered
    assert "Post 2: 2026-06-01T09:00:00-07:00" in rendered
    assert "Suggested windows:" in rendered
    assert "No automatic scheduling was performed." in rendered
    assert "post-relay drafts schedule --post-id" in rendered
    assert "No Discord, R2, or Meta network calls were made." in rendered


def test_cli_recommendations_schedule_is_local_advisory_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_signal_rows(connection)

    before_scheduled = connection.execute("select count(*) from drafts where scheduled_for is not null").fetchone()[0]

    result = runner.invoke(
        app,
        [
            "recommendations",
            "schedule",
            "--now",
            "2026-05-30T08:00:00-07:00",
            "--limit",
            "2",
            "--db",
            str(db_path),
        ],
    )

    after_scheduled = connection.execute("select count(*) from drafts where scheduled_for is not null").fetchone()[0]
    assert result.exit_code == 0
    assert before_scheduled == after_scheduled == 1
    assert "Schedule recommendations" in result.output
    assert "Existing scheduled queue:" in result.output
    assert "No automatic scheduling was performed." in result.output
    assert "No Discord, R2, or Meta network calls were made." in result.output


def _seed_signal_rows(connection):
    connection.execute(
        "insert into photo_sources (id, name, root, source_type) values (1, 'processed', '/tmp/photos', 'local')"
    )
    for photo_id in range(1, 5):
        connection.execute(
            """
            insert into photos (id, source_id, source_name, local_file_path, source_type, width, height)
            values (?, 1, 'processed', ?, 'local', 1080, 1440)
            """,
            (photo_id, f"/tmp/photos/kyoto/{photo_id}.jpg"),
        )
    connection.execute(
        """
        insert into candidate_groups (id, title, source_name, source_folder, source_year, post_type_recommendation)
        values (1, 'Kyoto night walk', 'processed', '/tmp/photos/kyoto', 2026, 'carousel')
        """
    )
    connection.execute(
        """
        insert into candidate_groups (id, title, source_name, source_folder, source_year, post_type_recommendation)
        values (2, 'Seoul cafe', 'processed', '/tmp/photos/seoul', 2026, 'single_image')
        """
    )
    for order, photo_id in enumerate([1, 2, 3], start=1):
        connection.execute(
            """
            insert into candidate_group_items (group_id, photo_id, sort_order, role, include_status)
            values (1, ?, ?, ?, 'included')
            """,
            (photo_id, order, "lead" if order == 1 else "support"),
        )
    connection.execute(
        """
        insert into candidate_group_items (group_id, photo_id, sort_order, include_status)
        values (2, 4, 1, 'removed')
        """
    )
    connection.execute(
        "insert into drafts (id, candidate_group_id, post_type, status) values (1, 1, 'carousel', 'drafting')"
    )
    connection.execute(
        "insert into drafts (id, candidate_group_id, post_type, status, scheduled_for) values (2, 2, 'single_image', 'scheduled', '2026-06-01T09:00:00-07:00')"
    )
    connection.execute(
        "insert into drafts (id, candidate_group_id, post_type, status) values (3, null, 'single_image', 'ready_to_publish')"
    )
    connection.execute(
        """
        insert into approvals (draft_id, approval_type, approved_by, invalidated_at, invalidation_reason)
        values (1, 'draft', 'andrew', null, null)
        """
    )
    connection.execute(
        """
        insert into approvals (draft_id, approval_type, approved_by, invalidated_at, invalidation_reason)
        values (1, 'publish', 'andrew', '2026-05-01T10:00:00-07:00', 'media changed')
        """
    )
    connection.execute(
        """
        insert into guided_draft_packages (
            draft_id, post_type_recommendation, post_type_rationale, caption_options_json,
            hashtag_suggestions_json, alt_text, growth_rationale, context_questions_json, accepted_caption_index, accepted_at
        ) values (1, 'carousel', 'cohesive route', '["caption"]', '["#travel"]', 'local alt', 'saveable', '[]', 0, '2026-05-01T09:00:00-07:00')
        """
    )
    connection.execute(
        """
        insert into publish_attempts (id, draft_id, post_type, status, published_media_id)
        values (1, 3, 'single_image', 'published', 'ig-media-1')
        """
    )
    connection.execute(
        """
        insert into published_post_snapshots (
            draft_id, publish_attempt_id, published_media_id, post_type, media_urls_json,
            media_dimensions_json, actual_published_at
        ) values (3, 1, 'ig-media-1', 'single_image', '["https://example.test/1.jpg"]', '[{"width":1080,"height":1440}]', '2026-05-01T09:00:00-07:00')
        """
    )
    connection.execute(
        """
        insert into media_insight_snapshots (
            draft_id, published_post_snapshot_id, published_media_id, metrics_json, raw_payload_json, collected_at
        ) values (3, 1, 'ig-media-1', '{"reach":100}', '{}', '2026-05-02T09:00:00-07:00')
        """
    )
    connection.execute(
        """
        insert into account_metric_snapshots (instagram_account_id, username, follower_count, raw_payload_json, collected_at)
        values ('1784', 'andrewhml', 1234, '{}', '2026-05-02T09:00:00-07:00')
        """
    )
    connection.execute(
        """
        insert into post_opportunities (trigger_type, trigger_key, title, summary, rationale, suggested_next_action)
        values ('cadence_due', 'weekly', 'Weekly post', 'Queue one post', 'cadence', 'Pick a candidate')
        """
    )
    connection.execute(
        """
        insert into conversation_threads (draft_id, discord_channel_id, status, last_prompt_summary)
        values (1, 'local-dm', 'active', 'select photos')
        """
    )
    connection.commit()

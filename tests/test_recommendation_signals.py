from pathlib import Path

from typer.testing import CliRunner

from post_relay.account_preferences import upsert_account_preferences
from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.recommendations import (
    build_caption_style_recommendations,
    build_growth_coach_recommendations,
    build_schedule_recommendations,
    build_signal_baseline,
    record_caption_feedback,
    render_caption_feedback_result,
    render_caption_style_recommendations,
    render_growth_coach_recommendations,
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


def test_build_growth_coach_recommendations_uses_goal_posture_and_local_evidence(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Grow with saveable route carousels and practical reels.",
        target_audience="Travelers planning city walks.",
        content_pillars=["city guides"],
        desired_cadence="3 posts per week",
        success_metrics=["followers", "saves"],
        strategy_notes="Recommend the next safe post plus one stretch experiment.",
        constraints=["avoid places not pictured"],
        reviewed_by="andrew",
    )
    upsert_account_preferences(
        connection,
        account_key="default",
        goal_type="growth",
        growth_mode="growth_push",
        primary_success_metric="followers",
        target_monthly_reels=10,
        target_monthly_carousels=4,
        target_weekly_posts=3,
        agent_checkin_cadence="weekly",
        comfort_zone_push_enabled=True,
        max_push_level="medium",
        preferred_growth_experiments=["reel_cadence_push"],
        blocked_growth_experiments=["trend_chasing"],
        reviewed_by="andrew",
    )
    _seed_signal_rows(connection)

    plan = build_growth_coach_recommendations(connection)

    assert plan.active_goal_title == "Travel account north star"
    assert plan.growth_mode == "growth_push"
    assert plan.primary_success_metric == "followers"
    assert "target 10 reels/month" in plan.cadence_gap
    assert "published reels this month: 0" in plan.cadence_gap
    assert "candidate groups: 2" in plan.evidence_used
    assert plan.safe_path.label == "safe"
    assert plan.growth_path.label == "growth"
    assert plan.stretch_path.label == "stretch"
    assert plan.growth_path.comfort_zone_delta == "medium"
    assert "reel_cadence_push" in " ".join(plan.stretch_path.rationale)
    assert plan.mutation_statement == (
        "No Discord, R2, or Meta network calls were made. No posts, approvals, "
        "schedules, opportunities, publish attempts, or analytics rows were mutated."
    )


def test_render_growth_coach_recommendations_is_advisory_and_actionable(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_signal_rows(connection)
    upsert_account_preferences(
        connection,
        account_key="default",
        growth_mode="balanced",
        primary_success_metric="saves",
        target_monthly_carousels=4,
        comfort_zone_push_enabled=True,
        max_push_level="low",
        preferred_growth_experiments=["carousel_first_slide_context"],
    )

    rendered = render_growth_coach_recommendations(connection)

    assert "Growth coach recommendations" in rendered
    assert "Account posture:" in rendered
    assert "Safe path:" in rendered
    assert "Growth path:" in rendered
    assert "Stretch path:" in rendered
    assert "Comfort-zone delta: low" in rendered
    assert "Evidence used:" in rendered
    assert "Next safe command:" in rendered
    assert "No automatic posting, scheduling, approval, messaging, upload, or analytics collection was performed." in rendered
    assert "No Discord, R2, or Meta network calls were made." in rendered


def test_cli_recommendations_growth_coach_is_local_advisory_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_signal_rows(connection)
    before_posts = connection.execute("select count(*) from drafts").fetchone()[0]
    before_approvals = connection.execute("select count(*) from approvals").fetchone()[0]
    before_scheduled = connection.execute("select count(*) from drafts where scheduled_for is not null").fetchone()[0]

    result = runner.invoke(app, ["recommendations", "growth-coach", "--db", str(db_path)])

    after_posts = connection.execute("select count(*) from drafts").fetchone()[0]
    after_approvals = connection.execute("select count(*) from approvals").fetchone()[0]
    after_scheduled = connection.execute("select count(*) from drafts where scheduled_for is not null").fetchone()[0]
    assert result.exit_code == 0
    assert before_posts == after_posts == 3
    assert before_approvals == after_approvals == 2
    assert before_scheduled == after_scheduled == 1
    assert "Growth coach recommendations" in result.output
    assert "No automatic posting, scheduling, approval, messaging, upload, or analytics collection was performed." in result.output


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


def test_build_caption_style_recommendations_uses_local_feedback_without_rewriting_copy(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_caption_style_rows(connection)

    plan = build_caption_style_recommendations(connection, post_id=4)

    assert plan.active_goal_title == "Travel account north star"
    assert plan.post_id == 4
    assert plan.current_caption == "Another temple sequence."
    assert plan.accepted_caption_count == 2
    assert plan.approved_post_count == 1
    assert plan.published_snapshot_count == 2
    assert plan.insight_snapshot_count == 2
    assert "Lead with a concrete hook in the first sentence." in plan.recommended_direction
    assert "Lean into saveable route/itinerary framing when the photos support it." in plan.recommended_direction
    assert "Do not overwrite the current caption automatically; treat this as review guidance." in plan.guardrails
    assert plan.mutation_statement == (
        "No Discord, R2, or Meta network calls were made. No posts, approvals, "
        "schedules, opportunities, publish attempts, or analytics rows were mutated."
    )


def test_render_caption_style_recommendations_is_advisory(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_caption_style_rows(connection)

    rendered = render_caption_style_recommendations(connection, post_id=4)

    assert "Caption style recommendations" in rendered
    assert "Post: 4" in rendered
    assert "Local feedback signals:" in rendered
    assert "Accepted caption packages: 2" in rendered
    assert "Recommended direction:" in rendered
    assert "Lead with a concrete hook" in rendered
    assert "No caption was rewritten or saved." in rendered
    assert "No Discord, R2, or Meta network calls were made." in rendered


def test_render_caption_style_recommendations_applies_durable_account_preferences(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_caption_style_rows(connection)
    upsert_account_preferences(
        connection,
        account_key="default",
        review_flow_order=["selection_sheet", "crop_sheet", "copy_collaboration", "final_preview"],
        require_goal_and_audience_for_copy=True,
        copy_collaboration_required=True,
        final_preview_requires_locked_copy=True,
        writing_style_notes=["human travel voice", "avoid em dashes"],
        goal_type="growth",
        growth_mode="growth_push",
        primary_success_metric="followers",
        target_monthly_reels=10,
        target_monthly_carousels=4,
        target_weekly_posts=3,
        agent_checkin_cadence="weekly",
        comfort_zone_push_enabled=True,
        max_push_level="medium",
        preferred_growth_experiments=["reel_cadence_push"],
        blocked_growth_experiments=["trend_chasing"],
        reviewed_by="andrew",
    )

    rendered = render_caption_style_recommendations(connection, post_id=4)

    assert "Account preference guidance:" in rendered
    assert "Review flow order: selection_sheet → crop_sheet → copy_collaboration → final_preview" in rendered
    assert "Copy should be collaborative and use the active goal/audience before finalizing." in rendered
    assert "Final preview should wait until caption, hashtags, alt text, and supporting text are locked." in rendered
    assert "Growth posture: growth_push optimizing followers; target 10 reels/month; target 4 carousels/month; target 3 posts/week; comfort-zone push enabled (max medium); preferred experiments: reel_cadence_push; blocked experiments: trend_chasing." in rendered
    assert "human travel voice" in rendered
    assert "avoid em dashes" in rendered


def test_caption_style_recommendations_include_instagram_growth_best_practices(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_caption_style_rows(connection)

    plan = build_caption_style_recommendations(connection, post_id=4)
    rendered = render_caption_style_recommendations(connection, post_id=4)

    assert any("10 or more reels per month" in guidance for guidance in plan.platform_best_practice_guidance)
    assert any("Carousels typically get better reach than single photo posts" in guidance for guidance in plan.platform_best_practice_guidance)
    assert any("relevant captions" in guidance for guidance in plan.platform_best_practice_guidance)
    assert "Instagram growth guidance:" in rendered
    assert "Add topics and places" in rendered
    assert "minimum resolution of 720p" in rendered


def test_cli_recommendations_caption_style_is_local_advisory_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_caption_style_rows(connection)
    caption_before = connection.execute("select caption from drafts where id = 4").fetchone()[0]
    approval_count_before = connection.execute("select count(*) from approvals").fetchone()[0]

    result = runner.invoke(app, ["recommendations", "caption-style", "--post-id", "4", "--db", str(db_path)])

    caption_after = connection.execute("select caption from drafts where id = 4").fetchone()[0]
    approval_count_after = connection.execute("select count(*) from approvals").fetchone()[0]
    assert result.exit_code == 0
    assert caption_before == caption_after == "Another temple sequence."
    assert approval_count_before == approval_count_after
    assert "Caption style recommendations" in result.output
    assert "No caption was rewritten or saved." in result.output
    assert "No Discord, R2, or Meta network calls were made." in result.output


def test_record_caption_feedback_captures_lightweight_review_signal_without_changing_caption(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_caption_style_rows(connection)
    caption_before = connection.execute("select caption from drafts where id = 4").fetchone()[0]

    result = record_caption_feedback(
        connection,
        post_id=4,
        sentiment="positive",
        signal="saveable_route",
        note="This framing feels useful enough to save.",
        reviewed_by="andrew",
    )

    caption_after = connection.execute("select caption from drafts where id = 4").fetchone()[0]
    stored = connection.execute(
        "select draft_id, sentiment, signal, note, reviewed_by from caption_feedback"
    ).fetchone()
    assert result.post_id == 4
    assert result.sentiment == "positive"
    assert result.signal == "saveable_route"
    assert caption_before == caption_after == "Another temple sequence."
    assert stored == (4, "positive", "saveable_route", "This framing feels useful enough to save.", "andrew")
    assert "No captions, posts, approvals, schedules, Discord, R2, or Meta state were changed." in result.mutation_statement


def test_render_caption_feedback_result_is_safe_and_concise(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_caption_style_rows(connection)
    result = record_caption_feedback(
        connection,
        post_id=4,
        sentiment="needs_work",
        signal="too_generic",
        note="Needs a sharper opening hook.",
        reviewed_by="andrew",
    )

    rendered = render_caption_feedback_result(result)

    assert "Caption feedback recorded for post 4" in rendered
    assert "Sentiment: needs_work" in rendered
    assert "Signal: too_generic" in rendered
    assert "Needs a sharper opening hook." in rendered
    assert "No Discord, R2, or Meta network calls were made." in rendered


def test_caption_style_recommendations_include_qualitative_caption_feedback(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_caption_style_rows(connection)
    record_caption_feedback(
        connection,
        post_id=4,
        sentiment="positive",
        signal="hook_first",
        note="The first line is finally concrete.",
        reviewed_by="andrew",
    )

    plan = build_caption_style_recommendations(connection, post_id=4)
    rendered = render_caption_style_recommendations(connection, post_id=4)

    assert plan.caption_feedback_count == 1
    assert any("hook_first" in pattern for pattern in plan.local_patterns)
    assert "Caption feedback rows: 1" in rendered
    assert "hook_first" in rendered


def test_cli_recommendations_caption_feedback_records_only_feedback_row(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_caption_style_rows(connection)
    caption_before = connection.execute("select caption from drafts where id = 4").fetchone()[0]
    approval_count_before = connection.execute("select count(*) from approvals").fetchone()[0]

    result = runner.invoke(
        app,
        [
            "recommendations",
            "caption-feedback",
            "--post-id",
            "4",
            "--sentiment",
            "positive",
            "--signal",
            "saveable_route",
            "--note",
            "Keep this route framing.",
            "--reviewed-by",
            "andrew",
            "--db",
            str(db_path),
        ],
    )

    caption_after = connection.execute("select caption from drafts where id = 4").fetchone()[0]
    approval_count_after = connection.execute("select count(*) from approvals").fetchone()[0]
    feedback_count = connection.execute("select count(*) from caption_feedback").fetchone()[0]
    assert result.exit_code == 0
    assert caption_before == caption_after == "Another temple sequence."
    assert approval_count_before == approval_count_after
    assert feedback_count == 1
    assert "Caption feedback recorded for post 4" in result.output
    assert "No Discord, R2, or Meta network calls were made." in result.output


def _seed_caption_style_rows(connection):
    upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Grow with saveable route carousels and practical city guides.",
        target_audience="Travelers planning city walks.",
        content_pillars=["city guides", "route carousels"],
        desired_cadence="2 posts per week",
        success_metrics=["saves", "shares"],
        strategy_notes="Favor hook-first captions with itinerary utility.",
        constraints=["avoid places not pictured"],
        reviewed_by="andrew",
        change_note="initial agreement",
    )
    connection.execute(
        "insert into photo_sources (id, name, root, source_type) values (1, 'processed', '/tmp/photos', 'local')"
    )
    for group_id, title in [(1, "Kyoto route"), (2, "Seoul market"), (3, "Lisbon overlook"), (4, "Nara temples")]:
        connection.execute(
            """
            insert into candidate_groups (id, title, source_name, source_folder, source_year, post_type_recommendation)
            values (?, ?, 'processed', ?, 2026, 'carousel')
            """,
            (group_id, title, f"/tmp/photos/{title.lower().replace(' ', '-')}")
        )
    connection.execute(
        """
        insert into drafts (id, candidate_group_id, post_type, status, caption)
        values (1, 1, 'carousel', 'posted', 'Start with Fushimi Inari before the tour buses arrive. Save this half-day Kyoto shrine route.')
        """
    )
    connection.execute(
        """
        insert into drafts (id, candidate_group_id, post_type, status, caption)
        values (2, 2, 'carousel', 'posted', 'A market walk for people who plan trips around snacks and neon.')
        """
    )
    connection.execute(
        """
        insert into drafts (id, candidate_group_id, post_type, status, caption)
        values (3, 3, 'carousel', 'approved_for_queue', 'Three viewpoints, one lazy afternoon.')
        """
    )
    connection.execute(
        """
        insert into drafts (id, candidate_group_id, post_type, status, caption)
        values (4, 4, 'carousel', 'drafting', 'Another temple sequence.')
        """
    )
    for package_id, draft_id, caption in [
        (1, 1, "Save this Kyoto shrine walk before your next trip."),
        (2, 3, "The Lisbon overlook route I would repeat."),
    ]:
        connection.execute(
            """
            insert into guided_draft_packages (
                id, draft_id, post_type_recommendation, post_type_rationale, caption_options_json,
                hashtag_suggestions_json, alt_text, growth_rationale, context_questions_json, accepted_caption_index, accepted_at
            ) values (?, ?, 'carousel', 'route utility', ?, '["#travel"]', 'local alt', 'saveable route framing', '[]', 0, '2026-05-01T09:00:00-07:00')
            """,
            (package_id, draft_id, f'["{caption}"]'),
        )
    connection.execute(
        """
        insert into approvals (draft_id, approval_type, approved_by, notes)
        values (3, 'draft', 'andrew', 'approved concise route angle')
        """
    )
    for attempt_id, draft_id in [(1, 1), (2, 2)]:
        connection.execute(
            """
            insert into publish_attempts (id, draft_id, post_type, status, published_media_id, caption)
            values (?, ?, 'carousel', 'published', ?, (select caption from drafts where id = ?))
            """,
            (attempt_id, draft_id, f"ig-media-{attempt_id}", draft_id),
        )
        connection.execute(
            """
            insert into published_post_snapshots (
                id, draft_id, publish_attempt_id, published_media_id, post_type, final_caption,
                media_urls_json, media_dimensions_json, actual_published_at
            ) values (?, ?, ?, ?, 'carousel', (select caption from drafts where id = ?), '["https://example.test/1.jpg"]', '[{"width":1080,"height":1440}]', '2026-05-01T09:00:00-07:00')
            """,
            (attempt_id, draft_id, attempt_id, f"ig-media-{attempt_id}", draft_id),
        )
        connection.execute(
            """
            insert into media_insight_snapshots (
                draft_id, published_post_snapshot_id, published_media_id, metrics_json, raw_payload_json, collected_at
            ) values (?, ?, ?, '{"reach":100,"saved":12,"shares":3}', '{}', '2026-05-02T09:00:00-07:00')
            """,
            (draft_id, attempt_id, f"ig-media-{attempt_id}"),
        )
    connection.commit()

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

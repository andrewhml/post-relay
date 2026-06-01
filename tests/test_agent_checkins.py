from pathlib import Path

from typer.testing import CliRunner

from post_relay.account_preferences import upsert_account_preferences
from post_relay.agent_checkins import build_agent_checkin_plan, render_agent_checkin_plan
from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.user_goals import upsert_active_user_goal


runner = CliRunner()


def test_build_agent_checkin_plan_prioritizes_cadence_and_user_review(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_checkin_rows(connection)
    upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Grow with saveable city-guide carousels.",
        target_audience="Travelers planning city walks.",
        content_pillars=["city guides"],
        desired_cadence="3 posts per week",
        success_metrics=["followers", "saves"],
        strategy_notes="Choose one useful next move.",
        constraints=["avoid places not pictured"],
        reviewed_by="andrew",
    )
    upsert_account_preferences(
        connection,
        account_key="default",
        growth_mode="growth_push",
        primary_success_metric="followers",
        target_weekly_posts=3,
        target_monthly_reels=10,
        agent_checkin_cadence="weekly",
        checkin_delivery_destination="discord_dm",
        checkin_trigger_policy="meaningful_plus_weekly",
        checkin_timezone="America/New_York",
        checkin_working_hours_start="09:00",
        checkin_working_hours_end="17:00",
        checkin_run_planners=True,
    )

    plan = build_agent_checkin_plan(connection)

    assert plan.recommended_checkin_cadence == "weekly"
    assert plan.delivery_destination == "discord_dm"
    assert plan.trigger_policy == "meaningful_plus_weekly"
    assert plan.working_hours == "09:00-17:00 America/New_York"
    assert plan.planners_enabled is True
    assert plan.trigger_reason.startswith("cadence risk:")
    assert plan.user_action_requested == "Review Post 2 or approve the suggested next pipeline action."
    assert "Travel account north star" in plan.draft_message
    assert "Post 2 needs user content review" in plan.draft_message
    assert "This is useful now because" in plan.why_useful_now
    assert plan.no_send_statement == "No Discord, WhatsApp, or other message was sent. This is only a local draft check-in plan."
    assert "No Discord, R2, or Meta network calls were made." in plan.mutation_statement


def test_render_agent_checkin_plan_is_no_send_and_actionable(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_checkin_rows(connection)

    rendered = render_agent_checkin_plan(connection)

    assert "Agent check-in plan" in rendered
    assert "Recommended check-in cadence:" in rendered
    assert "Delivery destination:" in rendered
    assert "Trigger policy:" in rendered
    assert "Working hours:" in rendered
    assert "Read-only planners may run:" in rendered
    assert "Trigger reason:" in rendered
    assert "Draft message:" in rendered
    assert "User action requested:" in rendered
    assert "Why useful now:" in rendered
    assert "No Discord, WhatsApp, or other message was sent." in rendered
    assert "No automatic posting, scheduling, approval, messaging, upload, or analytics collection was performed." in rendered


def test_cli_agent_checkin_plan_is_local_advisory_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_checkin_rows(connection)
    before_posts = connection.execute("select count(*) from drafts").fetchone()[0]
    before_approvals = connection.execute("select count(*) from approvals").fetchone()[0]

    result = runner.invoke(app, ["agent", "checkin-plan", "--db", str(db_path)])

    after_posts = connection.execute("select count(*) from drafts").fetchone()[0]
    after_approvals = connection.execute("select count(*) from approvals").fetchone()[0]
    assert result.exit_code == 0
    assert before_posts == after_posts == 3
    assert before_approvals == after_approvals == 1
    assert "Agent check-in plan" in result.output
    assert "No Discord, WhatsApp, or other message was sent." in result.output


def _seed_checkin_rows(connection):
    connection.execute(
        "insert into photo_sources (id, name, root, source_type) values (1, 'processed', '/tmp/photos', 'local')"
    )
    for candidate_id, title in [(1, "Kyoto temples"), (2, "Lisbon overlooks")]:
        connection.execute(
            """
            insert into candidate_groups (id, title, source_name, source_folder, post_type_recommendation)
            values (?, ?, 'processed', ?, 'carousel')
            """,
            (candidate_id, title, f"/tmp/photos/{candidate_id}"),
        )
    for draft_id, candidate_id, status, scheduled_for in [
        (1, 1, "drafting", None),
        (2, 2, "awaiting_review", None),
        (3, None, "scheduled", "2026-06-03T09:00:00-07:00"),
    ]:
        connection.execute(
            """
            insert into drafts (id, candidate_group_id, post_type, status, scheduled_for)
            values (?, ?, 'carousel', ?, ?)
            """,
            (draft_id, candidate_id, status, scheduled_for),
        )
    connection.execute(
        """
        insert into approvals (draft_id, approval_type, approved_by, invalidated_at, invalidation_reason)
        values (1, 'draft', 'andrew', '2026-06-01T09:00:00-07:00', 'media changed')
        """
    )
    connection.commit()

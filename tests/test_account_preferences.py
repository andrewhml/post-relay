from pathlib import Path

from typer.testing import CliRunner

from post_relay.account_preferences import (
    DEFAULT_REVIEW_FLOW_ORDER,
    get_active_account_preferences,
    list_account_preference_versions,
    render_account_preferences,
    render_account_preferences_agent_brief,
    upsert_account_preferences,
)
from post_relay.cli import app
from post_relay.db import connect_db, initialize_db


runner = CliRunner()


def test_upsert_account_preferences_persists_review_flow_and_versions(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    created = upsert_account_preferences(
        connection,
        account_key="andrew",
        review_flow_order=["selection_sheet", "crop_sheet", "copy_collaboration", "final_preview"],
        require_goal_and_audience_for_copy=True,
        copy_collaboration_required=True,
        final_preview_requires_locked_copy=True,
        writing_style_notes=["imply the point", "avoid em dashes"],
        reviewed_by="andrew",
        change_note="initial prefs",
    )
    updated = upsert_account_preferences(
        connection,
        account_key="andrew",
        review_flow_order=["selection_sheet", "crop_sheet", "copy_collaboration", "final_preview"],
        require_goal_and_audience_for_copy=True,
        copy_collaboration_required=True,
        final_preview_requires_locked_copy=True,
        writing_style_notes=["human travel voice", "avoid em dashes"],
        reviewed_by="andrew",
        change_note="style tightened",
    )

    active = get_active_account_preferences(connection, account_key="andrew")
    versions = list_account_preference_versions(connection, created.id)

    assert created.id == updated.id
    assert active is not None
    assert active.account_key == "andrew"
    assert active.review_flow_order == DEFAULT_REVIEW_FLOW_ORDER
    assert active.require_goal_and_audience_for_copy is True
    assert active.copy_collaboration_required is True
    assert active.final_preview_requires_locked_copy is True
    assert active.writing_style_notes == ["human travel voice", "avoid em dashes"]
    assert [version.version_number for version in versions] == [1, 2]
    assert versions[0].snapshot["writing_style_notes"] == ["imply the point", "avoid em dashes"]
    assert versions[1].change_note == "style tightened"


def test_upsert_account_preferences_persists_growth_posture_and_cadence(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    saved = upsert_account_preferences(
        connection,
        account_key="andrew",
        goal_type="growth",
        growth_mode="growth_push",
        primary_success_metric="followers",
        target_monthly_reels=10,
        target_monthly_carousels=4,
        target_weekly_posts=3,
        agent_checkin_cadence="weekly",
        comfort_zone_push_enabled=True,
        max_push_level="medium",
        preferred_growth_experiments=["reel_cadence_push", "carousel_text_overlay"],
        blocked_growth_experiments=["trend_chasing"],
        checkin_delivery_destination="discord_dm",
        checkin_trigger_policy="meaningful_plus_weekly",
        checkin_timezone="America/New_York",
        checkin_working_hours_start="09:00",
        checkin_working_hours_end="17:00",
        checkin_run_planners=True,
        reviewed_by="andrew",
        change_note="growth posture",
    )

    active = get_active_account_preferences(connection, account_key="andrew")
    versions = list_account_preference_versions(connection, saved.id)

    assert active is not None
    assert active.goal_type == "growth"
    assert active.growth_mode == "growth_push"
    assert active.primary_success_metric == "followers"
    assert active.target_monthly_reels == 10
    assert active.target_monthly_carousels == 4
    assert active.target_weekly_posts == 3
    assert active.agent_checkin_cadence == "weekly"
    assert active.comfort_zone_push_enabled is True
    assert active.max_push_level == "medium"
    assert active.preferred_growth_experiments == ["reel_cadence_push", "carousel_text_overlay"]
    assert active.blocked_growth_experiments == ["trend_chasing"]
    assert active.checkin_delivery_destination == "discord_dm"
    assert active.checkin_trigger_policy == "meaningful_plus_weekly"
    assert active.checkin_timezone == "America/New_York"
    assert active.checkin_working_hours_start == "09:00"
    assert active.checkin_working_hours_end == "17:00"
    assert active.checkin_run_planners is True
    assert versions[-1].snapshot["growth_mode"] == "growth_push"
    assert versions[-1].snapshot["target_monthly_reels"] == 10
    assert versions[-1].snapshot["checkin_delivery_destination"] == "discord_dm"


def test_account_preference_growth_posture_validation_rejects_unknown_values(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    try:
        upsert_account_preferences(connection, growth_mode="viral_at_all_costs")
    except ValueError as error:
        message = str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected ValueError")

    assert "growth_mode" in message
    assert "conservative" in message
    assert get_active_account_preferences(connection) is None


def test_render_account_preferences_agent_brief_includes_transferable_operating_order(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    upsert_account_preferences(
        connection,
        account_key="default",
        review_flow_order=DEFAULT_REVIEW_FLOW_ORDER,
        require_goal_and_audience_for_copy=True,
        copy_collaboration_required=True,
        final_preview_requires_locked_copy=True,
        goal_type="growth",
        growth_mode="growth_push",
        primary_success_metric="saves",
        target_monthly_reels=10,
        target_monthly_carousels=4,
        target_weekly_posts=3,
        agent_checkin_cadence="weekly",
        comfort_zone_push_enabled=True,
        max_push_level="medium",
        preferred_growth_experiments=["reel_cadence_push"],
        blocked_growth_experiments=["trend_chasing"],
        checkin_delivery_destination="discord_dm",
        checkin_trigger_policy="meaningful_plus_weekly",
        checkin_timezone="America/New_York",
        checkin_working_hours_start="09:00",
        checkin_working_hours_end="17:00",
        checkin_run_planners=True,
        writing_style_notes=["saveable route tone", "avoid em dashes"],
        reviewed_by="andrew",
    )

    brief = render_account_preferences_agent_brief(connection)

    assert "Account preferences" in brief
    assert "Review flow order:" in brief
    assert "1. selection_sheet" in brief
    assert "2. crop_sheet" in brief
    assert "3. copy_collaboration" in brief
    assert "4. final_preview" in brief
    assert "Goal/audience required before copy-heavy advice: yes" in brief
    assert "Final preview requires locked copy/supporting text: yes" in brief
    assert "Goal type: growth" in brief
    assert "Growth mode: growth_push" in brief
    assert "Primary success metric: saves" in brief
    assert "Target monthly reels: 10" in brief
    assert "Target monthly carousels: 4" in brief
    assert "Target weekly posts: 3" in brief
    assert "Agent check-in cadence: weekly" in brief
    assert "Comfort-zone push: enabled (max medium)" in brief
    assert "Preferred growth experiments: reel_cadence_push" in brief
    assert "Blocked growth experiments: trend_chasing" in brief
    assert "Check-in delivery: discord_dm" in brief
    assert "Check-in trigger policy: meaningful_plus_weekly" in brief
    assert "Check-in working hours: 09:00-17:00 America/New_York" in brief
    assert "Check-in planner execution: enabled" in brief
    assert "- saveable route tone" in brief
    assert "No Discord, R2, or Meta network calls were made." in brief


def test_account_preferences_show_missing_returns_defaults_without_mutation(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    text = render_account_preferences(get_active_account_preferences(connection))

    assert "No account preferences are stored yet." in text
    assert "Default review flow order:" in text
    assert "selection_sheet → crop_sheet → copy_collaboration → final_preview" in text
    assert "post-relay preferences set" in text


def test_cli_preferences_set_show_and_agent_brief_are_local_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"

    set_result = runner.invoke(
        app,
        [
            "preferences",
            "set",
            "--db",
            str(db_path),
            "--account-key",
            "andrew",
            "--review-step",
            "selection_sheet",
            "--review-step",
            "crop_sheet",
            "--review-step",
            "copy_collaboration",
            "--review-step",
            "final_preview",
            "--require-goal-and-audience-for-copy",
            "--copy-collaboration-required",
            "--final-preview-requires-locked-copy",
            "--goal-type",
            "growth",
            "--growth-mode",
            "growth_push",
            "--primary-success-metric",
            "followers",
            "--target-monthly-reels",
            "10",
            "--target-monthly-carousels",
            "4",
            "--target-weekly-posts",
            "3",
            "--agent-checkin-cadence",
            "weekly",
            "--comfort-zone-push",
            "--max-push-level",
            "medium",
            "--preferred-growth-experiment",
            "reel_cadence_push",
            "--blocked-growth-experiment",
            "trend_chasing",
            "--checkin-delivery-destination",
            "discord_dm",
            "--checkin-trigger-policy",
            "meaningful_plus_weekly",
            "--checkin-timezone",
            "America/New_York",
            "--checkin-working-hours-start",
            "09:00",
            "--checkin-working-hours-end",
            "17:00",
            "--checkin-run-planners",
            "--style-note",
            "avoid em dashes",
            "--reviewed-by",
            "andrew",
            "--change-note",
            "initial portable prefs",
        ],
    )
    show_result = runner.invoke(app, ["preferences", "show", "--db", str(db_path), "--account-key", "andrew"])
    brief_result = runner.invoke(app, ["preferences", "agent-brief", "--db", str(db_path), "--account-key", "andrew"])

    assert set_result.exit_code == 0
    assert "Saved account preferences #1 (andrew) version 1." in set_result.output
    assert "No Discord, R2, or Meta network calls were made." in set_result.output
    assert show_result.exit_code == 0
    assert "Account preferences for andrew" in show_result.output
    assert "selection_sheet → crop_sheet → copy_collaboration → final_preview" in show_result.output
    assert "Growth mode: growth_push" in show_result.output
    assert "Target monthly reels: 10" in show_result.output
    assert "Check-in delivery: discord_dm" in show_result.output
    assert "Check-in trigger policy: meaningful_plus_weekly" in show_result.output
    assert "Check-in working hours: 09:00-17:00 America/New_York" in show_result.output
    assert "Check-in planner execution: enabled" in show_result.output
    assert "avoid em dashes" in show_result.output
    assert brief_result.exit_code == 0
    assert "Goal/audience required before copy-heavy advice: yes" in brief_result.output
    assert "Comfort-zone push: enabled (max medium)" in brief_result.output
    assert "Check-in delivery: discord_dm" in brief_result.output
    assert "Check-in planner execution: enabled" in brief_result.output



def test_cli_preferences_set_preserves_unspecified_existing_checkin_fields(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    initial = runner.invoke(
        app,
        [
            "preferences",
            "set",
            "--db",
            str(db_path),
            "--account-key",
            "andrew",
            "--agent-checkin-cadence",
            "weekly",
            "--checkin-delivery-destination",
            "discord_dm",
            "--checkin-trigger-policy",
            "meaningful_plus_weekly",
            "--checkin-timezone",
            "America/New_York",
            "--checkin-working-hours-start",
            "09:00",
            "--checkin-working-hours-end",
            "17:00",
            "--checkin-run-planners",
            "--reviewed-by",
            "andrew",
        ],
    )
    update = runner.invoke(
        app,
        [
            "preferences",
            "set",
            "--db",
            str(db_path),
            "--account-key",
            "andrew",
            "--target-weekly-posts",
            "3",
            "--reviewed-by",
            "andrew",
        ],
    )

    connection = connect_db(db_path)
    active = get_active_account_preferences(connection, account_key="andrew")

    assert initial.exit_code == 0
    assert update.exit_code == 0
    assert active is not None
    assert active.target_weekly_posts == 3
    assert active.agent_checkin_cadence == "weekly"
    assert active.checkin_delivery_destination == "discord_dm"
    assert active.checkin_trigger_policy == "meaningful_plus_weekly"
    assert active.checkin_timezone == "America/New_York"
    assert active.checkin_working_hours_start == "09:00"
    assert active.checkin_working_hours_end == "17:00"
    assert active.checkin_run_planners is True

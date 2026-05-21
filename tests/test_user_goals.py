from pathlib import Path

from typer.testing import CliRunner

from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.user_goals import (
    get_active_user_goal,
    list_user_goal_versions,
    render_user_goal_agent_brief,
    upsert_active_user_goal,
)


runner = CliRunner()


def test_upsert_active_user_goal_persists_json_fields_and_versions(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    created = upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Grow a travel photography account with saveable city guides.",
        target_audience="Travelers who like polished city walks.",
        content_pillars=["city guides", "photo essays"],
        desired_cadence="2-3 posts per week",
        success_metrics=["saves", "shares", "follower growth"],
        strategy_notes="Prefer cohesive carousel sets over isolated singles.",
        constraints=["avoid places not pictured", "no fabricated facts"],
        reviewed_by="andrew",
        change_note="initial agreement",
    )
    updated = upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Grow a travel photography account with saveable route carousels.",
        target_audience="Travelers who like polished city walks.",
        content_pillars=["city guides", "route carousels"],
        desired_cadence="2-3 posts per week",
        success_metrics=["saves", "shares"],
        strategy_notes="Suggest one best next post with rationale.",
        constraints=["avoid places not pictured"],
        reviewed_by="andrew",
        change_note="tighten strategy",
    )

    active = get_active_user_goal(connection)
    versions = list_user_goal_versions(connection, created.id)

    assert created.id == updated.id
    assert active is not None
    assert active.goal_statement == "Grow a travel photography account with saveable route carousels."
    assert active.content_pillars == ["city guides", "route carousels"]
    assert active.success_metrics == ["saves", "shares"]
    assert active.constraints == ["avoid places not pictured"]
    assert active.reviewed_by == "andrew"
    assert [version.version_number for version in versions] == [1, 2]
    assert versions[0].snapshot["goal_statement"] == "Grow a travel photography account with saveable city guides."
    assert versions[1].change_note == "tighten strategy"


def test_render_user_goal_agent_brief_gives_agent_safe_advisory_north_star(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Build a travel photography account around useful route-like carousels.",
        target_audience="Travelers planning city walks.",
        content_pillars=["saveable itineraries", "standout single images"],
        desired_cadence="2 posts per week",
        success_metrics=["saves", "shares"],
        strategy_notes="Prefer one clear recommendation over a large menu.",
        constraints=["ask fewer generic questions", "avoid places not pictured"],
        reviewed_by="andrew",
        change_note="initial agreement",
    )

    brief = render_user_goal_agent_brief(connection)

    assert "Active user goal" in brief
    assert "Build a travel photography account" in brief
    assert "Content pillars:" in brief
    assert "- saveable itineraries" in brief
    assert "Desired cadence: 2 posts per week" in brief
    assert "Agent operating posture:" in brief
    assert "Suggest actions that fit this goal and cite the rationale." in brief
    assert "No Discord, R2, or Meta network calls were made." in brief
    assert "This brief is advisory and does not mutate posts, approvals, schedules, or publish state." in brief


def test_cli_goals_init_show_and_agent_brief_are_local_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"

    init_result = runner.invoke(
        app,
        [
            "goals",
            "init",
            "--db",
            str(db_path),
            "--title",
            "Travel account north star",
            "--statement",
            "Grow with saveable city-guide carousels.",
            "--target-audience",
            "Travelers planning city walks.",
            "--pillar",
            "city guides",
            "--pillar",
            "photo essays",
            "--cadence",
            "2-3 posts per week",
            "--metric",
            "saves",
            "--metric",
            "shares",
            "--strategy-note",
            "Recommend one best next post.",
            "--constraint",
            "avoid places not pictured",
            "--reviewed-by",
            "andrew",
            "--change-note",
            "initial agreement",
        ],
    )
    show_result = runner.invoke(app, ["goals", "show", "--db", str(db_path)])
    brief_result = runner.invoke(app, ["goals", "agent-brief", "--db", str(db_path)])

    assert init_result.exit_code == 0
    assert "Saved active user goal #1" in init_result.output
    assert "version 1" in init_result.output
    assert "No Discord, R2, or Meta network calls were made." in init_result.output
    assert show_result.exit_code == 0
    assert "Travel account north star" in show_result.output
    assert "Grow with saveable city-guide carousels." in show_result.output
    assert "Content pillars:" in show_result.output
    assert "- city guides" in show_result.output
    assert brief_result.exit_code == 0
    assert "Active user goal" in brief_result.output
    assert "Recommend one best next post." in brief_result.output
    assert "This brief is advisory" in brief_result.output


def test_cli_goals_show_handles_missing_goal(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"

    result = runner.invoke(app, ["goals", "show", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "No active user goal is stored yet." in result.output
    assert "post-relay goals init" in result.output

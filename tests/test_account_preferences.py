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
    assert "avoid em dashes" in show_result.output
    assert brief_result.exit_code == 0
    assert "Goal/audience required before copy-heavy advice: yes" in brief_result.output

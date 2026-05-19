from pathlib import Path

from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.indexer import index_photo_sources
from post_relay.post_opportunities import (
    create_post_opportunity,
    dismiss_post_opportunity,
    snooze_post_opportunity,
    convert_post_opportunity_to_draft,
    mark_post_opportunity_dm_sent,
    plan_proactive_opportunity_dm,
)
from post_relay.repository import get_draft, list_post_opportunities


runner = CliRunner()


def _build_fixture_library(tmp_path: Path):
    root = tmp_path / "processed"
    kyoto = root / "2025" / "kyoto-night-market"
    kyoto.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-lanterns.jpg"]:
        (kyoto / filename).write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    return connection, root


def test_create_post_opportunity_dedupes_active_trigger_key_and_sanitizes_text(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)

    first = create_post_opportunity(
        connection,
        trigger_type="new_media",
        trigger_key="processed/2025/kyoto-night-market",
        title="Kyoto night market candidate",
        summary="Fresh processed set from token=fake-token",
        rationale="New folder has enough images: https://signed.example/photo.jpg?token=fake-token",
        suggested_next_action="Ask Andrew whether to pick 5 for a carousel.",
    )
    second = create_post_opportunity(
        connection,
        trigger_type="new_media",
        trigger_key="processed/2025/kyoto-night-market",
        title="Duplicate should reuse",
        summary="duplicate",
        rationale="duplicate",
        suggested_next_action="duplicate",
    )

    assert second.id == first.id
    assert first.status == "new"
    assert "fake-token" not in first.summary
    assert "signed.example" not in first.rationale
    assert "pick 5" in first.suggested_next_action
    assert len(list_post_opportunities(connection)) == 1


def test_dismissed_opportunity_allows_future_opportunity_for_same_trigger(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    first = create_post_opportunity(
        connection,
        trigger_type="cadence_due",
        trigger_key="2026-05-17",
        title="Cadence due",
        summary="It has been several days since the last feed post.",
        rationale="Simple cadence check says a backlog post is reasonable.",
        suggested_next_action="Offer one low-friction backlog option.",
    )

    dismissed = dismiss_post_opportunity(connection, first.id, reason="Not today")
    replacement = create_post_opportunity(
        connection,
        trigger_type="cadence_due",
        trigger_key="2026-05-17",
        title="Cadence due again",
        summary="Another local check can recreate this later.",
        rationale="Dismissed opportunities should not block future checks forever.",
        suggested_next_action="Create a fresh suggestion if still relevant.",
    )

    assert dismissed.status == "dismissed"
    assert replacement.id != first.id
    assert replacement.status == "new"
    assert len(list_post_opportunities(connection)) == 2


def test_snooze_opportunity_records_due_time_without_sending_dm(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    opportunity = create_post_opportunity(
        connection,
        trigger_type="trend_window",
        trigger_key="spring-flowers-window",
        title="Spring flowers timing",
        summary="A seasonal window may be relevant.",
        rationale="Manual trend timing note.",
        suggested_next_action="Snooze until Andrew has time to review.",
    )

    snoozed = snooze_post_opportunity(
        connection, opportunity.id, snoozed_until="2026-05-20T09:30:00-07:00")

    assert snoozed.status == "snoozed"
    assert snoozed.snoozed_until == "2026-05-20T09:30:00-07:00"


def test_convert_opportunity_to_draft_links_candidate_and_preserves_double_approval_state(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    candidate_id = connection.execute("select id from candidate_groups").fetchone()[0]
    opportunity = create_post_opportunity(
        connection,
        trigger_type="new_media",
        trigger_key="processed/2025/kyoto-night-market",
        title="Kyoto night market candidate",
        summary="Fresh processed set.",
        rationale="Enough images for carousel planning.",
        suggested_next_action="Create a draft and ask Andrew to select media.",
        candidate_group_id=candidate_id,
    )

    converted = convert_post_opportunity_to_draft(connection, opportunity.id)
    draft = get_draft(connection, converted.draft_id)

    assert converted.status == "converted_to_draft"
    assert converted.candidate_group_id == candidate_id
    assert draft is not None
    assert draft.status == "drafting"
    assert draft.candidate_group_id == candidate_id


def test_plan_proactive_opportunity_dm_renders_safe_operator_controls_without_sending(tmp_path: Path):
    connection, root = _build_fixture_library(tmp_path)
    candidate_id = connection.execute("select id from candidate_groups").fetchone()[0]
    opportunity = create_post_opportunity(
        connection,
        trigger_type="new_media",
        trigger_key="processed/2025/kyoto-night-market",
        title="Kyoto night market candidate",
        summary="Fresh processed set from token=fake-token.",
        rationale="Enough images for carousel planning at https://signed.example/photo.jpg.",
        suggested_next_action="Ask Andrew whether to pick 5 for a carousel.",
        candidate_group_id=candidate_id,
    )

    plan = plan_proactive_opportunity_dm(connection, opportunity.id)
    text = plan.to_text()

    assert plan.opportunity.id == opportunity.id
    assert plan.requires_explicit_send_authorization is True
    assert "Proactive opportunity DM plan" in text
    assert "Suggested DM copy:" in text
    assert "Kyoto night market candidate" in text
    assert "Reply with one of:" in text
    assert "yes / snooze / dismiss" in text
    assert "post-relay opportunities convert-to-draft --opportunity-id" in text
    assert "post-relay opportunities mark-dm-sent --opportunity-id" in text
    assert "Requires explicit operator authorization before any Discord send." in text
    assert "No Discord, R2, or Meta network calls were made." in text
    assert root.as_posix() not in text
    assert "fake-token" not in text
    assert "signed.example" not in text


def test_mark_opportunity_dm_sent_is_explicit_local_state_only_and_blocks_terminal_statuses(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    opportunity = create_post_opportunity(
        connection,
        trigger_type="cadence_due",
        trigger_key="weekly-2026-05-19",
        title="Weekly posting window",
        summary="Queue a reviewed travel set.",
        rationale="Maintain posting cadence.",
        suggested_next_action="Ask Andrew whether to review one backlog option.",
    )

    marked = mark_post_opportunity_dm_sent(connection, opportunity.id)
    second_mark = mark_post_opportunity_dm_sent(connection, opportunity.id)
    dismissed = create_post_opportunity(
        connection,
        trigger_type="life_event",
        trigger_key="already-dismissed",
        title="Dismissed memory",
        summary="A dismissed memory.",
        rationale="Not relevant anymore.",
        suggested_next_action="Do not send.",
    )
    dismiss_post_opportunity(connection, dismissed.id, reason="not relevant")

    assert marked.status == "dm_sent"
    assert second_mark.status == "dm_sent"
    try:
        mark_post_opportunity_dm_sent(connection, dismissed.id)
    except ValueError as error:
        assert "cannot be marked DM sent" in str(error)
    else:
        raise AssertionError("dismissed opportunities must not be markable as sent")


def test_cli_opportunities_create_list_dismiss_and_convert_without_network_calls(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    candidate_id = connection.execute("select id from candidate_groups").fetchone()[0]

    create_result = runner.invoke(
        app,
        [
            "opportunities",
            "create",
            "--trigger-type",
            "life_event",
            "--trigger-key",
            "andrew-kyoto-memory",
            "--title",
            "Kyoto memory",
            "--summary",
            "Andrew mentioned a Kyoto memory with token=fake-token",
            "--rationale",
            "User-provided life/trip context can become a post.",
            "--suggested-next-action",
            "Ask Andrew whether to turn this into a carousel draft.",
            "--candidate-id",
            str(candidate_id),
            "--db",
            str(db_path),
        ],
    )
    list_result = runner.invoke(app, ["opportunities", "list", "--db", str(db_path)])
    dm_plan_result = runner.invoke(
        app,
        ["opportunities", "dm-plan", "--opportunity-id", "1", "--db", str(db_path)],
    )
    mark_sent_result = runner.invoke(
        app,
        ["opportunities", "mark-dm-sent", "--opportunity-id", "1", "--db", str(db_path)],
    )
    convert_result = runner.invoke(
        app,
        ["opportunities", "convert-to-draft", "--opportunity-id", "1", "--db", str(db_path)],
    )
    dismiss_result = runner.invoke(
        app,
        ["opportunities", "dismiss", "--opportunity-id", "1", "--reason", "Already handled", "--db", str(db_path)],
    )

    assert create_result.exit_code == 0
    assert "Post opportunity #1" in create_result.output
    assert "No Discord or Meta network calls were made." in create_result.output
    assert "fake-token" not in create_result.output
    assert list_result.exit_code == 0
    assert "Kyoto memory" in list_result.output
    assert "No Discord or Meta network calls were made." in list_result.output
    assert dm_plan_result.exit_code == 0
    assert "Proactive opportunity DM plan" in dm_plan_result.output
    assert "Requires explicit operator authorization before any Discord send." in dm_plan_result.output
    assert "No Discord, R2, or Meta network calls were made." in dm_plan_result.output
    assert mark_sent_result.exit_code == 0
    assert "marked DM sent" in mark_sent_result.output
    assert "No Discord, R2, or Meta network calls were made." in mark_sent_result.output
    assert convert_result.exit_code == 0
    assert "converted to post #" in convert_result.output
    assert dismiss_result.exit_code == 0
    assert "dismissed" in dismiss_result.output

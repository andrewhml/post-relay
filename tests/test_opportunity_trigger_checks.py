from pathlib import Path

from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.indexer import index_photo_sources
from post_relay.opportunity_checks import plan_opportunity_checks, execute_opportunity_checks
from post_relay.post_opportunities import snooze_post_opportunity
from post_relay.repository import list_post_opportunities, update_draft_schedule
from post_relay.drafts import create_draft_from_candidate


runner = CliRunner()


def _build_fixture_library(tmp_path: Path):
    root = tmp_path / "processed"
    kyoto = root / "2025" / "kyoto-night-market"
    seoul = root / "2025" / "seoul-cafe-windows"
    kyoto.mkdir(parents=True)
    seoul.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-lanterns.jpg"]:
        (kyoto / filename).write_bytes(b"fake image")
    for filename in ["01-window.jpg", "02-table.jpg"]:
        (seoul / filename).write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    return connection, root


def test_plan_opportunity_checks_detects_new_candidate_media_without_persisting_by_default(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    first_candidate_id = connection.execute("select min(id) from candidate_groups").fetchone()[0]
    create_draft_from_candidate(connection, first_candidate_id)

    result = plan_opportunity_checks(connection, now="2026-05-17T09:00:00-07:00")

    assert result.created_count == 0
    assert len(result.planned) == 1
    planned = result.planned[0]
    assert planned.trigger_type == "new_media"
    assert planned.candidate_group_id != first_candidate_id
    assert "No Discord or Meta network calls were made." in result.to_text()
    assert list_post_opportunities(connection) == []


def test_execute_opportunity_checks_creates_deduped_local_records_and_respects_snooze(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)

    first = execute_opportunity_checks(connection, now="2026-05-17T09:00:00-07:00")
    second = execute_opportunity_checks(connection, now="2026-05-17T10:00:00-07:00")
    opportunity = list_post_opportunities(connection)[0]
    snooze_post_opportunity(connection, opportunity.id, snoozed_until="2026-05-20T09:00:00-07:00")
    third = execute_opportunity_checks(connection, now="2026-05-18T09:00:00-07:00")

    assert first.created_count == 2
    assert second.created_count == 0
    assert len(list_post_opportunities(connection)) == 2
    assert any("already has an active opportunity" in skipped.reason for skipped in second.skipped)
    assert third.created_count == 0
    assert any("snoozed until 2026-05-20T09:00:00-07:00" in skipped.reason for skipped in third.skipped)
    assert len(list_post_opportunities(connection)) == 2


def test_cadence_and_inactivity_checks_use_local_schedule_history_and_thresholds(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    candidate_id = connection.execute("select min(id) from candidate_groups").fetchone()[0]
    draft = create_draft_from_candidate(connection, candidate_id)
    update_draft_schedule(
        connection,
        draft.id,
        scheduled_for="2026-05-10T09:30:00-07:00",
        status="posted",
    )

    result = plan_opportunity_checks(
        connection,
        now="2026-05-17T09:00:00-07:00",
        cadence_due_after_days=3,
        inactivity_after_days=30,
        include_new_media=False,
    )
    quiet_result = plan_opportunity_checks(
        connection,
        now="2026-05-17T09:00:00-07:00",
        cadence_due_after_days=10,
        inactivity_after_days=30,
        include_new_media=False,
    )

    assert [planned.trigger_type for planned in result.planned] == ["cadence_due"]
    assert "last scheduled/posted item was 7 days ago" in result.planned[0].rationale
    assert quiet_result.planned == []

    empty_connection = connect_db(tmp_path / "empty.sqlite")
    initialize_db(empty_connection)
    inactivity_result = plan_opportunity_checks(
        empty_connection,
        now="2026-05-17T09:00:00-07:00",
        include_new_media=False,
    )

    assert [planned.trigger_type for planned in inactivity_result.planned] == ["inactivity"]


def test_cli_opportunity_checks_dry_run_execute_and_manual_seed_without_network_calls(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"

    dry_run = runner.invoke(app, ["opportunities", "check", "--db", str(db_path)])
    after_dry_run = list_post_opportunities(connection)
    execute = runner.invoke(
        app,
        [
            "opportunities",
            "check",
            "--execute",
            "--manual-trigger-type",
            "life_event",
            "--manual-trigger-key",
            "andrew-kyoto-memory",
            "--manual-title",
            "Kyoto memory",
            "--manual-summary",
            "Andrew mentioned a Kyoto memory with secret=fake",
            "--manual-rationale",
            "Manual trip context can become a post.",
            "--manual-suggested-next-action",
            "Ask Andrew whether to turn this into a carousel draft.",
            "--db",
            str(db_path),
        ],
    )
    opportunities = list_post_opportunities(connection)

    assert dry_run.exit_code == 0
    assert "Dry run: planned" in dry_run.output
    assert "No Discord or Meta network calls were made." in dry_run.output
    assert after_dry_run == []
    assert execute.exit_code == 0
    assert "Created" in execute.output
    assert "fake" not in execute.output
    assert "No Discord or Meta network calls were made." in execute.output
    assert any(opportunity.trigger_type == "life_event" for opportunity in opportunities)

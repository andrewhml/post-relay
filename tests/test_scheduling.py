from pathlib import Path

import pytest
from typer.testing import CliRunner

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import get_draft, list_active_approvals, list_candidate_groups
from post_relay.scheduled_posts import build_scheduled_post_feedback
from post_relay.scheduling import (
    DraftNotFound,
    DraftNotReadyForPublishApproval,
    DraftNotReadyForScheduling,
    approve_draft_for_publishing,
    request_publish_approval,
    schedule_draft,
)
from post_relay.state import ApprovalType, DraftState


runner = CliRunner()


def _build_approved_fixture_draft(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    return connection, get_draft(connection, draft.id)


def test_schedule_draft_sets_time_and_moves_approved_draft_to_scheduled(tmp_path: Path):
    connection, draft = _build_approved_fixture_draft(tmp_path)

    scheduled = schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")

    assert scheduled.status == DraftState.SCHEDULED.value
    assert scheduled.scheduled_for == "2026-05-05T09:30:00-07:00"
    assert get_draft(connection, draft.id).scheduled_for == "2026-05-05T09:30:00-07:00"


def test_schedule_draft_requires_draft_approval_queue_status(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        schedule_draft(connection, 999, scheduled_for="2026-05-05T09:30:00-07:00")

    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    draft = create_draft_from_candidate(connection, list_candidate_groups(connection)[0].id)

    with pytest.raises(DraftNotReadyForScheduling):
        schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")


def test_publish_approval_records_publish_approval_directly_after_scheduling(tmp_path: Path):
    connection, draft = _build_approved_fixture_draft(tmp_path)
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")

    approval = approve_draft_for_publishing(
        connection,
        draft.id,
        approved_by="andrew",
        notes="Final publish approval after schedule check.",
    )

    assert approval.draft_id == draft.id
    assert approval.approval_type == ApprovalType.PUBLISH.value
    assert approval.approved_by == "andrew"
    assert approval.notes == "Final publish approval after schedule check."
    assert get_draft(connection, draft.id).status == DraftState.READY_TO_PUBLISH.value
    assert [approval.approval_type for approval in list_active_approvals(connection, draft.id)] == [
        ApprovalType.DRAFT.value,
        ApprovalType.PUBLISH.value,
    ]


def test_request_publish_approval_is_legacy_noop_for_scheduled_posts(tmp_path: Path):
    connection, draft = _build_approved_fixture_draft(tmp_path)
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")

    updated = request_publish_approval(connection, draft.id)

    assert updated.status == DraftState.SCHEDULED.value
    assert updated.scheduled_for == "2026-05-05T09:30:00-07:00"


def test_publish_approval_requires_scheduled_status(tmp_path: Path):
    connection, draft = _build_approved_fixture_draft(tmp_path)

    with pytest.raises(DraftNotReadyForPublishApproval):
        approve_draft_for_publishing(connection, draft.id, approved_by="andrew")


def test_scheduled_post_feedback_lists_existing_queue_in_schedule_order(tmp_path: Path):
    connection, first = _build_approved_fixture_draft(tmp_path)
    scheduled_first = schedule_draft(connection, first.id, scheduled_for="2026-06-08T09:30:00-07:00")

    candidate_cursor = connection.execute(
        "insert into candidate_groups (title, source_name, source_folder, post_type_recommendation, confidence, reason) values (?, ?, ?, ?, ?, ?)",
        ("Second post", "processed", "second-post", "carousel", 1.0, "test"),
    )
    cursor = connection.execute(
        "insert into drafts (candidate_group_id, post_type, status, scheduled_for) values (?, ?, ?, ?)",
        (int(candidate_cursor.lastrowid), "carousel", DraftState.READY_TO_PUBLISH.value, "2026-06-01T09:30:00-07:00"),
    )
    connection.commit()
    second_id = int(cursor.lastrowid)

    feedback = build_scheduled_post_feedback(connection)
    text = feedback.to_text()

    assert [item.draft_id for item in feedback.items] == [second_id, scheduled_first.id]
    assert f"#{second_id} ready_to_publish carousel at 2026-06-01T09:30:00-07:00" in text
    assert f"#{scheduled_first.id} scheduled carousel at 2026-06-08T09:30:00-07:00" in text
    assert "Use this queue before recommending another slot." in text


def test_schedule_cli_warns_when_another_post_is_already_scheduled(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
""".strip()
    )
    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    connection = connect_db(db_path)
    submit_draft_for_review(connection, 1)
    approve_draft_content(connection, 1, approved_by="andrew")
    schedule_draft(connection, 1, scheduled_for="2026-06-01T09:30:00-07:00")
    candidate_cursor = connection.execute(
        "insert into candidate_groups (title, source_name, source_folder, post_type_recommendation, confidence, reason) values (?, ?, ?, ?, ?, ?)",
        ("Second post", "processed", "second-post", "single_image", 1.0, "test"),
    )
    cursor = connection.execute("insert into drafts (candidate_group_id, post_type, status) values (?, ?, ?)", (int(candidate_cursor.lastrowid), "single_image", DraftState.APPROVED_FOR_QUEUE.value))
    connection.commit()
    second_id = int(cursor.lastrowid)

    result = runner.invoke(app, ["drafts", "schedule", "--post-id", str(second_id), "--scheduled-for", "2026-06-08T09:30:00-07:00", "--db", str(db_path)])

    assert result.exit_code == 0
    assert f"Scheduled post #{second_id} for 2026-06-08T09:30:00-07:00" in result.output
    assert "Scheduled posts:" in result.output
    assert "#1 scheduled single_image at 2026-06-01T09:30:00-07:00" in result.output

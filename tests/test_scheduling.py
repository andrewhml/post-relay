from pathlib import Path

import pytest

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import get_draft, list_active_approvals, list_candidate_groups
from post_relay.scheduling import (
    DraftNotFound,
    DraftNotReadyForPublishApproval,
    DraftNotReadyForScheduling,
    approve_draft_for_publishing,
    request_publish_approval,
    schedule_draft,
)
from post_relay.state import ApprovalType, DraftState


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


def test_request_publish_approval_moves_scheduled_draft_to_awaiting_publish_approval(tmp_path: Path):
    connection, draft = _build_approved_fixture_draft(tmp_path)
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")

    updated = request_publish_approval(connection, draft.id)

    assert updated.status == DraftState.AWAITING_PUBLISH_APPROVAL.value
    assert updated.scheduled_for == "2026-05-05T09:30:00-07:00"


def test_publish_approval_records_publish_approval_and_moves_to_ready(tmp_path: Path):
    connection, draft = _build_approved_fixture_draft(tmp_path)
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")
    request_publish_approval(connection, draft.id)

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


def test_publish_approval_requires_awaiting_publish_approval_status(tmp_path: Path):
    connection, draft = _build_approved_fixture_draft(tmp_path)
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")

    with pytest.raises(DraftNotReadyForPublishApproval):
        approve_draft_for_publishing(connection, draft.id, approved_by="andrew")

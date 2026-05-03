from pathlib import Path

import pytest

from post_relay.approvals import (
    DraftNotFound,
    DraftNotReadyForApproval,
    approve_draft_content,
    edit_draft_content,
    submit_draft_for_review,
)
from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import get_draft, list_active_approvals, list_candidate_groups
from post_relay.state import ApprovalType, DraftState


def _build_fixture_draft(tmp_path: Path):
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
    return connection, draft


def test_submit_draft_for_review_moves_drafting_draft_to_awaiting_review(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)

    updated = submit_draft_for_review(connection, draft.id)

    assert updated.status == DraftState.AWAITING_REVIEW.value
    assert get_draft(connection, draft.id).status == DraftState.AWAITING_REVIEW.value


def test_approve_draft_content_records_draft_approval_and_moves_to_queue(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)

    approval = approve_draft_content(
        connection,
        draft.id,
        approved_by="andrew",
        notes="Looks good for a carousel.",
    )

    assert approval.draft_id == draft.id
    assert approval.approval_type == ApprovalType.DRAFT.value
    assert approval.approved_by == "andrew"
    assert approval.notes == "Looks good for a carousel."
    assert approval.invalidated_at is None
    assert get_draft(connection, draft.id).status == DraftState.APPROVED_FOR_QUEUE.value
    assert list_active_approvals(connection, draft.id) == [approval]


def test_approve_draft_content_requires_awaiting_review_status(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)

    with pytest.raises(DraftNotReadyForApproval):
        approve_draft_content(connection, draft.id, approved_by="andrew")


def test_material_draft_edit_after_approval_invalidates_approval_and_needs_edits(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")

    updated = edit_draft_content(
        connection,
        draft.id,
        caption="A quiet morning wandering through Kyoto temple gardens.",
    )

    assert updated.caption == "A quiet morning wandering through Kyoto temple gardens."
    assert updated.status == DraftState.NEEDS_EDITS.value
    assert list_active_approvals(connection, draft.id) == []


def test_approval_helpers_raise_for_missing_draft(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        submit_draft_for_review(connection, 999)
    with pytest.raises(DraftNotFound):
        approve_draft_content(connection, 999, approved_by="andrew")
    with pytest.raises(DraftNotFound):
        edit_draft_content(connection, 999, caption="missing")

from pathlib import Path

import pytest

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.media_selection import (
    DraftNotFound,
    InvalidMediaSelection,
    apply_draft_media_selection,
    build_draft_media_plan,
)
from post_relay.repository import get_draft, list_active_approvals, list_candidate_groups
from post_relay.review_package import build_draft_review_package
from post_relay.state import DraftState


def _build_fixture_draft(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-hero.jpg", "04-duplicate.jpg"]:
        (folder / filename).write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    return connection, draft, folder


def test_build_draft_media_plan_numbers_included_media_for_contact_sheet_review(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)

    plan = build_draft_media_plan(connection, draft.id)

    assert plan.draft_id == draft.id
    assert [item.review_number for item in plan.items] == [1, 2, 3, 4]
    assert [Path(item.local_file_path).name for item in plan.items] == [
        "01-wide.jpg",
        "02-detail.jpg",
        "03-hero.jpg",
        "04-duplicate.jpg",
    ]
    assert [item.role for item in plan.items] == ["primary", "support", "support", "support"]
    assert all(item.include_status == "included" for item in plan.items)
    assert str(folder) in plan.to_text()
    assert "1. [primary] included" in plan.to_text()


def test_apply_draft_media_selection_sets_lead_keep_and_post_type(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)

    result = apply_draft_media_selection(
        connection,
        draft.id,
        lead=3,
        keep=[1, 3, 4],
        post_type="carousel",
    )

    assert result.draft_id == draft.id
    assert result.post_type == "carousel"
    assert [Path(item.local_file_path).name for item in result.included_items] == [
        "03-hero.jpg",
        "01-wide.jpg",
        "04-duplicate.jpg",
    ]
    assert [item.role for item in result.included_items] == ["primary", "support", "support"]
    assert [Path(item.local_file_path).name for item in result.excluded_items] == ["02-detail.jpg"]
    assert [item.include_status for item in result.excluded_items] == ["excluded"]

    review = build_draft_review_package(connection, draft.id)
    assert review.photo_file_paths == [
        (folder / "03-hero.jpg").as_posix(),
        (folder / "01-wide.jpg").as_posix(),
        (folder / "04-duplicate.jpg").as_posix(),
    ]
    assert get_draft(connection, draft.id).post_type == "carousel"


def test_apply_draft_media_selection_remove_uses_remaining_order_and_lead(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)

    result = apply_draft_media_selection(connection, draft.id, lead=2, remove=[4])

    assert [Path(item.local_file_path).name for item in result.included_items] == [
        "02-detail.jpg",
        "01-wide.jpg",
        "03-hero.jpg",
    ]
    assert [Path(item.local_file_path).name for item in result.excluded_items] == ["04-duplicate.jpg"]


def test_apply_draft_media_selection_invalidates_active_approvals(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    assert list_active_approvals(connection, draft.id)

    result = apply_draft_media_selection(connection, draft.id, lead=2, remove=[4])

    assert result.invalidated_approval_count == 1
    assert list_active_approvals(connection, draft.id) == []
    assert get_draft(connection, draft.id).status == DraftState.NEEDS_EDITS.value


def test_apply_draft_media_selection_rejects_missing_draft(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        build_draft_media_plan(connection, 999)


def test_apply_draft_media_selection_rejects_invalid_positions(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)

    with pytest.raises(InvalidMediaSelection):
        apply_draft_media_selection(connection, draft.id, lead=9, keep=[1, 9])

    with pytest.raises(InvalidMediaSelection):
        apply_draft_media_selection(connection, draft.id, lead=1, keep=[1], post_type="carousel")

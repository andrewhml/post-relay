from pathlib import Path

import pytest
from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.media_selection import (
    InvalidMediaSelection,
    apply_draft_crop_feedback,
    build_draft_media_plan,
)
from post_relay.repository import list_active_approvals, list_candidate_groups
from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.state import DraftState
from post_relay.repository import get_draft


runner = CliRunner()


def _build_fixture_draft(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-hero.jpg"]:
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


def test_apply_draft_crop_feedback_sets_anchor_tightness_ratio_and_summarizes_chat_vocabulary(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)

    result = apply_draft_crop_feedback(
        connection,
        draft.id,
        crop_edits={3: {"anchor": "B2", "tightness": 0.85, "ratio": 0.8}},
    )

    assert result.draft_id == draft.id
    assert result.updated_items[0].review_number == 3
    assert result.updated_items[0].crop_anchor == "B2"
    assert result.updated_items[0].crop_anchor_x == 0.25
    assert result.updated_items[0].crop_anchor_y == 0.25
    assert result.updated_items[0].crop_tightness == 0.85
    assert result.updated_items[0].crop_ratio == 0.8
    assert "Moved 3's crop anchor to B2" in result.to_text()
    assert "tightness medium" in result.to_text()
    assert "ratio 4:5" in result.to_text()

    plan = build_draft_media_plan(connection, draft.id)
    third = plan.items[2]
    assert third.crop_anchor == "B2"
    assert third.crop_tightness == 0.85
    assert third.crop_ratio == 0.8
    assert "crop B2" in plan.to_text()


def test_apply_draft_crop_feedback_understands_center_and_nudge_feedback(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)
    apply_draft_crop_feedback(connection, draft.id, crop_edits={2: {"anchor": "B2"}})

    result = apply_draft_crop_feedback(
        connection,
        draft.id,
        crop_edits={2: {"center": True, "nudge_x": 1, "nudge_y": 1, "tightness_delta": -0.1}},
    )

    item = result.updated_items[0]
    assert item.review_number == 2
    assert item.crop_anchor == "D4"
    assert item.crop_tightness == 0.9


def test_apply_draft_crop_feedback_invalidates_active_approvals(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    assert list_active_approvals(connection, draft.id)

    result = apply_draft_crop_feedback(connection, draft.id, crop_edits={1: {"anchor": "C3"}})

    assert result.invalidated_approval_count == 1
    assert list_active_approvals(connection, draft.id) == []
    assert get_draft(connection, draft.id).status == DraftState.NEEDS_EDITS.value


def test_apply_draft_crop_feedback_rejects_unknown_number_or_anchor(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)

    with pytest.raises(InvalidMediaSelection):
        apply_draft_crop_feedback(connection, draft.id, crop_edits={9: {"anchor": "B2"}})

    with pytest.raises(InvalidMediaSelection):
        apply_draft_crop_feedback(connection, draft.id, crop_edits={1: {"anchor": "Z9"}})


def test_cli_draft_crop_feedback_command_persists_chat_crop_language(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)
    connection.close()

    result = runner.invoke(
        app,
        [
            "drafts",
            "crop-feedback",
            "--draft-id",
            str(draft.id),
            "--shift",
            "3:B2",
            "--tighten",
            "3",
            "--ratio",
            "3:4:5",
            "--db",
            str(tmp_path / "post_relay.sqlite"),
        ],
    )

    assert result.exit_code == 0
    assert "Crop Feedback Applied" in result.output
    assert "Moved 3's crop anchor to B2" in result.output
    assert "ratio 4:5" in result.output
    assert "No Discord, R2, or Meta network calls were made." in result.output

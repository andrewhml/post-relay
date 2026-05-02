from pathlib import Path

import pytest

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import CandidateNotFound, create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups, list_drafts
from post_relay.state import DraftState


def _build_fixture_candidate(tmp_path: Path):
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
    return connection, candidate


def test_create_draft_from_candidate_persists_initial_draft(tmp_path: Path):
    connection, candidate = _build_fixture_candidate(tmp_path)

    draft = create_draft_from_candidate(connection, candidate.id)

    assert draft.candidate_group_id == candidate.id
    assert draft.post_type == "carousel"
    assert draft.status == DraftState.DRAFTING.value
    assert draft.caption is None
    assert draft.hashtags_json is None
    assert draft.location_text is None
    assert draft.alt_text is None
    assert list_drafts(connection) == [draft]


def test_create_draft_from_candidate_is_idempotent(tmp_path: Path):
    connection, candidate = _build_fixture_candidate(tmp_path)

    first = create_draft_from_candidate(connection, candidate.id)
    second = create_draft_from_candidate(connection, candidate.id)

    assert first == second
    assert len(list_drafts(connection)) == 1


def test_create_draft_from_missing_candidate_raises(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(CandidateNotFound):
        create_draft_from_candidate(connection, 999)

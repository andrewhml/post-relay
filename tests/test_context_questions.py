from pathlib import Path

import pytest

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.context_questions import DraftNotFound, generate_context_questions_for_draft
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups, list_context_questions


def _build_fixture_draft(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "garden.jpg").write_bytes(b"fake image")
    (folder / "temple.jpg").write_bytes(b"fake image")
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


def test_generate_context_questions_for_draft_persists_missing_context_questions(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)

    questions = generate_context_questions_for_draft(connection, draft.id)

    assert [question.field_name for question in questions] == [
        "place",
        "trip_name",
        "approximate_date",
        "mood",
        "story_angle",
    ]
    assert questions[0].question_text == "Where exactly was this photo set taken?"
    assert questions[1].question_text == "What trip or collection should this post be associated with?"
    assert questions[2].question_text == "Should this be described as part of the 2023 trip, or is there a more specific date?"
    assert questions[3].question_text == "What mood should the caption convey?"
    assert questions[4].question_text == "What story or takeaway should this post highlight?"
    assert all(question.status == "unresolved" for question in questions)
    assert list_context_questions(connection, draft.id) == questions


def test_generate_context_questions_for_draft_is_idempotent(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)

    first = generate_context_questions_for_draft(connection, draft.id)
    second = generate_context_questions_for_draft(connection, draft.id)

    assert first == second
    assert len(list_context_questions(connection, draft.id)) == 5


def test_generate_context_questions_for_missing_draft_raises(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        generate_context_questions_for_draft(connection, 999)

from pathlib import Path

import pytest

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.context_questions import DraftNotFound, generate_context_questions_for_draft
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import (
    list_candidate_groups,
    list_context_questions,
    update_draft_content,
    upsert_draft_location_tag,
    upsert_guided_draft_package,
)


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
        "mood",
        "story_angle",
    ]
    assert questions[0].question_text == "Where exactly was this photo set taken?"
    assert questions[1].question_text == "What mood should the caption convey?"
    assert questions[2].question_text == "What story or takeaway should this post highlight?"
    assert all(question.status == "unresolved" for question in questions)
    assert list_context_questions(connection, draft.id) == questions


def test_generate_context_questions_for_draft_is_idempotent(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)

    first = generate_context_questions_for_draft(connection, draft.id)
    second = generate_context_questions_for_draft(connection, draft.id)

    assert first == second
    assert len(list_context_questions(connection, draft.id)) == 3


def test_generate_context_questions_uses_existing_draft_context_and_folder_assumptions(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)
    update_draft_content(
        connection,
        draft.id,
        caption="A quiet Kyoto garden walk with a tiny temple detour.",
        location_text="Kyoto, Japan",
        alt_text="Two photos from a Kyoto garden and temple walk.",
    )
    connection.commit()

    questions = generate_context_questions_for_draft(connection, draft.id)

    assert questions == []
    assert list_context_questions(connection, draft.id) == []


def test_generate_context_questions_asks_only_targeted_location_tag_gap(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)
    update_draft_content(
        connection,
        draft.id,
        caption="A quiet Kyoto garden walk with a tiny temple detour.",
        location_text="Kyoto, Japan",
        alt_text="Two photos from a Kyoto garden and temple walk.",
    )
    upsert_guided_draft_package(
        connection,
        draft_id=draft.id,
        post_type_recommendation="carousel",
        post_type_rationale="Folder contains a coherent two-image Kyoto set.",
        caption_options=["A quiet Kyoto garden walk with a tiny temple detour."],
        hashtag_suggestions=["#Kyoto", "#JapanTravel"],
        location_text="Kyoto, Japan",
        alt_text="Two photos from a Kyoto garden and temple walk.",
        growth_rationale="Saveable city-walk post.",
        context_questions=[],
        accepted_caption_index=0,
        mark_accepted=True,
    )
    # A freeform location is local/review-only; without a resolved Page tag, ask only
    # whether to search for a publishable location tag instead of re-asking generic context.
    connection.commit()

    questions = generate_context_questions_for_draft(connection, draft.id)

    assert [question.field_name for question in questions] == ["location_tag"]
    assert questions[0].question_text == (
        "Freeform location text is local-only; should I search Meta Pages for a publishable location tag for Kyoto, Japan?"
    )


def test_generate_context_questions_suppresses_location_tag_when_reviewed_tag_exists(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)
    update_draft_content(
        connection,
        draft.id,
        caption="A quiet Kyoto garden walk with a tiny temple detour.",
        location_text="Kyoto, Japan",
        alt_text="Two photos from a Kyoto garden and temple walk.",
    )
    upsert_draft_location_tag(
        connection,
        draft_id=draft.id,
        page_id="12345",
        name="Kyoto, Japan",
        source="reviewed-test",
    )
    connection.commit()

    questions = generate_context_questions_for_draft(connection, draft.id)

    assert questions == []


def test_generate_context_questions_for_missing_draft_raises(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        generate_context_questions_for_draft(connection, 999)

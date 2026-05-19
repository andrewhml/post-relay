from pathlib import Path

import pytest

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups
from post_relay.context_questions import generate_context_questions_for_draft
from post_relay.review_package import DraftNotFound, build_draft_review_package
from post_relay.state import DraftState


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
    return connection, draft, candidate, folder


def test_build_draft_review_package_includes_candidate_context_and_ordered_photos(tmp_path: Path):
    connection, draft, candidate, folder = _build_fixture_draft(tmp_path)

    package = build_draft_review_package(connection, draft.id)

    assert package.draft_id == draft.id
    assert package.status == DraftState.DRAFTING.value
    assert package.candidate_title == candidate.title
    assert package.post_type == "carousel"
    assert package.photo_file_paths == [
        (folder / "garden.jpg").as_posix(),
        (folder / "temple.jpg").as_posix(),
    ]
    assert package.caption == ""
    assert package.location == ""
    assert package.hashtags == []
    assert package.alt_text == ""
    assert package.unresolved_context_notes == [
        "Caption is empty.",
        "Location is empty.",
        "Hashtags are empty.",
        "Alt text is empty.",
    ]
    assert package.allowed_next_actions == [
        "add caption/context",
        "answer unresolved context notes",
        "request edits",
        "approve post content",
    ]


def test_build_draft_review_package_formats_stable_local_preview_text(tmp_path: Path):
    connection, draft, _candidate, folder = _build_fixture_draft(tmp_path)

    package = build_draft_review_package(connection, draft.id)

    assert package.to_text() == "\n".join(
        [
            "Post Review Package",
            f"Post ID: {draft.id}",
            "Status: drafting",
            "Candidate: 2023 / kyoto",
            "Post type: carousel",
            "Photos:",
            f"  1. {(folder / 'garden.jpg').as_posix()}",
            f"  2. {(folder / 'temple.jpg').as_posix()}",
            "Caption: <empty>",
            "Location: <empty>",
            "Hashtags: <empty>",
            "Alt text: <empty>",
            "Unresolved context notes:",
            "  - Caption is empty.",
            "  - Location is empty.",
            "  - Hashtags are empty.",
            "  - Alt text is empty.",
            "Context questions:",
            "  - <none>",
            "Allowed next actions:",
            "  - add caption/context",
            "  - answer unresolved context notes",
            "  - request edits",
            "  - approve post content",
        ]
    )


def test_build_draft_review_package_includes_persisted_context_questions(tmp_path: Path):
    connection, draft, _candidate, _folder = _build_fixture_draft(tmp_path)
    generate_context_questions_for_draft(connection, draft.id)

    package = build_draft_review_package(connection, draft.id)

    assert [question.field_name for question in package.context_questions] == [
        "place",
        "trip_name",
        "approximate_date",
        "mood",
        "story_angle",
    ]
    assert "Context questions:" in package.to_text()
    assert "  - [place] Where exactly was this photo set taken?" in package.to_text()


def test_build_draft_review_package_raises_for_missing_draft(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        build_draft_review_package(connection, 999)

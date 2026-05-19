from pathlib import Path
from typing import Optional

import pytest
from typer.testing import CliRunner

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.discord_selection import (
    InvalidDiscordSelection,
    apply_discord_photo_selection,
    build_discord_selection_request,
)
from post_relay.indexer import index_photo_sources
from post_relay.repository import get_draft, list_active_approvals, list_candidate_groups
from post_relay.review_package import build_draft_review_package
from post_relay.state import DraftState


runner = CliRunner()


def _build_fixture_draft(tmp_path: Path, filenames: Optional[list[str]] = None):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    folder.mkdir(parents=True)
    for filename in filenames or [
        "01-wide.jpg",
        "02-detail.jpg",
        "03-hero.jpg",
        "04-crowd.jpg",
        "05-night.jpg",
    ]:
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


def test_build_discord_selection_request_numbers_suggested_photos_and_guidance(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)

    request = build_discord_selection_request(connection, draft.id, target_count=3, post_type="carousel")

    assert request.draft_id == draft.id
    assert request.target_count == 3
    assert request.suggested_count == 5
    assert request.post_type == "carousel"
    assert [item.review_number for item in request.items] == [1, 2, 3, 4, 5]
    assert [Path(item.local_file_path).name for item in request.items] == [
        "01-wide.jpg",
        "02-detail.jpg",
        "03-hero.jpg",
        "04-crowd.jpg",
        "05-night.jpg",
    ]
    text = request.to_text()
    assert "Discord Photo Selection Request" in text
    assert "Select 3 of 5 suggested photos" in text
    assert "Lead/cover: choose the strongest attention-grabbing opener" in text
    assert "discord-selection-apply --post-id" in text
    assert "--select 1,2,3 --lead 1 --target-count 3 --post-type carousel" in text
    assert (folder / "03-hero.jpg").as_posix() in text


@pytest.mark.parametrize(
    "target_count, post_type, message",
    [
        (0, "carousel", "Target selection count must be at least 1"),
        (6, "carousel", "cannot exceed suggested photo count"),
        (1, "carousel", "Carousel selections require 2 to 10 photos"),
        (2, "single_image", "Single-image selections require exactly one photo"),
    ],
)
def test_build_discord_selection_request_validates_selection_count(
    tmp_path: Path, target_count: int, post_type: str, message: str
):
    connection, draft, _folder = _build_fixture_draft(tmp_path)

    with pytest.raises(InvalidDiscordSelection, match=message):
        build_discord_selection_request(connection, draft.id, target_count=target_count, post_type=post_type)


def test_apply_discord_photo_selection_reuses_media_selection_and_invalidates_approvals(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    assert list_active_approvals(connection, draft.id)

    result = apply_discord_photo_selection(
        connection,
        draft.id,
        selected_numbers=[3, 1, 5],
        lead=3,
        target_count=3,
        post_type="carousel",
    )

    assert result.invalidated_approval_count == 1
    assert [Path(item.local_file_path).name for item in result.included_items] == [
        "03-hero.jpg",
        "01-wide.jpg",
        "05-night.jpg",
    ]
    assert get_draft(connection, draft.id).status == DraftState.NEEDS_EDITS.value
    assert list_active_approvals(connection, draft.id) == []
    review = build_draft_review_package(connection, draft.id)
    assert review.photo_file_paths == [
        (folder / "03-hero.jpg").as_posix(),
        (folder / "01-wide.jpg").as_posix(),
        (folder / "05-night.jpg").as_posix(),
    ]


def test_apply_discord_photo_selection_rejects_wrong_count_duplicates_and_missing_lead(tmp_path: Path):
    connection, draft, _folder = _build_fixture_draft(tmp_path)

    with pytest.raises(InvalidDiscordSelection, match="Select exactly 3 photo numbers"):
        apply_discord_photo_selection(
            connection,
            draft.id,
            selected_numbers=[1, 2],
            lead=1,
            target_count=3,
            post_type="carousel",
        )
    with pytest.raises(InvalidDiscordSelection, match="Duplicate selected photo numbers"):
        apply_discord_photo_selection(
            connection,
            draft.id,
            selected_numbers=[1, 1, 2],
            lead=1,
            target_count=3,
            post_type="carousel",
        )
    with pytest.raises(InvalidDiscordSelection, match="Lead photo must be included"):
        apply_discord_photo_selection(
            connection,
            draft.id,
            selected_numbers=[1, 2, 3],
            lead=4,
            target_count=3,
            post_type="carousel",
        )


def test_cli_discord_selection_plan_and_apply(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-hero.jpg", "04-crowd.jpg"]:
        (folder / filename).write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
""".strip()
    )
    db_path = tmp_path / "post_relay.sqlite"

    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    plan_result = runner.invoke(
        app,
        [
            "drafts",
            "discord-selection-plan",
            "--post-id",
            "1",
            "--target-count",
            "3",
            "--db",
            str(db_path),
        ],
    )
    apply_result = runner.invoke(
        app,
        [
            "drafts",
            "discord-selection-apply",
            "--post-id",
            "1",
            "--select",
            "3,1,4",
            "--lead",
            "3",
            "--target-count",
            "3",
            "--post-type",
            "carousel",
            "--db",
            str(db_path),
        ],
    )
    preview_result = runner.invoke(app, ["drafts", "preview", "--post-id", "1", "--db", str(db_path)])

    assert plan_result.exit_code == 0
    assert "Select 3 of 4 suggested photos" in plan_result.output
    assert "1. 01-wide.jpg" in plan_result.output
    assert apply_result.exit_code == 0
    assert "Updated media selection for post #1" in apply_result.output
    assert "Lead: 03-hero.jpg" in apply_result.output
    assert preview_result.output.index("03-hero.jpg") < preview_result.output.index("01-wide.jpg")
    assert "02-detail.jpg" not in preview_result.output

from pathlib import Path

import pytest

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.discord_preview import DraftNotFound, build_discord_preview_payload
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups


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
    return connection, draft, folder


def test_build_discord_preview_payload_includes_ordered_existing_image_paths(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)

    payload = build_discord_preview_payload(connection, draft.id)

    assert payload.draft_id == draft.id
    assert payload.destination == "discord"
    assert payload.dry_run is True
    assert payload.ready_to_send is True
    assert payload.image_paths == [
        (folder / "garden.jpg").as_posix(),
        (folder / "temple.jpg").as_posix(),
    ]
    assert payload.missing_image_paths == []
    assert "Draft Review Package" in payload.message_text
    assert "Candidate: 2023 / kyoto" in payload.message_text


def test_build_discord_preview_payload_reports_missing_images_without_sending(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)
    (folder / "temple.jpg").unlink()

    payload = build_discord_preview_payload(connection, draft.id)

    assert payload.ready_to_send is False
    assert payload.image_paths == [(folder / "garden.jpg").as_posix()]
    assert payload.missing_image_paths == [(folder / "temple.jpg").as_posix()]
    assert "Missing image files:" in payload.to_text()
    assert f"  - {(folder / 'temple.jpg').as_posix()}" in payload.to_text()


def test_discord_preview_payload_renders_stable_dry_run_text(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)

    payload = build_discord_preview_payload(connection, draft.id)

    assert payload.to_text() == "\n".join(
        [
            "Discord Preview Payload (dry run)",
            f"Draft ID: {draft.id}",
            "Ready to send: yes",
            "Image attachments:",
            f"  1. {(folder / 'garden.jpg').as_posix()}",
            f"  2. {(folder / 'temple.jpg').as_posix()}",
            "Missing image files:",
            "  - <none>",
            "Message text:",
            payload.message_text,
        ]
    )


def test_build_discord_preview_payload_raises_for_missing_draft(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        build_discord_preview_payload(connection, 999)

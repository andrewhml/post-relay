import json
from pathlib import Path
from typing import Optional

import pytest
from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.dm_guided_review import handle_dm_guided_review_reply
from post_relay.indexer import index_photo_sources
from post_relay.repository import (
    get_active_conversation_thread_for_channel,
    get_draft,
    get_guided_draft_package,
    list_candidate_groups,
    list_conversation_context_notes,
)


runner = CliRunner()


def _build_fixture_draft(tmp_path: Path, filenames: Optional[list[str]] = None):
    root = tmp_path / "processed"
    folder = root / "2025" / "kyoto-night-market"
    folder.mkdir(parents=True)
    for filename in filenames or ["01-wide.jpg", "02-detail.jpg", "03-hero.jpg"]:
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
    return connection, draft, root


def test_dm_guided_review_reply_accepts_caption_and_persists_package(tmp_path: Path):
    connection, draft, root = _build_fixture_draft(tmp_path)

    result = handle_dm_guided_review_reply(
        connection,
        draft.id,
        """location: Kyoto, Japan
story: night market alleys
mood: cinematic
hook: food and light
caption 2""",
        discord_channel_id="dm-channel-123",
    )

    updated = get_draft(connection, draft.id)
    package = get_guided_draft_package(connection, draft.id)
    thread = get_active_conversation_thread_for_channel(connection, "dm-channel-123")
    notes = list_conversation_context_notes(connection, thread.id)

    assert result.accepted_package is not None
    assert package is not None
    assert package.accepted_caption_index == 2
    assert updated.caption == result.accepted_package.caption
    assert updated.location_text == "Kyoto, Japan"
    assert "#kyoto" in json.loads(updated.hashtags_json)
    assert thread.status == "active"
    assert "Accepted guided review package" in thread.last_prompt_summary
    assert notes[-1].summary.startswith("location: Kyoto, Japan")
    text = result.to_text()
    assert "Accepted DM guided review for draft #" in text
    assert "Caption option: 2" in text
    assert "Publishable through Meta v1: media, caption text, hashtags in caption." in text
    assert "Review-only/local" in text
    assert "No Discord or Meta network calls were made." in text
    assert root.as_posix() not in text


def test_dm_guided_review_reply_without_caption_returns_questions_without_accepting(tmp_path: Path):
    connection, draft, root = _build_fixture_draft(tmp_path)

    result = handle_dm_guided_review_reply(
        connection,
        draft.id,
        "mood: cinematic and less touristy",
        discord_channel_id="dm-channel-123",
    )

    package = get_guided_draft_package(connection, draft.id)
    text = result.to_text()

    assert result.accepted_package is None
    assert package is None
    assert "DM guided review package" in text
    assert "Caption options:" in text
    assert "Questions for Andrew:" in text
    assert "Confirm the exact location/place" in text
    assert "Reply with `caption 1`" in text
    assert "No Discord or Meta network calls were made." in text
    assert root.as_posix() not in text


def test_dm_guided_review_reply_redacts_secrets_urls_and_local_paths(tmp_path: Path):
    connection, draft, root = _build_fixture_draft(tmp_path)

    result = handle_dm_guided_review_reply(
        connection,
        draft.id,
        "story: token: abc123 from /Users/andrewlee/Pictures/private.jpg; hook: see https://example.com/private; caption 1",
        discord_channel_id="dm-channel-123",
    )

    thread = get_active_conversation_thread_for_channel(connection, "dm-channel-123")
    notes = list_conversation_context_notes(connection, thread.id)
    text = result.to_text()
    updated = get_draft(connection, draft.id)

    assert "abc123" not in text
    assert "abc123" not in notes[-1].summary
    assert "abc123" not in updated.caption
    assert "/Users/andrewlee" not in text
    assert "/Users/andrewlee" not in notes[-1].summary
    assert "/Users/andrewlee" not in updated.caption
    assert "https://example.com" not in text
    assert "https://example.com" not in notes[-1].summary
    assert "[redacted" in text
    assert root.as_posix() not in text


def test_cli_dm_guided_review_apply_accepts_reply_without_network_calls(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "kyoto-night-market"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-hero.jpg"]:
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

    result = runner.invoke(
        app,
        [
            "discord",
            "dm-guided-review-apply",
            "--draft-id",
            "1",
            "--message",
            "location: Kyoto, Japan; story: night market alleys; mood: cinematic; hook: food and light; caption 1",
            "--discord-channel-id",
            "dm-channel-123",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Accepted DM guided review for draft #1" in result.output
    assert "No Discord or Meta network calls were made." in result.output
    assert root.as_posix() not in result.output

from pathlib import Path

from typing import Optional

from typer.testing import CliRunner

import post_relay.cli as cli_module
from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.dm_intake import handle_dm_intake
from post_relay.discord_dm import DiscordDmConfig, DiscordMessage, poll_dm_intake_reply
from post_relay.indexer import index_photo_sources
from post_relay.repository import (
    get_draft,
    list_candidate_groups,
    list_conversation_context_notes,
    list_conversation_threads,
)


runner = CliRunner()


class FakeDiscordTransport:
    def __init__(self, *, messages: Optional[list[DiscordMessage]] = None):
        self.messages = messages or []
        self.sent_messages: list[tuple[str, str]] = []
        self.created_for: list[str] = []

    def create_dm_channel(self, user_id: str) -> str:
        self.created_for.append(user_id)
        return f"dm-{user_id}"

    def send_message(self, channel_id: str, content: str) -> str:
        self.sent_messages.append((channel_id, content))
        return f"sent-{len(self.sent_messages)}"

    def list_messages(self, channel_id: str, *, after_message_id: Optional[str] = None, limit: int = 10):
        return self.messages


def _build_fixture_library(tmp_path: Path):
    root = tmp_path / "processed"
    kyoto = root / "2025" / "kyoto-night-market"
    seoul = root / "2025" / "seoul-alley"
    kyoto.mkdir(parents=True)
    seoul.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-lanterns.jpg"]:
        (kyoto / filename).write_bytes(b"fake image")
    for filename in ["01-street.jpg", "02-food.jpg"]:
        (seoul / filename).write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    return connection, root


def test_user_dm_starts_private_conversation_and_suggests_matching_candidates(tmp_path: Path):
    connection, root = _build_fixture_library(tmp_path)

    result = handle_dm_intake(
        connection,
        "start a post about my Kyoto night market photos. Make it cinematic and less touristy.",
        discord_channel_id="dm-andrew-123",
    )

    assert result.thread.status == "waiting_for_user"
    assert result.thread.discord_channel_id == "dm-andrew-123"
    assert result.thread.draft_id is None
    assert result.suggested_candidates
    assert result.suggested_candidates[0].title == "2025 / kyoto-night-market"
    text = result.to_text()
    assert "Post Relay DM intake" in text
    assert "Private DM mode: user-initiated" in text
    assert "2025 / kyoto-night-market" in text
    assert "choose candidate #" in text
    assert root.as_posix() not in text
    assert "fake-token" not in text


def test_user_dm_with_active_draft_records_sanitized_context_and_routes_to_next_step(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)

    result = handle_dm_intake(
        connection,
        "For this one, keep it cinematic, mention the lantern glow, avoid making it too touristy. token=fake-token",
        discord_channel_id="dm-andrew-123",
        draft_id=draft.id,
    )

    notes = list_conversation_context_notes(connection, result.thread.id)
    assert len(notes) == 1
    assert "cinematic" in notes[0].summary
    assert "lantern glow" in notes[0].summary
    assert "fake-token" not in notes[0].summary
    text = result.to_text()
    assert f"Linked draft: #{draft.id}" in text
    assert "Next safe step: media selection" in text
    assert "No Discord or Meta network calls were made." in text
    assert "fake-token" not in text


def test_user_dm_reuses_active_thread_for_channel(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)

    first = handle_dm_intake(connection, "start a post from Kyoto", discord_channel_id="dm-andrew-123")
    second = handle_dm_intake(connection, "maybe make it cinematic", discord_channel_id="dm-andrew-123")

    threads = list_conversation_threads(connection)
    assert len(threads) == 1
    assert second.thread.id == first.thread.id
    assert "Continuing active thread" in second.to_text()


def test_user_dm_can_choose_candidate_and_create_linked_draft(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    first = handle_dm_intake(connection, "start a post about Kyoto", discord_channel_id="dm-andrew-123")
    candidate_id = first.suggested_candidates[0].id

    result = handle_dm_intake(connection, f"choose candidate #{candidate_id}", discord_channel_id="dm-andrew-123")

    assert result.thread.draft_id is not None
    draft = get_draft(connection, result.thread.draft_id)
    assert draft is not None
    assert draft.candidate_group_id == candidate_id
    assert result.suggested_candidates == []
    text = result.to_text()
    assert f"Linked draft: #{draft.id}" in text
    assert "Next safe step: media selection" in text


def test_cli_dm_intake_simulates_private_dm_without_network_calls(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "kyoto-night-market"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-lanterns.jpg"]:
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

    result = runner.invoke(
        app,
        [
            "dm",
            "intake",
            "--message",
            "start a post about Kyoto night market",
            "--discord-channel-id",
            "dm-andrew-123",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Post Relay DM intake" in result.output
    assert "Private DM mode: user-initiated" in result.output
    assert "2025 / kyoto-night-market" in result.output
    assert "No Discord or Meta network calls were made." in result.output
    assert root.as_posix() not in result.output


def test_poll_dm_intake_reply_handles_natural_andrew_dm_and_confirms_suggestions(tmp_path: Path):
    connection, root = _build_fixture_library(tmp_path)
    transport = FakeDiscordTransport(
        messages=[
            DiscordMessage(id="101", author_id="bot-123", content="older bot message"),
            DiscordMessage(
                id="102",
                author_id="andrew-123",
                content="start a post about Kyoto night market, make it cinematic",
            ),
        ]
    )

    result = poll_dm_intake_reply(
        connection,
        target_user_id="andrew-123",
        after_message_id="100",
        transport=transport,
    )

    assert result.applied is True
    assert result.channel_id == "dm-andrew-123"
    assert result.reply_message_id == "102"
    assert "Post Relay DM intake" in result.confirmation_text
    assert "2025 / kyoto-night-market" in result.confirmation_text
    assert "No Meta publishing endpoints were called." in result.confirmation_text
    assert root.as_posix() not in result.confirmation_text
    assert transport.sent_messages == [("dm-andrew-123", result.confirmation_text)]


def test_poll_dm_intake_reply_reports_when_no_user_message_is_available(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    transport = FakeDiscordTransport(
        messages=[DiscordMessage(id="101", author_id="bot-123", content="older bot message")]
    )

    result = poll_dm_intake_reply(
        connection,
        target_user_id="andrew-123",
        after_message_id="100",
        transport=transport,
    )

    assert result.applied is False
    assert result.reply_message_id is None
    assert result.confirmation_text == "No new user-initiated DM intake message found yet."
    assert transport.sent_messages == []


def test_cli_discord_dm_intake_poll_uses_live_adapter_with_fake_transport(tmp_path: Path, monkeypatch):
    _connection, root = _build_fixture_library(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    fake_transport = FakeDiscordTransport(
        messages=[
            DiscordMessage(
                id="102",
                author_id="andrew-123",
                content="start a post about Kyoto night market",
            )
        ]
    )
    monkeypatch.setattr(
        cli_module,
        "load_discord_dm_config_from_env",
        lambda: DiscordDmConfig(bot_token="fake-token", target_user_id="andrew-123"),
    )
    monkeypatch.setattr(cli_module, "DiscordRestTransport", lambda *args, **kwargs: fake_transport)

    result = runner.invoke(
        app,
        [
            "discord",
            "dm-intake-poll",
            "--after-message-id",
            "100",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Post Relay DM intake" in result.output
    assert "2025 / kyoto-night-market" in result.output
    assert "No Meta publishing endpoints were called." in result.output
    assert root.as_posix() not in result.output

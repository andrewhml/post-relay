import json
from pathlib import Path
from typing import Optional

import pytest
from typer.testing import CliRunner

import post_relay.cli as cli_module
from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.dm_guided_review import handle_dm_guided_review_reply
from post_relay.discord_dm import (
    DiscordDmConfig,
    DiscordMessage,
    poll_dm_guided_review_reply,
    send_dm_guided_review_prompt,
)
from post_relay.indexer import index_photo_sources
from post_relay.repository import (
    get_active_conversation_thread_for_channel,
    get_draft,
    get_guided_draft_package,
    list_candidate_groups,
    list_conversation_context_notes,
)


runner = CliRunner()


class FakeDiscordTransport:
    def __init__(self, *, messages: Optional[list[DiscordMessage]] = None):
        self.messages = messages or []
        self.sent_messages: list[tuple[str, str]] = []

    def create_dm_channel(self, user_id: str) -> str:
        return f"dm-{user_id}"

    def send_message(self, channel_id: str, content: str) -> str:
        self.sent_messages.append((channel_id, content))
        return f"sent-{len(self.sent_messages)}"

    def list_messages(self, channel_id: str, *, after_message_id: Optional[str] = None, limit: int = 10):
        return self.messages


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
    assert "Accepted DM guided review for post #" in text
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
    assert "Accepted DM guided review for post #1" in result.output
    assert "No Discord or Meta network calls were made." in result.output
    assert root.as_posix() not in result.output


def test_send_dm_guided_review_prompt_sends_private_dm_and_records_waiting_thread(tmp_path: Path):
    connection, draft, root = _build_fixture_draft(tmp_path)
    transport = FakeDiscordTransport()

    result = send_dm_guided_review_prompt(
        connection,
        draft.id,
        config=DiscordDmConfig(bot_token="x", target_user_id="andrew"),
        transport=transport,
        mood="cinematic",
    )

    thread = get_active_conversation_thread_for_channel(connection, "dm-andrew")

    assert result.channel_id == "dm-andrew"
    assert result.message_id == "sent-1"
    assert thread is not None
    assert thread.status == "waiting_for_user"
    assert "guided review prompt" in thread.last_prompt_summary
    sent_text = transport.sent_messages[0][1]
    assert "Post Relay guided review" in sent_text
    assert "Post #" in sent_text
    assert "Caption options:" in sent_text
    assert "Reply with" in sent_text
    assert "never publishes to Instagram" in sent_text
    assert root.as_posix() not in sent_text

    connection.close()
    reopened = connect_db(tmp_path / "post_relay.sqlite")
    persisted_thread = get_active_conversation_thread_for_channel(reopened, "dm-andrew")
    assert persisted_thread is not None
    assert persisted_thread.status == "waiting_for_user"


def test_poll_dm_guided_review_reply_requires_prompt_message_boundary(tmp_path: Path):
    connection, draft, _root = _build_fixture_draft(tmp_path)
    transport = FakeDiscordTransport(
        messages=[
            DiscordMessage(id="102", author_id="andrew", content="caption 1"),
        ]
    )

    with pytest.raises(Exception, match="after_message_id is required"):
        poll_dm_guided_review_reply(
            connection,
            draft.id,
            channel_id="dm-andrew",
            target_user_id="andrew",
            after_message_id=None,
            transport=transport,
        )

    updated = get_draft(connection, draft.id)
    assert updated.caption in (None, "")


def test_poll_dm_guided_review_reply_accepts_and_confirms_first_andrew_reply(tmp_path: Path):
    connection, draft, _root = _build_fixture_draft(tmp_path)
    transport = FakeDiscordTransport(
        messages=[
            DiscordMessage(id="101", author_id="bot", content="ignore me"),
            DiscordMessage(
                id="102",
                author_id="andrew",
                content="location: Kyoto, Japan; story: lantern alleys; mood: cinematic; hook: food and light; caption 1",
            ),
        ]
    )

    result = poll_dm_guided_review_reply(
        connection,
        draft.id,
        channel_id="dm-andrew",
        target_user_id="andrew",
        after_message_id="sent-1",
        transport=transport,
    )

    updated = get_draft(connection, draft.id)

    assert result.applied is True
    assert result.reply_message_id == "102"
    assert updated.location_text == "Kyoto, Japan"
    assert "Accepted DM guided review" in result.confirmation_text
    assert "No Meta publishing endpoints were called." in result.confirmation_text
    assert "No Discord or Meta network calls were made." not in result.confirmation_text
    assert transport.sent_messages[-1] == ("dm-andrew", result.confirmation_text)


def test_poll_dm_guided_review_reply_reports_when_no_caption_choice_yet(tmp_path: Path):
    connection, draft, _root = _build_fixture_draft(tmp_path)
    transport = FakeDiscordTransport(
        messages=[
            DiscordMessage(
                id="102",
                author_id="andrew",
                content="mood: cinematic and less touristy",
            ),
        ]
    )

    result = poll_dm_guided_review_reply(
        connection,
        draft.id,
        channel_id="dm-andrew",
        target_user_id="andrew",
        after_message_id="sent-1",
        transport=transport,
    )

    assert result.applied is False
    assert result.reply_message_id == "102"
    assert "Caption options:" in result.confirmation_text
    assert "Reply with `caption 1`" in result.confirmation_text
    assert transport.sent_messages[-1] == ("dm-andrew", result.confirmation_text)


def test_cli_dm_guided_review_send_uses_live_discord_adapter_with_fake_transport(tmp_path: Path, monkeypatch):
    connection, draft, _root = _build_fixture_draft(tmp_path)
    connection.close()
    db_path = tmp_path / "post_relay.sqlite"
    transport = FakeDiscordTransport()

    monkeypatch.setattr(
        cli_module,
        "load_discord_dm_config_from_env",
        lambda: DiscordDmConfig(bot_token="x", target_user_id="andrew"),
    )
    monkeypatch.setattr(
        cli_module,
        "DiscordRestTransport",
        lambda bot_token, api_base_url="https://discord.com/api/v10": transport,
    )

    result = runner.invoke(
        app,
        [
            "discord",
            "dm-guided-review-send",
            "--draft-id",
            str(draft.id),
            "--mood",
            "cinematic",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Discord DM guided review prompt sent" in result.output
    assert "No Meta publishing endpoints were called." in result.output
    assert "Post Relay guided review" in transport.sent_messages[0][1]


def test_cli_dm_guided_review_poll_uses_live_discord_adapter_with_fake_transport(tmp_path: Path, monkeypatch):
    connection, draft, _root = _build_fixture_draft(tmp_path)
    connection.close()
    db_path = tmp_path / "post_relay.sqlite"
    transport = FakeDiscordTransport(
        messages=[
            DiscordMessage(
                id="102",
                author_id="andrew",
                content="location: Kyoto, Japan; story: lantern alleys; mood: cinematic; hook: food and light; caption 1",
            ),
        ]
    )

    monkeypatch.setattr(
        cli_module,
        "load_discord_dm_config_from_env",
        lambda: DiscordDmConfig(bot_token="x", target_user_id="andrew"),
    )
    monkeypatch.setattr(
        cli_module,
        "DiscordRestTransport",
        lambda bot_token, api_base_url="https://discord.com/api/v10": transport,
    )

    result = runner.invoke(
        app,
        [
            "discord",
            "dm-guided-review-poll",
            "--draft-id",
            str(draft.id),
            "--channel-id",
            "dm-andrew",
            "--after-message-id",
            "sent-1",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Accepted DM guided review" in result.output
    assert "No Meta publishing endpoints were called." in result.output
    assert transport.sent_messages[-1] == ("dm-andrew", result.output.strip())

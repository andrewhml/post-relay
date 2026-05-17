from pathlib import Path
import json
from typing import Optional
from urllib import request

import pytest
from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.discord_dm import (
    DiscordDmConfig,
    DiscordDmTransport,
    DiscordRestTransport,
    DiscordSelectionParseError,
    DiscordMessage,
    handle_dm_selection_reply,
    parse_selection_reply,
    poll_dm_selection_reply,
    send_dm_selection_prompt,
)
from post_relay.indexer import index_photo_sources
from post_relay.repository import get_draft, list_candidate_groups, list_conversation_threads
from post_relay.state import DraftState


runner = CliRunner()


class FakeDiscordTransport(DiscordDmTransport):
    def __init__(self) -> None:
        self.created_for_user_ids: list[str] = []
        self.sent_messages: list[tuple[str, str]] = []
        self.messages_to_poll: list[DiscordMessage] = []
        self._next_message_id = 100

    def create_dm_channel(self, user_id: str) -> str:
        self.created_for_user_ids.append(user_id)
        return "dm-channel-123"

    def send_message(self, channel_id: str, content: str) -> str:
        self.sent_messages.append((channel_id, content))
        self._next_message_id += 1
        return str(self._next_message_id)

    def list_messages(self, channel_id: str, *, after_message_id: Optional[str] = None, limit: int = 10) -> list[DiscordMessage]:
        return self.messages_to_poll[:limit]


def _build_fixture_draft(tmp_path: Path, filenames: Optional[list[str]] = None):
    root = tmp_path / "processed"
    folder = root / "2025" / "kyoto-night-market"
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
    return connection, draft, root


def test_send_dm_selection_prompt_uses_private_dm_and_records_thread(tmp_path: Path):
    connection, draft, root = _build_fixture_draft(tmp_path)
    transport = FakeDiscordTransport()

    result = send_dm_selection_prompt(
        connection,
        draft.id,
        target_count=3,
        config=DiscordDmConfig(bot_token="test-token", target_user_id="andrew-user-1"),
        transport=transport,
    )

    assert result.channel_id == "dm-channel-123"
    assert result.message_id == "101"
    assert transport.created_for_user_ids == ["andrew-user-1"]
    assert transport.sent_messages
    sent_content = transport.sent_messages[0][1]
    assert "Post Relay photo selection" in sent_content
    assert "Select 3 of 5 suggested photos" in sent_content
    assert "Reply like: select 1,2,3 lead 1" in sent_content
    assert root.as_posix() not in sent_content
    assert "test-token" not in sent_content
    threads = list_conversation_threads(connection)
    assert len(threads) == 1
    assert threads[0].draft_id == draft.id
    assert threads[0].discord_channel_id == "dm-channel-123"
    assert threads[0].status == "waiting_for_user"


@pytest.mark.parametrize(
    "message,selected,lead",
    [
        ("select 3,1,5 lead 3", [3, 1, 5], 3),
        ("3, 1, 5 lead=3", [3, 1, 5], 3),
        ("pick 3 1 5 cover 3", [3, 1, 5], 3),
    ],
)
def test_parse_selection_reply_accepts_dm_friendly_formats(message: str, selected: list[int], lead: int):
    parsed = parse_selection_reply(message)

    assert parsed.selected_numbers == selected
    assert parsed.lead == lead


@pytest.mark.parametrize("message", ["select two photos", "select 1,2,3", "lead 1"])
def test_parse_selection_reply_rejects_incomplete_messages(message: str):
    with pytest.raises(DiscordSelectionParseError):
        parse_selection_reply(message)


def test_handle_dm_selection_reply_applies_selection_and_returns_dm_confirmation(tmp_path: Path):
    connection, draft, root = _build_fixture_draft(tmp_path)

    result = handle_dm_selection_reply(
        connection,
        draft.id,
        "select 3,1,5 lead 3",
        target_count=3,
        discord_channel_id="dm-channel-123",
    )

    assert [Path(item.local_file_path).name for item in result.selection_result.included_items] == [
        "03-hero.jpg",
        "01-wide.jpg",
        "05-night.jpg",
    ]
    assert get_draft(connection, draft.id).status == DraftState.DRAFTING.value
    text = result.to_text()
    assert "Selection applied for draft #" in text
    assert "Lead/cover: 03-hero.jpg" in text
    assert "Included order:" in text
    assert "No Meta publishing endpoints were called." in text
    assert root.as_posix() not in text


def test_poll_dm_selection_reply_applies_first_parseable_user_reply_and_sends_confirmation(tmp_path: Path):
    connection, draft, root = _build_fixture_draft(tmp_path)
    transport = FakeDiscordTransport()
    transport.messages_to_poll = [
        DiscordMessage(id="200", author_id="andrew-user-1", content="looks good but thinking"),
        DiscordMessage(id="201", author_id="andrew-user-1", content="select 3,1,5 lead 3"),
    ]

    result = poll_dm_selection_reply(
        connection,
        draft.id,
        channel_id="dm-channel-123",
        target_count=3,
        target_user_id="andrew-user-1",
        after_message_id="101",
        transport=transport,
    )

    assert result.applied is True
    assert result.reply_message_id == "201"
    assert "Selection applied for draft #" in result.confirmation_text
    assert transport.sent_messages[-1][0] == "dm-channel-123"
    assert "Lead/cover: 03-hero.jpg" in transport.sent_messages[-1][1]
    assert root.as_posix() not in transport.sent_messages[-1][1]


def test_discord_rest_transport_lists_messages_from_discord_api(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                [
                    {
                        "id": "201",
                        "content": "select 3,1,5 lead 3",
                        "author": {"id": "andrew-user-1"},
                    }
                ]
            ).encode("utf-8")

    captured_urls: list[str] = []

    def fake_urlopen(req: request.Request, timeout: int):
        captured_urls.append(req.full_url)
        return FakeResponse()

    monkeypatch.setattr(request, "urlopen", fake_urlopen)

    messages = DiscordRestTransport("secret-token", api_base_url="https://discord.test/api").list_messages(
        "dm-channel-123",
        after_message_id="101",
    )

    assert messages == [DiscordMessage(id="201", author_id="andrew-user-1", content="select 3,1,5 lead 3")]
    assert captured_urls == ["https://discord.test/api/channels/dm-channel-123/messages?limit=10&after=101"]


def test_cli_dm_selection_apply_parses_reply_without_network_calls(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "kyoto-night-market"
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

    result = runner.invoke(
        app,
        [
            "discord",
            "dm-selection-apply",
            "--draft-id",
            "1",
            "--message",
            "select 3,1,4 lead 3",
            "--target-count",
            "3",
            "--discord-channel-id",
            "dm-channel-123",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Selection applied for draft #1" in result.output
    assert "Lead/cover: 03-hero.jpg" in result.output
    assert "No Discord or Meta network calls were made." in result.output
    assert root.as_posix() not in result.output

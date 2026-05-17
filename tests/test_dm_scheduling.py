from pathlib import Path
from typing import Optional

import pytest
from typer.testing import CliRunner

import post_relay.cli as cli_module
from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.discord_dm import DiscordDmConfig, DiscordMessage
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import get_active_conversation_thread_for_channel, get_draft, list_candidate_groups
from post_relay.state import DraftState
from post_relay.dm_scheduling import (
    build_dm_publish_approval_guidance,
    build_dm_schedule_guidance,
    handle_dm_publish_approval_reply,
    handle_dm_schedule_reply,
    poll_dm_schedule_reply,
    send_dm_schedule_prompt,
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


def _build_approved_fixture_draft(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "kyoto-night-market"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-hero.jpg"]:
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
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    return connection, get_draft(connection, draft.id), root


def test_build_dm_schedule_guidance_recommends_interpretable_slots_for_approved_draft(tmp_path: Path):
    connection, draft, root = _build_approved_fixture_draft(tmp_path)

    result = build_dm_schedule_guidance(
        connection,
        draft.id,
        now="2026-05-16T20:00:00-07:00",
    )

    text = result.to_text()
    assert result.draft_id == draft.id
    assert result.recommended_slots[0] == "2026-05-19T09:30:00-07:00"
    assert len(result.recommended_slots) == 3
    assert "simple cadence rule" in result.rationale
    assert "Reply with `slot 1`" in text
    assert "No Discord or Meta network calls were made." in text
    assert root.as_posix() not in text


def test_dm_schedule_reply_slot_choice_persists_schedule_and_updates_thread(tmp_path: Path):
    connection, draft, _root = _build_approved_fixture_draft(tmp_path)

    result = handle_dm_schedule_reply(
        connection,
        draft.id,
        "slot 2 please",
        now="2026-05-16T20:00:00-07:00",
        discord_channel_id="dm-andrew",
    )

    updated = get_draft(connection, draft.id)
    thread = get_active_conversation_thread_for_channel(connection, "dm-andrew")
    assert updated.status == DraftState.SCHEDULED.value
    assert updated.scheduled_for == "2026-05-21T09:30:00-07:00"
    assert thread is not None
    assert thread.status == "active"
    assert "Scheduled draft" in thread.last_prompt_summary
    assert "No Discord or Meta network calls were made." in result.to_text()


def test_publish_approval_guidance_and_reply_record_final_local_approval(tmp_path: Path):
    connection, draft, _root = _build_approved_fixture_draft(tmp_path)
    handle_dm_schedule_reply(
        connection,
        draft.id,
        "slot 1",
        now="2026-05-16T20:00:00-07:00",
        discord_channel_id="dm-andrew",
    )

    guidance = build_dm_publish_approval_guidance(
        connection,
        draft.id,
        now="2026-05-18T12:00:00-07:00",
    )
    result = handle_dm_publish_approval_reply(
        connection,
        draft.id,
        "approve publish",
        now="2026-05-18T12:00:00-07:00",
        discord_channel_id="dm-andrew",
    )

    updated = get_draft(connection, draft.id)
    thread = get_active_conversation_thread_for_channel(connection, "dm-andrew")
    assert guidance.scheduled_for == "2026-05-19T09:30:00-07:00"
    assert "final publish approval request" in guidance.to_text()
    assert updated.status == DraftState.READY_TO_PUBLISH.value
    assert thread is not None
    assert "final publish approval" in thread.last_prompt_summary
    assert "Publish approval recorded" in result.to_text()
    assert "No Discord or Meta network calls were made." in result.to_text()


def test_send_dm_schedule_prompt_sends_private_dm_and_records_waiting_thread(tmp_path: Path):
    connection, draft, root = _build_approved_fixture_draft(tmp_path)
    transport = FakeDiscordTransport()

    result = send_dm_schedule_prompt(
        connection,
        draft.id,
        now="2026-05-16T20:00:00-07:00",
        config=DiscordDmConfig(bot_token="x", target_user_id="andrew"),
        transport=transport,
    )

    thread = get_active_conversation_thread_for_channel(connection, "dm-andrew")
    assert result.channel_id == "dm-andrew"
    assert result.message_id == "sent-1"
    assert thread is not None
    assert thread.status == "waiting_for_user"
    assert "schedule prompt" in thread.last_prompt_summary
    sent_text = transport.sent_messages[0][1]
    assert "Post Relay schedule guidance" in sent_text
    assert "Reply with `slot 1`" in sent_text
    assert "never publishes to Instagram" in sent_text
    assert root.as_posix() not in sent_text


def test_poll_dm_schedule_reply_schedules_first_andrew_reply_and_confirms(tmp_path: Path):
    connection, draft, _root = _build_approved_fixture_draft(tmp_path)
    transport = FakeDiscordTransport(
        messages=[
            DiscordMessage(id="101", author_id="bot", content="ignore"),
            DiscordMessage(id="102", author_id="andrew", content="slot 1"),
        ]
    )

    result = poll_dm_schedule_reply(
        connection,
        draft.id,
        channel_id="dm-andrew",
        target_user_id="andrew",
        after_message_id="sent-1",
        now="2026-05-16T20:00:00-07:00",
        transport=transport,
    )

    assert result.applied is True
    assert result.reply_message_id == "102"
    assert get_draft(connection, draft.id).scheduled_for == "2026-05-19T09:30:00-07:00"
    assert "Scheduled draft" in result.confirmation_text
    assert "No Meta publishing endpoints were called." in result.confirmation_text
    assert "No Discord or Meta network calls were made." not in result.confirmation_text
    assert transport.sent_messages[-1] == ("dm-andrew", result.confirmation_text)


def test_cli_dm_schedule_apply_accepts_reply_without_network_calls(tmp_path: Path):
    connection, draft, _root = _build_approved_fixture_draft(tmp_path)
    connection.close()
    db_path = tmp_path / "post_relay.sqlite"

    result = runner.invoke(
        app,
        [
            "discord",
            "dm-schedule-apply",
            "--draft-id",
            str(draft.id),
            "--message",
            "slot 1",
            "--now",
            "2026-05-16T20:00:00-07:00",
            "--discord-channel-id",
            "dm-andrew",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Scheduled draft #" in result.output
    assert "No Discord or Meta network calls were made." in result.output


def test_cli_dm_publish_approval_apply_records_final_approval_without_network_calls(tmp_path: Path):
    connection, draft, _root = _build_approved_fixture_draft(tmp_path)
    handle_dm_schedule_reply(
        connection,
        draft.id,
        "slot 1",
        now="2026-05-16T20:00:00-07:00",
        discord_channel_id="dm-andrew",
    )
    connection.close()
    db_path = tmp_path / "post_relay.sqlite"

    result = runner.invoke(
        app,
        [
            "discord",
            "dm-publish-approval-apply",
            "--draft-id",
            str(draft.id),
            "--message",
            "approve publish",
            "--now",
            "2026-05-18T12:00:00-07:00",
            "--discord-channel-id",
            "dm-andrew",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Publish approval recorded for draft #" in result.output
    assert "No Discord or Meta network calls were made." in result.output


def test_cli_dm_schedule_send_uses_live_discord_adapter_with_fake_transport(tmp_path: Path, monkeypatch):
    connection, draft, _root = _build_approved_fixture_draft(tmp_path)
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
            "dm-schedule-send",
            "--draft-id",
            str(draft.id),
            "--now",
            "2026-05-16T20:00:00-07:00",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Discord DM schedule prompt sent" in result.output
    assert "No Meta publishing endpoints were called." in result.output
    assert "Post Relay schedule guidance" in transport.sent_messages[0][1]


def test_cli_dm_schedule_poll_uses_live_discord_adapter_with_fake_transport(tmp_path: Path, monkeypatch):
    connection, draft, _root = _build_approved_fixture_draft(tmp_path)
    connection.close()
    db_path = tmp_path / "post_relay.sqlite"
    transport = FakeDiscordTransport(messages=[DiscordMessage(id="102", author_id="andrew", content="slot 1")])

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
            "dm-schedule-poll",
            "--draft-id",
            str(draft.id),
            "--channel-id",
            "dm-andrew",
            "--after-message-id",
            "sent-1",
            "--now",
            "2026-05-16T20:00:00-07:00",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Scheduled draft" in result.output
    assert "No Meta publishing endpoints were called." in result.output
    assert transport.sent_messages[-1] == ("dm-andrew", result.output.strip())

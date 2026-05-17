from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Optional, Protocol
from urllib import error, request

from post_relay.discord_selection import (
    InvalidDiscordSelection,
    apply_discord_photo_selection,
    build_discord_selection_request,
)
from post_relay.media_selection import DraftMediaSelectionResult, DraftNotFound
from post_relay.repository import (
    ConversationThreadRecord,
    create_conversation_thread,
    get_active_conversation_thread_for_channel,
    update_conversation_thread,
)


class DiscordDmError(ValueError):
    pass


class DiscordSelectionParseError(ValueError):
    pass


@dataclass(frozen=True)
class DiscordDmConfig:
    bot_token: str
    target_user_id: str
    api_base_url: str = "https://discord.com/api/v10"


@dataclass(frozen=True)
class DmSelectionPromptResult:
    draft_id: int
    channel_id: str
    message_id: str
    thread: ConversationThreadRecord

    def to_text(self) -> str:
        return "\n".join(
            [
                "Discord DM selection prompt sent",
                f"Draft ID: {self.draft_id}",
                f"DM channel: {self.channel_id}",
                f"Discord message: {self.message_id}",
                f"Conversation thread: #{self.thread.id} ({self.thread.status})",
                "No Meta publishing endpoints were called.",
            ]
        )


@dataclass(frozen=True)
class ParsedSelectionReply:
    selected_numbers: list[int]
    lead: int


@dataclass(frozen=True)
class DiscordMessage:
    id: str
    author_id: str
    content: str


@dataclass(frozen=True)
class DmSelectionPollResult:
    applied: bool
    reply_message_id: Optional[str]
    confirmation_text: str


@dataclass(frozen=True)
class DmSelectionReplyResult:
    draft_id: int
    selection_result: DraftMediaSelectionResult
    discord_channel_id: Optional[str]

    def to_text(self) -> str:
        included_names = [_display_name(item.local_file_path) for item in self.selection_result.included_items]
        excluded_names = [_display_name(item.local_file_path) for item in self.selection_result.excluded_items]
        lead_name = included_names[0] if included_names else "<none>"
        lines = [
            f"Selection applied for draft #{self.draft_id}",
            f"Lead/cover: {lead_name}",
            "Included order:",
        ]
        lines.extend(f"  {index}. {name}" for index, name in enumerate(included_names, start=1))
        if excluded_names:
            lines.append("Excluded:")
            lines.extend(f"  - {name}" for name in excluded_names)
        lines.extend(
            [
                f"Approvals invalidated: {self.selection_result.invalidated_approval_count}",
                "No Discord or Meta network calls were made.",
                "No Meta publishing endpoints were called.",
            ]
        )
        return "\n".join(lines)


class DiscordDmTransport(Protocol):
    def create_dm_channel(self, user_id: str) -> str:
        ...

    def send_message(self, channel_id: str, content: str) -> str:
        ...

    def list_messages(
        self, channel_id: str, *, after_message_id: Optional[str] = None, limit: int = 10
    ) -> list[DiscordMessage]:
        ...


class DiscordRestTransport:
    def __init__(self, bot_token: str, *, api_base_url: str = "https://discord.com/api/v10") -> None:
        self.bot_token = bot_token
        self.api_base_url = api_base_url.rstrip("/")

    def create_dm_channel(self, user_id: str) -> str:
        payload = self._request_json(
            "POST",
            "/users/@me/channels",
            {"recipient_id": user_id},
        )
        if not isinstance(payload, dict):
            raise DiscordDmError("Discord did not return a DM channel object")
        channel_id = payload.get("id")
        if not channel_id:
            raise DiscordDmError("Discord did not return a DM channel id")
        return str(channel_id)

    def send_message(self, channel_id: str, content: str) -> str:
        payload = self._request_json(
            "POST",
            f"/channels/{channel_id}/messages",
            {"content": content},
        )
        if not isinstance(payload, dict):
            raise DiscordDmError("Discord did not return a message object")
        message_id = payload.get("id")
        if not message_id:
            raise DiscordDmError("Discord did not return a message id")
        return str(message_id)

    def list_messages(
        self, channel_id: str, *, after_message_id: Optional[str] = None, limit: int = 10
    ) -> list[DiscordMessage]:
        query = f"?limit={limit}"
        if after_message_id:
            query += f"&after={after_message_id}"
        payload = self._request_json("GET", f"/channels/{channel_id}/messages{query}", None)
        if not isinstance(payload, list):
            raise DiscordDmError("Discord did not return a message list")
        messages: list[DiscordMessage] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            author = item.get("author") if isinstance(item.get("author"), dict) else {}
            messages.append(
                DiscordMessage(
                    id=str(item.get("id", "")),
                    author_id=str(author.get("id", "")),
                    content=str(item.get("content", "")),
                )
            )
        return messages

    def _request_json(self, method: str, path: str, payload: Optional[object]) -> object:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(
            f"{self.api_base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bot {self.bot_token}",
                "Content-Type": "application/json",
                "User-Agent": "post-relay/0.1",
            },
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DiscordDmError(f"Discord API request failed with HTTP {exc.code}: {_redact(detail)}") from exc
        except error.URLError as exc:
            raise DiscordDmError(f"Discord API request failed: {_redact(str(exc))}") from exc
        parsed = json.loads(raw)
        if not isinstance(parsed, (dict, list)):
            raise DiscordDmError("Discord API returned an unexpected response")
        return parsed


def load_discord_dm_config_from_env() -> DiscordDmConfig:
    bot_token = os.environ.get("POST_RELAY_DISCORD_BOT_TOKEN")
    target_user_id = os.environ.get("POST_RELAY_DISCORD_TARGET_USER_ID")
    if not bot_token:
        raise DiscordDmError("POST_RELAY_DISCORD_BOT_TOKEN is required for live Discord DM sends")
    if not target_user_id:
        raise DiscordDmError("POST_RELAY_DISCORD_TARGET_USER_ID is required for live Discord DM sends")
    return DiscordDmConfig(bot_token=bot_token, target_user_id=target_user_id)


def send_dm_selection_prompt(
    connection,
    draft_id: int,
    *,
    target_count: int,
    config: DiscordDmConfig,
    transport: Optional[DiscordDmTransport] = None,
    post_type: Optional[str] = None,
) -> DmSelectionPromptResult:
    selection_request = build_discord_selection_request(
        connection,
        draft_id,
        target_count=target_count,
        post_type=post_type,
    )
    selected_transport = transport or DiscordRestTransport(
        config.bot_token,
        api_base_url=config.api_base_url,
    )
    channel_id = selected_transport.create_dm_channel(config.target_user_id)
    content = _dm_selection_prompt_text(selection_request)
    message_id = selected_transport.send_message(channel_id, content)
    thread = get_active_conversation_thread_for_channel(connection, channel_id)
    summary = f"Sent private DM selection prompt for draft #{draft_id}; select {target_count} of {selection_request.suggested_count}."
    if thread is None:
        thread = create_conversation_thread(
            connection,
            draft_id=draft_id,
            discord_channel_id=channel_id,
            status="waiting_for_user",
            last_prompt_summary=summary,
        )
    else:
        thread = update_conversation_thread(
            connection,
            thread.id,
            draft_id=draft_id,
            status="waiting_for_user",
            last_prompt_summary=summary,
        )
    return DmSelectionPromptResult(
        draft_id=draft_id,
        channel_id=channel_id,
        message_id=message_id,
        thread=thread,
    )


def handle_dm_selection_reply(
    connection,
    draft_id: int,
    message: str,
    *,
    target_count: int,
    discord_channel_id: Optional[str] = None,
    post_type: Optional[str] = None,
) -> DmSelectionReplyResult:
    parsed = parse_selection_reply(message)
    try:
        result = apply_discord_photo_selection(
            connection,
            draft_id,
            selected_numbers=parsed.selected_numbers,
            lead=parsed.lead,
            target_count=target_count,
            post_type=post_type,
        )
    except (DraftNotFound, InvalidDiscordSelection) as error:
        raise DiscordDmError(str(error)) from error
    if discord_channel_id:
        thread = get_active_conversation_thread_for_channel(connection, discord_channel_id)
        if thread is not None:
            update_conversation_thread(
                connection,
                thread.id,
                draft_id=draft_id,
                status="active",
                last_prompt_summary=f"Applied private DM selection for draft #{draft_id}.",
            )
    return DmSelectionReplyResult(
        draft_id=draft_id,
        selection_result=result,
        discord_channel_id=discord_channel_id,
    )


def poll_dm_selection_reply(
    connection,
    draft_id: int,
    *,
    channel_id: str,
    target_count: int,
    target_user_id: str,
    after_message_id: Optional[str],
    transport: DiscordDmTransport,
    post_type: Optional[str] = None,
) -> DmSelectionPollResult:
    messages = transport.list_messages(channel_id, after_message_id=after_message_id, limit=20)
    for message in sorted(messages, key=lambda item: int(item.id) if item.id.isdigit() else 0):
        if message.author_id != target_user_id:
            continue
        try:
            parse_selection_reply(message.content)
        except DiscordSelectionParseError:
            continue
        result = handle_dm_selection_reply(
            connection,
            draft_id,
            message.content,
            target_count=target_count,
            discord_channel_id=channel_id,
            post_type=post_type,
        )
        confirmation = result.to_text()
        transport.send_message(channel_id, confirmation)
        return DmSelectionPollResult(
            applied=True,
            reply_message_id=message.id,
            confirmation_text=confirmation,
        )
    return DmSelectionPollResult(
        applied=False,
        reply_message_id=None,
        confirmation_text="No parseable selection reply found yet.",
    )


def parse_selection_reply(message: str) -> ParsedSelectionReply:
    numbers = [int(value) for value in re.findall(r"\d+", message)]
    lead_match = re.search(r"(?i)(?:lead|cover)\s*=?\s*(\d+)", message)
    if not numbers or lead_match is None:
        raise DiscordSelectionParseError("Reply must include selected photo numbers and a lead/cover number")
    lead = int(lead_match.group(1))
    selected_numbers = numbers[:-1] if numbers[-1] == lead else [number for number in numbers if number != lead]
    if not selected_numbers:
        raise DiscordSelectionParseError("Reply must include at least one selected photo number")
    return ParsedSelectionReply(selected_numbers=selected_numbers, lead=lead)


def _dm_selection_prompt_text(selection_request) -> str:
    lines = [
        "Post Relay photo selection",
        f"Draft #{selection_request.draft_id} · {selection_request.post_type}",
        f"Select {selection_request.target_count} of {selection_request.suggested_count} suggested photos.",
        "Suggested media:",
    ]
    for item in selection_request.items:
        lines.append(f"  {item.review_number}. {_display_name(item.local_file_path)}")
    example_numbers = [item.review_number for item in selection_request.items[: selection_request.target_count]]
    example_select = ",".join(str(number) for number in example_numbers) or "<numbers>"
    example_lead = str(example_numbers[0]) if example_numbers else "<lead>"
    lines.extend(
        [
            "Lead/cover: choose the strongest opener.",
            f"Reply like: select {example_select} lead {example_lead}",
            "This DM step only updates local selection state after your reply; it never publishes to Instagram.",
        ]
    )
    return "\n".join(lines)


def _display_name(path: str) -> str:
    return Path(path).name


def _redact(value: str) -> str:
    return re.sub(r"(?i)(token|authorization|secret|password)[^,}\n]*", r"\1=[redacted]", value)

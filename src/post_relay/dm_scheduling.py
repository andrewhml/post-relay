from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import re
from typing import Optional

from post_relay.discord_dm import DiscordDmConfig, DiscordDmError, DiscordDmTransport, DiscordRestTransport
from post_relay.repository import (
    ConversationThreadRecord,
    create_conversation_thread,
    get_active_conversation_thread_for_channel,
    get_draft,
    list_drafts,
    update_conversation_thread,
)
from post_relay.scheduling import (
    DraftNotFound,
    DraftNotReadyForPublishApproval,
    DraftNotReadyForScheduling,
    approve_draft_for_publishing,
    request_publish_approval,
    schedule_draft,
)
from post_relay.state import DraftState


class DmSchedulingError(ValueError):
    pass


@dataclass(frozen=True)
class DmScheduleGuidanceResult:
    draft_id: int
    recommended_slots: list[str]
    rationale: str

    def to_text(self, *, no_network: bool = True) -> str:
        lines = [
            "Post Relay schedule guidance",
            f"Draft #{self.draft_id}",
            "Recommended slots:",
        ]
        lines.extend(f"  {index}. {slot}" for index, slot in enumerate(self.recommended_slots, start=1))
        lines.extend(
            [
                f"Why: {self.rationale}",
                "Reply with `slot 1`, `slot 2`, `slot 3`, or paste an ISO time like `2026-05-19T09:30:00-07:00`.",
                "After scheduling, Post Relay can request final publish approval near the publish window; it still will not publish without explicit approval.",
            ]
        )
        if no_network:
            lines.append("No Discord or Meta network calls were made.")
        lines.append("No Meta publishing endpoints were called.")
        return "\n".join(lines)


@dataclass(frozen=True)
class DmScheduleReplyResult:
    draft_id: int
    scheduled_for: str
    thread: Optional[ConversationThreadRecord]

    def to_text(self, *, no_network: bool = True) -> str:
        lines = [
            f"Scheduled draft #{self.draft_id}",
            f"Scheduled for: {self.scheduled_for}",
            "Next safe step: request final publish approval near the scheduled window, then run guarded publish validation only after explicit approval.",
        ]
        if no_network:
            lines.append("No Discord or Meta network calls were made.")
        lines.append("No Meta publishing endpoints were called.")
        return "\n".join(lines)


@dataclass(frozen=True)
class DmPublishApprovalGuidanceResult:
    draft_id: int
    scheduled_for: str
    hours_until_publish: float

    def to_text(self, *, no_network: bool = True) -> str:
        lines = [
            "Post Relay final publish approval request",
            f"Draft #{self.draft_id}",
            f"Scheduled for: {self.scheduled_for}",
            "Reply with `approve publish` only if the final caption, media order, and schedule are approved.",
            "This only records local publish approval; it does not publish to Instagram.",
        ]
        if no_network:
            lines.append("No Discord or Meta network calls were made.")
        lines.append("No Meta publishing endpoints were called.")
        return "\n".join(lines)


@dataclass(frozen=True)
class DmPublishApprovalReplyResult:
    draft_id: int
    approved: bool
    status: str
    thread: Optional[ConversationThreadRecord]

    def to_text(self, *, no_network: bool = True) -> str:
        lines = [
            f"Publish approval recorded for draft #{self.draft_id}",
            f"Draft status: {self.status}",
            "Next safe step: run guarded dry-run publish validation before any explicit live `--execute` publish.",
        ]
        if no_network:
            lines.append("No Discord or Meta network calls were made.")
        lines.append("No Meta publishing endpoints were called.")
        return "\n".join(lines)


@dataclass(frozen=True)
class DmSchedulePromptResult:
    draft_id: int
    channel_id: str
    message_id: str
    thread: ConversationThreadRecord

    def to_text(self) -> str:
        return "\n".join(
            [
                "Discord DM schedule prompt sent",
                f"Draft ID: {self.draft_id}",
                f"DM channel: {self.channel_id}",
                f"Discord message: {self.message_id}",
                f"Conversation thread: #{self.thread.id} ({self.thread.status})",
                "No Meta publishing endpoints were called.",
            ]
        )


@dataclass(frozen=True)
class DmSchedulePollResult:
    applied: bool
    reply_message_id: Optional[str]
    confirmation_text: str


def build_dm_schedule_guidance(
    connection,
    draft_id: int,
    *,
    now: Optional[str] = None,
) -> DmScheduleGuidanceResult:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DmSchedulingError(f"Draft #{draft_id} was not found")
    if draft.status != DraftState.APPROVED_FOR_QUEUE.value:
        raise DmSchedulingError(
            f"Draft #{draft_id} must be approved_for_queue before schedule guidance; current status is {draft.status}"
        )
    slots = _recommended_slots(connection, now=_parse_now(now))
    rationale = (
        "Uses a simple cadence rule: Tue/Thu/Sun morning slots, skipping already scheduled days, "
        "so travel posts do not cluster or dump the backlog at once."
    )
    return DmScheduleGuidanceResult(draft_id=draft_id, recommended_slots=slots, rationale=rationale)


def handle_dm_schedule_reply(
    connection,
    draft_id: int,
    message: str,
    *,
    now: Optional[str] = None,
    discord_channel_id: Optional[str] = None,
) -> DmScheduleReplyResult:
    guidance = build_dm_schedule_guidance(connection, draft_id, now=now)
    scheduled_for = _parse_schedule_choice(message, guidance.recommended_slots)
    try:
        scheduled = schedule_draft(connection, draft_id, scheduled_for=scheduled_for)
    except (DraftNotFound, DraftNotReadyForScheduling) as error:
        raise DmSchedulingError(str(error)) from error

    thread: Optional[ConversationThreadRecord] = None
    if discord_channel_id:
        thread = get_active_conversation_thread_for_channel(connection, discord_channel_id)
        summary = f"Scheduled draft #{draft_id} for {scheduled.scheduled_for}."
        if thread is None:
            thread = create_conversation_thread(
                connection,
                draft_id=draft_id,
                discord_channel_id=discord_channel_id,
                status="active",
                last_prompt_summary=summary,
            )
        else:
            thread = update_conversation_thread(
                connection,
                thread.id,
                draft_id=draft_id,
                status="active",
                last_prompt_summary=summary,
            )
    connection.commit()
    return DmScheduleReplyResult(
        draft_id=draft_id,
        scheduled_for=scheduled.scheduled_for or scheduled_for,
        thread=thread,
    )


def build_dm_publish_approval_guidance(
    connection,
    draft_id: int,
    *,
    now: Optional[str] = None,
    approval_window_hours: int = 24,
) -> DmPublishApprovalGuidanceResult:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DmSchedulingError(f"Draft #{draft_id} was not found")
    if draft.status != DraftState.SCHEDULED.value or not draft.scheduled_for:
        raise DmSchedulingError(
            f"Draft #{draft_id} must be scheduled before final publish approval can be requested; current status is {draft.status}"
        )
    current_time = _parse_now(now)
    scheduled_time = _parse_datetime(draft.scheduled_for)
    hours_until = (scheduled_time - current_time).total_seconds() / 3600
    if hours_until > approval_window_hours:
        raise DmSchedulingError(
            f"Draft #{draft_id} is scheduled outside the {approval_window_hours}-hour final approval window"
        )
    return DmPublishApprovalGuidanceResult(
        draft_id=draft_id,
        scheduled_for=draft.scheduled_for,
        hours_until_publish=hours_until,
    )


def handle_dm_publish_approval_reply(
    connection,
    draft_id: int,
    message: str,
    *,
    now: Optional[str] = None,
    discord_channel_id: Optional[str] = None,
    approved_by: str = "andrew",
) -> DmPublishApprovalReplyResult:
    build_dm_publish_approval_guidance(connection, draft_id, now=now)
    if not re.search(r"(?i)\bapprove\s+publish\b", message):
        raise DmSchedulingError("Reply must include `approve publish` to record final publish approval")
    try:
        request_publish_approval(connection, draft_id)
        approval = approve_draft_for_publishing(
            connection,
            draft_id,
            approved_by=approved_by,
            source_message_ref=discord_channel_id,
            notes="Final publish approval from private DM.",
        )
    except (DraftNotFound, DraftNotReadyForPublishApproval) as error:
        raise DmSchedulingError(str(error)) from error
    thread: Optional[ConversationThreadRecord] = None
    if discord_channel_id:
        thread = get_active_conversation_thread_for_channel(connection, discord_channel_id)
        summary = f"Recorded final publish approval for draft #{draft_id}."
        if thread is None:
            thread = create_conversation_thread(
                connection,
                draft_id=draft_id,
                discord_channel_id=discord_channel_id,
                status="active",
                last_prompt_summary=summary,
            )
        else:
            thread = update_conversation_thread(
                connection,
                thread.id,
                draft_id=draft_id,
                status="active",
                last_prompt_summary=summary,
            )
    connection.commit()
    return DmPublishApprovalReplyResult(
        draft_id=draft_id,
        approved=True,
        status=DraftState.READY_TO_PUBLISH.value,
        thread=thread,
    )


def send_dm_schedule_prompt(
    connection,
    draft_id: int,
    *,
    config: DiscordDmConfig,
    transport: Optional[DiscordDmTransport] = None,
    now: Optional[str] = None,
) -> DmSchedulePromptResult:
    guidance = build_dm_schedule_guidance(connection, draft_id, now=now)
    selected_transport = transport or DiscordRestTransport(
        config.bot_token,
        api_base_url=config.api_base_url,
    )
    channel_id = selected_transport.create_dm_channel(config.target_user_id)
    content = _dm_schedule_prompt_text(guidance)
    message_id = selected_transport.send_message(channel_id, content)
    thread = get_active_conversation_thread_for_channel(connection, channel_id)
    summary = f"Sent private DM schedule prompt for draft #{draft_id}."
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
    connection.commit()
    return DmSchedulePromptResult(
        draft_id=draft_id,
        channel_id=channel_id,
        message_id=message_id,
        thread=thread,
    )


def poll_dm_schedule_reply(
    connection,
    draft_id: int,
    *,
    channel_id: str,
    target_user_id: str,
    after_message_id: Optional[str],
    transport: DiscordDmTransport,
    now: Optional[str] = None,
) -> DmSchedulePollResult:
    if not after_message_id:
        raise DmSchedulingError("after_message_id is required for schedule polling")
    messages = transport.list_messages(channel_id, after_message_id=after_message_id, limit=20)
    for message in sorted(messages, key=lambda item: int(item.id) if item.id.isdigit() else 0):
        if message.author_id != target_user_id:
            continue
        try:
            result = handle_dm_schedule_reply(
                connection,
                draft_id,
                message.content,
                now=now,
                discord_channel_id=channel_id,
            )
        except DmSchedulingError as error:
            confirmation = _schedule_feedback_text(str(error))
            transport.send_message(channel_id, confirmation)
            return DmSchedulePollResult(
                applied=False,
                reply_message_id=message.id,
                confirmation_text=confirmation,
            )
        confirmation = result.to_text(no_network=False)
        transport.send_message(channel_id, confirmation)
        return DmSchedulePollResult(
            applied=True,
            reply_message_id=message.id,
            confirmation_text=confirmation,
        )
    return DmSchedulePollResult(
        applied=False,
        reply_message_id=None,
        confirmation_text="No schedule reply found yet.",
    )


def _recommended_slots(connection, *, now: datetime) -> list[str]:
    scheduled_dates = {
        _parse_datetime(draft.scheduled_for).date()
        for draft in list_drafts(connection)
        if draft.scheduled_for
    }
    target_weekdays = [1, 3, 6]  # Tue, Thu, Sun
    slots: list[str] = []
    cursor_date = now.date()
    earliest = now + timedelta(hours=36)
    while len(slots) < 3:
        candidate_dt = datetime.combine(cursor_date, time(9, 30), tzinfo=now.tzinfo)
        if (
            candidate_dt >= earliest
            and candidate_dt.weekday() in target_weekdays
            and candidate_dt.date() not in scheduled_dates
        ):
            slots.append(candidate_dt.isoformat())
        cursor_date += timedelta(days=1)
    return slots


def _parse_schedule_choice(message: str, slots: list[str]) -> str:
    slot_match = re.search(r"(?i)\bslot\s*(\d+)\b", message)
    if slot_match:
        index = int(slot_match.group(1))
        if 1 <= index <= len(slots):
            return slots[index - 1]
        raise DmSchedulingError(f"slot {index} is not available; choose 1-{len(slots)}")
    iso_match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?", message)
    if iso_match:
        return _normalize_iso(_parse_datetime(iso_match.group(0)))
    raise DmSchedulingError("Reply must include `slot 1`, `slot 2`, `slot 3`, or an ISO scheduled time")


def _dm_schedule_prompt_text(guidance: DmScheduleGuidanceResult) -> str:
    return guidance.to_text(no_network=False) + "\nThis DM step only schedules the local draft after your reply; it never publishes to Instagram."


def _schedule_feedback_text(detail: str) -> str:
    return "\n".join(
        [
            f"I couldn't apply that schedule reply: {detail}.",
            "Please reply with `slot 1`, `slot 2`, `slot 3`, or an ISO time like `2026-05-19T09:30:00-07:00`.",
            "No Meta publishing endpoints were called.",
        ]
    )


def _parse_now(value: Optional[str]) -> datetime:
    if value:
        return _parse_datetime(value)
    return datetime.now().astimezone()


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()

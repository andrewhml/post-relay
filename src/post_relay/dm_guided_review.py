from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from post_relay.guided_draft import (
    AcceptedGuidedDraftPackage,
    DraftNotFound,
    GuidedDraftPackage,
    InvalidGuidedDraftPackage,
    accept_guided_draft_package,
    build_guided_draft_package,
)
from post_relay.repository import (
    ConversationContextNoteRecord,
    ConversationThreadRecord,
    create_conversation_context_note,
    create_conversation_thread,
    get_active_conversation_thread_for_channel,
    get_draft,
    update_conversation_thread,
)


class DmGuidedReviewError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedGuidedReviewReply:
    location_text: Optional[str]
    story_angle: Optional[str]
    mood: Optional[str]
    audience_hook: Optional[str]
    include: Optional[str]
    avoid: Optional[str]
    caption_index: Optional[int]


@dataclass(frozen=True)
class DmGuidedReviewResult:
    draft_id: int
    package: GuidedDraftPackage
    accepted_package: Optional[AcceptedGuidedDraftPackage]
    caption_index: Optional[int]
    thread: Optional[ConversationThreadRecord]
    context_note: Optional[ConversationContextNoteRecord]

    def to_text(self, *, no_network: bool = True) -> str:
        lines = [
            (
                f"Accepted DM guided review for post #{self.draft_id}"
                if self.accepted_package is not None
                else f"DM guided review package for post #{self.draft_id}"
            ),
            f"Post type recommendation: {self.package.post_type_recommendation}",
            f"Rationale: {self.package.post_type_rationale}",
        ]
        if self.caption_index is not None:
            lines.append(f"Caption option: {self.caption_index}")
        if self.accepted_package is not None:
            lines.extend(
                [
                    f"Caption: {self.accepted_package.caption}",
                    "Hashtags: " + " ".join(self.accepted_package.hashtags),
                    f"Location: {self.accepted_package.location_text or '<unconfirmed>'}",
                    f"Alt text: {self.accepted_package.alt_text}",
                ]
            )
        else:
            lines.append("Caption options:")
            lines.extend(
                f"  {index}. {caption}"
                for index, caption in enumerate(self.package.caption_options, start=1)
            )
            lines.append("Questions for Andrew:")
            if self.package.context_questions:
                lines.extend(f"  - {question}" for question in self.package.context_questions)
            else:
                lines.append("  - <none>")
            lines.append("Reply with `caption 1`, `caption 2`, or `caption 3` plus any corrections.")
        lines.extend(
            [
                "Publishable through Meta v1: media, caption text, hashtags in caption.",
                "Review-only/local: alt text, growth rationale, unvalidated location ideas, collaborators, music, reels/story metadata.",
            ]
        )
        if no_network:
            lines.append("No Discord or Meta network calls were made.")
        else:
            lines.append("No Meta publishing endpoints were called.")
        return "\n".join(lines)


def handle_dm_guided_review_reply(
    connection,
    draft_id: int,
    message: str,
    *,
    discord_channel_id: Optional[str] = None,
) -> DmGuidedReviewResult:
    sanitized_message = _sanitize_text(message)
    if not sanitized_message:
        raise DmGuidedReviewError("DM guided review message must not be empty")
    if get_draft(connection, draft_id) is None:
        raise DmGuidedReviewError(f"Post #{draft_id} was not found")

    parsed = parse_guided_review_reply(sanitized_message)
    package = build_guided_draft_package(
        connection,
        draft_id,
        location_text=parsed.location_text,
        story_angle=parsed.story_angle,
        mood=parsed.mood,
        audience_hook=parsed.audience_hook,
        include=parsed.include,
        avoid=parsed.avoid,
    )
    accepted = None
    if parsed.caption_index is not None:
        try:
            accepted = accept_guided_draft_package(
                connection,
                package,
                caption_index=parsed.caption_index,
            )
        except (DraftNotFound, InvalidGuidedDraftPackage) as error:
            raise DmGuidedReviewError(str(error)) from error

    thread = None
    context_note = None
    if discord_channel_id is not None:
        thread = _upsert_thread(
            connection,
            draft_id=draft_id,
            discord_channel_id=discord_channel_id,
            accepted=accepted is not None,
        )
        context_note = create_conversation_context_note(
            connection,
            thread_id=thread.id,
            draft_id=draft_id,
            summary=_truncate(sanitized_message, 220),
        )
        connection.commit()
    return DmGuidedReviewResult(
        draft_id=draft_id,
        package=package,
        accepted_package=accepted,
        caption_index=parsed.caption_index,
        thread=thread,
        context_note=context_note,
    )


def parse_guided_review_reply(message: str) -> ParsedGuidedReviewReply:
    return ParsedGuidedReviewReply(
        location_text=_field(message, "location", "place"),
        story_angle=_field(message, "story", "story angle", "angle"),
        mood=_field(message, "mood", "tone"),
        audience_hook=_field(message, "hook", "audience hook"),
        include=_field(message, "include"),
        avoid=_field(message, "avoid"),
        caption_index=_caption_index(message),
    )


def _upsert_thread(
    connection,
    *,
    draft_id: int,
    discord_channel_id: str,
    accepted: bool,
) -> ConversationThreadRecord:
    status = "active"
    summary = (
        f"Accepted guided review package for post #{draft_id}."
        if accepted
        else f"Generated guided review package for post #{draft_id}."
    )
    thread = get_active_conversation_thread_for_channel(connection, discord_channel_id)
    if thread is None:
        return create_conversation_thread(
            connection,
            draft_id=draft_id,
            discord_channel_id=discord_channel_id,
            status=status,
            last_prompt_summary=summary,
        )
    updated = update_conversation_thread(
        connection,
        thread.id,
        draft_id=draft_id,
        status=status,
        last_prompt_summary=summary,
    )
    return updated or thread


def _field(message: str, *names: str) -> Optional[str]:
    for name in names:
        pattern = rf"(?i)(?:^|[;\n])\s*{re.escape(name)}\s*:\s*([^;\n]+)"
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()
    return None


def _caption_index(message: str) -> Optional[int]:
    match = re.search(r"(?i)\bcaption(?:\s+option)?\s*#?\s*(\d+)\b", message)
    if match:
        return int(match.group(1))
    return None


def _sanitize_text(value: str) -> str:
    sanitized = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password|key)\s*[:=]\s*[^;\s]+",
        lambda match: f"{match.group(1)}: [redacted]",
        value,
    )
    sanitized = re.sub(r"https?://\S+", "[redacted-url]", sanitized)
    sanitized = re.sub(r"(?:/Users|/Volumes)/[^;\s]+", "[redacted-path]", sanitized)
    lines = [" ".join(line.split()).strip() for line in sanitized.replace("\r\n", "\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"

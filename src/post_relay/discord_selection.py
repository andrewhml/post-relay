from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from post_relay.media_selection import (
    DraftMediaPlanItem,
    DraftMediaSelectionResult,
    DraftNotFound,
    InvalidMediaSelection,
    apply_draft_media_selection,
    build_draft_media_plan,
)


class InvalidDiscordSelection(ValueError):
    pass


@dataclass(frozen=True)
class DiscordSelectionRequest:
    draft_id: int
    post_type: str
    target_count: int
    suggested_count: int
    items: list[DraftMediaPlanItem]

    def to_text(self) -> str:
        lines = [
            "Discord Photo Selection Request",
            f"Post ID: {self.draft_id}",
            f"Post type: {self.post_type}",
            f"Select {self.target_count} of {self.suggested_count} suggested photos.",
            "Lead/cover: choose the strongest attention-grabbing opener.",
            "Suggested media:",
        ]
        if not self.items:
            lines.append("  <none>")
        else:
            lines.extend(
                f"  {item.review_number}. {_display_name(item.local_file_path)} — {item.local_file_path}"
                for item in self.items
            )
        example_numbers = [item.review_number for item in self.items[: self.target_count]]
        example_select = ",".join(str(number) for number in example_numbers) or "<numbers>"
        example_lead = str(example_numbers[0]) if example_numbers else "<lead>"
        lines.extend(
            [
                "Apply example:",
                "  drafts discord-selection-apply --draft-id "
                f"{self.draft_id} --select {example_select} --lead {example_lead} "
                f"--target-count {self.target_count} --post-type {self.post_type}",
            ]
        )
        return "\n".join(lines)


def build_discord_selection_request(
    connection,
    draft_id: int,
    *,
    target_count: int,
    post_type: Optional[str] = None,
) -> DiscordSelectionRequest:
    plan = build_draft_media_plan(connection, draft_id)
    final_post_type = post_type or plan.post_type
    suggested_count = len(plan.items)
    _validate_target_count(target_count, suggested_count, final_post_type)
    return DiscordSelectionRequest(
        draft_id=plan.draft_id,
        post_type=final_post_type,
        target_count=target_count,
        suggested_count=suggested_count,
        items=plan.items,
    )


def apply_discord_photo_selection(
    connection,
    draft_id: int,
    *,
    selected_numbers: Sequence[int],
    lead: int,
    target_count: int,
    post_type: Optional[str] = None,
) -> DraftMediaSelectionResult:
    request = build_discord_selection_request(
        connection,
        draft_id,
        target_count=target_count,
        post_type=post_type,
    )
    unique_selected = _unique_numbers(selected_numbers)
    if len(selected_numbers) != len(unique_selected):
        raise InvalidDiscordSelection("Duplicate selected photo numbers are not allowed")
    if len(unique_selected) != target_count:
        raise InvalidDiscordSelection(f"Select exactly {target_count} photo numbers")
    if lead not in unique_selected:
        raise InvalidDiscordSelection("Lead photo must be included in the final media selection")
    known_numbers = {item.review_number for item in request.items}
    invalid = [number for number in unique_selected if number not in known_numbers]
    if invalid:
        raise InvalidDiscordSelection(
            f"Unknown suggested photo number(s): {', '.join(str(number) for number in invalid)}"
        )
    try:
        return apply_draft_media_selection(
            connection,
            draft_id,
            lead=lead,
            keep=unique_selected,
            post_type=request.post_type,
        )
    except InvalidMediaSelection as error:
        raise InvalidDiscordSelection(str(error)) from error


def _validate_target_count(target_count: int, suggested_count: int, post_type: str) -> None:
    if target_count < 1:
        raise InvalidDiscordSelection("Target selection count must be at least 1")
    if target_count > suggested_count:
        raise InvalidDiscordSelection("Target selection count cannot exceed suggested photo count")
    if post_type == "single_image" and target_count != 1:
        raise InvalidDiscordSelection("Single-image selections require exactly one photo")
    if post_type == "carousel" and not 2 <= target_count <= 10:
        raise InvalidDiscordSelection("Carousel selections require 2 to 10 photos")
    if post_type not in {"single_image", "carousel", "reel"}:
        raise InvalidDiscordSelection("Post type must be single_image, carousel, or reel")


def _unique_numbers(numbers: Sequence[int]) -> list[int]:
    result: list[int] = []
    for number in numbers:
        if number not in result:
            result.append(number)
    return result


def _display_name(path: str) -> str:
    return Path(path).name

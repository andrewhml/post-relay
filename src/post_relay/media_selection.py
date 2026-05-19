from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from post_relay.contact_sheet_design import anchor_from_chess, chess_from_anchor, ratio_label, ratio_from_label, tightness_label, clamp
from post_relay.repository import (
    CandidateGroupPhotoItemRecord,
    DraftRecord,
    get_draft,
    invalidate_active_approvals,
    list_active_approvals,
    list_candidate_group_photo_items,
    update_candidate_group_photo_crop,
    update_candidate_group_photo_item,
    update_draft_content,
)
from post_relay.state import DraftState, transition_draft_state


class DraftNotFound(ValueError):
    pass


class InvalidMediaSelection(ValueError):
    pass


@dataclass(frozen=True)
class DraftMediaPlanItem:
    review_number: int
    photo_id: int
    local_file_path: str
    role: str
    include_status: str
    crop_ratio: float = 1.0
    crop_anchor_x: float = 0.5
    crop_anchor_y: float = 0.5
    crop_tightness: float = 1.0

    @property
    def crop_anchor(self) -> str:
        return chess_from_anchor(self.crop_anchor_x, self.crop_anchor_y)


@dataclass(frozen=True)
class DraftMediaPlan:
    draft_id: int
    post_type: str
    items: list[DraftMediaPlanItem]

    def to_text(self) -> str:
        lines = [
            "Post Media Plan",
            f"Post ID: {self.draft_id}",
            f"Post type: {self.post_type}",
            "Media:",
        ]
        if not self.items:
            lines.append("  <none>")
        else:
            lines.extend(
                f"  {item.review_number}. [{item.role}] {item.include_status} {item.local_file_path} "
                f"(crop {item.crop_anchor}, {ratio_label(item.crop_ratio)}, {tightness_label(item.crop_tightness)})"
                for item in self.items
            )
        lines.extend(
            [
                "Edit examples:",
                "  drafts media-edit --post-id N --lead 3 --keep 1,3,5 --post-type carousel",
                "  drafts media-edit --post-id N --lead 2 --remove 4",
                "Crop feedback examples:",
                "  drafts crop-feedback --post-id N --shift 3:B2 --tighten 3",
                "  drafts crop-feedback --post-id N --center 5 --ratio 5:4:5",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class DraftCropFeedbackResult:
    draft_id: int
    updated_items: list[DraftMediaPlanItem]
    invalidated_approval_count: int

    def to_text(self) -> str:
        lines = ["Crop Feedback Applied", f"Post ID: {self.draft_id}", "Updated crops:"]
        for item in self.updated_items:
            lines.append(
                f"  - Moved {item.review_number}'s crop anchor to {item.crop_anchor}; "
                f"ratio {ratio_label(item.crop_ratio)}; tightness {tightness_label(item.crop_tightness)}"
            )
        if self.invalidated_approval_count:
            lines.append(f"Invalidated active approvals: {self.invalidated_approval_count}")
        lines.append("No Discord, R2, or Meta network calls were made.")
        return "\n".join(lines)


@dataclass(frozen=True)
class DraftMediaSelectionResult:
    draft_id: int
    post_type: str
    included_items: list[DraftMediaPlanItem]
    excluded_items: list[DraftMediaPlanItem]
    invalidated_approval_count: int

    def to_text(self) -> str:
        lines = [
            f"Updated media selection for post #{self.draft_id}.",
            f"Post type: {self.post_type}",
            f"Lead: {_display_name(self.included_items[0].local_file_path) if self.included_items else '<none>'}",
            "Included:",
        ]
        lines.extend(_format_items(self.included_items))
        lines.append("Excluded:")
        lines.extend(_format_items(self.excluded_items))
        if self.invalidated_approval_count:
            lines.append(f"Invalidated active approvals: {self.invalidated_approval_count}")
        return "\n".join(lines)


def build_draft_media_plan(connection, draft_id: int) -> DraftMediaPlan:
    draft = _require_draft(connection, draft_id)
    current_items = list_candidate_group_photo_items(connection, draft.candidate_group_id)
    return DraftMediaPlan(
        draft_id=draft.id,
        post_type=draft.post_type,
        items=_number_items(current_items),
    )


def apply_draft_media_selection(
    connection,
    draft_id: int,
    *,
    lead: int,
    keep: Optional[Sequence[int]] = None,
    remove: Optional[Sequence[int]] = None,
    post_type: Optional[str] = None,
) -> DraftMediaSelectionResult:
    draft = _require_draft(connection, draft_id)
    original_items = list_candidate_group_photo_items(connection, draft.candidate_group_id)
    numbered_original = _number_items(original_items)
    if not numbered_original:
        raise InvalidMediaSelection(f"Post #{draft_id} has no candidate media to select")

    by_number = {item.review_number: item for item in numbered_original}
    _validate_positions([lead], by_number)
    if keep and remove:
        raise InvalidMediaSelection("Use either keep or remove, not both")
    if keep is not None:
        _validate_positions(keep, by_number)
        keep_numbers = _unique_numbers(keep)
    else:
        remove_numbers = _unique_numbers(remove or [])
        _validate_positions(remove_numbers, by_number)
        keep_numbers = [item.review_number for item in numbered_original if item.review_number not in remove_numbers]
    if lead not in keep_numbers:
        raise InvalidMediaSelection("Lead photo must be included in the final media selection")

    final_numbers = [lead] + [number for number in keep_numbers if number != lead]
    if not final_numbers:
        raise InvalidMediaSelection("At least one photo must remain included")

    final_post_type = post_type or draft.post_type
    _validate_post_type(final_post_type, final_numbers)

    included_numbers = set(final_numbers)
    final_order_by_number = {number: index for index, number in enumerate(final_numbers, start=1)}
    excluded_order = len(final_numbers) + 1
    for item in numbered_original:
        is_included = item.review_number in included_numbers
        update_candidate_group_photo_item(
            connection,
            group_id=draft.candidate_group_id,
            photo_id=item.photo_id,
            sort_order=final_order_by_number.get(item.review_number, excluded_order),
            role="primary" if item.review_number == lead else "support",
            include_status="included" if is_included else "excluded",
        )
        if not is_included:
            excluded_order += 1

    invalidated_count = 0
    active_approvals = list_active_approvals(connection, draft.id)
    status = None
    if active_approvals:
        status = transition_draft_state(DraftState(draft.status), DraftState.NEEDS_EDITS).value
        invalidated_count = invalidate_active_approvals(
            connection,
            draft.id,
            reason="material post media selection edit",
        )

    updated_draft = update_draft_content(connection, draft.id, status=status)
    if updated_draft is None:
        raise DraftNotFound(f"Post #{draft_id} was not found")
    if final_post_type != draft.post_type:
        connection.execute(
            "update drafts set post_type = ?, updated_at = current_timestamp where id = ?",
            (final_post_type, draft.id),
        )
    connection.execute(
        """
        update drafts
        set media_selection_confirmed_at = current_timestamp,
            updated_at = current_timestamp
        where id = ?
        """,
        (draft.id,),
    )
    connection.commit()

    refreshed_items = _number_items(list_candidate_group_photo_items(connection, draft.candidate_group_id))
    return DraftMediaSelectionResult(
        draft_id=draft.id,
        post_type=final_post_type,
        included_items=[item for item in refreshed_items if item.include_status == "included"],
        excluded_items=[item for item in refreshed_items if item.include_status == "excluded"],
        invalidated_approval_count=invalidated_count,
    )


def apply_draft_crop_feedback(connection, draft_id: int, *, crop_edits: dict[int, dict]) -> DraftCropFeedbackResult:
    draft = _require_draft(connection, draft_id)
    original_items = list_candidate_group_photo_items(connection, draft.candidate_group_id)
    numbered_original = _number_items(original_items)
    if not numbered_original:
        raise InvalidMediaSelection(f"Post #{draft_id} has no candidate media to crop")
    by_number = {item.review_number: item for item in numbered_original}
    _validate_positions(list(crop_edits.keys()), by_number)

    changed_numbers: list[int] = []
    for review_number, edit in crop_edits.items():
        item = by_number[review_number]
        ratio = _resolve_crop_ratio(item, edit)
        ax, ay = _resolve_crop_anchor(item, edit)
        tightness = _resolve_crop_tightness(item, edit)
        update_candidate_group_photo_crop(
            connection,
            group_id=draft.candidate_group_id,
            photo_id=item.photo_id,
            crop_ratio=ratio,
            crop_anchor_x=ax,
            crop_anchor_y=ay,
            crop_tightness=tightness,
        )
        changed_numbers.append(review_number)

    invalidated_count = 0
    active_approvals = list_active_approvals(connection, draft.id)
    if active_approvals:
        status = transition_draft_state(DraftState(draft.status), DraftState.NEEDS_EDITS).value
        invalidated_count = invalidate_active_approvals(
            connection,
            draft.id,
            reason="material post crop feedback edit",
        )
        updated_draft = update_draft_content(connection, draft.id, status=status)
        if updated_draft is None:
            raise DraftNotFound(f"Post #{draft_id} was not found")
    connection.commit()

    refreshed = _number_items(list_candidate_group_photo_items(connection, draft.candidate_group_id))
    refreshed_by_number = {item.review_number: item for item in refreshed}
    return DraftCropFeedbackResult(
        draft_id=draft.id,
        updated_items=[refreshed_by_number[number] for number in changed_numbers],
        invalidated_approval_count=invalidated_count,
    )


def _resolve_crop_anchor(item: DraftMediaPlanItem, edit: dict) -> tuple[float, float]:
    if edit.get("center"):
        ax, ay = 0.5, 0.5
    elif edit.get("anchor"):
        try:
            ax, ay = anchor_from_chess(str(edit["anchor"]))
        except ValueError as error:
            raise InvalidMediaSelection(str(error)) from error
    else:
        ax, ay = item.crop_anchor_x, item.crop_anchor_y
    ax = clamp(ax + (float(edit.get("nudge_x", 0)) * 0.25))
    ay = clamp(ay + (float(edit.get("nudge_y", 0)) * 0.25))
    return ax, ay


def _resolve_crop_ratio(item: DraftMediaPlanItem, edit: dict) -> float:
    ratio = edit.get("ratio", item.crop_ratio)
    if isinstance(ratio, str):
        try:
            ratio = ratio_from_label(ratio)
        except (ValueError, ZeroDivisionError) as error:
            raise InvalidMediaSelection("Crop ratio must be 1:1, 4:5, 1.91:1, 9:16, or a positive number") from error
    ratio = float(ratio)
    if ratio <= 0:
        raise InvalidMediaSelection("Crop ratio must be positive")
    return ratio


def _resolve_crop_tightness(item: DraftMediaPlanItem, edit: dict) -> float:
    tightness = float(edit.get("tightness", item.crop_tightness))
    tightness += float(edit.get("tightness_delta", 0))
    return clamp(tightness, 0.5, 1.0)


def _require_draft(connection, draft_id: int) -> DraftRecord:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post #{draft_id} was not found")
    return draft


def _number_items(items: list[CandidateGroupPhotoItemRecord]) -> list[DraftMediaPlanItem]:
    return [
        DraftMediaPlanItem(
            review_number=index,
            photo_id=item.photo_id,
            local_file_path=item.local_file_path,
            role=item.role,
            include_status=item.include_status,
            crop_ratio=item.crop_ratio if item.crop_ratio is not None else 1.0,
            crop_anchor_x=item.crop_anchor_x if item.crop_anchor_x is not None else 0.5,
            crop_anchor_y=item.crop_anchor_y if item.crop_anchor_y is not None else 0.5,
            crop_tightness=item.crop_tightness if item.crop_tightness is not None else 1.0,
        )
        for index, item in enumerate(items, start=1)
    ]


def _unique_numbers(numbers: Sequence[int]) -> list[int]:
    result: list[int] = []
    for number in numbers:
        if number not in result:
            result.append(number)
    return result


def _validate_positions(numbers: Sequence[int], by_number: dict[int, DraftMediaPlanItem]) -> None:
    invalid = [number for number in numbers if number not in by_number]
    if invalid:
        raise InvalidMediaSelection(f"Unknown review media number(s): {', '.join(str(number) for number in invalid)}")


def _validate_post_type(post_type: str, final_numbers: Sequence[int]) -> None:
    if post_type not in {"single_image", "carousel", "reel"}:
        raise InvalidMediaSelection("Post type must be single_image, carousel, or reel")
    if post_type == "single_image" and len(final_numbers) != 1:
        raise InvalidMediaSelection("single_image drafts must include exactly one photo")
    if post_type == "carousel" and len(final_numbers) < 2:
        raise InvalidMediaSelection("carousel drafts must include at least two photos")
    if post_type == "carousel" and len(final_numbers) > 10:
        raise InvalidMediaSelection("carousel drafts support at most ten photos")


def _format_items(items: list[DraftMediaPlanItem]) -> list[str]:
    if not items:
        return ["  <none>"]
    return [
        f"  {index}. [{item.role}] {item.local_file_path}"
        for index, item in enumerate(items, start=1)
    ]


def _display_name(path: str) -> str:
    return Path(path).name

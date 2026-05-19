from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from post_relay.discord_selection import build_discord_selection_request
from post_relay.instagram_capabilities import capability_matrix_text
from post_relay.review_package import (
    DraftNotFound,
    DraftReviewPackage,
    build_draft_review_package,
)


@dataclass(frozen=True)
class DiscordPreviewPayload:
    draft_id: int
    destination: str
    dry_run: bool
    message_text: str
    image_paths: List[str]
    missing_image_paths: List[str]

    @property
    def ready_to_send(self) -> bool:
        return not self.missing_image_paths

    def to_text(self) -> str:
        lines = [
            "Discord Preview Payload (dry run)",
            f"Post ID: {self.draft_id}",
            f"Ready to send: {'yes' if self.ready_to_send else 'no'}",
            "Image attachments:",
        ]
        if self.image_paths:
            lines.extend(
                f"  {index}. {path}" for index, path in enumerate(self.image_paths, start=1)
            )
        else:
            lines.append("  <none>")
        lines.append("Missing image files:")
        if self.missing_image_paths:
            lines.extend(f"  - {path}" for path in self.missing_image_paths)
        else:
            lines.append("  - <none>")
        lines.extend(["Message text:", self.message_text])
        return "\n".join(lines)


@dataclass(frozen=True)
class DiscordSelectionAttachment:
    review_number: int
    local_file_path: str
    exists: bool


@dataclass(frozen=True)
class DiscordSelectionPayload:
    draft_id: int
    destination: str
    dry_run: bool
    post_type: str
    target_count: int
    suggested_count: int
    message_text: str
    attachments: List[DiscordSelectionAttachment]
    image_paths: List[str]
    missing_image_paths: List[str]
    artifact_paths: List[str]
    missing_artifact_paths: List[str]

    @property
    def ready_to_send(self) -> bool:
        return not self.missing_image_paths and not self.missing_artifact_paths

    def to_text(self) -> str:
        lines = [
            "Discord Selection Payload (dry run)",
            f"Post ID: {self.draft_id}",
            f"Dry run: {'yes' if self.dry_run else 'no'}",
            "No Discord messages were sent.",
            f"Ready to send: {'yes' if self.ready_to_send else 'no'}",
            f"Post type: {self.post_type}",
            f"Select {self.target_count} of {self.suggested_count} suggested photos.",
            "Image attachments:",
        ]
        if self.attachments:
            lines.extend(_attachment_line(attachment) for attachment in self.attachments)
        else:
            lines.append("  <none>")
        lines.append("Missing image files:")
        if self.missing_image_paths:
            lines.extend(f"  - {path}" for path in self.missing_image_paths)
        else:
            lines.append("  - <none>")
        lines.append("Designed local artifact references:")
        if self.artifact_paths:
            lines.extend(f"  - {path}" for path in self.artifact_paths)
        else:
            lines.append("  - <none>")
        lines.append("Missing artifact files:")
        if self.missing_artifact_paths:
            lines.extend(f"  - {path}" for path in self.missing_artifact_paths)
        else:
            lines.append("  - <none>")
        lines.extend(
            [
                "Interaction semantics:",
                f"  - Accept exactly {self.target_count} selected photo numbers.",
                "  - Lead/cover must be one of the selected numbers.",
                "  - Preserve Andrew's selected order; the lead/cover is first in the final post media order.",
                "  - Crop/position feedback can use A1-E5 language from the designed contact sheet (e.g. shift 03 to B2, center 05, tighten 06).",
                "Command fallback:",
                _command_fallback(self.draft_id, self.target_count, self.post_type),
                "Crop feedback fallback:",
                f"  drafts crop-feedback --draft-id {self.draft_id} --shift 3:B2 --center 5 --tighten 6",
                "Fallbacks if Discord attachments fail:",
                "  - use the designed contact sheet or final post preview artifact paths rendered locally",
                "  - use local source paths for manual review",
                "  - stage review media separately only after the dry-run payload remains green",
                "Instagram capability notes:",
                capability_matrix_text(),
                "Message text:",
                self.message_text,
            ]
        )
        return "\n".join(lines)


def build_discord_preview_payload(connection, draft_id: int) -> DiscordPreviewPayload:
    review_package = build_draft_review_package(connection, draft_id)
    existing_paths = _existing_paths(review_package)
    missing_paths = _missing_paths(review_package)
    return DiscordPreviewPayload(
        draft_id=review_package.draft_id,
        destination="discord",
        dry_run=True,
        message_text=review_package.to_text(),
        image_paths=existing_paths,
        missing_image_paths=missing_paths,
    )


def build_discord_selection_payload(
    connection,
    draft_id: int,
    *,
    target_count: int,
    post_type: Optional[str] = None,
    artifact_paths: Sequence[Path] = (),
) -> DiscordSelectionPayload:
    selection_request = build_discord_selection_request(
        connection,
        draft_id,
        target_count=target_count,
        post_type=post_type,
    )
    attachments = [
        DiscordSelectionAttachment(
            review_number=item.review_number,
            local_file_path=item.local_file_path,
            exists=Path(item.local_file_path).is_file(),
        )
        for item in selection_request.items
    ]
    artifact_path_strings = [Path(path).as_posix() for path in artifact_paths]
    return DiscordSelectionPayload(
        draft_id=selection_request.draft_id,
        destination="discord",
        dry_run=True,
        post_type=selection_request.post_type,
        target_count=selection_request.target_count,
        suggested_count=selection_request.suggested_count,
        message_text=selection_request.to_text(),
        attachments=attachments,
        image_paths=[attachment.local_file_path for attachment in attachments if attachment.exists],
        missing_image_paths=[attachment.local_file_path for attachment in attachments if not attachment.exists],
        artifact_paths=[path for path in artifact_path_strings if Path(path).is_file()],
        missing_artifact_paths=[path for path in artifact_path_strings if not Path(path).is_file()],
    )


def _existing_paths(review_package: DraftReviewPackage) -> List[str]:
    return [
        path
        for path in review_package.photo_file_paths
        if Path(path).is_file()
    ]


def _missing_paths(review_package: DraftReviewPackage) -> List[str]:
    return [
        path
        for path in review_package.photo_file_paths
        if not Path(path).is_file()
    ]


def _command_fallback(draft_id: int, target_count: int, post_type: str) -> str:
    select_values = ",".join(str(index) for index in range(1, target_count + 1)) or "<numbers>"
    lead = "1" if target_count else "<lead>"
    return (
        "  drafts discord-selection-apply "
        f"--draft-id {draft_id} --select {select_values} --lead {lead} "
        f"--target-count {target_count} --post-type {post_type}"
    )


def _attachment_line(attachment: DiscordSelectionAttachment) -> str:
    if attachment.exists:
        return f"  {attachment.review_number}. {attachment.local_file_path}"
    return f"  {attachment.review_number}. <missing> {attachment.local_file_path}"

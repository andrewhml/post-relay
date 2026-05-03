from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

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
            f"Draft ID: {self.draft_id}",
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

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image, ImageOps

from post_relay.config import PublishExportsConfig
from post_relay.image_export_profiles import (
    LANDSCAPE_TREATMENTS,
    PROFILES,
    ImageExportProfile as PublishExportProfile,
    choose_treatment,
    export_image_for_profile,
    orientation,
)
from post_relay.media_selection import build_draft_media_plan
from post_relay.repository import get_candidate_group, get_draft
from post_relay.review_artifacts import _ensure_artifact_root_is_safe


class DraftNotFound(ValueError):
    pass


class UnsupportedPublishExportProfile(ValueError):
    pass


class UnsupportedLandscapeTreatment(ValueError):
    pass


@dataclass(frozen=True)
class PublishExportMediaItem:
    source_path: str
    local_path: str
    width: int
    height: int
    treatment: str
    source_orientation: str

    @property
    def object_key_hint(self) -> str:
        return Path(self.local_path).name


@dataclass(frozen=True)
class PublishExportsPackage:
    draft_id: int
    candidate_title: str
    profile_name: str
    width: int
    height: int
    export_root: Path
    media_items: list[PublishExportMediaItem]
    contact_sheet_path: Optional[str]
    warnings: list[str]

    def to_text(self) -> str:
        lines = [
            "Publish Exports",
            f"Post ID: {self.draft_id}",
            f"Candidate: {self.candidate_title}",
            f"Profile: {self.profile_name} ({self.width}x{self.height})",
            f"Export root: {self.export_root.as_posix()}",
            "Media:",
        ]
        if self.media_items:
            lines.extend(
                f"  {index}. {item.local_path} ({item.width}x{item.height}, {item.treatment})"
                for index, item in enumerate(self.media_items, start=1)
            )
        else:
            lines.append("  <none>")
        lines.append("Warnings:")
        if self.warnings:
            lines.extend(f"  - {warning}" for warning in self.warnings)
        else:
            lines.append("  <none>")
        lines.append("No Discord, R2, or Meta network calls were made.")
        return "\n".join(lines)


def render_publish_exports_for_draft(
    connection,
    draft_id: int,
    config: PublishExportsConfig,
    *,
    profile_name: str = "feed_portrait_3x4",
    landscape_treatment: str = "clean_mat",
    protected_source_roots: Sequence[Path] = (),
) -> PublishExportsPackage:
    profile = PROFILES.get(profile_name)
    if profile is None:
        raise UnsupportedPublishExportProfile(f"Unsupported publish export profile: {profile_name}")
    if landscape_treatment not in LANDSCAPE_TREATMENTS:
        raise UnsupportedLandscapeTreatment(f"Unsupported landscape treatment: {landscape_treatment}")

    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post {draft_id} was not found.")
    candidate = get_candidate_group(connection, draft.candidate_group_id)
    candidate_title = candidate.title if candidate is not None else f"candidate #{draft.candidate_group_id}"
    media_plan = build_draft_media_plan(connection, draft_id)
    selected_items = [item for item in media_plan.items if item.include_status == "included"]

    export_root = config.root / f"draft-{draft.id}" / profile.name
    _ensure_artifact_root_is_safe(export_root, protected_source_roots)
    stale_contact_sheet = export_root / "publish-contact-sheet.jpg"
    if stale_contact_sheet.exists():
        stale_contact_sheet.unlink()
    media_root = export_root / "media"
    media_root.mkdir(parents=True, exist_ok=True)

    media_items: list[PublishExportMediaItem] = []
    source_orientations: list[str] = []
    for index, item in enumerate(selected_items, start=1):
        source = Path(item.local_file_path)
        with Image.open(source) as image:
            original = ImageOps.exif_transpose(image).convert("RGB")
            source_orientation = orientation(original.width, original.height)
            source_orientations.append(source_orientation)
            treatment = choose_treatment(source_orientation, profile, landscape_treatment)
            exported = export_image_for_profile(
                original,
                profile,
                treatment,
                crop_anchor_x=item.crop_anchor_x,
                crop_anchor_y=item.crop_anchor_y,
                crop_tightness=item.crop_tightness,
            )
            output_path = media_root / f"{index:02d}-{_safe_artifact_stem(source)}.jpg"
            exported.save(output_path, format="JPEG", quality=92)
            media_items.append(
                PublishExportMediaItem(
                    source_path=source.as_posix(),
                    local_path=output_path.as_posix(),
                    width=exported.width,
                    height=exported.height,
                    treatment=treatment,
                    source_orientation=source_orientation,
                )
            )

    warnings = _build_warnings(source_orientations)
    return PublishExportsPackage(
        draft_id=draft.id,
        candidate_title=candidate_title,
        profile_name=profile.name,
        width=profile.width,
        height=profile.height,
        export_root=export_root,
        media_items=media_items,
        contact_sheet_path=None,
        warnings=warnings,
    )


def list_publish_export_media_paths(
    draft_id: int,
    export_root: Path,
    *,
    profile_name: str = "feed_portrait_3x4",
) -> list[str]:
    media_root = export_root / f"draft-{draft_id}" / profile_name / "media"
    return [path.as_posix() for path in sorted(media_root.glob("*.jpg"))]


def _build_warnings(source_orientations: list[str]) -> list[str]:
    unique = sorted(set(source_orientations))
    if len(unique) > 1:
        return [f"Mixed media orientations detected: {', '.join(unique)}"]
    return []


def _safe_artifact_stem(path: Path) -> str:
    stem = path.stem.strip().lower()
    safe = "".join(character if character.isalnum() else "-" for character in stem)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe or "image"

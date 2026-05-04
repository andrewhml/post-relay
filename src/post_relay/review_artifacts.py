from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from PIL import Image, ImageOps

from post_relay.config import ReviewArtifactsConfig
from post_relay.repository import get_candidate_group, get_draft, list_candidate_group_photo_paths


class DraftNotFound(ValueError):
    pass


class UnsafeArtifactRoot(ValueError):
    pass


@dataclass(frozen=True)
class ThumbnailArtifact:
    source_path: str
    local_path: str
    width: int
    height: int


@dataclass(frozen=True)
class ReviewArtifactsPackage:
    draft_id: int
    candidate_title: str
    artifact_root: Path
    thumbnails: List[ThumbnailArtifact]
    contact_sheet_path: str

    def to_text(self) -> str:
        lines = [
            "Review Artifacts",
            f"Draft ID: {self.draft_id}",
            f"Candidate: {self.candidate_title}",
            f"Artifact root: {self.artifact_root.as_posix()}",
            "Thumbnails:",
        ]
        if self.thumbnails:
            lines.extend(
                f"  {index}. {artifact.local_path} ({artifact.width}x{artifact.height})"
                for index, artifact in enumerate(self.thumbnails, start=1)
            )
        else:
            lines.append("  <none>")
        lines.extend(["Contact sheet:", f"  {self.contact_sheet_path}"])
        return "\n".join(lines)


def render_review_artifacts_for_draft(
    connection,
    draft_id: int,
    config: ReviewArtifactsConfig,
    *,
    protected_source_roots: Sequence[Path] = (),
) -> ReviewArtifactsPackage:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft {draft_id} was not found.")

    source_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    candidate = get_candidate_group(connection, draft.candidate_group_id)
    candidate_title = candidate.title if candidate is not None else f"candidate #{draft.candidate_group_id}"
    artifact_root = config.root / f"draft-{draft.id}"
    _ensure_artifact_root_is_safe(artifact_root, protected_source_roots)
    thumbnails_root = artifact_root / "thumbnails"
    thumbnails_root.mkdir(parents=True, exist_ok=True)

    thumbnails: list[ThumbnailArtifact] = []
    thumbnail_images: list[Image.Image] = []
    for index, source_path in enumerate(source_paths, start=1):
        source = Path(source_path)
        thumbnail_path = thumbnails_root / f"{index:02d}-{_safe_artifact_stem(source)}.jpg"
        with Image.open(source) as image:
            thumbnail_image = ImageOps.exif_transpose(image).convert("RGB")
            thumbnail_image.thumbnail(
                (config.thumbnail_max_px, config.thumbnail_max_px), Image.Resampling.LANCZOS
            )
            thumbnail_image.save(thumbnail_path, format="JPEG", quality=85)
            thumbnail_images.append(thumbnail_image.copy())
            thumbnails.append(
                ThumbnailArtifact(
                    source_path=source.as_posix(),
                    local_path=thumbnail_path.as_posix(),
                    width=thumbnail_image.width,
                    height=thumbnail_image.height,
                )
            )

    contact_sheet_path = artifact_root / "contact-sheet.jpg"
    _save_contact_sheet(
        thumbnail_images,
        contact_sheet_path,
        title=f"Draft {draft.id}: {candidate_title}",
        max_px=config.thumbnail_max_px,
        columns=config.contact_sheet_columns,
    )
    for image in thumbnail_images:
        image.close()

    return ReviewArtifactsPackage(
        draft_id=draft.id,
        candidate_title=candidate_title,
        artifact_root=artifact_root,
        thumbnails=thumbnails,
        contact_sheet_path=contact_sheet_path.as_posix(),
    )


def _ensure_artifact_root_is_safe(artifact_root: Path, protected_source_roots: Sequence[Path]) -> None:
    resolved_artifact_root = artifact_root.expanduser().resolve(strict=False)
    for source_root in protected_source_roots:
        resolved_source_root = source_root.expanduser().resolve(strict=False)
        if _paths_overlap(resolved_artifact_root, resolved_source_root):
            raise UnsafeArtifactRoot(
                "Review artifact root must not overlap a configured photo source root: "
                f"{artifact_root} overlaps {source_root}"
            )


def _paths_overlap(first: Path, second: Path) -> bool:
    return _is_relative_to(first, second) or _is_relative_to(second, first)


def _is_relative_to(path: Path, possible_parent: Path) -> bool:
    try:
        path.relative_to(possible_parent)
    except ValueError:
        return False
    return True



def _save_contact_sheet(
    images: list[Image.Image],
    path: Path,
    *,
    title: str,
    max_px: int,
    columns: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header_height = 24
    if not images:
        sheet = Image.new("RGB", (max_px, max_px + header_height), color="white")
        _draw_sheet_header(sheet, title)
        sheet.save(path, format="JPEG", quality=85)
        return

    column_count = max(1, columns)
    row_count = (len(images) + column_count - 1) // column_count
    sheet = Image.new(
        "RGB", (column_count * max_px, row_count * max_px + header_height), color="white"
    )
    _draw_sheet_header(sheet, title)
    for index, image in enumerate(images):
        row = index // column_count
        column = index % column_count
        x = column * max_px + (max_px - image.width) // 2
        y = header_height + row * max_px + (max_px - image.height) // 2
        sheet.paste(image, (x, y))
    sheet.save(path, format="JPEG", quality=85)


def _draw_sheet_header(sheet: Image.Image, title: str) -> None:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(sheet)
    draw.rectangle((0, 0, sheet.width, 23), fill="white")
    draw.text((8, 6), title, fill="black")


def _safe_artifact_stem(path: Path) -> str:
    stem = path.stem.strip().lower()
    safe = "".join(character if character.isalnum() else "-" for character in stem)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe or "image"

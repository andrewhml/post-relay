from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence


LARGE_REVIEW_ARTIFACT_MEDIA_COUNT = 120
BOUNDED_REVIEW_SAMPLE_COUNT = 24

from PIL import Image, ImageDraw, ImageFont, ImageOps

from post_relay.config import ReviewArtifactsConfig
from post_relay.contact_sheet_design import ContactSheetPhoto, chess_from_anchor, chess_span, crop_box, ratio_label, tightness_label
from post_relay.media_selection import build_draft_media_plan
from post_relay.repository import get_candidate_group, get_draft, list_candidate_group_photo_paths


class DraftNotFound(ValueError):
    pass


class UnsafeArtifactRoot(ValueError):
    pass


class OversizedReviewArtifactSet(ValueError):
    def __init__(self, plan: "BoundedReviewArtifactPlan") -> None:
        super().__init__(
            f"Post {plan.draft_id} has {plan.media_count} included photos; "
            "use a bounded review plan before rendering a full contact sheet."
        )
        self.plan = plan


@dataclass(frozen=True)
class BoundedReviewArtifactPlan:
    draft_id: int
    candidate_title: str
    media_count: int
    large_threshold: int
    sample_count: int

    @property
    def classification(self) -> str:
        if self.media_count >= self.large_threshold:
            return "large"
        return "normal"

    @property
    def full_render_safe(self) -> bool:
        return self.classification != "large"

    def to_text(self) -> str:
        lines = [
            "Bounded Review Artifact Plan",
            f"Post ID: {self.draft_id}",
            f"Candidate: {self.candidate_title}",
            f"Media volume: {self.media_count} included photos ({self.classification})",
        ]
        if self.full_render_safe:
            lines.extend(
                [
                    "Full contact sheet render is safe for this post.",
                    f"Next command: drafts artifacts render --draft-id {self.draft_id}",
                ]
            )
        else:
            sample_end = min(self.sample_count, self.media_count)
            lines.extend(
                [
                    "Full contact sheet render blocked until the set is narrowed.",
                    f"Recommended bounded first-pass review: inspect a capped first-pass review of items 1-{sample_end}, then choose a smaller range or explicit keep list.",
                    f"Operator commands: drafts media-plan --draft-id {self.draft_id}",
                    f"Operator commands: drafts media-edit --draft-id {self.draft_id} --keep <comma-separated-numbers> --lead <number> --post-type carousel",
                    "DM-safe prompt: This matched a large photo set. Please send a smaller range, date/neighborhood cue, or 5-10 filenames before I render the full contact sheet.",
                ]
            )
        lines.append("No Discord, R2, or Meta network calls were made.")
        return "\n".join(lines)


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
            f"Post ID: {self.draft_id}",
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


def plan_bounded_review_artifacts_for_draft(
    connection,
    draft_id: int,
    *,
    large_threshold: int = LARGE_REVIEW_ARTIFACT_MEDIA_COUNT,
    sample_count: int = BOUNDED_REVIEW_SAMPLE_COUNT,
) -> BoundedReviewArtifactPlan:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post {draft_id} was not found.")

    source_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    candidate = get_candidate_group(connection, draft.candidate_group_id)
    candidate_title = candidate.title if candidate is not None else f"candidate #{draft.candidate_group_id}"
    return BoundedReviewArtifactPlan(
        draft_id=draft.id,
        candidate_title=candidate_title,
        media_count=len(source_paths),
        large_threshold=large_threshold,
        sample_count=sample_count,
    )


def render_review_artifacts_for_draft(
    connection,
    draft_id: int,
    config: ReviewArtifactsConfig,
    *,
    protected_source_roots: Sequence[Path] = (),
    allow_large: bool = False,
) -> ReviewArtifactsPackage:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post {draft_id} was not found.")

    source_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    candidate = get_candidate_group(connection, draft.candidate_group_id)
    candidate_title = candidate.title if candidate is not None else f"candidate #{draft.candidate_group_id}"
    plan = BoundedReviewArtifactPlan(
        draft_id=draft.id,
        candidate_title=candidate_title,
        media_count=len(source_paths),
        large_threshold=LARGE_REVIEW_ARTIFACT_MEDIA_COUNT,
        sample_count=BOUNDED_REVIEW_SAMPLE_COUNT,
    )
    if not allow_large and not plan.full_render_safe:
        raise OversizedReviewArtifactSet(plan)

    artifact_root = config.root / f"draft-{draft.id}"
    _ensure_artifact_root_is_safe(artifact_root, protected_source_roots)
    thumbnails_root = artifact_root / "thumbnails"
    thumbnails_root.mkdir(parents=True, exist_ok=True)

    thumbnails: list[ThumbnailArtifact] = []
    contact_sheet_photos: list[tuple[ContactSheetPhoto, Image.Image, bool]] = []
    media_plan = build_draft_media_plan(connection, draft.id)
    for index, item in enumerate(media_plan.items, start=1):
        source = Path(item.local_file_path)
        thumbnail_path = thumbnails_root / f"{index:02d}-{_safe_artifact_stem(source)}.jpg"
        with Image.open(source) as image:
            full_image = ImageOps.exif_transpose(image).convert("RGB")
            thumbnail_image = full_image.copy()
            thumbnail_image.thumbnail(
                (config.thumbnail_max_px, config.thumbnail_max_px), Image.Resampling.LANCZOS
            )
            thumbnail_image.save(thumbnail_path, format="JPEG", quality=85)
            contact_sheet_photos.append(
                (
                    ContactSheetPhoto(
                        n=index,
                        file=source.name,
                        src=source.as_posix(),
                        w=full_image.width,
                        h=full_image.height,
                        ratio=item.crop_ratio,
                        ax=item.crop_anchor_x,
                        ay=item.crop_anchor_y,
                        tight=item.crop_tightness,
                    ),
                    full_image.copy(),
                    item.role == "primary",
                )
            )
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
        contact_sheet_photos,
        contact_sheet_path,
        title=f"Post {draft.id}: {candidate_title}",
        max_px=config.thumbnail_max_px,
        columns=config.contact_sheet_columns,
    )
    for _photo, image, _is_lead in contact_sheet_photos:
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



DESIGN_BG = (20, 18, 15)
DESIGN_MAT = (12, 11, 9)
DESIGN_CARD = (28, 25, 21)
DESIGN_AMBER = (232, 168, 56)
DESIGN_TEXT = (239, 232, 220)
DESIGN_MUTED = (155, 143, 124)


def _save_contact_sheet(
    photos: list[tuple[ContactSheetPhoto, Image.Image, bool]],
    path: Path,
    *,
    title: str,
    max_px: int,
    columns: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    font = _font(13)
    small = _font(10)
    mono = _font(11)
    header_height = 78
    footer_height = 42
    cell_size = max(max_px, 150)
    meta_height = 42
    gap = 16
    pad = 18
    column_count = max(1, columns)
    row_count = max(1, (len(photos) + column_count - 1) // column_count)
    card_w = cell_size
    card_h = cell_size + meta_height
    sheet_w = pad * 2 + column_count * card_w + (column_count - 1) * gap
    sheet_h = header_height + pad + row_count * card_h + (row_count - 1) * gap + footer_height
    sheet = Image.new("RGB", (sheet_w, sheet_h), color=DESIGN_BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, 14), "CONTACT SHEET", fill=DESIGN_AMBER, font=small)
    draw.text((pad, 34), title, fill=DESIGN_TEXT, font=font)
    draw.text((pad, 55), f"{len(photos)} photos · A1-E5 crop grid · reply: shift 03 to B2 / center 05 / tighten 06", fill=DESIGN_MUTED, font=small)

    for index, (photo, image, is_lead) in enumerate(photos):
        row = index // column_count
        col = index % column_count
        x0 = pad + col * (card_w + gap)
        y0 = header_height + row * (card_h + gap)
        _draw_photo_card(draw, sheet, photo, image, is_lead, x0, y0, cell_size, meta_height, font, small, mono)

    footer_y = sheet_h - footer_height + 8
    draw.text((pad, footer_y), "Crop feedback: shift 03 to B2 · center 05 · tighten 06 · loosen 09 · ratio 03 4:5", fill=DESIGN_MUTED, font=small)
    sheet.save(path, format="JPEG", quality=88)


def _draw_photo_card(
    draw: ImageDraw.ImageDraw,
    sheet: Image.Image,
    photo: ContactSheetPhoto,
    image: Image.Image,
    is_lead: bool,
    x0: int,
    y0: int,
    cell_size: int,
    meta_height: int,
    font: ImageFont.ImageFont,
    small: ImageFont.ImageFont,
    mono: ImageFont.ImageFont,
) -> None:
    outline = DESIGN_AMBER if is_lead else (46, 41, 34)
    draw.rounded_rectangle((x0 - 1, y0 - 1, x0 + cell_size + 1, y0 + cell_size + meta_height + 1), radius=10, fill=DESIGN_CARD, outline=outline, width=3 if is_lead else 1)
    draw.rectangle((x0, y0, x0 + cell_size, y0 + cell_size), fill=DESIGN_MAT)

    display = image.copy()
    display.thumbnail((cell_size, cell_size), Image.Resampling.LANCZOS)
    ix = x0 + (cell_size - display.width) // 2
    iy = y0 + (cell_size - display.height) // 2
    sheet.paste(display, (ix, iy))

    box = crop_box(photo)
    crop_rect = (
        ix + int(box.x * display.width),
        iy + int(box.y * display.height),
        ix + int((box.x + box.w) * display.width),
        iy + int((box.y + box.h) * display.height),
    )
    draw.rectangle(crop_rect, outline=DESIGN_AMBER, width=2)
    _draw_chess_grid(draw, crop_rect, chess_span(box), chess_from_anchor(photo.ax, photo.ay))

    chip = (x0 + 8, y0 + 8, x0 + 42, y0 + 30)
    draw.rounded_rectangle(chip, radius=7, fill=DESIGN_AMBER)
    draw.text((chip[0] + 7, chip[1] + 4), f"{photo.n:02d}", fill=DESIGN_MAT, font=mono)

    meta_y = y0 + cell_size + 8
    draw.text((x0 + 8, meta_y), _truncate(photo.file, 20), fill=DESIGN_TEXT, font=mono)
    meta = f"{ratio_label(photo.ratio)} · {chess_from_anchor(photo.ax, photo.ay)} · {tightness_label(photo.tight)}"
    draw.text((x0 + 8, meta_y + 18), meta, fill=DESIGN_MUTED, font=small)
    if is_lead:
        lead_x = x0 + cell_size - 44
        draw.rounded_rectangle((lead_x, meta_y + 15, x0 + cell_size - 8, meta_y + 33), radius=6, fill=DESIGN_AMBER)
        draw.text((lead_x + 6, meta_y + 19), "LEAD", fill=DESIGN_MAT, font=small)


def _draw_chess_grid(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], span: dict[str, int], anchor: str) -> None:
    x0, y0, x1, y1 = rect
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    active_col = ord(anchor[0]) - 65
    active_row = int(anchor[1]) - 1
    for row in range(5):
        for col in range(5):
            cx0 = x0 + int(col * w / 5)
            cy0 = y0 + int(row * h / 5)
            cx1 = x0 + int((col + 1) * w / 5)
            cy1 = y0 + int((row + 1) * h / 5)
            if col == active_col and row == active_row:
                draw.rectangle((cx0, cy0, cx1, cy1), outline=DESIGN_AMBER, width=2)
            elif span["c0"] <= col <= span["c1"] and span["r0"] <= row <= span["r1"]:
                draw.rectangle((cx0, cy0, cx1, cy1), outline=(118, 91, 43), width=1)
            else:
                draw.rectangle((cx0, cy0, cx1, cy1), outline=(80, 74, 64), width=1)


def _font(size: int) -> ImageFont.ImageFont:
    for font_name in ["Arial Unicode.ttf", "Arial.ttf", "Helvetica.ttc"]:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def _safe_artifact_stem(path: Path) -> str:
    stem = path.stem.strip().lower()
    safe = "".join(character if character.isalnum() else "-" for character in stem)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe or "image"

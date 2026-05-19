from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence


LARGE_REVIEW_ARTIFACT_MEDIA_COUNT = 120
BOUNDED_REVIEW_SAMPLE_COUNT = 24

from PIL import Image, ImageDraw, ImageFont, ImageOps

from post_relay.config import ReviewArtifactsConfig
from post_relay.contact_sheet_design import ContactSheetPhoto, chess_from_anchor, chess_span, crop_box, label_from_index, ratio_label, tightness_label
from post_relay.image_export_profiles import PROFILES, choose_treatment, export_image_for_profile, orientation
from post_relay.media_selection import DraftMediaPlanItem, build_draft_media_plan
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
    select_contact_sheet_path: Optional[str]
    crop_contact_sheet_path: Optional[str]

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
        if self.select_contact_sheet_path:
            lines.extend(
                [
                    "Stage 1 · Select:",
                    f"  {self.select_contact_sheet_path}",
                    "  selection only; no crop framing, grid, or lead marker",
                ]
            )
        if self.crop_contact_sheet_path:
            lines.extend(
                [
                    "Stage 2 · Crop:",
                    f"  {self.crop_contact_sheet_path}",
                ]
            )
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
    stage: str = "select",
) -> ReviewArtifactsPackage:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post {draft_id} was not found.")
    valid_stages = {"select", "crop", "all"}
    if stage not in valid_stages:
        raise ValueError(f"stage must be one of {', '.join(sorted(valid_stages))}")
    render_select = stage in {"select", "all"}
    render_crop = stage in {"crop", "all"}

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
    select_contact_sheet_path = artifact_root / "contact-sheet-select.png"
    crop_contact_sheet_path = artifact_root / "contact-sheet-crop.png"
    media_plan = build_draft_media_plan(connection, draft.id)
    included_media_items = [item for item in media_plan.items if item.include_status == "included"]
    single_media_post = len(included_media_items) == 1
    if render_crop and not single_media_post and not select_contact_sheet_path.exists():
        raise ValueError(
            "Stage 1 selection review sheet must exist before rendering Stage 2 crop artifacts; "
            "run drafts artifacts render --stage select first."
        )
    if render_crop and not single_media_post and draft.media_selection_confirmed_at is None:
        raise ValueError(
            "Stage 1 media selection must be confirmed before rendering Stage 2 crop artifacts; "
            "apply the selected media with drafts media-edit or discord dm-selection-apply first."
        )
    thumbnails_root = artifact_root / "thumbnails"
    thumbnails_root.mkdir(parents=True, exist_ok=True)
    for stale_thumbnail in thumbnails_root.glob("*.jpg"):
        stale_thumbnail.unlink()

    thumbnails: list[ThumbnailArtifact] = []
    contact_sheet_photos: list[tuple[ContactSheetPhoto, Image.Image, bool]] = []
    crop_contact_sheet_photos: list[tuple[ContactSheetPhoto, Image.Image, bool]] = []
    for index, item in enumerate(included_media_items, start=1):
        source = Path(item.local_file_path)
        thumbnail_path = thumbnails_root / f"{index:02d}-{_safe_artifact_stem(source)}.jpg"
        with Image.open(source) as image:
            full_image = ImageOps.exif_transpose(image).convert("RGB")
            thumbnail_image = full_image.copy()
            thumbnail_image.thumbnail(
                (config.thumbnail_max_px, config.thumbnail_max_px), Image.Resampling.LANCZOS
            )
            thumbnail_image.save(thumbnail_path, format="JPEG", quality=85)
            contact_photo = ContactSheetPhoto(
                n=item.review_number,
                file=source.name,
                src=source.as_posix(),
                w=full_image.width,
                h=full_image.height,
                ratio=item.crop_ratio,
                ax=item.crop_anchor_x,
                ay=item.crop_anchor_y,
                tight=item.crop_tightness,
            )
            is_lead = item.role == "primary"
            contact_sheet_photos.append((contact_photo, full_image.copy(), is_lead))
            crop_photo, crop_preview = _prepare_crop_preview(item, full_image)
            crop_contact_sheet_photos.append((crop_photo, crop_preview, is_lead))
            thumbnails.append(
                ThumbnailArtifact(
                    source_path=source.as_posix(),
                    local_path=thumbnail_path.as_posix(),
                    width=thumbnail_image.width,
                    height=thumbnail_image.height,
                )
            )

    rendered_select_contact_sheet_path = None
    rendered_crop_contact_sheet_path = None
    if render_select:
        _save_contact_sheet(
            contact_sheet_photos,
            select_contact_sheet_path,
            title=f"Post {draft.id}: {candidate_title}",
            mode="select",
            max_px=config.thumbnail_max_px,
            columns=config.contact_sheet_columns,
        )
        rendered_select_contact_sheet_path = select_contact_sheet_path.as_posix()
    if render_crop:
        _save_contact_sheet(
            crop_contact_sheet_photos,
            crop_contact_sheet_path,
            title=f"Post {draft.id}: {candidate_title}",
            mode="crop",
            max_px=config.thumbnail_max_px,
            columns=config.contact_sheet_columns,
        )
        rendered_crop_contact_sheet_path = crop_contact_sheet_path.as_posix()
    elif crop_contact_sheet_path.exists():
        crop_contact_sheet_path.unlink()
    if stage == "select":
        stale_final_preview_path = artifact_root / "final-post-preview.png"
        if stale_final_preview_path.exists():
            stale_final_preview_path.unlink()
    for _photo, image, _is_lead in contact_sheet_photos + crop_contact_sheet_photos:
        image.close()

    primary_contact_sheet_path = rendered_crop_contact_sheet_path or rendered_select_contact_sheet_path
    if primary_contact_sheet_path is None:
        raise ValueError("at least one review artifact stage must be rendered")
    return ReviewArtifactsPackage(
        draft_id=draft.id,
        candidate_title=candidate_title,
        artifact_root=artifact_root,
        thumbnails=thumbnails,
        contact_sheet_path=primary_contact_sheet_path,
        select_contact_sheet_path=rendered_select_contact_sheet_path,
        crop_contact_sheet_path=rendered_crop_contact_sheet_path,
    )


def _prepare_crop_preview(item: DraftMediaPlanItem, image: Image.Image) -> tuple[ContactSheetPhoto, Image.Image]:
    profile = PROFILES["feed_portrait_3x4"]
    source_orientation = orientation(image.width, image.height)
    treatment = choose_treatment(source_orientation, profile, "clean_mat")
    preview = export_image_for_profile(
        image,
        profile,
        treatment,
        crop_anchor_x=item.crop_anchor_x,
        crop_anchor_y=item.crop_anchor_y,
        crop_tightness=item.crop_tightness,
    )
    photo = ContactSheetPhoto(
        n=item.review_number,
        file=Path(item.local_file_path).name,
        src=item.local_file_path,
        w=preview.width,
        h=preview.height,
        ratio=profile.ratio,
        ax=0.5,
        ay=0.5,
        tight=1.0,
    )
    return photo, preview


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
DESIGN_PAPER = (20, 18, 15)
DESIGN_MAT = (12, 11, 9)
DESIGN_PAPER_SOFT = (26, 24, 20)
DESIGN_AMBER = (232, 168, 56)
DESIGN_AMBER_FG = (26, 23, 20)
DESIGN_TEXT = (236, 232, 222)
DESIGN_TEXT_SOFT = (184, 179, 167)
DESIGN_MUTED = (128, 122, 110)
DESIGN_MUTED_SOFT = (93, 88, 79)
DESIGN_LINE = (28, 26, 22)
DESIGN_LINE_STRONG = (42, 39, 34)
DESIGN_CROP_LINE = (240, 238, 232)
RENDER_SCALE = 2
PNG_DPI = (192, 192)


def _px(value: int | float) -> int:
    return int(round(value * RENDER_SCALE))


def _save_contact_sheet(
    photos: list[tuple[ContactSheetPhoto, Image.Image, bool]],
    path: Path,
    *,
    title: str,
    mode: str = "crop",
    max_px: int,
    columns: int,
) -> None:
    del max_px, columns  # The v2 Discord attachment design is fixed-width.
    path.parent.mkdir(parents=True, exist_ok=True)
    width = _px(720)
    header_h = _px(88)
    footer_h = _px(44)
    body_top_pad = _px(18)
    body_bottom_pad = _px(14)
    col_gap = _px(10)
    row_gap = _px(18)
    card_w = [_px(223), _px(223), _px(222)]
    cell_size = _px(223)
    meta_h = _px(56)
    row_count = max(1, (len(photos) + 2) // 3)
    body_h = body_top_pad + row_count * (cell_size + meta_h) + max(0, row_count - 1) * row_gap + body_bottom_pad
    height = header_h + body_h + footer_h
    sheet = Image.new("RGBA", (width, height), color=DESIGN_PAPER + (255,))
    draw = ImageDraw.Draw(sheet)
    eyebrow_font = _font(_px(10))
    title_font = _font(_px(17))
    sub_font = _font(_px(10))
    mono = _font(_px(11))
    small = _font(_px(10))

    _draw_header(
        draw,
        width,
        "CONTACT SHEET",
        f"{len(photos):02d} PHOTOS",
        "SELECT" if mode == "select" else "A1-E5 GRID",
        title,
        "SHOOT REVIEW",
        title_font,
        eyebrow_font,
        sub_font,
    )

    y_start = header_h + body_top_pad
    x_start = _px(16)
    for index, (photo, image, is_lead) in enumerate(photos):
        row = index // 3
        col = index % 3
        x0 = x_start + sum(card_w[:col]) + col * col_gap
        y0 = y_start + row * (cell_size + meta_h + row_gap)
        _draw_photo_card(draw, sheet, photo, image, is_lead, mode, x0, y0, card_w[col], cell_size, meta_h, title_font, small, mono)

    footer_y = height - footer_h
    draw.line((0, footer_y, width, footer_y), fill=DESIGN_LINE, width=_px(1))
    x = _px(24)
    y = footer_y + _px(12)
    footer_label = "REPLY" if mode == "select" else "CROP TALK"
    hints = ["keep A, C, D, G", "drop F", "include B too"] if mode == "select" else ["shift C to B2", "span D across A2-C4", "tighten F", "lead C"]
    draw.text((x, y), footer_label, fill=DESIGN_TEXT_SOFT, font=small)
    x += _text_w(draw, footer_label, small) + _px(14)
    for hint in hints:
        x = _draw_kbd(draw, x, y - _px(1), hint, small) + _px(10)
    sheet.save(path, format="PNG", optimize=True, dpi=PNG_DPI)


def _draw_header(draw: ImageDraw.ImageDraw, width: int, kind: str, count: str, accent: str, title: str, sub: str, title_font: ImageFont.ImageFont, eyebrow_font: ImageFont.ImageFont, sub_font: ImageFont.ImageFont) -> None:
    x = _px(24)
    y = _px(20)
    for text, fill in [(kind, DESIGN_MUTED), (count, DESIGN_MUTED), (accent, DESIGN_AMBER)]:
        draw.text((x, y), text, fill=fill, font=eyebrow_font)
        x += _text_w(draw, text, eyebrow_font) + _px(10)
        if text != accent:
            draw.ellipse((x, y + _px(7), x + _px(3), y + _px(10)), fill=DESIGN_MUTED_SOFT)
            x += _px(13)
    draw.text((_px(24), _px(41)), title, fill=DESIGN_TEXT, font=title_font)
    sub_w = _text_w(draw, sub, sub_font)
    draw.text((width - _px(24) - sub_w, _px(47)), sub, fill=DESIGN_MUTED, font=sub_font)
    draw.line((0, _px(87), width, _px(87)), fill=DESIGN_LINE, width=_px(1))


def _draw_photo_card(
    draw: ImageDraw.ImageDraw,
    sheet: Image.Image,
    photo: ContactSheetPhoto,
    image: Image.Image,
    is_lead: bool,
    mode: str,
    x0: int,
    y0: int,
    card_w: int,
    cell_size: int,
    meta_height: int,
    font: ImageFont.ImageFont,
    small: ImageFont.ImageFont,
    mono: ImageFont.ImageFont,
) -> None:
    del meta_height, font
    is_select = mode == "select"
    draw.rectangle((x0, y0, x0 + card_w, y0 + cell_size), fill=DESIGN_MAT)
    if is_lead and not is_select:
        draw.rectangle((x0, y0, x0 + card_w - _px(1), y0 + cell_size - _px(1)), outline=DESIGN_AMBER, width=_px(2))

    display = image.copy()
    display.thumbnail((card_w, cell_size), Image.Resampling.LANCZOS)
    ix = x0 + (card_w - display.width) // 2
    iy = y0 + (cell_size - display.height) // 2
    sheet.paste(display.convert("RGBA"), (ix, iy))

    if not is_select:
        box = crop_box(photo)
        crop_rect = (
            ix + int(box.x * display.width),
            iy + int(box.y * display.height),
            ix + int((box.x + box.w) * display.width),
            iy + int((box.y + box.h) * display.height),
        )
        _draw_crop_scrim(sheet, (ix, iy, ix + display.width, iy + display.height), crop_rect)
        draw.rectangle(crop_rect, outline=DESIGN_CROP_LINE, width=_px(2))
        _draw_chess_grid(draw, sheet, (ix, iy, ix + display.width, iy + display.height), chess_span(box), chess_from_anchor(photo.ax, photo.ay), small)

    chip = (x0 + _px(8), y0 + _px(8), x0 + _px(38), y0 + _px(32))
    draw.rounded_rectangle((chip[0], chip[1] + _px(2), chip[2], chip[3] + _px(2)), radius=_px(3), fill=(0, 0, 0, 90))
    draw.rounded_rectangle(chip, radius=_px(3), fill=DESIGN_AMBER)
    label = label_from_index(photo.n)
    _draw_centered(draw, chip, label, mono, DESIGN_AMBER_FG)
    if is_lead and not is_select:
        lead = "LEAD"
        w = _text_w(draw, lead, small) + _px(14)
        lead_box = (x0 + card_w - _px(8) - w, y0 + _px(8), x0 + card_w - _px(8), y0 + _px(26))
        draw.rounded_rectangle(lead_box, radius=_px(2), outline=DESIGN_AMBER, width=_px(1))
        _draw_centered(draw, lead_box, lead, small, DESIGN_AMBER)

    meta_y = y0 + cell_size + _px(10)
    file_fill = DESIGN_AMBER if is_lead and not is_select else DESIGN_TEXT
    lead_w = _text_w(draw, "▲ LEAD", small) + _px(6) if is_lead and not is_select else 0
    draw.text((x0 + _px(2), meta_y), _truncate_to_width(draw, photo.file, mono, card_w - _px(4) - lead_w), fill=file_fill, font=mono)
    if is_lead and not is_select:
        draw.text((x0 + card_w - lead_w + _px(4), meta_y + _px(2)), "▲ LEAD", fill=DESIGN_AMBER, font=small)
    if is_select:
        return
    attr_y = meta_y + _px(20)
    anchor = chess_from_anchor(photo.ax, photo.ay)
    draw.text((x0 + _px(2), attr_y), ratio_label(photo.ratio).upper(), fill=DESIGN_TEXT_SOFT, font=small)
    ax = x0 + _px(2) + _text_w(draw, ratio_label(photo.ratio).upper(), small) + _px(8)
    draw.text((ax, attr_y), "·", fill=DESIGN_MUTED_SOFT, font=small)
    ax += _px(12)
    draw.text((ax, attr_y), f"◎ {anchor}", fill=DESIGN_AMBER, font=small)
    ax += _text_w(draw, f"◎ {anchor}", small) + _px(8)
    draw.text((ax, attr_y), "·", fill=DESIGN_MUTED_SOFT, font=small)
    ax += _px(12)
    draw.text((ax, attr_y), tightness_label(photo.tight).upper(), fill=DESIGN_TEXT_SOFT, font=small)


def _draw_crop_scrim(sheet: Image.Image, photo_rect: tuple[int, int, int, int], crop_rect: tuple[int, int, int, int]) -> None:
    px0, py0, px1, py1 = photo_rect
    overlay = Image.new("RGBA", (px1 - px0, py1 - py0), (6, 5, 4, 140))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle((crop_rect[0] - px0, crop_rect[1] - py0, crop_rect[2] - px0, crop_rect[3] - py0), fill=(0, 0, 0, 0))
    sheet.alpha_composite(overlay, (px0, py0))


def _draw_chess_grid(draw: ImageDraw.ImageDraw, sheet: Image.Image, rect: tuple[int, int, int, int], span: dict[str, int], anchor: str, font: ImageFont.ImageFont) -> None:
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
            is_active = col == active_col and row == active_row
            is_in_crop = span["c0"] <= col <= span["c1"] and span["r0"] <= row <= span["r1"]
            if is_active or is_in_crop:
                alpha = 107 if is_active else 26
                fill_layer = Image.new("RGBA", (cx1 - cx0, cy1 - cy0), DESIGN_AMBER + (alpha,))
                sheet.alpha_composite(fill_layer, (cx0, cy0))
            draw.rectangle((cx0, cy0, cx1, cy1), outline=(255, 255, 255, 24 if is_active else 13), width=_px(1))
            if is_active:
                draw.rectangle((cx0, cy0, cx1, cy1), outline=DESIGN_AMBER, width=_px(2))
            label = f"{chr(65 + col)}{row + 1}"
            color = DESIGN_TEXT if is_active else (255, 255, 255, 128 if is_in_crop else 87)
            _draw_centered(draw, (cx0, cy0, cx1, cy1), label, font, color)


def _draw_kbd(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.ImageFont) -> int:
    w = _text_w(draw, text, font) + _px(12)
    box = (x, y, x + w, y + _px(19))
    draw.rounded_rectangle(box, radius=_px(3), fill=DESIGN_PAPER_SOFT, outline=DESIGN_LINE_STRONG, width=_px(1))
    _draw_centered(draw, box, text, font, DESIGN_TEXT_SOFT)
    return x + w


def _draw_centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.ImageFont, fill) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = box[0] + ((box[2] - box[0]) - tw) // 2
    y = box[1] + ((box[3] - box[1]) - th) // 2 - bbox[1]
    draw.text((x, y), text, fill=fill, font=font)


def _font(size: int) -> ImageFont.ImageFont:
    for font_name in [
        "/Library/Fonts/SF-Mono-Semibold.otf",
        "/Library/Fonts/SF-Mono-Medium.otf",
        "/Library/Fonts/SF-Mono-Regular.otf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _truncate_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if _text_w(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    for length in range(len(text) - 1, 0, -1):
        candidate = text[:length] + ellipsis
        if _text_w(draw, candidate, font) <= max_width:
            return candidate
    return ellipsis


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"

def _safe_artifact_stem(path: Path) -> str:
    stem = path.stem.strip().lower()
    safe = "".join(character if character.isalnum() else "-" for character in stem)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe or "image"

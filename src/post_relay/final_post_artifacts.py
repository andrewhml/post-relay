from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from post_relay.config import ReviewArtifactsConfig
from post_relay.contact_sheet_design import ContactSheetPhoto, crop_box, label_from_index, ratio_label
from post_relay.final_publish_preview import compose_final_meta_caption
from post_relay.media_selection import build_draft_media_plan
from post_relay.repository import get_draft, get_draft_location_tag

BG = (12, 11, 9)
PAPER = (20, 18, 15)
MAT = (12, 11, 9)
AMBER = (232, 168, 56)
AMBER_FG = (26, 23, 20)
TEXT = (236, 232, 222)
TEXT_SOFT = (184, 179, 167)
MUTED = (128, 122, 110)
MUTED_SOFT = (93, 88, 79)
LINE = (28, 26, 22)
RENDER_SCALE = 2
PNG_DPI = (192, 192)


def _px(value: int | float) -> int:
    return int(round(value * RENDER_SCALE))


@dataclass(frozen=True)
class FinalPostPreviewArtifactPackage:
    draft_id: int
    preview_path: str
    ordered_files: list[str]
    ratio_label: str
    caption: str
    metadata_tags: list[str]

    def to_text(self) -> str:
        lines = [
            "Final Post Preview Artifact",
            f"Post ID: {self.draft_id}",
            f"Locked ratio: {self.ratio_label}",
            "Preview image:",
            f"  {self.preview_path}",
            "Carousel order:",
        ]
        lines.extend(f"  {index}. {filename}" for index, filename in enumerate(self.ordered_files, start=1))
        if self.metadata_tags:
            lines.append("Metadata:")
            lines.extend(f"  {tag}" for tag in self.metadata_tags)
        if self.caption:
            lines.extend(["Caption preview:", self.caption])
        lines.append("No Discord, R2, or Meta network calls were made.")
        return "\n".join(lines)


def render_final_post_preview_artifact(
    connection,
    draft_id: int,
    config: ReviewArtifactsConfig,
    *,
    ratio: float = 0.8,
) -> FinalPostPreviewArtifactPackage:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise ValueError(f"Post #{draft_id} was not found")
    plan = build_draft_media_plan(connection, draft_id)
    items = [item for item in plan.items if item.include_status == "included"]
    artifact_root = config.root / f"draft-{draft_id}"
    artifact_root.mkdir(parents=True, exist_ok=True)
    path = artifact_root / "final-post-preview.png"
    caption = compose_final_meta_caption(draft)
    metadata_tags = _metadata_tags(connection, draft, ratio_label(ratio))

    width = _px(720)
    header_h = _px(88)
    side_pad = _px(24)
    gap = _px(12)
    slide_w = int((width - side_pad * 2 - max(0, len(items) - 1) * gap) / max(1, len(items)))
    slide_h = int(slide_w / ratio)
    body_h = _px(22) + slide_h + _px(36) + _px(8)
    dots_h = _px(29)
    metadata_h = _px(42) if metadata_tags else 0
    caption_h = _px(1) + metadata_h + _px(14) + (_px(54) if caption else _px(18)) + _px(20)
    height = header_h + body_h + dots_h + caption_h
    canvas = Image.new("RGBA", (width, height), PAPER + (255,))
    draw = ImageDraw.Draw(canvas)
    title_font = _font(_px(17))
    small = _font(_px(10))
    mono = _font(_px(11))
    caption_font = _font(_px(13))

    _draw_header(draw, width, len(items), ratio_label(ratio), label_from_index(items[0].review_number) if items else "-", title_font, small)

    ordered_files: list[str] = []
    y = header_h + _px(22)
    for index, item in enumerate(items):
        source = Path(item.local_file_path)
        ordered_files.append(source.name)
        x = side_pad + index * (slide_w + gap)
        with Image.open(source) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
        photo = ContactSheetPhoto(
            n=item.review_number,
            file=source.name,
            src=source.as_posix(),
            w=image.width,
            h=image.height,
            ratio=item.crop_ratio,
            ax=item.crop_anchor_x,
            ay=item.crop_anchor_y,
            tight=item.crop_tightness,
        )
        _draw_slide(canvas, draw, image, photo, x, y, slide_w, slide_h, ratio, index, len(items), small, mono)

    dots_y = y + slide_h + _px(36)
    _draw_dots(draw, width, len(items), dots_y)
    caption_y = header_h + body_h + dots_h
    draw.line((0, caption_y, width, caption_y), fill=LINE, width=_px(1))
    body_text_y = caption_y + _px(14)
    if metadata_tags:
        draw.text((side_pad, body_text_y + _px(3)), "META", fill=MUTED, font=small)
        tag_x = side_pad + _px(82)
        for tag in metadata_tags:
            tag_x = _draw_metadata_tag(draw, tag_x, body_text_y, tag, small) + _px(8)
            if tag_x > width - side_pad - _px(80):
                break
        body_text_y += metadata_h
    draw.text((side_pad, body_text_y), "CAPTION", fill=MUTED, font=small)
    if caption:
        _draw_wrapped_text(draw, caption.replace("\n", " "), side_pad + _px(82), body_text_y - _px(2), width - side_pad - (side_pad + _px(82)), caption_font, TEXT_SOFT, line_h=_px(18), max_lines=3)
    canvas.save(path, format="PNG", optimize=True, dpi=PNG_DPI)
    return FinalPostPreviewArtifactPackage(
        draft_id=draft_id,
        preview_path=path.as_posix(),
        ordered_files=ordered_files,
        ratio_label=ratio_label(ratio),
        caption=caption,
        metadata_tags=metadata_tags,
    )


def _draw_header(draw: ImageDraw.ImageDraw, width: int, count: int, ratio_text: str, lead_label: str, title_font: ImageFont.ImageFont, small: ImageFont.ImageFont) -> None:
    x = _px(24)
    y = _px(20)
    for text, fill in [("CAROUSEL PREVIEW", MUTED), (f"{count:02d} SLIDES", MUTED), (ratio_text.upper(), AMBER)]:
        draw.text((x, y), text, fill=fill, font=small)
        x += _text_w(draw, text, small) + _px(10)
        if fill != AMBER:
            draw.ellipse((x, y + _px(7), x + _px(3), y + _px(10)), fill=MUTED_SOFT)
            x += _px(13)
    draw.text((_px(24), _px(41)), "Final post · ordered", fill=TEXT, font=title_font)
    sub = f"LEAD {lead_label}"
    sw = _text_w(draw, sub, small)
    draw.text((width - _px(24) - sw, _px(47)), sub[:-len(lead_label)], fill=MUTED, font=small)
    draw.text((width - _px(24) - _text_w(draw, lead_label, small), _px(47)), lead_label, fill=AMBER, font=small)
    draw.line((0, _px(87), width, _px(87)), fill=LINE, width=_px(1))


def _draw_slide(canvas: Image.Image, draw: ImageDraw.ImageDraw, image: Image.Image, photo: ContactSheetPhoto, x: int, y: int, w: int, h: int, ratio: float, index: int, total: int, small: ImageFont.ImageFont, mono: ImageFont.ImageFont) -> None:
    draw.rectangle((x, y, x + w, y + h), fill=MAT)
    box = crop_box(photo, override_ratio=ratio)
    left = int(box.x * image.width)
    top = int(box.y * image.height)
    right = int((box.x + box.w) * image.width)
    bottom = int((box.y + box.h) * image.height)
    cropped = image.crop((left, top, right, bottom))
    cropped = ImageOps.fit(cropped, (w, h), method=Image.Resampling.LANCZOS)
    canvas.paste(cropped.convert("RGBA"), (x, y))
    if index == 0:
        draw.rectangle((x, y, x + w - _px(1), y + h - _px(1)), outline=AMBER, width=_px(2))
        lead_box = (x + _px(6), y + _px(6), x + _px(59), y + _px(28))
        draw.rounded_rectangle(lead_box, radius=_px(2), fill=AMBER)
        _draw_centered(draw, lead_box, "LEAD", small, AMBER_FG)
    chip = f"{index + 1} / {total}"
    chip_w = _text_w(draw, chip, mono) + _px(14)
    chip_box = (x + w - chip_w - _px(6), y + h - _px(29), x + w - _px(6), y + h - _px(6))
    draw.rounded_rectangle(chip_box, radius=_px(3), fill=(64, 60, 54), outline=(110, 104, 94), width=_px(1))
    _draw_centered(draw, chip_box, chip, mono, TEXT)
    meta = f"{label_from_index(photo.n)} {photo.file}"
    draw.text((x, y + h + _px(8)), _truncate_to_width(draw, meta, mono, w), fill=MUTED, font=mono)
    draw.text((x, y + h + _px(8)), label_from_index(photo.n), fill=AMBER, font=mono)


def _metadata_tags(connection, draft, ratio_text: str) -> list[str]:
    tags: list[str] = []
    location_tag = get_draft_location_tag(connection, draft.id)
    if location_tag is not None and location_tag.status == "resolved":
        tags.append(f"LOCATION · {location_tag.name}")
    elif draft.location_text:
        tags.append(f"LOCATION · {draft.location_text}")
    tags.append(f"TYPE · {draft.post_type.replace('_', ' ').upper()}")
    tags.append(f"RATIO · {ratio_text}")
    return tags


def _draw_metadata_tag(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.ImageFont) -> int:
    w = _text_w(draw, text, font) + _px(16)
    box = (x, y, x + w, y + _px(24))
    draw.rounded_rectangle((box[0], box[1] + _px(2), box[2], box[3] + _px(2)), radius=_px(3), fill=(0, 0, 0, 80))
    draw.rounded_rectangle(box, radius=_px(3), fill=(26, 24, 20), outline=(42, 39, 34), width=_px(1))
    _draw_centered(draw, box, text, font, TEXT_SOFT)
    return x + w


def _draw_dots(draw: ImageDraw.ImageDraw, width: int, count: int, y: int) -> None:
    if count <= 0:
        return
    total_w = _px(18) + max(0, count - 1) * (_px(5) + _px(5))
    x = (width - total_w) // 2
    draw.rounded_rectangle((x, y, x + _px(18), y + _px(5)), radius=_px(3), fill=AMBER)
    x += _px(23)
    for _ in range(1, count):
        draw.ellipse((x, y, x + _px(5), y + _px(5)), fill=MUTED_SOFT)
        x += _px(10)


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, max_w: int, font: ImageFont.ImageFont, fill, *, line_h: int, max_lines: int) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if _text_w(draw, candidate, font) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    for i, line in enumerate(lines[:max_lines]):
        if i == max_lines - 1 and len(lines) == max_lines and len(words) > len(" ".join(lines).split()):
            line = _truncate_to_width(draw, line + "…", font, max_w)
        draw.text((x, y + i * line_h), line, fill=fill, font=font)


def _draw_centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.ImageFont, fill) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((box[0] + ((box[2] - box[0]) - tw) // 2, box[1] + ((box[3] - box[1]) - th) // 2 - bbox[1]), text, fill=fill, font=font)


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
    for length in range(len(text) - 1, 0, -1):
        candidate = text[:length] + "…"
        if _text_w(draw, candidate, font) <= max_width:
            return candidate
    return "…"


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"

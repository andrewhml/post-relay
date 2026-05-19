from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from post_relay.config import ReviewArtifactsConfig
from post_relay.contact_sheet_design import ContactSheetPhoto, crop_box, ratio_label
from post_relay.final_publish_preview import compose_final_meta_caption
from post_relay.media_selection import build_draft_media_plan
from post_relay.repository import get_draft

BG = (20, 18, 15)
MAT = (12, 11, 9)
CARD = (28, 25, 21)
AMBER = (232, 168, 56)
TEXT = (239, 232, 220)
MUTED = (155, 143, 124)


@dataclass(frozen=True)
class FinalPostPreviewArtifactPackage:
    draft_id: int
    preview_path: str
    ordered_files: list[str]
    ratio_label: str
    caption: str

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
    path = artifact_root / "final-post-preview.jpg"
    caption = compose_final_meta_caption(draft)

    slide_w = 130
    slide_h = int(slide_w / ratio)
    pad = 18
    gap = 12
    header_h = 66
    caption_h = 76 if caption else 36
    width = max(320, pad * 2 + len(items) * slide_w + max(0, len(items) - 1) * gap)
    height = header_h + slide_h + 50 + caption_h
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    font = _font(13)
    small = _font(10)
    mono = _font(11)
    draw.text((pad, 14), "FINAL POST PREVIEW", fill=AMBER, font=small)
    draw.text((pad, 34), f"Post {draft_id} · {len(items)} slide carousel · {ratio_label(ratio)} locked crop", fill=TEXT, font=font)

    ordered_files: list[str] = []
    y = header_h
    for index, item in enumerate(items):
        source = Path(item.local_file_path)
        ordered_files.append(source.name)
        x = pad + index * (slide_w + gap)
        with Image.open(source) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
        photo = ContactSheetPhoto(
            n=index + 1,
            file=source.name,
            src=source.as_posix(),
            w=image.width,
            h=image.height,
            ratio=item.crop_ratio,
            ax=item.crop_anchor_x,
            ay=item.crop_anchor_y,
            tight=item.crop_tightness,
        )
        _draw_slide(canvas, draw, image, photo, x, y, slide_w, slide_h, ratio, index == 0, small, mono)

    dots_y = y + slide_h + 18
    for index in range(len(items)):
        dot_x = pad + index * 14
        if index == 0:
            draw.rounded_rectangle((dot_x, dots_y, dot_x + 20, dots_y + 7), radius=4, fill=AMBER)
        else:
            draw.ellipse((dot_x, dots_y, dot_x + 7, dots_y + 7), fill=(92, 85, 75))
    if caption:
        draw.text((pad, dots_y + 22), _truncate(caption.replace("\n", " "), 110), fill=TEXT, font=small)
    canvas.save(path, format="JPEG", quality=88)
    return FinalPostPreviewArtifactPackage(
        draft_id=draft_id,
        preview_path=path.as_posix(),
        ordered_files=ordered_files,
        ratio_label=ratio_label(ratio),
        caption=caption,
    )


def _draw_slide(canvas: Image.Image, draw: ImageDraw.ImageDraw, image: Image.Image, photo: ContactSheetPhoto, x: int, y: int, w: int, h: int, ratio: float, lead: bool, small: ImageFont.ImageFont, mono: ImageFont.ImageFont) -> None:
    draw.rounded_rectangle((x - 1, y - 1, x + w + 1, y + h + 1), radius=10, fill=CARD, outline=AMBER if lead else (46, 41, 34), width=3 if lead else 1)
    box = crop_box(photo, override_ratio=ratio)
    left = int(box.x * image.width)
    top = int(box.y * image.height)
    right = int((box.x + box.w) * image.width)
    bottom = int((box.y + box.h) * image.height)
    cropped = image.crop((left, top, right, bottom))
    cropped = ImageOps.fit(cropped, (w, h), method=Image.Resampling.LANCZOS)
    canvas.paste(cropped, (x, y))
    if lead:
        draw.rounded_rectangle((x + 8, y + 8, x + 48, y + 28), radius=7, fill=AMBER)
        draw.text((x + 14, y + 12), "LEAD", fill=MAT, font=small)
    draw.rectangle((x, y + h - 20, x + w, y + h), fill=MAT)
    draw.text((x + 6, y + h - 17), f"{photo.n:02d} {_truncate(photo.file, 14)}", fill=TEXT, font=mono)


def _font(size: int) -> ImageFont.ImageFont:
    for font_name in ["Arial Unicode.ttf", "Arial.ttf", "Helvetica.ttc"]:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"

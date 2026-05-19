from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageOps

from post_relay.contact_sheet_design import ContactSheetPhoto, crop_box


@dataclass(frozen=True)
class ImageExportProfile:
    name: str
    width: int
    height: int

    @property
    def ratio(self) -> float:
        return self.width / self.height


PROFILES = {
    "feed_portrait_3x4": ImageExportProfile("feed_portrait_3x4", 1080, 1440),
    "feed_portrait_4x5": ImageExportProfile("feed_portrait_4x5", 1080, 1350),
    "feed_square": ImageExportProfile("feed_square", 1080, 1080),
}

LANDSCAPE_TREATMENTS = {"clean_mat"}


def choose_treatment(source_orientation: str, profile: ImageExportProfile, landscape_treatment: str) -> str:
    target_orientation = orientation(profile.width, profile.height)
    if source_orientation == "landscape" and target_orientation == "portrait":
        return landscape_treatment
    return "center_crop"


def export_image_for_profile(
    image: Image.Image,
    profile: ImageExportProfile,
    treatment: str,
    *,
    crop_anchor_x: float = 0.5,
    crop_anchor_y: float = 0.5,
    crop_tightness: float = 1.0,
) -> Image.Image:
    target = (profile.width, profile.height)
    if treatment == "clean_mat":
        contained = ImageOps.contain(image, target, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", target, color="white")
        x = (target[0] - contained.width) // 2
        y = (target[1] - contained.height) // 2
        canvas.paste(contained, (x, y))
        return canvas

    preview_photo = ContactSheetPhoto(
        n=1,
        file="preview",
        src="",
        w=image.width,
        h=image.height,
        ratio=profile.ratio,
        ax=crop_anchor_x,
        ay=crop_anchor_y,
        tight=crop_tightness,
    )
    box = crop_box(preview_photo)
    crop_rect = (
        int(round(box.x * image.width)),
        int(round(box.y * image.height)),
        int(round((box.x + box.w) * image.width)),
        int(round((box.y + box.h) * image.height)),
    )
    cropped = image.crop(crop_rect)
    return cropped.resize(target, Image.Resampling.LANCZOS)


def orientation(width: int, height: int) -> str:
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"

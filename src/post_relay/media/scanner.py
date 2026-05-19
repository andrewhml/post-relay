from __future__ import annotations

from dataclasses import dataclass
from math import gcd
from pathlib import Path
from typing import Iterable, List, Optional, TypedDict

from PIL import Image, UnidentifiedImageError

from post_relay.config import PostRelayConfig, PhotoSource


class LocalImageMetadata(TypedDict):
    width: Optional[int]
    height: Optional[int]
    orientation: str
    aspect_ratio: Optional[str]
    date_taken: Optional[str]
    camera_model: Optional[str]
    lens_model: Optional[str]


@dataclass(frozen=True)
class ScannedMedia:
    path: Path
    source_name: str
    source_type: str
    source_confidence: float
    inferred_year: Optional[int]
    width: Optional[int] = None
    height: Optional[int] = None
    orientation: str = "unknown"
    aspect_ratio: Optional[str] = None
    date_taken: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None

    @property
    def has_local_metadata(self) -> bool:
        return any(
            value is not None
            for value in (
                self.width,
                self.height,
                self.date_taken,
                self.camera_model,
                self.lens_model,
            )
        )


def scan_photo_sources(config: PostRelayConfig) -> List[ScannedMedia]:
    supported_extensions = {extension.lower() for extension in config.supported_image_extensions}
    scanned: List[ScannedMedia] = []

    for source in config.photo_sources:
        if not source.enabled:
            continue
        scanned.extend(_scan_source(source, supported_extensions))

    return sorted(scanned, key=lambda item: item.path.as_posix())


def _scan_source(source: PhotoSource, supported_extensions: Iterable[str]) -> Iterable[ScannedMedia]:
    supported = set(supported_extensions)
    if not source.root.exists():
        return []

    results: List[ScannedMedia] = []
    for path in source.root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in supported:
            continue
        metadata = _read_local_image_metadata(path)
        results.append(
            ScannedMedia(
                path=path,
                source_name=source.name,
                source_type=source.source_type,
                source_confidence=source.reliability_score,
                inferred_year=_infer_year_from_path(path, source.root),
                **metadata,
            )
        )
    return results


def _infer_year_from_path(path: Path, root: Path) -> Optional[int]:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts

    for part in relative_parts[:-1]:
        if len(part) == 4 and part.isdigit() and part.startswith("20"):
            return int(part)
    return None


def _read_local_image_metadata(path: Path) -> LocalImageMetadata:
    try:
        with Image.open(path) as image:
            width, height = image.size
            exif = image.getexif()
    except (OSError, UnidentifiedImageError):
        return {
            "width": None,
            "height": None,
            "orientation": "unknown",
            "aspect_ratio": None,
            "date_taken": None,
            "camera_model": None,
            "lens_model": None,
        }

    return {
        "width": width,
        "height": height,
        "orientation": _classify_orientation(width, height),
        "aspect_ratio": _format_aspect_ratio(width, height),
        "date_taken": _first_exif_value(exif, (36867, 306)),  # DateTimeOriginal, DateTime
        "camera_model": _first_exif_value(exif, (272,)),  # Model
        "lens_model": _first_exif_value(exif, (42036,)),  # LensModel
    }


def _classify_orientation(width: int, height: int) -> str:
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def _format_aspect_ratio(width: int, height: int) -> str:
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _first_exif_value(exif, tag_ids: tuple[int, ...]) -> Optional[str]:
    for tag_id in tag_ids:
        value = exif.get(tag_id)
        if value:
            return str(value).strip()
    return None

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from post_relay.config import PostRelayConfig, PhotoSource


@dataclass(frozen=True)
class ScannedMedia:
    path: Path
    source_name: str
    source_type: str
    source_confidence: float
    inferred_year: Optional[int]


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
        results.append(
            ScannedMedia(
                path=path,
                source_name=source.name,
                source_type=source.source_type,
                source_confidence=source.reliability_score,
                inferred_year=_infer_year_from_path(path, source.root),
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

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from post_relay.repository import create_candidate_group, list_photos_for_candidates


@dataclass(frozen=True)
class CandidateBuildResult:
    created_count: int
    considered_photo_count: int


def build_candidate_groups(connection) -> CandidateBuildResult:
    """Build initial reviewable candidate groups from indexed local photos.

    The MVP groups photos by their immediate parent folder inside a source/year
    hierarchy. This maps naturally to Lightroom export folders such as
    ``processed/2023/kyoto/*.jpg`` and gives Andrew one reviewable travel set per
    folder.
    """
    photos = list_photos_for_candidates(connection)
    grouped = defaultdict(list)
    for photo in photos:
        source_folder = _candidate_source_folder(Path(photo.local_file_path))
        grouped[(photo.source_name, source_folder)].append(photo)

    created_count = 0
    for (source_name, source_folder), group_photos in grouped.items():
        group_photos = sorted(group_photos, key=lambda photo: photo.local_file_path)
        photo_count = len(group_photos)
        post_type = "carousel" if photo_count > 1 else "single_image"
        confidence = sum(photo.source_confidence for photo in group_photos) / photo_count
        source_year = _common_year([photo.inferred_year for photo in group_photos])
        group_id = create_candidate_group(
            connection,
            title=_title_from_source_folder(source_folder),
            source_name=source_name,
            source_folder=source_folder,
            source_year=source_year,
            post_type_recommendation=post_type,
            confidence=confidence,
            reason=f"{photo_count} indexed photo{'s' if photo_count != 1 else ''} from the same source folder.",
            photo_ids=[photo.id for photo in group_photos],
        )
        if group_id is not None:
            created_count += 1

    connection.commit()
    return CandidateBuildResult(created_count=created_count, considered_photo_count=len(photos))


def _candidate_source_folder(path: Path) -> str:
    parent = path.parent
    if parent.parent == parent:
        return parent.name
    return f"{parent.parent.name}/{parent.name}"


def _title_from_source_folder(source_folder: str) -> str:
    return source_folder.replace("/", " / ")


def _common_year(years: list[int | None]) -> int | None:
    known_years = {year for year in years if year is not None}
    if len(known_years) == 1:
        return known_years.pop()
    return None

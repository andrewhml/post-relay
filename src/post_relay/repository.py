from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from post_relay.config import PhotoSource
from post_relay.media.scanner import ScannedMedia


@dataclass(frozen=True)
class LibraryStats:
    total_photos: int
    by_source: Dict[str, int]
    by_year: Dict[Optional[int], int]


def upsert_photo_source(connection, source: PhotoSource) -> int:
    connection.execute(
        """
        insert into photo_sources (name, root, source_type, reliability_score, enabled)
        values (?, ?, ?, ?, ?)
        on conflict(name) do update set
            root = excluded.root,
            source_type = excluded.source_type,
            reliability_score = excluded.reliability_score,
            enabled = excluded.enabled
        """,
        (
            source.name,
            source.root.as_posix(),
            source.source_type,
            source.reliability_score,
            1 if source.enabled else 0,
        ),
    )
    row = connection.execute(
        "select id from photo_sources where name = ?", (source.name,)
    ).fetchone()
    return int(row[0])


def upsert_scanned_photo(connection, scanned: ScannedMedia, source_id: int) -> None:
    connection.execute(
        """
        insert into photos (
            source_id,
            source_name,
            local_file_path,
            source_type,
            source_confidence,
            inferred_year,
            processed_status
        )
        values (?, ?, ?, ?, ?, ?, 'processed')
        on conflict(local_file_path) do update set
            source_id = excluded.source_id,
            source_name = excluded.source_name,
            source_type = excluded.source_type,
            source_confidence = excluded.source_confidence,
            inferred_year = excluded.inferred_year,
            indexed_at = current_timestamp
        """,
        (
            source_id,
            scanned.source_name,
            scanned.path.as_posix(),
            scanned.source_type,
            scanned.source_confidence,
            scanned.inferred_year,
        ),
    )


def get_library_stats(connection) -> LibraryStats:
    total = connection.execute("select count(*) from photos").fetchone()[0]
    by_source = {
        row[0]: row[1]
        for row in connection.execute(
            "select source_name, count(*) from photos group by source_name order by source_name"
        )
    }
    by_year = {
        row[0]: row[1]
        for row in connection.execute(
            "select inferred_year, count(*) from photos group by inferred_year order by inferred_year"
        )
    }
    return LibraryStats(total_photos=total, by_source=by_source, by_year=by_year)

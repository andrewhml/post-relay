from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from post_relay.config import PhotoSource
from post_relay.media.scanner import ScannedMedia


@dataclass(frozen=True)
class LibraryStats:
    total_photos: int
    by_source: Dict[str, int]
    by_year: Dict[Optional[int], int]


@dataclass(frozen=True)
class PhotoForCandidate:
    id: int
    source_name: str
    local_file_path: str
    source_confidence: float
    inferred_year: Optional[int]


@dataclass(frozen=True)
class CandidateGroupRecord:
    id: int
    title: str
    source_name: str
    source_folder: str
    source_year: Optional[int]
    post_type_recommendation: str
    confidence: float
    reason: str
    status: str
    photo_count: int


@dataclass(frozen=True)
class DraftRecord:
    id: int
    candidate_group_id: int
    post_type: str
    caption: Optional[str]
    hashtags_json: Optional[str]
    location_text: Optional[str]
    alt_text: Optional[str]
    status: str
    scheduled_for: Optional[str]


@dataclass(frozen=True)
class ContextQuestionRecord:
    id: int
    draft_id: int
    field_name: str
    question_text: str
    status: str
    answer_text: Optional[str]


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


def list_photos_for_candidates(connection) -> list[PhotoForCandidate]:
    rows = connection.execute(
        """
        select id, source_name, local_file_path, source_confidence, inferred_year
        from photos
        where processed_status = 'processed'
        order by source_name, local_file_path
        """
    ).fetchall()
    return [
        PhotoForCandidate(
            id=int(row[0]),
            source_name=row[1],
            local_file_path=row[2],
            source_confidence=float(row[3]),
            inferred_year=row[4],
        )
        for row in rows
    ]


def create_candidate_group(
    connection,
    *,
    title: str,
    source_name: str,
    source_folder: str,
    source_year: Optional[int],
    post_type_recommendation: str,
    confidence: float,
    reason: str,
    photo_ids: Sequence[int],
) -> Optional[int]:
    cursor = connection.execute(
        """
        insert or ignore into candidate_groups (
            title,
            source_name,
            source_folder,
            source_year,
            post_type_recommendation,
            confidence,
            reason
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            source_name,
            source_folder,
            source_year,
            post_type_recommendation,
            confidence,
            reason,
        ),
    )
    if cursor.rowcount == 0:
        return None

    group_id = int(cursor.lastrowid)
    for sort_order, photo_id in enumerate(photo_ids, start=1):
        connection.execute(
            """
            insert into candidate_group_items (group_id, photo_id, sort_order, role)
            values (?, ?, ?, ?)
            """,
            (group_id, photo_id, sort_order, "primary" if sort_order == 1 else "support"),
        )
    return group_id


def list_candidate_groups(connection) -> list[CandidateGroupRecord]:
    rows = connection.execute(
        """
        select
            candidate_groups.id,
            candidate_groups.title,
            candidate_groups.source_name,
            candidate_groups.source_folder,
            candidate_groups.source_year,
            candidate_groups.post_type_recommendation,
            candidate_groups.confidence,
            candidate_groups.reason,
            candidate_groups.status,
            count(candidate_group_items.photo_id) as photo_count
        from candidate_groups
        left join candidate_group_items on candidate_group_items.group_id = candidate_groups.id
        group by candidate_groups.id
        order by candidate_groups.source_name, candidate_groups.source_folder
        """
    ).fetchall()
    return [
        CandidateGroupRecord(
            id=int(row[0]),
            title=row[1],
            source_name=row[2],
            source_folder=row[3],
            source_year=row[4],
            post_type_recommendation=row[5],
            confidence=float(row[6]),
            reason=row[7],
            status=row[8],
            photo_count=int(row[9]),
        )
        for row in rows
    ]


def get_candidate_group(connection, candidate_group_id: int) -> Optional[CandidateGroupRecord]:
    rows = connection.execute(
        """
        select
            candidate_groups.id,
            candidate_groups.title,
            candidate_groups.source_name,
            candidate_groups.source_folder,
            candidate_groups.source_year,
            candidate_groups.post_type_recommendation,
            candidate_groups.confidence,
            candidate_groups.reason,
            candidate_groups.status,
            count(candidate_group_items.photo_id) as photo_count
        from candidate_groups
        left join candidate_group_items on candidate_group_items.group_id = candidate_groups.id
        where candidate_groups.id = ?
        group by candidate_groups.id
        """,
        (candidate_group_id,),
    ).fetchall()
    if not rows:
        return None
    row = rows[0]
    return CandidateGroupRecord(
        id=int(row[0]),
        title=row[1],
        source_name=row[2],
        source_folder=row[3],
        source_year=row[4],
        post_type_recommendation=row[5],
        confidence=float(row[6]),
        reason=row[7],
        status=row[8],
        photo_count=int(row[9]),
    )


def create_draft_record(
    connection,
    *,
    candidate_group_id: int,
    post_type: str,
    status: str,
) -> DraftRecord:
    connection.execute(
        """
        insert or ignore into drafts (candidate_group_id, post_type, status)
        values (?, ?, ?)
        """,
        (candidate_group_id, post_type, status),
    )
    row = connection.execute(
        """
        select id, candidate_group_id, post_type, caption, hashtags_json,
               location_text, alt_text, status, scheduled_for
        from drafts
        where candidate_group_id = ?
        """,
        (candidate_group_id,),
    ).fetchone()
    return _draft_from_row(row)


def get_draft(connection, draft_id: int) -> Optional[DraftRecord]:
    row = connection.execute(
        """
        select id, candidate_group_id, post_type, caption, hashtags_json,
               location_text, alt_text, status, scheduled_for
        from drafts
        where id = ?
        """,
        (draft_id,),
    ).fetchone()
    if row is None:
        return None
    return _draft_from_row(row)


def list_drafts(connection) -> list[DraftRecord]:
    rows = connection.execute(
        """
        select id, candidate_group_id, post_type, caption, hashtags_json,
               location_text, alt_text, status, scheduled_for
        from drafts
        order by id
        """
    ).fetchall()
    return [_draft_from_row(row) for row in rows]


def list_candidate_group_photo_paths(connection, candidate_group_id: int) -> list[str]:
    rows = connection.execute(
        """
        select photos.local_file_path
        from candidate_group_items
        join photos on photos.id = candidate_group_items.photo_id
        where candidate_group_items.group_id = ?
        order by candidate_group_items.sort_order, photos.local_file_path
        """,
        (candidate_group_id,),
    ).fetchall()
    return [row[0] for row in rows]


def create_context_question(
    connection,
    *,
    draft_id: int,
    field_name: str,
    question_text: str,
    status: str = "unresolved",
) -> ContextQuestionRecord:
    connection.execute(
        """
        insert or ignore into context_questions (draft_id, field_name, question_text, status)
        values (?, ?, ?, ?)
        """,
        (draft_id, field_name, question_text, status),
    )
    row = connection.execute(
        """
        select id, draft_id, field_name, question_text, status, answer_text
        from context_questions
        where draft_id = ? and field_name = ?
        """,
        (draft_id, field_name),
    ).fetchone()
    return _context_question_from_row(row)


def list_context_questions(connection, draft_id: int) -> list[ContextQuestionRecord]:
    rows = connection.execute(
        """
        select id, draft_id, field_name, question_text, status, answer_text
        from context_questions
        where draft_id = ?
        order by id
        """,
        (draft_id,),
    ).fetchall()
    return [_context_question_from_row(row) for row in rows]


def list_unresolved_context_questions(connection, draft_id: int) -> list[ContextQuestionRecord]:
    rows = connection.execute(
        """
        select id, draft_id, field_name, question_text, status, answer_text
        from context_questions
        where draft_id = ? and status = 'unresolved'
        order by id
        """,
        (draft_id,),
    ).fetchall()
    return [_context_question_from_row(row) for row in rows]


def _draft_from_row(row) -> DraftRecord:
    return DraftRecord(
        id=int(row[0]),
        candidate_group_id=int(row[1]),
        post_type=row[2],
        caption=row[3],
        hashtags_json=row[4],
        location_text=row[5],
        alt_text=row[6],
        status=row[7],
        scheduled_for=row[8],
    )


def _context_question_from_row(row) -> ContextQuestionRecord:
    return ContextQuestionRecord(
        id=int(row[0]),
        draft_id=int(row[1]),
        field_name=row[2],
        question_text=row[3],
        status=row[4],
        answer_text=row[5],
    )

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence
import json

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
class CandidateGroupPhotoItemRecord:
    group_id: int
    photo_id: int
    local_file_path: str
    sort_order: int
    role: str
    include_status: str


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


@dataclass(frozen=True)
class ApprovalRecord:
    id: int
    draft_id: int
    approval_type: str
    approved_by: Optional[str]
    approved_at: str
    source_message_ref: Optional[str]
    notes: Optional[str]
    invalidated_at: Optional[str]
    invalidation_reason: Optional[str]


@dataclass(frozen=True)
class PublishAttemptRecord:
    id: int
    draft_id: int
    post_type: str
    image_url: Optional[str]
    caption: Optional[str]
    container_id: Optional[str]
    published_media_id: Optional[str]
    status: str
    status_code: Optional[str]
    status_message: Optional[str]
    image_urls: list[str]
    child_container_ids: list[str]


@dataclass(frozen=True)
class R2StagedObjectRecord:
    id: int
    draft_id: int
    kind: str
    source_path: str
    bucket: str
    object_key: str
    public_url: str
    status: str
    staged_at: str
    deleted_at: Optional[str]
    cleanup_reason: Optional[str]


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


def list_candidate_group_photo_items(
    connection,
    candidate_group_id: int,
    *,
    included_only: bool = False,
) -> list[CandidateGroupPhotoItemRecord]:
    include_clause = "and candidate_group_items.include_status = 'included'" if included_only else ""
    rows = connection.execute(
        f"""
        select
            candidate_group_items.group_id,
            candidate_group_items.photo_id,
            photos.local_file_path,
            candidate_group_items.sort_order,
            candidate_group_items.role,
            candidate_group_items.include_status
        from candidate_group_items
        join photos on photos.id = candidate_group_items.photo_id
        where candidate_group_items.group_id = ?
        {include_clause}
        order by candidate_group_items.sort_order, photos.local_file_path
        """,
        (candidate_group_id,),
    ).fetchall()
    return [
        CandidateGroupPhotoItemRecord(
            group_id=int(row[0]),
            photo_id=int(row[1]),
            local_file_path=row[2],
            sort_order=int(row[3]),
            role=row[4],
            include_status=row[5],
        )
        for row in rows
    ]


def list_candidate_group_photo_paths(connection, candidate_group_id: int) -> list[str]:
    return [
        item.local_file_path
        for item in list_candidate_group_photo_items(
            connection, candidate_group_id, included_only=True
        )
    ]


def update_candidate_group_photo_item(
    connection,
    *,
    group_id: int,
    photo_id: int,
    sort_order: int,
    role: str,
    include_status: str,
) -> None:
    connection.execute(
        """
        update candidate_group_items
        set sort_order = ?, role = ?, include_status = ?
        where group_id = ? and photo_id = ?
        """,
        (sort_order, role, include_status, group_id, photo_id),
    )


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


def update_draft_status(connection, draft_id: int, status: str) -> Optional[DraftRecord]:
    connection.execute(
        """
        update drafts
        set status = ?, updated_at = current_timestamp
        where id = ?
        """,
        (status, draft_id),
    )
    return get_draft(connection, draft_id)


def update_draft_schedule(
    connection,
    draft_id: int,
    *,
    scheduled_for: str,
    status: str,
) -> Optional[DraftRecord]:
    connection.execute(
        """
        update drafts
        set scheduled_for = ?,
            status = ?,
            updated_at = current_timestamp
        where id = ?
        """,
        (scheduled_for, status, draft_id),
    )
    return get_draft(connection, draft_id)


def update_draft_content(
    connection,
    draft_id: int,
    *,
    caption: Optional[str] = None,
    hashtags: Optional[Sequence[str]] = None,
    location_text: Optional[str] = None,
    alt_text: Optional[str] = None,
    status: Optional[str] = None,
) -> Optional[DraftRecord]:
    hashtags_json = json.dumps(list(hashtags)) if hashtags is not None else None
    connection.execute(
        """
        update drafts
        set
            caption = coalesce(?, caption),
            hashtags_json = coalesce(?, hashtags_json),
            location_text = coalesce(?, location_text),
            alt_text = coalesce(?, alt_text),
            status = coalesce(?, status),
            updated_at = current_timestamp
        where id = ?
        """,
        (caption, hashtags_json, location_text, alt_text, status, draft_id),
    )
    return get_draft(connection, draft_id)


def create_approval_record(
    connection,
    *,
    draft_id: int,
    approval_type: str,
    approved_by: Optional[str] = None,
    source_message_ref: Optional[str] = None,
    notes: Optional[str] = None,
) -> ApprovalRecord:
    cursor = connection.execute(
        """
        insert into approvals (draft_id, approval_type, approved_by, source_message_ref, notes)
        values (?, ?, ?, ?, ?)
        """,
        (draft_id, approval_type, approved_by, source_message_ref, notes),
    )
    return get_approval(connection, int(cursor.lastrowid))


def get_approval(connection, approval_id: int) -> Optional[ApprovalRecord]:
    row = connection.execute(
        """
        select id, draft_id, approval_type, approved_by, approved_at,
               source_message_ref, notes, invalidated_at, invalidation_reason
        from approvals
        where id = ?
        """,
        (approval_id,),
    ).fetchone()
    if row is None:
        return None
    return _approval_from_row(row)


def list_active_approvals(connection, draft_id: int) -> list[ApprovalRecord]:
    rows = connection.execute(
        """
        select id, draft_id, approval_type, approved_by, approved_at,
               source_message_ref, notes, invalidated_at, invalidation_reason
        from approvals
        where draft_id = ? and invalidated_at is null
        order by id
        """,
        (draft_id,),
    ).fetchall()
    return [_approval_from_row(row) for row in rows]


def invalidate_active_approvals(
    connection,
    draft_id: int,
    *,
    reason: str,
) -> int:
    cursor = connection.execute(
        """
        update approvals
        set invalidated_at = current_timestamp,
            invalidation_reason = ?
        where draft_id = ? and invalidated_at is null
        """,
        (reason, draft_id),
    )
    return int(cursor.rowcount)


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


def create_publish_attempt(
    connection,
    *,
    draft_id: int,
    post_type: str,
    image_url: Optional[str],
    caption: Optional[str],
    status: str,
    container_id: Optional[str] = None,
    published_media_id: Optional[str] = None,
    status_code: Optional[str] = None,
    status_message: Optional[str] = None,
    image_urls: Optional[Sequence[str]] = None,
    child_container_ids: Optional[Sequence[str]] = None,
) -> PublishAttemptRecord:
    image_urls_json = json.dumps(list(image_urls)) if image_urls is not None else None
    child_container_ids_json = (
        json.dumps(list(child_container_ids)) if child_container_ids is not None else None
    )
    cursor = connection.execute(
        """
        insert into publish_attempts (
            draft_id,
            post_type,
            image_url,
            caption,
            container_id,
            published_media_id,
            status,
            status_code,
            status_message,
            image_urls_json,
            child_container_ids_json
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft_id,
            post_type,
            image_url,
            caption,
            container_id,
            published_media_id,
            status,
            status_code,
            status_message,
            image_urls_json,
            child_container_ids_json,
        ),
    )
    return get_publish_attempt(connection, int(cursor.lastrowid))


def update_publish_attempt(
    connection,
    attempt_id: int,
    *,
    status: str,
    container_id: Optional[str] = None,
    published_media_id: Optional[str] = None,
    status_code: Optional[str] = None,
    status_message: Optional[str] = None,
    image_urls: Optional[Sequence[str]] = None,
    child_container_ids: Optional[Sequence[str]] = None,
) -> PublishAttemptRecord:
    image_urls_json = json.dumps(list(image_urls)) if image_urls is not None else None
    child_container_ids_json = (
        json.dumps(list(child_container_ids)) if child_container_ids is not None else None
    )
    connection.execute(
        """
        update publish_attempts
        set status = ?,
            container_id = coalesce(?, container_id),
            published_media_id = coalesce(?, published_media_id),
            status_code = coalesce(?, status_code),
            status_message = coalesce(?, status_message),
            image_urls_json = coalesce(?, image_urls_json),
            child_container_ids_json = coalesce(?, child_container_ids_json),
            updated_at = current_timestamp
        where id = ?
        """,
        (
            status,
            container_id,
            published_media_id,
            status_code,
            status_message,
            image_urls_json,
            child_container_ids_json,
            attempt_id,
        ),
    )
    return get_publish_attempt(connection, attempt_id)


def get_publish_attempt(connection, attempt_id: int) -> Optional[PublishAttemptRecord]:
    row = connection.execute(
        """
        select id, draft_id, post_type, image_url, caption, container_id,
               published_media_id, status, status_code, status_message,
               image_urls_json, child_container_ids_json
        from publish_attempts
        where id = ?
        """,
        (attempt_id,),
    ).fetchone()
    if row is None:
        return None
    return _publish_attempt_from_row(row)


def list_publish_attempts(connection, draft_id: int) -> list[PublishAttemptRecord]:
    rows = connection.execute(
        """
        select id, draft_id, post_type, image_url, caption, container_id,
               published_media_id, status, status_code, status_message,
               image_urls_json, child_container_ids_json
        from publish_attempts
        where draft_id = ?
        order by id
        """,
        (draft_id,),
    ).fetchall()
    return [_publish_attempt_from_row(row) for row in rows]


def create_r2_staged_object_record(
    connection,
    *,
    draft_id: int,
    kind: str,
    source_path: str,
    bucket: str,
    object_key: str,
    public_url: str,
) -> R2StagedObjectRecord:
    connection.execute(
        """
        insert into r2_staged_objects (
            draft_id, kind, source_path, bucket, object_key, public_url, status
        ) values (?, ?, ?, ?, ?, ?, 'uploaded')
        on conflict(object_key) do update set
            draft_id = excluded.draft_id,
            kind = excluded.kind,
            source_path = excluded.source_path,
            bucket = excluded.bucket,
            public_url = excluded.public_url,
            status = 'uploaded',
            staged_at = current_timestamp,
            deleted_at = null,
            cleanup_reason = null
        """,
        (draft_id, kind, source_path, bucket, object_key, public_url),
    )
    row = connection.execute(
        """
        select id, draft_id, kind, source_path, bucket, object_key, public_url,
               status, staged_at, deleted_at, cleanup_reason
        from r2_staged_objects
        where object_key = ?
        """,
        (object_key,),
    ).fetchone()
    return _r2_staged_object_from_row(row)


def list_r2_staged_objects(
    connection,
    draft_id: int,
    *,
    status: Optional[str] = None,
) -> list[R2StagedObjectRecord]:
    status_clause = "and status = ?" if status is not None else ""
    params: tuple[object, ...] = (draft_id, status) if status is not None else (draft_id,)
    rows = connection.execute(
        f"""
        select id, draft_id, kind, source_path, bucket, object_key, public_url,
               status, staged_at, deleted_at, cleanup_reason
        from r2_staged_objects
        where draft_id = ? {status_clause}
        order by id
        """,
        params,
    ).fetchall()
    return [_r2_staged_object_from_row(row) for row in rows]


def mark_r2_staged_object_deleted(
    connection,
    object_id: int,
    *,
    reason: Optional[str] = None,
) -> R2StagedObjectRecord:
    connection.execute(
        """
        update r2_staged_objects
        set status = 'deleted', deleted_at = current_timestamp, cleanup_reason = ?
        where id = ?
        """,
        (reason, object_id),
    )
    row = connection.execute(
        """
        select id, draft_id, kind, source_path, bucket, object_key, public_url,
               status, staged_at, deleted_at, cleanup_reason
        from r2_staged_objects
        where id = ?
        """,
        (object_id,),
    ).fetchone()
    return _r2_staged_object_from_row(row)


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


def _approval_from_row(row) -> ApprovalRecord:
    return ApprovalRecord(
        id=int(row[0]),
        draft_id=int(row[1]),
        approval_type=row[2],
        approved_by=row[3],
        approved_at=row[4],
        source_message_ref=row[5],
        notes=row[6],
        invalidated_at=row[7],
        invalidation_reason=row[8],
    )


def _publish_attempt_from_row(row) -> PublishAttemptRecord:
    return PublishAttemptRecord(
        id=int(row[0]),
        draft_id=int(row[1]),
        post_type=row[2],
        image_url=row[3],
        caption=row[4],
        container_id=row[5],
        published_media_id=row[6],
        status=row[7],
        status_code=row[8],
        status_message=row[9],
        image_urls=_json_list(row[10]),
        child_container_ids=_json_list(row[11]),
    )


def _r2_staged_object_from_row(row) -> R2StagedObjectRecord:
    return R2StagedObjectRecord(
        id=int(row[0]),
        draft_id=int(row[1]),
        kind=row[2],
        source_path=row[3],
        bucket=row[4],
        object_key=row[5],
        public_url=row[6],
        status=row[7],
        staged_at=row[8],
        deleted_at=row[9],
        cleanup_reason=row[10],
    )


def _json_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


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

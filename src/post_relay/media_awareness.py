from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


DEFAULT_USER_KEY = "default"
USED_STATUSES = {"posted", "scheduled", "queued", "manually_excluded"}


@dataclass(frozen=True)
class MediaUsageRecord:
    id: int
    user_key: str
    photo_id: int
    local_file_path: str
    usage_status: str
    source: str
    draft_id: Optional[int]
    used_at: str
    note: Optional[str]


@dataclass(frozen=True)
class MediaUsageSummary:
    user_key: str
    total: int
    by_status: dict[str, int]
    mutation_statement: str = "Source media was not moved or modified."


def mark_media_used(
    connection,
    *,
    local_file_path: str,
    user_key: str = DEFAULT_USER_KEY,
    usage_status: str = "posted",
    source: str = "manual_mark",
    draft_id: Optional[int] = None,
    note: Optional[str] = None,
) -> MediaUsageRecord:
    photo = connection.execute(
        "select id, local_file_path from photos where local_file_path = ?",
        (local_file_path,),
    ).fetchone()
    if photo is None:
        raise ValueError(f"No indexed photo found for path: {local_file_path}")
    return mark_photo_used(
        connection,
        photo_id=int(photo[0]),
        user_key=user_key,
        usage_status=usage_status,
        source=source,
        draft_id=draft_id,
        note=note,
    )


def mark_photo_used(
    connection,
    *,
    photo_id: int,
    user_key: str = DEFAULT_USER_KEY,
    usage_status: str = "posted",
    source: str = "manual_mark",
    draft_id: Optional[int] = None,
    note: Optional[str] = None,
) -> MediaUsageRecord:
    user_key = (user_key or DEFAULT_USER_KEY).strip() or DEFAULT_USER_KEY
    usage_status = usage_status.strip().lower()
    if usage_status not in USED_STATUSES and usage_status != "allowed_reuse":
        raise ValueError(f"Unsupported media usage status: {usage_status}")
    photo = connection.execute(
        "select id, local_file_path from photos where id = ?",
        (photo_id,),
    ).fetchone()
    if photo is None:
        raise ValueError(f"No indexed photo found for id: {photo_id}")
    connection.execute(
        """
        insert into user_media_usage (
            user_key, photo_id, usage_status, source, draft_id, note
        ) values (?, ?, ?, ?, ?, ?)
        on conflict(user_key, photo_id) do update set
            usage_status = excluded.usage_status,
            source = excluded.source,
            draft_id = excluded.draft_id,
            note = excluded.note,
            used_at = current_timestamp,
            updated_at = current_timestamp
        """,
        (user_key, photo_id, usage_status, source, draft_id, note),
    )
    connection.commit()
    row = connection.execute(
        """
        select umu.id, umu.user_key, umu.photo_id, p.local_file_path, umu.usage_status,
               umu.source, umu.draft_id, umu.used_at, umu.note
        from user_media_usage umu
        join photos p on p.id = umu.photo_id
        where umu.user_key = ? and umu.photo_id = ?
        """,
        (user_key, photo_id),
    ).fetchone()
    return _usage_record(row)


def mark_post_media_used(
    connection,
    *,
    draft_id: int,
    user_key: str = DEFAULT_USER_KEY,
    usage_status: str = "posted",
    note: Optional[str] = None,
) -> list[MediaUsageRecord]:
    rows = connection.execute(
        """
        select cgi.photo_id
        from drafts d
        join candidate_group_items cgi on cgi.group_id = d.candidate_group_id
        where d.id = ? and cgi.include_status = 'included'
        order by cgi.sort_order, cgi.photo_id
        """,
        (draft_id,),
    ).fetchall()
    if not rows:
        raise ValueError(f"No included media found for post: {draft_id}")
    return [
        mark_photo_used(
            connection,
            photo_id=int(row[0]),
            user_key=user_key,
            usage_status=usage_status,
            source="post_relay_publish",
            draft_id=draft_id,
            note=note,
        )
        for row in rows
    ]


def list_media_usage(connection, *, user_key: str = DEFAULT_USER_KEY) -> list[MediaUsageRecord]:
    rows = connection.execute(
        """
        select umu.id, umu.user_key, umu.photo_id, p.local_file_path, umu.usage_status,
               umu.source, umu.draft_id, umu.used_at, umu.note
        from user_media_usage umu
        join photos p on p.id = umu.photo_id
        where umu.user_key = ?
        order by umu.id
        """,
        ((user_key or DEFAULT_USER_KEY).strip() or DEFAULT_USER_KEY,),
    ).fetchall()
    return [_usage_record(row) for row in rows]


def summarize_media_usage(
    connection,
    *,
    user_key: str = DEFAULT_USER_KEY,
    post_id: Optional[int] = None,
) -> MediaUsageSummary:
    if post_id is not None:
        mark_post_media_used(connection, draft_id=post_id, user_key=user_key)
    rows = connection.execute(
        """
        select usage_status, count(*)
        from user_media_usage
        where user_key = ?
        group by usage_status
        order by usage_status
        """,
        ((user_key or DEFAULT_USER_KEY).strip() or DEFAULT_USER_KEY,),
    ).fetchall()
    by_status = {str(row[0]): int(row[1]) for row in rows}
    return MediaUsageSummary(user_key=user_key, total=sum(by_status.values()), by_status=by_status)


def render_media_usage_record(record: MediaUsageRecord) -> str:
    lines = [
        "Media usage recorded",
        f"User: {record.user_key}",
        f"Status: {record.usage_status}",
        f"Photo: {record.local_file_path}",
        f"Source: {record.source}",
    ]
    if record.draft_id is not None:
        lines.append(f"Post: {record.draft_id}")
    if record.note:
        lines.append(f"Note: {record.note}")
    lines.append("Source media was not moved or modified.")
    lines.append("No Discord, R2, or Meta network calls were made.")
    return "\n".join(lines)


def render_media_usage_summary(summary: MediaUsageSummary) -> str:
    lines = ["Media awareness summary", f"User: {summary.user_key}", f"Total tracked media: {summary.total}"]
    if summary.by_status:
        lines.append("By status:")
        for status, count in summary.by_status.items():
            lines.append(f"- {status}: {count}")
    else:
        lines.append("By status: <none>")
    lines.append(summary.mutation_statement)
    lines.append("No Discord, R2, or Meta network calls were made.")
    return "\n".join(lines)


def _usage_record(row) -> MediaUsageRecord:
    return MediaUsageRecord(
        id=int(row[0]),
        user_key=str(row[1]),
        photo_id=int(row[2]),
        local_file_path=str(row[3]),
        usage_status=str(row[4]),
        source=str(row[5]),
        draft_id=int(row[6]) if row[6] is not None else None,
        used_at=str(row[7]),
        note=row[8],
    )

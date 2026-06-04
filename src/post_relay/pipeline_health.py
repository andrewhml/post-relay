from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from post_relay.account_preferences import get_active_account_preferences
from post_relay.recommendations import NO_MUTATION_STATEMENT


@dataclass(frozen=True)
class PipelineHealth:
    stage_counts: dict[str, int]
    candidate_groups_without_posts: int
    blocked_posts: list[str]
    cadence_risk: list[str]
    user_needed_reviews: list[str]
    agent_preparable_work: list[str]
    mutation_statement: str = NO_MUTATION_STATEMENT


def build_pipeline_health(connection, *, now_iso: str | None = None) -> PipelineHealth:
    stage_counts = _draft_counts_by_status(connection)
    candidate_groups_without_posts = _count_candidate_groups_without_posts(connection)
    blocked_posts = _blocked_posts(connection)
    cadence_risk = _cadence_risk(connection, stage_counts, now_iso=now_iso)
    user_needed_reviews = _user_needed_reviews(connection)
    agent_preparable_work = _agent_preparable_work(connection, candidate_groups_without_posts)
    return PipelineHealth(
        stage_counts=stage_counts,
        candidate_groups_without_posts=candidate_groups_without_posts,
        blocked_posts=blocked_posts,
        cadence_risk=cadence_risk,
        user_needed_reviews=user_needed_reviews,
        agent_preparable_work=agent_preparable_work,
    )


def render_pipeline_health(connection) -> str:
    health = build_pipeline_health(connection)
    lines = ["Pipeline health", "Local pipeline status; advisory only."]
    lines.append("")
    lines.append("Counts by stage:")
    if health.stage_counts:
        for status, count in sorted(health.stage_counts.items()):
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- <none>: 0")
    lines.append(f"- candidate_groups_without_posts: {health.candidate_groups_without_posts}")
    lines.append("")
    lines.append("Blocked posts/tasks:")
    _append_list(lines, health.blocked_posts, empty="No blocked posts/tasks found from local state.")
    lines.append("")
    lines.append("Cadence risk:")
    _append_list(lines, health.cadence_risk, empty="No cadence risk detected from stored local targets.")
    lines.append("")
    lines.append("User-needed reviews:")
    _append_list(lines, health.user_needed_reviews, empty="No user-needed reviews detected from local post states.")
    lines.append("")
    lines.append("Agent-preparable next work:")
    _append_list(lines, health.agent_preparable_work, empty="No agent-preparable work detected from local state.")
    lines.append("")
    lines.append("No automatic posting, scheduling, approval, messaging, upload, or analytics collection was performed.")
    lines.append(health.mutation_statement)
    return "\n".join(lines)


def _draft_counts_by_status(connection) -> dict[str, int]:
    rows = connection.execute(
        """
        select status, count(*)
        from drafts
        group by status
        order by status asc
        """
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _count_candidate_groups_without_posts(connection) -> int:
    row = connection.execute(
        """
        select count(*)
        from candidate_groups cg
        left join drafts d on d.candidate_group_id = cg.id
        where cg.status = 'candidate'
          and d.id is null
        """
    ).fetchone()
    return int(row[0])


def _blocked_posts(connection) -> list[str]:
    rows = connection.execute(
        """
        select distinct d.id, d.status, a.invalidation_reason
        from drafts d
        join approvals a on a.draft_id = d.id
        where a.invalidated_at is not null
          and d.status not in ('posted', 'published')
        order by d.id asc
        limit 10
        """
    ).fetchall()
    return [f"Post {int(row[0])} has invalidated approval ({row[2] or 'reason not recorded'}); current status: {row[1]}." for row in rows]


def _cadence_risk(connection, stage_counts: dict[str, int], *, now_iso: str | None = None) -> list[str]:
    preferences = get_active_account_preferences(connection)
    scheduled = stage_counts.get("scheduled", 0) + stage_counts.get("awaiting_publish_approval", 0)
    risks: list[str] = []
    if preferences and preferences.target_weekly_posts is not None and scheduled < preferences.target_weekly_posts:
        risks.append(f"cadence risk: target {preferences.target_weekly_posts} posts/week, scheduled queue has {scheduled}")
    no_future_content_risk = _no_future_content_risk(connection, now_iso=now_iso)
    if no_future_content_risk:
        risks.append(no_future_content_risk)
    if preferences and preferences.target_monthly_reels is not None:
        reels = _count_published_snapshots_by_type(connection, "reel")
        if reels < preferences.target_monthly_reels:
            risks.append(f"reels cadence risk: target {preferences.target_monthly_reels} reels/month, stored published reels this month: {reels}")
    return risks


def _no_future_content_risk(connection, *, now_iso: Optional[str] = None, due_after_days: int = 2) -> Optional[str]:
    now_dt = _parse_iso_datetime(now_iso) if now_iso else datetime.now(timezone.utc)
    if _future_scheduled_content_count(connection, now_dt) > 0:
        return None
    latest = _latest_scheduled_or_published_at(connection)
    if latest is None:
        return None
    days_since_latest = max(0, (now_dt.date() - latest.date()).days)
    if days_since_latest < due_after_days:
        return None
    return (
        "cadence risk: no future content scheduled; "
        f"last published/scheduled post was {days_since_latest} day(s) ago; threshold is {due_after_days} days"
    )


def _future_scheduled_content_count(connection, now_dt: datetime) -> int:
    rows = connection.execute(
        """
        select scheduled_for
        from drafts
        where scheduled_for is not null
          and status in ('scheduled', 'awaiting_publish_approval', 'ready_to_publish')
        """
    ).fetchall()
    return sum(1 for row in rows if _parse_iso_datetime(str(row[0])) > now_dt)


def _latest_scheduled_or_published_at(connection) -> Optional[datetime]:
    values = [
        str(row[0])
        for row in connection.execute(
            """
            select scheduled_for
            from drafts
            where scheduled_for is not null
              and status in ('scheduled', 'awaiting_publish_approval', 'ready_to_publish', 'posted', 'published')
            """
        ).fetchall()
        if row[0]
    ]
    values.extend(
        str(row[0])
        for row in connection.execute(
            """
            select actual_published_at
            from published_post_snapshots
            where actual_published_at is not null
            """
        ).fetchall()
        if row[0]
    )
    parsed = [_parse_iso_datetime(value) for value in values]
    return max(parsed) if parsed else None


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _user_needed_reviews(connection) -> list[str]:
    rows = connection.execute(
        """
        select id, status, post_type
        from drafts
        where status in ('awaiting_review', 'needs_edits', 'awaiting_publish_approval', 'scheduled')
        order by case status
            when 'awaiting_review' then 0
            when 'needs_edits' then 1
            when 'awaiting_publish_approval' then 2
            when 'scheduled' then 3
            else 4
        end,
        id asc
        limit 10
        """
    ).fetchall()
    reviews: list[str] = []
    for row in rows:
        draft_id = int(row[0])
        status = str(row[1])
        if status == "awaiting_review":
            reviews.append(f"Post {draft_id} needs user content review.")
        elif status == "needs_edits":
            reviews.append(f"Post {draft_id} needs user/agent edit follow-up before approval.")
        elif status == "awaiting_publish_approval":
            reviews.append(f"Post {draft_id} needs final publish approval review.")
        elif status == "scheduled":
            reviews.append(f"Post {draft_id} is scheduled; review final publish approval readiness before due time.")
    return reviews


def _agent_preparable_work(connection, candidate_groups_without_posts: int) -> list[str]:
    work: list[str] = []
    if candidate_groups_without_posts:
        row = connection.execute(
            """
            select cg.id, cg.title
            from candidate_groups cg
            left join drafts d on d.candidate_group_id = cg.id
            where cg.status = 'candidate'
              and d.id is null
            order by cg.id asc
            limit 1
            """
        ).fetchone()
        if row:
            work.append(f"Candidate {int(row[0])} can become a draft: {row[1]}.")
    rows = connection.execute(
        """
        select id, status
        from drafts
        where status in ('drafting', 'needs_edits')
        order by id asc
        limit 5
        """
    ).fetchall()
    for row in rows:
        work.append(f"Post {int(row[0])} can be prepared through selection/crop/copy review from status {row[1]}.")
    if not work:
        work.append("Run post-relay recommendations growth-coach --db data/post_relay.sqlite to choose the next advisory move.")
    return work


def _count_published_snapshots_by_type(connection, post_type: str) -> int:
    row = connection.execute("select count(*) from published_post_snapshots where post_type = ?", (post_type,)).fetchone()
    return int(row[0])


def _append_list(lines: list[str], values: list[str], *, empty: str) -> None:
    if values:
        for value in values:
            lines.append(f"- {value}")
    else:
        lines.append(f"- {empty}")

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from post_relay.user_goals import get_active_user_goal


NO_MUTATION_STATEMENT = (
    "No Discord, R2, or Meta network calls were made. No posts, approvals, "
    "schedules, opportunities, publish attempts, or analytics rows were mutated."
)


@dataclass(frozen=True)
class SignalBaseline:
    has_active_goal: bool
    active_goal_title: Optional[str]
    counts: dict[str, int]
    posts_by_status: dict[str, int]
    warnings: list[str]
    next_safe_commands: list[str]
    mutation_statement: str = NO_MUTATION_STATEMENT


def build_signal_baseline(connection) -> SignalBaseline:
    goal = get_active_user_goal(connection)
    posts_by_status = _counts_by_value(connection, "drafts", "status")
    counts = {
        "candidate_groups": _count(connection, "candidate_groups"),
        "posts_total": _count(connection, "drafts"),
        "selected_media": _count_selected_media(connection),
        "accepted_guided_packages": _count(
            connection,
            "guided_draft_packages",
            "accepted_at is not null",
        ),
        "published_snapshots": _count(connection, "published_post_snapshots"),
        "insight_snapshots": _count(connection, "media_insight_snapshots"),
        "follower_snapshots": _count(connection, "account_metric_snapshots"),
        "approvals_total": _count(connection, "approvals"),
        "approval_invalidations": _count(connection, "approvals", "invalidated_at is not null"),
        "scheduled_posts": _count(connection, "drafts", "scheduled_for is not null"),
        "opportunities": _count(connection, "post_opportunities"),
        "dm_threads": _count(connection, "conversation_threads"),
    }
    return SignalBaseline(
        has_active_goal=goal is not None,
        active_goal_title=goal.title if goal is not None else None,
        counts=counts,
        posts_by_status=posts_by_status,
        warnings=_build_warnings(goal is not None, counts),
        next_safe_commands=_build_next_safe_commands(goal is not None, counts),
    )


def render_signal_baseline(connection) -> str:
    baseline = build_signal_baseline(connection)
    lines = ["Recommendation signal baseline"]
    if baseline.has_active_goal:
        lines.append(f"Active goal: {baseline.active_goal_title}")
    else:
        lines.append("Active goal: missing")
    lines.append("")
    lines.append("Local signal coverage:")
    for key in _COUNT_ORDER:
        lines.append(f"- {key}: {baseline.counts[key]}")
    lines.append("")
    lines.append("Post lifecycle states:")
    if baseline.posts_by_status:
        for status, count in baseline.posts_by_status.items():
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- <none>: 0")
    lines.append("")
    lines.append("Sparse-signal warnings:")
    if baseline.warnings:
        for warning in baseline.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- Enough local baseline signals exist for the next advisory recommendation slice.")
    lines.append("")
    lines.append("Next safe commands:")
    for command in baseline.next_safe_commands:
        lines.append(f"- {command}")
    lines.append("")
    lines.append(baseline.mutation_statement)
    return "\n".join(lines)


_COUNT_ORDER = [
    "candidate_groups",
    "posts_total",
    "selected_media",
    "accepted_guided_packages",
    "published_snapshots",
    "insight_snapshots",
    "follower_snapshots",
    "approvals_total",
    "approval_invalidations",
    "scheduled_posts",
    "opportunities",
    "dm_threads",
]


def _count(connection, table_name: str, where_clause: Optional[str] = None) -> int:
    sql = f"select count(*) from {table_name}"
    if where_clause:
        sql = f"{sql} where {where_clause}"
    row = connection.execute(sql).fetchone()
    return int(row[0])


def _count_selected_media(connection) -> int:
    row = connection.execute(
        """
        select count(*)
        from candidate_group_items cgi
        join drafts d on d.candidate_group_id = cgi.group_id
        where cgi.include_status = 'included'
        """
    ).fetchone()
    return int(row[0])


def _counts_by_value(connection, table_name: str, column_name: str) -> dict[str, int]:
    rows = connection.execute(
        f"""
        select {column_name}, count(*)
        from {table_name}
        group by {column_name}
        order by {column_name} asc
        """
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _build_warnings(has_active_goal: bool, counts: dict[str, int]) -> list[str]:
    warnings: list[str] = []
    if not has_active_goal:
        warnings.append("Active goal is missing; recommendations should ask for the north star before ranking posts.")
    if counts["candidate_groups"] == 0:
        warnings.append("Not enough candidate groups; scan and build candidates before ranking what to post next.")
    if counts["posts_total"] == 0:
        warnings.append("No posts exist yet; create at least one post before post-specific recommendations.")
    if counts["published_snapshots"] < 3 or counts["insight_snapshots"] < 3:
        warnings.append("Performance history is sparse")
    if counts["follower_snapshots"] < 2:
        warnings.append("Follower trend history is sparse; use cadence priors before account-growth timing claims.")
    if counts["accepted_guided_packages"] == 0:
        warnings.append("No accepted guided packages yet; caption/style recommendations should stay generic.")
    return warnings


def _build_next_safe_commands(has_active_goal: bool, counts: dict[str, int]) -> list[str]:
    commands: list[str] = []
    if not has_active_goal:
        commands.append("post-relay goals init --db data/post_relay.sqlite --title ... --statement ...")
    if counts["candidate_groups"] == 0:
        commands.append("post-relay candidates build --db data/post_relay.sqlite")
    if counts["posts_total"] == 0 and counts["candidate_groups"] > 0:
        commands.append("post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite")
    commands.append("post-relay analytics feedback-summary --db data/post_relay.sqlite")
    commands.append("post-relay analytics follower-summary --db data/post_relay.sqlite")
    return commands

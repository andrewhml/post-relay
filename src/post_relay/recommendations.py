from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
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


@dataclass(frozen=True)
class CandidateRanking:
    rank: int
    candidate_id: int
    title: str
    post_type: str
    score: int
    media_count: int
    included_media_count: int
    missing_file_count: int
    dimensions_known_count: int
    draft_id: Optional[int]
    draft_status: Optional[str]
    score_breakdown: list[str]
    warnings: list[str]
    next_safe_command: str


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


def build_candidate_rankings(connection, *, limit: int = 10) -> list[CandidateRanking]:
    goal = get_active_user_goal(connection)
    goal_terms = _goal_terms(goal)
    analytics_sparse = _count(connection, "published_post_snapshots") < 3 or _count(connection, "media_insight_snapshots") < 3
    rows = connection.execute(
        """
        select cg.id,
               cg.title,
               cg.source_folder,
               cg.post_type_recommendation,
               cg.reason,
               d.id as draft_id,
               d.status as draft_status,
               count(cgi.photo_id) as media_count,
               sum(case when cgi.include_status = 'included' then 1 else 0 end) as included_media_count,
               sum(case when cgi.include_status = 'included' and p.width is not null and p.height is not null then 1 else 0 end) as dimensions_known_count,
               group_concat(case when cgi.include_status = 'included' then p.local_file_path end, '\n') as included_paths
        from candidate_groups cg
        left join candidate_group_items cgi on cgi.group_id = cg.id
        left join photos p on p.id = cgi.photo_id
        left join drafts d on d.candidate_group_id = cg.id
        where cg.status = 'candidate'
        group by cg.id, d.id
        """
    ).fetchall()
    rankings = [_rank_candidate(row, goal_terms, analytics_sparse) for row in rows]
    rankings.sort(key=lambda ranking: (-ranking.score, ranking.candidate_id))
    return [
        CandidateRanking(
            rank=index,
            candidate_id=ranking.candidate_id,
            title=ranking.title,
            post_type=ranking.post_type,
            score=ranking.score,
            media_count=ranking.media_count,
            included_media_count=ranking.included_media_count,
            missing_file_count=ranking.missing_file_count,
            dimensions_known_count=ranking.dimensions_known_count,
            draft_id=ranking.draft_id,
            draft_status=ranking.draft_status,
            score_breakdown=ranking.score_breakdown,
            warnings=ranking.warnings,
            next_safe_command=ranking.next_safe_command,
        )
        for index, ranking in enumerate(rankings[:limit], start=1)
    ]


def render_candidate_rankings(connection, *, limit: int = 10) -> str:
    rankings = build_candidate_rankings(connection, limit=limit)
    lines = ["Candidate recommendations", "Local deterministic ranking; advisory only."]
    if not rankings:
        lines.extend(
            [
                "No candidate groups are available yet.",
                "Next safe command: post-relay candidates build --db data/post_relay.sqlite",
                "",
                NO_MUTATION_STATEMENT,
            ]
        )
        return "\n".join(lines)
    lines.append("Sparse analytics note: performance data is not weighted strongly yet.")
    for ranking in rankings:
        lines.extend(
            [
                "",
                f"#{ranking.rank} Candidate {ranking.candidate_id}: {ranking.title}",
                f"Score: {ranking.score}",
                f"Post type: {ranking.post_type}",
                f"Media: {ranking.included_media_count} included / {ranking.media_count} total; missing files: {ranking.missing_file_count}; dimensions known: {ranking.dimensions_known_count}",
            ]
        )
        if ranking.draft_id is not None:
            lines.append(f"Existing post: {ranking.draft_id} ({ranking.draft_status})")
        lines.append("Why this ranks here:")
        for item in ranking.score_breakdown:
            lines.append(f"- {item}")
        if ranking.warnings:
            lines.append("Warnings:")
            for warning in ranking.warnings:
                lines.append(f"- {warning}")
        lines.append(f"Next safe command: {ranking.next_safe_command}")
    lines.append("")
    lines.append(NO_MUTATION_STATEMENT)
    return "\n".join(lines)


@dataclass(frozen=True)
class _CandidateScore:
    candidate_id: int
    title: str
    post_type: str
    score: int
    media_count: int
    included_media_count: int
    missing_file_count: int
    dimensions_known_count: int
    draft_id: Optional[int]
    draft_status: Optional[str]
    score_breakdown: list[str]
    warnings: list[str]
    next_safe_command: str


def _rank_candidate(row, goal_terms: set[str], analytics_sparse: bool) -> _CandidateScore:
    candidate_id = int(row[0])
    title = str(row[1])
    source_folder = row[2] or ""
    post_type = row[3] or "unknown"
    reason = row[4] or ""
    draft_id = int(row[5]) if row[5] is not None else None
    draft_status = row[6]
    media_count = int(row[7] or 0)
    included_media_count = int(row[8] or 0)
    dimensions_known_count = int(row[9] or 0)
    included_paths = [path for path in (row[10] or "").split("\n") if path]
    missing_file_count = sum(1 for path in included_paths if not Path(path).exists())
    score = 0
    breakdown: list[str] = []
    warnings: list[str] = []

    if included_media_count > 0:
        score += 10
        breakdown.append("Readiness: has included media")
    else:
        score -= 25
        breakdown.append("Readiness: no included media")
        warnings.append("No included media; make a media selection before review.")

    if missing_file_count == 0 and included_media_count > 0:
        score += 20
        breakdown.append("Readiness: all included source files exist")
    elif missing_file_count > 0:
        score -= 20
        breakdown.append("Readiness: missing local source files")
        warnings.append("Some source files are missing locally.")

    if included_media_count > 0 and dimensions_known_count == included_media_count:
        score += 10
        breakdown.append("Readiness: dimensions known for included media")
    elif included_media_count > 0:
        score -= 5
        breakdown.append("Readiness: missing dimensions for some included media")

    if included_media_count > 60:
        score -= 15
        warnings.append("Large set: narrow before rendering a contact sheet")
        breakdown.append("Readiness: oversized set needs narrowing")
    else:
        score += 5
        breakdown.append("Readiness: reviewable set size")

    if post_type == "carousel" and 2 <= included_media_count <= 10:
        score += 20
        breakdown.append("Content potential: carousel-sized coherent local set")
    elif included_media_count == 1:
        score += 8
        breakdown.append("Content potential: single-image candidate")
    elif included_media_count > 10:
        score += 4
        breakdown.append("Content potential: broad set may contain a strong carousel after narrowing")

    candidate_terms = _terms(" ".join([title, source_folder, reason]))
    if goal_terms and candidate_terms.intersection(goal_terms):
        score += 15
        breakdown.append("Goal alignment: matched active goal language")
    elif goal_terms:
        breakdown.append("Goal alignment: no explicit active-goal match found")

    if draft_id is None:
        score += 8
        breakdown.append("Effort: no post exists yet; can create a fresh draft")
        next_safe_command = f"post-relay drafts create --candidate-id {candidate_id} --db data/post_relay.sqlite"
    elif draft_status in {"drafting", "needs_edits", "awaiting_review"}:
        score += 4
        breakdown.append("Effort: existing post can continue through review")
        next_safe_command = f"post-relay drafts preview --post-id {draft_id} --db data/post_relay.sqlite"
    else:
        score -= 35
        breakdown.append("Effort: existing post is already queued or completed")
        warnings.append("Existing post is already queued or completed; prefer unfinished fresh candidates when available.")
        next_safe_command = f"post-relay drafts preview --post-id {draft_id} --db data/post_relay.sqlite"

    if analytics_sparse:
        breakdown.append("Learning signal: sparse analytics, performance is not weighted strongly")

    return _CandidateScore(
        candidate_id=candidate_id,
        title=title,
        post_type=post_type,
        score=score,
        media_count=media_count,
        included_media_count=included_media_count,
        missing_file_count=missing_file_count,
        dimensions_known_count=dimensions_known_count,
        draft_id=draft_id,
        draft_status=draft_status,
        score_breakdown=breakdown,
        warnings=warnings,
        next_safe_command=next_safe_command,
    )

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


def _goal_terms(goal) -> set[str]:
    if goal is None:
        return set()
    text_parts = [
        goal.title,
        goal.goal_statement,
        goal.target_audience or "",
        goal.desired_cadence or "",
        goal.strategy_notes or "",
        " ".join(goal.content_pillars),
        " ".join(goal.success_metrics),
        " ".join(goal.constraints),
    ]
    return _terms(" ".join(text_parts))


def _terms(text: str) -> set[str]:
    stopwords = {"with", "from", "that", "this", "post", "posts", "travel", "account"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 4 and token not in stopwords
    }


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

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import json
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


@dataclass(frozen=True)
class ScheduledPostSummary:
    post_id: int
    scheduled_for: str
    status: str
    post_type: str
    title: Optional[str]


@dataclass(frozen=True)
class ScheduleWindowRecommendation:
    rank: int
    scheduled_for: str
    label: str
    rationale: list[str]
    conflicts: list[str]
    next_safe_command: str


@dataclass(frozen=True)
class ScheduleRecommendationPlan:
    active_goal_title: Optional[str]
    scheduled_posts: list[ScheduledPostSummary]
    recommendations: list[ScheduleWindowRecommendation]
    warnings: list[str]
    mutation_statement: str = NO_MUTATION_STATEMENT


@dataclass(frozen=True)
class CaptionFeedbackResult:
    id: int
    post_id: int
    sentiment: str
    signal: str
    note: str
    reviewed_by: Optional[str]
    mutation_statement: str = (
        "No Discord, R2, or Meta network calls were made. "
        "No captions, posts, approvals, schedules, Discord, R2, or Meta state were changed."
    )


@dataclass(frozen=True)
class CaptionStyleRecommendationPlan:
    active_goal_title: Optional[str]
    post_id: Optional[int]
    current_caption: str
    accepted_caption_count: int
    approved_post_count: int
    published_snapshot_count: int
    insight_snapshot_count: int
    caption_feedback_count: int
    local_patterns: list[str]
    recommended_direction: list[str]
    guardrails: list[str]
    example_captions: list[str]
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


def build_schedule_recommendations(
    connection,
    *,
    now: Optional[str] = None,
    limit: int = 3,
) -> ScheduleRecommendationPlan:
    goal = get_active_user_goal(connection)
    scheduled_posts = _list_scheduled_posts(connection)
    scheduled_dates = {_parse_iso_datetime(post.scheduled_for).date() for post in scheduled_posts}
    reference_time = _parse_iso_datetime(now) if now else datetime.now().astimezone()
    post_id = _next_unscheduled_post_id(connection)
    warnings: list[str] = []
    if goal is None:
        warnings.append("Active goal is missing; schedule suggestions should be treated as generic cadence priors.")
    if _count(connection, "published_post_snapshots") < 3 or _count(connection, "media_insight_snapshots") < 3:
        warnings.append("Performance/follower timing data is sparse; using conservative cadence priors.")
    if _count(connection, "account_metric_snapshots") < 2:
        warnings.append("Follower trend history is sparse; avoid making account-growth timing claims.")

    recommendations: list[ScheduleWindowRecommendation] = []
    candidate_day = reference_time.date() + timedelta(days=1)
    while len(recommendations) < limit:
        if candidate_day.weekday() in _PREFERRED_SCHEDULE_WEEKDAYS:
            slot = datetime.combine(candidate_day, time(9, 0), tzinfo=reference_time.tzinfo)
            conflicts = []
            if candidate_day in scheduled_dates:
                conflicts.append("Existing scheduled queue already has a post on this date.")
            else:
                rank = len(recommendations) + 1
                rationale = [
                    "Checked the existing scheduled queue before suggesting this slot.",
                    "Uses conservative morning cadence prior while local timing data is sparse.",
                ]
                if goal and goal.desired_cadence:
                    rationale.append(f"Active goal cadence: {goal.desired_cadence}.")
                recommendations.append(
                    ScheduleWindowRecommendation(
                        rank=rank,
                        scheduled_for=slot.isoformat(timespec="seconds"),
                        label=_weekday_label(slot),
                        rationale=rationale,
                        conflicts=conflicts,
                        next_safe_command=(
                            f"post-relay drafts schedule --post-id {post_id or '<post-id>'} "
                            f"--scheduled-for \"{slot.isoformat(timespec='seconds')}\" --db data/post_relay.sqlite"
                        ),
                    )
                )
        candidate_day += timedelta(days=1)
    return ScheduleRecommendationPlan(
        active_goal_title=goal.title if goal else None,
        scheduled_posts=scheduled_posts,
        recommendations=recommendations,
        warnings=warnings,
    )


def render_schedule_recommendations(connection, *, now: Optional[str] = None, limit: int = 3) -> str:
    plan = build_schedule_recommendations(connection, now=now, limit=limit)
    lines = ["Schedule recommendations", "Local schedule-window suggestions; advisory only."]
    lines.append(f"Active goal: {plan.active_goal_title or '<missing>'}")
    lines.append("")
    lines.append("Existing scheduled queue:")
    if plan.scheduled_posts:
        for post in plan.scheduled_posts:
            title = f" — {post.title}" if post.title else ""
            lines.append(f"- Post {post.post_id}: {post.scheduled_for} ({post.status}, {post.post_type}){title}")
    else:
        lines.append("- <none>")
    lines.append("")
    lines.append("Warnings:")
    if plan.warnings:
        for warning in plan.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No schedule-specific warnings from local stored signals.")
    lines.append("")
    lines.append("Suggested windows:")
    for recommendation in plan.recommendations:
        lines.append(f"#{recommendation.rank} {recommendation.scheduled_for} ({recommendation.label})")
        lines.append("Rationale:")
        for rationale in recommendation.rationale:
            lines.append(f"- {rationale}")
        lines.append("Conflicts:")
        if recommendation.conflicts:
            for conflict in recommendation.conflicts:
                lines.append(f"- {conflict}")
        else:
            lines.append("- No same-day conflict with the existing scheduled queue.")
        lines.append(f"Next safe command: {recommendation.next_safe_command}")
    lines.append("")
    lines.append("No automatic scheduling was performed.")
    lines.append(plan.mutation_statement)
    return "\n".join(lines)



def record_caption_feedback(
    connection,
    *,
    post_id: int,
    sentiment: str,
    signal: str,
    note: str,
    reviewed_by: Optional[str] = None,
) -> CaptionFeedbackResult:
    if _draft_exists(connection, post_id) is False:
        raise ValueError(f"Post #{post_id} was not found")
    sentiment = _normalize_caption_feedback_token(sentiment, field_name="sentiment")
    signal = _normalize_caption_feedback_token(signal, field_name="signal")
    note = note.strip()
    if not note:
        raise ValueError("Caption feedback note must not be empty")
    cursor = connection.execute(
        """
        insert into caption_feedback (draft_id, sentiment, signal, note, reviewed_by)
        values (?, ?, ?, ?, ?)
        """,
        (post_id, sentiment, signal, note[:500], (reviewed_by or "").strip() or None),
    )
    connection.commit()
    return CaptionFeedbackResult(
        id=int(cursor.lastrowid),
        post_id=post_id,
        sentiment=sentiment,
        signal=signal,
        note=note[:500],
        reviewed_by=(reviewed_by or "").strip() or None,
    )


def render_caption_feedback_result(result: CaptionFeedbackResult) -> str:
    lines = [
        f"Caption feedback recorded for post {result.post_id}",
        f"Sentiment: {result.sentiment}",
        f"Signal: {result.signal}",
        f"Note: {result.note}",
    ]
    if result.reviewed_by:
        lines.append(f"Reviewed by: {result.reviewed_by}")
    lines.append(result.mutation_statement)
    return "\n".join(lines)

def build_caption_style_recommendations(connection, *, post_id: Optional[int] = None) -> CaptionStyleRecommendationPlan:
    goal = get_active_user_goal(connection)
    current_caption = _current_caption(connection, post_id)
    accepted_captions = _accepted_caption_examples(connection)
    approved_post_count = _count(
        connection,
        "approvals",
        "approval_type = 'draft' and invalidated_at is null",
    )
    published_snapshot_count = _count(connection, "published_post_snapshots")
    insight_snapshot_count = _count(connection, "media_insight_snapshots")
    caption_feedback = _caption_feedback_rows(connection, post_id=post_id)
    example_captions = _published_caption_examples(connection) + accepted_captions
    local_patterns = _caption_local_patterns(
        accepted_caption_count=len(accepted_captions),
        approved_post_count=approved_post_count,
        published_snapshot_count=published_snapshot_count,
        insight_snapshot_count=insight_snapshot_count,
        example_captions=example_captions,
        caption_feedback=caption_feedback,
    )
    recommended_direction = _caption_recommended_direction(goal, current_caption, example_captions)
    guardrails = [
        "Do not overwrite the current caption automatically; treat this as review guidance.",
        "Keep claims grounded in visible photos and confirmed local context.",
        "Freeform location text remains review-only unless a resolved Meta Page location tag is explicitly selected.",
    ]
    return CaptionStyleRecommendationPlan(
        active_goal_title=goal.title if goal else None,
        post_id=post_id,
        current_caption=current_caption,
        accepted_caption_count=len(accepted_captions),
        approved_post_count=approved_post_count,
        published_snapshot_count=published_snapshot_count,
        insight_snapshot_count=insight_snapshot_count,
        caption_feedback_count=len(caption_feedback),
        local_patterns=local_patterns,
        recommended_direction=recommended_direction,
        guardrails=guardrails,
        example_captions=example_captions[:3],
    )


def render_caption_style_recommendations(connection, *, post_id: Optional[int] = None) -> str:
    plan = build_caption_style_recommendations(connection, post_id=post_id)
    lines = ["Caption style recommendations", "Local caption-direction guidance; advisory only."]
    lines.append(f"Active goal: {plan.active_goal_title or '<missing>'}")
    lines.append(f"Post: {plan.post_id if plan.post_id is not None else '<not specified>'}")
    lines.append(f"Current caption: {plan.current_caption or '<empty>'}")
    lines.append("")
    lines.append("Local feedback signals:")
    lines.append(f"- Accepted caption packages: {plan.accepted_caption_count}")
    lines.append(f"- Currently approved posts: {plan.approved_post_count}")
    lines.append(f"- Published snapshots: {plan.published_snapshot_count}")
    lines.append(f"- Insight snapshots: {plan.insight_snapshot_count}")
    lines.append(f"- Caption feedback rows: {plan.caption_feedback_count}")
    lines.append("")
    lines.append("Observed local patterns:")
    for pattern in plan.local_patterns:
        lines.append(f"- {pattern}")
    lines.append("")
    lines.append("Recommended direction:")
    for direction in plan.recommended_direction:
        lines.append(f"- {direction}")
    lines.append("")
    lines.append("Example local captions considered:")
    if plan.example_captions:
        for caption in plan.example_captions:
            lines.append(f"- {caption}")
    else:
        lines.append("- <none yet>")
    lines.append("")
    lines.append("Guardrails:")
    for guardrail in plan.guardrails:
        lines.append(f"- {guardrail}")
    lines.append("")
    lines.append("No caption was rewritten or saved.")
    lines.append(plan.mutation_statement)
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


def _draft_exists(connection, post_id: int) -> bool:
    row = connection.execute("select 1 from drafts where id = ?", (post_id,)).fetchone()
    return row is not None


def _normalize_caption_feedback_token(value: str, *, field_name: str) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not token:
        raise ValueError(f"Caption feedback {field_name} must not be empty")
    return token[:60]


def _caption_feedback_rows(connection, *, post_id: Optional[int]) -> list[tuple[str, str, str]]:
    if post_id is not None:
        rows = connection.execute(
            """
            select sentiment, signal, note
            from caption_feedback
            where draft_id = ?
            order by id desc
            limit 10
            """,
            (post_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            select sentiment, signal, note
            from caption_feedback
            order by id desc
            limit 10
            """
        ).fetchall()
    return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]

def _current_caption(connection, post_id: Optional[int]) -> str:
    if post_id is None:
        return ""
    row = connection.execute("select caption from drafts where id = ?", (post_id,)).fetchone()
    return str(row[0] or "") if row else ""


def _accepted_caption_examples(connection) -> list[str]:
    rows = connection.execute(
        """
        select caption_options_json, accepted_caption_index
        from guided_draft_packages
        where accepted_at is not null
        order by accepted_at desc, id desc
        """
    ).fetchall()
    captions: list[str] = []
    for row in rows:
        try:
            options = json.loads(row[0] or "[]")
        except json.JSONDecodeError:
            options = []
        index = int(row[1] or 0)
        if 0 <= index < len(options) and str(options[index]).strip():
            captions.append(str(options[index]).strip())
    return captions


def _published_caption_examples(connection) -> list[str]:
    rows = connection.execute(
        """
        select coalesce(final_caption, '')
        from published_post_snapshots
        where final_caption is not null and trim(final_caption) != ''
        order by actual_published_at desc, id desc
        limit 5
        """
    ).fetchall()
    return [str(row[0]).strip() for row in rows if str(row[0]).strip()]


def _caption_local_patterns(
    *,
    accepted_caption_count: int,
    approved_post_count: int,
    published_snapshot_count: int,
    insight_snapshot_count: int,
    example_captions: list[str],
    caption_feedback: list[tuple[str, str, str]],
) -> list[str]:
    patterns: list[str] = []
    if accepted_caption_count:
        patterns.append("Accepted guided packages provide local evidence for caption tone and structure.")
    else:
        patterns.append("No accepted guided caption packages yet; style advice should remain generic.")
    if approved_post_count:
        patterns.append("Active content approvals indicate some caption directions already passed review.")
    if published_snapshot_count:
        patterns.append("Published snapshots provide real local examples of final Meta-bound captions.")
    if insight_snapshot_count:
        patterns.append("Insight snapshots exist, but use them conservatively until history is larger.")
    if caption_feedback:
        signal_counts: dict[str, int] = {}
        for sentiment, signal, _note in caption_feedback:
            key = f"{sentiment}:{signal}"
            signal_counts[key] = signal_counts.get(key, 0) + 1
        for key, count in sorted(signal_counts.items()):
            sentiment, signal = key.split(":", 1)
            patterns.append(f"Qualitative caption feedback: {count} {sentiment} note(s) tagged {signal}.")
    if any(_caption_starts_with_hook(caption) for caption in example_captions):
        patterns.append("Local examples often start with a concrete travel hook or planning promise.")
    return patterns


def _caption_recommended_direction(goal, current_caption: str, example_captions: list[str]) -> list[str]:
    directions = ["Lead with a concrete hook in the first sentence."]
    goal_terms = _goal_terms(goal)
    caption_terms = _terms(" ".join(example_captions + [current_caption]))
    if {"saveable", "route", "routes", "itinerary", "guide", "guides"}.intersection(goal_terms | caption_terms):
        directions.append("Lean into saveable route/itinerary framing when the photos support it.")
    if current_caption and len(current_caption.split()) < 8:
        directions.append("Expand the current caption with one specific why-this-moment-matters detail.")
    directions.append("Keep the caption human and specific; avoid generic travel-superlative filler.")
    return directions


def _caption_starts_with_hook(caption: str) -> bool:
    first_sentence = caption.strip().split(".", 1)[0].lower()
    hook_words = {"save", "start", "first", "before", "three", "one", "walk", "route"}
    return bool(_terms(first_sentence).intersection(hook_words))


def _list_scheduled_posts(connection) -> list[ScheduledPostSummary]:
    rows = connection.execute(
        """
        select d.id,
               d.scheduled_for,
               d.status,
               d.post_type,
               cg.title
        from drafts d
        left join candidate_groups cg on cg.id = d.candidate_group_id
        where d.scheduled_for is not null
          and d.status not in ('posted', 'published')
        order by d.scheduled_for asc, d.id asc
        """
    ).fetchall()
    return [
        ScheduledPostSummary(
            post_id=int(row[0]),
            scheduled_for=str(row[1]),
            status=str(row[2]),
            post_type=str(row[3]),
            title=str(row[4]) if row[4] is not None else None,
        )
        for row in rows
    ]


def _next_unscheduled_post_id(connection) -> Optional[int]:
    row = connection.execute(
        """
        select id
        from drafts
        where scheduled_for is null
          and status in ('ready_to_publish', 'approved', 'awaiting_publish_approval', 'drafting', 'needs_edits', 'awaiting_review')
        order by case status
            when 'ready_to_publish' then 0
            when 'approved' then 1
            when 'awaiting_publish_approval' then 2
            else 3
        end,
        id asc
        limit 1
        """
    ).fetchone()
    return int(row[0]) if row else None


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _weekday_label(value: datetime) -> str:
    return value.strftime("%A morning")


_PREFERRED_SCHEDULE_WEEKDAYS = {1, 3, 6}


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

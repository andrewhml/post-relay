from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from post_relay.account_preferences import get_active_account_preferences
from post_relay.pipeline_health import build_pipeline_health
from post_relay.recommendations import NO_MUTATION_STATEMENT
from post_relay.user_goals import get_active_user_goal


NO_SEND_STATEMENT = "No Discord, WhatsApp, or other message was sent. This is only a local draft check-in plan."


@dataclass(frozen=True)
class ScheduledCheckinDelivery:
    should_send: bool
    destination: str
    reason: str
    message: str
    progress_summary: str
    performance_summary: str
    safety_note: str
    mutation_statement: str = NO_MUTATION_STATEMENT


@dataclass(frozen=True)
class AgentCheckinPlan:
    recommended_checkin_cadence: str
    delivery_destination: str
    trigger_policy: str
    working_hours: str
    planners_enabled: bool
    trigger_reason: str
    draft_message: str
    user_action_requested: str
    why_useful_now: str
    no_send_statement: str = NO_SEND_STATEMENT
    mutation_statement: str = NO_MUTATION_STATEMENT


def build_scheduled_checkin_delivery(
    connection,
    *,
    now_iso: str | None = None,
    weekly_checkin: bool = False,
) -> ScheduledCheckinDelivery:
    preferences = get_active_account_preferences(connection)
    destination = preferences.checkin_delivery_destination if preferences and preferences.checkin_delivery_destination else "local_only"
    trigger_policy = preferences.checkin_trigger_policy if preferences and preferences.checkin_trigger_policy else "manual"
    health = build_pipeline_health(connection, now_iso=now_iso)
    plan = build_agent_checkin_plan(connection, now_iso=now_iso)
    progress_summary = _build_progress_summary(connection, health)
    performance_summary = _build_performance_summary(connection)
    safety_note = "No automatic posting, scheduling, approval, upload, analytics collection, R2, Meta, or workflow mutation was performed."

    if not _is_within_working_hours(preferences, now_iso=now_iso):
        return ScheduledCheckinDelivery(
            should_send=False,
            destination=destination,
            reason="outside_working_hours",
            message="",
            progress_summary=progress_summary,
            performance_summary=performance_summary,
            safety_note=safety_note,
        )

    meaningful_reviews = [review for review in health.user_needed_reviews if " is scheduled;" not in review]
    has_meaningful_trigger = bool(health.cadence_risk or meaningful_reviews or health.blocked_posts)
    should_send_weekly = weekly_checkin and trigger_policy in {"meaningful_plus_weekly", "weekly"}
    if not has_meaningful_trigger and not should_send_weekly:
        return ScheduledCheckinDelivery(
            should_send=False,
            destination=destination,
            reason="silent_no_meaningful_trigger",
            message="",
            progress_summary=progress_summary,
            performance_summary=performance_summary,
            safety_note=safety_note,
        )

    reason = "meaningful_trigger" if has_meaningful_trigger else "weekly_checkin"
    message = _build_scheduled_message(connection, plan, health, reason)
    return ScheduledCheckinDelivery(
        should_send=True,
        destination=destination,
        reason=reason,
        message=message,
        progress_summary=progress_summary,
        performance_summary=performance_summary,
        safety_note=safety_note,
    )


def render_scheduled_checkin_delivery(delivery: ScheduledCheckinDelivery, *, cron_output: bool = False) -> str:
    if not delivery.should_send:
        return "" if cron_output else f"No scheduled check-in sent: {delivery.reason}"
    return delivery.message


def build_agent_checkin_plan(connection, *, now_iso: str | None = None) -> AgentCheckinPlan:
    health = build_pipeline_health(connection, now_iso=now_iso)
    preferences = get_active_account_preferences(connection)
    goal = get_active_user_goal(connection)
    cadence = preferences.agent_checkin_cadence if preferences and preferences.agent_checkin_cadence else "manual"
    delivery_destination = preferences.checkin_delivery_destination if preferences and preferences.checkin_delivery_destination else "local_only"
    trigger_policy = preferences.checkin_trigger_policy if preferences and preferences.checkin_trigger_policy else "manual"
    working_hours = _format_working_hours(preferences)
    planners_enabled = bool(preferences and preferences.checkin_run_planners)
    trigger_reason = _select_trigger_reason(health, trigger_policy=trigger_policy)
    user_action = _select_user_action(health)
    draft_message = _build_draft_message(goal.title if goal else None, trigger_reason, health, user_action)
    why_useful_now = _why_useful_now(trigger_reason, health)
    return AgentCheckinPlan(
        recommended_checkin_cadence=cadence,
        delivery_destination=delivery_destination,
        trigger_policy=trigger_policy,
        working_hours=working_hours,
        planners_enabled=planners_enabled,
        trigger_reason=trigger_reason,
        draft_message=draft_message,
        user_action_requested=user_action,
        why_useful_now=why_useful_now,
    )


def render_agent_checkin_plan(connection) -> str:
    plan = build_agent_checkin_plan(connection)
    return "\n".join(
        [
            "Agent check-in plan",
            "Local draft only; no message was sent.",
            "",
            f"Recommended check-in cadence: {plan.recommended_checkin_cadence}",
            f"Delivery destination: {plan.delivery_destination}",
            f"Trigger policy: {plan.trigger_policy}",
            f"Working hours: {plan.working_hours}",
            f"Read-only planners may run: {'yes' if plan.planners_enabled else 'no'}",
            f"Trigger reason: {plan.trigger_reason}",
            "Draft message:",
            plan.draft_message,
            f"User action requested: {plan.user_action_requested}",
            f"Why useful now: {plan.why_useful_now}",
            plan.no_send_statement,
            "No automatic posting, scheduling, approval, messaging, upload, or analytics collection was performed.",
            plan.mutation_statement,
        ]
    )


def _select_trigger_reason(health, *, trigger_policy: str = "manual") -> str:
    no_future_content_risks = [risk for risk in health.cadence_risk if "no future content scheduled" in risk]
    if no_future_content_risks:
        return no_future_content_risks[0]
    if health.cadence_risk:
        return health.cadence_risk[0]
    if health.user_needed_reviews:
        return health.user_needed_reviews[0]
    if health.blocked_posts:
        return health.blocked_posts[0]
    if health.agent_preparable_work:
        return health.agent_preparable_work[0]
    if trigger_policy == "meaningful_plus_weekly":
        return "weekly check-in: share progress and performance even when no urgent content gap exists"
    return "No urgent trigger; this is a low-priority status check."


def _select_user_action(health) -> str:
    if health.user_needed_reviews:
        first = health.user_needed_reviews[0]
        post_id = _extract_post_id(first)
        if post_id is not None:
            return f"Review Post {post_id} or approve the suggested next pipeline action."
        return "Review the pending post or approve the suggested next pipeline action."
    if health.cadence_risk and health.agent_preparable_work:
        return "Approve the agent-preparable next work to reduce cadence risk."
    if health.blocked_posts:
        return "Resolve the blocked approval/edit item or confirm the agent should prepare a replacement."
    return "No user action is required unless you want the agent to prepare the next recommendation."


def _build_draft_message(goal_title: str | None, trigger_reason: str, health, user_action: str) -> str:
    goal_text = goal_title or "the active Post Relay goal"
    lines = [
        f"Quick Post Relay check-in for {goal_text}.",
        f"Trigger: {trigger_reason}.",
    ]
    if health.user_needed_reviews:
        lines.append(f"Needs you: {health.user_needed_reviews[0]}")
    if health.agent_preparable_work:
        lines.append(f"I can prepare next: {health.agent_preparable_work[0]}")
    lines.append(user_action)
    lines.append("Include progress and performance context from stored local analytics when available.")
    return " ".join(lines)


def _why_useful_now(trigger_reason: str, health) -> str:
    reasons = [f"This is useful now because {trigger_reason}"]
    if health.agent_preparable_work:
        reasons.append("there is agent-preparable work that can move the pipeline without publishing")
    if health.user_needed_reviews:
        reasons.append("a user review can unblock the next stage")
    return "; ".join(reasons) + "."


def _format_working_hours(preferences) -> str:
    if not preferences:
        return "<not set>"
    start = preferences.checkin_working_hours_start
    end = preferences.checkin_working_hours_end
    timezone = preferences.checkin_timezone
    if start and end and timezone:
        return f"{start}-{end} {timezone}"
    if start and end:
        return f"{start}-{end} <timezone not set>"
    if timezone:
        return f"working hours in {timezone}"
    return "<not set>"


def _build_scheduled_message(connection, plan: AgentCheckinPlan, health, reason: str) -> str:
    lines = ["**Post Relay check-in**", "", _build_checkin_lede(health, reason)]
    preparable = _first_concrete_preparable_work(health.agent_preparable_work)
    if preparable:
        title, candidate_label = preparable
        lines.extend(["", "**I can prepare next**", title, candidate_label])
    lines.extend(["", "**Pipeline**"])
    lines.extend(_build_pipeline_bullets(connection, health))
    lines.extend(["", "**Your move**", _build_action_line(plan, health, preparable)])
    lines.extend(["", "_Local-only. Nothing was posted, scheduled, uploaded, or sent to Instagram._"])
    return "\n".join(lines)


def _build_checkin_lede(health, reason: str) -> str:
    meaningful_reviews = [review for review in health.user_needed_reviews if " is scheduled;" not in review]
    if meaningful_reviews:
        post_id = _extract_post_id(meaningful_reviews[0])
        if post_id is not None:
            return f"Post #{post_id} needs your review."
        return "A post needs your review."
    no_future_risk = next((risk for risk in health.cadence_risk if "no future content scheduled" in risk), None)
    if no_future_risk:
        days = _extract_between(no_future_risk, "was ", " day(s) ago")
        if days:
            return f"You have no future posts scheduled. Last post was {days} days ago."
        return "You have no future posts scheduled."
    scheduled = _scheduled_count(health)
    if scheduled:
        plural = "post" if scheduled == 1 else "posts"
        return f"You have {scheduled} {plural} scheduled."
    if reason == "weekly_checkin":
        return "Your Post Relay pipeline is steady."
    if health.cadence_risk:
        return _sentence_case(health.cadence_risk[0]) + "."
    if health.blocked_posts:
        return health.blocked_posts[0]
    return "Post Relay is ready for the next move."


def _build_pipeline_bullets(connection, health) -> list[str]:
    published = _scalar(connection, "select count(*) from published_post_snapshots")
    scheduled = _scheduled_count(health)
    reviews = len(health.user_needed_reviews)
    candidates = health.candidate_groups_without_posts
    bullets = [
        f"- {_plural_count(published, 'post')} published",
        f"- {scheduled} scheduled",
        f"- {reviews} {'review' if reviews == 1 else 'reviews'} waiting on you",
        f"- {candidates} {'candidate' if candidates == 1 else 'candidates'} ready",
    ]
    performance = _latest_post_performance_line(connection)
    if performance:
        bullets.append(f"- Latest post: {performance}")
    return bullets


def _latest_post_performance_line(connection) -> str | None:
    insight_row = connection.execute(
        """
        select metrics_json
        from media_insight_snapshots
        order by collected_at desc, id desc
        limit 1
        """
    ).fetchone()
    if not insight_row:
        return None
    metrics = json.loads(insight_row[0] or "{}")
    reach = _format_int(metrics.get("reach", 0))
    likes = _format_int(metrics.get("likes", 0))
    comments = _format_int(metrics.get("comments", 0))
    saves = _format_int(metrics.get("saved", metrics.get("saves", 0)))
    return f"{reach} reach, {likes} likes, {comments} comments, {saves} saves"


def _first_concrete_preparable_work(agent_preparable_work: list[str]) -> tuple[str, str] | None:
    for item in agent_preparable_work:
        if item.startswith("Candidate ") and " can become a draft: " in item:
            candidate_label = item.split(" can become a draft: ", 1)[0]
            title = _display_candidate_title(item.split(" can become a draft: ", 1)[1])
            return title, candidate_label
    return None


def _build_action_line(plan: AgentCheckinPlan, health, preparable: tuple[str, str] | None) -> str:
    actions: list[str] = []
    meaningful_reviews = [review for review in health.user_needed_reviews if " is scheduled;" not in review]
    if meaningful_reviews:
        post_id = _extract_post_id(meaningful_reviews[0])
        if post_id is not None:
            actions.append(f"`review post {post_id}`")
    if preparable:
        title, _candidate_label = preparable
        actions.append(f"`prepare {_prepare_reply_slug(title)}`")
    if actions:
        return "Reply " + " or ".join(actions) + "."
    return plan.user_action_requested


def _display_candidate_title(title: str) -> str:
    cleaned = title.strip().rstrip(".")
    for separator in [" — ", " - "]:
        if separator in cleaned:
            cleaned = cleaned.split(separator, 1)[0].strip()
    return cleaned


def _prepare_reply_slug(title: str) -> str:
    if title.startswith("After Road to "):
        return title.split("After Road to ", 1)[1].strip()
    return title


def _scheduled_count(health) -> int:
    return health.stage_counts.get("scheduled", 0) + health.stage_counts.get("awaiting_publish_approval", 0)


def _plural_count(value: int, noun: str) -> str:
    return f"{value} {noun if value == 1 else noun + 's'}"


def _format_int(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _extract_between(text: str, start: str, end: str) -> str | None:
    if start not in text:
        return None
    after_start = text.split(start, 1)[1]
    if end not in after_start:
        return None
    return after_start.split(end, 1)[0]


def _sentence_case(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _build_progress_summary(connection, health) -> str:
    published = _scalar(connection, "select count(*) from published_post_snapshots")
    scheduled = health.stage_counts.get("scheduled", 0) + health.stage_counts.get("awaiting_publish_approval", 0)
    in_review = len(health.user_needed_reviews)
    candidates = health.candidate_groups_without_posts
    return f"{published} published snapshots stored, {scheduled} upcoming/approval-ready posts, {in_review} user-needed reviews, {candidates} candidate groups not yet drafted."


def _build_performance_summary(connection) -> str:
    follower_row = connection.execute(
        """
        select follower_count, media_count, collected_at
        from account_metric_snapshots
        order by collected_at desc, id desc
        limit 1
        """
    ).fetchone()
    insight_row = connection.execute(
        """
        select metrics_json, collected_at
        from media_insight_snapshots
        order by collected_at desc, id desc
        limit 1
        """
    ).fetchone()
    parts: list[str] = []
    if follower_row:
        followers = "unknown" if follower_row[0] is None else int(follower_row[0])
        media_count = "unknown" if follower_row[1] is None else int(follower_row[1])
        parts.append(f"latest account snapshot: {followers} followers, {media_count} media")
    if insight_row:
        metrics = json.loads(insight_row[0] or "{}")
        compact_metrics = []
        for key in ["reach", "saved", "saves", "likes", "comments", "shares"]:
            if key in metrics:
                compact_metrics.append(f"{key}={metrics[key]}")
        if compact_metrics:
            parts.append("latest post insights: " + ", ".join(compact_metrics))
    return "; ".join(parts) if parts else "No stored local performance snapshots yet."


def _is_within_working_hours(preferences, *, now_iso: str | None) -> bool:
    if not preferences:
        return True
    start = preferences.checkin_working_hours_start
    end = preferences.checkin_working_hours_end
    if not start or not end:
        return True
    now = _parse_now(now_iso)
    timezone_name = preferences.checkin_timezone
    if timezone_name:
        try:
            now = now.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            return True
    current_minutes = now.hour * 60 + now.minute
    start_minutes = _time_to_minutes(start)
    end_minutes = _time_to_minutes(end)
    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes <= end_minutes
    return current_minutes >= start_minutes or current_minutes <= end_minutes


def _parse_now(now_iso: str | None) -> datetime:
    if not now_iso:
        return datetime.now(timezone.utc).astimezone()
    parsed = datetime.fromisoformat(now_iso)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _time_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _scalar(connection, query: str) -> int:
    row = connection.execute(query).fetchone()
    return int(row[0] or 0)


def _extract_post_id(text: str) -> int | None:
    parts = text.split()
    for index, part in enumerate(parts):
        if part.lower() == "post" and index + 1 < len(parts):
            candidate = parts[index + 1].strip("#.:,;")
            if candidate.isdigit():
                return int(candidate)
    return None

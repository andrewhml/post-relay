from __future__ import annotations

from dataclasses import dataclass

from post_relay.account_preferences import get_active_account_preferences
from post_relay.pipeline_health import build_pipeline_health
from post_relay.recommendations import NO_MUTATION_STATEMENT
from post_relay.user_goals import get_active_user_goal


NO_SEND_STATEMENT = "No Discord, WhatsApp, or other message was sent. This is only a local draft check-in plan."


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


def build_agent_checkin_plan(connection) -> AgentCheckinPlan:
    health = build_pipeline_health(connection)
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


def _extract_post_id(text: str) -> int | None:
    parts = text.split()
    for index, part in enumerate(parts):
        if part.lower() == "post" and index + 1 < len(parts):
            candidate = parts[index + 1].strip("#.:,;")
            if candidate.isdigit():
                return int(candidate)
    return None

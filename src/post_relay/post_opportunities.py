from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from post_relay.drafts import CandidateNotFound, create_draft_from_candidate
from post_relay.repository import (
    PostOpportunityRecord,
    create_post_opportunity_record,
    get_active_post_opportunity_by_trigger,
    get_candidate_group,
    get_post_opportunity,
    update_post_opportunity_status,
)


VALID_TRIGGER_TYPES = {
    "user_dm",
    "new_media",
    "cadence_due",
    "inactivity",
    "life_event",
    "holiday_event",
    "current_event",
    "trend_window",
}

TERMINAL_STATUSES = {"dismissed", "snoozed", "converted_to_draft"}


class PostOpportunityError(ValueError):
    pass


@dataclass(frozen=True)
class PostOpportunityCommandResult:
    opportunity: PostOpportunityRecord
    action: str
    reused_existing: bool = False

    def to_text(self) -> str:
        lines = [
            f"Post opportunity #{self.opportunity.id}: {self.opportunity.title}",
            f"Trigger: {self.opportunity.trigger_type} / {self.opportunity.trigger_key}",
            f"Status: {self.opportunity.status}",
        ]
        if self.reused_existing:
            lines.append("Reused existing active opportunity for this trigger key.")
        if self.opportunity.candidate_group_id is not None:
            lines.append(f"Candidate group: #{self.opportunity.candidate_group_id}")
        if self.opportunity.draft_id is not None:
            lines.append(f"Linked post: #{self.opportunity.draft_id}")
        if self.opportunity.snoozed_until is not None:
            lines.append(f"Snoozed until: {self.opportunity.snoozed_until}")
        if self.opportunity.dismissed_reason is not None:
            lines.append(f"Dismissed reason: {self.opportunity.dismissed_reason}")
        lines.extend(
            [
                f"Summary: {self.opportunity.summary}",
                f"Rationale: {self.opportunity.rationale}",
                f"Suggested next action: {self.opportunity.suggested_next_action}",
                f"Action: {self.action}",
                "No Discord or Meta network calls were made.",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class ProactiveOpportunityDmPlan:
    opportunity: PostOpportunityRecord
    suggested_dm_copy: str
    requires_explicit_send_authorization: bool = True

    def to_text(self) -> str:
        lines = [
            f"Proactive opportunity DM plan for opportunity #{self.opportunity.id}: {self.opportunity.title}",
            f"Status: {self.opportunity.status}",
            f"Trigger: {self.opportunity.trigger_type} / {self.opportunity.trigger_key}",
        ]
        if self.opportunity.candidate_group_id is not None:
            lines.append(f"Candidate group: #{self.opportunity.candidate_group_id}")
        if self.opportunity.draft_id is not None:
            lines.append(f"Linked post: #{self.opportunity.draft_id}")
        lines.extend(
            [
                f"Summary: {self.opportunity.summary}",
                f"Rationale: {self.opportunity.rationale}",
                "Suggested DM copy:",
                self.suggested_dm_copy,
                "Reply with one of: yes / snooze / dismiss",
                "Operator controls:",
                f"  - Convert if Andrew says yes: post-relay opportunities convert-to-draft --opportunity-id {self.opportunity.id} --db data/post_relay.sqlite",
                f"  - Snooze if timing is wrong: post-relay opportunities snooze --opportunity-id {self.opportunity.id} --until <ISO_TIME> --db data/post_relay.sqlite",
                f"  - Dismiss if not relevant: post-relay opportunities dismiss --opportunity-id {self.opportunity.id} --reason <REASON> --db data/post_relay.sqlite",
                f"  - After an explicitly authorized live send, record it locally: post-relay opportunities mark-dm-sent --opportunity-id {self.opportunity.id} --db data/post_relay.sqlite",
                "Requires explicit operator authorization before any Discord send.",
                "No Discord, R2, or Meta network calls were made.",
            ]
        )
        return "\n".join(lines)


def create_post_opportunity(
    connection,
    *,
    trigger_type: str,
    trigger_key: str,
    title: str,
    summary: str,
    rationale: str,
    suggested_next_action: str,
    candidate_group_id: Optional[int] = None,
    draft_id: Optional[int] = None,
    due_at: Optional[str] = None,
    expires_at: Optional[str] = None,
) -> PostOpportunityRecord:
    trigger_type = trigger_type.strip()
    trigger_key = trigger_key.strip()
    if trigger_type not in VALID_TRIGGER_TYPES:
        raise PostOpportunityError(
            f"Unsupported opportunity trigger type '{trigger_type}'. Expected one of: {', '.join(sorted(VALID_TRIGGER_TYPES))}"
        )
    if not trigger_key:
        raise PostOpportunityError("Opportunity trigger key must not be empty")
    if candidate_group_id is not None and get_candidate_group(connection, candidate_group_id) is None:
        raise PostOpportunityError(f"Candidate group #{candidate_group_id} was not found")

    existing = get_active_post_opportunity_by_trigger(
        connection, trigger_type=trigger_type, trigger_key=trigger_key
    )
    if existing is not None:
        return existing

    return create_post_opportunity_record(
        connection,
        trigger_type=trigger_type,
        trigger_key=trigger_key,
        title=_sanitize_text(title, 140),
        summary=_sanitize_text(summary, 240),
        rationale=_sanitize_text(rationale, 320),
        suggested_next_action=_sanitize_text(suggested_next_action, 240),
        candidate_group_id=candidate_group_id,
        draft_id=draft_id,
        due_at=due_at,
        expires_at=expires_at,
    )


def create_post_opportunity_result(connection, **kwargs) -> PostOpportunityCommandResult:
    existing = get_active_post_opportunity_by_trigger(
        connection,
        trigger_type=kwargs.get("trigger_type", "").strip(),
        trigger_key=kwargs.get("trigger_key", "").strip(),
    )
    opportunity = create_post_opportunity(connection, **kwargs)
    return PostOpportunityCommandResult(
        opportunity=opportunity,
        action="created local opportunity" if existing is None else "deduped local opportunity",
        reused_existing=existing is not None,
    )


def dismiss_post_opportunity(
    connection,
    opportunity_id: int,
    *,
    reason: Optional[str] = None,
) -> PostOpportunityRecord:
    opportunity = _require_opportunity(connection, opportunity_id)
    return update_post_opportunity_status(
        connection,
        opportunity_id,
        status="dismissed",
        dismissed_reason=_sanitize_text(reason or "dismissed", 180),
    )


def snooze_post_opportunity(
    connection,
    opportunity_id: int,
    *,
    snoozed_until: str,
) -> PostOpportunityRecord:
    if not snoozed_until.strip():
        raise PostOpportunityError("Snoozed-until value must not be empty")
    opportunity = _require_opportunity(connection, opportunity_id)
    if opportunity.status in TERMINAL_STATUSES:
        raise PostOpportunityError(f"Opportunity #{opportunity_id} is already {opportunity.status}")
    return update_post_opportunity_status(
        connection,
        opportunity_id,
        status="snoozed",
        snoozed_until=snoozed_until.strip(),
    )


def convert_post_opportunity_to_draft(connection, opportunity_id: int) -> PostOpportunityRecord:
    opportunity = _require_opportunity(connection, opportunity_id)
    if opportunity.status == "converted_to_draft":
        return opportunity
    if opportunity.candidate_group_id is None:
        raise PostOpportunityError("Opportunity must be linked to a candidate group before conversion")
    try:
        draft = create_draft_from_candidate(connection, opportunity.candidate_group_id)
    except CandidateNotFound as error:
        raise PostOpportunityError(str(error)) from error
    return update_post_opportunity_status(
        connection,
        opportunity_id,
        status="converted_to_draft",
        draft_id=draft.id,
    )


def plan_proactive_opportunity_dm(connection, opportunity_id: int) -> ProactiveOpportunityDmPlan:
    opportunity = _require_opportunity(connection, opportunity_id)
    if opportunity.status not in {"new", "dm_sent"}:
        raise PostOpportunityError(
            f"Opportunity #{opportunity_id} is {opportunity.status} and cannot be planned for proactive DM"
        )
    suggested_dm_copy = _build_proactive_dm_copy(opportunity)
    return ProactiveOpportunityDmPlan(opportunity=opportunity, suggested_dm_copy=suggested_dm_copy)


def mark_post_opportunity_dm_sent(connection, opportunity_id: int) -> PostOpportunityRecord:
    opportunity = _require_opportunity(connection, opportunity_id)
    if opportunity.status == "dm_sent":
        return opportunity
    if opportunity.status != "new":
        raise PostOpportunityError(
            f"Opportunity #{opportunity_id} is {opportunity.status} and cannot be marked DM sent"
        )
    marked = update_post_opportunity_status(connection, opportunity_id, status="dm_sent")
    if marked is None:
        raise PostOpportunityError(f"Opportunity #{opportunity_id} was not found")
    return marked


def _build_proactive_dm_copy(opportunity: PostOpportunityRecord) -> str:
    lead = f"Potential post idea: {opportunity.title}."
    summary = opportunity.summary.rstrip(".") + "."
    next_action = opportunity.suggested_next_action.rstrip(".") + "."
    return " ".join(
        [
            lead,
            summary,
            next_action,
            "Want me to start this, snooze it, or dismiss it?",
        ]
    )


def _require_opportunity(connection, opportunity_id: int) -> PostOpportunityRecord:
    opportunity = get_post_opportunity(connection, opportunity_id)
    if opportunity is None:
        raise PostOpportunityError(f"Opportunity #{opportunity_id} was not found")
    return opportunity


def _sanitize_text(value: str, limit: int) -> str:
    sanitized = re.sub(r"(?i)(token|secret|password|key)\s*=\s*\S+", r"\1=[REDACTED]", value or "")
    sanitized = re.sub(r"https?://\S+", "[REDACTED-URL]", sanitized)
    sanitized = " ".join(sanitized.split()).strip()
    if not sanitized:
        raise PostOpportunityError("Opportunity text fields must not be empty")
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[: limit - 1].rstrip() + "…"

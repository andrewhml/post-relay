from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from post_relay.post_opportunities import create_post_opportunity
from post_relay.repository import CandidateGroupRecord, PostOpportunityRecord, list_candidate_groups


@dataclass(frozen=True)
class PlannedOpportunity:
    trigger_type: str
    trigger_key: str
    title: str
    summary: str
    rationale: str
    suggested_next_action: str
    candidate_group_id: Optional[int] = None


@dataclass(frozen=True)
class SkippedOpportunity:
    trigger_type: str
    trigger_key: str
    reason: str


@dataclass(frozen=True)
class OpportunityCheckResult:
    planned: list[PlannedOpportunity]
    created: list[PostOpportunityRecord]
    skipped: list[SkippedOpportunity]
    dry_run: bool

    @property
    def created_count(self) -> int:
        return len(self.created)

    def to_text(self) -> str:
        mode = "Dry run" if self.dry_run else "Executed"
        lines = [
            f"{mode}: planned {len(self.planned)} post opportunity check result(s); created {self.created_count} local record(s).",
        ]
        if self.planned:
            lines.append("Planned opportunities:")
            for planned in self.planned:
                candidate = (
                    f", candidate #{planned.candidate_group_id}"
                    if planned.candidate_group_id is not None
                    else ""
                )
                lines.append(
                    f"  - {planned.trigger_type} / {planned.trigger_key}: {planned.title}{candidate}"
                )
        if self.created:
            lines.append("Created opportunities:")
            for created in self.created:
                lines.append(f"  - #{created.id} {created.title} — {created.trigger_type}")
        if self.skipped:
            lines.append("Skipped opportunities:")
            for skipped in self.skipped:
                lines.append(f"  - {skipped.trigger_type} / {skipped.trigger_key}: {skipped.reason}")
        lines.append("No Discord or Meta network calls were made.")
        return "\n".join(lines)


def plan_opportunity_checks(
    connection,
    *,
    now: str,
    cadence_due_after_days: int = 3,
    inactivity_after_days: int = 14,
    include_new_media: bool = True,
    max_new_media_candidates: int = 5,
    manual_trigger_type: Optional[str] = None,
    manual_trigger_key: Optional[str] = None,
    manual_title: Optional[str] = None,
    manual_summary: Optional[str] = None,
    manual_rationale: Optional[str] = None,
    manual_suggested_next_action: Optional[str] = None,
) -> OpportunityCheckResult:
    return _run_opportunity_checks(
        connection,
        now=now,
        cadence_due_after_days=cadence_due_after_days,
        inactivity_after_days=inactivity_after_days,
        include_new_media=include_new_media,
        max_new_media_candidates=max_new_media_candidates,
        manual_trigger_type=manual_trigger_type,
        manual_trigger_key=manual_trigger_key,
        manual_title=manual_title,
        manual_summary=manual_summary,
        manual_rationale=manual_rationale,
        manual_suggested_next_action=manual_suggested_next_action,
        execute=False,
    )


def execute_opportunity_checks(
    connection,
    *,
    now: str,
    cadence_due_after_days: int = 3,
    inactivity_after_days: int = 14,
    include_new_media: bool = True,
    max_new_media_candidates: int = 5,
    manual_trigger_type: Optional[str] = None,
    manual_trigger_key: Optional[str] = None,
    manual_title: Optional[str] = None,
    manual_summary: Optional[str] = None,
    manual_rationale: Optional[str] = None,
    manual_suggested_next_action: Optional[str] = None,
) -> OpportunityCheckResult:
    result = _run_opportunity_checks(
        connection,
        now=now,
        cadence_due_after_days=cadence_due_after_days,
        inactivity_after_days=inactivity_after_days,
        include_new_media=include_new_media,
        max_new_media_candidates=max_new_media_candidates,
        manual_trigger_type=manual_trigger_type,
        manual_trigger_key=manual_trigger_key,
        manual_title=manual_title,
        manual_summary=manual_summary,
        manual_rationale=manual_rationale,
        manual_suggested_next_action=manual_suggested_next_action,
        execute=True,
    )
    connection.commit()
    return result


def _run_opportunity_checks(
    connection,
    *,
    now: str,
    cadence_due_after_days: int,
    inactivity_after_days: int,
    include_new_media: bool,
    max_new_media_candidates: int,
    manual_trigger_type: Optional[str],
    manual_trigger_key: Optional[str],
    manual_title: Optional[str],
    manual_summary: Optional[str],
    manual_rationale: Optional[str],
    manual_suggested_next_action: Optional[str],
    execute: bool,
) -> OpportunityCheckResult:
    now_dt = _parse_iso_datetime(now)
    planned: list[PlannedOpportunity] = []
    skipped: list[SkippedOpportunity] = []

    if include_new_media:
        for candidate in _candidate_groups_without_drafts(connection)[:max_new_media_candidates]:
            _add_if_allowed(
                connection,
                planned,
                skipped,
                now_dt=now_dt,
                opportunity=_planned_new_media_opportunity(candidate),
            )

    history = _latest_scheduled_or_posted_at(connection)
    if history is None:
        if not planned and not skipped:
            _add_if_allowed(
                connection,
                planned,
                skipped,
                now_dt=now_dt,
                opportunity=PlannedOpportunity(
                    trigger_type="inactivity",
                    trigger_key="no-local-scheduled-or-post-history",
                    title="No recent local posting history",
                    summary="No scheduled or posted post history is recorded locally yet.",
                    rationale=f"Local inactivity check found no scheduled/posted history; threshold is {inactivity_after_days} days.",
                    suggested_next_action="Offer one reviewed backlog candidate before sending any proactive DM.",
                ),
            )
    else:
        days_since_history = max(0, (now_dt.date() - history.date()).days)
        if days_since_history >= cadence_due_after_days:
            _add_if_allowed(
                connection,
                planned,
                skipped,
                now_dt=now_dt,
                opportunity=PlannedOpportunity(
                    trigger_type="cadence_due",
                    trigger_key=f"cadence-due-{now_dt.date().isoformat()}",
                    title="Posting cadence check is due",
                    summary="A local cadence check says it may be time to prepare another reviewed post.",
                    rationale=f"The last scheduled/posted item was {days_since_history} days ago; threshold is {cadence_due_after_days} days.",
                    suggested_next_action="Pick one strong backlog candidate and ask Andrew whether to turn it into a draft.",
                ),
            )

    manual = _manual_opportunity(
        manual_trigger_type=manual_trigger_type,
        manual_trigger_key=manual_trigger_key,
        manual_title=manual_title,
        manual_summary=manual_summary,
        manual_rationale=manual_rationale,
        manual_suggested_next_action=manual_suggested_next_action,
    )
    if manual is not None:
        _add_if_allowed(connection, planned, skipped, now_dt=now_dt, opportunity=manual)

    created: list[PostOpportunityRecord] = []
    if execute:
        for opportunity in planned:
            created.append(
                create_post_opportunity(
                    connection,
                    trigger_type=opportunity.trigger_type,
                    trigger_key=opportunity.trigger_key,
                    title=opportunity.title,
                    summary=opportunity.summary,
                    rationale=opportunity.rationale,
                    suggested_next_action=opportunity.suggested_next_action,
                    candidate_group_id=opportunity.candidate_group_id,
                )
            )

    return OpportunityCheckResult(
        planned=planned,
        created=created,
        skipped=skipped,
        dry_run=not execute,
    )


def _candidate_groups_without_drafts(connection) -> list[CandidateGroupRecord]:
    drafted_ids = {
        int(row[0])
        for row in connection.execute("select candidate_group_id from drafts").fetchall()
    }
    return [candidate for candidate in list_candidate_groups(connection) if candidate.id not in drafted_ids]


def _planned_new_media_opportunity(candidate: CandidateGroupRecord) -> PlannedOpportunity:
    photo_plural = "" if candidate.photo_count == 1 else "s"
    return PlannedOpportunity(
        trigger_type="new_media",
        trigger_key=f"candidate:{candidate.id}",
        title=f"New candidate media: {candidate.title}",
        summary=f"Candidate group #{candidate.id} has {candidate.photo_count} processed photo{photo_plural} ready for review.",
        rationale=f"Indexed processed media exists without a post yet; recommended post type is {candidate.post_type_recommendation}.",
        suggested_next_action="Ask Andrew whether to start a post conversation from this candidate before sending any proactive DM.",
        candidate_group_id=candidate.id,
    )


def _manual_opportunity(
    *,
    manual_trigger_type: Optional[str],
    manual_trigger_key: Optional[str],
    manual_title: Optional[str],
    manual_summary: Optional[str],
    manual_rationale: Optional[str],
    manual_suggested_next_action: Optional[str],
) -> Optional[PlannedOpportunity]:
    manual_values = [
        manual_trigger_type,
        manual_trigger_key,
        manual_title,
        manual_summary,
        manual_rationale,
        manual_suggested_next_action,
    ]
    if all(value is None for value in manual_values):
        return None
    if any(value is None or not value.strip() for value in manual_values):
        raise ValueError("Manual opportunity checks require all manual trigger/title/summary/rationale/next-action fields")
    return PlannedOpportunity(
        trigger_type=manual_trigger_type.strip(),
        trigger_key=manual_trigger_key.strip(),
        title=manual_title.strip(),
        summary=manual_summary.strip(),
        rationale=manual_rationale.strip(),
        suggested_next_action=manual_suggested_next_action.strip(),
    )


def _add_if_allowed(
    connection,
    planned: list[PlannedOpportunity],
    skipped: list[SkippedOpportunity],
    *,
    now_dt: datetime,
    opportunity: PlannedOpportunity,
) -> None:
    prior = _latest_opportunity_for_trigger(connection, opportunity.trigger_type, opportunity.trigger_key)
    if prior is not None:
        reason = _skip_reason_for_prior_opportunity(prior, now_dt)
        if reason is not None:
            skipped.append(
                SkippedOpportunity(
                    trigger_type=opportunity.trigger_type,
                    trigger_key=opportunity.trigger_key,
                    reason=reason,
                )
            )
            return
    planned.append(opportunity)


def _skip_reason_for_prior_opportunity(opportunity: PostOpportunityRecord, now_dt: datetime) -> Optional[str]:
    if opportunity.status in {"new", "dm_sent"}:
        return f"already has an active opportunity #{opportunity.id}"
    if opportunity.status == "snoozed" and opportunity.snoozed_until:
        snoozed_until = _parse_iso_datetime(opportunity.snoozed_until)
        if snoozed_until > now_dt:
            return f"snoozed until {opportunity.snoozed_until}"
    if opportunity.status == "dismissed":
        return f"dismissed as opportunity #{opportunity.id}"
    if opportunity.status == "converted_to_draft":
        return f"already converted to post #{opportunity.draft_id}"
    return None


def _latest_opportunity_for_trigger(
    connection, trigger_type: str, trigger_key: str
) -> Optional[PostOpportunityRecord]:
    row = connection.execute(
        """
        select id, trigger_type, trigger_key, title, summary, rationale,
               suggested_next_action, status, candidate_group_id, draft_id,
               due_at, expires_at, snoozed_until, dismissed_reason
        from post_opportunities
        where trigger_type = ? and trigger_key = ?
        order by id desc
        limit 1
        """,
        (trigger_type, trigger_key),
    ).fetchone()
    if row is None:
        return None
    return PostOpportunityRecord(
        id=int(row[0]),
        trigger_type=row[1],
        trigger_key=row[2],
        title=row[3],
        summary=row[4],
        rationale=row[5],
        suggested_next_action=row[6],
        status=row[7],
        candidate_group_id=row[8],
        draft_id=row[9],
        due_at=row[10],
        expires_at=row[11],
        snoozed_until=row[12],
        dismissed_reason=row[13],
    )


def _latest_scheduled_or_posted_at(connection) -> Optional[datetime]:
    row = connection.execute(
        """
        select max(scheduled_for)
        from drafts
        where scheduled_for is not null
          and status in ('scheduled', 'awaiting_publish_approval', 'ready_to_publish', 'posted')
        """
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return _parse_iso_datetime(row[0])


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)

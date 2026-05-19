from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from post_relay.repository import (
    DraftRecord,
    ConversationThreadRecord,
    get_active_conversation_thread_for_channel,
    get_draft,
    list_active_approvals,
    list_candidate_group_photo_items,
    list_drafts,
)
from post_relay.scheduled_posts import build_scheduled_post_feedback
from post_relay.state import ApprovalType, DraftState


class DmNextActionError(ValueError):
    pass


@dataclass(frozen=True)
class DmNextActionPlan:
    action: str
    summary: str
    command: Optional[str]
    draft_id: Optional[int]
    thread_id: Optional[int]
    status: Optional[str]
    rationale: list[str]
    safety_notes: list[str]
    scheduled_posts_text: Optional[str] = None

    def to_text(self) -> str:
        lines = ["Post Relay DM next action", f"Action: {self.action}", self.summary]
        if self.thread_id is not None:
            lines.append(f"Conversation thread: #{self.thread_id}")
        if self.draft_id is not None:
            lines.append(f"Post: #{self.draft_id}")
        if self.status is not None:
            lines.append(f"Post status: {self.status}")
        if self.rationale:
            lines.append("Why:")
            lines.extend(f"  - {item}" for item in self.rationale)
        if self.command:
            lines.append("Suggested command:")
            lines.append(f"  {self.command}")
        if self.scheduled_posts_text:
            lines.append(self.scheduled_posts_text)
        if self.safety_notes:
            lines.append("Safety:")
            lines.extend(f"  - {item}" for item in self.safety_notes)
        lines.append("No Discord, Meta, or R2 network calls were made.")
        return "\n".join(lines)


def build_dm_next_action_plan(
    connection,
    *,
    draft_id: Optional[int] = None,
    discord_channel_id: Optional[str] = None,
    target_count: int = 5,
) -> DmNextActionPlan:
    thread = _resolve_thread(connection, discord_channel_id)
    resolved_draft_id = draft_id if draft_id is not None else (thread.draft_id if thread else None)

    if resolved_draft_id is None:
        if thread is not None:
            return _with_schedule_feedback(
                connection,
                DmNextActionPlan(
                    action="candidate_selection",
                    summary="Ask Andrew to choose one candidate or provide narrower folder/date/location details.",
                    command='post-relay dm intake --message "choose candidate #<id>" --discord-channel-id <dm-channel-id> --db data/post_relay.sqlite',
                    draft_id=None,
                    thread_id=thread.id,
                    status=None,
                    rationale=[
                        "An active private-DM thread exists but it is not linked to a post yet.",
                        "Candidate selection must happen before photo selection, copy, scheduling, or approvals.",
                    ],
                    safety_notes=_base_safety_notes(),
                ),
            )
        drafts = list_drafts(connection)
        if drafts:
            latest = drafts[-1]
            return _with_schedule_feedback(connection, _plan_for_draft(connection, latest, thread, target_count=target_count))
        return _with_schedule_feedback(
            connection,
            DmNextActionPlan(
                action="start_intake",
                summary="Wait for Andrew to initiate a private DM or run local intake with his requested trip/set.",
                command='post-relay dm intake --message "start a post about <trip or folder>" --discord-channel-id <dm-channel-id> --db data/post_relay.sqlite',
                draft_id=None,
                thread_id=None,
                status=None,
                rationale=["No post id or active linked DM thread was provided."],
                safety_notes=_base_safety_notes(),
            ),
        )

    draft = get_draft(connection, resolved_draft_id)
    if draft is None:
        raise DmNextActionError(f"Post #{resolved_draft_id} was not found")
    return _with_schedule_feedback(connection, _plan_for_draft(connection, draft, thread, target_count=target_count))


def _resolve_thread(connection, discord_channel_id: Optional[str]) -> Optional[ConversationThreadRecord]:
    if discord_channel_id is None:
        return None
    return get_active_conversation_thread_for_channel(connection, discord_channel_id)


def _with_schedule_feedback(connection, plan: DmNextActionPlan) -> DmNextActionPlan:
    feedback = build_scheduled_post_feedback(connection)
    if not feedback.items:
        return plan
    return replace(plan, scheduled_posts_text=feedback.to_text())


def _plan_for_draft(
    connection,
    draft: DraftRecord,
    thread: Optional[ConversationThreadRecord],
    *,
    target_count: int,
) -> DmNextActionPlan:
    active_approval_types = {approval.approval_type for approval in list_active_approvals(connection, draft.id)}
    media_count = len(list_candidate_group_photo_items(connection, draft.candidate_group_id, included_only=True))
    status = draft.status

    if status in {DraftState.DRAFTING.value, DraftState.NEEDS_EDITS.value}:
        summary = "Send/prepare a private DM photo selection prompt, then build the guided caption package after selection is settled."
        return DmNextActionPlan(
            action="media_selection",
            summary=summary,
            command=(
                f"post-relay discord dm-selection-send --draft-id {draft.id} "
                f"--target-count {min(max(target_count, 1), max(media_count, 1))} --db data/post_relay.sqlite"
            ),
            draft_id=draft.id,
            thread_id=thread.id if thread else None,
            status=status,
            rationale=[
                f"Post has {media_count} included candidate photo(s).",
                "Photo ordering/lead choice should be reviewed before final copy and content approval.",
                f"After selection, draft copy locally with: post-relay drafts guided-package-plan --draft-id {draft.id} --db data/post_relay.sqlite",
            ],
            safety_notes=_base_safety_notes(),
        )

    if status == DraftState.AWAITING_REVIEW.value:
        return DmNextActionPlan(
            action="content_review",
            summary="Ask Andrew to approve or edit the post content direction before queueing.",
            command=f"post-relay drafts approve --draft-id {draft.id} --approved-by andrew --notes \"Content direction approved\" --db data/post_relay.sqlite",
            draft_id=draft.id,
            thread_id=thread.id if thread else None,
            status=status,
            rationale=["The post is submitted for content review but not approved for queueing yet."],
            safety_notes=_base_safety_notes(),
        )

    if status == DraftState.APPROVED_FOR_QUEUE.value:
        return DmNextActionPlan(
            action="schedule_prompt",
            summary="Send a private-DM scheduling prompt; content approval is active and the next gate is queue scheduling.",
            command=f"post-relay discord dm-schedule-send --draft-id {draft.id} --db data/post_relay.sqlite",
            draft_id=draft.id,
            thread_id=thread.id if thread else None,
            status=status,
            rationale=[
                "Active content approval is present." if ApprovalType.DRAFT.value in active_approval_types else "Status is queue-approved; verify content approval if this looks unexpected.",
                "Scheduling is local-only and does not publish to Instagram.",
            ],
            safety_notes=_base_safety_notes(),
        )

    if status in {DraftState.SCHEDULED.value, DraftState.AWAITING_PUBLISH_APPROVAL.value}:
        return DmNextActionPlan(
            action="publish_approval_prompt",
            summary="Request double-confirmed final publish approval in the private DM; this only records local approval and does not publish to Instagram.",
            command=f"post-relay discord dm-publish-approval-send --draft-id {draft.id} --db data/post_relay.sqlite",
            draft_id=draft.id,
            thread_id=thread.id if thread else None,
            status=status,
            rationale=[
                f"Scheduled for {draft.scheduled_for or '<unset>'}.",
                "Final publish approval must be separate from content approval.",
            ],
            safety_notes=_base_safety_notes(),
        )

    if status == DraftState.READY_TO_PUBLISH.value:
        return DmNextActionPlan(
            action="publish_preflight",
            summary="Render the final Meta-bound preview and let the due scheduled-publish runner execute from stored final approval when the schedule arrives.",
            command=(
                f"post-relay meta final-publish-preview --draft-id {draft.id} --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite && "
                f"post-relay meta publish-scheduled --draft-id {draft.id} --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute"
            ),
            draft_id=draft.id,
            thread_id=thread.id if thread else None,
            status=status,
            rationale=[
                "Content approval and final publish approval should both be active before live execution.",
                "Stored final publish approval is durable for this scheduled post until a material edit invalidates it.",
                "No reapproval is needed inside Meta's 24-hour container window; containers are created only when the due runner executes.",
                "Schedule enforcement and staged-media completeness still need preflight checks.",
            ],
            safety_notes=_base_safety_notes()
            + ["The --execute runner may publish only after the stored schedule is due and active double approval is still present."],
        )

    if status == DraftState.POSTED.value:
        return DmNextActionPlan(
            action="post_publish_feedback",
            summary="Review stored analytics/feedback summaries and follower progress before choosing the next post opportunity.",
            command=f"post-relay analytics feedback-summary --draft-id {draft.id} --db data/post_relay.sqlite && post-relay analytics follower-summary --db data/post_relay.sqlite",
            draft_id=draft.id,
            thread_id=thread.id if thread else None,
            status=status,
            rationale=["The post is already marked posted; only read-only analytics/advisory feedback is appropriate."],
            safety_notes=_base_safety_notes(),
        )

    return DmNextActionPlan(
        action="manual_review",
        summary="Review this post manually before sending another DM prompt.",
        command=f"post-relay drafts preview --draft-id {draft.id} --db data/post_relay.sqlite",
        draft_id=draft.id,
        thread_id=thread.id if thread else None,
        status=status,
        rationale=["The post status does not map to a safe automated DM next step."],
        safety_notes=_base_safety_notes(),
    )


def _base_safety_notes() -> list[str]:
    return [
        "Private-DM-first operating loop; no public Discord channel sends.",
        "Never publish to Instagram from this planner.",
        "Keep content approval, scheduling, final publish approval, and live Meta execution as separate gates.",
    ]

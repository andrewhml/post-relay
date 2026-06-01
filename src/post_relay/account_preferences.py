from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Optional, Sequence


DEFAULT_ACCOUNT_KEY = "default"
DEFAULT_REVIEW_FLOW_ORDER = ["selection_sheet", "crop_sheet", "copy_collaboration", "final_preview"]
_VALID_REVIEW_STEPS = set(DEFAULT_REVIEW_FLOW_ORDER)


@dataclass(frozen=True)
class AccountPreferenceRecord:
    id: int
    account_key: str
    review_flow_order: list[str]
    require_goal_and_audience_for_copy: bool
    copy_collaboration_required: bool
    final_preview_requires_locked_copy: bool
    writing_style_notes: list[str]
    reviewed_by: Optional[str]
    status: str


@dataclass(frozen=True)
class AccountPreferenceVersionRecord:
    id: int
    account_preference_id: int
    version_number: int
    snapshot: dict
    changed_by: Optional[str]
    change_note: Optional[str]


def upsert_account_preferences(
    connection,
    *,
    account_key: str = DEFAULT_ACCOUNT_KEY,
    review_flow_order: Optional[Sequence[str]] = None,
    require_goal_and_audience_for_copy: bool = True,
    copy_collaboration_required: bool = True,
    final_preview_requires_locked_copy: bool = True,
    writing_style_notes: Optional[Sequence[str]] = None,
    reviewed_by: Optional[str] = None,
    change_note: Optional[str] = None,
) -> AccountPreferenceRecord:
    account_key = _clean_account_key(account_key)
    flow = _normalize_review_flow_order(review_flow_order)
    notes = _normalize_list(writing_style_notes)
    existing = get_active_account_preferences(connection, account_key=account_key)
    if existing is None:
        cursor = connection.execute(
            """
            insert into account_preferences (
                account_key, review_flow_order_json, require_goal_and_audience_for_copy,
                copy_collaboration_required, final_preview_requires_locked_copy,
                writing_style_notes_json, reviewed_by
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_key,
                json.dumps(flow),
                int(require_goal_and_audience_for_copy),
                int(copy_collaboration_required),
                int(final_preview_requires_locked_copy),
                json.dumps(notes),
                _clean_optional(reviewed_by),
            ),
        )
        preference_id = int(cursor.lastrowid)
    else:
        preference_id = existing.id
        connection.execute(
            """
            update account_preferences
            set review_flow_order_json = ?,
                require_goal_and_audience_for_copy = ?,
                copy_collaboration_required = ?,
                final_preview_requires_locked_copy = ?,
                writing_style_notes_json = ?,
                reviewed_by = ?,
                updated_at = current_timestamp
            where id = ?
            """,
            (
                json.dumps(flow),
                int(require_goal_and_audience_for_copy),
                int(copy_collaboration_required),
                int(final_preview_requires_locked_copy),
                json.dumps(notes),
                _clean_optional(reviewed_by),
                preference_id,
            ),
        )
    saved = _get_account_preference_by_id(connection, preference_id)
    if saved is None:
        raise RuntimeError("Failed to save account preferences")
    _record_account_preference_version(connection, saved, changed_by=reviewed_by, change_note=change_note)
    connection.commit()
    return saved


def get_active_account_preferences(
    connection,
    *,
    account_key: str = DEFAULT_ACCOUNT_KEY,
) -> Optional[AccountPreferenceRecord]:
    row = connection.execute(
        """
        select id, account_key, review_flow_order_json, require_goal_and_audience_for_copy,
               copy_collaboration_required, final_preview_requires_locked_copy,
               writing_style_notes_json, reviewed_by, status
        from account_preferences
        where account_key = ? and status = 'active'
        order by updated_at desc, id desc
        limit 1
        """,
        (_clean_account_key(account_key),),
    ).fetchone()
    return _row_to_account_preferences(row) if row else None


def list_account_preference_versions(connection, account_preference_id: int) -> list[AccountPreferenceVersionRecord]:
    rows = connection.execute(
        """
        select id, account_preference_id, version_number, snapshot_json, changed_by, change_note
        from account_preference_versions
        where account_preference_id = ?
        order by version_number
        """,
        (account_preference_id,),
    ).fetchall()
    return [_row_to_account_preference_version(row) for row in rows]


def render_account_preferences(preferences: Optional[AccountPreferenceRecord]) -> str:
    if preferences is None:
        return "\n".join(
            [
                "No account preferences are stored yet.",
                f"Default review flow order: {_format_flow(DEFAULT_REVIEW_FLOW_ORDER)}",
                "Next safe command: post-relay preferences set --review-step selection_sheet --review-step crop_sheet --review-step copy_collaboration --review-step final_preview --db data/post_relay.sqlite",
                "No Discord, R2, or Meta network calls were made.",
            ]
        )
    lines = [
        f"Account preferences for {preferences.account_key}",
        f"Review flow order: {_format_flow(preferences.review_flow_order)}",
        f"Goal/audience required before copy-heavy advice: {_yes_no(preferences.require_goal_and_audience_for_copy)}",
        f"Copy collaboration required before final approval: {_yes_no(preferences.copy_collaboration_required)}",
        f"Final preview requires locked copy/supporting text: {_yes_no(preferences.final_preview_requires_locked_copy)}",
        "Writing style notes:",
    ]
    if preferences.writing_style_notes:
        lines.extend(f"- {note}" for note in preferences.writing_style_notes)
    else:
        lines.append("- <none yet>")
    if preferences.reviewed_by:
        lines.append(f"Reviewed by: {preferences.reviewed_by}")
    lines.append("No Discord, R2, or Meta network calls were made.")
    return "\n".join(lines)


def render_account_preferences_agent_brief(connection, *, account_key: str = DEFAULT_ACCOUNT_KEY) -> str:
    preferences = get_active_account_preferences(connection, account_key=account_key)
    if preferences is None:
        preferences = AccountPreferenceRecord(
            id=0,
            account_key=_clean_account_key(account_key),
            review_flow_order=list(DEFAULT_REVIEW_FLOW_ORDER),
            require_goal_and_audience_for_copy=True,
            copy_collaboration_required=True,
            final_preview_requires_locked_copy=True,
            writing_style_notes=[],
            reviewed_by=None,
            status="default",
        )
    lines = [
        "Account preferences",
        f"Account key: {preferences.account_key}",
        "Review flow order:",
    ]
    lines.extend(f"{index}. {step}" for index, step in enumerate(preferences.review_flow_order, start=1))
    lines.extend(
        [
            f"Goal/audience required before copy-heavy advice: {_yes_no(preferences.require_goal_and_audience_for_copy)}",
            f"Copy collaboration required before final approval: {_yes_no(preferences.copy_collaboration_required)}",
            f"Final preview requires locked copy/supporting text: {_yes_no(preferences.final_preview_requires_locked_copy)}",
            "Writing style notes:",
        ]
    )
    if preferences.writing_style_notes:
        lines.extend(f"- {note}" for note in preferences.writing_style_notes)
    else:
        lines.append("- Learn from accepted copy, revisions, and explicit feedback over time.")
    lines.extend(
        [
            "Agent operating posture:",
            "- Keep review artifacts resource-aware and do not render later-stage sheets before prerequisites are met.",
            "- Treat copy as collaborative; do not overwrite or finalize the user's voice automatically.",
            "No Discord, R2, or Meta network calls were made.",
            "This brief is advisory and does not mutate posts, approvals, schedules, or publish state.",
        ]
    )
    return "\n".join(lines)


def preference_guidance_lines(preferences: Optional[AccountPreferenceRecord]) -> list[str]:
    preferences = preferences or AccountPreferenceRecord(
        id=0,
        account_key=DEFAULT_ACCOUNT_KEY,
        review_flow_order=list(DEFAULT_REVIEW_FLOW_ORDER),
        require_goal_and_audience_for_copy=True,
        copy_collaboration_required=True,
        final_preview_requires_locked_copy=True,
        writing_style_notes=[],
        reviewed_by=None,
        status="default",
    )
    lines = [f"Review flow order: {_format_flow(preferences.review_flow_order)}"]
    if preferences.require_goal_and_audience_for_copy:
        lines.append("Copy should be collaborative and use the active goal/audience before finalizing.")
    if preferences.final_preview_requires_locked_copy:
        lines.append("Final preview should wait until caption, hashtags, alt text, and supporting text are locked.")
    if preferences.writing_style_notes:
        lines.append("Writing style notes: " + "; ".join(preferences.writing_style_notes))
    else:
        lines.append("Writing style notes: learn from accepted copy, revisions, and explicit feedback over time.")
    return lines


def _get_account_preference_by_id(connection, preference_id: int) -> Optional[AccountPreferenceRecord]:
    row = connection.execute(
        """
        select id, account_key, review_flow_order_json, require_goal_and_audience_for_copy,
               copy_collaboration_required, final_preview_requires_locked_copy,
               writing_style_notes_json, reviewed_by, status
        from account_preferences
        where id = ?
        """,
        (preference_id,),
    ).fetchone()
    return _row_to_account_preferences(row) if row else None


def _record_account_preference_version(
    connection,
    preferences: AccountPreferenceRecord,
    *,
    changed_by: Optional[str],
    change_note: Optional[str],
) -> None:
    version_number = connection.execute(
        "select coalesce(max(version_number), 0) + 1 from account_preference_versions where account_preference_id = ?",
        (preferences.id,),
    ).fetchone()[0]
    snapshot = {
        "account_key": preferences.account_key,
        "review_flow_order": preferences.review_flow_order,
        "require_goal_and_audience_for_copy": preferences.require_goal_and_audience_for_copy,
        "copy_collaboration_required": preferences.copy_collaboration_required,
        "final_preview_requires_locked_copy": preferences.final_preview_requires_locked_copy,
        "writing_style_notes": preferences.writing_style_notes,
        "reviewed_by": preferences.reviewed_by,
        "status": preferences.status,
    }
    connection.execute(
        """
        insert into account_preference_versions (account_preference_id, version_number, snapshot_json, changed_by, change_note)
        values (?, ?, ?, ?, ?)
        """,
        (preferences.id, int(version_number), json.dumps(snapshot), _clean_optional(changed_by), _clean_optional(change_note)),
    )


def _row_to_account_preferences(row) -> AccountPreferenceRecord:
    return AccountPreferenceRecord(
        id=int(row[0]),
        account_key=row[1],
        review_flow_order=_normalize_review_flow_order(json.loads(row[2] or "[]")),
        require_goal_and_audience_for_copy=bool(row[3]),
        copy_collaboration_required=bool(row[4]),
        final_preview_requires_locked_copy=bool(row[5]),
        writing_style_notes=_normalize_list(json.loads(row[6] or "[]")),
        reviewed_by=row[7],
        status=row[8],
    )


def _row_to_account_preference_version(row) -> AccountPreferenceVersionRecord:
    return AccountPreferenceVersionRecord(
        id=int(row[0]),
        account_preference_id=int(row[1]),
        version_number=int(row[2]),
        snapshot=json.loads(row[3]),
        changed_by=row[4],
        change_note=row[5],
    )


def _normalize_review_flow_order(steps: Optional[Sequence[str]]) -> list[str]:
    cleaned = [str(step).strip() for step in (steps or DEFAULT_REVIEW_FLOW_ORDER) if str(step).strip()]
    if sorted(cleaned) != sorted(DEFAULT_REVIEW_FLOW_ORDER) or len(cleaned) != len(DEFAULT_REVIEW_FLOW_ORDER):
        raise ValueError(
            "Review flow order must include each step exactly once: " + ", ".join(DEFAULT_REVIEW_FLOW_ORDER)
        )
    invalid = [step for step in cleaned if step not in _VALID_REVIEW_STEPS]
    if invalid:
        raise ValueError(f"Unknown review flow step(s): {', '.join(invalid)}")
    return cleaned


def _normalize_list(values: Optional[Sequence[str]]) -> list[str]:
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _clean_account_key(account_key: str) -> str:
    return (account_key or DEFAULT_ACCOUNT_KEY).strip() or DEFAULT_ACCOUNT_KEY


def _clean_optional(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def _format_flow(flow: Sequence[str]) -> str:
    return " → ".join(flow)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"

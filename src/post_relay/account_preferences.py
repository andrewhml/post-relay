from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Optional, Sequence


DEFAULT_ACCOUNT_KEY = "default"
DEFAULT_REVIEW_FLOW_ORDER = ["selection_sheet", "crop_sheet", "copy_collaboration", "final_preview"]
VALID_GOAL_TYPES = {"growth", "sales_leads", "education", "portfolio", "community", "personal_archive", "fun"}
VALID_GROWTH_MODES = {"conservative", "balanced", "growth_push", "experimental"}
VALID_SUCCESS_METRICS = {
    "followers",
    "saves",
    "shares",
    "comments",
    "dms",
    "profile_visits",
    "website_clicks",
    "sales_leads",
    "cadence",
    "satisfaction",
}
VALID_CHECKIN_CADENCES = {"daily", "twice_weekly", "weekly", "monthly", "goal_adaptive", "off"}
VALID_PUSH_LEVELS = {"low", "medium", "high"}
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
    goal_type: Optional[str]
    growth_mode: Optional[str]
    primary_success_metric: Optional[str]
    target_monthly_reels: Optional[int]
    target_monthly_carousels: Optional[int]
    target_weekly_posts: Optional[int]
    agent_checkin_cadence: Optional[str]
    comfort_zone_push_enabled: bool
    max_push_level: Optional[str]
    preferred_growth_experiments: list[str]
    blocked_growth_experiments: list[str]
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
    goal_type: Optional[str] = None,
    growth_mode: Optional[str] = None,
    primary_success_metric: Optional[str] = None,
    target_monthly_reels: Optional[int] = None,
    target_monthly_carousels: Optional[int] = None,
    target_weekly_posts: Optional[int] = None,
    agent_checkin_cadence: Optional[str] = None,
    comfort_zone_push_enabled: bool = False,
    max_push_level: Optional[str] = None,
    preferred_growth_experiments: Optional[Sequence[str]] = None,
    blocked_growth_experiments: Optional[Sequence[str]] = None,
    reviewed_by: Optional[str] = None,
    change_note: Optional[str] = None,
) -> AccountPreferenceRecord:
    account_key = _clean_account_key(account_key)
    flow = _normalize_review_flow_order(review_flow_order)
    notes = _normalize_list(writing_style_notes)
    goal_type = _normalize_choice("goal_type", goal_type, VALID_GOAL_TYPES)
    growth_mode = _normalize_choice("growth_mode", growth_mode, VALID_GROWTH_MODES)
    primary_success_metric = _normalize_choice("primary_success_metric", primary_success_metric, VALID_SUCCESS_METRICS)
    agent_checkin_cadence = _normalize_choice("agent_checkin_cadence", agent_checkin_cadence, VALID_CHECKIN_CADENCES)
    max_push_level = _normalize_choice("max_push_level", max_push_level, VALID_PUSH_LEVELS)
    target_monthly_reels = _normalize_optional_nonnegative_int("target_monthly_reels", target_monthly_reels)
    target_monthly_carousels = _normalize_optional_nonnegative_int("target_monthly_carousels", target_monthly_carousels)
    target_weekly_posts = _normalize_optional_nonnegative_int("target_weekly_posts", target_weekly_posts)
    preferred_growth_experiments_list = _normalize_list(preferred_growth_experiments)
    blocked_growth_experiments_list = _normalize_list(blocked_growth_experiments)
    existing = get_active_account_preferences(connection, account_key=account_key)
    if existing is None:
        cursor = connection.execute(
            """
            insert into account_preferences (
                account_key, review_flow_order_json, require_goal_and_audience_for_copy,
                copy_collaboration_required, final_preview_requires_locked_copy,
                writing_style_notes_json, goal_type, growth_mode, primary_success_metric,
                target_monthly_reels, target_monthly_carousels, target_weekly_posts,
                agent_checkin_cadence, comfort_zone_push_enabled, max_push_level,
                preferred_growth_experiments_json, blocked_growth_experiments_json, reviewed_by
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_key,
                json.dumps(flow),
                int(require_goal_and_audience_for_copy),
                int(copy_collaboration_required),
                int(final_preview_requires_locked_copy),
                json.dumps(notes),
                goal_type,
                growth_mode,
                primary_success_metric,
                target_monthly_reels,
                target_monthly_carousels,
                target_weekly_posts,
                agent_checkin_cadence,
                int(comfort_zone_push_enabled),
                max_push_level,
                json.dumps(preferred_growth_experiments_list),
                json.dumps(blocked_growth_experiments_list),
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
                goal_type = ?,
                growth_mode = ?,
                primary_success_metric = ?,
                target_monthly_reels = ?,
                target_monthly_carousels = ?,
                target_weekly_posts = ?,
                agent_checkin_cadence = ?,
                comfort_zone_push_enabled = ?,
                max_push_level = ?,
                preferred_growth_experiments_json = ?,
                blocked_growth_experiments_json = ?,
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
                goal_type,
                growth_mode,
                primary_success_metric,
                target_monthly_reels,
                target_monthly_carousels,
                target_weekly_posts,
                agent_checkin_cadence,
                int(comfort_zone_push_enabled),
                max_push_level,
                json.dumps(preferred_growth_experiments_list),
                json.dumps(blocked_growth_experiments_list),
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
               writing_style_notes_json, goal_type, growth_mode, primary_success_metric,
               target_monthly_reels, target_monthly_carousels, target_weekly_posts,
               agent_checkin_cadence, comfort_zone_push_enabled, max_push_level,
               preferred_growth_experiments_json, blocked_growth_experiments_json,
               reviewed_by, status
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
        "Growth posture:",
        f"- Goal type: {_format_optional(preferences.goal_type)}",
        f"- Growth mode: {_format_optional(preferences.growth_mode)}",
        f"- Primary success metric: {_format_optional(preferences.primary_success_metric)}",
        f"- Target monthly reels: {_format_optional(preferences.target_monthly_reels)}",
        f"- Target monthly carousels: {_format_optional(preferences.target_monthly_carousels)}",
        f"- Target weekly posts: {_format_optional(preferences.target_weekly_posts)}",
        f"- Agent check-in cadence: {_format_optional(preferences.agent_checkin_cadence)}",
        f"- Comfort-zone push: {_format_comfort_zone(preferences)}",
        f"- Preferred growth experiments: {_format_list(preferences.preferred_growth_experiments)}",
        f"- Blocked growth experiments: {_format_list(preferences.blocked_growth_experiments)}",
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
            goal_type=None,
            growth_mode=None,
            primary_success_metric=None,
            target_monthly_reels=None,
            target_monthly_carousels=None,
            target_weekly_posts=None,
            agent_checkin_cadence=None,
            comfort_zone_push_enabled=False,
            max_push_level=None,
            preferred_growth_experiments=[],
            blocked_growth_experiments=[],
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
            "Growth posture:",
            f"Goal type: {_format_optional(preferences.goal_type)}",
            f"Growth mode: {_format_optional(preferences.growth_mode)}",
            f"Primary success metric: {_format_optional(preferences.primary_success_metric)}",
            f"Target monthly reels: {_format_optional(preferences.target_monthly_reels)}",
            f"Target monthly carousels: {_format_optional(preferences.target_monthly_carousels)}",
            f"Target weekly posts: {_format_optional(preferences.target_weekly_posts)}",
            f"Agent check-in cadence: {_format_optional(preferences.agent_checkin_cadence)}",
            f"Comfort-zone push: {_format_comfort_zone(preferences)}",
            f"Preferred growth experiments: {_format_list(preferences.preferred_growth_experiments)}",
            f"Blocked growth experiments: {_format_list(preferences.blocked_growth_experiments)}",
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
        goal_type=None,
        growth_mode=None,
        primary_success_metric=None,
        target_monthly_reels=None,
        target_monthly_carousels=None,
        target_weekly_posts=None,
        agent_checkin_cadence=None,
        comfort_zone_push_enabled=False,
        max_push_level=None,
        preferred_growth_experiments=[],
        blocked_growth_experiments=[],
        reviewed_by=None,
        status="default",
    )
    lines = [f"Review flow order: {_format_flow(preferences.review_flow_order)}"]
    if preferences.require_goal_and_audience_for_copy:
        lines.append("Copy should be collaborative and use the active goal/audience before finalizing.")
    if preferences.final_preview_requires_locked_copy:
        lines.append("Final preview should wait until caption, hashtags, alt text, and supporting text are locked.")
    growth_parts = _growth_posture_guidance_parts(preferences)
    if growth_parts:
        lines.append("Growth posture: " + "; ".join(growth_parts) + ".")
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
               writing_style_notes_json, goal_type, growth_mode, primary_success_metric,
               target_monthly_reels, target_monthly_carousels, target_weekly_posts,
               agent_checkin_cadence, comfort_zone_push_enabled, max_push_level,
               preferred_growth_experiments_json, blocked_growth_experiments_json,
               reviewed_by, status
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
        "goal_type": preferences.goal_type,
        "growth_mode": preferences.growth_mode,
        "primary_success_metric": preferences.primary_success_metric,
        "target_monthly_reels": preferences.target_monthly_reels,
        "target_monthly_carousels": preferences.target_monthly_carousels,
        "target_weekly_posts": preferences.target_weekly_posts,
        "agent_checkin_cadence": preferences.agent_checkin_cadence,
        "comfort_zone_push_enabled": preferences.comfort_zone_push_enabled,
        "max_push_level": preferences.max_push_level,
        "preferred_growth_experiments": preferences.preferred_growth_experiments,
        "blocked_growth_experiments": preferences.blocked_growth_experiments,
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
        goal_type=row[7],
        growth_mode=row[8],
        primary_success_metric=row[9],
        target_monthly_reels=row[10],
        target_monthly_carousels=row[11],
        target_weekly_posts=row[12],
        agent_checkin_cadence=row[13],
        comfort_zone_push_enabled=bool(row[14]),
        max_push_level=row[15],
        preferred_growth_experiments=_normalize_list(json.loads(row[16] or "[]")),
        blocked_growth_experiments=_normalize_list(json.loads(row[17] or "[]")),
        reviewed_by=row[18],
        status=row[19],
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


def _normalize_choice(name: str, value: Optional[str], allowed: set[str]) -> Optional[str]:
    cleaned = _clean_optional(value)
    if cleaned is None:
        return None
    if cleaned not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return cleaned


def _normalize_optional_nonnegative_int(name: str, value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{name} must be greater than or equal to 0")
    return normalized


def _format_optional(value) -> str:
    return str(value) if value not in (None, "") else "<not set>"


def _format_list(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "<none>"


def _format_comfort_zone(preferences: AccountPreferenceRecord) -> str:
    if not preferences.comfort_zone_push_enabled:
        return "disabled"
    max_push = preferences.max_push_level or "unspecified"
    return f"enabled (max {max_push})"


def _growth_posture_guidance_parts(preferences: AccountPreferenceRecord) -> list[str]:
    parts: list[str] = []
    if preferences.growth_mode:
        if preferences.primary_success_metric:
            parts.append(f"{preferences.growth_mode} optimizing {preferences.primary_success_metric}")
        else:
            parts.append(preferences.growth_mode)
    elif preferences.goal_type:
        parts.append(f"goal type {preferences.goal_type}")
    if preferences.target_monthly_reels is not None:
        parts.append(f"target {preferences.target_monthly_reels} reels/month")
    if preferences.target_monthly_carousels is not None:
        parts.append(f"target {preferences.target_monthly_carousels} carousels/month")
    if preferences.target_weekly_posts is not None:
        parts.append(f"target {preferences.target_weekly_posts} posts/week")
    if preferences.comfort_zone_push_enabled:
        parts.append(f"comfort-zone push {_format_comfort_zone(preferences)}")
    if preferences.preferred_growth_experiments:
        parts.append("preferred experiments: " + ", ".join(preferences.preferred_growth_experiments))
    if preferences.blocked_growth_experiments:
        parts.append("blocked experiments: " + ", ".join(preferences.blocked_growth_experiments))
    return parts


def _clean_account_key(account_key: str) -> str:
    return (account_key or DEFAULT_ACCOUNT_KEY).strip() or DEFAULT_ACCOUNT_KEY


def _clean_optional(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def _format_flow(flow: Sequence[str]) -> str:
    return " → ".join(flow)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"

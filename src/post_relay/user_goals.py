from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Optional, Sequence


@dataclass(frozen=True)
class UserGoalRecord:
    id: int
    title: str
    goal_statement: str
    target_audience: Optional[str]
    content_pillars: list[str]
    desired_cadence: Optional[str]
    success_metrics: list[str]
    strategy_notes: Optional[str]
    constraints: list[str]
    reviewed_by: Optional[str]
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class UserGoalVersionRecord:
    id: int
    goal_id: int
    version_number: int
    snapshot: dict
    changed_by: Optional[str]
    change_note: Optional[str]
    created_at: str


def upsert_active_user_goal(
    connection,
    *,
    title: str,
    goal_statement: str,
    target_audience: Optional[str] = None,
    content_pillars: Sequence[str] = (),
    desired_cadence: Optional[str] = None,
    success_metrics: Sequence[str] = (),
    strategy_notes: Optional[str] = None,
    constraints: Sequence[str] = (),
    reviewed_by: Optional[str] = None,
    change_note: Optional[str] = None,
) -> UserGoalRecord:
    existing = get_active_user_goal(connection)
    pillars_json = json.dumps(_clean_list(content_pillars))
    metrics_json = json.dumps(_clean_list(success_metrics))
    constraints_json = json.dumps(_clean_list(constraints))
    if existing is None:
        cursor = connection.execute(
            """
            insert into user_goals (
                title,
                goal_statement,
                target_audience,
                content_pillars_json,
                desired_cadence,
                success_metrics_json,
                strategy_notes,
                constraints_json,
                reviewed_by,
                status
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                title.strip(),
                goal_statement.strip(),
                _blank_to_none(target_audience),
                pillars_json,
                _blank_to_none(desired_cadence),
                metrics_json,
                _blank_to_none(strategy_notes),
                constraints_json,
                _blank_to_none(reviewed_by),
            ),
        )
        goal_id = int(cursor.lastrowid)
    else:
        goal_id = existing.id
        connection.execute(
            """
            update user_goals
            set title = ?,
                goal_statement = ?,
                target_audience = ?,
                content_pillars_json = ?,
                desired_cadence = ?,
                success_metrics_json = ?,
                strategy_notes = ?,
                constraints_json = ?,
                reviewed_by = ?,
                updated_at = current_timestamp
            where id = ?
            """,
            (
                title.strip(),
                goal_statement.strip(),
                _blank_to_none(target_audience),
                pillars_json,
                _blank_to_none(desired_cadence),
                metrics_json,
                _blank_to_none(strategy_notes),
                constraints_json,
                _blank_to_none(reviewed_by),
                goal_id,
            ),
        )
    saved = _get_user_goal_by_id(connection, goal_id)
    if saved is None:
        raise RuntimeError("failed to save active user goal")
    _record_goal_version(
        connection,
        saved,
        changed_by=_blank_to_none(reviewed_by),
        change_note=_blank_to_none(change_note),
    )
    connection.commit()
    return saved


def get_active_user_goal(connection) -> Optional[UserGoalRecord]:
    row = connection.execute(
        """
        select id, title, goal_statement, target_audience, content_pillars_json,
               desired_cadence, success_metrics_json, strategy_notes, constraints_json,
               reviewed_by, status, created_at, updated_at
        from user_goals
        where status = 'active'
        order by updated_at desc, id desc
        limit 1
        """
    ).fetchone()
    if row is None:
        return None
    return _row_to_user_goal(row)


def list_user_goal_versions(connection, goal_id: int) -> list[UserGoalVersionRecord]:
    rows = connection.execute(
        """
        select id, goal_id, version_number, snapshot_json, changed_by, change_note, created_at
        from user_goal_versions
        where goal_id = ?
        order by version_number asc
        """,
        (goal_id,),
    ).fetchall()
    return [_row_to_user_goal_version(row) for row in rows]


def render_user_goal(goal: Optional[UserGoalRecord]) -> str:
    if goal is None:
        return "\n".join(
            [
                "No active user goal is stored yet.",
                "Create one with post-relay goals init --title ... --statement ...",
                "No Discord, R2, or Meta network calls were made.",
            ]
        )
    lines = [
        f"Active user goal #{goal.id}: {goal.title}",
        f"Status: {goal.status}",
        f"Goal statement: {goal.goal_statement}",
    ]
    if goal.target_audience:
        lines.append(f"Target audience: {goal.target_audience}")
    lines.extend(_render_list("Content pillars", goal.content_pillars))
    if goal.desired_cadence:
        lines.append(f"Desired cadence: {goal.desired_cadence}")
    lines.extend(_render_list("Success metrics", goal.success_metrics))
    if goal.strategy_notes:
        lines.append(f"Strategy notes: {goal.strategy_notes}")
    lines.extend(_render_list("Constraints", goal.constraints))
    if goal.reviewed_by:
        lines.append(f"Reviewed by: {goal.reviewed_by}")
    lines.extend(
        [
            f"Updated at: {goal.updated_at}",
            "No Discord, R2, or Meta network calls were made.",
        ]
    )
    return "\n".join(lines)


def render_user_goal_agent_brief(connection) -> str:
    goal = get_active_user_goal(connection)
    if goal is None:
        return render_user_goal(None)
    lines = [
        "Active user goal",
        f"Title: {goal.title}",
        f"North star: {goal.goal_statement}",
    ]
    if goal.target_audience:
        lines.append(f"Target audience: {goal.target_audience}")
    lines.extend(_render_list("Content pillars", goal.content_pillars))
    if goal.desired_cadence:
        lines.append(f"Desired cadence: {goal.desired_cadence}")
    lines.extend(_render_list("Success metrics", goal.success_metrics))
    if goal.strategy_notes:
        lines.append(f"Current strategy: {goal.strategy_notes}")
    lines.extend(_render_list("Constraints", goal.constraints))
    lines.extend(
        [
            "Agent operating posture:",
            "- Suggest actions that fit this goal and cite the rationale.",
            "- Prefer the safest next local action when confidence is incomplete.",
            "- Ask only questions that materially change selection, copy, schedule, or publishability.",
            "- Keep generated facts as assumptions until reviewed by the user.",
            "This brief is advisory and does not mutate posts, approvals, schedules, or publish state.",
            "No Discord, R2, or Meta network calls were made.",
        ]
    )
    return "\n".join(lines)


def _get_user_goal_by_id(connection, goal_id: int) -> Optional[UserGoalRecord]:
    row = connection.execute(
        """
        select id, title, goal_statement, target_audience, content_pillars_json,
               desired_cadence, success_metrics_json, strategy_notes, constraints_json,
               reviewed_by, status, created_at, updated_at
        from user_goals
        where id = ?
        """,
        (goal_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_user_goal(row)


def _record_goal_version(
    connection,
    goal: UserGoalRecord,
    *,
    changed_by: Optional[str],
    change_note: Optional[str],
) -> None:
    row = connection.execute(
        "select coalesce(max(version_number), 0) + 1 from user_goal_versions where goal_id = ?",
        (goal.id,),
    ).fetchone()
    version_number = int(row[0])
    connection.execute(
        """
        insert into user_goal_versions (
            goal_id, version_number, snapshot_json, changed_by, change_note
        ) values (?, ?, ?, ?, ?)
        """,
        (
            goal.id,
            version_number,
            json.dumps(_goal_snapshot(goal), sort_keys=True),
            changed_by,
            change_note,
        ),
    )


def _row_to_user_goal(row) -> UserGoalRecord:
    return UserGoalRecord(
        id=int(row[0]),
        title=row[1],
        goal_statement=row[2],
        target_audience=row[3],
        content_pillars=_json_list(row[4]),
        desired_cadence=row[5],
        success_metrics=_json_list(row[6]),
        strategy_notes=row[7],
        constraints=_json_list(row[8]),
        reviewed_by=row[9],
        status=row[10],
        created_at=row[11],
        updated_at=row[12],
    )


def _row_to_user_goal_version(row) -> UserGoalVersionRecord:
    return UserGoalVersionRecord(
        id=int(row[0]),
        goal_id=int(row[1]),
        version_number=int(row[2]),
        snapshot=json.loads(row[3]),
        changed_by=row[4],
        change_note=row[5],
        created_at=row[6],
    )


def _goal_snapshot(goal: UserGoalRecord) -> dict:
    return {
        "id": goal.id,
        "title": goal.title,
        "goal_statement": goal.goal_statement,
        "target_audience": goal.target_audience,
        "content_pillars": goal.content_pillars,
        "desired_cadence": goal.desired_cadence,
        "success_metrics": goal.success_metrics,
        "strategy_notes": goal.strategy_notes,
        "constraints": goal.constraints,
        "reviewed_by": goal.reviewed_by,
        "status": goal.status,
    }


def _clean_list(values: Sequence[str]) -> list[str]:
    return [value.strip() for value in values if value and value.strip()]


def _json_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _render_list(label: str, values: Sequence[str]) -> list[str]:
    if not values:
        return [f"{label}: <none>"]
    return [f"{label}:"] + [f"- {value}" for value in values]

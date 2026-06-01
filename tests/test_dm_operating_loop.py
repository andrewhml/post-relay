from pathlib import Path

from typer.testing import CliRunner

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.dm_intake import handle_dm_intake
from post_relay.dm_operating_loop import build_dm_next_action_plan
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups
from post_relay.scheduling import approve_draft_for_publishing, request_publish_approval, schedule_draft
from post_relay.state import DraftState
from post_relay.user_goals import upsert_active_user_goal


runner = CliRunner()


def _build_fixture_library(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "kyoto-night-market"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-hero.jpg", "04-crowd.jpg"]:
        (folder / filename).write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    return connection, root


def _create_draft(tmp_path: Path):
    connection, root = _build_fixture_library(tmp_path)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    return connection, draft, root


def test_dm_next_action_routes_open_intake_thread_to_candidate_selection_without_network(tmp_path: Path):
    connection, root = _build_fixture_library(tmp_path)
    intake = handle_dm_intake(
        connection,
        "start a post about Kyoto night market",
        discord_channel_id="dm-andrew",
    )

    plan = build_dm_next_action_plan(connection, discord_channel_id="dm-andrew")
    text = plan.to_text()

    assert plan.action == "candidate_selection"
    assert plan.thread_id == intake.thread.id
    assert plan.draft_id is None
    assert "Ask Andrew to choose one candidate" in text
    assert "post-relay dm intake --message \"choose candidate #<id>\"" in text
    assert "No Discord, Meta, or R2 network calls were made." in text
    assert root.as_posix() not in text


def test_dm_next_action_prompts_for_goal_before_first_chat_post_when_goal_missing(tmp_path: Path):
    connection, root = _build_fixture_library(tmp_path)

    plan = build_dm_next_action_plan(connection, discord_channel_id="dm-new-user")
    text = plan.to_text()

    assert plan.action == "goal_onboarding"
    assert plan.draft_id is None
    assert plan.thread_id is None
    assert "Ask the user to agree on the active user/agent goal before recommending a first post." in text
    assert "What kind of account are we trying to build?" in text
    assert "post-relay goals init" in text
    assert "post-relay setup --photo-root" in text
    assert "No Discord, Meta, or R2 network calls were made." in text
    assert root.as_posix() not in text


def test_dm_next_action_starts_intake_after_goal_exists(tmp_path: Path):
    connection, _root = _build_fixture_library(tmp_path)
    upsert_active_user_goal(
        connection,
        title="Travel north star",
        goal_statement="Grow with saveable travel carousels.",
        target_audience="Travelers planning trips.",
        content_pillars=["city guides"],
        desired_cadence="2 posts per week",
        success_metrics=["saves"],
        strategy_notes="Suggest one best next post.",
        constraints=["avoid places not pictured"],
        reviewed_by="tester",
    )

    plan = build_dm_next_action_plan(connection, discord_channel_id="dm-new-user")

    assert plan.action == "start_intake"



def test_dm_next_action_includes_local_candidate_recommendations_before_starting_intake(tmp_path: Path):
    connection, root = _build_fixture_library(tmp_path)
    upsert_active_user_goal(
        connection,
        title="Travel north star",
        goal_statement="Grow with saveable travel carousels.",
        target_audience="Travelers planning trips.",
        content_pillars=["city guides"],
        desired_cadence="2 posts per week",
        success_metrics=["saves"],
        strategy_notes="Suggest one best next post.",
        constraints=["avoid places not pictured"],
        reviewed_by="tester",
    )

    plan = build_dm_next_action_plan(connection, discord_channel_id="dm-new-user")
    text = plan.to_text()

    assert plan.action == "start_intake"
    assert "Advisory recommendations:" in text
    assert "Candidate recommendations" in text
    assert "Next safe command: post-relay drafts create --candidate-id" in text
    assert "No proactive Discord send was performed." in text
    assert root.as_posix() not in text


def test_dm_next_action_includes_caption_style_advice_for_drafting_post_without_sending(tmp_path: Path):
    connection, draft, root = _create_draft(tmp_path)

    plan = build_dm_next_action_plan(connection, draft_id=draft.id, target_count=3)
    text = plan.to_text()

    assert plan.action == "media_selection"
    assert "Advisory recommendations:" in text
    assert "Caption style recommendations" in text
    assert f"Post: {draft.id}" in text
    assert "No caption was rewritten or saved." in text
    assert "No proactive Discord send was performed." in text
    assert root.as_posix() not in text


def test_dm_next_action_routes_drafting_post_to_selection_first_then_crop_before_copy(tmp_path: Path):
    connection, draft, root = _create_draft(tmp_path)

    plan = build_dm_next_action_plan(connection, draft_id=draft.id, target_count=3)
    text = plan.to_text()

    assert plan.action == "media_selection"
    assert plan.draft_id == draft.id
    assert "Send/prepare a private DM photo selection prompt" in text
    assert "Review flow order: selection_sheet → crop_sheet → copy_collaboration → final_preview" in text
    assert "contact-sheet-select.png" in text
    assert "contact-sheet-crop.png" in text
    assert "final-post-preview.png" in text
    assert "defer contact-sheet-crop.png until media/order is selected" in text
    assert "defer copy collaboration until crop review is ready" in text
    assert f"post-relay drafts artifacts render --post-id {draft.id} --stage select" in text
    assert f"post-relay discord dm-selection-send --post-id {draft.id} --target-count 3" in text
    assert "drafts guided-package-plan" not in text
    assert root.as_posix() not in text


def test_dm_next_action_routes_approved_post_to_scheduling_prompt(tmp_path: Path):
    connection, draft, _root = _create_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")

    plan = build_dm_next_action_plan(connection, draft_id=draft.id)

    assert plan.action == "schedule_prompt"
    assert "post-relay discord dm-schedule-send" in plan.to_text()
    assert "content approval is active" in plan.to_text()


def test_dm_next_action_routes_scheduled_post_to_double_confirm_publish_approval(tmp_path: Path):
    connection, draft, _root = _create_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    schedule_draft(connection, draft.id, scheduled_for="2026-05-21T09:30:00-07:00")

    plan = build_dm_next_action_plan(connection, draft_id=draft.id)
    text = plan.to_text()

    assert plan.action == "publish_approval_prompt"
    assert "final publish approval" in text
    assert f"post-relay discord dm-publish-approval-send --post-id {draft.id}" in text
    assert "does not publish to Instagram" in text


def test_dm_next_action_routes_ready_post_to_final_preview_and_guarded_publish(tmp_path: Path):
    connection, draft, _root = _create_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    schedule_draft(connection, draft.id, scheduled_for="2026-05-21T09:30:00-07:00")
    request_publish_approval(connection, draft.id)
    approve_draft_for_publishing(connection, draft.id, approved_by="andrew")

    plan = build_dm_next_action_plan(connection, draft_id=draft.id)
    text = plan.to_text()

    assert plan.action == "publish_preflight"
    assert "meta final-publish-preview" in text
    assert "meta publish-scheduled" in text
    assert "Stored final publish approval is durable" in text
    assert "No reapproval is needed inside Meta's 24-hour container window" in text
    assert "--execute" not in text
    assert "only with explicit active-session authorization" in text


def test_dm_next_action_includes_all_scheduled_posts_for_agent_awareness(tmp_path: Path):
    connection, draft, _root = _create_draft(tmp_path)
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    schedule_draft(connection, draft.id, scheduled_for="2026-06-01T09:30:00-07:00")

    candidate_cursor = connection.execute(
        "insert into candidate_groups (title, source_name, source_folder, post_type_recommendation, confidence, reason) values (?, ?, ?, ?, ?, ?)",
        ("Second post", "processed", "second-post", "carousel", 1.0, "test"),
    )
    cursor = connection.execute(
        "insert into drafts (candidate_group_id, post_type, status, scheduled_for) values (?, ?, ?, ?)",
        (int(candidate_cursor.lastrowid), "carousel", DraftState.READY_TO_PUBLISH.value, "2026-06-08T09:30:00-07:00"),
    )
    connection.commit()
    other_id = int(cursor.lastrowid)

    plan = build_dm_next_action_plan(connection, draft_id=draft.id)
    text = plan.to_text()

    assert "Scheduled posts:" in text
    assert f"#{draft.id} scheduled carousel at 2026-06-01T09:30:00-07:00" in text
    assert f"#{other_id} ready_to_publish carousel at 2026-06-08T09:30:00-07:00" in text
    assert "Use this queue before recommending another slot." in text


def test_dm_next_action_cli_renders_local_plan_without_network(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    root = tmp_path / "processed"
    folder = root / "2025" / "kyoto-night-market"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg"]:
        (folder / filename).write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
""".strip()
    )
    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])

    result = runner.invoke(app, ["dm", "next-action", "--post-id", "1", "--target-count", "2", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Post Relay DM next action" in result.output
    assert "Action: media_selection" in result.output
    assert "No Discord, Meta, or R2 network calls were made." in result.output
    assert root.as_posix() not in result.output

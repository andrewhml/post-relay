import json
from pathlib import Path
from typing import Optional

from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.guided_draft import accept_guided_draft_package, build_guided_draft_package
from post_relay.indexer import index_photo_sources
from post_relay.repository import (
    get_draft,
    get_guided_draft_package,
    list_candidate_groups,
    update_draft_content,
    upsert_guided_draft_package,
)

runner = CliRunner()


def _build_fixture_draft(tmp_path: Path, filenames: Optional[list[str]] = None):
    root = tmp_path / "processed"
    folder = root / "2025" / "seoul"
    folder.mkdir(parents=True)
    for filename in filenames or ["01-hero.jpg", "02-detail.jpg", "03-night.jpg"]:
        (folder / filename).write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    return connection, draft


def test_build_guided_draft_package_recommends_post_type_and_questions_without_fabricating_location(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)

    package = build_guided_draft_package(
        connection,
        draft.id,
        story_angle="neon side streets after a long food walk",
        mood="cinematic and personal",
        audience_hook="hidden city texture",
        include="mention the warm noodle shop glow",
        avoid="do not say Tokyo",
    )

    assert package.draft_id == draft.id
    assert package.post_type_recommendation == "carousel"
    assert "3 selected photos" in package.post_type_rationale
    assert package.location_text is None
    assert any("Confirm the exact location/place" in question for question in package.context_questions)
    assert len(package.caption_options) == 3
    assert all(option.startswith(("Hidden", "A ", "What")) for option in package.caption_options)
    assert "#travelphotography" in package.hashtag_suggestions
    assert package.alt_text.startswith("Travel photo set")
    assert "followers" in package.growth_rationale
    assert any("warm noodle shop glow" in option for option in package.caption_options)
    assert "Tokyo" not in package.to_text()
    assert any("Confirm the trip name" in question for question in package.context_questions)
    assert any("Confirm the date" in question for question in package.context_questions)
    rendered = package.to_text()
    assert "Guided Draft Package" in rendered
    assert "Do not fabricate" in rendered
    assert "Needs Andrew confirmation" in rendered


def test_accept_guided_draft_package_persists_fields_and_audited_rationale(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)
    package = build_guided_draft_package(
        connection,
        draft.id,
        location_text="Seoul, South Korea",
        story_angle="blue-hour food alleys",
        mood="cinematic",
        audience_hook="where the city starts glowing",
    )

    accepted = accept_guided_draft_package(connection, package, caption_index=2)

    updated = get_draft(connection, draft.id)
    stored = get_guided_draft_package(connection, draft.id)
    assert accepted.caption == package.caption_options[1]
    assert updated.caption == package.caption_options[1]
    assert updated.location_text == "Seoul, South Korea"
    assert json.loads(updated.hashtags_json) == package.hashtag_suggestions
    assert updated.alt_text == package.alt_text
    assert stored is not None
    assert stored.growth_rationale == package.growth_rationale
    assert stored.caption_options == package.caption_options


def test_accept_guided_draft_package_clears_stale_location_when_unconfirmed(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)
    update_draft_content(connection, draft.id, location_text="Old inferred place")
    package = build_guided_draft_package(
        connection,
        draft.id,
        story_angle="blue-hour food alleys",
        mood="cinematic",
        audience_hook="where the city starts glowing",
    )

    accept_guided_draft_package(connection, package, caption_index=1)

    updated = get_draft(connection, draft.id)
    assert updated.location_text is None


def test_upsert_guided_draft_package_can_store_unaccepted_package(tmp_path: Path):
    connection, draft = _build_fixture_draft(tmp_path)

    record = upsert_guided_draft_package(
        connection,
        draft_id=draft.id,
        post_type_recommendation="carousel",
        post_type_rationale="Needs review",
        caption_options=["Option one"],
        hashtag_suggestions=["#travelphotography"],
        location_text=None,
        alt_text="Alt text",
        growth_rationale="Growth rationale",
        context_questions=["Confirm the date"],
    )

    assert record.accepted_at is None
    assert record.caption_options == ["Option one"]


def test_cli_guided_draft_package_plan_and_accept(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "seoul"
    folder.mkdir(parents=True)
    for filename in ["01-hero.jpg", "02-detail.jpg"]:
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
    db_path = tmp_path / "post_relay.sqlite"
    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])

    plan_result = runner.invoke(
        app,
        [
            "drafts",
            "guided-package-plan",
            "--draft-id",
            "1",
            "--location",
            "Seoul, South Korea",
            "--story-angle",
            "night market alleys",
            "--mood",
            "cinematic",
            "--audience-hook",
            "food and light",
            "--db",
            str(db_path),
        ],
    )
    accept_result = runner.invoke(
        app,
        [
            "drafts",
            "guided-package-accept",
            "--draft-id",
            "1",
            "--location",
            "Seoul, South Korea",
            "--story-angle",
            "night market alleys",
            "--mood",
            "cinematic",
            "--audience-hook",
            "food and light",
            "--caption-index",
            "1",
            "--db",
            str(db_path),
        ],
    )

    assert plan_result.exit_code == 0
    assert "Guided Draft Package" in plan_result.output
    assert "Post type recommendation: carousel" in plan_result.output
    assert accept_result.exit_code == 0
    assert "Accepted guided draft package for draft #1" in accept_result.output
    assert "Caption:" in accept_result.output

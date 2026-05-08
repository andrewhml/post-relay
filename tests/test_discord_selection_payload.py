from pathlib import Path
from typing import Optional

from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.discord_preview import build_discord_selection_payload
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups


runner = CliRunner()


def _build_fixture_draft(tmp_path: Path, filenames: Optional[list[str]] = None):
    root = tmp_path / "processed"
    folder = root / "2025" / "osaka"
    folder.mkdir(parents=True)
    for filename in filenames or ["01-hero.jpg", "02-food.jpg", "03-street.jpg", "04-night.jpg"]:
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
    return connection, draft, folder


def test_build_discord_selection_payload_renders_numbered_request_and_interaction_semantics(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)
    contact_sheet = tmp_path / "artifacts" / "draft-1" / "contact-sheet.jpg"
    contact_sheet.parent.mkdir(parents=True)
    contact_sheet.write_bytes(b"fake contact sheet")

    payload = build_discord_selection_payload(
        connection,
        draft.id,
        target_count=3,
        post_type="carousel",
        artifact_paths=[contact_sheet],
    )

    assert payload.draft_id == draft.id
    assert payload.destination == "discord"
    assert payload.dry_run is True
    assert payload.target_count == 3
    assert payload.suggested_count == 4
    assert payload.ready_to_send is True
    assert payload.image_paths == [
        (folder / "01-hero.jpg").as_posix(),
        (folder / "02-food.jpg").as_posix(),
        (folder / "03-street.jpg").as_posix(),
        (folder / "04-night.jpg").as_posix(),
    ]
    assert payload.artifact_paths == [contact_sheet.as_posix()]
    rendered = payload.to_text()
    assert "Discord Selection Payload (dry run)" in rendered
    assert "Select 3 of 4 suggested photos" in rendered
    assert "Interaction semantics:" in rendered
    assert "Accept exactly 3 selected photo numbers" in rendered
    assert "Lead/cover must be one of the selected numbers" in rendered
    assert "Command fallback:" in rendered
    assert "discord-selection-apply --draft-id" in rendered
    assert "Instagram Capability Matrix" in rendered
    assert "caption: publishable" in rendered
    assert "alt_text: review_only" in rendered
    assert "location_tag: needs_validation" in rendered
    assert "1. 01-hero.jpg" in rendered
    assert contact_sheet.as_posix() in rendered


def test_build_discord_selection_payload_reports_missing_media_and_artifacts(tmp_path: Path):
    connection, draft, folder = _build_fixture_draft(tmp_path)
    (folder / "03-street.jpg").unlink()
    missing_contact_sheet = tmp_path / "artifacts" / "draft-1" / "contact-sheet.jpg"

    payload = build_discord_selection_payload(
        connection,
        draft.id,
        target_count=3,
        post_type="carousel",
        artifact_paths=[missing_contact_sheet],
    )

    assert payload.ready_to_send is False
    assert payload.image_paths == [
        (folder / "01-hero.jpg").as_posix(),
        (folder / "02-food.jpg").as_posix(),
        (folder / "04-night.jpg").as_posix(),
    ]
    assert payload.missing_image_paths == [(folder / "03-street.jpg").as_posix()]
    assert payload.artifact_paths == []
    assert payload.missing_artifact_paths == [missing_contact_sheet.as_posix()]
    rendered = payload.to_text()
    assert "Ready to send: no" in rendered
    assert "Missing image files:" in rendered
    assert f"  - {(folder / '03-street.jpg').as_posix()}" in rendered
    assert f"  3. <missing> {(folder / '03-street.jpg').as_posix()}" in rendered
    assert f"  4. {(folder / '04-night.jpg').as_posix()}" in rendered
    assert f"  3. {(folder / '04-night.jpg').as_posix()}" not in rendered
    assert "Missing artifact files:" in rendered
    assert f"  - {missing_contact_sheet.as_posix()}" in rendered
    assert "Fallbacks if Discord attachments fail:" in rendered


def test_cli_discord_selection_preview_outputs_dry_run_payload_without_sending(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "osaka"
    folder.mkdir(parents=True)
    for filename in ["01-hero.jpg", "02-food.jpg", "03-street.jpg"]:
        (folder / filename).write_bytes(b"fake image")
    contact_sheet = tmp_path / "artifacts" / "draft-1" / "contact-sheet.jpg"
    contact_sheet.parent.mkdir(parents=True)
    contact_sheet.write_bytes(b"fake contact sheet")
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
    result = runner.invoke(
        app,
        [
            "drafts",
            "discord-selection-preview",
            "--draft-id",
            "1",
            "--target-count",
            "2",
            "--artifact-path",
            str(contact_sheet),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Discord Selection Payload (dry run)" in result.output
    assert "Dry run: yes" in result.output
    assert "No Discord messages were sent." in result.output
    assert "Select 2 of 3 suggested photos" in result.output
    assert "1. 01-hero.jpg" in result.output
    assert contact_sheet.as_posix() in result.output

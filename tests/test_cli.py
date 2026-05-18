from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.repository import create_r2_staged_object_record, list_candidate_group_photo_paths


runner = CliRunner()


def test_cli_db_init_creates_database(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"

    result = runner.invoke(app, ["db", "init", "--db", str(db_path)])

    assert result.exit_code == 0
    assert db_path.exists()
    assert "Initialized database" in result.output


def test_cli_index_scan_and_library_stats(tmp_path: Path):
    root = tmp_path / "processed"
    (root / "2023").mkdir(parents=True)
    (root / "2023" / "kyoto.jpg").write_bytes(b"fake image")
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

    scan_result = runner.invoke(
        app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)]
    )
    stats_result = runner.invoke(app, ["library", "stats", "--db", str(db_path)])

    assert scan_result.exit_code == 0
    assert "Indexed 1 photos from 1 source" in scan_result.output
    assert stats_result.exit_code == 0
    assert "Total photos: 1" in stats_result.output
    assert "processed: 1" in stats_result.output
    assert "2023: 1" in stats_result.output


def test_cli_candidate_build_and_list(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
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
    build_result = runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    list_result = runner.invoke(app, ["candidates", "list", "--db", str(db_path)])

    assert build_result.exit_code == 0
    assert "Created 1 candidate group" in build_result.output
    assert list_result.exit_code == 0
    assert "2023 / kyoto" in list_result.output
    assert "carousel" in list_result.output
    assert "2 photos" in list_result.output


def test_cli_draft_create_and_list(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
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
    create_result = runner.invoke(
        app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)]
    )
    list_result = runner.invoke(app, ["drafts", "list", "--db", str(db_path)])

    assert create_result.exit_code == 0
    assert "Created draft #1 from candidate #1" in create_result.output
    assert list_result.exit_code == 0
    assert "#1 candidate #1" in list_result.output
    assert "carousel" in list_result.output
    assert "drafting" in list_result.output


def test_cli_draft_preview_outputs_review_package(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
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
    preview_result = runner.invoke(app, ["drafts", "preview", "--draft-id", "1", "--db", str(db_path)])

    assert preview_result.exit_code == 0
    assert "Draft Review Package" in preview_result.output
    assert "Draft ID: 1" in preview_result.output
    assert "Status: drafting" in preview_result.output
    assert "Candidate: 2023 / kyoto" in preview_result.output
    assert "Post type: carousel" in preview_result.output
    assert (folder / "garden.jpg").as_posix() in preview_result.output
    assert (folder / "temple.jpg").as_posix() in preview_result.output
    assert "Caption: <empty>" in preview_result.output
    assert "Unresolved context notes:" in preview_result.output
    assert "Allowed next actions:" in preview_result.output


def test_cli_draft_artifacts_render_creates_local_review_artifacts(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    folder.mkdir(parents=True)
    Image.new("RGB", (400, 300), color="red").save(folder / "shibuya.jpg", format="JPEG")
    Image.new("RGB", (300, 500), color="blue").save(folder / "rooftop.jpg", format="JPEG")
    artifact_root = tmp_path / "review_artifacts"
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
review_artifacts:
  root: {artifact_root.as_posix()}
  thumbnail_max_px: 120
  contact_sheet_columns: 2
  mode: local
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
            "artifacts",
            "render",
            "--draft-id",
            "1",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Review Artifacts" in result.output
    assert "Draft ID: 1" in result.output
    assert "Thumbnails:" in result.output
    assert "Contact sheet:" in result.output
    assert (artifact_root / "draft-1" / "contact-sheet.jpg").is_file()
    assert len(list((artifact_root / "draft-1" / "thumbnails").glob("*.jpg"))) == 2


def test_cli_draft_r2_stage_plan_prints_sanitized_no_network_plan(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    folder.mkdir(parents=True)
    Image.new("RGB", (400, 300), color="red").save(folder / "shibuya crossing.jpg", format="JPEG")
    Image.new("RGB", (300, 500), color="blue").save(folder / "rooftop.jpg", format="JPEG")
    artifact_root = tmp_path / "review_artifacts"
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
review_artifacts:
  root: {artifact_root.as_posix()}
  thumbnail_max_px: 120
  contact_sheet_columns: 2
  mode: local
r2_staging:
  enabled: false
  bucket: post-relay-publish
  public_base_url: https://peddocks.net
  prefix: post-relay/staging
""".strip()
    )
    db_path = tmp_path / "post_relay.sqlite"

    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    runner.invoke(
        app,
        [
            "drafts",
            "artifacts",
            "render",
            "--draft-id",
            "1",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
        ],
    )

    result = runner.invoke(
        app,
        [
            "drafts",
            "r2-stage-plan",
            "--draft-id",
            "1",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "R2 Staging Plan (dry run)" in result.output
    assert "Draft ID: 1" in result.output
    assert "Ready to upload: yes" in result.output
    assert "https://peddocks.net/post-relay/staging/drafts/1/media/" in result.output
    assert "contact-sheet.jpg" in result.output
    assert "No network calls were made." in result.output
    assert tmp_path.as_posix() not in result.output.split("Object keys:")[-1]


def test_cli_draft_r2_stage_upload_and_cleanup_are_dry_run_by_default(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    folder.mkdir(parents=True)
    Image.new("RGB", (400, 300), color="red").save(folder / "shibuya.jpg", format="JPEG")
    artifact_root = tmp_path / "review_artifacts"
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
review_artifacts:
  root: {artifact_root.as_posix()}
  thumbnail_max_px: 120
  contact_sheet_columns: 2
  mode: local
r2_staging:
  enabled: true
  bucket: post-relay-publish
  endpoint_url: https://example-account.r2.cloudflarestorage.com
  public_base_url: https://peddocks.net
  prefix: post-relay/staging
""".strip()
    )
    db_path = tmp_path / "post_relay.sqlite"

    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    runner.invoke(
        app,
        ["drafts", "artifacts", "render", "--draft-id", "1", "--config", str(config_path), "--db", str(db_path)],
    )

    upload_result = runner.invoke(
        app,
        ["drafts", "r2-stage-upload", "--draft-id", "1", "--config", str(config_path), "--db", str(db_path)],
    )
    upload_with_artifacts_result = runner.invoke(
        app,
        [
            "drafts",
            "r2-stage-upload",
            "--draft-id",
            "1",
            "--include-review-artifacts",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
        ],
    )
    cleanup_result = runner.invoke(
        app,
        ["drafts", "r2-cleanup", "--draft-id", "1", "--config", str(config_path), "--db", str(db_path)],
    )

    assert upload_result.exit_code == 0
    assert "R2 Staging Upload (dry run)" in upload_result.output
    assert "Planned objects: 1" in upload_result.output
    assert "review-artifacts" not in upload_result.output
    assert "No network calls were made." in upload_result.output
    assert upload_with_artifacts_result.exit_code == 0
    assert "Planned objects: 3" in upload_with_artifacts_result.output
    assert "review-artifacts" in upload_with_artifacts_result.output
    assert cleanup_result.exit_code == 0
    assert "R2 Staging Cleanup (dry run)" in cleanup_result.output
    assert "No objects were deleted." in cleanup_result.output


def test_cli_draft_media_plan_and_edit_updates_lead_keep_and_post_type(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    folder.mkdir(parents=True)
    for filename in ["01-wide.jpg", "02-detail.jpg", "03-hero.jpg"]:
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
    plan_result = runner.invoke(app, ["drafts", "media-plan", "--draft-id", "1", "--db", str(db_path)])
    edit_result = runner.invoke(
        app,
        [
            "drafts",
            "media-edit",
            "--draft-id",
            "1",
            "--lead",
            "3",
            "--keep",
            "1,3",
            "--post-type",
            "carousel",
            "--db",
            str(db_path),
        ],
    )
    preview_result = runner.invoke(app, ["drafts", "preview", "--draft-id", "1", "--db", str(db_path)])

    assert plan_result.exit_code == 0
    assert "Draft Media Plan" in plan_result.output
    assert "1. [primary] included" in plan_result.output
    assert "3. [support] included" in plan_result.output
    assert edit_result.exit_code == 0
    assert "Updated media selection for draft #1" in edit_result.output
    assert "Lead: 03-hero.jpg" in edit_result.output
    assert "Excluded:" in edit_result.output
    assert "02-detail.jpg" in edit_result.output
    assert preview_result.exit_code == 0
    assert preview_result.output.index("03-hero.jpg") < preview_result.output.index("01-wide.jpg")
    assert "02-detail.jpg" not in preview_result.output


def test_cli_draft_approval_and_edit_invalidation_flow(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
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
    submit_result = runner.invoke(app, ["drafts", "submit", "--draft-id", "1", "--db", str(db_path)])
    approve_result = runner.invoke(
        app,
        [
            "drafts",
            "approve",
            "--draft-id",
            "1",
            "--approved-by",
            "andrew",
            "--notes",
            "Carousel direction approved.",
            "--db",
            str(db_path),
        ],
    )
    edit_result = runner.invoke(
        app,
        [
            "drafts",
            "edit",
            "--draft-id",
            "1",
            "--caption",
            "A quiet morning wandering through Kyoto temple gardens.",
            "--db",
            str(db_path),
        ],
    )
    list_result = runner.invoke(app, ["drafts", "list", "--db", str(db_path)])

    assert submit_result.exit_code == 0
    assert "Submitted draft #1 for review" in submit_result.output
    assert approve_result.exit_code == 0
    assert "Approved draft #1 for queue" in approve_result.output
    assert edit_result.exit_code == 0
    assert "Updated draft #1" in edit_result.output
    assert "invalidated active approvals" in edit_result.output
    assert list_result.exit_code == 0
    assert "needs_edits" in list_result.output


def test_cli_schedule_and_publish_approval_flow(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
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
    runner.invoke(app, ["drafts", "submit", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(
        app,
        ["drafts", "approve", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)],
    )
    schedule_result = runner.invoke(
        app,
        [
            "drafts",
            "schedule",
            "--draft-id",
            "1",
            "--scheduled-for",
            "2026-05-05T09:30:00-07:00",
            "--db",
            str(db_path),
        ],
    )
    request_result = runner.invoke(
        app, ["drafts", "request-publish-approval", "--draft-id", "1", "--db", str(db_path)]
    )
    approve_publish_result = runner.invoke(
        app,
        [
            "drafts",
            "approve-publish",
            "--draft-id",
            "1",
            "--approved-by",
            "andrew",
            "--notes",
            "Ready for the scheduled queue.",
            "--db",
            str(db_path),
        ],
    )
    list_result = runner.invoke(app, ["drafts", "list", "--db", str(db_path)])

    assert schedule_result.exit_code == 0
    assert "Scheduled draft #1 for 2026-05-05T09:30:00-07:00" in schedule_result.output
    assert request_result.exit_code == 0
    assert "Requested publish approval for draft #1" in request_result.output
    assert approve_publish_result.exit_code == 0
    assert "Approved draft #1 for publishing" in approve_publish_result.output
    assert list_result.exit_code == 0
    assert "ready_to_publish" in list_result.output



def test_cli_controlled_image_publish_dry_run_requires_ready_draft_and_redacts_url(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
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
    not_ready_result = runner.invoke(
        app,
        [
            "meta",
            "validate-image-publish",
            "--draft-id",
            "1",
            "--image-url",
            "https://example.com/test-image.jpg?token=abc123",
            "--db",
            str(db_path),
            "--dry-run",
        ],
    )

    runner.invoke(
        app,
        [
            "drafts",
            "edit",
            "--draft-id",
            "1",
            "--caption",
            "Temple morning.",
            "--db",
            str(db_path),
        ],
    )
    runner.invoke(app, ["drafts", "submit", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(
        app,
        ["drafts", "approve", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)],
    )
    runner.invoke(
        app,
        [
            "drafts",
            "schedule",
            "--draft-id",
            "1",
            "--scheduled-for",
            "2026-05-05T09:30:00-07:00",
            "--db",
            str(db_path),
        ],
    )
    runner.invoke(app, ["drafts", "request-publish-approval", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(
        app,
        ["drafts", "approve-publish", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)],
    )
    dry_run_result = runner.invoke(
        app,
        [
            "meta",
            "validate-image-publish",
            "--draft-id",
            "1",
            "--image-url",
            "https://example.com/test-image.jpg?token=abc123",
            "--db",
            str(db_path),
            "--dry-run",
        ],
    )

    assert not_ready_result.exit_code != 0
    assert "ready_to_publish" in not_ready_result.output
    assert dry_run_result.exit_code == 0
    assert "Single-image publish validation" in dry_run_result.output
    assert "Status: planned" in dry_run_result.output
    assert "https://example.com/test-image.jpg?token=<redacted>" in dry_run_result.output
    assert "abc123" not in dry_run_result.output
    assert "No Meta publishing endpoints were called." in dry_run_result.output



def test_cli_controlled_image_publish_execute_refuses_before_scheduled_time(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
""".strip()
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POST_RELAY_USER_ACCESS_TOKEN=fake-token",
                "POST_RELAY_INSTAGRAM_ACCOUNT_ID=17841400498120050",
            ]
        )
    )
    db_path = tmp_path / "post_relay.sqlite"

    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "edit", "--draft-id", "1", "--caption", "Temple morning.", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "submit", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "schedule", "--draft-id", "1", "--scheduled-for", "2026-05-05T09:30:00-07:00", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "request-publish-approval", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve-publish", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])

    result = runner.invoke(
        app,
        [
            "meta",
            "validate-image-publish",
            "--draft-id",
            "1",
            "--image-url",
            "https://example.com/test-image.jpg",
            "--db",
            str(db_path),
            "--env-file",
            str(env_file),
            "--execute",
            "--now",
            "2026-05-05T08:30:00-07:00",
        ],
    )

    assert result.exit_code != 0
    assert "2026-05-05T09:30:00-07:00" in result.output
    assert "refusing to publish before the scheduled time" in result.output
    assert "Current time:" in result.output
    assert "2026-05-05T08:30:00-07:00" in result.output
    assert "--publish-now" in result.output
    assert "fake-token" not in result.output



def test_cli_draft_discord_preview_payload_dry_run_reports_images(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
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
    payload_result = runner.invoke(
        app, ["drafts", "discord-preview", "--draft-id", "1", "--db", str(db_path)]
    )

    assert payload_result.exit_code == 0
    assert "Discord Preview Payload (dry run)" in payload_result.output
    assert "Ready to send: yes" in payload_result.output
    assert "Image attachments:" in payload_result.output
    assert (folder / "garden.jpg").as_posix() in payload_result.output
    assert (folder / "temple.jpg").as_posix() in payload_result.output
    assert "Missing image files:" in payload_result.output
    assert "  - <none>" in payload_result.output
    assert "Draft Review Package" in payload_result.output



def test_cli_meta_validate_readonly_dry_run_redacts_token(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POST_RELAY_USER_ACCESS_TOKEN=super-secret-token",
                "POST_RELAY_FACEBOOK_PAGE_ID=998312870038313",
                "POST_RELAY_INSTAGRAM_ACCOUNT_ID=17841400498120050",
            ]
        )
    )

    result = runner.invoke(
        app, ["meta", "validate-readonly", "--env-file", str(env_file), "--dry-run"]
    )

    assert result.exit_code == 0
    assert "Meta Graph read-only validation (dry run)" in result.output
    assert "graph.facebook.com" in result.output
    assert "998312870038313" in result.output
    assert "17841400498120050" in result.output
    assert "super-secret-token" not in result.output
    assert "<redacted>" in result.output
    assert "No publishing endpoints will be called." in result.output



def test_cli_draft_context_questions_generate_and_list(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
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
    generate_result = runner.invoke(
        app, ["drafts", "questions", "generate", "--draft-id", "1", "--db", str(db_path)]
    )
    list_result = runner.invoke(
        app, ["drafts", "questions", "list", "--draft-id", "1", "--db", str(db_path)]
    )

    assert generate_result.exit_code == 0
    assert "Generated 5 unresolved context questions for draft #1" in generate_result.output
    assert list_result.exit_code == 0
    assert "[place] Where exactly was this photo set taken?" in list_result.output
    assert "[trip_name] What trip or collection should this post be associated with?" in list_result.output
    assert "[approximate_date] Should this be described as part of the 2023 trip" in list_result.output


def test_cli_controlled_carousel_publish_dry_run_records_sanitized_plan(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
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
    runner.invoke(
        app,
        [
            "drafts",
            "edit",
            "--draft-id",
            "1",
            "--caption",
            "Kyoto garden sequence.",
            "--db",
            str(db_path),
        ],
    )
    runner.invoke(app, ["drafts", "submit", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])
    runner.invoke(
        app,
        [
            "drafts",
            "schedule",
            "--draft-id",
            "1",
            "--scheduled-for",
            "2026-05-05T09:30:00-07:00",
            "--db",
            str(db_path),
        ],
    )
    runner.invoke(app, ["drafts", "request-publish-approval", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve-publish", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])

    dry_run_result = runner.invoke(
        app,
        [
            "meta",
            "validate-carousel-publish",
            "--draft-id",
            "1",
            "--image-url",
            "https://example.com/temple.jpg?token=abc123",
            "--image-url",
            "https://example.com/garden.jpg?signature=def456",
            "--db",
            str(db_path),
            "--dry-run",
        ],
    )

    assert dry_run_result.exit_code == 0
    assert "Carousel publish validation" in dry_run_result.output
    assert "Status: planned" in dry_run_result.output
    assert "https://example.com/temple.jpg?token=<redacted>" in dry_run_result.output
    assert "https://example.com/garden.jpg?signature=<redacted>" in dry_run_result.output
    assert "abc123" not in dry_run_result.output
    assert "def456" not in dry_run_result.output
    assert "No Meta publishing endpoints were called." in dry_run_result.output


def test_cli_controlled_carousel_publish_dry_run_can_use_staged_r2_urls(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
r2_staging:
  enabled: true
  bucket: post-relay-publish
  public_base_url: https://peddocks.net
  prefix: post-relay/staging
""".strip()
    )
    db_path = tmp_path / "post_relay.sqlite"

    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "edit", "--draft-id", "1", "--caption", "Kyoto garden sequence.", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "submit", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "schedule", "--draft-id", "1", "--scheduled-for", "2026-05-05T09:30:00-07:00", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "request-publish-approval", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve-publish", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])
    connection = connect_db(db_path)
    initialize_db(connection)
    selected_paths = list_candidate_group_photo_paths(connection, 1)
    for index, source_path in enumerate(selected_paths, start=1):
        create_r2_staged_object_record(
            connection,
            draft_id=1,
            kind="draft_media",
            source_path=source_path,
            bucket="post-relay-publish",
            object_key=f"post-relay/staging/drafts/1/media/{index:02d}-image.jpg",
            public_url=f"https://peddocks.net/post-relay/staging/drafts/1/media/{index:02d}-image.jpg?token=secret",
        )
    connection.commit()

    dry_run_result = runner.invoke(
        app,
        [
            "meta",
            "validate-carousel-publish",
            "--draft-id",
            "1",
            "--from-staged-r2",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--dry-run",
        ],
    )

    assert dry_run_result.exit_code == 0
    assert "Carousel publish validation" in dry_run_result.output
    assert "https://peddocks.net/post-relay/staging/drafts/1/media/01-image.jpg?token=<redacted>" in dry_run_result.output
    assert "https://peddocks.net/post-relay/staging/drafts/1/media/02-image.jpg?token=<redacted>" in dry_run_result.output
    assert "secret" not in dry_run_result.output
    assert "No Meta publishing endpoints were called." in dry_run_result.output


def test_cli_scheduled_publish_preflight_uses_staged_r2_urls_without_meta_calls(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
r2_staging:
  enabled: true
  bucket: post-relay-publish
  public_base_url: https://peddocks.net
  prefix: post-relay/staging
""".strip()
    )
    db_path = tmp_path / "post_relay.sqlite"

    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "edit", "--draft-id", "1", "--caption", "Kyoto garden sequence.", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "submit", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "schedule", "--draft-id", "1", "--scheduled-for", "2026-05-05T09:30:00-07:00", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "request-publish-approval", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve-publish", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])
    connection = connect_db(db_path)
    initialize_db(connection)
    selected_paths = list_candidate_group_photo_paths(connection, 1)
    for index, source_path in enumerate(selected_paths, start=1):
        create_r2_staged_object_record(
            connection,
            draft_id=1,
            kind="draft_media",
            source_path=source_path,
            bucket="post-relay-publish",
            object_key=f"post-relay/staging/drafts/1/media/{index:02d}-image.jpg",
            public_url=f"https://peddocks.net/post-relay/staging/drafts/1/media/{index:02d}-image.jpg?token=secret",
        )
    connection.commit()

    result = runner.invoke(
        app,
        [
            "meta",
            "publish-scheduled",
            "--draft-id",
            "1",
            "--from-staged-r2",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--now",
            "2026-05-05T09:31:00-07:00",
        ],
    )

    assert result.exit_code == 0
    assert "Scheduled publish preflight" in result.output
    assert "Ready: yes" in result.output
    assert "https://peddocks.net/post-relay/staging/drafts/1/media/01-image.jpg?token=<redacted>" in result.output
    assert "secret" not in result.output
    assert "No Meta publishing endpoints were called." in result.output


def test_cli_final_publish_preview_shows_exact_meta_caption_and_review_only_fields(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
r2_staging:
  enabled: true
  bucket: post-relay-publish
  public_base_url: https://peddocks.net
  prefix: post-relay/staging
""".strip()
    )
    db_path = tmp_path / "post_relay.sqlite"

    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    runner.invoke(
        app,
        [
            "drafts",
            "edit",
            "--draft-id",
            "1",
            "--caption",
            "Kyoto garden sequence.",
            "--hashtags",
            "#travelphotography,#Kyoto",
            "--location",
            "Kyoto, Japan",
            "--alt-text",
            "Review-only accessibility note",
            "--db",
            str(db_path),
        ],
    )
    runner.invoke(app, ["drafts", "submit", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "schedule", "--draft-id", "1", "--scheduled-for", "2026-05-05T09:30:00-07:00", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "request-publish-approval", "--draft-id", "1", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "approve-publish", "--draft-id", "1", "--approved-by", "andrew", "--db", str(db_path)])
    connection = connect_db(db_path)
    initialize_db(connection)
    selected_paths = list_candidate_group_photo_paths(connection, 1)
    for index, source_path in enumerate(selected_paths, start=1):
        create_r2_staged_object_record(
            connection,
            draft_id=1,
            kind="draft_media",
            source_path=source_path,
            bucket="post-relay-publish",
            object_key=f"post-relay/staging/drafts/1/media/{index:02d}-image.jpg",
            public_url=f"https://peddocks.net/post-relay/staging/drafts/1/media/{index:02d}-image.jpg?token=secret",
        )
    connection.commit()

    result = runner.invoke(
        app,
        [
            "meta",
            "final-publish-preview",
            "--draft-id",
            "1",
            "--from-staged-r2",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Final publish preview" in result.output
    assert "Exact Meta-bound caption:" in result.output
    assert "Kyoto garden sequence." in result.output
    assert "#travelphotography #Kyoto" in result.output
    assert "Location handling: local/review-only" in result.output
    assert "Review-only fields:" in result.output
    assert "alt_text: Review-only accessibility note" in result.output
    assert "https://peddocks.net/post-relay/staging/drafts/1/media/01-image.jpg?token=<redacted>" in result.output
    assert "secret" not in result.output
    assert "No Meta publishing endpoints were called." in result.output

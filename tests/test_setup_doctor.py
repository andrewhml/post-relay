from pathlib import Path

from typer.testing import CliRunner

from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.setup_doctor import build_setup_doctor_report, render_setup_doctor_report


runner = CliRunner()


def _write_config(path: Path, photo_root: Path, artifact_root: Path, export_root: Path, *, r2_enabled: bool = False) -> None:
    path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {photo_root.as_posix()}
    source_type: processed_folder
review_artifacts:
  root: {artifact_root.as_posix()}
publish_exports:
  root: {export_root.as_posix()}
r2_staging:
  enabled: {str(r2_enabled).lower()}
  bucket: beta-post-relay
  endpoint_url: https://example.r2.cloudflarestorage.com
  public_base_url: https://media.example.com
  prefix: post-relay/tester-a
""".strip()
    )


def test_setup_doctor_reports_local_preview_ready_without_network_or_secret_output(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    artifact_root = tmp_path / "review_artifacts"
    artifact_root.mkdir()
    export_root = tmp_path / "publish_exports"
    export_root.mkdir()
    config_path = tmp_path / "photo_sources.yaml"
    _write_config(config_path, photo_root, artifact_root, export_root)
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POST_RELAY_USER_ACCESS_TOKEN=super-secret-token",
                "POST_RELAY_FACEBOOK_PAGE_ID=12345",
                "POST_RELAY_INSTAGRAM_ACCOUNT_ID=67890",
                "POST_RELAY_DISCORD_BOT_TOKEN=discord-secret-token",
                "POST_RELAY_DISCORD_TARGET_USER_ID=111222333",
            ]
        )
    )

    report = build_setup_doctor_report(config_path=config_path, db_path=db_path, env_file=env_path)
    rendered = render_setup_doctor_report(report)

    assert report.local_preview_ready is True
    assert report.network_calls_made is False
    assert "PASS config file exists" in rendered
    assert "PASS database exists" in rendered
    assert "PASS photo source 'processed' readable" in rendered
    assert "PASS review artifact root writable" in rendered
    assert "PASS publish export root writable" in rendered
    assert "PASS Meta env present" in rendered
    assert "PASS Discord env present" in rendered
    assert "SKIP R2 staging disabled" in rendered
    assert "super-secret-token" not in rendered
    assert "discord-secret-token" not in rendered
    assert "No network calls were made." in rendered


def test_setup_doctor_reports_actionable_missing_local_setup(tmp_path: Path):
    config_path = tmp_path / "missing-photo-sources.yaml"
    db_path = tmp_path / "missing.sqlite"
    env_path = tmp_path / ".env"

    report = build_setup_doctor_report(config_path=config_path, db_path=db_path, env_file=env_path)
    rendered = render_setup_doctor_report(report)

    assert report.local_preview_ready is False
    assert "FAIL config file missing" in rendered
    assert "WARN database missing" in rendered
    assert "WARN env file missing" in rendered
    assert f"cp config/photo_sources.example.yaml {config_path.as_posix()}" in rendered
    assert f"post-relay db init --db {db_path.as_posix()}" in rendered
    assert "No network calls were made." in rendered


def test_setup_doctor_reports_database_missing_as_not_local_preview_ready(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    config_path = tmp_path / "photo_sources.yaml"
    _write_config(config_path, photo_root, tmp_path / "review_artifacts", tmp_path / "publish_exports")

    report = build_setup_doctor_report(
        config_path=config_path,
        db_path=tmp_path / "missing.sqlite",
        env_file=tmp_path / ".env",
    )
    rendered = render_setup_doctor_report(report)

    assert report.local_preview_ready is False
    assert "WARN database missing" in rendered
    assert "Local preview ready: no" in rendered


def test_setup_doctor_reports_r2_enabled_requires_config_and_secret_env(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    config_path = tmp_path / "photo_sources.yaml"
    _write_config(config_path, photo_root, tmp_path / "review_artifacts", tmp_path / "publish_exports", r2_enabled=True)
    db_path = tmp_path / "post_relay.sqlite"
    connect_db(db_path).close()
    env_path = tmp_path / ".env"
    env_path.write_text("POST_RELAY_R2_ACCOUNT_ID=acct-only\n")

    report = build_setup_doctor_report(config_path=config_path, db_path=db_path, env_file=env_path)
    rendered = render_setup_doctor_report(report)

    assert "PASS R2 bucket configured" in rendered
    assert "PASS R2 S3 endpoint URL configured" in rendered
    assert "PASS R2 public base URL configured" in rendered
    assert "FAIL R2 env missing" in rendered
    assert "POST_RELAY_R2_ACCESS_KEY_ID" in rendered
    assert "POST_RELAY_R2_SECRET_ACCESS_KEY" in rendered
    assert "acct-only" not in rendered
    assert "No network calls were made." in rendered
    assert report.network_calls_made is False


def test_setup_doctor_flags_r2_public_base_that_reuses_s3_endpoint(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    config_path = tmp_path / "photo_sources.yaml"
    artifact_root = tmp_path / "review_artifacts"
    export_root = tmp_path / "publish_exports"
    endpoint_url = "https://example-account.r2.cloudflarestorage.com"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {photo_root.as_posix()}
    source_type: processed_folder
review_artifacts:
  root: {artifact_root.as_posix()}
publish_exports:
  root: {export_root.as_posix()}
r2_staging:
  enabled: true
  bucket: beta-post-relay
  endpoint_url: {endpoint_url}
  public_base_url: {endpoint_url}
  prefix: post-relay/tester-a
""".strip()
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POST_RELAY_R2_ACCOUNT_ID=example-account",
                "POST_RELAY_R2_ACCESS_KEY_ID=access-key-id",
                "POST_RELAY_R2_SECRET_ACCESS_KEY=secret-access-key",
            ]
        )
    )

    report = build_setup_doctor_report(config_path=config_path, db_path=tmp_path / "post_relay.sqlite", env_file=env_path)
    rendered = render_setup_doctor_report(report)

    assert "FAIL R2 endpoint/public URL separated" in rendered
    assert "endpoint_url is the S3 API URL" in rendered
    assert "public_base_url must be the unauthenticated public HTTPS object base" in rendered
    assert "secret-access-key" not in rendered
    assert report.network_calls_made is False


def test_setup_doctor_reports_r2_ready_without_printing_secret_values(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    config_path = tmp_path / "photo_sources.yaml"
    _write_config(config_path, photo_root, tmp_path / "review_artifacts", tmp_path / "publish_exports", r2_enabled=True)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POST_RELAY_R2_ACCOUNT_ID=example-account",
                "POST_RELAY_R2_ACCESS_KEY_ID=access-key-id",
                "POST_RELAY_R2_SECRET_ACCESS_KEY=secret-access-key",
            ]
        )
    )

    report = build_setup_doctor_report(config_path=config_path, db_path=tmp_path / "post_relay.sqlite", env_file=env_path)
    rendered = render_setup_doctor_report(report)

    assert "PASS R2 bucket configured" in rendered
    assert "PASS R2 S3 endpoint URL configured" in rendered
    assert "PASS R2 public base URL configured" in rendered
    assert "PASS R2 env present" in rendered
    assert "PASS R2 staging ready" in rendered
    assert "example-account" not in rendered
    assert "access-key-id" not in rendered
    assert "secret-access-key" not in rendered
    assert "No network calls were made." in rendered


def test_setup_doctor_cli_outputs_report(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    config_path = tmp_path / "photo_sources.yaml"
    _write_config(config_path, photo_root, tmp_path / "review_artifacts", tmp_path / "publish_exports")
    db_path = tmp_path / "post_relay.sqlite"
    connect_db(db_path).close()
    env_path = tmp_path / ".env"
    env_path.write_text("POST_RELAY_FACEBOOK_PAGE_ID=12345\n")

    result = runner.invoke(
        app,
        [
            "doctor",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--env-file",
            str(env_path),
        ],
    )

    assert result.exit_code == 0
    assert "Post Relay setup doctor" in result.output
    assert "PASS config file exists" in result.output
    assert "No network calls were made." in result.output

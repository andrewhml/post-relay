from pathlib import Path

import yaml
from typer.testing import CliRunner

from post_relay.cli import app
from post_relay.setup_wizard import run_setup_wizard, render_setup_wizard_result


runner = CliRunner()


def _write_templates(root: Path) -> tuple[Path, Path]:
    env_template = root / ".env.example"
    env_template.write_text("POST_RELAY_USER_ACCESS_TOKEN=\n")
    config_template = root / "config" / "photo_sources.example.yaml"
    config_template.parent.mkdir(parents=True)
    config_template.write_text(
        """
photo_sources:
  - name: local-processed-photos
    root: /path/to/your/processed/photos
    source_type: processed_folder
    enabled: true
    reliability_score: 1.0
review_artifacts:
  root: data/review_artifacts
publish_exports:
  root: data/publish_exports
r2_staging:
  enabled: false
supported_image_extensions:
  - .jpg
""".strip()
    )
    return env_template, config_template


def test_setup_wizard_creates_local_files_from_templates_without_network(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    env_template, config_template = _write_templates(tmp_path)
    env_path = tmp_path / ".env"
    config_path = tmp_path / "config" / "photo_sources.yaml"
    db_path = tmp_path / "data" / "post_relay.sqlite"

    result = run_setup_wizard(
        photo_root=photo_root,
        env_file=env_path,
        config_path=config_path,
        db_path=db_path,
        env_template=env_template,
        config_template=config_template,
        initialize_database=True,
    )
    rendered = render_setup_wizard_result(result)

    assert env_path.read_text() == env_template.read_text()
    loaded_config = yaml.safe_load(config_path.read_text())
    assert loaded_config["photo_sources"][0]["root"] == photo_root.as_posix()
    assert (tmp_path / "data" / "review_artifacts").is_dir()
    assert (tmp_path / "data" / "publish_exports").is_dir()
    assert db_path.exists()
    assert result.network_calls_made is False
    assert "CREATED .env" in rendered
    assert "CREATED config" in rendered
    assert "INITIALIZED database" in rendered
    assert "No network calls were made." in rendered
    assert f"post-relay doctor --config {config_path.as_posix()} --db {db_path.as_posix()} --env-file {env_path.as_posix()}" in rendered


def test_setup_wizard_does_not_overwrite_existing_private_files(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    env_template, config_template = _write_templates(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("KEEP_SECRET=do-not-touch\n")
    config_path = tmp_path / "config" / "photo_sources.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    original_config = "photo_sources:\n  - name: existing\n    root: /already/configured\n    source_type: processed_folder\n"
    config_path.write_text(original_config)
    db_path = tmp_path / "data" / "post_relay.sqlite"

    result = run_setup_wizard(
        photo_root=photo_root,
        env_file=env_path,
        config_path=config_path,
        db_path=db_path,
        env_template=env_template,
        config_template=config_template,
        initialize_database=False,
    )
    rendered = render_setup_wizard_result(result)

    assert env_path.read_text() == "KEEP_SECRET=do-not-touch\n"
    assert config_path.read_text() == original_config
    assert "SKIPPED .env exists" in rendered
    assert "SKIPPED config exists" in rendered
    assert "do-not-touch" not in rendered
    assert result.network_calls_made is False


def test_setup_wizard_cli_prompts_for_photo_root_and_sets_up_local_preview(tmp_path: Path):
    photo_root = tmp_path / "processed"
    photo_root.mkdir()
    env_template, config_template = _write_templates(tmp_path)
    env_path = tmp_path / ".env"
    config_path = tmp_path / "config" / "photo_sources.yaml"
    db_path = tmp_path / "data" / "post_relay.sqlite"

    result = runner.invoke(
        app,
        [
            "setup",
            "--env-file",
            str(env_path),
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--env-template",
            str(env_template),
            "--config-template",
            str(config_template),
        ],
        input=f"{photo_root.as_posix()}\n",
    )

    assert result.exit_code == 0
    assert "Processed/exported photo folder" in result.output
    assert "Post Relay setup wizard" in result.output
    assert "No network calls were made." in result.output
    loaded_config = yaml.safe_load(config_path.read_text())
    assert loaded_config["photo_sources"][0]["root"] == photo_root.as_posix()
    assert db_path.exists()


def test_setup_wizard_rejects_missing_photo_root(tmp_path: Path):
    missing_root = tmp_path / "missing"
    env_template, config_template = _write_templates(tmp_path)

    result = run_setup_wizard(
        photo_root=missing_root,
        env_file=tmp_path / ".env",
        config_path=tmp_path / "config" / "photo_sources.yaml",
        db_path=tmp_path / "data" / "post_relay.sqlite",
        env_template=env_template,
        config_template=config_template,
        initialize_database=True,
    )
    rendered = render_setup_wizard_result(result)

    assert result.success is False
    assert "FAIL photo root missing" in rendered
    assert not (tmp_path / ".env").exists()
    assert result.network_calls_made is False

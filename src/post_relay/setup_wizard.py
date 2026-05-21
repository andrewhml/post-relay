from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import yaml

from post_relay.db import connect_db, initialize_db


@dataclass(frozen=True)
class SetupWizardStep:
    status: str
    label: str
    detail: str = ""


@dataclass(frozen=True)
class SetupWizardResult:
    env_file: Path
    config_path: Path
    db_path: Path
    photo_root: Path
    steps: List[SetupWizardStep] = field(default_factory=list)
    next_commands: List[str] = field(default_factory=list)
    success: bool = True
    network_calls_made: bool = False


def run_setup_wizard(
    *,
    photo_root: Path,
    env_file: Path,
    config_path: Path,
    db_path: Path,
    env_template: Path = Path(".env.example"),
    config_template: Path = Path("config/photo_sources.example.yaml"),
    initialize_database: bool = True,
) -> SetupWizardResult:
    """Create a local-first Post Relay setup without overwriting private files or making network calls."""
    expanded_photo_root = photo_root.expanduser()
    steps: List[SetupWizardStep] = []

    if not expanded_photo_root.exists() or not expanded_photo_root.is_dir():
        steps.append(SetupWizardStep("FAIL", "photo root missing", expanded_photo_root.as_posix()))
        return SetupWizardResult(
            env_file=env_file,
            config_path=config_path,
            db_path=db_path,
            photo_root=expanded_photo_root,
            steps=steps,
            next_commands=["Choose an existing processed/exported photo folder and rerun post-relay setup"],
            success=False,
            network_calls_made=False,
        )

    _copy_template_if_missing(env_template, env_file, ".env", steps)
    _create_config_if_missing(config_template, config_path, expanded_photo_root, steps)
    _create_local_directories(config_path, steps)
    _initialize_database_if_requested(db_path, initialize_database, steps)

    next_commands = [
        f"post-relay doctor --config {config_path.as_posix()} --db {db_path.as_posix()} --env-file {env_file.as_posix()}",
        (
            'post-relay goals init --title "Travel account north star" '
            '--statement "<what are we trying to achieve?>" '
            '--target-audience "<who should this help?>" '
            '--pillar "<repeatable content theme>" '
            '--cadence "<posting rhythm>" '
            '--metric "<success signal>" '
            '--strategy-note "<how should the agent steer choices?>" '
            '--constraint "<what should the agent avoid?>" '
            f"--reviewed-by <name> --db {db_path.as_posix()}"
        ),
        f"post-relay index scan --config {config_path.as_posix()} --db {db_path.as_posix()}",
        f"post-relay library stats --db {db_path.as_posix()}",
        f"post-relay candidates build --db {db_path.as_posix()}",
        f"post-relay candidates list --db {db_path.as_posix()}",
    ]
    return SetupWizardResult(
        env_file=env_file,
        config_path=config_path,
        db_path=db_path,
        photo_root=expanded_photo_root,
        steps=steps,
        next_commands=next_commands,
        success=not any(step.status == "FAIL" for step in steps),
        network_calls_made=False,
    )


def render_setup_wizard_result(result: SetupWizardResult) -> str:
    lines = [
        "Post Relay setup wizard",
        f"Photo root: {result.photo_root.as_posix()}",
        f"Config: {result.config_path.as_posix()}",
        f"Database: {result.db_path.as_posix()}",
        f"Env file: {result.env_file.as_posix()}",
        "",
        "Steps:",
    ]
    for step in result.steps:
        detail = f" — {step.detail}" if step.detail else ""
        lines.append(f"{step.status} {step.label}{detail}")

    lines.append("")
    lines.append(f"Setup ready: {'yes' if result.success else 'no'}")
    lines.append("No network calls were made." if not result.network_calls_made else "Network calls were made.")

    if result.next_commands:
        lines.extend(["", "Next commands:"])
        lines.extend(f"- {command}" for command in result.next_commands)
    return "\n".join(lines)


def _copy_template_if_missing(template: Path, destination: Path, label: str, steps: List[SetupWizardStep]) -> None:
    if destination.exists():
        steps.append(SetupWizardStep("SKIPPED", f"{label} exists", destination.as_posix()))
        return
    if not template.exists():
        steps.append(SetupWizardStep("FAIL", f"{label} template missing", template.as_posix()))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, destination)
    steps.append(SetupWizardStep("CREATED", label, destination.as_posix()))


def _create_config_if_missing(template: Path, destination: Path, photo_root: Path, steps: List[SetupWizardStep]) -> None:
    if destination.exists():
        steps.append(SetupWizardStep("SKIPPED", "config exists", destination.as_posix()))
        return
    if not template.exists():
        steps.append(SetupWizardStep("FAIL", "config template missing", template.as_posix()))
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    data = _read_yaml_template(template)
    sources = data.get("photo_sources")
    if not isinstance(sources, list) or not sources:
        sources = [{}]
    first_source = dict(sources[0] or {})
    first_source.update(
        {
            "name": first_source.get("name") or "local-processed-photos",
            "root": photo_root.as_posix(),
            "source_type": first_source.get("source_type") or "processed_folder",
            "enabled": True,
            "reliability_score": first_source.get("reliability_score", 1.0),
        }
    )
    data["photo_sources"] = [first_source, *sources[1:]]
    destination.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    steps.append(SetupWizardStep("CREATED", "config", destination.as_posix()))


def _read_yaml_template(template: Path) -> dict[str, Any]:
    data = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _create_local_directories(config_path: Path, steps: List[SetupWizardStep]) -> None:
    if not config_path.exists():
        steps.append(SetupWizardStep("SKIPPED", "local data directories", "config unavailable"))
        return
    data = _read_yaml_template(config_path)
    project_root = _infer_project_root(config_path)
    for label, root in [
        ("review artifact root", _nested_root(data, "review_artifacts")),
        ("publish export root", _nested_root(data, "publish_exports")),
    ]:
        if root is None:
            steps.append(SetupWizardStep("SKIPPED", label, "not configured"))
            continue
        directory = _resolve_config_path(root, project_root)
        directory.mkdir(parents=True, exist_ok=True)
        steps.append(SetupWizardStep("CREATED", label, directory.as_posix()))


def _nested_root(data: dict[str, Any], key: str) -> str | None:
    section = data.get(key)
    if isinstance(section, dict) and section.get("root"):
        return str(section["root"])
    return None


def _resolve_config_path(raw_path: str, project_root: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return project_root / path


def _infer_project_root(config_path: Path) -> Path:
    if config_path.parent.name == "config":
        return config_path.parent.parent
    return config_path.parent


def _initialize_database_if_requested(db_path: Path, initialize_database: bool, steps: List[SetupWizardStep]) -> None:
    if not initialize_database:
        steps.append(SetupWizardStep("SKIPPED", "database initialization", "disabled by option"))
        return
    if db_path.exists():
        steps.append(SetupWizardStep("SKIPPED", "database exists", db_path.as_posix()))
        return
    connection = connect_db(db_path)
    initialize_db(connection)
    connection.close()
    steps.append(SetupWizardStep("INITIALIZED", "database", db_path.as_posix()))

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from post_relay.config import PostRelayConfig, load_config


META_ENV_VARS = [
    "POST_RELAY_USER_ACCESS_TOKEN",
    "POST_RELAY_FACEBOOK_PAGE_ID",
    "POST_RELAY_INSTAGRAM_ACCOUNT_ID",
]

DISCORD_ENV_VARS = [
    "POST_RELAY_DISCORD_BOT_TOKEN",
    "POST_RELAY_DISCORD_TARGET_USER_ID",
]

DEFAULT_R2_ENV_VARS = [
    "POST_RELAY_R2_ACCOUNT_ID",
    "POST_RELAY_R2_ACCESS_KEY_ID",
    "POST_RELAY_R2_SECRET_ACCESS_KEY",
]


@dataclass(frozen=True)
class DoctorCheck:
    status: str
    label: str
    detail: str = ""


@dataclass(frozen=True)
class SetupDoctorReport:
    config_path: Path
    db_path: Path
    env_file: Path
    checks: List[DoctorCheck] = field(default_factory=list)
    next_commands: List[str] = field(default_factory=list)
    local_preview_ready: bool = False
    network_calls_made: bool = False


def build_setup_doctor_report(config_path: Path, db_path: Path, env_file: Path) -> SetupDoctorReport:
    """Build a no-network setup readiness report for a local Post Relay instance."""
    checks: List[DoctorCheck] = []
    next_commands: List[str] = []
    env_values = _read_env_file(env_file)
    loaded_config: Optional[PostRelayConfig] = None

    if config_path.exists():
        checks.append(DoctorCheck("PASS", "config file exists", config_path.as_posix()))
        try:
            loaded_config = load_config(config_path)
        except Exception as exc:  # noqa: BLE001 - render actionable config parser errors without crashing doctor.
            checks.append(DoctorCheck("FAIL", "config file invalid", str(exc)))
            next_commands.append(f"Edit {config_path.as_posix()} and rerun post-relay doctor")
    else:
        checks.append(DoctorCheck("FAIL", "config file missing", config_path.as_posix()))
        next_commands.append(f"cp config/photo_sources.example.yaml {config_path.as_posix()}")

    if db_path.exists():
        checks.append(DoctorCheck("PASS", "database exists", db_path.as_posix()))
    else:
        checks.append(DoctorCheck("WARN", "database missing", db_path.as_posix()))
        next_commands.append(f"post-relay db init --db {db_path.as_posix()}")

    if env_file.exists():
        checks.append(DoctorCheck("PASS", "env file exists", env_file.as_posix()))
    else:
        checks.append(DoctorCheck("WARN", "env file missing", env_file.as_posix()))
        next_commands.append(f"cp .env.example {env_file.as_posix()}")

    if loaded_config is not None:
        checks.extend(_photo_source_checks(loaded_config))
        checks.append(_writable_path_check("review artifact root writable", loaded_config.review_artifacts.root))
        checks.append(_writable_path_check("publish export root writable", loaded_config.publish_exports.root))
        checks.append(_r2_check(loaded_config, env_values))
    else:
        checks.append(DoctorCheck("SKIP", "photo sources not checked", "config unavailable"))
        checks.append(DoctorCheck("SKIP", "review artifact root not checked", "config unavailable"))
        checks.append(DoctorCheck("SKIP", "publish export root not checked", "config unavailable"))
        checks.append(DoctorCheck("SKIP", "R2 staging not checked", "config unavailable"))

    checks.append(_env_group_check("Meta env present", META_ENV_VARS, env_values, skip_label="Meta env optional"))
    checks.append(_env_group_check("Discord env present", DISCORD_ENV_VARS, env_values, skip_label="Discord env optional"))

    local_preview_ready = _local_preview_ready(checks)
    if local_preview_ready:
        next_commands.append(
            f"post-relay index scan --config {config_path.as_posix()} --db {db_path.as_posix()}"
        )
    else:
        next_commands.append("Fix FAIL items above, then rerun post-relay doctor")

    return SetupDoctorReport(
        config_path=config_path,
        db_path=db_path,
        env_file=env_file,
        checks=checks,
        next_commands=_dedupe(next_commands),
        local_preview_ready=local_preview_ready,
        network_calls_made=False,
    )


def render_setup_doctor_report(report: SetupDoctorReport) -> str:
    lines = [
        "Post Relay setup doctor",
        f"Config: {report.config_path.as_posix()}",
        f"Database: {report.db_path.as_posix()}",
        f"Env file: {report.env_file.as_posix()}",
        "",
        "Checks:",
    ]
    for check in report.checks:
        detail = f" — {check.detail}" if check.detail else ""
        lines.append(f"{check.status} {check.label}{detail}")

    lines.append("")
    lines.append(f"Local preview ready: {'yes' if report.local_preview_ready else 'no'}")
    lines.append("No network calls were made." if not report.network_calls_made else "Network calls were made.")

    if report.next_commands:
        lines.extend(["", "Next commands:"])
        lines.extend(f"- {command}" for command in report.next_commands)

    return "\n".join(lines)


def _photo_source_checks(config: PostRelayConfig) -> List[DoctorCheck]:
    if not config.photo_sources:
        return [DoctorCheck("FAIL", "photo sources configured", "no photo_sources entries found")]

    checks: List[DoctorCheck] = []
    for source in config.photo_sources:
        if not source.enabled:
            checks.append(DoctorCheck("SKIP", f"photo source '{source.name}' disabled", source.root.as_posix()))
            continue
        if source.root.exists() and source.root.is_dir() and os.access(source.root, os.R_OK):
            checks.append(DoctorCheck("PASS", f"photo source '{source.name}' readable", source.root.as_posix()))
        elif source.root.exists():
            checks.append(DoctorCheck("FAIL", f"photo source '{source.name}' readable", f"not a readable directory: {source.root.as_posix()}"))
        else:
            checks.append(DoctorCheck("FAIL", f"photo source '{source.name}' readable", f"missing: {source.root.as_posix()}"))
    return checks


def _writable_path_check(label: str, path: Path) -> DoctorCheck:
    if path.exists():
        if path.is_dir() and os.access(path, os.W_OK):
            return DoctorCheck("PASS", label, path.as_posix())
        return DoctorCheck("FAIL", label, f"not a writable directory: {path.as_posix()}")
    parent = path.parent if path.parent != Path("") else Path(".")
    if parent.exists() and parent.is_dir() and os.access(parent, os.W_OK):
        return DoctorCheck("PASS", label, f"can create under {parent.as_posix()}")
    return DoctorCheck("FAIL", label, f"missing and parent not writable: {path.as_posix()}")


def _r2_check(config: PostRelayConfig, env_values: Dict[str, str]) -> DoctorCheck:
    r2 = config.r2_staging
    if not r2.enabled:
        return DoctorCheck("SKIP", "R2 staging disabled", "enable r2_staging only when you need public HTTPS media URLs")

    missing_config = [
        name
        for name, value in [
            ("bucket", r2.bucket),
            ("endpoint_url", r2.endpoint_url),
            ("public_base_url", r2.public_base_url),
        ]
        if not value
    ]
    if missing_config:
        return DoctorCheck("FAIL", "R2 config missing", ", ".join(missing_config))

    required_env = [r2.account_id_env, r2.access_key_id_env, r2.secret_access_key_env]
    missing_env = _missing_env(required_env, env_values)
    if missing_env:
        return DoctorCheck("FAIL", "R2 env missing", ", ".join(missing_env))
    return DoctorCheck("PASS", "R2 staging configured", "required config and env var names are present")


def _env_group_check(label: str, required: Iterable[str], env_values: Dict[str, str], *, skip_label: str) -> DoctorCheck:
    missing = _missing_env(required, env_values)
    if not missing:
        return DoctorCheck("PASS", label, ", ".join(required))
    present = [name for name in required if env_values.get(name)]
    if present:
        return DoctorCheck("WARN", label, f"missing: {', '.join(missing)}")
    return DoctorCheck("SKIP", skip_label, f"missing: {', '.join(missing)}")


def _missing_env(required: Iterable[str], env_values: Dict[str, str]) -> List[str]:
    return [name for name in required if not env_values.get(name)]


def _local_preview_ready(checks: Iterable[DoctorCheck]) -> bool:
    blocking_labels = (
        "config file",
        "config file invalid",
        "database missing",
        "photo source",
        "review artifact root",
        "publish export root",
    )
    for check in checks:
        if check.status in {"FAIL", "WARN"} and any(fragment in check.label for fragment in blocking_labels):
            return False
    return True


def _read_env_file(env_file: Path) -> Dict[str, str]:
    if not env_file.exists():
        return {}
    values: Dict[str, str] = {}
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _strip_optional_quotes(value.strip())
    return values


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _dedupe(items: Iterable[str]) -> List[str]:
    result: List[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result

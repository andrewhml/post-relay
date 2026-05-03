from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path("data/post_relay.sqlite")
ENV_PATH = Path(".env")


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def configured(name: str, env_values: dict[str, str]) -> bool:
    return bool(os.environ.get(name) or env_values.get(name))


def main() -> None:
    env_values = read_env_file(ENV_PATH)
    print("Publish smoke readiness")
    print(f".env exists: {'yes' if ENV_PATH.exists() else 'no'}")
    for name in (
        "POST_RELAY_USER_ACCESS_TOKEN",
        "POST_RELAY_INSTAGRAM_ACCOUNT_ID",
        "POST_RELAY_TEST_IMAGE_URL",
    ):
        print(f"{name} configured: {'yes' if configured(name, env_values) else 'no'}")
    print(f"database exists: {'yes' if DB_PATH.exists() else 'no'}")

    if not DB_PATH.exists():
        return

    connection = sqlite3.connect(DB_PATH)
    rows = connection.execute(
        """
        select drafts.id, drafts.post_type, drafts.status, drafts.caption,
               count(candidate_group_items.photo_id) as photo_count
        from drafts
        left join candidate_groups on candidate_groups.id = drafts.candidate_group_id
        left join candidate_group_items on candidate_group_items.group_id = candidate_groups.id
        group by drafts.id
        order by drafts.id
        """
    ).fetchall()
    print(f"draft count: {len(rows)}")
    ready_single = [row for row in rows if row[1] == "single_image" and row[2] == "ready_to_publish" and row[3] and row[4] == 1]
    print(f"ready single-image drafts with caption: {len(ready_single)}")
    if ready_single:
        print("ready draft ids: " + ", ".join(str(row[0]) for row in ready_single))
    else:
        print("ready draft ids: <none>")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from typing import Optional

from post_relay.repository import DraftRecord


def parse_hashtags(hashtags_json: Optional[str]) -> list[str]:
    if not hashtags_json:
        return []
    try:
        raw_values = json.loads(hashtags_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw_values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        if not isinstance(raw_value, str):
            continue
        value = raw_value.strip()
        if not value:
            continue
        if not value.startswith("#"):
            value = f"#{value}"
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def compose_final_meta_caption(draft: DraftRecord) -> str:
    base_caption = (draft.caption or "").strip()
    hashtags_to_add: list[str] = []
    caption_words = set(base_caption.lower().split())
    for hashtag in parse_hashtags(draft.hashtags_json):
        if hashtag.lower() not in caption_words:
            hashtags_to_add.append(hashtag)
    if not hashtags_to_add:
        return base_caption
    hashtag_line = " ".join(hashtags_to_add)
    if not base_caption:
        return hashtag_line
    return f"{base_caption}\n\n{hashtag_line}"

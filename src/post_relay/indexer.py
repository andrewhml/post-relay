from __future__ import annotations

from dataclasses import dataclass

from post_relay.config import PostRelayConfig
from post_relay.media.scanner import scan_photo_sources
from post_relay.repository import upsert_photo_source, upsert_scanned_photo


@dataclass(frozen=True)
class IndexResult:
    scanned_count: int
    inserted_or_updated_count: int
    source_count: int
    enriched_count: int


def index_photo_sources(connection, config: PostRelayConfig) -> IndexResult:
    enabled_sources = [source for source in config.photo_sources if source.enabled]
    source_ids = {source.name: upsert_photo_source(connection, source) for source in enabled_sources}
    scanned_items = scan_photo_sources(config)

    for item in scanned_items:
        upsert_scanned_photo(connection, item, source_ids[item.source_name])

    connection.commit()
    return IndexResult(
        scanned_count=len(scanned_items),
        inserted_or_updated_count=len(scanned_items),
        source_count=len(enabled_sources),
        enriched_count=sum(1 for item in scanned_items if item.has_local_metadata),
    )

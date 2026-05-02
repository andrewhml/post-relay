from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal

import yaml
from pydantic import BaseModel, Field


class PhotoSource(BaseModel):
    """A configured source of candidate media."""

    name: str
    root: Path
    source_type: Literal["processed_folder", "immich", "manual"] = "processed_folder"
    enabled: bool = True
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0)


class PostRelayConfig(BaseModel):
    """Runtime configuration for Post Relay."""

    photo_sources: List[PhotoSource] = Field(default_factory=list)
    supported_image_extensions: List[str] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff"]
    )


def load_config(path: Path) -> PostRelayConfig:
    """Load Post Relay configuration from a YAML file."""
    data = _read_yaml_mapping(path)
    sources = data.get("photo_sources", [])
    normalized_sources = []
    for source in sources:
        normalized = dict(source)
        if "root" in normalized:
            normalized["root"] = Path(str(normalized["root"])).expanduser()
        normalized_sources.append(normalized)
    data["photo_sources"] = normalized_sources
    return PostRelayConfig(**data)


def _read_yaml_mapping(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data

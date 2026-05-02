from pathlib import Path

from post_relay.config import load_config


def test_load_config_from_yaml_expands_user_and_defaults(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    source_root = home / "Pictures" / "Processed"
    source_root.mkdir(parents=True)
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        """
photo_sources:
  - name: processed
    root: ~/Pictures/Processed
    source_type: processed_folder
    reliability_score: 0.95
""".strip()
    )
    monkeypatch.setenv("HOME", str(home))

    config = load_config(config_path)

    assert len(config.photo_sources) == 1
    source = config.photo_sources[0]
    assert source.name == "processed"
    assert source.root == source_root
    assert source.source_type == "processed_folder"
    assert source.enabled is True
    assert source.reliability_score == 0.95

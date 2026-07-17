from pathlib import Path

import yaml


def test_config_has_only_the_requested_change():
    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))

    assert config == {
        "provider": "gemini",
        "timeout": 10,
        "retries": 2,
    }

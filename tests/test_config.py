import json
import pytest
import config


MOCK_CONFIG = {
    "mqtt": {"broker": "1.2.3.4"},
    "files": {"sub_directory": "./test_subs"},
    "device_info": {},
}


def test_load_config_valid(tmp_path, monkeypatch):
    # Pretend config.py "lives" in tmp_path so load_config() resolves config.json there
    monkeypatch.setattr(config, "__file__", str(tmp_path / "config.py"))

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(MOCK_CONFIG), encoding="utf-8")

    cfg = config.load_config()

    assert cfg["mqtt"]["broker"] == "1.2.3.4"
    # Relative path should be normalized to an absolute path under tmp_path
    assert str(tmp_path) in cfg["files"]["sub_directory"]


def test_load_config_missing_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "__file__", str(tmp_path / "config.py"))

    with pytest.raises(SystemExit) as e:
        config.load_config()
    assert int(e.value.code) == 1

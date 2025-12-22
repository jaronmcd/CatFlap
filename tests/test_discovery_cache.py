import json
from unittest.mock import MagicMock
import discovery


def test_load_cache_invalid_json_returns_empty(tmp_path):
    cache = tmp_path / ".discovery_cache.json"
    cache.write_text("{not json", encoding="utf-8")

    assert discovery.load_cache(str(cache)) == set()


def test_save_cache_logs_on_failure(tmp_path, monkeypatch):
    # Force open() to fail so save_cache hits its exception path
    def bad_open(*_a, **_k):
        raise OSError("boom")

    monkeypatch.setattr(discovery, "open", bad_open, raising=False)

    # Should not raise
    discovery.save_cache(str(tmp_path / ".discovery_cache.json"), {"a", "b"})


def test_run_discovery_directory_missing_returns_empty(tmp_path):
    client = MagicMock()

    cfg = {
        "files": {"sub_directory": str(tmp_path / "nope"), "node_id": "n"},
        "device_info": {"hub_name": "hub", "manufacturer": "m", "model": "x"},
    }

    topic_map = discovery.run_discovery(client, cfg)
    assert topic_map == {}


def test_run_discovery_cleans_stale_topics(tmp_path):
    client = MagicMock()

    tx_dir = tmp_path / "tx_files"
    tx_dir.mkdir()

    # Cache is stored in parent of sub_directory (tmp_path)
    cache = tmp_path / ".discovery_cache.json"
    stale_topic = "homeassistant/button/n_main_old/config"
    cache.write_text(json.dumps([stale_topic]), encoding="utf-8")

    cfg = {
        "files": {"sub_directory": str(tx_dir), "node_id": "n", "discovery_prefix": "homeassistant"},
        "device_info": {"hub_name": "hub", "manufacturer": "m", "model": "x"},
    }

    discovery.run_discovery(client, cfg)

    # Should publish an empty retained payload to the stale topic to delete it
    assert any(
        call.args[0] == stale_topic and call.args[1] == "" and call.kwargs.get("retain") is True
        for call in client.publish.call_args_list
    )


def test_set_offline_publishes_status(tmp_path):
    client = MagicMock()
    cfg = {"files": {"node_id": "n"}}
    discovery.set_offline(client, cfg)
    client.publish.assert_called_with("n/status", "OFF", retain=True)

import builtins
import runpy
from unittest.mock import MagicMock
import pytest


def test_timestamped_print_header_branches():
    import main

    calls = []

    def fake_print(*args, **kwargs):
        calls.append((args, kwargs))

    tp = main._make_timestamped_print(fake_print)

    tp("error happened")
    tp("warning happened")
    tp("tx hello")

    out = " ".join(c[0][0] for c in calls)
    assert "ERROR" in out
    assert "WARN" in out
    assert "TX" in out


def test_on_connect_discovery_exception_path(monkeypatch):
    import main

    state = main.AppState(config={"files": {"node_id": "n"}}, topic_map={}, radio=None)

    def boom(*_a, **_k):
        raise RuntimeError("nope")

    monkeypatch.setattr(main, "run_discovery", boom)

    on_connect = main._on_connect_factory(state)
    on_connect(MagicMock(), None, None, 0)  # rc=0 => enters try/except


def test_on_message_topic_not_mapped_returns():
    import main

    state = main.AppState(config={"files": {"node_id": "n"}}, topic_map={}, radio=MagicMock())
    msg = type("M", (), {"topic": "missing/set", "payload": b"PRESS"})()

    # Should just return (no crash)
    main._on_message_factory(state)(MagicMock(), None, msg)


def test_main_dunder_main_guard_executes_and_exits_cleanly(monkeypatch):
    # Covers: if __name__ == "__main__": run()
    import config

    # Make run() exit fast by forcing missing broker.
    monkeypatch.setattr(config, "load_config", lambda: {"mqtt": {}, "files": {"node_id": "n"}})

    orig_print = builtins.print
    try:
        with pytest.raises(SystemExit):
            runpy.run_module("main", run_name="__main__")
    finally:
        builtins.print = orig_print

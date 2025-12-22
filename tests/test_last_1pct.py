import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_on_connect_success_covers_discovery_assignment(monkeypatch):
    import main

    state = main.AppState(config={"files": {"node_id": "n"}}, topic_map={}, radio=None)
    monkeypatch.setattr(main, "run_discovery", lambda *_a, **_k: {"t/set": "/tmp/a.sub"})

    on_connect = main._on_connect_factory(state)
    on_connect(MagicMock(), None, None, 0)

    assert state.topic_map == {"t/set": "/tmp/a.sub"}


def test_on_message_ignores_non_press_payload(monkeypatch):
    import main

    radio = MagicMock()
    state = main.AppState(
        config={"files": {"node_id": "n"}},
        topic_map={"t/set": "/tmp/a.sub"},
        radio=radio,
    )

    # Should never be called because payload is ignored
    monkeypatch.setattr(main, "get_tx_request", lambda *_a, **_k: {"freq": 1, "payload": b"\x00"})

    msg = SimpleNamespace(topic="t/set", payload=b"NOPE")
    main._on_message_factory(state)(MagicMock(), None, msg)

    assert not radio.transmit.called


def test_run_hits_disconnect_in_finally(monkeypatch):
    import main

    cfg = {"mqtt": {"broker": "127.0.0.1", "port": 1883}, "files": {"node_id": "node"}}
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "install_pretty_print", lambda: None)
    monkeypatch.setattr(main, "set_offline", lambda *_a, **_k: None)
    monkeypatch.setattr(main, "Radio", None)

    client = MagicMock()
    client.loop_forever.side_effect = KeyboardInterrupt()
    monkeypatch.setattr(main, "_make_client", lambda: client)

    main.run()

    assert client.disconnect.called


def test_get_tx_request_unsupported_extension_hits_final_raise(tmp_path):
    import payload

    p = tmp_path / "nope.bin"
    p.write_text("hi", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        payload.get_tx_request(str(p))

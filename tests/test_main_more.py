import builtins
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import main


def test_get_source_color_branches():
    assert main._get_source_color("mqtt") == main.c_magenta
    assert main._get_source_color("rfcat") == main.c_cyan
    assert main._get_source_color("file") == main.c_yellow
    assert main._get_source_color("something else") == main.c_green


def test_timestamped_print_injects_flush_and_parses_source():
    calls = []

    def fake_print(*args, **kwargs):
        calls.append((args, kwargs))

    tp = main._make_timestamped_print(fake_print)
    tp("[MQTT] hello world")  # no flush passed -> injected

    assert calls, "expected fake_print to be called"
    out = calls[-1][0][0]
    kw = calls[-1][1]
    assert kw.get("flush") is True
    assert "MQTT" in out
    assert "hello world" in out


def test_timestamped_print_preserves_flush_kwarg():
    calls = []

    def fake_print(*args, **kwargs):
        calls.append((args, kwargs))

    tp = main._make_timestamped_print(fake_print)
    tp("hi", flush=False)

    assert calls[-1][1]["flush"] is False


def test_install_pretty_print_idempotent(monkeypatch):
    # reset the sentinel for this test
    if hasattr(main.install_pretty_print, "_installed"):
        delattr(main.install_pretty_print, "_installed")

    monkeypatch.setattr(builtins, "print", lambda *a, **k: None)
    main.install_pretty_print()
    p1 = builtins.print

    main.install_pretty_print()
    p2 = builtins.print

    assert p1 is p2


def test_make_client_both_branches(monkeypatch):
    # Branch with CallbackAPIVersion
    fake_client = MagicMock()

    class FakeCB:
        VERSION2 = object()

    fake_mqtt = types.SimpleNamespace(CallbackAPIVersion=FakeCB, Client=fake_client)
    monkeypatch.setattr(main, "mqtt", fake_mqtt)
    main._make_client()
    fake_client.assert_called_with(FakeCB.VERSION2)

    # Branch without CallbackAPIVersion
    fake_client.reset_mock()
    fake_mqtt2 = types.SimpleNamespace(Client=fake_client)
    monkeypatch.setattr(main, "mqtt", fake_mqtt2)
    main._make_client()
    fake_client.assert_called_with()


def test_configure_client_sets_username_and_lwt():
    client = MagicMock()
    cfg = {"mqtt": {"username": "u", "password": "p"}, "files": {"node_id": "node"}}
    main._configure_client(client, cfg)

    client.username_pw_set.assert_called_with("u", "p")
    client.will_set.assert_called_with("node/status", "OFF", retain=True)


def test_on_connect_rc_nonzero_does_not_run_discovery(monkeypatch):
    state = main.AppState(config={"files": {"node_id": "n"}}, topic_map={}, radio=None)
    called = {"d": False}

    def fake_discovery(*_a, **_k):
        called["d"] = True
        return {}

    monkeypatch.setattr(main, "run_discovery", fake_discovery)

    on_connect = main._on_connect_factory(state)
    on_connect(MagicMock(), None, None, 1)

    assert called["d"] is False


def test_on_message_payload_decode_exception_still_triggers(monkeypatch):
    state = main.AppState(config={"files": {"node_id": "n"}}, topic_map={"t/set": "/tmp/a.sub"}, radio=MagicMock())
    monkeypatch.setattr(main, "get_tx_request", lambda _p: {"freq": 1, "payload": b"\x00"})

    class BadPayload:
        pass

    msg = SimpleNamespace(topic="t/set", payload=BadPayload())
    main._on_message_factory(state)(MagicMock(), None, msg)

    state.radio.transmit.assert_called_once()


def test_on_message_get_tx_request_error(monkeypatch):
    state = main.AppState(config={"files": {"node_id": "n"}}, topic_map={"t/set": "/tmp/a.sub"}, radio=MagicMock())

    def boom(_p):
        raise ValueError("bad file")

    monkeypatch.setattr(main, "get_tx_request", boom)

    msg = SimpleNamespace(topic="t/set", payload=b"PRESS")
    main._on_message_factory(state)(MagicMock(), None, msg)

    assert not state.radio.transmit.called


def test_on_message_radio_missing(monkeypatch):
    state = main.AppState(config={"files": {"node_id": "n"}}, topic_map={"t/set": "/tmp/a.sub"}, radio=None)
    monkeypatch.setattr(main, "get_tx_request", lambda _p: {"freq": 1, "payload": b"\x00"})

    msg = SimpleNamespace(topic="t/set", payload=b"PRESS")
    main._on_message_factory(state)(MagicMock(), None, msg)


def test_on_message_transmit_exception_is_caught(monkeypatch):
    radio = MagicMock()
    radio.transmit.side_effect = RuntimeError("tx failed")
    state = main.AppState(config={"files": {"node_id": "n"}}, topic_map={"t/set": "/tmp/a.sub"}, radio=radio)
    monkeypatch.setattr(main, "get_tx_request", lambda _p: {"freq": 1, "payload": b"\x00"})

    msg = SimpleNamespace(topic="t/set", payload=b"PRESS")
    main._on_message_factory(state)(MagicMock(), None, msg)
    assert radio.transmit.called


def test_run_finally_disconnects_even_if_set_offline_raises(monkeypatch):
    cfg = {"mqtt": {"broker": "127.0.0.1", "port": 1883}, "files": {"node_id": "node"}}
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "install_pretty_print", lambda: None)

    client = MagicMock()
    monkeypatch.setattr(main, "_make_client", lambda: client)

    # Force exit via KeyboardInterrupt so we hit finally
    client.loop_forever.side_effect = KeyboardInterrupt()

    # Make set_offline raise to cover exception handling
    monkeypatch.setattr(main, "set_offline", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))

    # Prevent RF init from doing anything
    monkeypatch.setattr(main, "Radio", None)

    main.run()
    assert client.disconnect.called

from unittest.mock import MagicMock
import types


def test_run_exits_when_broker_missing(monkeypatch):
    import main

    # load_config returns missing broker -> SystemExit(1)
    monkeypatch.setattr(main, "load_config", lambda: {"mqtt": {}, "files": {"node_id": "n"}})

    # Avoid actually installing print hook
    monkeypatch.setattr(main, "install_pretty_print", lambda: None)

    # Avoid paho client creation side effects
    monkeypatch.setattr(main, "_make_client", lambda: MagicMock())

    try:
        main.run()
        assert False, "Expected SystemExit"
    except SystemExit as e:
        assert int(e.code) == 1


def test_run_configures_lwt_and_connects_and_finally_disconnects(monkeypatch):
    import main

    cfg = {"mqtt": {"broker": "127.0.0.1", "port": 1883}, "files": {"node_id": "node"}}
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "install_pretty_print", lambda: None)

    client = MagicMock()
    monkeypatch.setattr(main, "_make_client", lambda: client)

    # Simulate loop_forever raising KeyboardInterrupt so we hit finally
    def _raise():
        raise KeyboardInterrupt()

    client.loop_forever.side_effect = _raise

    # Prevent set_offline from erroring (and verify it's called)
    offline = MagicMock()
    monkeypatch.setattr(main, "set_offline", offline)

    # Force Radio init path to succeed without touching rflib
    class FakeRadio:
        def __init__(self):
            pass

    monkeypatch.setattr(main, "Radio", FakeRadio)

    main.run()

    # LWT configured
    client.will_set.assert_called_once_with("node/status", "OFF", retain=True)

    # Connected to broker/port
    client.connect.assert_called_once_with("127.0.0.1", 1883, 60)

    # Finally: set_offline + disconnect attempted
    assert offline.called
    assert client.disconnect.called


def test_run_radio_init_failure_is_nonfatal(monkeypatch):
    import main

    cfg = {"mqtt": {"broker": "127.0.0.1", "port": 1883}, "files": {"node_id": "node"}}
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "install_pretty_print", lambda: None)

    client = MagicMock()
    monkeypatch.setattr(main, "_make_client", lambda: client)

    # Short-circuit loop immediately
    client.loop_forever.side_effect = KeyboardInterrupt()

    # Radio raises on init -> should still proceed to connect
    class BadRadio:
        def __init__(self):
            raise RuntimeError("no dongle")

    monkeypatch.setattr(main, "Radio", BadRadio)

    # Keep set_offline harmless
    monkeypatch.setattr(main, "set_offline", lambda *_a, **_k: None)

    main.run()
    client.connect.assert_called_once()

from unittest.mock import MagicMock


def test_run_disconnect_exception_is_swallowed(monkeypatch):
    import main

    cfg = {"mqtt": {"broker": "127.0.0.1", "port": 1883}, "files": {"node_id": "node"}}
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "install_pretty_print", lambda: None)
    monkeypatch.setattr(main, "set_offline", lambda *_a, **_k: None)
    monkeypatch.setattr(main, "Radio", None)

    client = MagicMock()
    client.loop_forever.side_effect = KeyboardInterrupt()
    client.disconnect.side_effect = RuntimeError("disconnect failed")
    monkeypatch.setattr(main, "_make_client", lambda: client)

    # Should not raise (disconnect exception is swallowed)
    main.run()

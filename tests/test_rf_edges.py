import pytest


def test_radio_init_importerror_when_rflib_none(monkeypatch):
    import rf
    monkeypatch.setattr(rf, "rflib", None)
    with pytest.raises(ImportError):
        rf.Radio()


def test_radio_init_logs_and_raises_when_rflib_rfcat_fails(monkeypatch):
    import rf
    import rflib  # mocked in conftest

    rflib.RfCat.side_effect = RuntimeError("boom")
    try:
        with pytest.raises(RuntimeError):
            rf.Radio()
    finally:
        rflib.RfCat.side_effect = None


def test_transmit_importerror_when_rflib_none(monkeypatch):
    import rf
    radio = rf.Radio()

    monkeypatch.setattr(rf, "rflib", None)
    with pytest.raises(ImportError):
        radio.transmit(freq=433920000, payload=b"\x00")


def test_transmit_rejects_payload_types():
    import rf
    radio = rf.Radio()

    with pytest.raises(TypeError):
        radio.transmit(freq=433920000, payload="not-bytes")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        radio.transmit(freq=433920000, payload=1234)  # type: ignore[arg-type]


def test_transmit_finally_swallows_setmodeidle_error(monkeypatch):
    import rf
    import rflib

    radio = rf.Radio()
    d = rflib.RfCat.return_value

    # Make the finally block's setModeIDLE throw.
    d.setModeIDLE.side_effect = RuntimeError("idle fail")

    # Should not raise due to the finally/except
    radio.transmit(freq=433920000, payload=b"\x01", modulation="ASK_OOK")

    # Reset for other tests
    d.setModeIDLE.side_effect = None

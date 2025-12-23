import types


def test_radio_transmit_calls_rflib(monkeypatch):
    # rflib is mocked globally in conftest.py
    import rflib
    from rf import Radio

    # Make sure the mock has the methods we expect on the RfCat instance.
    d = rflib.RfCat.return_value
    for name in (
        "setModeIDLE",
        "setFreq",
        "setMdmModulation",
        "setMdmDRate",
        "setMdmSyncMode",
        "setMdmNumPreamble",
        "setMaxPower",
        "makePktFLEN",
        "RFxmit",
    ):
        if not hasattr(d, name):
            setattr(d, name, types.MethodType(lambda *_a, **_k: None, d))

    radio = Radio()
    assert rflib.RfCat.called
    assert d.setModeIDLE.called

    payload = b"\x01\x02\x03"
    radio.transmit(
        freq=433_920_000,
        payload=payload,
        repeat=3,
        drate=1000,
        modulation="ASK_OOK",
        manchester=True,
        deviation=None,
        syncmode=1,
        preamble=2,
    )

    d.setFreq.assert_called_with(433_920_000)
    # Manchester bit should be OR'ed in.
    d.setMdmModulation.assert_called_with(rflib.MOD_ASK_OOK | rflib.MANCHESTER)
    d.setMdmDRate.assert_called_with(1000)
    d.setMdmSyncMode.assert_called_with(1)
    d.setMdmNumPreamble.assert_called_with(2)
    assert d.setMaxPower.called
    d.makePktFLEN.assert_called_with(len(payload))
    d.RFxmit.assert_called_with(payload, repeat=3)


def test_radio_transmit_deviation_only_for_fsk():
    import rflib
    from rf import Radio

    d = rflib.RfCat.return_value
    radio = Radio()
    d.reset_mock()

    radio.transmit(
        freq=315_000_000,
        payload=b"\x00",
        modulation="ASK_OOK",
        deviation=10_000,
    )
    # Deviation should NOT be called for ASK/OOK.
    assert not d.setMdmDeviatn.called

    d.reset_mock()
    radio.transmit(
        freq=315_000_000,
        payload=b"\x00",
        modulation="2FSK",
        deviation=10_000,
    )
    assert d.setMdmDeviatn.called


def test_radio_transmit_rejects_unknown_modulation():
    from rf import Radio
    import pytest

    radio = Radio()
    with pytest.raises(ValueError):
        radio.transmit(freq=433_920_000, payload=b"\x00", modulation="NOPE")

import pytest

# Expected TI-style mapping (target dBm -> PATABLE code) by band bucket.
EXPECTED_POWER_TABLE = {
    315: {-30: 0x12, -20: 0x0D, -15: 0x1C, -10: 0x34, -5: 0x2B, 0: 0x51, 5: 0x85, 7: 0xCB, 10: 0xC2},
    433: {-30: 0x12, -20: 0x0E, -15: 0x1D, -10: 0x34, -5: 0x2C, 0: 0x60, 5: 0x84, 7: 0xC8, 10: 0xC0},
    868: {-30: 0x03, -20: 0x0E, -15: 0x1E, -10: 0x27, -5: 0x8F, 0: 0x50, 5: 0x84, 7: 0xCB, 10: 0xC2},
    915: {-30: 0x03, -20: 0x0D, -15: 0x1D, -10: 0x26, -5: 0x57, 0: 0x8E, 5: 0x83, 7: 0xC7, 10: 0xC0},
}


def _assert_poke_called(d, addr: int, byte_value: int) -> None:
    """Accept either bytes([v]) or [v] depending on poke() implementation."""
    for call in d.poke.call_args_list:
        args = call.args
        if len(args) < 2:
            continue
        if args[0] != addr:
            continue
        data = args[1]
        if data == bytes([byte_value & 0xFF]):
            return
        if data == [byte_value & 0xFF]:
            return
        if isinstance(data, (bytearray, bytes)) and bytes(data) == bytes([byte_value & 0xFF]):
            return
    raise AssertionError(
        f"poke() never called with addr=0x{addr:04X} value=0x{byte_value:02X}. "
        f"Calls: {d.poke.call_args_list}"
    )


def test_register_addresses_match_spec():
    import rf

    # SWRS033H: 0xDF1B FREND0, 0xDF2E..0xDF27 PA_TABLE0..7
    assert rf.FREND0_ADDR == 0xDF1B
    assert rf.PA_TABLE0_ADDR == 0xDF2E


def test_apply_power_settings_updates_frend0_bitfields_only():
    """
    Spec (SWRS033H, FREND0):
      - PA_POWER is bits [2:0]
      - LODIV_BUF_CURRENT_TX is bits [5:4]
    We should update only those fields and preserve other bits.
    """
    import rflib
    import rf

    d = rflib.RfCat.return_value
    d.reset_mock()

    initial_frend0 = 0b1100_1000  # random upper bits set (7..6 and bit 3 set)
    pa_power = 5                  # 0b101
    lodiv = 3                     # 0b11 -> bits 5..4

    def peek_side_effect(addr, size=1):
        if addr == rf.FREND0_ADDR:
            return [initial_frend0]
        return [0x00] * size

    d.peek.side_effect = peek_side_effect

    radio = rf.Radio()
    radio._apply_power_settings(
        freq_hz=433_920_000,
        modulation="2FSK",
        tx_power_mode="manual",
        tx_power_target_dbm=0,
        tx_power_band="auto",
        frend0_pa_power=pa_power,
        frend0_lodiv_buf_current_tx=lodiv,
        patable="0xC0",
    )

    # Clear bits [2:0] and [5:4], then OR in new values.
    cleared = initial_frend0 & ~0b0000_0111
    cleared &= ~(0b11 << 4)
    expected = cleared | (pa_power & 0b111) | ((lodiv & 0b11) << 4)

    _assert_poke_called(d, rf.FREND0_ADDR, expected)


def test_apply_power_settings_ask_single_value_sets_index0_off_and_fills_up_to_pa_power():
    """
    For ASK/OOK with single PATABLE value:
      - Force PA_TABLE0 = 0x00 (off / '0' level)
      - Fill indices 1..PA_POWER with ON value
    """
    import rflib
    import rf

    d = rflib.RfCat.return_value
    d.reset_mock()

    # Make FREND0 read 0 so the code will write the requested PA_POWER.
    d.peek.side_effect = lambda addr, size=1: [0x00] if addr == rf.FREND0_ADDR else [0x00] * size

    radio = rf.Radio()
    radio._apply_power_settings(
        freq_hz=433_920_000,
        modulation="ASK_OOK",
        tx_power_mode="manual",
        tx_power_target_dbm=0,
        tx_power_band="auto",
        frend0_pa_power=3,
        frend0_lodiv_buf_current_tx=None,
        patable="0x60",
    )

    # PA_POWER=3 -> expect PA_TABLE0 forced to 0, and PA_TABLE1..PA_TABLE3 = 0x60
    _assert_poke_called(d, rf.PA_TABLE0_ADDR, 0x00)         # index 0
    _assert_poke_called(d, rf.PA_TABLE0_ADDR - 1, 0x60)     # index 1
    _assert_poke_called(d, rf.PA_TABLE0_ADDR - 2, 0x60)     # index 2
    _assert_poke_called(d, rf.PA_TABLE0_ADDR - 3, 0x60)     # index 3


def test_apply_power_settings_fsk_single_value_fills_from_index0_to_pa_power():
    """
    For non-ASK modulation with single PATABLE value:
      - Fill indices 0..PA_POWER with ON value
    """
    import rflib
    import rf

    d = rflib.RfCat.return_value
    d.reset_mock()

    # Force FREND0 non-zero so we can also observe the write.
    d.peek.side_effect = lambda addr, size=1: [0x07] if addr == rf.FREND0_ADDR else [0x00] * size

    radio = rf.Radio()
    radio._apply_power_settings(
        freq_hz=433_920_000,
        modulation="2FSK",
        tx_power_mode="manual",
        tx_power_target_dbm=0,
        tx_power_band="auto",
        frend0_pa_power=2,
        frend0_lodiv_buf_current_tx=None,
        patable="0xC0",
    )

    _assert_poke_called(d, rf.PA_TABLE0_ADDR, 0xC0)         # index 0
    _assert_poke_called(d, rf.PA_TABLE0_ADDR - 1, 0xC0)     # index 1
    _assert_poke_called(d, rf.PA_TABLE0_ADDR - 2, 0xC0)     # index 2


def test_apply_power_settings_rejects_out_of_range_values():
    import rf

    radio = rf.Radio()

    with pytest.raises(ValueError):
        radio._apply_power_settings(
            freq_hz=433_920_000,
            modulation="ASK_OOK",
            tx_power_mode="manual",
            tx_power_target_dbm=0,
            tx_power_band="auto",
            frend0_pa_power=8,
            frend0_lodiv_buf_current_tx=None,
            patable="0x60",
        )

    with pytest.raises(ValueError):
        radio._apply_power_settings(
            freq_hz=433_920_000,
            modulation="ASK_OOK",
            tx_power_mode="manual",
            tx_power_target_dbm=0,
            tx_power_band="auto",
            frend0_pa_power=1,
            frend0_lodiv_buf_current_tx=4,
            patable="0x60",
        )


def test_smart_power_table_matches_spec_if_present():
    """
    Optional: once you implement "smart" mode via rf.POWER_TABLE,
    this locks the mapping to the TI table so it can’t drift.
    """
    import rf

    if not hasattr(rf, "POWER_TABLE"):
        pytest.skip("rf.POWER_TABLE not implemented (smart mode not enabled yet)")

    assert rf.POWER_TABLE == EXPECTED_POWER_TABLE

import base64
import json
import pytest

import payload


# A simple RAW signal that becomes deterministic at drate=1000:
#  +1000us => 1 chip of '1'
#  -1000us => 1 chip of '0'
# Repeating gives 0b10101010 = 0xAA
FLIPPER_RAW_AA = """Filetype: Flipper SubGhz Key File
Version: 1
Frequency: 433920000
Preset: FuriHalSubGhzPresetOok650Async
Protocol: RAW
RAW_Data: 1000 -1000 1000 -1000 1000 -1000 1000 -1000
"""


def test_strip_known_suffix():
    assert payload._strip_known_suffix("Door_Bell.rfcat.json") == "Door_Bell"
    assert payload._strip_known_suffix("Fan_Power.sub") == "Fan_Power"


def test_pack_bits_lsb_first_reverses_per_byte():
    # Bits 0..7 = 10000000 -> if msb_first=False it reverses to 00000001
    assert payload._pack_bits([1, 0, 0, 0, 0, 0, 0, 0], msb_first=False) == b"\x01"


def test_parse_flipper_sub_basic(tmp_path):
    f = tmp_path / "test.sub"
    f.write_text(FLIPPER_RAW_AA, encoding="utf-8")

    freq, data, opts = payload.parse_flipper_sub(str(f), drate=1000)

    assert freq == 433920000
    assert data == b"\xAA"
    assert opts["modulation"] == "ASK_OOK"
    assert opts["drate"] == 1000


def test_parse_flipper_sub_missing_frequency_raises(tmp_path):
    f = tmp_path / "bad.sub"
    f.write_text("RAW_Data: 1000 -1000\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No Frequency"):
        payload.parse_flipper_sub(str(f), drate=1000)


def test_parse_flipper_sub_missing_raw_data_raises(tmp_path):
    f = tmp_path / "bad.sub"
    f.write_text("Frequency: 433920000\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No RAW_Data"):
        payload.parse_flipper_sub(str(f), drate=1000)


def test_parse_rfcat_json_payload_list(tmp_path):
    p = tmp_path / "a.rfcat.json"
    p.write_text(
        json.dumps(
            {
                "frequency": 433920000,
                "payload": [1, 2, 255],
                "repeat": 3,
                "drate": 1234,
                "modulation": "ASK_OOK",
                "manchester": True,
            }
        ),
        encoding="utf-8",
    )

    tx = payload.parse_rfcat_json(str(p))
    assert tx["freq"] == 433920000
    assert tx["payload"] == b"\x01\x02\xFF"
    assert tx["repeat"] == 3
    assert tx["drate"] == 1234
    assert tx["manchester"] is True


def test_parse_rfcat_json_payload_hex(tmp_path):
    p = tmp_path / "b.rfcat.json"
    p.write_text(json.dumps({"freq_hz": 315000000, "payload_hex": "0x0a ff"}), encoding="utf-8")

    tx = payload.parse_rfcat_json(str(p))
    assert tx["freq"] == 315000000
    assert tx["payload"] == b"\x0a\xff"


def test_parse_rfcat_json_payload_b64(tmp_path):
    raw = b"\x10\x20\x30"
    p = tmp_path / "c.rfcat.json"
    p.write_text(
        json.dumps({"freq": 390000000, "payload_b64": base64.b64encode(raw).decode("ascii")}),
        encoding="utf-8",
    )

    tx = payload.parse_rfcat_json(str(p))
    assert tx["freq"] == 390000000
    assert tx["payload"] == raw


def test_parse_rfcat_json_raw_durations_fallback(tmp_path):
    # Exercises:
    # - raw_durations_us fallback path
    # - invert_level True branch
    # - max_gap_us cap branch
    # - msb_first False branch
    #
    # With drate=1000 and max_gap_us=1000, all huge durations get capped to 1000us,
    # so each duration becomes 1 chip. Durations: +huge, -huge, +1000, -1000
    # levels: 1,0,1,0 then invert -> 0,1,0,1 then pad to 8:
    # [0,1,0,1,0,0,0,0] and msb_first=False reverses to [0,0,0,0,1,0,1,0] = 0x0A.
    p = tmp_path / "d.rfcat.json"
    p.write_text(
        json.dumps(
            {
                "frequency": 433920000,
                "drate": 1000,
                "raw_durations_us": [100000, -100000, 1000, -1000],
                "invert_level": True,
                "msb_first": False,
                "max_gap_us": 1000,
            }
        ),
        encoding="utf-8",
    )

    tx = payload.parse_rfcat_json(str(p))
    assert tx["modulation"] == "ASK_OOK"
    assert tx["payload"] == b"\x0a"


def test_parse_rfcat_json_missing_frequency_raises(tmp_path):
    p = tmp_path / "e.rfcat.json"
    p.write_text(json.dumps({"payload_hex": "aa"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing frequency"):
        payload.parse_rfcat_json(str(p))


def test_parse_rfcat_json_missing_payload_raises(tmp_path):
    p = tmp_path / "f.rfcat.json"
    p.write_text(json.dumps({"frequency": 433920000}), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing payload"):
        payload.parse_rfcat_json(str(p))


def test_get_tx_request_sub_and_unsupported(tmp_path):
    # .sub path
    f = tmp_path / "x.sub"
    f.write_text(FLIPPER_RAW_AA, encoding="utf-8")

    tx = payload.get_tx_request(str(f), default_repeat=9, default_drate=1000)
    assert tx["freq"] == 433920000
    assert tx["repeat"] == 9
    assert tx["drate"] == 1000

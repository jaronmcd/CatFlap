import json
import pytest
import payload


def test_is_supported_path():
    assert payload.is_supported_path("x.sub") is True
    assert payload.is_supported_path("x.rfcat.json") is True
    assert payload.is_supported_path("x.SUB") is True
    assert payload.is_supported_path("x.txt") is False


def test_durations_to_bits_min_chip_of_1():
    # chips = round(dur_us * drate / 1e6)
    # Choose values that round to 0 so it hits: if chips < 1: chips = 1
    bits = payload._durations_to_bits([1], drate=10, invert_level=False, max_gap_us=30000)
    assert bits == [1]


def test_parse_flipper_sub_raw_index_out_of_range_resets_to_zero(tmp_path):
    f = tmp_path / "a.sub"
    f.write_text(
        "Filetype: Flipper SubGhz Key File\n"
        "Version: 1\n"
        "Frequency: 433920000\n"
        "Protocol: RAW\n"
        "RAW_Data: 1000 -1000\n",
        encoding="utf-8",
    )

    # raw_index is too large => should reset to 0 and still work
    freq, data, opts = payload.parse_flipper_sub(str(f), raw_index=999, drate=1000)
    assert freq == 433920000
    assert isinstance(data, (bytes, bytearray))
    assert opts["drate"] == 1000


def test_hex_to_bytes_pads_odd_length():
    # "a" -> "0a"
    assert payload._hex_to_bytes("a") == b"\x0a"
    assert payload._hex_to_bytes("0xa") == b"\x0a"


def test_load_rfcat_json_rejects_non_object(tmp_path):
    p = tmp_path / "bad.rfcat.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a JSON object"):
        payload.parse_rfcat_json(str(p))


def test_get_tx_request_rfcat_json_branch(tmp_path):
    p = tmp_path / "ok.rfcat.json"
    p.write_text(json.dumps({"frequency": 433920000, "payload_hex": "aa"}), encoding="utf-8")

    tx = payload.get_tx_request(str(p))
    assert tx["freq"] == 433920000
    assert tx["payload"] == b"\xaa"

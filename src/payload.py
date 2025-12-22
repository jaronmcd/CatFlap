import base64
import json
import os
import re

#
# Parsers for supported TX file formats.
#
# 1) Flipper Zero .sub (RAW_Data) — we approximate the waveform by sampling
#    pulse durations into 0/1 "chips" at a chosen data rate.
#
# 2) .rfcat.json — a simple, explicit "TX descriptor" format (freq + modem
#    settings + payload). This is the most reliable way to replay things that
#    aren't Flipper captures.
#


SUPPORTED_EXTENSIONS = (
    ".sub",
    ".rfcat.json",
)


def _strip_known_suffix(filename: str) -> str:
    """Return a stable stem for entity IDs (handles double extensions)."""
    fn = filename
    for suf in (".rfcat.json",):
        if fn.lower().endswith(suf):
            return fn[: -len(suf)]
    return os.path.splitext(fn)[0]


def is_supported_path(path: str) -> bool:
    p = path.lower()
    return p.endswith(SUPPORTED_EXTENSIONS)


# -----------------------------
# Flipper .sub (RAW_Data)
# -----------------------------

def _read_flipper_sub(path: str):
    freq = None
    raw_lines = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("Frequency:"):
                freq = int(line.split(":", 1)[1].strip())
            elif line.startswith("RAW_Data:"):
                nums = [int(x) for x in re.findall(r"-?\d+", line[len("RAW_Data:"):])]
                if nums:
                    raw_lines.append(nums)

    if freq is None:
        raise ValueError("No Frequency found")
    if not raw_lines:
        raise ValueError("No RAW_Data found")
    return freq, raw_lines


def _durations_to_bits(durs, drate, invert_level=False, max_gap_us=30000):
    """Convert +/- duration microseconds into a chip-level 0/1 stream."""
    bits = []
    for v in durs:
        level = 1 if v > 0 else 0
        if invert_level:
            level ^= 1

        dur_us = abs(v)
        if dur_us > max_gap_us:
            dur_us = max_gap_us

        chips = int(round(dur_us * drate / 1_000_000.0))
        if chips < 1:
            chips = 1
        bits.extend([level] * chips)
    return bits


def _pack_bits(bits, msb_first=True) -> bytes:
    rem = len(bits) % 8
    if rem:
        bits = bits + [0] * (8 - rem)

    out = bytearray()
    for i in range(0, len(bits), 8):
        b = bits[i:i + 8]
        if not msb_first:
            b = list(reversed(b))
        val = 0
        for bit in b:
            val = (val << 1) | bit
        out.append(val)
    return bytes(out)


def parse_flipper_sub(
    path: str,
    raw_index: int = 0,
    drate: int = 3333,
    invert_level: bool = False,
    msb_first: bool = True,
    max_gap_us: int = 30000,
):
    """Return (freq_hz, payload_bytes, inferred_opts)."""
    freq, raw_lines = _read_flipper_sub(path)
    if raw_index >= len(raw_lines):
        raw_index = 0

    bits = _durations_to_bits(raw_lines[raw_index], drate, invert_level=invert_level, max_gap_us=max_gap_us)
    payload = _pack_bits(bits, msb_first=msb_first)
    opts = {
        "modulation": "ASK_OOK",
        "drate": int(drate),
    }
    return freq, payload, opts


# -----------------------------
# .rfcat.json (TX descriptor)
# -----------------------------

def _hex_to_bytes(s: str) -> bytes:
    s = s.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    s = re.sub(r"[^0-9a-f]", "", s)
    if len(s) % 2:
        s = "0" + s
    return bytes.fromhex(s)


def _load_rfcat_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(".rfcat.json must contain a JSON object")
    return data


def parse_rfcat_json(path: str):
    """Return a tx_request dict compatible with rf.Radio.transmit()."""
    data = _load_rfcat_json(path)

    # Frequency
    freq = data.get("frequency")
    if freq is None:
        freq = data.get("freq")
    if freq is None:
        freq = data.get("freq_hz")
    if freq is None:
        raise ValueError("Missing frequency (expected frequency/freq/freq_hz)")
    freq = int(freq)

    # Modem settings
    modulation = str(data.get("modulation", "ASK_OOK")).upper()
    manchester = bool(data.get("manchester", False))
    drate = int(data.get("drate", 3333))
    deviation = data.get("deviation")
    deviation = int(deviation) if deviation is not None else None

    syncmode = int(data.get("syncmode", 0))
    preamble = int(data.get("preamble", 0))
    repeat = int(data.get("repeat", 20))
    max_power = bool(data.get("max_power", True))

    # Payload: prefer explicit bytes; fall back to raw durations for OOK.
    payload = None
    if isinstance(data.get("payload"), list):
        payload = bytes(int(x) & 0xFF for x in data["payload"])
    elif isinstance(data.get("payload_hex"), str):
        payload = _hex_to_bytes(data["payload_hex"])
    elif isinstance(data.get("payload_b64"), str):
        payload = base64.b64decode(data["payload_b64"].encode("ascii"))

    if payload is None:
        # Optional: OOK pulse durations (same convention as Flipper RAW_Data)
        raw = data.get("raw_durations")
        if raw is None:
            raw = data.get("raw_durations_us")
        if isinstance(raw, list) and raw:
            invert_level = bool(data.get("invert_level", False))
            msb_first = bool(data.get("msb_first", True))
            max_gap_us = int(data.get("max_gap_us", 30000))
            bits = _durations_to_bits(raw, drate, invert_level=invert_level, max_gap_us=max_gap_us)
            payload = _pack_bits(bits, msb_first=msb_first)
            # Force OOK for this path.
            modulation = "ASK_OOK"

    if payload is None:
        raise ValueError(
            "Missing payload. Provide one of: payload (byte list), payload_hex, payload_b64, or raw_durations_us."
        )

    return {
        "freq": freq,
        "payload": payload,
        "repeat": repeat,
        "drate": drate,
        "modulation": modulation,
        "manchester": manchester,
        "deviation": deviation,
        "syncmode": syncmode,
        "preamble": preamble,
        "max_power": max_power,
    }


# -----------------------------
# Public API used by main.py
# -----------------------------

def get_tx_request(path: str, default_repeat: int = 20, default_drate: int = 3333) -> dict:
    """Auto-detect format and return a dict for rf.Radio.transmit()."""
    p = path.lower()
    if p.endswith(".sub"):
        freq, payload, opts = parse_flipper_sub(path, drate=default_drate)
        return {
            "freq": freq,
            "payload": payload,
            "repeat": default_repeat,
            "drate": int(opts.get("drate", default_drate)),
            "modulation": opts.get("modulation", "ASK_OOK"),
            "manchester": False,
            "deviation": None,
            "syncmode": 0,
            "preamble": 0,
            "max_power": True,
        }
    if p.endswith(".rfcat.json"):
        return parse_rfcat_json(path)

    raise ValueError(f"Unsupported file type for replay: {os.path.basename(path)}")

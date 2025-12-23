#!/usr/bin/env python3
"""CatFlap - RfCat MQTT Bridge for Home Assistant.

Key design goals for this file:
 - No side-effects on import (so pytest can import it)
 - Configuration is loaded relative to this repo/add-on (/app/src/config.json)
 - MQTT discovery publishes HA "button" entities that trigger TX replay
 - TX payload parsing is delegated to payload.py
 - RF transmit is delegated to rf.py
"""

from __future__ import annotations

import builtins
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

from config import load_config
from discovery import run_discovery, set_offline
from payload import get_tx_request

try:
    from rf import Radio
except Exception:  # pragma: no cover (unit tests may not need RF)
    Radio = None  # type: ignore


# ---------------------------------------------------------------------------
# Pretty logging (optional)
# ---------------------------------------------------------------------------

c_cyan = "\033[1;36m"
c_magenta = "\033[1;35m"
c_blue = "\033[1;34m"
c_green = "\033[1;32m"
c_yellow = "\033[1;33m"
c_red = "\033[1;31m"
c_white = "\033[1;37m"
c_dim = "\033[37m"
c_reset = "\033[0m"


def _get_source_color(clean_text: str) -> str:
    clean = clean_text.lower()
    if "mqtt" in clean:
        return c_magenta
    if "rf" in clean:
        return c_cyan
    if "file" in clean:
        return c_yellow
    return c_green


def _make_timestamped_print(original_print):
    def timestamped_print(*args, **kwargs):
        now = datetime.now().strftime("%H:%M:%S")
        time_prefix = f"{c_dim}[{now}]{c_reset}"
        msg = " ".join(map(str, args))
        lower_msg = msg.lower()

        header = f"{c_green}INFO{c_reset}{c_white}:{c_reset}"
        if any(x in lower_msg for x in ["error", "critical", "failed", "crashed", "exception"]):
            header = f"{c_red}ERROR{c_reset}{c_white}:{c_reset}"
        elif "warning" in lower_msg or "warn" in lower_msg:
            header = f"{c_yellow}WARN{c_reset}{c_white}:{c_reset}"
        elif "transmitting" in lower_msg or "replay" in lower_msg or lower_msg.startswith("tx"):
            header = f"{c_cyan}TX{c_reset}{c_white}  :{c_reset}"
        elif "mqtt" in lower_msg:
            header = f"{c_magenta}MQTT{c_reset}{c_white}:{c_reset}"

        match = re.match(r"^\[(.*?)\]\s*(.*)", msg)
        if match:
            src_text = match.group(1)
            rest_of_msg = match.group(2)
            s_color = _get_source_color(src_text)
            msg = f"{c_white}[{c_reset}{s_color}{src_text}{c_reset}{c_white}]:{c_reset} {rest_of_msg}"

        # Avoid double-flush kwarg collisions.
        if "flush" not in kwargs:
            kwargs["flush"] = True
        original_print(f"{time_prefix} {header} {msg}", **kwargs)

    return timestamped_print


def install_pretty_print() -> None:
    """Install timestamped, colored print. Safe to call multiple times."""
    if getattr(install_pretty_print, "_installed", False):
        return
    original_print = builtins.print
    builtins.print = _make_timestamped_print(original_print)
    install_pretty_print._installed = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Version (read from config.yaml like rtl-haos)
# ---------------------------------------------------------------------------

def get_version() -> str:
    """Return a display version like 'v0.5.1' (or 'Unknown')."""
    env_ver = (os.getenv("CATFLAP_VERSION") or os.getenv("BUILD_VERSION") or "").strip()
    if env_ver:
        return env_ver if env_ver.lower().startswith("v") else f"v{env_ver}"

    candidates = [
        "/app/config.yaml",  # if Dockerfile copies config.yaml here
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.yaml"),  # src/config.yaml
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "config.yaml"),  # repo root
        "config.yaml",
    ]

    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if s.startswith("version:"):
                            v = s.split(":", 1)[1].strip().strip('"').strip("'")
                            if not v:
                                break
                            return v if v.lower().startswith("v") else f"v{v}"
        except Exception:
            pass

    return "Unknown"


# ---------------------------------------------------------------------------
# ASCII logo (shown on direct execution only)
# ---------------------------------------------------------------------------
def _colorize_border(line: str) -> str:
    """Color border characters blue, everything else white."""
    border_chars = set("+-|-")  # includes '-'
    out = []
    for ch in line:
        if ch in border_chars:
            out.append(f"{c_blue}{ch}{c_reset}")
        else:
            out.append(f"{c_white}{ch}{c_reset}")
    return "".join(out)


def show_logo(version: str) -> None:
    """Blue border, white cat+text, version centered in bottom border."""
    catface = "( o.o )"
    ears = "/\\_/\\"
    text_lines = ["CATFLAP", "RF REPLAY BRIDGE"]
    ver_token = f"[{version}]"

    # Box sizing
    inner_width = max(max(len(s) for s in text_lines), len(ver_token)) + 6
    inside_len = inner_width + 2  # accounts for the spaces inside "| ... |"

    # Top border with embedded catface
    left_dashes = 2
    min_len = left_dashes + len(catface) + 2
    if inside_len < min_len:
        inside_len = min_len
        inner_width = inside_len - 2

    top_inside = ("-" * left_dashes) + catface + ("-" * (inside_len - left_dashes - len(catface)))
    top = "+" + top_inside + "+"

    def boxed(content: str) -> str:
        return "| " + content.center(inner_width) + " |"

    # Bottom border with centered version token: ----[vX]----
    pad_total = inside_len - len(ver_token)
    left = pad_total // 2
    right = pad_total - left
    bottom_inside = ("-" * left) + ver_token + ("-" * right)
    bottom = "+" + bottom_inside + "+"

    # Ears aligned over the catface (catface is inside the top border after '+' + dashes)
    ears_indent = 1 + left_dashes + (len(catface) - len(ears)) // 2
    print(" " * ears_indent + f"{c_white}{ears}{c_reset}")

    # Print box
    print(_colorize_border(top))
    for s in text_lines:
        print(_colorize_border(boxed(s)))
    print(_colorize_border(bottom))
    print()


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------


@dataclass
class AppState:
    config: Dict[str, Any]
    topic_map: Dict[str, str]
    radio: Optional[Any]


def _make_client() -> mqtt.Client:
    # Support both paho-mqtt v1 and v2 callback API.
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    return mqtt.Client()


def _configure_client(client: mqtt.Client, cfg: Dict[str, Any]) -> None:
    mqtt_cfg = cfg.get("mqtt", {})
    if mqtt_cfg.get("username"):
        client.username_pw_set(mqtt_cfg.get("username"), mqtt_cfg.get("password"))

    # LWT: mark the bridge offline if we die.
    node_id = cfg.get("files", {}).get("node_id", "rfcat_replay")
    client.will_set(f"{node_id}/status", "OFF", retain=True)


def _on_connect_factory(state: AppState):
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"[MQTT] Connection failed with code {rc}")
            return

        print("[MQTT] Connected")

        # Publish HA discovery + build topic->file map.
        try:
            state.topic_map = run_discovery(client, state.config)
            print(f"[Files] Mapped {len(state.topic_map)} replay topics")
        except Exception as e:
            print(f"[Discovery] ERROR: {e}")

    return on_connect


def _on_message_factory(state: AppState):
    def on_message(client, userdata, msg):
        topic = msg.topic
        file_path = state.topic_map.get(topic)
        if not file_path:
            return

        payload_text = None
        try:
            payload_text = msg.payload.decode("utf-8", errors="ignore").strip()
        except Exception:
            payload_text = None

        # HA "button" uses payload_press=PRESS by convention.
        if payload_text and payload_text.upper() not in ("PRESS", "1", "ON", "TRUE"):
            print(f"[MQTT] Ignoring payload '{payload_text}' for {topic}")
            return

        print(f"[MQTT] Trigger: {topic}")
        try:
            tx = get_tx_request(file_path)
        except Exception as e:
            print(f"[Payload] ERROR parsing {file_path}: {e}")
            return

        if not state.radio:
            print("[RfCat] ERROR: RF device not initialized")
            return

        try:
            print(f"[RfCat] Replaying {os.path.basename(file_path)}")
            rf_cfg = state.config.get("rf", {})

            # New CC1110/CC1111 power configuration (no backwards compatibility)
            tx["tx_power_mode"] = rf_cfg.get("tx_power_mode", "max")
            tx["frend0_pa_power"] = rf_cfg.get("frend0_pa_power")
            tx["frend0_lodiv_buf_current_tx"] = rf_cfg.get("frend0_lodiv_buf_current_tx")
            tx["patable"] = rf_cfg.get("patable")

            state.radio.transmit(**tx)
            print("[RfCat] Transmission complete")
        except Exception as e:
            print(f"[RfCat] ERROR during transmission: {e}")

    return on_message


def run() -> None:
    # Force basic color support in typical docker/HA logs.
    os.environ.setdefault("TERM", "xterm-256color")
    os.environ.setdefault("CLICOLOR_FORCE", "1")
    install_pretty_print()

    cfg = load_config()
    state = AppState(config=cfg, topic_map={}, radio=None)

    # Init RF (optional; the add-on should still start and expose buttons)
    if Radio is not None:
        try:
            state.radio = Radio()
        except Exception as e:
            state.radio = None
            print(f"[RfCat] WARNING: RF init failed: {e}")

    client = _make_client()
    _configure_client(client, cfg)
    client.on_connect = _on_connect_factory(state)
    client.on_message = _on_message_factory(state)

    mqtt_cfg = cfg.get("mqtt", {})
    broker = mqtt_cfg.get("broker")
    port = int(mqtt_cfg.get("port", 1883))
    if not broker:
        print("[Config] CRITICAL: mqtt.broker is missing")
        raise SystemExit(1)

    try:
        print(f"[MQTT] Connecting to {broker}:{port} ...")
        client.connect(broker, port, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("[System] Shutdown requested")
    finally:
        try:
            set_offline(client, cfg)
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    show_logo(get_version())
    install_pretty_print()
    run()

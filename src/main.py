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
import runpy
import signal
import traceback
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


def _apply_rf_defaults(tx: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Merge global RF config into a tx_request dict."""
    rf_cfg = cfg.get("rf", {}) or {}
    out = dict(tx)
    out.setdefault("tx_power_mode", rf_cfg.get("tx_power_mode", "smart"))
    out.setdefault("tx_power_target_dbm", rf_cfg.get("tx_power_target_dbm", 0))
    out.setdefault("tx_power_band", rf_cfg.get("tx_power_band", "auto"))
    out.setdefault("frend0_pa_power", rf_cfg.get("frend0_pa_power"))
    out.setdefault("frend0_lodiv_buf_current_tx", rf_cfg.get("frend0_lodiv_buf_current_tx"))
    out.setdefault("patable", rf_cfg.get("patable"))
    return out


class TxScriptContext:
    """Helpers exposed to user *.py tx scripts."""

    def __init__(self, *, radio: Any, cfg: Dict[str, Any], script_path: str):
        self.radio = radio
        self.config = cfg
        self.script_path = script_path
        self.script_dir = os.path.dirname(os.path.abspath(script_path))

    def log(self, msg: str) -> None:
        print(f"[Py] {msg}")

    def sleep(self, seconds: float) -> None:
        time.sleep(float(seconds))

    def transmit(self, **tx: Any) -> None:
        """Low-level transmit helper (accepts rf.Radio.transmit kwargs)."""
        if "freq" not in tx or "payload" not in tx:
            raise ValueError("transmit() requires freq=<hz> and payload=<bytes>")
        merged = _apply_rf_defaults(tx, self.config)
        self.radio.transmit(**merged)

    def tx_hex(self, freq_hz: int, payload_hex: str, **opts: Any) -> None:
        s = (payload_hex or "").strip()
        if s.lower().startswith("0x"):
            s = s[2:]
        s = re.sub(r"[^0-9a-fA-F]", "", s)
        if len(s) % 2:
            s = "0" + s
        payload = bytes.fromhex(s)
        self.transmit(freq=int(freq_hz), payload=payload, **opts)

    def tx_b64(self, freq_hz: int, payload_b64: str, **opts: Any) -> None:
        import base64

        payload = base64.b64decode((payload_b64 or "").encode("ascii"))
        self.transmit(freq=int(freq_hz), payload=payload, **opts)

    def tx_file(self, rel_or_abs_path: str, **overrides: Any) -> None:
        """Replay a .sub or .rfcat.json from within a script."""
        p = rel_or_abs_path
        if not os.path.isabs(p):
            p = os.path.join(self.script_dir, p)
        tx = get_tx_request(p)
        tx.update(overrides)
        tx = _apply_rf_defaults(tx, self.config)
        self.radio.transmit(**tx)


def _coerce_tx_list(obj: Any) -> Optional[list[dict]]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, (list, tuple)):
        out: list[dict] = []
        for item in obj:
            if not isinstance(item, dict):
                raise ValueError("TX list items must be dicts")
            out.append(item)
        return out
    return None


def _execute_python_tx_script(path: str, state: AppState) -> None:
    files_cfg = state.config.get("files", {}) or {}
    allow = bool(files_cfg.get("allow_python_scripts", False))
    if not allow:
        print("[Py] ERROR: Python scripts are disabled. Set files.allow_python_scripts=true to enable.")
        return
    if not state.radio:
        print("[Py] ERROR: RF device not initialized")
        return

    timeout_s_raw = files_cfg.get("python_timeout_s", 30)
    try:
        timeout_s = int(timeout_s_raw)
    except Exception:
        timeout_s = 30
    if timeout_s < 1:
        timeout_s = 1

    ctx = TxScriptContext(radio=state.radio, cfg=state.config, script_path=path)

    # Run in the script's folder so relative paths work.
    cwd = os.getcwd()
    old_handler = None

    def _timeout_handler(signum, frame):  # pragma: no cover
        raise TimeoutError(f"TX script timed out after {timeout_s}s")

    try:
        os.chdir(ctx.script_dir)

        # Best-effort timeout (Unix only).
        if hasattr(signal, "SIGALRM"):
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout_s)

        # Load the script without executing __main__ blocks.
        env = runpy.run_path(
            path,
            init_globals={"ctx": ctx},
            run_name="__tx_script__",
        )

        # Convention 1: run(ctx) or main(ctx)
        fn = env.get("run") or env.get("main")
        if callable(fn):
            fn(ctx)
            return

        # Convention 2: TX = {...} or TX = [{...}, {...}]
        tx_list = _coerce_tx_list(env.get("TX"))
        if tx_list is None and callable(env.get("get_tx_requests")):
            tx_list = _coerce_tx_list(env["get_tx_requests"]())

        if tx_list:
            for i, tx in enumerate(tx_list, start=1):
                merged = _apply_rf_defaults(tx, state.config)
                print(f"[Py] TX {i}/{len(tx_list)}")
                state.radio.transmit(**merged)
            return

        # Otherwise: assume the script used ctx.tx_* helpers directly.
        print("[Py] Script executed (no TX object detected)")

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[Py] ERROR executing {os.path.basename(path)}: {e}\n{tb}")
    finally:
        try:
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
        except Exception:
            pass
        try:
            os.chdir(cwd)
        except Exception:
            pass


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

        # Special case: execute user-provided TX scripts (optional).
        if str(file_path).lower().endswith(".py"):
            print(f"[Py] Running {os.path.basename(file_path)}")
            _execute_python_tx_script(file_path, state)
            return

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
            merged = _apply_rf_defaults(tx, state.config)
            state.radio.transmit(**merged)
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
    port_raw = mqtt_cfg.get("port", 1883)
    if port_raw in (None, "", "null"):
        port = 1883
    else:
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            port = 1883

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

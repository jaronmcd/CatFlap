import os
import json
import re
import logging

logger = logging.getLogger("Discovery")

SUPPORTED_EXTENSIONS = (
    ".sub",
    ".rfcat.json",
    ".py",
)

DEFAULT_ENTITY_ICON = "mdi:radio-tower"
CACHE_FILENAME = ".discovery_cache.json"


# ---------------------------------------------------------------------------
# Icon defaults / heuristics
# ---------------------------------------------------------------------------

# Keyword -> icon (first match wins). Edit freely.
ICON_KEYWORDS = [
    ("garage", "mdi:garage"),
    ("door", "mdi:door"),
    ("gate", "mdi:gate"),
    ("lock", "mdi:lock"),
    ("unlock", "mdi:lock-open-variant"),
    ("alarm", "mdi:alarm-light"),
    ("sir", "mdi:alarm-light"),         # "siren"
    ("light", "mdi:lightbulb"),
    ("lamp", "mdi:lamp"),
    ("fan", "mdi:fan"),
    ("sprink", "mdi:sprinkler"),
    ("water", "mdi:water"),
    ("heat", "mdi:fire"),
    ("heater", "mdi:fire"),
    ("ac", "mdi:snowflake"),
    ("air", "mdi:air-conditioner"),
    ("car", "mdi:car"),
    ("vehicle", "mdi:car"),
    ("outlet", "mdi:power-socket-us"),
    ("plug", "mdi:power-plug"),
    ("bell", "mdi:bell"),
    ("remote", "mdi:remote"),
    ("rf", "mdi:radio-tower"),
    ("radio", "mdi:radio-tower"),
]

# File extension defaults (used only if no keyword match and no overrides).
ICON_BY_EXTENSION = {
    ".sub": "mdi:remote",
    ".rfcat.json": "mdi:radio-tower",
    ".py": "mdi:language-python",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize(text):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text).lower()


def _strip_known_suffix(filename: str) -> str:
    fn = filename
    for suf in (".rfcat.json",):
        if fn.lower().endswith(suf):
            return fn[: -len(suf)]
    return os.path.splitext(fn)[0]


def get_cache_path(base_dir):
    return os.path.join(base_dir, CACHE_FILENAME)


def load_cache(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data) if isinstance(data, list) else set()
        except Exception:
            return set()
    return set()


def save_cache(path, topics):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(list(topics)), f)
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")


def _purge_topics(client, topics):
    """Delete HA entities by clearing retained discovery config topics."""
    for t in topics:
        try:
            client.publish(t, "", retain=True)
        except Exception:
            pass


def _normalize_mdi_icon(s: str):
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    return s if s.startswith("mdi:") else f"mdi:{s}"


def _read_first_line(path: str):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readline().strip()
    except Exception:
        return None


def _guess_icon_from_text(text: str):
    t = (text or "").lower()
    for kw, icon in ICON_KEYWORDS:
        if kw in t:
            return icon
    return None


def _ext_for_file(filename: str):
    low = filename.lower()
    for ext in ICON_BY_EXTENSION.keys():
        if low.endswith(ext):
            return ext
    return os.path.splitext(low)[1]


def _find_folder_icon(root_dir: str, stop_dir: str, default_icon: str, cache: dict):
    """
    Folder icon resolution:
      1) nearest .mdi-icon file (walking up to stop_dir)
      2) keyword guess from relative path
      3) default_icon
    Cached by absolute root_dir.
    """
    abs_root = os.path.abspath(root_dir)
    if abs_root in cache:
        return cache[abs_root]

    stop = os.path.abspath(stop_dir)

    d = abs_root
    while True:
        candidate = os.path.join(d, ".mdi-icon")
        if os.path.exists(candidate):
            icon = _normalize_mdi_icon(_read_first_line(candidate))
            if icon:
                cache[abs_root] = icon
                return icon

        if d == stop:
            break
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent

    # No explicit .mdi-icon found — try keyword guess based on relative path
    try:
        rel = os.path.relpath(abs_root, stop)
    except Exception:
        rel = os.path.basename(abs_root)
    guess = _guess_icon_from_text(rel)
    icon = guess or default_icon
    cache[abs_root] = icon
    return icon


def _find_file_icon(root: str, filename: str, stem: str, folder_icon: str):
    """
    File icon resolution:
      1) sidecar <stem>.icon (or <filename>.icon)
      2) keyword guess from stem
      3) extension default
      4) folder_icon
    """
    # sidecar options
    sidecars = [
        os.path.join(root, f"{stem}.icon"),
        os.path.join(root, f"{filename}.icon"),  # allows "thing.sub.icon"
    ]
    for sc in sidecars:
        if os.path.exists(sc):
            icon = _normalize_mdi_icon(_read_first_line(sc))
            if icon:
                return icon

    guess = _guess_icon_from_text(stem)
    if guess:
        return guess

    ext = _ext_for_file(filename)
    if ext in ICON_BY_EXTENSION:
        return ICON_BY_EXTENSION[ext]

    return folder_icon


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_discovery(client, config):
    files_cfg = config.get("files", {}) or {}
    dev_cfg = config.get("device_info", {}) or {}

    # Only expose *.py scripts as buttons when explicitly enabled.
    allow_py = bool(files_cfg.get("allow_python_scripts", False))
    supported_exts = SUPPORTED_EXTENSIONS if allow_py else tuple(
        e for e in SUPPORTED_EXTENSIONS if e != ".py"
    )

    sub_dir = files_cfg["sub_directory"]
    node_id = files_cfg.get("node_id", "rfcat_replay")
    prefix = files_cfg.get("discovery_prefix", "homeassistant")

    # Cleanup modes:
    #  - "stale" (default): remove only entities that no longer exist
    #  - "wipe": remove everything from last run, then recreate
    cleanup_mode = str(files_cfg.get("discovery_cleanup", "stale")).strip().lower()
    if cleanup_mode not in ("stale", "wipe"):
        cleanup_mode = "stale"

    hub_name = dev_cfg.get("hub_name", "rfcat gateway")
    manufacturer = dev_cfg.get("manufacturer", "CatFlap")
    model = dev_cfg.get("model", "RF Remote")

    # Optional override for overall default icon
    default_icon = _normalize_mdi_icon(dev_cfg.get("default_entity_icon")) or DEFAULT_ENTITY_ICON

    topic_map = {}
    current_topics = set()

    # Cache is stored in parent of sub_directory (your tests assume this)
    cache_file = get_cache_path(os.path.dirname(sub_dir))
    previous_topics = load_cache(cache_file)

    if cleanup_mode == "wipe" and previous_topics:
        logger.info(f"Wipe mode: removing {len(previous_topics)} previously created entities")
        _purge_topics(client, previous_topics)
        previous_topics = set()

    # Register Hub
    gateway_icon = config.get("device_info", {}).get("gateway_icon", "mdi:cat")

    hub_topic = f"{prefix}/binary_sensor/{node_id}_status/config"
    client.publish(hub_topic, json.dumps({
        "name": "Bridge Status",
        "unique_id": f"{node_id}_status",
        "state_topic": f"{node_id}/status",
        "device_class": "connectivity",
        "icon": gateway_icon,   # <-- add this
        "device": {
            "identifiers": [node_id],
            "name": hub_name,
            "model": "Python Gateway",
            "manufacturer": manufacturer
        }
    }), retain=True)
    
    client.publish(f"{node_id}/status", "ON", retain=True)
    current_topics.add(hub_topic)

    if not os.path.exists(sub_dir):
        logger.error(f"Directory not found: {sub_dir}")
        # Keep legacy behavior: bail without cleanup if folder missing
        return topic_map

    folder_icon_cache = {}

    # Scan Files
    for root, dirs, files in os.walk(sub_dir):
        supported_files = [f for f in files if f.lower().endswith(supported_exts)]
        if not supported_files:
            continue

        folder_name = os.path.basename(root)
        is_root = (os.path.abspath(root) == os.path.abspath(sub_dir))

        device_name = "Misc Files" if is_root else folder_name.replace("_", " ")
        device_suffix = "main" if is_root else sanitize(folder_name)
        device_id = f"{node_id}_{device_suffix}"

        folder_icon = _find_folder_icon(root, sub_dir, default_icon, folder_icon_cache)

        for f in supported_files:
            stem = _strip_known_suffix(f)
            file_clean = sanitize(stem)
            unique_id = f"{device_id}_{file_clean}"

            cmd_topic = f"{node_id}/{device_suffix}/{file_clean}/set"
            disc_topic = f"{prefix}/button/{unique_id}/config"

            topic_map[cmd_topic] = os.path.join(root, f)

            file_icon = _find_file_icon(root, f, stem, folder_icon)

            client.publish(
                disc_topic,
                json.dumps(
                    {
                        "name": stem.replace("_", " "),
                        "unique_id": unique_id,
                        "command_topic": cmd_topic,
                        "payload_press": "PRESS",
                        "icon": file_icon,
                        "device": {
                            "identifiers": [device_id],
                            "name": device_name,
                            "model": model,
                            "manufacturer": manufacturer,
                            "via_device": node_id,
                        },
                    }
                ),
                retain=True,
            )
            client.subscribe(cmd_topic)
            current_topics.add(disc_topic)

    # Cleanup stale (default)
    if cleanup_mode == "stale":
        stale = previous_topics - current_topics
        if stale:
            logger.info(f"Cleaning up {len(stale)} old entities")
            _purge_topics(client, stale)

    save_cache(cache_file, current_topics)
    return topic_map


def set_offline(client, config):
    node_id = (config.get("files") or {}).get("node_id", "rfcat_replay")
    client.publish(f"{node_id}/status", "OFF", retain=True)

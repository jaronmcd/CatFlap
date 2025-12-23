import json
import os
import sys

CONFIG_FILE = "config.json"


def load_config() -> dict:
    """Load runtime config from src/config.json.

    When running as a Home Assistant add-on, run.sh writes this file into
    /app/src/config.json. In a development environment you can create it
    yourself (see config.json.example).
    """

    # Determine path relative to this script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, CONFIG_FILE)

    if not os.path.exists(config_path):
        print(f"CRITICAL: Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if not isinstance(config, dict):
        print("CRITICAL: config.json must contain a JSON object")
        sys.exit(1)

    config.setdefault("mqtt", {})
    config.setdefault("files", {})
    config.setdefault("device_info", {})

    # New CC1110/CC1111 power configuration (no backwards compatibility)
    config.setdefault("rf", {})
    rf = config["rf"]
    rf.setdefault("tx_power_mode", "max")  # 'max' | 'default' | 'manual'
    rf.setdefault("frend0_pa_power", None)  # 0..7 (FREND0.PA_POWER)
    rf.setdefault("frend0_lodiv_buf_current_tx", None)  # 0..3 (FREND0.LODIV_BUF_CURRENT_TX)
    rf.setdefault("patable", None)  # single value or list/CSV of up to 8 values

    # Normalize the sub_directory path
    raw_sub = config["files"].get("sub_directory", "./tx_files")
    if isinstance(raw_sub, str) and not raw_sub.startswith("/"):
        config["files"]["sub_directory"] = os.path.join(base_dir, raw_sub)

    return config

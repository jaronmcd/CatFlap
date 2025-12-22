import json
import os
import sys

CONFIG_FILE = "config.json"

def load_config():
    # Determine path relative to this script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, CONFIG_FILE)

    if not os.path.exists(config_path):
        print(f"CRITICAL: Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = json.load(f)

    # Normalize the sub_directory path
    raw_sub = config['files'].get('sub_directory', './sub_files')
    if not raw_sub.startswith("/"):
        config['files']['sub_directory'] = os.path.join(base_dir, raw_sub)
    
    return config
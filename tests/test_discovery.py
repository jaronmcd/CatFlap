import os
import json
import pytest
from unittest.mock import MagicMock
import sys

# Ensure we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from discovery import run_discovery

# --- Helper to create mock files ---
def create_mock_file(base_dir, subfolder, filename):
    """Creates a dummy file to simulate a radio recording."""
    folder = base_dir / subfolder
    os.makedirs(folder, exist_ok=True)
    (folder / filename).touch()
    return str(folder / filename)

def test_discovery_logic(tmp_path):
    # 1. Setup Mock Directory Structure
    # We create a mix of valid and invalid files to test the filtering logic.
    tx_dir = tmp_path / "tx_files"
    
    create_mock_file(tx_dir, "Remotes", "Fan_Power.sub")       # Valid .sub
    create_mock_file(tx_dir, "Sensors", "Door_Bell.rfcat.json") # Valid .json
    create_mock_file(tx_dir, "Logs", "readme.txt")             # Invalid (should be ignored)

    # 2. Mock Config
    config = {
        'files': {
            'sub_directory': str(tx_dir),
            'node_id': 'test_node',
            'discovery_prefix': 'homeassistant'
        },
        'device_info': {
            'hub_name': 'Test Hub',
            'manufacturer': 'TestBrand',
            'model': 'TestModel'
        }
    }
    
    # 3. Mock MQTT Client
    mock_client = MagicMock()
    
    # 4. Run Discovery
    run_discovery(mock_client, config)
    
    # 5. Analyze Results
    discovered_ids = []
    
    for call in mock_client.publish.call_args_list:
        topic, payload = call[0][0], call[0][1]
        
        # We only care about discovery config messages
        if topic.endswith("/config"):
            # FIX: Skip empty payloads (deletion messages)
            if not payload:
                continue
                
            data = json.loads(payload)
            if 'unique_id' in data:
                discovered_ids.append(data['unique_id'])

    # 6. Assertions
    print(f"Discovered IDs: {discovered_ids}")
    
    # Check that the Hub status was published
    assert "test_node_status" in discovered_ids
    
    # Check that valid files were found (names are sanitized: 'Fan_Power' -> 'fan_power')
    # ID format: node_id + subfolder + filename
    assert "test_node_remotes_fan_power" in discovered_ids
    assert "test_node_sensors_door_bell" in discovered_ids
    
    # Check that the text file was IGNORED
    assert "test_node_logs_readme" not in discovered_ids
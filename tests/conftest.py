import sys
import os
from unittest.mock import MagicMock
from types import ModuleType

# 1. Add 'src' to the Python path so tests can find your code
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# 2. Mock rflib BEFORE any test imports rf.py
# This prevents "ImportError: No module named rflib"
mock_rflib = MagicMock()
sys.modules["rflib"] = mock_rflib

# 3. Define constants that rflib usually provides
mock_rflib.MOD_ASK_OOK = 0x30
mock_rflib.MOD_2FSK = 0x00
mock_rflib.MOD_GFSK = 0x10
mock_rflib.MOD_MSK = 0x70
mock_rflib.MANCHESTER = 0x08

# 4. Mock paho-mqtt for environments where it's not installed.
# The production add-on image installs it via requirements.txt, but the unit
# test runner here may not.
paho = ModuleType("paho")
paho_mqtt = ModuleType("paho.mqtt")
paho_mqtt_client = MagicMock()

# Minimal API surface used by src/main.py
class _CbVersion:
    VERSION2 = object()

paho_mqtt_client.CallbackAPIVersion = _CbVersion
paho_mqtt_client.Client = MagicMock()

sys.modules.setdefault("paho", paho)
sys.modules.setdefault("paho.mqtt", paho_mqtt)
sys.modules.setdefault("paho.mqtt.client", paho_mqtt_client)

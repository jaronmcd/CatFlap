#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting CatFlap..."

# Add-on version -> used by main.py banner (it will add the leading "v" if needed)
if bashio::addon.version >/dev/null 2>&1; then
  export CATFLAP_VERSION="$(bashio::addon.version)"
fi

# Defaults (keep these internal unless you *want* to expose them again)
TX_POWER="max"
PREFIX="homeassistant"
LOG_LEVEL="info"

# Optional overrides (only if present in add-on config)
if bashio::config.has_value 'tx_power'; then
  TX_POWER="$(bashio::config 'tx_power')"
fi
if bashio::config.has_value 'discovery_prefix'; then
  PREFIX="$(bashio::config 'discovery_prefix')"
fi
if bashio::config.has_value 'log_level'; then
  LOG_LEVEL="$(bashio::config 'log_level')"
fi

MQTT_HOST="$(bashio::config 'mqtt_broker')"
MQTT_PORT="$(bashio::config 'mqtt_port')"
MQTT_USER="$(bashio::config 'mqtt_user')"
MQTT_PASS="$(bashio::config 'mqtt_password')"
NODE_ID="$(bashio::config 'node_id')"
SUB_DIR="$(bashio::config 'sub_directory')"

mkdir -p "${SUB_DIR}"

# Log config safely (never print password)
if [ -n "${MQTT_USER}" ]; then
  bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT} (user: ${MQTT_USER})"
else
  bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT} (no auth)"
fi
bashio::log.info "Node ID: ${NODE_ID}"
bashio::log.info "TX directory: ${SUB_DIR}"
bashio::log.info "TX power: ${TX_POWER}"
bashio::log.info "Log level: ${LOG_LEVEL}"

# Generate runtime config for the python app
cat > /app/src/config.json <<EOF
{
  "mqtt": {
    "broker": "${MQTT_HOST}",
    "port": ${MQTT_PORT},
    "username": "${MQTT_USER}",
    "password": "${MQTT_PASS}"
  },
  "files": {
    "sub_directory": "${SUB_DIR}",
    "node_id": "${NODE_ID}",
    "discovery_prefix": "${PREFIX}"
  },
  "device_info": {
    "hub_name": "CatFlap",
    "manufacturer": "CatFlap",
    "model": "Gateway"
  },
  "rf": {
    "tx_power": "${TX_POWER}"
  },
  "log_level": "${LOG_LEVEL}"
}
EOF

bashio::log.info "Launching bridge..."
export PYTHONPATH="/app/src"
exec python3 -u /app/src/main.py

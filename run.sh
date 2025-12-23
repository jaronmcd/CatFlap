#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting CatFlap..."

# Add-on version -> used by main.py banner (it will add the leading "v" if needed)
if bashio::addon.version >/dev/null 2>&1; then
  export CATFLAP_VERSION="$(bashio::addon.version)"
fi

PREFIX="homeassistant"
LOG_LEVEL="info"

# CC1110/CC1111 power config
TX_POWER_MODE="max"
FREND0_PA_POWER=""
FREND0_LODIV_BUF_CURRENT_TX=""
PATABLE_RAW=""

# Optional overrides (only if present in add-on config)
if bashio::config.has_value 'discovery_prefix'; then
  PREFIX="$(bashio::config 'discovery_prefix')"
fi
if bashio::config.has_value 'log_level'; then
  LOG_LEVEL="$(bashio::config 'log_level')"
fi

if bashio::config.has_value 'tx_power_mode'; then
  TX_POWER_MODE="$(bashio::config 'tx_power_mode')"
fi
if bashio::config.has_value 'frend0_pa_power'; then
  FREND0_PA_POWER="$(bashio::config 'frend0_pa_power')"
fi
if bashio::config.has_value 'frend0_lodiv_buf_current_tx'; then
  FREND0_LODIV_BUF_CURRENT_TX="$(bashio::config 'frend0_lodiv_buf_current_tx')"
fi
if bashio::config.has_value 'patable'; then
  PATABLE_RAW="$(bashio::config 'patable')"
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
bashio::log.info "Log level: ${LOG_LEVEL}"

bashio::log.info "TX power mode: ${TX_POWER_MODE}"
if [ -n "${FREND0_PA_POWER}" ]; then
  bashio::log.info "FREND0.PA_POWER: ${FREND0_PA_POWER}"
fi
if [ -n "${FREND0_LODIV_BUF_CURRENT_TX}" ]; then
  bashio::log.info "FREND0.LODIV_BUF_CURRENT_TX: ${FREND0_LODIV_BUF_CURRENT_TX}"
fi
if [ -n "${PATABLE_RAW}" ]; then
  bashio::log.info "PATABLE: ${PATABLE_RAW}"
fi

# Build JSON-safe values
PA_POWER_JSON="null"
if [ -n "${FREND0_PA_POWER}" ]; then
  PA_POWER_JSON="${FREND0_PA_POWER}"
fi

LODIV_JSON="null"
if [ -n "${FREND0_LODIV_BUF_CURRENT_TX}" ]; then
  LODIV_JSON="${FREND0_LODIV_BUF_CURRENT_TX}"
fi

PATABLE_JSON="null"
if [ -n "${PATABLE_RAW}" ]; then
  # Escape for JSON string: backslash, then quote.
  PATABLE_ESC="${PATABLE_RAW//\\/\\\\}"
  PATABLE_ESC="${PATABLE_ESC//\"/\\\"}"
  PATABLE_JSON="\"${PATABLE_ESC}\""
fi

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
    "tx_power_mode": "${TX_POWER_MODE}",
    "frend0_pa_power": ${PA_POWER_JSON},
    "frend0_lodiv_buf_current_tx": ${LODIV_JSON},
    "patable": ${PATABLE_JSON}
  },
  "log_level": "${LOG_LEVEL}"
}
EOF

bashio::log.info "Launching bridge..."
export PYTHONPATH="/app/src"
exec python3 -u /app/src/main.py

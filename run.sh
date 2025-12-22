#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting CatFlap..."

MQTT_HOST="$(bashio::config 'mqtt_broker')"
MQTT_PORT="$(bashio::config 'mqtt_port')"
MQTT_USER="$(bashio::config 'mqtt_user')"
MQTT_PASS="$(bashio::config 'mqtt_password')"
NODE_ID="$(bashio::config 'node_id')"
PREFIX="$(bashio::config 'discovery_prefix')"
SUB_DIR="$(bashio::config 'sub_directory')"
LOG_LEVEL="$(bashio::config 'log_level')"

mkdir -p "${SUB_DIR}"

# Log config safely (never print password)
if [ -n "${MQTT_USER}" ]; then
  bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT} (user: ${MQTT_USER})"
else
  bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT} (no auth)"
fi
bashio::log.info "Discovery prefix: ${PREFIX}"
bashio::log.info "Node ID: ${NODE_ID}"
bashio::log.info "TX directory: ${SUB_DIR}"
bashio::log.info "Log level: ${LOG_LEVEL}"

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
  "log_level": "${LOG_LEVEL}"
}
EOF

bashio::log.info "Launching bridge..."
export PYTHONPATH="/app/src"
exec python3 -u /app/src/main.py

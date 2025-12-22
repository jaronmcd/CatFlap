#!/bin/bash

# --- Configuration ---
SERVICE_NAME="CatFlap"
UDEV_RULE="/etc/udev/rules.d/20-rfcat.rules"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${RED}Starting CatFlap uninstaller...${NC}"

# 1. Check for Sudo
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Please run as root (sudo).${NC}"
  exit
fi

# 2. Stop and Remove Service
if systemctl list-units --full -all | grep -Fq "$SERVICE_NAME.service"; then
    echo -e "[1/4] Stopping and disabling service..."
    systemctl stop $SERVICE_NAME
    systemctl disable $SERVICE_NAME
    rm $SERVICE_FILE
    systemctl daemon-reload
    echo -e "${GREEN}Service removed.${NC}"
else
    echo -e "[1/4] Service not found (skipping)."
fi

# 3. Remove USB Permissions
if [ -f "$UDEV_RULE" ]; then
    echo -e "[2/4] Removing USB permission rules..."
    rm $UDEV_RULE
    udevadm control --reload-rules
    udevadm trigger
    echo -e "${GREEN}Rules removed.${NC}"
else
    echo -e "[2/4] Udev rules not found (skipping)."
fi

# 4. Final Cleanup Info
echo -e "[3/4] System clean up complete."
echo -e ""
echo -e "${GREEN}------------------------------------------------${NC}"
echo -e "The system integration has been removed."
echo -e "To delete the software completely, run this command:"
echo -e "${RED}rm -rf $(pwd)${NC}"
echo -e "${GREEN}------------------------------------------------${NC}"
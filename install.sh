#!/bin/bash

# --- Configuration ---
REPO_DIR=$(pwd)
VENV_DIR="$REPO_DIR/venv"
RFCAT_GIT="https://github.com/atlas0fd00m/rfcat.git"
SERVICE_NAME="CatFlap"
USER_NAME=$(whoami)

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting CatFlap installer...${NC}"

# 1. Check for Sudo/Root
if [ "$EUID" -eq 0 ]; then 
  echo -e "${RED}Please do not run as root. Run as your normal user with sudo privileges.${NC}"
  exit
fi

# 2. Install System Dependencies
echo -e "${GREEN}[1/7] Installing system dependencies...${NC}"
sudo apt-get update
sudo apt-get install -y git libusb-1.0-0-dev python3-venv python3-pip python3-setuptools

# 3. Create Virtual Environment
echo -e "${GREEN}[2/7] Setting up Python environment...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 4. Install RfCat (The hard part)
echo -e "${GREEN}[3/7] Building RfCat drivers...${NC}"
pip install --upgrade pip setuptools wheel

if [ ! -d "rfcat" ]; then
    git clone "$RFCAT_GIT"
fi

cd rfcat
python setup.py install
cd ..

# 5. Install Python Requirements
echo -e "${GREEN}[4/7] Installing Python requirements...${NC}"
pip install -r requirements.txt

# 6. Setup Config
echo -e "${GREEN}[5/7] Checking configuration...${NC}"
# Check if src/config.json exists (preferred location)
if [ ! -f "src/config.json" ]; then
    if [ -f "config.json.example" ]; then
        cp config.json.example src/config.json
        echo -e "${GREEN}Created src/config.json from example.${NC}"
        echo -e "${RED}IMPORTANT: You must edit src/config.json with your MQTT details!${NC}"
    else
        echo -e "${RED}No config.json.example found!${NC}"
    fi
fi

# 7. Setup Udev Rules (USB Permissions)
echo -e "${GREEN}[6/7] Configuring USB permissions...${NC}"
sudo bash -c 'cat > /etc/udev/rules.d/20-rfcat.rules <<EOF
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="605b", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="6047", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="6048", MODE="0666"
EOF'
sudo udevadm control --reload-rules
sudo udevadm trigger

# 8. Setup Systemd Service (Optional)
echo -e "${GREEN}[7/7] Service Setup${NC}"
read -p "Do you want to install the systemd service for auto-start? (y/N) " -n 1 -r
echo # move to new line
SERVICE_INSTALLED=false

if [[ $REPLY =~ ^[Yy]$ ]]; then
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

    sudo bash -c "cat > $SERVICE_FILE <<EOF
[Unit]
Description=RfCat to Home Assistant Bridge
After=network.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$REPO_DIR
ExecStart=$VENV_DIR/bin/python $REPO_DIR/src/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME
    SERVICE_INSTALLED=true
    echo -e "${GREEN}Service installed.${NC}"
else
    echo -e "Skipping service installation."
fi

echo -e "${GREEN}------------------------------------------------${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e ""
echo -e "1. Edit your config:  ${GREEN}nano src/config.json${NC}"

if [ "$SERVICE_INSTALLED" = true ]; then
    echo -e "2. Start the bridge:  ${GREEN}sudo systemctl start $SERVICE_NAME${NC}"
    echo -e "3. Check logs:        ${GREEN}sudo journalctl -u $SERVICE_NAME -f${NC}"
else
    echo -e "2. Run manually:      ${GREEN}source venv/bin/activate && python src/main.py${NC}"
fi
echo -e "${GREEN}------------------------------------------------${NC}"
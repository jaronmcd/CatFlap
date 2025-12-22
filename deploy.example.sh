#!/bin/bash

# ==============================================================================
# RF_CAT HOME ASSISTANT DEPLOYMENT SCRIPT (TEMPLATE)
# ==============================================================================

# --- CONFIGURATION (EDIT THESE) ---
HA_HOST="192.168.1.X"
HA_USER="root"
REMOTE_ADDON_PATH="/addons/local/catflap"
REMOTE_SHARE_PATH="/share/tx_files"
ADDON_SLUG="local_catflap"
# --- END CONFIGURATION ---

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${BLUE}[1/4] Preparing Remote Directories...${NC}"
ssh "$HA_USER@$HA_HOST" "mkdir -p $REMOTE_ADDON_PATH && mkdir -p $REMOTE_SHARE_PATH"

echo -e "${BLUE}[2/4] Syncing Add-on Code...${NC}"
rsync -avz --delete \
    --exclude-from='.gitignore' \
    --exclude='.git' \
    --exclude='deploy.sh' \
    --exclude='deploy.example.sh' \
    --exclude='tx_files' \
    ./ "$HA_USER@$HA_HOST:$REMOTE_ADDON_PATH/"

echo -e "${BLUE}[3/4] Syncing Radio Files (Data)...${NC}"
rsync -avz --delete \
    ./tx_files/ "$HA_USER@$HA_HOST:$REMOTE_SHARE_PATH/"

echo -e "${BLUE}[4/4] Managing Home Assistant Add-on...${NC}"
# IMPROVED LOGIC:
# We silence the output of the check (> /dev/null 2>&1) so the user sees no errors.
ssh "$HA_USER@$HA_HOST" "
    echo '... Refreshing Add-on Store'
    ha store reload
    
    # Check if the addon is already installed
    if ha addons info $ADDON_SLUG > /dev/null 2>&1; then
        echo '... Add-on found. UPDATING (Rebuild)...'
        ha addons rebuild $ADDON_SLUG
    else
        echo '... Add-on not found. INSTALLING...'
        ha addons install $ADDON_SLUG
    fi
    
    echo '... Starting Service'
    ha addons start $ADDON_SLUG
    
    echo '... Waiting for startup logs'
    sleep 3
    ha addons logs $ADDON_SLUG
"

echo -e "${GREEN}Deployment Complete!${NC}"
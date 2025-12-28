#!/bin/bash

# IOTA Wallet Setup Script
# Creates a Bittensor wallet and configures it for mining

set -e

WALLET_NAME="${1:-iota_miner}"
HOTKEY_NAME="${2:-default}"

echo "========================================="
echo "  IOTA Wallet Setup Script"
echo "========================================="
echo ""
echo "Wallet Name: $WALLET_NAME"
echo "Hotkey Name: $HOTKEY_NAME"
echo ""

# Check if btcli is installed
if ! command -v btcli &> /dev/null; then
    echo "Installing bittensor-cli..."
    pip install bittensor-cli
fi

# Check if wallet already exists
WALLET_PATH="$HOME/.bittensor/wallets/$WALLET_NAME"
if [ -d "$WALLET_PATH" ]; then
    echo "Wallet '$WALLET_NAME' already exists at $WALLET_PATH"
    read -p "Do you want to use existing wallet? (y/n): " use_existing
    if [ "$use_existing" != "y" ]; then
        echo "Exiting. Please choose a different wallet name."
        exit 1
    fi
else
    # Create coldkey (wallet)
    echo ""
    echo "Creating coldkey (main wallet)..."
    echo "IMPORTANT: Save your mnemonic phrase securely!"
    echo ""
    btcli wallet new_coldkey --wallet.name "$WALLET_NAME" --n-words 12
fi

# Check if hotkey exists
HOTKEY_PATH="$WALLET_PATH/hotkeys/$HOTKEY_NAME"
if [ -f "$HOTKEY_PATH" ]; then
    echo "Hotkey '$HOTKEY_NAME' already exists."
else
    # Create hotkey
    echo ""
    echo "Creating hotkey..."
    btcli wallet new_hotkey --wallet.name "$WALLET_NAME" --wallet.hotkey "$HOTKEY_NAME" --n-words 12
fi

# Update .env file
ENV_FILE=".env"
if [ -f ".env.example" ] && [ ! -f "$ENV_FILE" ]; then
    cp .env.example "$ENV_FILE"
fi

# Create or update .env
echo ""
echo "Configuring .env file..."

if [ -f "$ENV_FILE" ]; then
    # Update existing .env
    sed -i "s/^MINER_WALLET=.*/MINER_WALLET=$WALLET_NAME/" "$ENV_FILE" 2>/dev/null || \
        echo "MINER_WALLET=$WALLET_NAME" >> "$ENV_FILE"
    sed -i "s/^MINER_HOTKEY=.*/MINER_HOTKEY=$HOTKEY_NAME/" "$ENV_FILE" 2>/dev/null || \
        echo "MINER_HOTKEY=$HOTKEY_NAME" >> "$ENV_FILE"
else
    # Create new .env
    cat > "$ENV_FILE" << EOF
# IOTA Miner Configuration
MINER_WALLET=$WALLET_NAME
MINER_HOTKEY=$HOTKEY_NAME
DEVICE=xla
EOF
fi

echo ""
echo "========================================="
echo "  Wallet Setup Complete!"
echo "========================================="
echo ""
echo "Wallet: $WALLET_NAME"
echo "Hotkey: $HOTKEY_NAME"
echo "Path:   $WALLET_PATH"
echo ""

# Show wallet address
echo "Your wallet addresses:"
btcli wallet overview --wallet.name "$WALLET_NAME" 2>/dev/null || true

echo ""
echo "========================================="
echo "  Next Steps:"
echo "========================================="
echo ""
echo "1. Fund your wallet with TAO tokens"
echo "   - Get your coldkey address: btcli wallet overview --wallet.name $WALLET_NAME"
echo "   - Send TAO to that address"
echo ""
echo "2. Register on Subnet 9 (IOTA):"
echo "   btcli subnet register --wallet.name $WALLET_NAME --wallet.hotkey $HOTKEY_NAME --netuid 9"
echo ""
echo "3. Start mining:"
echo "   python src/miner/main.py"
echo ""
echo "For TPU, make sure DEVICE=xla is set in your .env"
echo ""

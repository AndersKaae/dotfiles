#!/bin/bash

# Configuration
VPN_NAME="UniFi-VPN"
GATEWAY="62.243.44.174"

# Check for required packages
REQUIRED_PKGS=("networkmanager-l2tp" "strongswan" "xl2tpd")
MISSING_PKGS=()

for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! pacman -Qs "$pkg" > /dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -ne 0 ]; then
    echo "Missing required packages: ${MISSING_PKGS[*]}"
    echo "Please run: sudo pacman -S ${MISSING_PKGS[*]}"
    exit 1
fi

# Securely gather credentials
read -p "Enter VPN Username: " VPN_USER
read -s -p "Enter VPN Password: " VPN_PASS
echo
read -s -p "Enter IPsec Pre-Shared Key (PSK): " VPN_PSK
echo

# Remove existing connection if it exists to avoid conflicts
nmcli connection delete "$VPN_NAME" 2>/dev/null

# Stop conflicting system services
echo "Stopping conflicting services..."
sudo systemctl stop strongswan xl2tpd 2>/dev/null
sudo systemctl disable strongswan xl2tpd 2>/dev/null

# Create the VPN connection
echo "Creating $VPN_NAME connection..."
nmcli connection add \
    type vpn \
    vpn-type l2tp \
    con-name "$VPN_NAME" \
    ifname "*" \
    -- \
    vpn.data "gateway=$GATEWAY, user=$VPN_USER, ipsec-enabled=yes, ipsec-psk=$VPN_PSK, password-flags=0, ipsec-ike=aes256-sha1-modp2048!, ipsec-esp=aes256-sha1!, refuse-eap=yes" \
    vpn.user-name "$VPN_USER"

# Add the password
nmcli connection modify "$VPN_NAME" vpn.secrets "password=$VPN_PASS"

echo "Setup complete! You can now toggle the VPN from Waybar or run: nmcli connection up '$VPN_NAME'"

#!/bin/bash
set -e

# Official repo packages (pacman)
PACMAN_PKGS=(
    # Hyprland core / lock / wallpaper
    hyprland hyprlock hyprpaper

    # Bars / launchers / notifications
    waybar rofi-wayland swaync

    # Screenshot / idle / lock helpers
    grim slurp swappy swaylock hypridle

    # Audio / brightness / media
    pipewire wireplumber pamixer alsa-utils brightnessctl playerctl

    # Clipboard / notification utils
    cliphist wl-clipboard libnotify

    # Terminal / file managers / browsers / apps
    ghostty nautilus firefox flatpak

    # Networking / VPN
    networkmanager networkmanager-l2tp strongswan xl2tpd impala iwd

    # Bluetooth
    bluez bluez-utils bluetui

    # Fonts
    ttf-jetbrains-mono-nerd

    # Sync / misc
    syncthing jq udiskie bc
)

# AUR packages (yay)
AUR_PKGS=(
    hyprpanel
)

sudo pacman -S --needed "${PACMAN_PKGS[@]}"

if ! command -v yay >/dev/null 2>&1; then
    echo "yay not found — install yay first to get AUR packages: ${AUR_PKGS[*]}"
    exit 1
fi
yay -S --needed "${AUR_PKGS[@]}"

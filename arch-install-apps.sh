#!/bin/bash
set -e

# Official repo packages (pacman)
PACMAN_PKGS=(
    # Hyprland core / lock / wallpaper
    hyprland hyprlock hyprpaper

    # Bars / launchers / notifications
    waybar rofi-wayland fuzzel mako

    # Screenshot / idle / lock helpers
    grim slurp swappy swayidle swaylock

    # Audio / brightness / media
    pipewire wireplumber pamixer alsa-utils brightnessctl playerctl mpc

    # Clipboard / notification utils
    cliphist wl-clipboard libnotify

    # Terminal / file managers / browsers / apps
    ghostty nautilus nemo firefox flatpak

    # Networking / VPN
    networkmanager-l2tp strongswan xl2tpd

    # Sync / misc
    syncthing jq
)

# AUR packages (yay)
AUR_PKGS=(
    hyprpanel
    vesktop-bin
    brave-bin
    spotify
)

sudo pacman -S --needed "${PACMAN_PKGS[@]}"

if ! command -v yay >/dev/null 2>&1; then
    echo "yay not found — install yay first to get AUR packages: ${AUR_PKGS[*]}"
    exit 1
fi
yay -S --needed "${AUR_PKGS[@]}"

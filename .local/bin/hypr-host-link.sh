#!/usr/bin/env bash
# Point ~/.config/hypr/host.conf at this machine's per-host Hyprland config.
#
# hyprland.conf ends with `source = ~/.config/hypr/host.conf`. Hyprland's config
# language has no conditionals and cannot shell out, so this symlink is what
# selects the per-host file. Run once per machine; safe to re-run.
set -euo pipefail

HYPR_DIR="$HOME/.config/hypr"
HOST="$(cat /etc/hostname 2>/dev/null || uname -n)"

target="hosts/${HOST}.conf"
if [ ! -f "$HYPR_DIR/$target" ]; then
    echo "No $target - falling back to hosts/default.conf"
    echo "  (create $HYPR_DIR/$target to give this host its own rules)"
    target="hosts/default.conf"
fi

ln -sfn "$target" "$HYPR_DIR/host.conf"
echo "host.conf -> $target"

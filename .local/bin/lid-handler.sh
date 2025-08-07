#!/bin/bash

LAPTOP="eDP-1"
EXTERNAL="DP-3"
WORKSPACE="1"
LAST_STATE=""

# Wait for Hyprland socket
while [ -z "$HYPRLAND_INSTANCE_SIGNATURE" ] || [ ! -S "$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock" ]; do
    echo "Waiting for Hyprland..."
    sleep 1
    export HYPRLAND_INSTANCE_SIGNATURE=$(systemctl --user show-environment | grep HYPRLAND_INSTANCE_SIGNATURE | cut -d= -f2)
done

echo "✅ Hyprland is ready. Detecting original laptop monitor config..."

# Grab original config line for LAPTOP from hyprctl monitors
ORIGINAL_CFG=$(hyprctl monitors -j | jq -r ".[] | select(.name==\"$LAPTOP\") | \"${LAPTOP},\(.width)x\(.height)@\(.refreshRate),\(.x)x\(.y),\(.scale)\"")

if [ -z "$ORIGINAL_CFG" ]; then
    echo "❌ Could not detect original config for $LAPTOP"
    exit 1
fi

echo "Original config for $LAPTOP: $ORIGINAL_CFG"

# Main loop watching lid state
while true; do
    LID_STATE=$(awk '{print $2}' /proc/acpi/button/lid/*/state)

    if [ "$LID_STATE" != "$LAST_STATE" ]; then
        if [ "$LID_STATE" == "closed" ]; then
            hyprctl dispatch moveworkspacetomonitor $WORKSPACE $EXTERNAL
            hyprctl keyword monitor "$LAPTOP,disable"
            echo "Moved workspace $WORKSPACE to $EXTERNAL and disabled $LAPTOP (lid closed)"
        else
            hyprctl keyword monitor "$ORIGINAL_CFG"
            hyprctl dispatch moveworkspacetomonitor $WORKSPACE $LAPTOP
            echo "Re-enabled $LAPTOP and moved workspace $WORKSPACE back (lid open)"
        fi
        LAST_STATE=$LID_STATE
    fi

    sleep 1
done

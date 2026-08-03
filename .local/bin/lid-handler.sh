#!/bin/bash

LAPTOP="eDP-1"
WORKSPACE="1"
LAST_STATE=""

# Machines without a lid (the desktop) have no lid to watch. Exit 0 rather than
# spinning a 1-second poll loop forever over a path that will never exist.
LID_STATE_FILE=$(echo /proc/acpi/button/lid/*/state)
if [ ! -r "$LID_STATE_FILE" ]; then
    echo "No lid on this machine - nothing to do."
    exit 0
fi

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

# Resolved fresh on every lid close: connector names are not stable (this was
# hardcoded to DP-3, which the Dell had already moved off of).
external_monitor() {
    hyprctl monitors -j | jq -r --arg laptop "$LAPTOP" \
        'first(.[] | select(.name != $laptop) | .name) // empty'
}

# Main loop watching lid state
while true; do
    LID_STATE=$(awk '{print $2}' "$LID_STATE_FILE")

    if [ "$LID_STATE" != "$LAST_STATE" ]; then
        if [ "$LID_STATE" == "closed" ]; then
            EXTERNAL=$(external_monitor)
            if [ -z "$EXTERNAL" ]; then
                # Disabling the only output leaves no screen at all.
                echo "Lid closed but no external monitor - leaving $LAPTOP enabled"
            else
                hyprctl dispatch moveworkspacetomonitor $WORKSPACE $EXTERNAL
                hyprctl keyword monitor "$LAPTOP,disable"
                echo "Moved workspace $WORKSPACE to $EXTERNAL and disabled $LAPTOP (lid closed)"
            fi
        else
            hyprctl keyword monitor "$ORIGINAL_CFG"
            hyprctl dispatch moveworkspacetomonitor $WORKSPACE $LAPTOP
            echo "Re-enabled $LAPTOP and moved workspace $WORKSPACE back (lid open)"
        fi
        LAST_STATE=$LID_STATE
    fi

    sleep 1
done

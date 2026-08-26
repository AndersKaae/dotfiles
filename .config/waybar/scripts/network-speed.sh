#!/usr/bin/env bash
set -uo pipefail

ifname=$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')

if [[ -z "${ifname:-}" ]]; then
  jq -cn '{text: "󰇚 –  󰕒 –", tooltip: "No network", class: "disconnected"}'
  exit 0
fi

stats_dir="/sys/class/net/$ifname/statistics"
rx_now=$(<"$stats_dir/rx_bytes")
tx_now=$(<"$stats_dir/tx_bytes")
now=$(date +%s.%N)

state_file="/tmp/waybar-netspeed-${ifname}.state"

rx_rate=0
tx_rate=0
if [[ -f "$state_file" ]]; then
  read -r prev_time prev_rx prev_tx < "$state_file"
  elapsed=$(awk -v a="$now" -v b="$prev_time" 'BEGIN {d=a-b; if (d<=0) d=1; print d}')
  rx_rate=$(awk -v a="$rx_now" -v b="$prev_rx" -v t="$elapsed" 'BEGIN {d=a-b; if (d<0) d=0; printf "%.0f", d/t}')
  tx_rate=$(awk -v a="$tx_now" -v b="$prev_tx" -v t="$elapsed" 'BEGIN {d=a-b; if (d<0) d=0; printf "%.0f", d/t}')
fi

echo "$now $rx_now $tx_now" > "$state_file"

# Whole numbers only in the bar, to keep the module narrow. Every branch is
# padded to the same width (3 digits + 4-char unit) so the bar never reflows
# as the rate crosses a digit or unit boundary.
human() {
  awk -v b="$1" 'BEGIN {
    if (b >= 1073741824)      printf "%3.0f GB/s", b/1073741824
    else if (b >= 1048576)    printf "%3.0f MB/s", b/1048576
    else if (b >= 1024)       printf "%3.0f KB/s", b/1024
    else                      printf "%3d  B/s", b
  }'
}

# Tooltip has the room for finer detail
human_precise() {
  awk -v b="$1" 'BEGIN {
    if (b >= 1073741824)      printf "%.2f GB/s", b/1073741824
    else if (b >= 1048576)    printf "%.2f MB/s", b/1048576
    else if (b >= 1024)       printf "%.2f KB/s", b/1024
    else                      printf "%d B/s", b
  }'
}

rx_h=$(human "$rx_rate")
tx_h=$(human "$tx_rate")

tooltip=$(printf "Interface  %s\nDown  %s\nUp    %s" \
  "$ifname" "$(human_precise "$rx_rate")" "$(human_precise "$tx_rate")")

jq -cn --arg text "󰇚 ${rx_h}  󰕒 ${tx_h}" --arg tooltip "$tooltip" \
  '{text: $text, tooltip: $tooltip}'

#!/usr/bin/env bash
set -uo pipefail

strip_ansi() { sed -r 's/\x1b\[[0-9;]*[mGKH]//g'; }

ifname=$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')

if [[ -z "${ifname:-}" ]]; then
  jq -cn '{text: "󰖪", tooltip: "No network", class: "disconnected"}'
  exit 0
fi

gw=$(ip route show default 2>/dev/null | awk '/default/ {print $3; exit}')
ip_cidr=$(ip -4 -o addr show dev "$ifname" 2>/dev/null | awk '{print $4; exit}')

ping_ms=$(ping -c 1 -W 1 -n "$gw" 2>/dev/null \
  | awk -F'time=' '/time=/ {print $2; exit}' \
  | awk '{printf "%.0f", $1}')
ping_ms=${ping_ms:-–}

# Treat as wifi if iwctl recognises the device
if iwctl device "$ifname" show >/dev/null 2>&1; then
  raw=$(iwctl station "$ifname" show 2>/dev/null | strip_ansi)

  ssid=$(awk -F'  +' '/Connected network/ {print $3; exit}' <<<"$raw")
  freq=$(awk -F'  +' '/Frequency/ {print $3; exit}' <<<"$raw")
  chan=$(awk -F'  +' '/Channel/ {print $3; exit}' <<<"$raw")
  rssi=$(awk -F'  +' '/RSSI/ {print $3; exit}' <<<"$raw" | awk '{print $1}')
  tx=$(awk -F'  +' '/TxBitrate/ {print $3; exit}' <<<"$raw" | awk '{printf "%d Mbps", $1/1000}')

  pct=$(awk -v r="${rssi:-0}" 'BEGIN {p=(r+100)*2; if (p<0) p=0; if (p>100) p=100; printf "%d", p}')

  icons=("󰤯" "󰤟" "󰤢" "󰤥" "󰤨")
  if   (( pct < 20 )); then icon=${icons[0]}
  elif (( pct < 40 )); then icon=${icons[1]}
  elif (( pct < 60 )); then icon=${icons[2]}
  elif (( pct < 80 )); then icon=${icons[3]}
  else                      icon=${icons[4]}
  fi

  band="2.4 GHz"
  [[ "${freq:-0}" -ge 5000 ]] && band="5 GHz"

  tooltip=$(printf "%s  (%s%%, %s ch %s)\nIP    %s\nGW    %s  (%s ms)\nLink  %s" \
    "${ssid:-?}" "$pct" "$band" "${chan:-?}" "${ip_cidr:-–}" "${gw:-–}" "$ping_ms" "${tx:-–}")
  class="wifi"
else
  icon="󰀂"
  tooltip=$(printf "Ethernet  (%s)\nIP    %s\nGW    %s  (%s ms)" \
    "$ifname" "${ip_cidr:-–}" "${gw:-–}" "$ping_ms")
  class="ethernet"
fi

if [[ "$class" == "wifi" ]]; then
  text="$icon  ${pct}%"
else
  text="$icon"
fi

jq -cn --arg text "$text" --arg tooltip "$tooltip" --arg class "$class" \
  '{text: $text, tooltip: $tooltip, class: $class}'

#!/usr/bin/env bash
set -euo pipefail

read -r mem_total mem_avail swap_total swap_free < <(
  awk '
    /^MemTotal:/     {t=$2}
    /^MemAvailable:/ {a=$2}
    /^SwapTotal:/    {st=$2}
    /^SwapFree:/     {sf=$2}
    END {print t, a, st, sf}
  ' /proc/meminfo
)

mem_used=$((mem_total - mem_avail))
to_gib() { awk -v k="$1" 'BEGIN {printf "%.1f", k/1024/1024}'; }
pct()    { awk -v u="$1" -v t="$2" 'BEGIN {if (t==0) print 0; else printf "%.0f", u/t*100}'; }

mem_used_g=$(to_gib "$mem_used")
mem_total_g=$(to_gib "$mem_total")
mem_pct=$(pct "$mem_used" "$mem_total")

swap_used=$((swap_total - swap_free))
swap_used_g=$(to_gib "$swap_used")
swap_total_g=$(to_gib "$swap_total")
swap_pct=$(pct "$swap_used" "$swap_total")

top=$(
  ps -eo comm,rss --sort=-rss --no-headers \
    | awk 'NR<=5 {printf "  %-20s %6.1f GiB\n", $1, $2/1024/1024}'
)

tooltip=$(printf "RAM   %s / %s GiB  (%s%%)\nSwap  %s / %s GiB  (%s%%)\n\nTop processes\n%s" \
  "$mem_used_g" "$mem_total_g" "$mem_pct" \
  "$swap_used_g" "$swap_total_g" "$swap_pct" \
  "$top")

jq -cn --arg text " ${mem_used_g} GB" --arg tooltip "$tooltip" \
  '{text: $text, tooltip: $tooltip}'

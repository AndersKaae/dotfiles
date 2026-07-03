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
  ps -eo pid,rss,comm --no-headers \
    | awk '{pid=$1; rss=$2; sub(/^ *[0-9]+ +[0-9]+ +/, "");
            name=$0
            # comm is kernel-truncated to 15 chars; recover the full name from the executable
            if (length(name) == 15) {
              cmd = "readlink /proc/" pid "/exe 2>/dev/null"
              if ((cmd | getline exe) > 0) {
                sub(/ \(deleted\)$/, "", exe)
                sub(/.*\//, "", exe)
                if (exe != "") name = exe
              }
              close(cmd)
            }
            # LegalDesk instances stay separate (parallel dev servers), everything else aggregates
            key = (name ~ /^LegalDesk/) ? name SUBSEP pid : name
            sum[key]+=rss; disp[key]=name}
           END {for (key in sum) printf "%d\t%s\n", sum[key], disp[key]}' \
    | sort -rn \
    | awk -F'\t' 'NR<=5 {printf "  %-30s %6.1f GiB\n", $2, $1/1024/1024}'
)

tooltip=$(printf "RAM   %s / %s GiB  (%s%%)\nSwap  %s / %s GiB  (%s%%)\n\nTop processes\n%s" \
  "$mem_used_g" "$mem_total_g" "$mem_pct" \
  "$swap_used_g" "$swap_total_g" "$swap_pct" \
  "$top")

jq -cn --arg text " ${mem_used_g} GB" --arg tooltip "$tooltip" \
  '{text: $text, tooltip: $tooltip}'

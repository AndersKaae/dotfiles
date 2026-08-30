#!/usr/bin/env bash
# Claude Code status line: model · dir · git branch · context usage.
# Receives the session JSON payload on stdin; prints one line to stdout.
# Wired up via "statusLine" in ~/.claude/settings.json.

input=$(cat)

# One field per line, so values containing spaces survive.
mapfile -t f < <(
  jq -r '
    (.model.display_name // "claude"),
    (.workspace.current_dir // .cwd // "."),
    (.context_window.used_percentage // -1 | floor),
    (.context_window.total_input_tokens // -1),
    (.context_window.context_window_size // -1),
    (.cost.total_cost_usd // 0)
  ' <<<"$input" 2>/dev/null
)
model=${f[0]:-claude}
dir=${f[1]:-.}
used_pct=${f[2]:--1}
used_tok=${f[3]:--1}
max_tok=${f[4]:--1}
total_cost=${f[5]:-0}

# 1234 -> 1.2k, 123456 -> 123k, 1000000 -> 1M
human() {
  awk -v n="$1" 'BEGIN{
    if (n >= 1000000) { v = n/1000000; u = "M" }
    else if (n >= 1000) { v = n/1000; u = "k" }
    else { printf "%d", n; exit }
    printf (v == int(v) ? "%.0f%s" : (v < 10 ? "%.1f%s" : "%.0f%s")), v, u
  }'
}

# --- colors -----------------------------------------------------------------
r=$'\033[0m'; dim=$'\033[2m'; bold=$'\033[1m'
blue=$'\033[34m'; cyan=$'\033[36m'; magenta=$'\033[35m'
green=$'\033[32m'; yellow=$'\033[33m'; red=$'\033[31m'

# --- git --------------------------------------------------------------------
git_part=""
if branch=$(timeout 0.3s git -C "$dir" --no-optional-locks symbolic-ref --short HEAD 2>/dev/null) \
   || branch=$(timeout 0.3s git -C "$dir" --no-optional-locks rev-parse --short HEAD 2>/dev/null); then
  dirty=""
  timeout 0.3s git -C "$dir" --no-optional-locks diff --no-ext-diff --quiet 2>/dev/null || dirty="*"
  git_part=" ${dim}·${r} ${magenta} ${branch}${dirty}${r}"
fi

# --- context ----------------------------------------------------------------
ctx_part=""
if [[ $used_tok -ge 0 && $max_tok -gt 0 ]]; then
  if   [[ $used_pct -lt 0 || $used_pct -lt 50 ]]; then ctx_color=$green
  elif [[ $used_pct -lt 75 ]];                    then ctx_color=$yellow
  else                                                 ctx_color=$red
  fi
  ctx_part=" ${dim}·${r} ${ctx_color}$(human "$used_tok")${r}${dim}/$(human "$max_tok") ctx${r}"
fi

# --- cost -------------------------------------------------------------------
cost_part=""
if [[ $(awk -v c="$total_cost" 'BEGIN{print (c>=0.01)?1:0}') == 1 ]]; then
  cost_part=$(printf ' %s·%s %s$%.2f%s' "$dim" "$r" "$dim" "$total_cost" "$r")
fi

printf '%s%s%s %s·%s %s%s%s%s%s%s' \
  "$bold$blue" "$model" "$r" \
  "$dim" "$r" \
  "$cyan" "$(basename "$dir")" "$r" \
  "$git_part" "$ctx_part" "$cost_part"

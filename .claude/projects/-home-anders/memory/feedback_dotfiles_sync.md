---
name: Keep dotfiles in sync with Claude state
description: Always check dotfiles are up to date at session start and periodically commit changes during work
type: feedback
---

At the start of each session, check if the dotfiles repo is on the latest version (git pull). Periodically during work, commit and push changes to the dotfiles repo when memory files or settings are updated.

**Why:** Claude state files (memory, settings) are managed via git in ~/dotfiles and stowed to ~/.claude. Keeping them synced ensures consistent context across machines and sessions.

**How to apply:** 1) At session start: `cd ~/dotfiles && git pull` 2) After updating memory or settings: `cd ~/dotfiles && git add .claude && git commit -m "Update Claude memory" && git push`

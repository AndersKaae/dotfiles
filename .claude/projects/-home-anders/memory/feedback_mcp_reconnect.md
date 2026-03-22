---
name: Re-check state after MCP reconnection
description: Always verify current element state after losing and regaining Webflow Designer MCP connection to avoid duplicates
type: feedback
---

After losing and regaining the Webflow Designer MCP connection, always re-check the current state of elements before making changes. Get fresh element data and verify what exists before creating new elements.

**Why:** MCP timeouts can happen mid-operation. The operation may have partially succeeded, and re-running it without checking creates duplicates (e.g. duplicate social buttons, duplicate headings, duplicate component instances).

**How to apply:** After any MCP timeout/reconnection: 1) Get fresh elements list, 2) Verify what was created vs what's missing, 3) Only create what's actually needed.

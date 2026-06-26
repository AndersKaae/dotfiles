---
name: task-figma
description: Audit and fix a UI's compliance against a Figma design, screen by screen, with evidence-backed element-by-element comparison and a side-by-side comparison artifact. Use when the user points at a Figma file/frame and asks to "make our design compliant", "check this against Figma", "match the design", "is this pixel-perfect", or to implement/QA a design. Covers the WHOLE file, not one node, and never declares a match from memory.
---

# Task Figma — design-compliance workflow

An eight-phase loop for making an implementation compliant with a Figma design. It exists to defeat two specific, recurring failure modes:

1. **Scoping to one node when asked about the whole file.** A Figma "Navigation" / "Checkout" file has many frames (desktop, mobile, hover/expanded states, breakpoints). Auditing the one node in the URL and calling it done silently drops most of the design.
2. **Declaring a match from memory.** Building a mental checklist of Figma elements and ticking them ✓ against what you *expect* the render to be — instead of looking at the real render and the real computed styles — passes broken things as compliant. Every ✓ must come from evidence.

Run the phases in order. The comparison artifact (Phase 6) is the deliverable that lets the user catch your misses in seconds instead of describing each one.

This skill reuses `task-tdd`'s infrastructure (worktree off `develop`, `ld-dev-server`, full-suite gates, commit hygiene, teardown prompt). Where those steps recur, they're referenced, not repeated.

## Phase 1: Enumerate the whole design — don't trust the single node

The URL names one node; the *file* is the scope unless the user says otherwise. Build a complete inventory of frames/screens/states before writing any code.

- `mcp__claude_ai_Figma__get_metadata` with no `nodeId` lists top-level pages; with a page id lists its frames.
- **Known limitation: the Figma MCP often truncates the file tree** — listing the file returns only a "Cover" page, and a page's metadata returns only the frame at the origin. A screenshot of the page node renders just the cover. So you frequently **cannot** auto-discover the other frames.
- When that happens, **ask the user** to enumerate: in Figma, right-click each frame → **Copy link to selection** → paste the URLs (each carries `?node-id=`). Don't guess node IDs.
- Cross-reference the codebase: list the components that plausibly back this design area (e.g. `grep` the nav/checkout components) so the inventory is "every design frame ↔ every component", with gaps visible.

Produce an explicit **screen inventory**: each row = a Figma frame (name + node id) × each state (logged-in/out, breakpoint, hover/expanded). Confirm scope with the user via `AskUserQuestion` (whole file vs one screen vs a subset). The audit is not "done" until every row has a verified section — never narrow scope silently.

## Phase 2: Map each frame to a component, route, and state

For every inventory row, identify:
- The exact component file that renders it (`file:line`).
- How to drive the live app into that state: route/URL, auth context (member vs anonymous vs admin), viewport/breakpoint, and any interaction (open menu, hover, expand).
- The data the state needs (a logged-in member with a display name + email, a basket with items, etc.).

If a frame has no corresponding component, that's a finding (unbuilt screen), not a skip.

## Phase 3: Worktree + dev server

Per `task-tdd` Phase 4 and the `ld-dev-server` skill:
- Worktree off `origin/develop`: `git worktree add ../<repo>-figma-<area> -b figma-<area>-compliance origin/develop`.
- Cold worktree: symlink `node_modules` from the primary checkout for `src/LegalDesk.VueComponents` **and** `tests/e2e` (avoids the Yarn-berry lockfile rewrite and a slow install), copy `tests/e2e/.env.local`.
- Lease an isolated instance with `ld-dev-server` (never bare `dotnet run`). Note the leased `$URL` / port.

## Phase 4: Capture evidence for each screen — Figma side and live side

For each inventory row, gather **both**:

**Figma side.**
- `get_screenshot` of the frame node (download the returned URL with `curl`, then `Read` the PNG).
- `get_design_context` and/or `get_variable_defs` for exact tokens (font family/size/weight, color hex, line-height, spacing, radii). These are the spec you compare against.

**Live side.**
- Drive the app into the state with Playwright at the **design's native viewport** (e.g. 390 px for a mobile frame; use a mobile device profile + `deviceScaleFactor` on mobile). A throwaway spec under `tests/e2e/tests/...` run with `--no-deps --project=<mobile project>` and `E2E_SKIP_LOCAL_FIXTURES=1` is the fastest path; reuse helpers like `loginMember`. **Delete the throwaway spec before committing.**
- Take a screenshot, **and** dump computed styles + asset status via `page.evaluate`:
  ```js
  const cs = getComputedStyle(el);              // fontFamily, fontSize, fontWeight, color, lineHeight
  const broken = img.complete && img.naturalWidth === 0;  // a referenced asset that 404s
  ```
  Computed styles are how you catch font/size/color drift objectively; `naturalWidth === 0` is how you catch missing/broken assets instead of hand-waving them.

## Phase 5: Compare element-by-element — from evidence, never memory

For each screen, walk **every** element in the Figma frame top to bottom and record a status backed by evidence:

- **Match** — render + computed style agree with the Figma spec.
- **Mismatch / Fixed** — they differ (and what you changed).
- **Unverified (❓)** — you could not confirm it (asset not loadable in this env, state not reachable). Mark it ❓; **do not** tick ✓.
- **Caveat** — differs for a non-code reason (CMS content text, env-only data). Say so explicitly.

Discipline that prevents the recurring misses:
- **Resolve tokens against the project's own system before declaring a color/spacing mismatch.** A class like `text-primary-900` may map to the exact Figma hex via `tailwind.config.js`. Check the config; a "wrong color" is often a false alarm. (Equally, confirm the token actually resolves — don't assume.)
- **A missing element is the easiest thing to miss.** Explicitly check presence of every Figma element in the DOM. The classic trap: a logged-in-only CTA that exists in the design but was never rendered.
- **Treat "probably an environment artifact" as a bug until proven otherwise.** Broken images, absent data, "it works in prod" — verify with `naturalWidth`, `git log -S`, and a search for the asset. A never-shipped asset path looks identical to a missing-media env quirk.

## Phase 6: Build the side-by-side comparison artifact

This is the core deliverable — it makes discrepancies visible at a glance so the user can catch what you missed.

- **The artifact must always contain EVERY view from the Figma file — no exceptions.** It has one section per row of the Phase 1 inventory, period. A view you've audited shows its side-by-side + checklist; a view you haven't yet shows the Figma export with a **Pending** status and the reason (e.g. awaiting node URL, state not reachable). The document is a complete map of the design at all times, not just the slice you finished. If a Figma view is absent from the artifact, the artifact is wrong — the user must never have to wonder whether a screen was considered. Keep the artifact and the inventory in lockstep: every view appears, and the summary counts reconcile to the inventory total.
- Use the `Artifact` tool (load the `artifact-design` skill first; treat this as a polished but utilitarian QA/info-design page, not a flashy landing page).
- Per screen: two columns — **Figma export | live render** — above a per-element checklist table (Element · Figma spec · Status). Status pills color-coded: match / fixed / caveat / unverified / pending.
- A **"Not yet audited"** section collects every inventory row still at Pending, plus the ask for any missing node URLs. Honesty about coverage is part of the deliverable — but Pending views still appear with their Figma export, never as a bare list item with nothing to look at.
- **Inline every image as a `data:` URI** (base64) — the artifact CSP blocks external hosts, so Figma asset URLs and local screenshots both must be embedded. A small Python step that replaces `{{TOKEN}}` placeholders with `data:image/png;base64,...` keeps the HTML readable.
- Redeploy the same file (same artifact URL) as you add screens.

## Phase 7: Fix each discrepancy — smallest change, then re-verify

- The smallest change that makes the element match. Resist "while I'm here" refactors.
- **Missing assets:** extract them from Figma with `download_assets` (`defaultFormat: svg`). The export wraps the asset in the surrounding frame backgrounds — **strip it down** to just the target group (e.g. the flag circle), wrap in a clean `0 0 W H` viewBox. If the design system lacks a needed variant (e.g. a DK flag the file omits), author it in the same style/palette as its siblings. Commit static assets under a **tracked** static path (`wwwroot/css/img_new/...`) — **not** `wwwroot/media` (Umbraco-managed and git-ignored) — and repoint the code.
- After Vue edits, **rebuild the bundle** (`vite build` / `yarn build`) — the live app and e2e consume the built artifact, not your source.
- Re-capture the live screenshot and recompute styles to confirm the fix, and update the artifact row to ✅.

## Phase 8: Gates, commit, teardown

- **Full regression gates** (per `task-tdd`): `dotnet test` if backend touched, `yarn test` (jest) if VueComponents touched, the relevant e2e spec(s) if runtime behavior changed. Name which you ran; don't silently narrow.
- **Commit hygiene:** focused commits with `Task`/area prefix; commit rebuilt artifacts and any new design assets; revert server-regenerated drift (e.g. `appsettings-schema.*`). The Vue bundle under `wwwroot/scripts/vue` is git-ignored — don't commit it. `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Don't open the PR unless asked** (Azure DevOps repo — `az repos pr create`, not `gh`). Provide the command + web fallback.
- **Prompt to tear down** the leased server + worktree once the PR exists (stop background tasks → release lease → decide on the DB clone → `git worktree remove`).

## Anti-patterns this skill exists to stop

- "The URL points at one node, so that's the scope." — No: audit the file; enumerate first.
- "I checked the Figma element list, looks compliant." — You checked your *memory*. Put the export next to the render and read computed styles.
- "Ticked ✓" for something you didn't actually observe. — Unverified is ❓, not ✓.
- "The flags are just broken in my env." — Prove it (`naturalWidth`, `git log -S`, asset search) before dismissing; it was a never-shipped asset.
- "The color's wrong." — Resolve the class against `tailwind.config.js` first; it's often the right token.

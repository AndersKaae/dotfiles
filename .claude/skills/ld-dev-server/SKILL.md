---
name: ld-dev-server
description: Spin up (or reuse) a local LegalDesk-V2 dev site without port/database collisions. Use whenever you need a RUNNING server to reproduce, diagnose, screenshot, or test a change in the live app — and ESPECIALLY when another server may already be running (parallel instances). Leases an isolated port + its own clone of UmbracoDb via the pool allocator instead of a bare `dotnet run`.
---

# Running a LegalDesk-V2 dev site (parallel-safe)

**Never start the site with a bare `dotnet run`.** The committed `launchSettings.json`
hardcodes port `44333` and the shared `UmbracoDb`, so it collides with any server already
running, and two branches sharing one database corrupt each other's EF migrations on startup.

Instead, lease an isolated slot. The allocator picks a free port, gives you your own database
clone, reuses idle clones, parks unused ones to save RAM, and never hands out a taken port.

## 1. Lease a slot

```bash
cd /home/alk/projects/Legaldesk-V2-Database
eval "$(scripts/lease-db.sh)"
```

This sets `INSTANCE`, `PORT`, `HTTP_PORT`, `URL`, `DATABASE`, `CONNSTRING` in your shell and
guarantees the database exists and is online. If it prints **`POOL EXHAUSTED`**, all slots are
in use — stop and report; do not force a port.

## 2. Launch the site (background it, then poll)

```bash
scripts/run-instance.sh "$INSTANCE" <path-to-your-worktree> &
```

Then poll `"$URL"` until it returns 200 — cold start is ~45 s, up to 2–3 min if the worktree
still needs building. Your site is at `$URL` (e.g. `https://localhost:44334`).

## 3. Release when finished

```bash
scripts/lease-db.sh --release "$INSTANCE"
```

(If you forget, the lease self-expires in 10 min — but release explicitly when you can.)

## Rules & gotchas

- **One instance per worktree.** Two sites from the same checkout collide on
  `App_Data`/NuCache/Examine. If you don't have your own worktree, create one first
  (see the `task-tdd` skill / git worktree setup).
- `scripts/lease-db.sh --status` shows the current pool.
- `scripts/ensure-db.sh --connections N` checks whether a slot is actually in use before any
  destructive DB op (re-clone/offline force-kills connections).
- Each warmed site uses ~2.6 GB RAM; the box is RAM-tight until a hardware upgrade — don't run
  more instances than you need.
- Full reference (env knobs, all scripts): `/home/alk/projects/Legaldesk-V2-Database/scripts/README.md`.

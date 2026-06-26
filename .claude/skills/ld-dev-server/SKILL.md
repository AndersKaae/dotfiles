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
export INSTANCE PORT HTTP_PORT URL DATABASE CONNSTRING   # so child processes (e.g. lease-test.sh) inherit the lease
```

This sets `INSTANCE`, `PORT`, `HTTP_PORT`, `URL`, `DATABASE`, `CONNSTRING` in your shell and
guarantees the database exists and is online. If it prints **`POOL EXHAUSTED`**, all slots are
in use — stop and report; do not force a port.

## 2. Launch the site (background it, then poll)

**Redirect the server's output to a disk-backed log — never let it stream into the default
capture path.** `/tmp` here is a RAM-backed tmpfs (~15 GB), and a backgrounded `&` with no
redirect dumps the dev server's entire (unbounded) log into the Bash tool's capture file on
that tmpfs. Left running, it fills `/tmp`, after which *every* shell command fails its
output-capture write and returns a bare `exit 1`. Send the log to `$HOME` (a real disk) instead:

```bash
LOG="$HOME/.cache/ld-dev-logs/instance-$INSTANCE.log"; mkdir -p "$(dirname "$LOG")"
scripts/run-instance.sh "$INSTANCE" <path-to-your-worktree> > "$LOG" 2>&1 &
```

The `>` truncates the log each launch, so it stays bounded to one run on a roomy filesystem.
Then poll `"$URL"` until it returns 200 — cold start is ~45 s, up to 2–3 min if the worktree
still needs building (watch boot progress with `tail -f "$LOG"`). Your site is at `$URL`
(e.g. `https://localhost:44334`).

## Running e2e tests against your instance

The Playwright harness targets `BASE_URL`, which defaults to `https://localhost:44333`
(pinned in `tests/e2e/.env.local`). Your leased site is on a **different** port, so you must
point the run at `$URL` — otherwise the suite silently tests whatever sits on 44333 (often a
*different* leased instance) and a confusing **subset** of specs fail.

**Pass the port inline — never `export BASE_URL`.** `BASE_URL` is a single process-global; a
global export (or editing `.env.local`) makes parallel instances clobber each other. The inline
form scopes the port to that one command, so each leased shell stays isolated:

```bash
cd <your-worktree>/tests/e2e
BASE_URL="$URL" npx playwright test <specs...>
```

This works even with `.env.local` pinning 44333: the inline var is set before Playwright loads
`.env.local`, and `dotenv` does not override an already-set var, so `$URL` wins. After a server
restart, re-run `--project=setup` before `--no-deps` specs (auth storage-state is invalidated).

Convenience wrapper (reads the current shell's lease, run from your worktree root):

```bash
/home/alk/projects/Legaldesk-V2-Database/scripts/lease-test.sh <specs...>   # = BASE_URL="$URL" npx playwright test
```

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

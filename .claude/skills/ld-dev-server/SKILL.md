---
name: ld-dev-server
description: Spin up (or reuse) a local LegalDesk-V2 dev site without port/database collisions. Use whenever you need a RUNNING server to reproduce, diagnose, screenshot, or test a change in the live app — and ESPECIALLY when another server may already be running (parallel instances). Leases an isolated port + its own clone of UmbracoDb via the `lddev` pool allocator instead of a bare `dotnet run`.
---

# Running a LegalDesk-V2 dev site (parallel-safe)

**Never start the site with a bare `dotnet run`.** The committed `launchSettings.json`
hardcodes port `44333` and the shared `UmbracoDb`, so it collides with any server already
running, and two branches sharing one database corrupt each other's EF migrations on startup.

Instead lease an isolated slot with `lddev`. The allocator picks a free port, gives you your own
**pristine** database clone, parks unused ones to save RAM, and never hands out a taken port.

```bash
make -C ~/projects/Legaldesk-V2-Database lddev      # idempotent, ~1s; do this first
LDDEV=~/projects/Legaldesk-V2-Database/bin/lddev
```

The binary is gitignored, so build it before use — it also warns if it is older than its source.
Use the `$LDDEV` path form in commands: it works regardless of PATH, which a `lddev` on PATH does
not (`make install` symlinks it into `~/.local/bin`, but that directory may not be on the PATH of
the shell you are given). `$LDDEV help` and `$LDDEV help states` are the authoritative reference;
this skill is the recipe.

## 1. Look before you leap

```bash
$LDDEV list
```

One line per slot: state, owner, how long held, how long that agent has been idle, worktree — plus
what the next lease will take. Read it first: it tells you whether you are about to join a queue.
Add `--why` when you need the reasoning behind a verdict rather than the verdict itself.

## 2. Lease a slot

```bash
eval "$($LDDEV lease --purpose 'task 10880 repro' --worktree <path-to-your-worktree>)"
export INSTANCE PORT HTTP_PORT URL DATABASE CONNSTRING   # so child processes inherit the lease
```

This sets `INSTANCE`, `PORT`, `HTTP_PORT`, `URL`, `DATABASE`, `CONNSTRING` and guarantees the
database exists and is online. `--purpose` is what makes your slot legible to everyone else in
`$LDDEV list` — always pass it. Ownership (your session id + pid) is recorded automatically.

The clone is reset from base `UmbracoDb` at lease time, so you never inherit the previous task's
members/drafts/orders and you never clean up on the way out. Budget ~50 s for it on top of the
site's cold start. If you are re-leasing a slot mid-task and need its data (expensive seeded
fixtures) to survive, lease with `--reuse`. *Restarting* a site is not a re-lease — `lddev run`
takes the instance number — so rebuild/restart loops never reset anything.

### If every slot is taken, you get queued — you do not get rejected

The allocator parks your request in a FIFO queue and re-checks every 5 s until a slot frees up,
so a full pool is a wait, not a failure. Never force a port and never edit `launchSettings.json`
to get around it. One consequence for you: **a queued lease can outlive a single Bash tool call**
(they cap at 10 min; the queue waits up to 1 h), so don't block a foreground call on it —
background it and collect it when it lands:

```bash
LEASEFILE="$HOME/.cache/lddev-lease-$$.env"
$LDDEV lease --purpose '<why>' > "$LEASEFILE" 2> "$LEASEFILE.log" &
# poll (with an explicit upper bound) until INSTANCE= appears; tail the .log for queue position
eval "$(cat "$LEASEFILE")"; export INSTANCE PORT HTTP_PORT URL DATABASE CONNSTRING
```

### Reclaiming happens for you — don't do it by hand

While you are queued, the allocator frees slots on your behalf:

- `DEAD` and `ABANDONED` — provably unused (nothing running, or the session that leased it no
  longer exists). Freed on sight.
- `IDLE-SUSPECT` — owner session alive but silent for over 10 minutes with no traffic to its port.
  **Evicted for you**, because a slot sitting idle while agents queue is the more expensive
  mistake. Only under real contention (you are at the head of the queue and nothing is free).

So **do not run `reclaim` yourself, and do not ask the user for permission to take a slot** — just
lease and let the queue do its job. `ACTIVE` and `STARTING` slots are never taken. Reach for
`$LDDEV kill <N>` only if the user explicitly asks you to clear a specific slot.

If the pool is genuinely all `ACTIVE`, growing it beats waiting: `LD_MAX_INSTANCES=5 $LDDEV lease`.
When every slot is busy, `list` says so and prints current free RAM — check it, because each warmed
site is ~2.6–3.6 GB and this box has run at 57 of 60 GB used. `list` shows the configured pool
(`1..LD_MAX_INSTANCES`); a slot number beyond that is not part of the pool.

### If YOUR site suddenly stops responding

It may have been evicted, not crashed. Any `lddev` command tells you so:

```
[lddev] NOTE: your slot 3 was reclaimed 4m ago — it had been idle 22m with no traffic...
```

Don't debug it. Lease again (`$LDDEV lease`), relaunch, and carry on — the slot's database was
reset, so re-seed anything your task had set up. `$LDDEV evictions` shows the full recent history.
To avoid it while doing something long that doesn't touch the server (a big build, a subagent
fan-out), just keep the lease legible: work that hits `$URL` counts as traffic and protects the
slot automatically.

## 3. Launch the site (background it, then poll)

**Redirect the server's output to a disk-backed log — never let it stream into the default
capture path.** `/tmp` here is a RAM-backed tmpfs (~15 GB), and a backgrounded `&` with no
redirect dumps the dev server's entire (unbounded) log onto it. Left running, it fills `/tmp`,
after which *every* shell command fails its output-capture write and returns a bare `exit 1`.
Send the log to `$HOME` (a real disk) instead:

```bash
LOG="$HOME/.cache/ld-dev-logs/instance-$INSTANCE.log"; mkdir -p "$(dirname "$LOG")"
$LDDEV run "$INSTANCE" <path-to-your-worktree> > "$LOG" 2>&1 &
```

The `>` truncates the log each launch, so it stays bounded to one run. Then poll `"$URL"` until
it returns 200 — cold start is ~45 s, up to 2–3 min if the worktree still needs building (watch
with `tail -f "$LOG"`). Your site is at `$URL` (e.g. `https://localhost:44334`).

`lddev run` stays the parent of `dotnet run` and heartbeats your lease every 60 s, so a slot whose
site is merely rebuilding is no longer mistaken for an abandoned one. Keep it running for the life
of the site; if you must restart, run it again with the same `$INSTANCE`.

## 4. Running e2e tests against your instance

The Playwright harness targets `BASE_URL`, which defaults to `https://localhost:44333` (pinned in
`tests/e2e/.env.local`). Your leased site is on a **different** port, so you must point the run at
`$URL` — otherwise the suite silently tests whatever sits on 44333 (often a *different* leased
instance) and a confusing **subset** of specs fails.

**Pass the port inline — never `export BASE_URL`.** It is a single process-global; a global export
(or editing `.env.local`) makes parallel instances clobber each other.

```bash
cd <your-worktree>/tests/e2e
BASE_URL="$URL" npx playwright test <specs...> -- --workers=2
```

Or use the wrapper, which reads the current shell's lease (run from your worktree root):

```bash
$LDDEV test <specs...>          # = BASE_URL="$URL" npx playwright test
$LDDEV test --instance 3 <specs...>   # when $URL isn't in this shell
```

This works even with `.env.local` pinning 44333: the inline var is set before Playwright loads
`.env.local`, and `dotenv` does not override an already-set var. After a server restart, re-run
`--project=setup` before `--no-deps` specs (auth storage-state is invalidated).

## 5. Release when finished

```bash
$LDDEV teardown "$INSTANCE"
```

Use `teardown` whenever you actually launched a site: it stops the process, offlines the clone to
free SQL memory, clears the lease, and stops the SQL container if the pool went fully idle.
`$LDDEV release "$INSTANCE"` only clears the lease record and leaves the site running — use it
only when you did not start a server. Either way, **do not re-clone the database on the way out**;
the next lease does that for you. Nothing to decide and nothing to ask.

## Rules & gotchas

- **One instance per worktree.** Two sites from the same checkout collide on
  `App_Data`/NuCache/Examine. If you don't have your own worktree, create one first
  (see the `task-tdd` skill / git worktree setup).
- `$LDDEV list` / `$LDDEV status` show the pool and the queue; `$LDDEV list --json` for scripting.
- `~/projects/Legaldesk-V2-Database/scripts/ensure-db.sh --connections N` checks whether a slot is
  really in use before any destructive DB op (re-clone/offline force-kills connections).
- Never broad-`pkill` a dev server (`pkill -f LegalDesk.Website` kills other agents' servers *and*
  your own shell). Kill by pid from `ss -ltnp`, or use `teardown`.
- The bash allocator (`scripts/lease-db.sh`, `scripts/run-instance.sh`, `scripts/lease-test.sh`) is
  still supported and shares the same state, so a lease taken either way is respected by both. Use
  `lddev` unless you have a specific reason not to: slots leased by the scripts record no owner,
  show as `UNATTRIBUTED`, and can never be reclaimed automatically when forgotten.
- Full reference: `~/projects/Legaldesk-V2-Database/CLAUDE.md`, `scripts/README.md`, and
  `cmd/lddev/README.md`.

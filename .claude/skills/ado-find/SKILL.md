---
name: ado-find
description: Search the Azure DevOps backlog for work items matching a shape — unassigned, created by someone, matching text, or "TDD-shaped" (specific enough to write a failing test from) — reading the body field that actually holds the text and verifying the code each ticket names still exists. Use when the user asks "any unassigned tasks", "what can I pick up", "find tasks with a TDD shape", "what did <person> file", "is there a ticket for X", "anything worth working on", or wants the backlog filtered by anything other than assignment to themselves.
---

# Backlog search

Finds work items by shape and ranks them by whether you could actually start one.
Companion to `ado-cleanup`, which sweeps *your own* PRs and tickets; this one
searches the backlog generally, most often the part nobody owns yet.

## The field trap — read this first

**A Bug in the Legal Desk project stores its body in
`Microsoft.VSTS.TCM.ReproSteps`, not `System.Description`.**

`System.Description` on a Bug is usually empty. Query only that field and every
Bug in the backlog looks like a blank ticket, which makes the best-specified
work in the queue invisible and produces a confident, wrong conclusion:
"nothing here is actionable, the team files tickets without detail."

This is not hypothetical. It happened: nine consecutive backlog scans reported
"all 29 of Visti's bugs have empty descriptions" when every one of them had a
real repro with URLs and expected behaviour. The reporter was doing their job
properly the whole time.

So: always read **all** body fields and take the longest.

| Field | Holds the body for |
|---|---|
| `Microsoft.VSTS.TCM.ReproSteps` | **Bug** |
| `System.Description` | Task, Feature, User Story, Epic |
| `Microsoft.VSTS.Common.AcceptanceCriteria` | sometimes the real spec on a Feature |
| `Microsoft.VSTS.TCM.SystemInfo` | environment notes on a Bug |

`scripts/ado-find.py` does this. If you query the REST API by hand instead,
request every field above, or you will repeat the mistake.

## Usage

```bash
# the common one: unowned work you could actually test-drive
python3 ~/.claude/skills/ado-find/scripts/ado-find.py --unassigned --tdd

# everything unowned, nothing filtered out, so you can judge for yourself
python3 ~/.claude/skills/ado-find/scripts/ado-find.py --unassigned --min-score 0

# what did someone file lately, regardless of who owns it now
python3 ~/.claude/skills/ado-find/scripts/ado-find.py --created-by visti@legaldesk.dk --since 2026-09-14

# is there already a ticket for this?
python3 ~/.claude/skills/ado-find/scripts/ado-find.py --text 'hreflang|canonical' --include-done

# read the repros without opening a browser
python3 ~/.claude/skills/ado-find/scripts/ado-find.py --unassigned --tdd --show-body 600
```

Useful flags: `--assigned-to me`, `--type Bug`, `--since YYYY-MM-DD`
(default `2026-01-01` — V2 work starts in 2026, earlier items are V1/V8),
`--include-done`, `--json`, `--limit`, `--no-verify`.

Read-only. Auth is the PAT in `~/azure.key`.

## What the score means

Points for naming code, giving a repro URL, stating wrong-vs-right behaviour,
and having real detail. Penalties for an empty body, pure visual/CSS wording,
container types, `(Pass)` audit records, and V1-port dumps. `--tdd` keeps
score >= 4.

**The score is a sieve, not a verdict.** It ranks how *writable* a ticket is, and
it cannot tell you whether the work is worth doing. Always read the top rows
before recommending one.

## Judgement the script can't do

Check these by hand before you hand someone a candidate:

- **Is it already fixed?** Colleagues ship without linking the work item.
  `git log --all --grep '<id>'`, and search for the symptom in the code — a
  ticket saying "X resolves by name" is void if the line now resolves by id.
  Read the *whole* ticket first: a two-paragraph report can have one half fixed
  and one half open.
- **Does the repro point at V2?** `www.legaldesk.dk` is V1 production.
  `dev.legaldesk.dk` / `dev.jurio.com` are V2. A V1-only repro is not yet a V2
  bug however plainly the shared code exists in both trees.
- **Is it a content fix wearing a code ticket?** Empty pickers, a coupon on a
  soft-deleted discount, missing CMS properties. Flag these; never fix authored
  content with code.
- **Does the ticket say not yet?** Some carry an explicit "deferred until V2 is
  live" — well-specified and still the wrong thing to start.
- **Is it a duplicate?** Near-identical titles from different reporters are
  common. Compare against open items before recommending.
- **Would the fix be a bulk refactor?** A broad convention change has no red-green.

The `Named files NOT found` list at the bottom of the output is the fastest
staleness signal: a ticket pointing at a path that no longer exists is either
already fixed, or describing a different repo.

## Reporting back — a table, not an essay

**The answer is a table.** Do the judgement work above, then put its conclusions
in columns. Do not narrate the candidates one by one, do not give each its own
heading, and do not paste code blocks from the source — put the file:line in the
cell and let the reader open it.

Rank best-first and use exactly these columns:

| # | id | title | why testable | caveat |
|---|---|---|---|---|
| 1 | 11406 | DocumentStep index not static | `wizardStore.ts:360` indexes visible steps, not authored; `wizardStore.datalayer.test.ts` already asserts documentStep | — |
| 2 | 11425 | Hylleselskap charged VAT | repro on dev.jurio.com, only addon should be taxed | need the NO VAT rule to assert a number |

**The id column is a bare number, never a markdown link.** The id is what gets
typed into a branch name, a commit message and `/task-tdd`; a link makes it
something to click instead of something to copy. Same in prose — write "11406",
not a hyperlink.

- **why testable** — the seam, in one clause: the file:line that's wrong, or the
  existing test file to extend. If you can't name one, it doesn't belong here.
- **caveat** — the single thing that would stop someone starting, from the
  judgement list: V1-only repro, duplicate of #X, content fix, deferred, bulk
  refactor, needs a decision from the user. `—` when genuinely clear.

Around the table: one line before it naming the top pick, and at most three
lines after it for ruled-out items (grouped, with ids, not one per line). That
is the whole response. Anything else — the score column, body excerpts, commit
hashes proving a thing isn't fixed — goes only if asked.

If nothing changed since the last run, say so in one line and re-print the table.
If the same query comes up dry more than twice, the filter is wrong; say so and
offer to change it rather than running it again.

When a ticket is good except for a missing detail, the useful move is often to
go get the detail — reproduce it on a dev server and write the repro into the
ticket — rather than to report it as unusable.

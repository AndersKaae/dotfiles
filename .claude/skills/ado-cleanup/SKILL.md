---
name: ado-cleanup
description: Sweep Azure DevOps for cleanup work — a table of your own open pull requests classified by what is actually blocking each one (merge conflicts, unresolved review comments, failed tests, green-and-approved-but-unmerged), plus the work items assigned to you judged as genuinely open or merely forgotten. Offers a checklist and dispatches agents to fix conflicts, answer review comments, and close shipped tasks back to their creator. Use when the user asks to "clean up devops", "what's blocking our PRs", "which PRs are ready to merge", "PR status", "are my tasks still open", "did we forget to close anything", or wants a sweep of outstanding PRs and tickets.
---

# PR board

One read-only sweep of **the user's own** open PRs, bucketed by the single thing
standing between each one and `develop`. The point is to turn "we have a pile of
open PRs" into "these three need a rebase, these two need you to answer Biraj,
and this one has been green and approved for eleven days."

**Scope is the user's PRs, always.** The board filters to `AZDO_USER`
(`anders@legaldesk.dk`) by default. A colleague's PR is not the user's cleanup
work — we cannot rebase it, cannot answer its threads, and must not merge it, so
listing it only adds an "MERGE IT" the user will act on for someone else's
branch. `--all-authors` exists for the rare "what is the whole team sitting on"
question; never reach for it on an ordinary sweep, and when it is used, say
explicitly that the colleagues' rows are report-only.

## Run it

```bash
python3 ~/.claude/skills/ado-cleanup/scripts/ado-cleanup.py
```

That is the whole happy path — ~1s, no arguments, prints a markdown table plus a
per-bucket breakdown. Show the user the table; don't paraphrase it into prose.

| flag | effect |
|---|---|
| `--json` | raw rows, for filtering or follow-up analysis |
| `--drafts` | include draft PRs (excluded by default — a draft is not waiting on anyone) |
| `--author thamis` | override whose PRs — substring on display name or email |
| `--all-authors` | drop the owner filter entirely (report-only; see above) |
| `--bucket ready` | one bucket only |

Defaults come from env vars, so the script works on any ADO repo:
`AZDO_ORG` (`legaldesk`), `AZDO_PROJECT` (`Legal Desk`), `AZDO_REPO`
(`LegalDesk-V2`), `AZDO_USER` (`anders@legaldesk.dk`), `AZDO_PAT` (falls back to
`~/azure.key`). The table header names the scope it ran under — read it before
quoting a count.

## The buckets, in priority order

A PR is listed under its most urgent blocker, but the **Blocked by** column shows
*every* blocker — a PR routinely has a red build and an open thread at once.

| bucket | meaning | what to do |
|---|---|---|
| `ready` | build green, `legaldesk/unit-tests` green, ≥1 approval, no conflicts | **merge it** — nothing is blocking it but attention |
| `e2e-only` | approved, unit-tests gate green, build red **only** in an E2E stage | judgement call, see below |
| `conflicts` | `mergeStatus == conflicts` | rebase on `develop` |
| `failed` | build red in a stage that is not E2E (i.e. the real gate broke) | fix the code |
| `comments` | ≥1 review thread still `active` or `pending` | answer and resolve the threads |
| `changes-requested` | a reviewer voted −5 or −10 | address the reviewer |
| `needs-review` | green but zero approvals | chase a reviewer |
| `stuck-queue` | build queued/running >12h | the agent pool is backed up, not the PR |
| `running` | build in flight <12h | wait |

### `ready` is reported, never merged for you

The skill never completes a PR. `MERGE IT` is an instruction to the user, not an
action on the checklist — say so when the bucket is non-empty, so the imperative
does not read as something that was silently skipped.

Watch for a `ready` row that also says **auto-complete on**. That PR should have
merged itself; if it is still sitting there days later, a blocking policy is
parked at `pending` (a canceled or never-queued build posts `pending` and then
403s the completion) and nobody is coming to fix it. Treat an aged
auto-complete-on row as a thing to diagnose, not a thing to merge — read its
policy evaluations before telling the user it is ready:

```bash
PAT=$(tr -d '\n' < ~/azure.key); ORG=https://dev.azure.com/legaldesk
curl -s -u :"$PAT" "$ORG/Legal%20Desk/_apis/policy/evaluations?artifactId=vstfs:///CodeReview/CodeReviewId/<PROJECT_ID>/<PR_ID>&api-version=7.1-preview.1"
```

### `e2e-only` is the bucket that matters here

Two blocking policies guard `develop` (verified 2026-09-15, policy config ids 14
and 15):

- **Build** — `PR-CI: Unit Tests + E2E`, definition 35, `isBlocking: true`
- **Status** — `legaldesk/unit-tests`, `isBlocking: true`, `invalidateOnSourceUpdate: false`

The E2E suite is *intended* to report rather than gate, but because the whole
build is one blocking policy, a flaky E2E stage still holds the PR shut even when
the unit-test gate is green. That is why `e2e-only` exists as its own bucket: it
separates "this branch is broken" from "E2E flaked again."

> This contradicts the repo `CLAUDE.md`, which says the Build-validation policy is
> deliberately *not* used. It is in place and blocking. Read the live policy, not
> the doc:
> ```bash
> curl -s -u :"$(tr -d '\n' < ~/azure.key)" \
>   "https://dev.azure.com/legaldesk/Legal%20Desk/_apis/policy/configurations?api-version=7.1-preview.1"
> ```

Before calling an `e2e-only` PR "just flaky", check which spec failed — the
timeline gives stage results and the build-step log carries the full Playwright
locator and call log (never download the ~300MB report artifact):

```bash
PAT=$(tr -d '\n' < ~/azure.key); ORG=https://dev.azure.com/legaldesk
curl -s -u :"$PAT" "$ORG/Legal%20Desk/_apis/build/builds/<BUILD_ID>/timeline?api-version=7.1" \
  | python3 -c "import json,sys;[print(r['type'],r['name'],r['result']) for r in json.load(sys.stdin)['records'] if r['result']=='failed']"
```

Known-flaky specs that do **not** indicate a real break: `manual-signature-reload`
(fails ~9/10 on pristine `develop`), and the partner-lead family (DB-state
dependent). A failure in those is a re-run, not a fix.

## Data sources

All read-only, all verified working with the `~/azure.key` PAT:

| what | endpoint |
|---|---|
| open PRs, `mergeStatus`, reviewer votes | `git/repositories/{repo}/pullrequests?searchCriteria.status=active` |
| blocking policies + build result | `policy/evaluations?artifactId=vstfs:///CodeReview/CodeReviewId/{projectId}/{prId}` — **needs `api-version=7.1-preview.1`**, plain `7.1` is a 400 |
| which stage failed | `build/builds/{buildId}/timeline` |
| review threads | `git/repositories/{repo}/pullRequests/{prId}/threads` |

Two parsing rules that are easy to get wrong:

- **Threads**: entries whose first comment has `commentType == "system"` are
  ADO's own noise ("X voted 10", "the reference was updated"). They carry
  `status: null` and must be skipped. A real thread is unresolved only when
  `status` is `active` or `pending` — `fixed`, `closed`, `wontFix` and
  `byDesign` are all resolved.
- **Queue age**: measure from the policy evaluation's `startedDate`, never from
  PR creation date. And a conflicted PR's build is *always* queued — there is no
  mergeable commit to build — so that queue entry is a symptom, not a blocker.

Reviewer `vote` values: `10` approved, `5` approved with suggestions, `0` no
vote, `-5` waiting for author, `-10` rejected.

## Limits

- **Read-only.** The PAT in `~/azure.key` cannot queue builds (401), so the skill
  can never re-run a flaky E2E stage itself. Hand the user the build link and let
  them hit *Rerun failed jobs*, or offer to push an empty commit to retrigger.
- It reports; it does not rebase, resolve threads, or complete PRs. Any of those
  is a separate, explicitly-confirmed action — several of these PRs belong to
  colleagues.
- Drafts are hidden by default. `6235` and `6816` have been open for months and
  will otherwise dominate the age column.
## Second sweep: your work items

The PR board answers "what is blocking my code". This answers "what is still on
my plate that shouldn't be". Run it alongside the board whenever the user asks to
clean up DevOps:

```bash
python3 ~/.claude/skills/ado-cleanup/scripts/task-sweep.py
```

It pulls every work item assigned to `AZDO_USER` (default `anders@legaldesk.dk`)
that is not Closed or Removed, then judges each against two independent kinds of
evidence:

- **Linked pull requests** and their status, from the item's `ArtifactLink`
  relations.
- **Merge commits on `develop`** matching `Task <id>` — `git log --grep`. This
  matters because `az repos pr create` does **not** link the work item, so a
  large share of shipped tasks have no link at all. The git history is the more
  reliable of the two.

| verdict | meaning | action |
|---|---|---|
| `needs-resolve` | a PR exists, item still New/Active | set its done state, hand back |
| `needs-handback` | done + **merged**, someone else created it, still in your queue | reassign to the creator |
| `resolved-pr-still-open` | done, but its PR has not merged | wait — nothing for the reporter to look at yet |
| `resolved-no-evidence` | done, no PR found anywhere | **verify** — the fix may never have landed |
| `resolved-mine` | done and you created it | nothing to hand back |
| `genuinely-open` | no PR, no evidence | real work |

**Never hand back work that has not merged.** An item can be marked Resolved the
moment a PR opens, which is correct under this workflow — but handing it to the
reporter then asks them to verify something that is not on `develop`. Require
`merged_pr or merge_commits`, not merely `open_pr`. On 2026-09-15 items 11169,
11318 and 11322 were all Resolved with their PRs still open.

### THE RULE: we mark Resolved, we never Close

**Opening a PR means the work item becomes `Resolved` and goes back to the person
who created it.** They verify and decide whether to Close. Closing is never ours
to do — the reporter is the one who can say the bug is actually gone.

**Except where the type has no Resolved state.** The Agile template here gives
`Task` only New / Active / Closed / Removed — there is no Resolved. `Bug` and
`User Story` do have it. So the done state is per type, and the script asks the
API rather than assuming:

| type | done state we set |
|---|---|
| Bug, User Story | `Resolved` — Closed stays the reporter's call |
| Task | `Closed` — it is the only done state the type offers |

`update_item` refuses `Closed` for any type that has a `Resolved` state, so the
exception cannot quietly spread beyond Tasks.

```bash
# merged PR, item still New  ->  Resolved + handback
python3 ~/.claude/skills/ado-cleanup/scripts/task-sweep.py \
  --resolve 11372 --comment "Shipped in PR 7499, merged to develop."

# already Resolved, just in the wrong queue  ->  handback only
python3 ~/.claude/skills/ado-cleanup/scripts/task-sweep.py --handback 10605
```

Handback is skipped automatically when you created the item yourself —
reassigning something to yourself is a no-op that only churns the history.

The PAT in `~/azure.key` writes work items fine even though `az boards` returns
TF400813 on the same operation, so go through the script, not the CLI.

### How much verification each verdict deserves

Match the effort to the evidence — do not spawn twenty agents to make twenty API
calls:

- `needs-handback` — a human already marked this Resolved and the merge is on
  `develop`. Reassigning is bookkeeping; do it directly in a loop, no agent.
- `needs-resolve` — nobody has judged it yet. The PR exists, but did it address
  what the item actually describes? **One agent per item**, which reads the item
  and the merged diff, then resolves or reports back.
- `resolved-no-evidence` — someone marked it Resolved and no PR can be found at
  all. **One agent**, and it must be willing to conclude the fix never landed and
  say so rather than quietly hand the item on.
- `resolved-mine` / `genuinely-open` — report, never touch.

### Task agent prompt

> Decide whether Azure DevOps work item **{id}** — "{title}" ({url}) is genuinely
> finished, then act on that decision. Current state: {state}. Evidence found:
> {merge commits / linked PRs}.
>
> 1. Read the **whole** work item — description, repro steps, acceptance
>    criteria, and comments. Fetch it with the `~/azure.key` PAT:
>    `GET {BASE}/wit/workitems/{id}?$expand=all&api-version=7.1`.
> 2. Read the merged change that supposedly fixes it (`git show <commit>`, or the
>    PR's diff) and judge whether it actually addresses what the item describes —
>    not merely whether it mentions the same id. A PR titled after the task can
>    still fix only part of it; a title beginning "(Partial)" is an explicit
>    warning.
> 3. If it is genuinely finished, mark it Resolved and hand it back to its
>    creator:
>    `python3 ~/.claude/skills/ado-cleanup/scripts/task-sweep.py --resolve {id}
>    --comment "<one line naming the PR and what shipped>"`.
>    Never set `Closed` — the creator decides that, and the script will refuse.
> 4. If it is **not** finished — the fix is partial, addresses a different
>    symptom, or you cannot find the change at all — **do not resolve it**.
>    Report what is missing and leave the item alone.
>
> Report: your verdict, the evidence you based it on, and whether you resolved it.

## After the table: offer the checklist

Showing the board is only half the skill. **Always** follow it with a checklist of
which categories to actually resolve, via `AskUserQuestion` with
`multiSelect: true`. Build the options from live counts, never from a fixed list:

```bash
for b in conflicts comments; do
  python3 ~/.claude/skills/ado-cleanup/scripts/ado-cleanup.py --blocker "$b" --json \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print('$b',len(d),[r['id'] for r in d])"
done
for v in needs-resolve needs-handback resolved-no-evidence; do
  python3 ~/.claude/skills/ado-cleanup/scripts/task-sweep.py --verdict "$v" --json \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print('$v',len(d),[r['id'] for r in d])"
done
```

Select with `--blocker`, **not** `--bucket`. A PR is filed under its most urgent
blocker, so a PR with a red build *and* an open thread is bucketed `e2e-only` but
still needs the comment answered. `--blocker comments` catches it; `--bucket
comments` silently misses it.

Rules for the checklist:

- Four categories are wired for automated fixing today. From the PR board:
  **`conflicts`** and **`comments`**. From the work-item sweep:
  **`needs-handback`** (bookkeeping, reassign in a loop) and
  **`needs-resolve`** + **`resolved-no-evidence`** (agent verifies first).
  Every other bucket is reported only — say so rather than offering an option
  that does nothing.
- Never offer `resolved-mine` or `genuinely-open` as actionable, and never offer
  anything that would set `Closed`.
- Label each option with its count and PR ids, e.g. *"Merge conflicts — 2 PRs
  (7456, 7469)"*, so the user is choosing against real work.
- Drop any category with zero PRs. `AskUserQuestion` needs at least two options,
  so when only one category has hits, pair it with *"Neither — just leave the
  board"*.
- If nothing at all is actionable, say so and stop. Don't ask an empty question.

## Dispatching the fixes

When a category is ticked, spawn **one fresh subagent per PR** — not one per
category. Launch them all in a single message so they run concurrently, and give
each `isolation: "worktree"` so it gets its own checkout. Do not use
`subagent_type: "fork"`: these want clean context, not yours.

The worktree isolation is not optional. Concurrent sessions in this repo have
twice wiped each other's uncommitted edits working in a shared checkout.

**First, check for stacked PRs — this is not optional:**

```bash
python3 ~/.claude/skills/ado-cleanup/scripts/ado-cleanup.py --blocker conflicts --stacks
```

Branches in this repo are routinely stacked: a follow-up task branches off the
previous task's branch rather than off `develop`, so it replays that PR's commits
under new SHAs. `--stacks` groups the selected PRs by shared commit subjects above
`develop` and prints the base-to-tip order.

- PRs in **different** groups are independent — dispatch them all in parallel.
- PRs in the **same** group must be done **one at a time, base first**, re-running
  the board between each. Fixing the base rewrites commits the tip is still
  carrying a stale copy of, so a parallel tip rebase replays the *old* version of
  the base's files and silently reverts the base's fix on merge.

This was learned the hard way on 2026-09-15: 7454 (base), 7456 and 7469 were
dispatched in parallel. All three "succeeded", but the two tips ended up holding
`DefaultMarket = "se"` while their own base had just been fixed to
`CountryCodeConstant.Sweden`. Both tips had to be redone.

Before dispatching:

- **Only the user's own PRs.** `anders@legaldesk.dk` — rebasing or pushing to a
  colleague's branch is an outward-facing change on someone else's work. The
  board already filters to the user, so this should be automatic; if a
  colleague's PR reached the dispatch list, the filter was overridden and that is
  a bug — stop and ask rather than dispatching.
- **More than six PRs selected?** Confirm the scale before spawning.
- Feed each agent the row from `--json`: `id`, `source`, `title`, `url`, and for
  comments the full `unresolved` array (it carries `file`, `line`, and the whole
  `transcript`).

### Conflict agent prompt

> You are resolving the merge conflicts on Azure DevOps PR **{id}** — "{title}"
> ({url}). Branch `{source}` → `{target}`. You are in a dedicated git worktree;
> work only inside it.
>
> 1. `git fetch origin`, then rebase `{source}` onto `origin/{target}`.
> 2. Resolve every conflict. Resolve **only** the conflicts — no drive-by
>    refactors, renames, or "while I'm here" cleanups. The diff you push must be
>    the original PR's intent plus nothing.
> 3. For each conflicted hunk, understand both sides before choosing: read the
>    incoming `{target}` commits that touched the file (`git log -p
>    origin/{target} -- <file>`). If a conflict needs a product decision you
>    cannot derive from the code — two features genuinely disagree — **stop and
>    report it unresolved**. A plausible guess that compiles is worse than a
>    question.
> 4. Verify: `dotnet build LegalDesk.sln`. If the conflict touched
>    `src/LegalDesk.VueComponents/`, also run `yarn build` in that directory.
>    If it touched code covered by unit tests, run
>    `dotnet test tests/LegalDesk.Tests/LegalDesk.Tests.csproj`.
> 5. Push with `git push --force-with-lease`. (Force-push to this org works —
>    verified 2026-09-11. If it fails with TF401027, do **not** retry: abandon
>    the rebase and instead merge `origin/{target}` into `{source}` and push
>    normally.)
>
> **Known conflict class:** `tests/e2e/playwright.config.ts`. Two PRs each
> register a new spec in the same `testMatch` list at the same position, and git
> calls it a conflict. There is no disagreement — **keep both lines**, develop's
> first. Confirm afterwards that the branch's only delta in that file against
> `origin/develop` is its own added line.
>
> Never run `git stash` — the stash stack is shared across every worktree in this
> repo and popping can destroy another session's work. Git pathspecs are relative
> to your cwd; a wrong-cwd pathspec reports "no changes" and silently drops your
> edits.
>
> Report: every file that conflicted, how you resolved each one and why, the
> verification output, and whether the push landed.

### Comment agent prompt

> You are addressing unresolved review comments on Azure DevOps PR **{id}** —
> "{title}" ({url}), branch `{source}`. You are in a dedicated git worktree.
>
> Threads to address, verbatim from the reviewer:
> {for each unresolved thread: thread id, file, line, full transcript}
>
> 1. Read the code at each anchor **before** deciding anything. The comment is a
>    pointer, not a spec.
> 2. Make the smallest change that answers the comment. Nothing else.
> 3. The reviewer can be wrong, or can be asking about code that has since
>    changed. If so, do not contort the code to comply — draft a reply explaining
>    why and leave the code alone.
> 4. Verify as above (`dotnet build`; `yarn build` for VueComponents; the unit
>    suite if you touched covered code).
> 5. Commit per thread with a message naming what the reviewer asked, and
>    `git push` (a normal push — no force needed).
>
> Do **not** post a reply on the thread and do **not** resolve it. Return, for
> each thread id, a two-sentence reply for a human to post.
>
> Same repo rules: never `git stash`, pathspecs are cwd-relative.

### Collecting the results

When the agents report back:

1. Relay each agent's outcome per PR — the user does not see subagent output.
2. Surface anything an agent refused to decide (an ambiguous conflict, a comment
   it judged wrong) as a question, not a footnote. That is the whole reason it
   stopped.
3. Re-run the board to confirm the blockers actually cleared. A pushed rebase
   re-queues the build, so expect those PRs to move to `running`, not to `ready`.
   For a stack, re-running is also what releases the next PR in the group — check
   `--stacks` again before dispatching the next one.
4. Offer to post the drafted replies and resolve the threads — one confirmation,
   then do it. The `~/azure.key` PAT **can** write threads (confirmed 2026-09-15,
   HTTP 200 on both calls) even though it cannot queue builds:

   ```bash
   PAT=$(tr -d '\n' < ~/azure.key)
   API="https://dev.azure.com/legaldesk/Legal%20Desk/_apis/git/repositories/LegalDesk-V2/pullRequests"

   # reply (body from a file - the content is markdown and often multi-line)
   curl -s -u :"$PAT" -H "Content-Type: application/json" -X POST \
     "$API/<PR>/threads/<THREAD>/comments?api-version=7.1" --data-binary @reply.json
   # {"content": "...", "commentType": "text"}

   # resolve: "fixed" when code changed, "closed" for a tool-generated thread
   curl -s -u :"$PAT" -H "Content-Type: application/json" -X PATCH \
     "$API/<PR>/threads/<THREAD>?api-version=7.1" -d '{"status":"fixed"}'
   ```

   Then re-run `--blocker comments` to confirm nothing is left unresolved.

### Threads that are not review feedback

The ADO web conflict-editor posts a thread reading *"Submitted conflict
resolution for the file(s) — …"*. It is anchored to a real file and authored by a
real person, so it is indistinguishable from review feedback until you read it —
but it asks for nothing. The script flags these as `tool_generated`. Never
dispatch a code agent at one: it needs the thread resolved and nothing else.
Check for others of this shape before spawning, and add them to the pattern in
`classify()` when you find one.

### `mergeStatus` can be stale

Azure DevOps computes a PR's merge preview lazily and caches it. A PR can report
`mergeStatus: succeeded` while genuinely conflicting — the value is only refreshed
when something forces a recompute, and a push to the source branch is what
usually does it. Observed 2026-09-15: PR 7454 reported `succeeded`, a single
unrelated commit was pushed, and it immediately reported `conflicts` against an
unchanged `develop`. The conflict had been latent the whole time.

So a clean board is weaker evidence than it looks. When it matters — before
telling someone a PR is ready, or before counting the `conflicts` bucket as
complete — confirm locally:

```bash
git fetch -q origin
git merge-tree --write-tree origin/develop origin/<source-branch> >/dev/null \
  && echo "merges cleanly" || echo "CONFLICTS"
```

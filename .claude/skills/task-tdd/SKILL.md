---
name: task-tdd
description: Resolve a tracked work item (Azure DevOps, GitHub Issue, Jira, etc.) using a strict test-driven workflow — fetch the task, agree on scope, scope the test, create a git worktree branched off develop, write a failing test that captures the bug or feature, verify it fails for the right reason, implement the fix, verify it turns green, run an adversarial review of the diff against the task, then commit and push as separate test/fix commits, and on teardown audit that everything was concluded (work item resolved, reviewer assigned, PR linked). Use when the user references a work-item URL or task number and wants to address it via TDD ("let's fix task X using TDD", "do this with a failing test first", "TDD this", "address ticket Y test-first").
---

# Task TDD workflow

An eight-phase loop for resolving a tracked work item using TDD with explicit scope alignment up-front, an adversarial review gate, clean commit hygiene, and a completion audit at teardown. Run the phases in order. Don't skip — each phase prevents a specific failure mode that's expensive to recover from later.

## Phase 1: Get the task

**First, assign the work item to the user** so the tracker reflects who's on it before any other work begins. The user is `anders@legaldesk.dk`.

**Azure DevOps** (the LegalDesk default):
```bash
az boards work-item update --id <ID> --organization https://dev.azure.com/<org> --assigned-to anders@legaldesk.dk --output json
```
**GitHub**: `gh issue edit <ID> --add-assignee @me`.
**Jira**: `acli jira workitem assign <ID> anders@legaldesk.dk` (or the official `jira` CLI).

If assignment fails (permissions, unknown identity), surface it and continue — don't block the workflow on it.

Then fetch the work item directly from its tracker. Don't use `WebFetch` against authenticated trackers — it'll just hit the login page.

**Azure DevOps** (the LegalDesk default):
```bash
az boards work-item show --id <ID> --organization https://dev.azure.com/<org> --output json
```
Description is HTML in `fields["System.Description"]`. Parent id is in the top-level `relations` array — entries with `rel: "System.LinkTypes.Hierarchy-Reverse"` point to the parent. Fetch the parent for context if the child describes "item N" of a list. Useful fields: `System.Title`, `System.WorkItemType`, `System.State`, `System.Tags`, `System.Parent`, `System.IterationPath`.

**GitHub**: `gh issue view <ID> --json number,title,body,state,labels,assignees`.
**Jira**: `acli jira workitem view <ID>` or the official `jira` CLI.

**Read the WHOLE task, not a fragment.** It is not acceptable to skim the title and the first line of the description and move on. Read the entire description, every repro step, the acceptance criteria, and all comments — and **look at every screenshot/attachment**. Tracker descriptions are HTML with embedded `<img src="…/_apis/wit/attachments/…">` tags; those images frequently carry the actual bug (a red validation state, an "expected vs current" side-by-side, a stack trace in a console panel) and the prose alone is often incomplete or misleading without them. Download each attachment and view it before summarizing:
```bash
# extract every attachment URL from the description/repro HTML, then fetch and Read each
az boards work-item show --id <ID> --organization https://dev.azure.com/<org> --output json \
  | grep -oE 'https://[^"]*/_apis/wit/attachments/[^"]*'
# az devops attachment URLs need auth; pipe your PAT: curl -sL -u :"$AZDO_PAT" "<url>" -o <file>.png
```
Then open each downloaded image with the Read tool. Only summarize once you have read the full task and seen **every** image.

**A task you cannot fully read is a HARD STOP — not a disclaimer you proceed past.** If any attachment fails to fetch — missing/expired `AZDO_PAT`, a 401/403, a network error, an unreadable format — you do **not** have the whole task, and you must not continue. Do not rationalize your way forward ("the prose is probably enough", "I'll infer the bug from the title"): the images routinely carry the actual bug, so proceeding without them means fixing a task you have not read. Instead:

1. **Stop the workflow.** Do not scope, branch, write a test, or touch code.
2. **Report precisely** which attachment(s) you couldn't fetch and the exact failure (e.g. "`AZDO_PAT` unset → 401 on attachment `<url>`"), plus what you *were* able to read.
3. **Ask the user for help** — the PAT, the images pasted directly, or an explicit instruction to proceed without them — and **wait**. Only the user may waive an unreadable attachment; you may never waive it yourself.

The one thing that is never acceptable is silently concluding you can fix the task without the image.

Summarize the task in plain language and confirm shared understanding. **Translate, don't restate** — turn tracker prose into the concrete user-visible behavior.
> Bad: *"fix the wizard bug."*
> Good: *"When a member revisits step 3 of the SE incorporation wizard, the company-name field they entered earlier is blank."*

End the summary with a one-sentence proposed approach so the user has something concrete to react to.

**Sanity-check the shape of the task before continuing.** TDD doesn't fit every work item — pure refactors, doc-only changes, copy tweaks, dependency bumps, and hotfixes during incident response usually shouldn't be forced through this workflow. If the task isn't TDD-shaped, surface that now and ask the user how they want to proceed instead of ramming the loop onto it.

## Phase 2: Agree on scope

Before writing code, identify the forks where the user's intent matters and you'd otherwise guess:
- Which surface (legacy vs new, multiple layers, frontend vs backend)
- Test layer (unit, integration, E2E)
- Test fixture style (factory in code, seeded backend data, real production-like flow)
- Cleanup approach (per-test, per-suite, none)
- Any prerequisites the user needs to confirm (env vars, test accounts, payment-gateway test mode)

Use `AskUserQuestion` with 2-4 options per question. Label your recommendation `(Recommended)`. Don't ask trivial questions, but DO ask when getting it wrong forces a rewrite. Bundle related questions into a single `AskUserQuestion` call so the user answers them together.

> `AskUserQuestion` is a deferred tool in some harnesses — load its schema via `ToolSearch` with `select:AskUserQuestion` if it isn't already available.

For non-trivial work, draft a short plan in `~/.claude/plans/<auto-name>.md` covering: context, approach, critical files, verification, open questions, out-of-scope. The plan grounds later phases — refer back to it when context shifts.

## Phase 3: Scope the test

Explore the relevant code (use the `Explore` agent for broad searches, multiple agents in parallel when scope is uncertain). The output should be:
- Exact file paths, function names, line numbers of the buggy or feature-relevant code
- The user-facing failure mode (or success criterion) in concrete terms
- The shape of the assertion that captures it
- The fixture / data the test needs

For E2E specifically, also identify:
- Existing helpers, page objects, and fixtures to reuse (don't reinvent)
- Auth state requirements — re-run the setup project if storage-state cookies might be stale
- Cleanup hooks the test should fire (and which auth context can perform them)

Doing this **before** branching means you discover "this is already fixed" or "the scope is wildly different than the ticket implies" without leaving an orphan branch behind.

### Reproduce the bug first (bug fixes only)

**For any bug fix, you must reproduce the bug and observe the failure with your own eyes before writing a line of test or fix code.** A ticket description is a claim, not evidence — reproduce it against the *real* current code/data so the test you write next mirrors what actually happens, not what the ticket says happens.

**Reading the code and concluding "this is probably where it breaks" is not reproduction — it's a hypothesis, and it's the specific failure mode this section exists to block.** Tracing the call path, spotting a plausible off-by-one or missing null check, and moving straight to a test/fix is exactly how you end up pinning a bug that was never confirmed to be the one in the ticket. A hypothesis earns the right to become a fix only *after* it's checked against an observed failure — never the other way around, and never skipped because the code reading felt conclusive.

- Drive the actual failure: run the app (`ld-dev-server`), hit the endpoint, run the wizard step, query the real authored config/data (e.g. unauth `/api/wizard/config` + `/module-elements` on dev) — whatever exhibits the reported behavior. Capture the concrete wrong value / error / stack trace you observe; that observed value is what the Phase 5 assertion asserts against.
- **State the reproduction as evidence, not narrative.** The exact command or action you ran, and the actual output/response/screenshot you got back — not "I traced through X and Y, so Z would happen." If you cannot quote or show the actual bad output, you have not reproduced it yet, no matter how confident the code reading made you.
- If you **can't** reproduce it, stop and resolve *why* before proceeding — the repro steps are incomplete, the environment differs, it's already fixed, or the premise is wrong. Do **not** write a speculative test against a bug you've never seen; that's how a green test ships alongside a still-live bug (see `~/.claude/projects/<project>/memory/feedback_verify_root_cause_before_fix.md`). Report the failure-to-reproduce back to the user rather than guessing.
- Confirm the reproduction is on the code path the ticket points to. A symptom you can trigger through a *different* cause is not the same bug — you'd fix the wrong thing and the test would pin nothing.

The Phase 5 failing test is the *automated* form of this reproduction. Reproducing manually first is what lets you tell a right-reason red from a wrong-reason one.

## Phase 4: Create a worktree off develop

**All work happens in a dedicated git worktree branched from `develop`** — never in the primary checkout, and never branched from whatever happens to be checked out. This keeps the main working tree untouched, isolates the task, and guarantees a clean base regardless of the current branch.

Naming convention: branch `task-<ID>-<kebab-case-summary>` to match repo history; worktree directory as a sibling of the repo, e.g. `../<repo>-task-<ID>`. Confirm the repo's host before creating — Azure DevOps repos use `az repos pr create` later, not `gh`. Check `~/.claude/projects/<project>/memory/reference_code_host.md` if it exists.

```bash
# run from inside the primary repo checkout
git fetch origin develop
git worktree add ../<repo>-task-NNNN-short-description -b task-NNNN-short-description origin/develop
cd ../<repo>-task-NNNN-short-description
```

Branch from `origin/develop` (freshly fetched), not local `develop`, so the base is up to date even if the local tip is stale. **Verify the base is actually the remote tip before writing any code** — a stale base is the single most common source of a merge conflict discovered later, at PR-open time, when it's most expensive to fix:

```bash
git rev-parse origin/develop            # must equal...
git rev-parse HEAD                       # ...this, right after the worktree is created
```

If they differ, you branched off something stale — `git fetch origin develop` and re-create the branch before continuing. Note the base SHA in the plan file; Phase 8 compares against it to detect upstream movement.

**Worktrees start cold** — git-ignored config and installed dependencies do not carry over. For LegalDesk-V2: copy `appsettings.Development.json` and `tests/e2e/.env.local` from the primary checkout, run `npm install` in `tests/e2e`, and expect a 2-3 min first build/cold start. See `~/.claude/projects/<project>/memory/reference_git_worktree_setup.md` if present for the project's exact setup steps.

**Use the `ld-dev-server` skill to start the local server — don't ask first, and never a bare `dotnet run`.** Multiple LLMs often run in parallel against this repo. The `ld-dev-server` skill leases an isolated port + its own `UmbracoDb` clone so instances don't collide; a bare `dotnet run`/`dotnet watch` hardcodes port 44333 and the shared DB, which fights other agents, serves stale code, and corrupts EF migrations. Because it's isolated, it's safe to start a server whenever you need one without checking in. The box is RAM-tight (~2.6 GB per warmed instance), so don't lease more instances than you need, and stop + release the one you started when done (see the Phase 8 teardown). Invoke `/ld-dev-server` for any server boot or E2E run that needs a running app. Full procedure: the `ld-dev-server` skill and `~/.claude/projects/<project>/memory/reference_multi_instance_dev_servers.md`.

Don't commit anything yet. Run the rest of the workflow (Phases 5-8) from inside this worktree. When the task is fully done — PR opened, merged, or abandoned — remove the worktree so it doesn't linger:

```bash
git worktree remove ../<repo>-task-NNNN-short-description
```

## Phase 5: Write the failing test and verify it fails for the right reason

Implement the test, run it, and confirm:
1. It **fails**, and
2. The failure is on the assertion that captures the bug — not on setup, fixture creation, env prerequisites, or fragile selectors.
3. Setup tests in the same spec (1, 2, 3...) all pass — only the bug-capturing assertion is red.

When the failure is on the wrong line, fix the test infrastructure first. The bug-capturing failure must be unmistakable. Read the failure output carefully — if the test failed because a selector didn't match or an env var was missing, that's a different problem than the bug.

**Don't paint CI red with an intentionally-failing test.** If the repo has a tier for known-failing tests (`pending`, `wip`, `quarantine`), put the new test there until it goes green. If there's no such tier, use the test runner's skip mechanism (`test.skip`, `it.skip`, `[Ignore]`, etc.) and leave a `// TDD: unskip when fix lands` comment so the gate is easy to find when promoting in Phase 6.

**Don't add retries or polling to a failing assertion to mask a bounce.** Polling for readiness (the page has loaded, the network has settled) is fine; retrying an assertion that already saw the wrong value is just hiding the bug. Re-read the failure output: expected vs received values should mirror the bug description exactly, and the failure should happen inside the production code path the bug report points to — not in scaffolding.

When uncertain whether the failure is "right", add temporary logging that surfaces the actual values being compared, so you can confirm before celebrating. This phase exists to prevent celebrating a wrong-reason red. If the failure isn't unmistakable, fix the test, don't fix the code.

## Phase 6: Implement the fix and validate it turns green

The smallest change that turns the test green. Resist:
- Refactoring beyond what the bug demands
- Adding error handling for hypothetical scenarios
- Threading new fields through APIs unless the assertion needs them
- Touching unrelated files
- "While I'm here" cleanups

**Enforce smallness explicitly:** if you find yourself editing more than the one or two files the assertion points to, stop and justify it. Usually the larger change is a refactor that belongs in a separate commit (or a separate task).

**Speed is a feature — a faster site is a better user experience, and that matters on every task, not just perf tickets.** Don't let an otherwise-correct fix quietly make a page slower: an added synchronous DB/API call in a hot path, an N+1 query, an unindexed filter over a growing table, a new blocking script/stylesheet, or a bundle-size jump in `LegalDesk.VueComponents` are all in scope even when the ticket is about something else entirely. If the fix requires a genuine tradeoff (correctness for latency), make the tradeoff consciously and say so — don't let it happen by accident because nobody looked.

If the fix is in a layer that compiles or bundles to a different artifact (Vue → JS bundle, TS → JS, SCSS → CSS), rebuild whatever the test actually consumes. Don't assume the test runs against your source.

Run the test again. Expect:
- The previously-red assertion is now green
- Every other test in the spec is still green
- No new warnings/errors in stdout
- Cleanup hooks ran successfully

If a test now passes that was passing *before* the test scaffolding existed, investigate — could be a regression introduced by the test setup itself.

Once green, **promote** the test out of any "pending" tier or `.skip` gate into the default-running tier so future runs catch regressions. Update the test name if it still says "FAILING" or similar TDD-mid-flow language.

### Full regression gate (before moving to Phase 7)

The single-spec run in this phase proves the fix works and didn't break its own neighbours — it does **not** prove the fix is regression-free across the codebase. Before committing, run the full suites for every layer your change can reach:

- **Unit (.NET)**: `dotnet test tests/LegalDesk.Tests/LegalDesk.Tests.csproj`
- **Jest (Vue components)** — if the change touched anything under `src/LegalDesk.VueComponents/`: `cd src/LegalDesk.VueComponents && yarn test`
- **E2E (Playwright)** — **always. There is no condition under which this is skipped.** Not "if the change looks risky", not "if it could plausibly reach the browser" — every task runs the full suite before commit, including backend-only, config, tooling, and docs-adjacent changes. Regressions hide in interactions no unit or Jest test covers, and the judgement call about whether a diff "can reach a browser" has been wrong often enough that the call is no longer yours to make. `cd tests/e2e && npm run test -- --workers=2`. Don't ask first — boot the server via `/ld-dev-server` (it's isolated; see the Phase 4 server note) and run it.

**Verify the E2E test count, not just the green.** As of 2026-07-31 `npm run test` (setup + smoke + core + deep + mobile-chrome + jurio) collects **~457 tests in 89 files**. A run that reports meaningfully fewer (say under ~445) did *not* run the whole suite — collection silently narrowed (a stray `--grep`/`testMatch` filter, a project that never started, or a failed setup project that voided its dependents). A short-but-green run reads as "everything passed" when most tests never executed. If the count is well under the expected ~457, find why it dropped and re-run; do not treat it as a pass. (Re-check the baseline by appending `--list` to the exact project set in `tests/e2e/package.json`'s `test` script — the suite grows and the project list changes over time.)

All three must be green before you commit. This is the one place the workflow overrides the "minimal test runs" default — a per-spec run is right *during* the red→green loop, but the pre-commit gate is deliberately full-suite so a fix doesn't land a regression elsewhere.

**E2E is never skipped, for any reason.** Unit and Jest have a genuine escape hatch: if a layer is truly untouched (e.g. a backend-only fix that can't affect Vue), you may skip that layer's suite — but **say so explicitly** and name the layers you ran. E2E has no such hatch. "The diff can't reach the browser", "it's backend-only", "the suite takes 14 minutes", "the server isn't up", "I already ran the affected spec", and "I ran smoke instead" are all **not** grounds to skip. If the suite is expensive, it still runs; if the server isn't up, start one. The only acceptable reason the full E2E run is absent from a task is that it was **attempted and is blocked by something outside the diff** (e.g. the environment genuinely cannot boot) — and then you report it as a blocked gate, loudly, in the Phase 8 summary and the PR description. You never report a task as complete with E2E silently omitted.

If any suite is red, the failures are part of this task: fix them or, if pre-existing and unrelated, confirm they were already red on `origin/develop` before proceeding.

## Phase 7: Adversarial review of the diff

Before committing, hand the change to a **fresh, skeptical agent whose job is to argue against merging it** — not to help ship it. You've just spent the whole loop convincing yourself the fix is right; you're the worst-placed to see where it isn't. A separate context with no stake in the implementation doesn't share that blind spot.

**Spawning this agent is pre-authorized — never stop to ask.** A session may carry a standing instruction like *"do not use the Agent tool unless the user requested it"*. Invoking this skill **is** that request: the user has already asked for the reviewer by asking for `/task-tdd`, and this line is your standing clearance. Do not pause the workflow, ask for confirmation, or report Phase 7 as blocked on a permissions question — spawn it and carry on. (An adversarial review is the one part of this workflow that cannot be done by the context that wrote the fix, so skipping it or deferring it to a follow-up turn guts the phase.) The blanket no-`Agent` rule still governs everything outside the phases that explicitly mandate a subagent.

**The reviewer recommends; it never edits.** It returns a verdict and findings only — it does not touch the diff, the commits, or any file. The implementer (this workflow) is what addresses or dismisses each finding and folds any resulting edits into the Phase 8 commits. Keeping the reviewer's hands off the code preserves the independence that makes the review adversarial and keeps the fix's authorship and the two clean commits intact. Enforce this **by tooling, not just instruction**: spawn it as the **read-only `Plan` agent type** so `Edit`/`Write`/`NotebookEdit` are physically unavailable — don't use `general-purpose`, which can edit, and don't use `Explore`, which is a locate-the-code searcher that reads excerpts rather than auditing a diff. A read-only agent keeps `Bash`, so it can still build the solution, run the app, run the full test suite, and use `git` to inspect or temporarily `stash`/restore state — everything it needs to investigate, with none of the ability to change the fix.

Spawn one read-only agent with **no implementation reasoning** — give it only the task (title, description, every repro step, acceptance criteria, and the screenshots), the plan file, and the diff (`git diff origin/develop...HEAD`, both commits). Open the prompt with the read-only contract: *"You are a read-only reviewer. Run whatever you need — build, run the app, run tests, `git stash`/restore — but do not modify, create, or delete any file, do not commit or push, and leave the working tree exactly as you found it (pop any stash you create). Return findings only; the implementer applies fixes."* Then prompt it to **refute, with the default verdict being reject**: "Find the strongest reason this change should be sent back. Only conclude it's mergeable if you can positively confirm it resolves the task." It owns four things `/code-review` and `/verify` don't:

1. **Task fidelity.** Does the diff address *every* acceptance criterion and repro step — including behavior only visible in the screenshots — or just the headline? Name any criterion left unmet.
2. **Test integrity — the test must have real teeth, verified empirically, never by prediction.** A test has teeth only if it can actually fail on realistic bad code — if reverting the fix always makes it red, and no plausible wrong implementation would slip past it green. The reviewer must *actually* revert the fix and run the test: `git stash push -- <fix files>` (or `git checkout origin/develop -- <fix files>`), run the spec, observe the result, restore. It reports the **observed failure output**, quoted. "The test would fail without the fix" with no run behind it is not an answer and does not satisfy this item — a mental prediction is precisely how a toothless test that pins nothing survives review. Also: does it assert on the bug-capturing value, or on scaffolding? A test that only checks "no error was thrown" or "the function was called" has no teeth even if it goes red on revert for an unrelated reason (e.g. a crash) — it must fail *because the asserted value is wrong*, not incidentally.
3. **Minimality.** Is this the smallest change that resolves the task (Phase 6 rule), or did unrelated edits, speculative error-handling, or "while I'm here" cleanups creep in?
4. **Performance impact.** A faster site is a better user experience, full stop — so a "correct" fix that quietly slows a page down is still a finding, even on a ticket that isn't about performance. Look for a new synchronous call in a hot path, an N+1 query, an unindexed filter, a newly-added render-blocking script/stylesheet, or a meaningful bundle-size jump in `LegalDesk.VueComponents`. Cite the specific mechanism, not a vague "might be slower."
5. **Justified workarounds — reject them.** *"If you need a paragraph-long comment to justify why the workaround is OK, the code is wrong — fix the code."* A long explanatory comment defending a hack is not documentation, it's the tell that the fix is wrong and the author knew it. Treat any comment that argues for its own code — why this is safe, why this edge case can't happen, why the obvious approach didn't work — as a rejection trigger: send the code back, don't accept a shorter comment. Same for stubs, no-op branches, and swallowed errors that exist to make something pass rather than work. (Rule lifted from Bun's Zig→Rust rewrite, where it was handed to the adversarial reviewers as a rejection criterion after Claude began papering over stubbed functions with suspiciously long comments — [bun.com/blog/bun-in-rust](https://bun.com/blog/bun-in-rust).)

For pure code-correctness (bugs, edge cases, cleanups), it should invoke or defer to `/code-review` rather than re-deriving it — this phase composes with that skill, it doesn't repeat it. For a high-risk or large diff, escalate to a 4-lens panel (fidelity / test-integrity / minimality-and-workarounds / correctness, majority-to-reject) instead of a single skeptic.

**Every finding carries evidence or is labelled unverified.** Require each one to cite `file:line` plus either a command and its actual output, or a concrete failure scenario (specific inputs/state → wrong result). Findings the reviewer could not substantiate must be marked `UNVERIFIED` and are advisory only — they never block. This cuts both ways: it stops a confident-sounding but wrong finding from forcing a pointless edit, and stops a real one from being waved off. Reviewer agents do return plausible-but-false findings; don't take them at face value, check the cited evidence yourself before acting on it.

**A "mergeable" verdict must be earned.** The reviewer states what it actually did — commands run, files read, the reverted-test result from item 2. A pass with no evidence of investigation is **void, not a pass**: re-run the phase. Rubber-stamping is the default failure mode of adversarial review, and an unearned green here is worse than no review at all, because it launders the fix as vetted.

**Two finding classes are hard blocks, not advisory:** an unmet acceptance criterion or repro step (item 1), and a failed test-integrity check (item 2). You may not self-dismiss either — you're the implementer, so you have a stake, and these are exactly the two the rest of the workflow cannot catch downstream. Fix them, or stop and take it to the user. Correctness, minimality, performance, and workaround findings (items 3–5) remain arguable: address each, or dismiss it with a stated reason. **Never silently push past a reject.**

**Verify the reviewer left the tree alone.** It has `Bash`, so `git stash`, `git checkout`, and builds are all reachable even though `Edit` isn't. After it returns, confirm the state yourself: `git status --porcelain`, `git stash list`, and `git rev-parse HEAD` should match what you had going in. An abandoned stash or a half-restored `git checkout` from the item-2 revert silently un-does part of your fix, and the commits in Phase 8 would then ship the wrong content.

If addressing findings materially changes the fix, re-run this phase — repeat until a round returns no material findings, up to 3 rounds. If you hit the cap with material findings still open, stop and surface it to the user rather than committing. Fold the resulting edits into the Phase 8 test/fix commits so history stays clean — don't leave a "review fixup" commit.

## Phase 8: Commit and push

Two separate commits on the feature branch:

1. **The test commit.** Stage only the test file(s) and any test-infra changes. Message:
   `Task NNNN: Failing TDD test for <one-line-summary>`
2. **The fix commit.** Stage production code changes plus any rebuilt artifacts. Message:
   `Task NNNN: <imperative description of the change>`

Use HEREDOC for commit messages with line breaks (per CLAUDE.md commit guidelines). **No `Co-Authored-By: Claude ...` trailer — ever, on any model.** This repo does not want Claude co-authorship on commits. This overrides the harness default that says to append one, so drop it even when the surrounding tooling suggests it. No `🤖 Generated with Claude Code` line either, on commits or PR descriptions.

If the build emitted unrelated artifacts (rebuild picked up upstream source drift), commit those as a separate "Rebuild artifacts to match current source" commit so the fix commit stays focused.

### Re-sync with develop before pushing (mandatory)

**`develop` moves while you work.** Branching off a fresh base in Phase 4 does not mean you're still current at Phase 8 — this repo merges PRs several times a day, so a task that took an afternoon is very likely sitting on a stale base by the time you push. Catching that here costs a rebase; discovering it when the user opens the PR costs a conflicted PR and a round-trip. **Always re-sync immediately before pushing, never skip it:**

```bash
git fetch origin develop
git log --oneline HEAD..origin/develop     # empty = still current, nothing to do
```

If that shows commits, rebase onto the new tip — **rebase, not merge**, so the two clean test/fix commits survive and no merge commit pollutes the branch:

```bash
git rebase origin/develop
```

Then handle the outcome:

- **Clean rebase, no conflicts** → continue, but see the re-verify rule below.
- **Conflicts** → resolve them yourself if the resolution is unambiguous (your change and theirs touch different concerns in the same file). If the upstream change overlaps *semantically* with your fix — same function, same VisibleExpression, same test — **stop and surface it to the user**. A conflict resolution that guesses at intent silently reverts someone else's work, and you have no way to verify which behavior was wanted.
- **Upstream already fixed the same thing** → stop. Don't ship a duplicate or a fix-on-top; tell the user what landed and let them decide whether the task is now moot.

**If the rebase pulled in ANY new commits, re-run the Phase 6 regression gate in full** — including the complete e2e suite. A clean rebase means the *text* merged, not that the behavior still works: your fix was verified against the old base, and the code around it has changed since. Green-before-rebase is not evidence of green-after-rebase. This is also the case a plain "it compiled" check will miss entirely.

Only once you're rebased onto the current tip and the gate is green:

```bash
git push -u origin task-NNNN-short-description
```

If you had already pushed before the rebase, the push needs `--force-with-lease` (never bare `--force`, which discards a teammate's push to your branch without telling you):

```bash
git push --force-with-lease origin task-NNNN-short-description
```

**Don't open the PR unless the user asks.** Provide the CLI command and a web-UI fallback URL so they can decide.

If they do ask you to open it — especially if any time has passed since the push — **re-check the base one last time first** (`git fetch origin develop && git log --oneline HEAD..origin/develop`). If it's moved again, re-sync per the section above before creating the PR. Opening a PR that's already behind is exactly the failure this gate exists to prevent, and the check costs one command.

Azure DevOps:
```bash
az repos pr create \
  --organization https://dev.azure.com/<org> \
  --project "<Project>" \
  --repository <repo> \
  --source-branch task-NNNN-short-description \
  --target-branch develop \
  --title "Task NNNN: <title>"
```

Web fallback:
`https://dev.azure.com/<org>/<project>/_git/<repo>/pullrequestcreate?sourceRef=<branch>&targetRef=develop`

**Azure DevOps caps the PR description at 4000 characters** and rejects the whole `pr create` call when you exceed it — you get `Invalid argument value. Parameter name: A description for a pull request must not be longer than 4000 characters` and no PR. Count before calling (`${#DESC}`), and if it's over, *trim* — drop whole sections, tighten prose, move detail into the commit bodies — rather than truncating mid-sentence. Anything the user explicitly approved (accepted caveats, known side effects) stays; it is the reason they said yes.

### Announcing the PR in Slack

When the user asks to "post"/"announce"/"share" the PR in Slack, follow the house protocol exactly — it is terse, and a rich write-up is *wrong* here, not merely verbose.

- **Channel: `#pull-requests`** (`C06FK0APYVC`). Not `#dev-chat`, not wherever the discussion happened. `#dev-chat` is for questions, IP-whitelisting and debugging chatter.
- **Format: exactly two lines** — a title line, then the bare PR URL on its own line:

  ```
  V2: Task 10839: Build product page wizard URLs from TrackingName, not SKU
  https://dev.azure.com/legaldesk/Legal%20Desk/_git/LegalDesk-V2/pullrequest/7031
  ```

- **The `V2: ` prefix** marks the LegalDesk-V2 repo. Other repos name themselves instead (`AutomationApp: …`).
- **The title says what the change *does*** — imperative, like the fix commit — not the raw ticket title. Include `Task NNNN:` when there is a work item; e2e/chore PRs use a conventional-commit style instead (`V2: test(e2e): full company-incorporation timeline traversal coverage`).
- **No body.** No problem statement, no root cause, no test counts, no caveats, no reviewer notes, no @-mentions. All of that belongs in the PR description, which is where reviewers read it. The Slack post is a pointer, nothing more.
- **Draft only, never send** — use `slack_send_message_draft`. "Post it" means prepare the draft for the user to send. (See `~/.claude/projects/<project>/memory/feedback_slack_draft_never_send.md`.)

Only one attached draft is allowed per channel, so if a draft already exists there, say so rather than silently failing.

### After the PR is created: prompt to tear down the worktree and server

Once the PR exists, this worktree's job is done. **Ask the user to confirm teardown — don't do it unprompted** (they may still want to inspect the branch, re-run a spec, or push a fixup).

#### Teardown is also the final completion gate — audit before you remove anything

**A teardown request is almost always the last step of the whole workflow.** Nothing follows it, so anything still open at that moment stays open forever — and the loose end is invisible a week later, when the branch, the server and this context are all gone. So when the user says "tear down" / "clean up" / "we're done", **first run a completion audit and report it as a short checklist**, then do the mechanical teardown. Cost now: one minute. Cost later: a fix that shipped against a work item nobody ever closed and nobody ever reviewed.

Audit each item by **checking**, not by recalling what you believe you did:

1. **Nothing uncommitted or unpushed.** `git status --porcelain` (clean) and `git log --oneline origin/task-NNNN-short-description..HEAD` (empty). A stray edit from a Phase 7 finding is the classic straggler.
2. **The Phase 6 regression gate really ran green** — unit / Jest where applicable, and the full e2e suite with a plausible test count. If it was blocked, that must already be stated loudly in the summary and the PR description (Phase 6 rule). Don't let teardown be the place a skipped gate quietly disappears.
3. **Phase 7 adversarial review ran**, and every hard-block finding (unmet acceptance criterion, failed test-integrity check) is resolved rather than dropped.
4. **The PR exists, targets `develop`, and the work item is linked to it.** `pr create` does *not* link the task — `az repos pr work-item add` does, and it's routinely forgotten. Verify, don't assume:
   ```bash
   az repos pr show --id <PR-ID> --organization https://dev.azure.com/<org> \
     --query "workItemRefs[].id" -o tsv        # empty = not linked
   az repos pr work-item add --id <PR-ID> --organization https://dev.azure.com/<org> --work-items <ID>
   ```
5. **The original work item's state** — the single most-forgotten item, because the code work feels finished once the PR is up. Fetch the *current* state; a stale memory of having assigned it in Phase 1 says nothing about its state now:
   ```bash
   az boards work-item show --id <ID> --organization https://dev.azure.com/<org> \
     --query 'fields."System.State"' -o tsv
   ```
6. **Slack announcement.** Was the `#pull-requests` question asked, and the answer honoured? If the PR exists and was never posted (and the user never declined), the work is effectively invisible — raise it now.
7. **Everything this task started is accounted for**: background tasks, leased dev servers (including any *extra* instance you leased mid-task), worktrees, and throwaway files written into the repo rather than the scratchpad.

Report the audit as a checklist with a plain ✅ / ❌ per item and the evidence for each. Anything red is surfaced before teardown, not after.

#### Then ask about the two tracker actions — every time

Bundle both into one `AskUserQuestion` call, alongside teardown confirmation:

- **"Mark work item NNNN as Resolved?"** — include its current state in the question so the user can see whether it's already been moved.
- **"Add a reviewer, and who?"** — a PR nobody is assigned to review can sit for days.

```bash
# state transition — only on an explicit yes
az boards work-item update --id <ID> --organization https://dev.azure.com/<org> \
  --state Resolved --output json

# reviewer: resolve the GUID first — `--reviewers <email>` fails identity lookup and errors out
az repos pr list --organization https://dev.azure.com/<org> --project "<Project>" \
  --repository <repo> --query "[].reviewers[].{name:displayName,id:id}" -o table
az repos pr reviewer add --id <PR-ID> --organization https://dev.azure.com/<org> \
  --reviewers <GUID> --output json
az repos pr show --id <PR-ID> --organization https://dev.azure.com/<org> \
  --query "reviewers[].displayName" -o tsv        # verify it stuck
```
GitHub: `gh issue close <ID>` / `gh pr edit <PR> --add-reviewer <user>`. Jira: transition via `acli jira workitem transition`.

**Neither action is ever taken on your own initiative, and neither is implied by the teardown confirmation.** Both are outward-facing — a state change and a review request land in front of the team and other people's queues — so only an explicit yes authorises each one. Equally, **never let a "no" go unrecorded**: if the user declines or defers, say so in the final summary so the open item is visible rather than lost. And don't hold the mechanical teardown hostage to these answers — if the user says "just tear down", tear down and report the tracker items as still open.

When they confirm teardown, do it in this order:

1. **Stop any background tasks you spawned** — poll loops, `run_in_background` commands, file/log watchers, monitors. They may still be hitting the server or holding resources; kill them before tearing down what they point at.
2. **Stop the leased dev server**, *before* removing the worktree — the running server holds the worktree's files open, and stopping it frees the port + ~2.6 GB RAM. One command does the whole thing (stops the site, offlines the clone, clears the lease, returns the slot to the pool):
   ```bash
   ~/projects/Legaldesk-V2-Database/bin/lddev teardown "$INSTANCE"
   ```
   Confirm the port is free afterwards. (`release` only clears the lease record and leaves the site running — that's for when you never started one.)
3. **Don't re-clone the slot's database.** The allocator re-clones the slot it hands out, so cleanliness is guaranteed on the way *in*, not on the way out — whatever this task's tests wrote (members, drafts, orders) is wiped when the slot is next leased. Nothing to decide and nothing to ask. (This is deliberate: teardown-side cleanup depended on the previous holder exiting politely, which often didn't happen — a crash, SIGKILL, or forgotten `--release` silently handed its pollution to the next task.) The one thing to remember is the inverse: if you need a slot's data to *survive* a mid-task re-lease, lease with `--reuse` (or `LD_LEASE_CLONE=0`).
4. **Remove the worktree:**
   ```bash
   git worktree remove ../<repo>-task-NNNN-short-description
   ```
   This also discards the worktree's on-disk Umbraco indexes (`<worktree>/src/LegalDesk.Website/umbraco/Data/TEMP`, ~800 MB), so nothing is orphaned.

Why prompt every time: a leftover leased server pins a port + RAM + index data, and an orphaned worktree leaves several hundred MB to a few GB behind (indexes plus `bin`/`obj`/`node_modules`) — these accumulate across tasks. PR-creation is the natural checkpoint to clear them. And because teardown is where the session ends, it's also the last chance to catch an unresolved work item, an unlinked PR, or a review nobody was asked for — which is why the audit above runs first. (See `~/.claude/projects/<project>/memory/reference_multi_instance_dev_servers.md` and the `ld-dev-server` skill.)

### Last step: announce the PR in Slack — only once the user confirms

Every PR is announced in **`#pull-requests`** (`C06FK0APYVC`) by its author. A PR that was never posted there is effectively invisible: nobody watches Azure DevOps for new PRs, so skipping this leaves the work unreviewed.

**As soon as the PR is created, ask: "Shall I post it to `#pull-requests`?"** Then wait. Posting is the final action of the whole workflow — nothing follows it — so the sequence is: create the PR, ask, prompt for teardown, and post once they say yes.

**The question is asked every single time, and only an explicit yes authorises it.** It is not implied by the PR being ready, by the user having asked you to open the PR, or by them confirming teardown — none of those carry over. Posting is outward-facing and lands in front of the whole team, so the user decides when the team sees it. There is no standing approval for it.

Once they confirm, **create a draft — never send.** Use `slack_send_message_draft` so the message lands in their Drafts for them to post; `slack_send_message` is not used in this workspace (see `~/.claude/projects/<project>/memory/feedback_slack_draft_never_send.md`). So there are two gates, not one: confirmation to draft, and the user's own hand to post.

One message per PR, no thread, no commentary, exactly this shape:

```
<repo>: <PR title>
<PR URL>
```

`<repo>` is the **repository** shorthand — `V2` for LegalDesk-V2, `V1` for the legacy repo. It is *not* a version of the change and never varies by task; it tells readers which codebase the PR lands in. `<PR title>` is the PR's title verbatim, so the channel and the PR agree.

```
V2: Task 10834: Checkout: correct discount calculation for add-on bundles
https://dev.azure.com/legaldesk/Legal%20Desk/_git/LegalDesk-V2/pullrequest/7029
```

**Never add attribution.** No "posted by Claude", no "generated with", no bot signature, no emoji flourish — nothing beyond the two lines above. The message must be indistinguishable from one the user typed, exactly as with commit trailers and PR descriptions.

Two channel-name traps: `#pr` is a *public relations* channel with nothing to do with pull requests, and searching Slack for "pull request" finds nothing because these messages contain only a title and a URL. Search `pullrequest` (the URL fragment), or go straight to `#pull-requests`.

## Common PR pushback (pre-empt it before pushing)

These are recurring review comments on LegalDesk PRs. Scan the diff for them in Phase 6 before committing, so you don't burn a review round on a known nit.

- **Magic-string Umbraco property access** (reviewer: Biraj — flagged on PR 6350 and PR 6352). In any Razor view/partial, controller, or service touching Umbraco content, use strongly-typed `ContentModels.*` accessors, not string aliases:
  - `Model is ContentModels.ProductCategory pc` instead of `Model.ContentType.Alias == "productCategory"`
  - `pc.PageManchet` instead of `Model.Value<string>("pageManchet")`
  - `pc.OGimage?.Url()` instead of `Model.Value<IPublishedContent>("OGimage")?.Url()`

  Generated models live under `src/LegalDesk.Infrastructure/Models/CmsModels/*.generated.cs`; the `ContentModels` alias is set up in `Views/_ViewImports.cshtml`. **Improve on the way out** — convert even pre-existing magic-string lines you *touch*, not just brand-new code. The only acceptable exception is when no generated accessor exists (a composition not surfaced on that doc type) — then leave `Value<>("alias")` with a one-line comment explaining why.

- **Tests must exercise the public API only** (reviewer: Vladica — PR #6448: *"your tests are not good. You should rely on dependency injection and mocking of services."*). Don't bend production code's encapsulation to make a test writeable:
  - No `static` / `[InternalsVisibleTo]` seams added just so a test can reach a method.
  - No reflection on private entity setters (same anti-pattern, softer form).
  - Instead: instantiate the concrete service with NSubstitute-mocked dependencies and call only its **public** methods; build domain entities via their public factory methods (e.g. `Product.CreateTimeline(template, requiredIds)`). For EF `.Include().ThenInclude()...ToListAsync(ct)` chains, mock the `IQueryable` with `MockQueryable.NSubstitute`'s `BuildMock()`.
  - If you can't reach the behavior through the public surface, the test is at the wrong layer — move it, don't widen visibility.

Both reviewers apply the same underlying principle: **don't weaken type-safety or encapsulation to make the change easier — leave the code better than you found it.**

## Common detours and how to handle them

- **Auth/storage state expired**: re-run the auth setup project, then re-run the spec. Don't pretend it's an env config problem when it's a stale cookie.
- **Env vars missing**: surface the requirement clearly. For tests using third-party test modes (Reepay test cards, Stripe test mode), set sensible public defaults and override via env var.
- **API schema mismatch**: log the actual response once when assertions fail, then write code defensive against the real shape (e.g., `JSON.stringify(item).includes(needle)` is robust against ProductId being a number vs string).
- **Timezone parsing**: .NET `DateTime` serialized as `"2026-04-27T19:13:14"` (no `Z`) parses as **local time** in JS. Force UTC: `new Date(/[Zz]$|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z')`.
- **Headed works, headless fails**: usually real keystroke events matter for reactive frameworks (Angular, React). Use `pressSequentially` not `fill`, and `press('Tab')` after each field to trigger blur/validate.
- **Selector hangs in headless mode**: the iframe/structure assumption was wrong. Open in headed mode and inspect the actual DOM.
- **Cleanup endpoint silently no-ops**: check if the endpoint requires admin auth (`IsUmbracoAdminUser` or equivalent). Run cleanup from a separately-authenticated admin context, not the member context.
- **Build artifacts drifted on develop**: when `yarn build` shows unrelated diffs in checked-in bundles, commit those as a separate "rebuild artifacts" commit, not as part of the fix.

## What this skill does not do

- Open the PR (the user opens it after reviewing the branch).
- Merge, deploy, or affect shared/production state beyond the feature branch.
- Replace human review of the fix's correctness — the test is necessary but not sufficient.
- Force a TDD shape on tasks where it doesn't fit. Phase 1 catches this; if it slips through, surface it as soon as you notice and ask the user before continuing.

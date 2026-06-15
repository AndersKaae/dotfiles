---
name: task-tdd
description: Resolve a tracked work item (Azure DevOps, GitHub Issue, Jira, etc.) using a strict test-driven workflow — fetch the task, agree on scope, scope the test, create a git worktree branched off develop, write a failing test that captures the bug or feature, verify it fails for the right reason, implement the fix, verify it turns green, then commit and push as separate test/fix commits. Use when the user references a work-item URL or task number and wants to address it via TDD ("let's fix task X using TDD", "do this with a failing test first", "TDD this", "address ticket Y test-first").
---

# Task TDD workflow

A seven-phase loop for resolving a tracked work item using TDD with explicit scope alignment up-front and clean commit hygiene at the end. Run the phases in order. Don't skip — each phase prevents a specific failure mode that's expensive to recover from later.

## Phase 1: Get the task

Fetch the work item directly from its tracker. Don't use `WebFetch` against authenticated trackers — it'll just hit the login page.

**Azure DevOps** (the LegalDesk default):
```bash
az boards work-item show --id <ID> --organization https://dev.azure.com/<org> --output json
```
Description is HTML in `fields["System.Description"]`. Parent id is in the top-level `relations` array — entries with `rel: "System.LinkTypes.Hierarchy-Reverse"` point to the parent. Fetch the parent for context if the child describes "item N" of a list. Useful fields: `System.Title`, `System.WorkItemType`, `System.State`, `System.Tags`, `System.Parent`, `System.IterationPath`.

**GitHub**: `gh issue view <ID> --json number,title,body,state,labels,assignees`.
**Jira**: `acli jira workitem view <ID>` or the official `jira` CLI.

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

## Phase 4: Create a worktree off develop

**All work happens in a dedicated git worktree branched from `develop`** — never in the primary checkout, and never branched from whatever happens to be checked out. This keeps the main working tree untouched, isolates the task, and guarantees a clean base regardless of the current branch.

Naming convention: branch `task-<ID>-<kebab-case-summary>` to match repo history; worktree directory as a sibling of the repo, e.g. `../<repo>-task-<ID>`. Confirm the repo's host before creating — Azure DevOps repos use `az repos pr create` later, not `gh`. Check `~/.claude/projects/<project>/memory/reference_code_host.md` if it exists.

```bash
# run from inside the primary repo checkout
git fetch origin develop
git worktree add ../<repo>-task-NNNN-short-description -b task-NNNN-short-description origin/develop
cd ../<repo>-task-NNNN-short-description
```

Branch from `origin/develop` (freshly fetched), not local `develop`, so the base is up to date even if the local tip is stale.

**Worktrees start cold** — git-ignored config and installed dependencies do not carry over. For LegalDesk-V2: copy `appsettings.Development.json` and `tests/e2e/.env.local` from the primary checkout, run `npm install` in `tests/e2e`, and expect a 2-3 min first build/cold start. See `~/.claude/projects/<project>/memory/reference_git_worktree_setup.md` if present for the project's exact setup steps.

Don't commit anything yet. Run the rest of the workflow (Phases 5-7) from inside this worktree. When the task is fully done — PR opened, merged, or abandoned — remove the worktree so it doesn't linger:

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

If the fix is in a layer that compiles or bundles to a different artifact (Vue → JS bundle, TS → JS, SCSS → CSS), rebuild whatever the test actually consumes. Don't assume the test runs against your source.

Run the test again. Expect:
- The previously-red assertion is now green
- Every other test in the spec is still green
- No new warnings/errors in stdout
- Cleanup hooks ran successfully

If a test now passes that was passing *before* the test scaffolding existed, investigate — could be a regression introduced by the test setup itself.

Once green, **promote** the test out of any "pending" tier or `.skip` gate into the default-running tier so future runs catch regressions. Update the test name if it still says "FAILING" or similar TDD-mid-flow language.

## Phase 7: Commit and push

Two separate commits on the feature branch:

1. **The test commit.** Stage only the test file(s) and any test-infra changes. Message:
   `Task NNNN: Failing TDD test for <one-line-summary>`
2. **The fix commit.** Stage production code changes plus any rebuilt artifacts. Message:
   `Task NNNN: <imperative description of the change>`

Use HEREDOC for commit messages with line breaks (per CLAUDE.md commit guidelines). Include `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` if the codebase uses Claude co-authorship.

If the build emitted unrelated artifacts (rebuild picked up upstream source drift), commit those as a separate "Rebuild artifacts to match current source" commit so the fix commit stays focused.

Push:
```bash
git push -u origin task-NNNN-short-description
```

**Don't open the PR unless the user asks.** Provide the CLI command and a web-UI fallback URL so they can decide:

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

#!/usr/bin/env python3
"""Collect every open Azure DevOps PR and classify it by what is blocking it.

Read-only. Emits JSON (--json) or a markdown table (default).
Auth: PAT from ~/azure.key (override with AZDO_PAT).
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

ORG = os.environ.get("AZDO_ORG", "legaldesk")
PROJECT = os.environ.get("AZDO_PROJECT", "Legal Desk")
REPO = os.environ.get("AZDO_REPO", "LegalDesk-V2")
BASE = f"https://dev.azure.com/{ORG}/{urllib.parse.quote(PROJECT)}/_apis"
WEB = f"https://dev.azure.com/{ORG}/{urllib.parse.quote(PROJECT)}/_git/{REPO}"

# Reviewer vote values (Azure DevOps)
VOTE = {10: "approved", 5: "approved w/ suggestions", 0: "no vote",
        -5: "waiting for author", -10: "rejected"}


def _pat():
    pat = os.environ.get("AZDO_PAT")
    if not pat:
        path = os.path.expanduser("~/azure.key")
        if not os.path.exists(path):
            sys.exit("No PAT: set AZDO_PAT or create ~/azure.key")
        with open(path) as fh:
            pat = fh.read()
    return pat.strip()


AUTH = "Basic " + base64.b64encode(f":{_pat()}".encode()).decode()


def get(url):
    req = urllib.request.Request(url, headers={"Authorization": AUTH,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        if exc.code in (401, 203):
            raise SystemExit("Azure DevOps rejected the PAT (HTTP %d). Check "
                             "~/azure.key / $AZDO_PAT is current and has "
                             "Code:Read + Build:Read." % exc.code) from exc
        raise SystemExit(f"HTTP {exc.code} on {url}\n{body}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # ADO answers an unauthenticated request with an HTML sign-in page
        hint = ("Azure DevOps returned a sign-in page instead of JSON - the PAT "
                "in ~/azure.key / $AZDO_PAT is invalid or expired."
                if raw[:100].lstrip().startswith(b"<") else raw[:200].decode(errors="replace"))
        raise SystemExit(hint) from exc


def _parse(iso):
    if not iso:
        return None
    return datetime.fromisoformat(re.sub(r"\.\d+", "", iso).replace("Z", "+00:00"))


def age_days(iso):
    dt = _parse(iso)
    return None if dt is None else (datetime.now(timezone.utc) - dt).days


def age_hours(iso):
    dt = _parse(iso)
    return None if dt is None else (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def list_prs(include_drafts):
    url = (f"{BASE}/git/repositories/{REPO}/pullrequests"
           "?searchCriteria.status=active&$top=500&api-version=7.1")
    prs = get(url)["value"]
    if not include_drafts:
        prs = [p for p in prs if not p.get("isDraft")]
    return prs


def project_id(pr):
    # the PR url embeds the project guid: /_apis is preceded by <org>/<projectId>/
    m = re.search(r"dev\.azure\.com/[^/]+/([0-9a-f-]{36})/", pr["url"])
    return m.group(1) if m else None


def policies(pid, pr_id):
    art = f"vstfs:///CodeReview/CodeReviewId/{pid}/{pr_id}"
    url = (f"{BASE}/policy/evaluations?artifactId={urllib.parse.quote(art, safe='')}"
           "&api-version=7.1-preview.1")
    return get(url)["value"]


def threads(pr_id):
    url = (f"{BASE}/git/repositories/{REPO}/pullRequests/{pr_id}"
           "/threads?api-version=7.1")
    return get(url)["value"]


def failed_stages(build_id):
    url = f"{BASE}/build/builds/{build_id}/timeline?api-version=7.1"
    try:
        records = get(url)["records"]
    except SystemExit:
        return []
    return sorted(r["name"] for r in records
                  if r.get("type") == "Stage" and r.get("result") == "failed")


def classify(pr):
    pid = project_id(pr)
    pr_id = pr["pullRequestId"]
    row = {
        "id": pr_id,
        "title": pr["title"],
        "author": pr["createdBy"]["displayName"],
        "draft": bool(pr.get("isDraft")),
        "source": pr["sourceRefName"].replace("refs/heads/", ""),
        "target": pr["targetRefName"].replace("refs/heads/", ""),
        "age": age_days(pr.get("creationDate")),
        "url": f"{WEB}/pullrequest/{pr_id}",
        "conflicts": pr.get("mergeStatus") == "conflicts",
        "merge_status": pr.get("mergeStatus"),
        "auto_complete": bool(pr.get("autoCompleteSetBy")),
    }

    votes = [(r["displayName"], r.get("vote", 0)) for r in pr.get("reviewers", [])]
    row["approvals"] = [n for n, v in votes if v >= 5]
    row["rejections"] = [n for n, v in votes if v <= -5]
    row["reviewers"] = [f"{n} ({VOTE.get(v, v)})" for n, v in votes]

    # --- comment threads -------------------------------------------------
    unresolved = []
    for t in threads(pr_id):
        comments = t.get("comments") or [{}]
        if comments[0].get("commentType") == "system":
            continue
        if all(c.get("isDeleted") for c in comments):
            continue
        if t.get("status") in ("active", "pending"):
            ctx = t.get("threadContext") or {}
            live = [c for c in comments if not c.get("isDeleted")]
            # The ADO web conflict-editor posts a thread that LOOKS like review
            # feedback but asks for nothing. It needs resolving, never a code fix.
            body = (live[0].get("content") or "") if live else ""
            tool_generated = body.startswith("Submitted conflict resolution")
            unresolved.append({
                "thread": t["id"],
                "tool_generated": tool_generated,
                "by": (live[0].get("author") or {}).get("displayName", "?"),
                "text": " ".join((live[0].get("content") or "").split())[:120],
                # where in the diff the reviewer pointed - None for a PR-level comment
                "file": ctx.get("filePath"),
                "line": (ctx.get("rightFileStart") or ctx.get("leftFileStart")
                         or {}).get("line"),
                # full transcript, so an agent sees any follow-up replies too
                "transcript": [
                    {"by": (c.get("author") or {}).get("displayName", "?"),
                     "text": " ".join((c.get("content") or "").split())}
                    for c in live
                ],
            })
    row["unresolved"] = unresolved

    # --- branch policies -------------------------------------------------
    row["build"] = None
    row["gate"] = None
    row["failed_stages"] = []
    row["build_id"] = None
    row["build_waiting_h"] = None
    for ev in policies(pid, pr_id) if pid else []:
        cfg = ev["configuration"]
        if not cfg.get("isEnabled") or not cfg.get("isBlocking"):
            continue
        kind = cfg["type"]["displayName"]
        ctx = ev.get("context") or {}
        if kind == "Build":
            row["build"] = ev.get("status")          # approved/rejected/queued/running
            row["build_id"] = ctx.get("buildId")
            # how long THIS evaluation has sat in its current state - not PR age
            row["build_waiting_h"] = age_hours(ev.get("startedDate"))
            if ev.get("status") == "rejected" and ctx.get("buildId"):
                row["failed_stages"] = failed_stages(ctx["buildId"])
        elif kind == "Status":
            s = cfg.get("settings", {})
            row["gate"] = ev.get("status")
            row["gate_name"] = f"{s.get('statusGenre')}/{s.get('statusName')}"

    # --- blockers, most-severe first -------------------------------------
    stages = row["failed_stages"]
    # A build that failed ONLY in E2E while the unit-tests gate is green is the
    # repo's most common false block: E2E is flaky here and is meant to report,
    # not gate. Call it out separately so it is never confused with a real break.
    # An absent policy is a satisfied policy - not every repo defines both.
    gate_ok = row["gate"] in (None, "approved")
    row["e2e_only"] = bool(stages) and all("E2E" in s for s in stages) and gate_ok

    blockers = []
    if row["conflicts"]:
        blockers.append("conflicts")
    if row["build"] == "rejected":
        blockers.append("e2e-only" if row["e2e_only"] else "failed")
    if row["unresolved"]:
        blockers.append("comments")
    if row["rejections"]:
        blockers.append("changes-requested")
    if row["build"] in ("queued", "running") or row["gate"] == "pending":
        # A conflicted PR has no mergeable commit to build, so its queued build
        # is a symptom of the conflict, not an independent blocker.
        if not row["conflicts"]:
            waited = row["build_waiting_h"] or 0
            blockers.append("stuck-queue" if waited >= 12 else "running")
    row["blockers"] = blockers

    green = row["build"] in (None, "approved") and gate_ok
    if blockers:
        bucket = blockers[0]
    elif green and row["approvals"]:
        bucket = "ready"
    elif green:
        bucket = "needs-review"
    else:
        bucket = "other"
    row["bucket"] = bucket
    return row


def stacks(rows, target="develop"):
    """Group selected PRs into dependency stacks using the LOCAL git repo.

    A branch built on top of another PR's branch replays that PR's commits, so
    two branches sharing commit subjects above {target} are one stack. Dispatching
    them in parallel is wrong: fixing the base rewrites commits the tip is still
    carrying a stale copy of.
    """
    def git(*args):
        return subprocess.run(("git",) + args, capture_output=True, text=True).stdout

    subprocess.run(["git", "fetch", "-q", "origin"], capture_output=True)
    subjects = {}
    for r in rows:
        out = git("log", "--format=%s", f"origin/{target}..origin/{r['source']}")
        subjects[r["id"]] = set(filter(None, out.splitlines()))

    groups = []
    for r in sorted(rows, key=lambda r: len(subjects[r["id"]])):
        for g in groups:
            if any(subjects[r["id"]] & subjects[m["id"]] for m in g):
                g.append(r)
                break
        else:
            groups.append([r])
    # within a stack, fewest commits above target == closest to the base
    return [sorted(g, key=lambda r: len(subjects[r["id"]])) for g in groups]


BUCKETS = [
    ("ready", "Green + approved, not merged", "MERGE IT"),
    ("e2e-only", "Approved, only E2E red (unit gate green)", "re-run E2E or complete"),
    ("conflicts", "Merge conflicts", "rebase on develop"),
    ("failed", "Failed tests", "fix the build"),
    ("comments", "Unresolved comments", "answer / resolve the threads"),
    ("changes-requested", "Changes requested", "address the reviewer"),
    ("needs-review", "Green, awaiting approval", "chase a reviewer"),
    ("stuck-queue", "Build stuck >12h", "queue is backed up \u2014 check the agent pool"),
    ("running", "Build in flight", "wait"),
    ("other", "Other", "inspect"),
]


def state_cell(r):
    """Every reason this PR is not merged, not just the top one."""
    parts = []
    for b in r["blockers"]:
        if b == "conflicts":
            parts.append("conflicts")
        elif b == "failed":
            parts.append("FAILED: " + (", ".join(r["failed_stages"]) or "build"))
        elif b == "e2e-only":
            parts.append("E2E red (unit gate green)")
        elif b == "comments":
            parts.append(f"{len(r['unresolved'])} unresolved")
        elif b == "changes-requested":
            parts.append("rejected by " + ", ".join(r["rejections"]))
        elif b == "stuck-queue":
            parts.append(f"build {r['build'] or r['gate']} "
                         f"{(r['build_waiting_h'] or 0) / 24:.1f}d")
        elif b == "running":
            parts.append(f"build {r['build'] or r['gate']}")
    if not parts:
        parts.append("green + approved" if r["approvals"] else "green, 0 approvals")
    if r["auto_complete"]:
        parts.append("auto-complete on")
    return "; ".join(parts)


def markdown(rows):
    order = {b: i for i, (b, _, _) in enumerate(BUCKETS)}
    rows = sorted(rows, key=lambda r: (order[r["bucket"]], -(r["age"] or 0)))
    out = [f"## Open PRs — {ORG}/{PROJECT}/{REPO} ({len(rows)})", ""]
    out.append("| PR | Title | Author | Age | Blocked by | Approvals | Action |")
    out.append("|---|---|---|---|---|---|---|")
    for r in rows:
        label = next(a for b, _, a in BUCKETS if b == r["bucket"])
        title = r["title"].replace("|", "\\|")
        title = title[:57] + "…" if len(title) > 58 else title
        appr = ", ".join(r["approvals"]) or "—"
        draft = " _(draft)_" if r["draft"] else ""
        out.append(f"| [{r['id']}]({r['url']}) | {title}{draft} | {r['author']} "
                   f"| {r['age']}d | {state_cell(r)} | {appr} | {label} |")
    out.append("")
    for bucket, heading, action in BUCKETS:
        hits = [r for r in rows if r["bucket"] == bucket]
        if not hits:
            continue
        out.append(f"### {heading} ({len(hits)}) — {action}")
        for r in hits:
            out.append(f"- **{r['id']}** {r['title']} — {r['author']}, {r['age']}d")
            if r["failed_stages"]:
                out.append(f"  - failed stage(s): {', '.join(r['failed_stages'])} "
                           f"(build {r['build_id']})")
            for t in r["unresolved"]:
                where = f" [{t['file']}:{t['line']}]" if t.get("file") else ""
                tag = " *(tool-generated — resolve, no code change)*" \
                    if t.get("tool_generated") else ""
                out.append(f"  - thread {t['thread']} ({t['by']}){where}: "
                           f"{t['text']}{tag}")
            if bucket == "ready" and r["auto_complete"]:
                out.append("  - auto-complete is set — it is waiting on a policy, not a human")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    ap.add_argument("--drafts", action="store_true", help="include draft PRs")
    ap.add_argument("--author", help="filter by author substring (case-insensitive)")
    ap.add_argument("--bucket", help="only PRs whose TOP blocker is this bucket")
    ap.add_argument("--blocker", help="only PRs carrying this blocker ANYWHERE "
                                      "(what dispatch should select on)")
    ap.add_argument("--stacks", action="store_true",
                    help="group the selected PRs into dependency stacks and "
                         "print the order to dispatch them in")
    args = ap.parse_args()

    prs = list_prs(args.drafts)
    if args.author:
        prs = [p for p in prs
               if args.author.lower() in p["createdBy"]["displayName"].lower()
               or args.author.lower() in p["createdBy"].get("uniqueName", "").lower()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(classify, prs))
    if args.bucket:
        rows = [r for r in rows if r["bucket"] == args.bucket]
    if args.blocker:
        rows = [r for r in rows if args.blocker in r["blockers"]]
    if args.stacks:
        for i, group in enumerate(stacks(rows), 1):
            if len(group) == 1:
                print(f"independent: {group[0]['id']} ({group[0]['source']})")
            else:
                print(f"stack {i} - dispatch IN THIS ORDER, one at a time:")
                for depth, r in enumerate(group):
                    print(f"  {depth + 1}. {r['id']} ({r['source']})"
                          + ("  <- base" if depth == 0 else "  <- rebase after the one above"))
        return
    print(json.dumps(rows, indent=2) if args.json else markdown(rows))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Sweep the work items assigned to you and judge which are genuinely still open.

Read-only by default. Emits JSON (--json) or a markdown table.
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
USER = os.environ.get("AZDO_USER", "anders@legaldesk.dk")
TARGET = os.environ.get("AZDO_TARGET_BRANCH", "develop")
BASE = f"https://dev.azure.com/{ORG}/{urllib.parse.quote(PROJECT)}/_apis"
WEB = f"https://dev.azure.com/{ORG}/{urllib.parse.quote(PROJECT)}"


def _pat():
    pat = os.environ.get("AZDO_PAT")
    if not pat:
        path = os.path.expanduser("~/azure.key")
        if not os.path.exists(path):
            sys.exit("No PAT: set AZDO_PAT or create ~/azure.key")
        pat = open(path).read()
    return pat.strip()


AUTH = "Basic " + base64.b64encode(f":{_pat()}".encode()).decode()


def call(url, method="GET", body=None, ctype="application/json"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": AUTH,
                                          "Accept": "application/json",
                                          "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise SystemExit(f"HTTP {exc.code} on {method} {url}\n{detail}") from exc
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        if raw[:100].lstrip().startswith(b"<"):
            raise SystemExit("Azure DevOps returned a sign-in page - the PAT in "
                             "~/azure.key / $AZDO_PAT is invalid or expired.") from exc
        raise


def git(*args):
    return subprocess.run(("git",) + args, capture_output=True, text=True).stdout


def age_days(iso):
    if not iso:
        return None
    iso = re.sub(r"\.\d+", "", iso).replace("Z", "+00:00")
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).days


def assigned_ids():
    q = (f"SELECT [System.Id] FROM WorkItems "
         f"WHERE [System.AssignedTo] = '{USER}' "
         f"AND [System.State] <> 'Closed' AND [System.State] <> 'Removed' "
         f"ORDER BY [System.ChangedDate] DESC")
    res = call(f"{BASE}/wit/wiql?api-version=7.1", "POST", {"query": q})
    return [w["id"] for w in res.get("workItems", [])]


def fetch_items(ids):
    out = []
    for i in range(0, len(ids), 190):          # batch endpoint caps at 200
        chunk = ",".join(map(str, ids[i:i + 190]))
        out += call(f"{BASE}/wit/workitems?ids={chunk}&$expand=relations"
                    f"&api-version=7.1")["value"]
    return out


def type_states(wit, _cache={}):
    """Which states this work item type allows. The Agile template gives Task
    only New/Active/Closed - there is NO Resolved state for a Task, while Bug and
    User Story do have one. Never assume; ask."""
    if wit not in _cache:
        enc = urllib.parse.quote(wit)
        try:
            d = call(f"{BASE}/wit/workitemtypes/{enc}/states?api-version=7.1")
            _cache[wit] = [x["name"] for x in d.get("value", [])]
        except SystemExit:
            _cache[wit] = []
    return _cache[wit]


def pr_state(pr_id, _cache={}):
    if pr_id not in _cache:
        try:
            d = call(f"{BASE}/git/repositories/{REPO}/pullRequests/{pr_id}"
                     "?api-version=7.1")
            _cache[pr_id] = d.get("status")
        except SystemExit:
            _cache[pr_id] = "unknown"
    return _cache[pr_id]


def reopen_history(wid):
    """Find a reopen that was later re-resolved.

    A creator flipping an item back to Active with reason "Not fixed" is the
    strongest possible signal it did not ship. If it is Resolved again now, the
    re-resolve must be backed by work that landed AFTER the reopen - otherwise
    someone clicked Resolved without fixing anything, and handing it back would
    bounce the reporter the same item they already rejected.
    """
    try:
        ups = call(f"{BASE}/wit/workitems/{wid}/updates?api-version=7.1")["value"]
    except SystemExit:
        return None
    last_reopen = None
    for u in ups:
        st = (u.get("fields") or {}).get("System.State") or {}
        old, new = st.get("oldValue"), st.get("newValue")
        if old in ("Resolved", "Closed") and new in ("Active", "New"):
            reason = ((u.get("fields") or {}).get("System.Reason") or {}).get("newValue")
            by = (u.get("revisedBy") or {}).get("displayName", "?")
            last_reopen = {"when": u.get("revisedDate"), "by": by, "reason": reason}
    return last_reopen


def assess(item):
    f = item["fields"]
    wid = item["id"]
    created_by = f.get("System.CreatedBy") or {}
    row = {
        "id": wid,
        "title": f.get("System.Title", ""),
        "type": f.get("System.WorkItemType"),
        "state": f.get("System.State"),
        "created_by": created_by.get("displayName", "?"),
        "created_by_email": created_by.get("uniqueName", ""),
        "idle": age_days(f.get("System.ChangedDate")),
        "url": f"{WEB}/_workitems/edit/{wid}",
    }

    # --- linked pull requests -------------------------------------------
    linked = []
    for rel in item.get("relations") or []:
        if rel.get("rel") == "ArtifactLink" and "PullRequestId" in rel.get("url", ""):
            m = re.search(r"%2F(\d+)$", rel["url"])
            if m:
                linked.append(int(m.group(1)))
    row["linked_prs"] = [{"id": p, "status": pr_state(p)} for p in linked]
    row["open_pr"] = [p["id"] for p in row["linked_prs"] if p["status"] == "active"]
    row["merged_pr"] = [p["id"] for p in row["linked_prs"] if p["status"] == "completed"]

    # --- merged evidence in git history ---------------------------------
    # "Merged PR 7192: Task 10981: ..." on the target branch is the strongest
    # signal a task shipped, and it exists even when nobody linked the PR.
    log = git("log", f"origin/{TARGET}", "--oneline",
              f"--grep=Task {wid}", "-i", "--max-count=20").splitlines()
    row["merge_commits"] = [l for l in log if l.split(" ", 1)[-1].startswith("Merged PR")]
    row["branch_commits"] = [l for l in log if l not in row["merge_commits"]]

    # --- verdict ---------------------------------------------------------
    # Policy: opening a PR means the item becomes Resolved and goes back to its
    # creator, who decides whether to Close it. We never set Closed ourselves.
    has_pr = bool(row["merged_pr"] or row["merge_commits"] or row["open_pr"])
    mine = row["created_by_email"].lower() == USER.lower()
    row["creator_is_me"] = mine

    # Was it rejected once and quietly re-resolved with nothing shipped since?
    row["reopened"] = reopen_history(wid) if row["state"] in ("Resolved", "Closed") else None
    if row["reopened"]:
        when = row["reopened"]["when"]
        since = git("log", f"origin/{TARGET}", "--oneline",
                    f"--since={when}", f"--grep=Task {wid}", "-i").splitlines()
        row["commits_since_reopen"] = since

    row["states_available"] = type_states(row["type"])
    # A Task has no Resolved state, so Closed IS its "done, handed back" state.
    # Bug and User Story keep Resolved, where Closed stays the creator's call.
    row["has_resolved_state"] = "Resolved" in row["states_available"]
    row["done_state"] = "Resolved" if row["has_resolved_state"] else "Closed"

    done = row["state"] in ("Resolved", "Closed")
    merged = bool(row["merged_pr"] or row["merge_commits"])
    if done:
        if not (merged or row["open_pr"]):
            verdict = "resolved-no-evidence"
        elif not merged:
            # Resolved ahead of the merge. Do NOT hand this to the reporter to
            # verify - there is nothing on develop for them to look at yet.
            verdict = "resolved-pr-still-open"
        elif row["reopened"] and not row.get("commits_since_reopen"):
            verdict = "reresolved-without-work"
        elif mine:
            verdict = "resolved-mine"           # nothing to hand back
        else:
            verdict = "needs-handback"          # state right, ownership wrong
    elif has_pr:
        verdict = "needs-resolve"
    else:
        verdict = "genuinely-open"
    row["verdict"] = verdict
    return row


VERDICTS = [
    ("needs-resolve", "Has a PR but is not in a done state",
     "set its done state (Resolved, or Closed for a Task), then hand back"),
    ("needs-handback", "Resolved but still in your queue",
     "reassign to the creator so they can verify and close"),
    ("resolved-no-evidence", "Resolved but no PR found anywhere",
     "VERIFY - the fix may never have landed"),
    ("reresolved-without-work", "Reopened as 'not fixed', then re-resolved with nothing shipped",
     "DO NOT hand back - the reporter already rejected this once"),
    ("resolved-pr-still-open", "Resolved, but its PR has not merged",
     "wait for the merge - do not hand back yet"),
    ("resolved-mine", "Resolved, and you created it",
     "nothing to hand back - yours to close when you are satisfied"),
    ("genuinely-open", "Genuinely open", "real work"),
]


def markdown(rows):
    order = {v: i for i, (v, _, _) in enumerate(VERDICTS)}
    rows = sorted(rows, key=lambda r: (order[r["verdict"]], -(r["idle"] or 0)))
    out = [f"## Work items assigned to {USER} ({len(rows)} not closed)", "",
           "| ID | Type | Title | State | Idle | Evidence | Verdict |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        title = r["title"].replace("|", "\\|")
        title = title[:52] + "…" if len(title) > 53 else title
        ev = []
        if r["merged_pr"]:
            ev.append("PR " + ", ".join(f"!{p}" for p in r["merged_pr"]) + " merged")
        if r["merge_commits"] and not r["merged_pr"]:
            m = re.search(r"Merged PR (\d+)", r["merge_commits"][0])
            ev.append(f"PR {m.group(1)} on {TARGET}" if m else f"on {TARGET}")
        if r["open_pr"]:
            ev.append("PR " + ", ".join(f"!{p}" for p in r["open_pr"]) + " open")
        label = next(h for v, h, _ in VERDICTS if v == r["verdict"])
        out.append(f"| [{r['id']}]({r['url']}) | {r['type']} | {title} | {r['state']} "
                   f"| {r['idle']}d | {'; '.join(ev) or '—'} | {label} |")
    out.append("")
    for verdict, heading, action in VERDICTS:
        hits = [r for r in rows if r["verdict"] == verdict]
        if not hits:
            continue
        out.append(f"### {heading} ({len(hits)}) — {action}")
        for r in hits:
            out.append(f"- **{r['id']}** {r['title']} — created by {r['created_by']}, "
                       f"idle {r['idle']}d")
            for c in r["merge_commits"][:2]:
                out.append(f"  - `{c}`")
        out.append("")
    return "\n".join(out)


def update_item(wid, state=None, assignee=None, comment=None, allow_closed=False):
    """Patch an item. We only ever set Resolved - Closed is the creator's call."""
    if state and state.lower() == "closed" and not allow_closed:
        raise SystemExit("refusing to set Closed on a type that has a Resolved "
                         "state: this workflow marks items Resolved and leaves "
                         "the Close decision to whoever reported them.")
    ops = []
    if state:
        ops.append({"op": "add", "path": "/fields/System.State", "value": state})
    if assignee:
        ops.append({"op": "add", "path": "/fields/System.AssignedTo", "value": assignee})
    if comment:
        ops.append({"op": "add", "path": "/fields/System.History", "value": comment})
    if not ops:
        raise SystemExit("nothing to update")
    return call(f"{BASE}/wit/workitems/{wid}?api-version=7.1", "PATCH", ops,
                ctype="application/json-patch+json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verdict", help="only this verdict")
    ap.add_argument("--resolve", type=int, metavar="ID",
                    help="mark Resolved and hand back to the creator")
    ap.add_argument("--handback", type=int, metavar="ID",
                    help="reassign to the creator, leaving the state alone")
    ap.add_argument("--comment", help="history note to attach to the update")
    args = ap.parse_args()

    wid = args.resolve or args.handback
    if wid:
        item = fetch_items([wid])[0]
        creator = (item["fields"].get("System.CreatedBy") or {}).get("uniqueName", "")
        # Never reassign an item back to yourself - that is a no-op that just
        # churns the history. Leave your own items where they are.
        assignee = creator if creator.lower() != USER.lower() else None
        wit = item["fields"].get("System.WorkItemType", "")
        # Closed is only allowed where the type offers nothing better.
        done = "Resolved" if "Resolved" in type_states(wit) else "Closed"
        update_item(wid, state=done if args.resolve else None,
                    assignee=assignee, comment=args.comment,
                    allow_closed=(done == "Closed"))
        did = [done] if args.resolve else []
        did += [f"handed to {assignee}"] if assignee else ["kept (you created it)"]
        print(f"{wid}: {', '.join(did)}")
        return

    subprocess.run(["git", "fetch", "-q", "origin"], capture_output=True)
    items = fetch_items(assigned_ids())
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(assess, items))
    if args.verdict:
        rows = [r for r in rows if r["verdict"] == args.verdict]
    print(json.dumps(rows, indent=2) if args.json else markdown(rows))


if __name__ == "__main__":
    main()

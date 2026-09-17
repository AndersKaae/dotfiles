#!/usr/bin/env python3
"""Find Azure DevOps work items by shape, reading the body field that actually holds the text.

The whole point of this script: a Bug in the Legal Desk project stores its body in
Microsoft.VSTS.TCM.ReproSteps, NOT System.Description. Querying only Description makes
every Bug look empty and silently hides the best-specified tickets in the backlog.

Read-only. Emits a markdown table or JSON (--json).
Auth: PAT from ~/azure.key (override with AZDO_PAT).
"""
import argparse
import base64
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ORG = os.environ.get("AZDO_ORG", "legaldesk")
PROJECT = os.environ.get("AZDO_PROJECT", "Legal Desk")
USER = os.environ.get("AZDO_USER", "anders@legaldesk.dk")
BASE = f"https://dev.azure.com/{ORG}/{urllib.parse.quote(PROJECT)}/_apis"
WEB = f"https://dev.azure.com/{ORG}/{urllib.parse.quote(PROJECT)}/_workitems/edit"

# Every field that can hold a work item's body, in the order we prefer them.
# ReproSteps first: Bug is the most common type here and it is where Bugs keep their text.
BODY_FIELDS = [
    "Microsoft.VSTS.TCM.ReproSteps",
    "System.Description",
    "Microsoft.VSTS.Common.AcceptanceCriteria",
    "Microsoft.VSTS.TCM.SystemInfo",
]

FIELDS = [
    "System.Id", "System.WorkItemType", "System.State", "System.Title",
    "System.AssignedTo", "System.CreatedBy", "System.CreatedDate",
    "System.ChangedDate", "System.Tags",
] + BODY_FIELDS

DONE_STATES = ("Resolved", "Closed", "Removed", "Done")


def _pat():
    pat = os.environ.get("AZDO_PAT")
    if not pat:
        path = os.path.expanduser("~/azure.key")
        if not os.path.exists(path):
            sys.exit("No PAT: set AZDO_PAT or create ~/azure.key")
        pat = open(path).read()
    return pat.strip()


AUTH = "Basic " + base64.b64encode(f":{_pat()}".encode()).decode()


def call(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": AUTH, "Accept": "application/json",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise SystemExit(f"HTTP {exc.code} on {method} {url}\n{detail}") from exc
    if not raw:
        return {}
    if raw[:100].lstrip().startswith(b"<"):
        raise SystemExit("Azure DevOps returned HTML, not JSON - the PAT in "
                         "~/azure.key is probably expired.")
    return json.loads(raw)


def strip_html(s):
    """ADO bodies are HTML. Flatten to text without collapsing paragraph breaks."""
    if not s:
        return ""
    s = re.sub(r"<(br|/p|/div|/li|/tr)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def body_of(fields):
    """Return (text, which_field). Tries every body field, longest wins."""
    best, best_name = "", None
    for name in BODY_FIELDS:
        text = strip_html(fields.get(name))
        if len(text) > len(best):
            best, best_name = text, name
    return best, best_name


def wiql(where, order="[System.ChangedDate] DESC"):
    q = f"SELECT [System.Id] FROM WorkItems WHERE {where} ORDER BY {order}"
    res = call(f"{BASE}/wit/wiql?api-version=7.0", "POST", {"query": q})
    return [w["id"] for w in res.get("workItems", [])]


def fetch(ids):
    """Batch-fetch full fields. ADO caps ids per request, so chunk."""
    out = []

    def one(chunk):
        url = (f"{BASE}/wit/workitems?ids={','.join(map(str, chunk))}"
               f"&fields={','.join(FIELDS)}&api-version=7.0")
        return call(url).get("value", [])

    chunks = [ids[i:i + 180] for i in range(0, len(ids), 180)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for part in pool.map(one, chunks):
            out += part
    return out


# --- TDD-shape scoring ------------------------------------------------------
# A ticket is TDD-shaped when you can write a failing test from it ALONE:
# it names a concrete artifact, and it says what the wrong behaviour is.

# (?![\w.]) matters: without it ".cs" matches inside ".cshtml" and invents
# phantom files like EstateProcess.cs from EstateProcess.cshtml.
_EXT = r"(?:cshtml|csproj|json|cs|ts|vue|js)(?![\w.])"
CODE_REF = re.compile(
    rf"\b(?:src|tests)/[\w./-]+\.{_EXT}"
    rf"|\b[A-Z]\w+\.{_EXT}(?::\d+)?"
    r"|\b[A-Z]\w+(?:Controller|Service|Application|Helper|Resolver|Repository)\b")
URL_REF = re.compile(r"https?://[^\s<>\"]+")
SYMPTOM = re.compile(
    r"\b(should|expected|instead|but |returns?|throws?|renders?|404|500|"
    r"null|empty|blank|incorrect|wrong|missing|ignored|not respected|"
    r"fails?|broken|mismatch)\b", re.I)
PORT_DUMP = re.compile(r"\(V1 PR #\d+\)|^\[(?:Other|Vue/UI Components|Partner/Landing Pages|"
                       r"Signatures/Penneo|Payments/Commerce)\]")
AUDIT_PASS = re.compile(r"^\((?:Pass|Inconclusive)\)")
VISUAL = re.compile(
    r"\b(padding|margin|font|colou?r|styling|align|spacing|logo|icon|"
    r"pixel|design|figma|responsive|viewport|z-index|css)\b", re.I)


def score(item):
    f = item["fields"]
    title = f["System.Title"].strip()
    text, field = body_of(f)
    code = sorted(set(CODE_REF.findall(text)))
    urls = sorted(set(URL_REF.findall(text)))
    has_symptom = bool(SYMPTOM.search(text))
    visual_hits = len(VISUAL.findall(text))

    pts, why = 0, []

    # A V1-port backlog entry ("[Other] ... (V1 PR #4494)") carries a huge
    # auto-generated list of changed files. That is a diff dump, not a repro:
    # it says what a V1 PR touched, never what V2 does wrong. Without this the
    # file dump scores higher than a real bug report.
    if PORT_DUMP.search(title):
        pts -= 6; why.append("V1-port dump")
        code = []
    # "(Pass)" / "(Inconclusive)" are audit findings recorded for the record.
    # A Pass is not work; do not offer it as a candidate.
    if AUDIT_PASS.search(title):
        pts -= 6; why.append("audit record, not a defect")

    if code:
        pts += 3; why.append(f"names code ({len(code)})")
    if urls:
        pts += 1; why.append(f"repro url ({len(urls)})")
    if has_symptom:
        pts += 2; why.append("states wrong-vs-right")
    if len(text) >= 200:
        pts += 1; why.append("detailed")
    if not text:
        pts -= 4; why.append("NO BODY")
    if visual_hits >= 2 and not code:
        pts -= 3; why.append("visual/CSS")
    if f["System.WorkItemType"] in ("Epic", "Feature", "User Story") and not code:
        pts -= 2; why.append("container")

    return {
        "id": item["id"],
        "type": f["System.WorkItemType"],
        "state": f["System.State"],
        "title": f["System.Title"].strip(),
        "assigned": (f.get("System.AssignedTo") or {}).get("uniqueName", ""),
        "created_by": (f.get("System.CreatedBy") or {}).get("uniqueName", ""),
        "created": f["System.CreatedDate"][:10],
        "changed": f["System.ChangedDate"][:10],
        "body_field": field,
        "body_len": len(text),
        "body": text,
        "code_refs": code,
        "urls": urls,
        "score": pts,
        "why": why,
        "url": f"{WEB}/{item['id']}",
    }


def verify_refs(rows, repo):
    """Check that file paths a ticket names still exist. A ticket pointing at a
    path that is gone is either stale or describes a different repo."""
    if not repo or not os.path.isdir(repo):
        return
    # Index every source filename once, rather than walking per reference.
    index = set()
    for base in ("src", "tests"):
        for root, dirs, files in os.walk(os.path.join(repo, base)):
            dirs[:] = [d for d in dirs
                       if d not in ("obj", "bin", "node_modules", ".git")]
            index.update(files)

    def known(path):
        if "/" in path:
            return os.path.exists(os.path.join(repo, path))
        if "." in path:                      # already has an extension
            return path in index
        # A bare symbol such as ContentPageHelper is a type name, not a file
        # name. Match it against every extension it could live behind,
        # otherwise a class that plainly exists is reported missing.
        return any(f"{path}.{ext}" in index
                   for ext in ("cs", "cshtml", "ts", "vue", "js"))

    for r in rows:
        found, missing = [], []
        for ref in r["code_refs"]:
            path = ref.split(":")[0]
            (found if known(path) else missing).append(path)
        r["refs_found"], r["refs_missing"] = found, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unassigned", action="store_true", help="only items with no assignee")
    ap.add_argument("--assigned-to", metavar="EMAIL", help="'me' resolves to AZDO_USER")
    ap.add_argument("--created-by", metavar="EMAIL", help="'me' resolves to AZDO_USER")
    ap.add_argument("--since", metavar="YYYY-MM-DD", default="2026-01-01",
                    help="created on or after (default 2026-01-01; V2 work starts in 2026)")
    ap.add_argument("--type", metavar="T", help="Bug | Task | Feature | User Story")
    ap.add_argument("--include-done", action="store_true",
                    help="include Resolved/Closed/Removed/Done")
    ap.add_argument("--text", metavar="RE", help="regex the body must match")
    ap.add_argument("--min-score", type=int, help="only rows scoring >= N (try 4 for TDD-shaped)")
    ap.add_argument("--tdd", action="store_true", help="shorthand for --min-score 4")
    ap.add_argument("--repo", metavar="DIR", default=os.getcwd(),
                    help="repo to verify named files against (default cwd)")
    ap.add_argument("--no-verify", action="store_true", help="skip file verification")
    ap.add_argument("--show-body", type=int, default=0, metavar="N",
                    help="print first N chars of each body")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    clauses = [f"[System.CreatedDate] >= '{args.since}'"]
    if args.unassigned:
        clauses.append("[System.AssignedTo] = ''")
    if args.assigned_to:
        who = USER if args.assigned_to == "me" else args.assigned_to
        clauses.append(f"[System.AssignedTo] = '{who}'")
    if args.created_by:
        who = USER if args.created_by == "me" else args.created_by
        clauses.append(f"[System.CreatedBy] = '{who}'")
    if args.type:
        clauses.append(f"[System.WorkItemType] = '{args.type}'")
    if not args.include_done:
        clauses.append("[System.State] NOT IN " + str(DONE_STATES))

    ids = wiql(" AND ".join(clauses))
    if not ids:
        print("No work items matched.")
        return
    rows = [score(w) for w in fetch(ids)]

    if args.text:
        rx = re.compile(args.text, re.I)
        rows = [r for r in rows if rx.search(r["body"]) or rx.search(r["title"])]

    floor = 4 if args.tdd else args.min_score
    if floor is not None:
        rows = [r for r in rows if r["score"] >= floor]

    if not args.no_verify:
        verify_refs(rows, args.repo)

    rows.sort(key=lambda r: (-r["score"], r["id"]))
    rows = rows[:args.limit]

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    print(f"{len(ids)} matched the query; {len(rows)} shown.\n")
    print("| id | type | state | assignee | body | score | why | title |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        a = r["assigned"].split("@")[0] or "-"
        src = {"Microsoft.VSTS.TCM.ReproSteps": "repro",
               "System.Description": "desc",
               "Microsoft.VSTS.Common.AcceptanceCriteria": "accept",
               "Microsoft.VSTS.TCM.SystemInfo": "sysinfo"}.get(r["body_field"], "-")
        body = f"{src}:{r['body_len']}" if r["body_len"] else "**EMPTY**"
        # Bare id, never a markdown link: the id is what gets typed into a
        # branch name, a commit message and /task-tdd. The url stays in --json.
        print(f"| {r['id']} | {r['type']} | {r['state']} | {a} | "
              f"{body} | {r['score']} | {', '.join(r['why'])} | {r['title'][:58]} |")

    flagged = [r for r in rows if r.get("refs_missing")]
    if flagged:
        print("\n**Named files NOT found in the repo** (stale ticket, or another repo):")
        for r in flagged:
            print(f"- {r['id']}: {', '.join(r['refs_missing'])}")

    if args.show_body:
        for r in rows:
            print(f"\n### {r['id']} {r['title']}\n{r['url']}")
            print(r["body"][:args.show_body] or "(no body in any field)")


if __name__ == "__main__":
    main()

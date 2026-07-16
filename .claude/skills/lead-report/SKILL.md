---
name: lead-report
description: Produce a CSV "lead report" of LegalDesk company-registration purchases (enkeltmandsvirksomhed, ApS, etc.) matching a natural-language request — a company type, a date range, and a set of desired columns/conditions. Pulls from the automation API by default and enriches missing fields (email, CVR) from the read-only v8 reporting DB. Use when the user asks for a "lead report", "lead list", "leads for <period>", "all <company type> created between <dates>", "export leads to CSV", or similar. NOT for a single fixed report — the skill interprets each request.
---

# Lead report

Turn a **natural-language lead request** into a **CSV**. A "lead" is a company-registration product purchase (enkeltmandsvirksomhed, ApS, …) in a date window, optionally carrying contact fields the user wants to follow up on.

The skill is **general** — it interprets the request each time. Do **not** hardcode one report. Requests vary along three axes:
- **Company type** — enkeltmandsvirksomhed (`emv`), ApS (`aps`), possibly others.
- **Date range** — "1 June to 30 June", "last month", "since 11 May", etc.
- **Columns / conditions** — which fields to output; whether some fields ("must have a phone and a CVR") are wanted.

**Default posture (decided with the user):**
- **API-first.** Pull the lead list from the automation API. It's the authoritative feed of registrations and needs no DB credentials.
- **DB-enrich for gaps.** The API's fields differ per type (e.g. `emv` has no email or CVR). Fill those from the read-only v8 reporting DB.
- **Full list, conditions as columns — never drop rows.** When a request says leads "must have a phone number and a CVR", do **not** filter them out. Return every lead in the range and put phone/CVR in their own columns so the end user filters in the spreadsheet. (Blank = not present/known.)

> ### ⛔ Hard rule: CVR and CPR are never interchangeable
> **CVR** = 8-digit *company* number (`dbld.CvrToMembers.Cvr`, e.g. `46547144`). **CPR** = *personal* number (API `founderCPR`, e.g. `050579-2955`).
> - When asked for **CVR**, source it **only** from the CVR field — never fall back to `founderCPR`. When asked for **CPR**, never emit a CVR. If the true value is unknown, leave the cell **blank** — never substitute the other number.
> - Never guess or reconstruct one from the other. A blank CVR is correct; a CPR in a CVR column is a serious error.
> - **CPR is sensitive personal data** — only include it when the user explicitly asks for CPR, and flag that the file then contains personal data.

Run the phases in order.

## Phase 1: Parse the request

From the user's request, extract:
1. **Company type** → an API slug (see the type registry in Phase 2). If ambiguous, ask.
2. **Date range** → `from` and `to` as `YYYY-MM-DD`. Resolve relative dates against **today** (the harness supplies the current date). "1 June to 30 June" with no year → the most recent such range. Confirm the resolved absolute dates back to the user in one line.
3. **Columns** → the exact columns to output, in order. If the user names them (e.g. *Company name, Email, Type, Tlf., CVR*), honour that list and those labels verbatim. If they don't, propose a sensible default and state it.

Play the request back in one sentence with the resolved type, absolute dates, and column list before doing work — a wrong date range or type wastes a full pull.

## Phase 2: Resolve the company type

**Type registry** (verified 2026-07; confirm slugs still 200 before relying on them):

| Request term | API slug | DB `Category` (CaseworkProductConfigurations) | API has email? | API has CVR? | Holding-classifiable? |
|---|---|---|---|---|---|
| Enkeltmandsvirksomhed / sole proprietorship | `emv` | `Enkeltmandsvirksomhed` | ❌ (enrich) | ❌ (enrich) | n/a (no holding sole-props) |
| ApS / anpartsselskab / limited company | `aps` | `Selskabsstiftelse` | ✅ `companyMail` | ❌ (enrich) | ✅ via `industryDescription` (Phase 4b) |

Unknown slugs return **HTTP 400**. To discover/confirm a slug, probe it:
```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  "https://legaldesk-new-razor-html-v2.azurewebsites.net/api/automation/<slug>?from=2026-01-01&pagesize=1"
```

For each type, the DB enrichment needs its **SKU set** and **NameJsonPath** (the WizardData path holding the company name). Both come from one row of `dbld.CaseworkProductConfigurations` — the current `Sku` plus the comma-separated `LegacySkus`, and `NameJsonPath`:
```sql
SELECT Sku, LegacySkus, NameJsonPath, Category, Type
FROM dbld.CaseworkProductConfigurations
WHERE Category = 'Enkeltmandsvirksomhed';   -- Id 24: Sku 5047; NameJsonPath 'navn.navn_navn'
```
`emv` SKU set (verified): `5047, 5038, 5025, 5008, 5004, 5002, 599, 597, 596, 591, 582, 579, 560, 541, 534, 519`; NameJsonPath `navn.navn_navn`.

If the request needs no DB-only column for this type (e.g. `aps` when only company/email/phone are asked), skip the DB entirely.

## Phase 3: Fetch the lead list from the API

`GET https://legaldesk-new-razor-html-v2.azurewebsites.net/api/automation/{slug}`

- Params: `from`, `to` (dates, inclusive), `page` (1-based), `pagesize`.
- Envelope: `{ "page", "pageSize", "totalCount", "items": [ { "documentGuid", "data": {…} } ] }`.
- **Paginate until you have all rows:** keep requesting `page` 1,2,… with a large `pagesize` (e.g. 100) until `page * pageSize >= totalCount`.
- No auth. Public endpoint.

Field map (the columns the API can fill directly):

| Column | `emv` field | `aps` field |
|---|---|---|
| Company name | `data.companyName` | `data.companyName` |
| Tlf. (phone) | `data.companyPhone` | `data.companyPhone` |
| Email | — (enrich) | `data.companyMail` (may be `"-"` → treat as blank) |
| Type | (from slug: "Enkeltmandsvirksomhed") | (from slug: "ApS") |
| Address | `data.companyAddress.{street,zip,city}` | `data.companyAddress.{…}` |
| Founder | `data.founderName`, `data.founderCPR` | `data.foundersDetails[]` |
| Industry / purpose | `data.branchCode` | `data.industryDescription` (e.g. `[64.20.20] Ikke-finansielle holdingselskaber`), `data.purpose` |

Helper (fetch all pages → newline JSON):
```bash
python3 - "$SLUG" "$FROM" "$TO" <<'PY'
import json,sys,urllib.request
slug,frm,to=sys.argv[1:4]
base=f"https://legaldesk-new-razor-html-v2.azurewebsites.net/api/automation/{slug}"
items,page=[],1
while True:
    u=f"{base}?from={frm}&to={to}&page={page}&pagesize=100"
    d=json.load(urllib.request.urlopen(u,timeout=60))
    items+=d["items"]
    if page*d["pageSize"]>=d["totalCount"]: break
    page+=1
print(f"# {len(items)} items",file=sys.stderr)
for it in items: print(json.dumps(it))
PY
```

## Phase 4: Enrich missing columns from the DB

Only for columns the type's API doesn't provide (Email/CVR for `emv`; CVR for `aps`). Read-only reporting DB, via `sqlcmd`.

**Connection** — the credential lives OUTSIDE the dotfiles repo; source it, never inline it:
```bash
source /home/anders/.secrets/legaldesk-reporting-db.env   # exports LEGALDESK_REPORT_SQL_{SERVER,DB,USER,PWD}
export SQLCMDPASSWORD="$LEGALDESK_REPORT_SQL_PWD"
SQLCMD=/home/anders/.local/bin/sqlcmd   # not on PATH by default — use the full path
"$SQLCMD" -S "$LEGALDESK_REPORT_SQL_SERVER" -d "$LEGALDESK_REPORT_SQL_DB" \
  -U "$LEGALDESK_REPORT_SQL_USER" -N -C -W -s "|" -Q "SELECT 1"
```
`-N -C` = encrypt + trust server cert (required for Azure SQL). `-W -s "|"` = trimmed, pipe-separated. For machine-readable output add `-h -1` and `SET NOCOUNT ON;`.

**The join key is `companyName`** — the API's `documentGuid` does **not** match any DB key, so there is no exact join. Match on company name:

- **CVR** (any type): `dbld.CvrToMembers` keyed by name.
  ```sql
  SELECT CompanyName, MAX(Cvr) AS Cvr
  FROM dbld.CvrToMembers
  WHERE IsDeleted = 0 AND Cvr > 0 AND CompanyName IN (<api company names>)
  GROUP BY CompanyName;
  ```
- **Email** (types whose API lacks it, e.g. `emv`): `dbld.Products.MemberEmail`, matched via the WizardData company name.
  ```sql
  SELECT JSON_VALUE(WizardData, '$.navn.navn_navn') AS companyName, MIN(MemberEmail) AS email
  FROM dbld.Products
  WHERE Sku IN (<type SKU set>) AND Status = 1 AND IsDeleted = 0
    AND CreatedOn >= @from AND CreatedOn < DATEADD(day,1,@to)
    AND JSON_VALUE(WizardData, '$.navn.navn_navn') IN (<api company names>)
  GROUP BY JSON_VALUE(WizardData, '$.navn.navn_navn');
  ```
  Substitute the type's real `NameJsonPath` for `navn.navn_navn`. `Status = 1` = completed.

Merge the DB results back onto the API rows by company name. Leave a cell **blank** when there's no match — don't invent, don't drop the row. When a name is **ambiguous** (duplicated in the API result, or matching >1 distinct email/CVR in the DB), **do not broadcast one value across the rows** — resolve it via Phase 4c.

> **CVR ≠ CPR — never conflate them.** **CVR** is the 8-digit *company* number (`dbld.CvrToMembers.Cvr`, e.g. `46547144`) — the report's CVR column. **CPR** is the *personal* number (API `founderCPR`, e.g. `050579-2955`) — never a report column, and not stored in emv `WizardData`, so it can't be a join key.

**Name-match caveats (state these to the user):**
- Generic or coincidental names collide → wrong enrichment. Duplicate/ambiguous names are handled explicitly in **Phase 4c** (detect → explain → ask). Never staple one match onto several same-named rows.
- The API (v2 system) and the reporting DB (v8) are **different populations** — counts differ (e.g. June `emv`: API 46 vs DB 58) and some API leads won't match any DB row. Report the match rate ("email filled for N of M leads").
- **CVR lags registration** — freshly created companies often have no CVR yet, so recent windows will show many blank CVRs. Expected, not a bug.

## Phase 4b: Derived columns — Drift vs Holding (operating vs holding company)

When a request distinguishes **driftselskaber** (operating companies) from **holdingselskaber** — e.g. *"kun driftselskaber"*, *"Momslead"* (VAT lead: holding companies can't be sold VAT products), or *"marker holding"* — add a **`Drift/Holding`** classification. Applies to company types with an industry code (`aps`); not to `emv`.

**Classify each lead:**
1. **Holding** if `data.industryDescription` contains branch code **`64.20`** (`Ikke-finansielle holdingselskaber` → `[64.20.20]`, `[64.20.10]`). This is the authoritative signal.
2. If `industryDescription` is blank, fall back to `data.purpose`: **Holding** if it reads as pure holding activity — "eje ejerandele i andre selskaber", "besiddelse af kapitalandele/aktier", "holdingvirksomhed" — or if the company name contains "holding".
3. Otherwise **Drift**.

**Validated (2026-07):** on 892 Jan-2026 ApS this matched an industry-code baseline on **891/892**; the lone diff was a real-estate/holding hybrid (purpose "investering i udlejningsejendomme og kapitalandele"). Such borderline text (property investment *plus* kapitalandele) is genuinely ambiguous — **default it to Drift** and move on; don't over-engineer. Naive name-matching alone is wrong — ~40% of holdings ("Invest", "Ventures", plain names) have no "holding" in the name, so use the industry code.

**Output rule (follows the skill's no-drop principle):** by default **include all rows and add the `Drift/Holding` column** so the user filters in the spreadsheet. Only **hard-filter to Drift** (drop holdings) if the user explicitly says to exclude them entirely — if unsure which they want, include-and-flag and say so. Report the split ("534 Drift / 358 Holding").

## Phase 4c: Duplicate / ambiguous company names — detect, explain, ask

The enrichment key (`companyName`) is **not unique**, so before finalizing you must check for duplicates and resolve them *with the user* — never silently staple one DB match onto several same-named rows (that's how a real company ends up with the wrong email or CVR).

**1. Detect.** Flag any company name that is either:
- **duplicated in the API result set** (same name on ≥2 leads), or
- **ambiguous against the DB** (its name matches >1 distinct `MemberEmail` or `Cvr`).

If none, skip straight to Phase 5 — don't bother the user.

**2. Explain why (per duplicate group).** Query the DB for every same-named registration in the window and read the cause off the result. The founder name (`stifter_navn`) is the key diagnostic:
```sql
SELECT JSON_VALUE(p.WizardData,'$.navn.navn_navn')   AS company,
       JSON_VALUE(p.WizardData,'$.navn.stifter_navn') AS founder,
       p.MemberEmail, p.MemberId, c.Cvr, p.CreatedOn
FROM dbld.Products p
LEFT JOIN dbld.CvrToMembers c ON c.ProductId = p.Id AND c.IsDeleted = 0 AND c.Cvr > 0
WHERE p.Sku IN (<type SKU set>) AND p.Status = 1 AND p.IsDeleted = 0
  AND p.CreatedOn >= @from AND p.CreatedOn < DATEADD(day,1,@to)
  AND JSON_VALUE(p.WizardData,'$.navn.navn_navn') = '<name>'
ORDER BY p.CreatedOn;
```
Read the cause:
- **Same founder, registered twice** — identical `stifter_navn`, close in time, different email/`MemberId` (a redo or typo-fix). Often only one attempt completed (has a CVR). *This is the common case.* → usually collapse to the completed one.
- **Different founders, same company name** — distinct `stifter_navn` → genuinely separate businesses that coincidentally chose the same name → both are real leads.
- **Feed artifact** — identical everything (same `MemberId`) → a true duplicate row → collapse.

State it concretely, e.g.: *"'LSTJ Biler' appears twice — same founder Lars Kornerup Jensen registering twice a day apart; only the first (`salg@lstjbiler.com`) completed and holds CVR 46547144, the second (`salg@lstj.com`) has none."*

**3. Ask once per *category*, not per row or per group.** Bucket every flagged duplicate by its cause (from step 2), then ask the user for **one rule per non-empty category** — the answer applies to *all* duplicates in that bucket. Never walk the user through groups one at a time or make them type the same decision twice.

Use a single `AskUserQuestion` call with one question per category (load its schema via `ToolSearch` `select:AskUserQuestion` if needed). For each category, show its **count** and 1–2 example groups as evidence, then offer the rule options. Suggested categories, options, and default recommendations:

| Category | Rule options | Default |
|---|---|---|
| Same founder, registered twice (redo/typo) | keep all / collapse to the CVR-holding attempt (else latest) / drop | collapse to CVR-holding |
| Different founders, same company name | keep all (pair enrichment by founder name; blank if unpairable) / drop | keep all |
| Feed artifact (identical rows) | collapse to one / keep all | collapse to one |

Only surface categories that actually occur. If just one category is present, it's one question.

**4. Apply the chosen rule to the whole category** and enrich safely:
- Apply each category's rule uniformly to every group in it — no per-group prompts.
- For kept rows that remain ambiguous (name can't tell them apart), **leave email/CVR blank** unless a *reliable* secondary key disambiguates — e.g. distinct founder names let you pair each API `founderName` to its DB `stifter_navn`. Never broadcast, never guess. (Founder **CPR** is not in `WizardData`, so it can't be that key.)
- In the final summary, report per category: how many duplicate groups and the rule applied.

## Phase 5: Assemble and deliver the CSV

- Columns in the exact order/labels the user asked for (Danish labels like `Tlf.` verbatim).
- One row per API lead (full list — no condition filtering).
- Proper CSV quoting; UTF-8 (names/addresses have æøå). Comma or semicolon delimiter — semicolon (`;`) is friendlier for Danish Excel; ask or default to `;` and say so.
- Write to a dated file in the working directory unless told otherwise, e.g. `leads-<slug>-<from>_<to>.csv`.
- Close with a one-line summary: type, range, row count, and per-enriched-column fill rate ("CVR present for 14/46; email for 45/46").

## Reference: the automation API

- Base: `https://legaldesk-new-razor-html-v2.azurewebsites.net/api/automation/{slug}`
- List: `?from&to&page&pagesize` → `{page,pageSize,totalCount,items[{documentGuid,data}]}`
- Detail: `/{slug}/{documentGuid}` → the `data` object only (no extra fields beyond the list; not worth calling).
- Unknown slug → 400. Unknown query params are ignored (no server-side `hasCvr`/`includeEmail` filtering — do it client-side).
- Backed by the **v2** app; not the same store as the v8 reporting DB.

## Reference: the reporting DB (v8, read-only)

- Server `legaldesk-stage.database.windows.net`, DB `legaldeskv8-production`, login `legaldeskreporting` (read-only). Azure SQL — encryption required.
- `dbld.Products` — core purchase/product rows. Key cols: `Id, Sku, Name, MemberEmail, MemberId, Status (0 draft / 1 completed / 2 other), WizardData (JSON), CreatedOn, CvrNumber (unused for emv — do NOT use), Guid`.
- `dbld.CaseworkProductConfigurations` — per-type config: `Sku + LegacySkus` (the full SKU set for a type), `Category`, `Type`, `NameJsonPath` (WizardData path to the company name). The source of truth for identifying a type.
- `dbld.CvrToMembers` — CVR per company: `Cvr, CompanyName, ProductId, MemberId, IsActive, IsDeleted`. Join to a product by `ProductId` (clean) or match by `CompanyName` (for API bridging). Only ~⅓ of rows have a CVR (registration lag).
- **Phone in the DB is unreliable** — uCommerce tables are effectively empty (≈4 rows); the Umbraco member property `phone` (propertyTypeId 343, member type `Customer`) is filled for almost no one (3/58 in a June sample). **Get phone from the API, not the DB.**

## What this skill does not do

- Filter out leads that miss a condition — always return the full list with condition columns.
- Send anything anywhere (no email/Slack) — it produces a CSV file; the user distributes it.
- Guess enrichment on ambiguous name matches — blank beats wrong for a follow-up list.
- Persist or log the DB password anywhere; the credential stays in `~/.secrets/` only.

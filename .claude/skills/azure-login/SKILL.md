---
name: azure-login
description: Diagnose and fix Azure Portal / az CLI sign-in failures for Anders (anders@legaldesk.dk) — Conditional Access blocks (AADSTS53003, AADSTS530036), "multiple accounts with the same username" az CLI errors, or sign-in landing in the wrong tenant. Use whenever Azure Portal or `az login` rejects Anders's account, or the CLI complains about ambiguous cached accounts.
---

# Azure sign-in troubleshooting (legaldesk.dk)

Anders's email `anders@legaldesk.dk` is shared by **three separate Microsoft identities**,
which is the root cause of almost every confusing Azure sign-in symptom:

1. **Default directory** (tenant `2fd5e0d2-9d3e-4710-92da-6d48014bcd7b`) — the real work
   account. This is where Legaldesk's actual subscription and resources live:
   subscription "Pay-As-You-Go" (`b7254c94-d6e9-43f5-9b83-dfacdcc287b4`). **This is the one
   you want.**
2. **Microsoft Personal** — a personal/consumer Microsoft account (MSA) that happens to use
   the same email as its alias. MSAL/az CLI represents personal accounts with the reserved
   tenant GUID `9188040d-6c67-4c5b-b112-36a304b66dad` — seeing that GUID in any error output
   is a dead giveaway the personal account got selected instead of the work one.
3. **Legaldesk** (Authenticator app label) — the personal account also has a stale/unrelated
   B2B guest relationship in a totally unrelated org's tenant (confirmed once as
   `c7d1b6e9-1447-457b-9223-ac25df4941bf`, "Danske Bank A/S" — no business relationship,
   just an old forgotten guest invite). If a sign-in attempt ever shows foreign company
   branding, this is why — it's a red herring, not the real problem.

## The known-good login recipe

The current password for the Default Directory account is saved in Bitwarden under the
**"Azure Portal"** entry.

Multiple cached MSAL accounts sharing one username makes `az login` fail even with
`--tenant` specified, straight into an ambiguous-account error
(see https://github.com/Azure/azure-cli/issues/20168). `az account clear` alone doesn't
fix it if a stray login re-populates the cache before the real attempt. Do exactly this,
with no other `az login` attempt in between:

```bash
az account clear
az login --tenant 2fd5e0d2-9d3e-4710-92da-6d48014bcd7b
```

In the browser/device flow that opens, sign in as the **work/school** account (not
personal), with the current password and the TOTP code from the **"Default directory"**
entry in Microsoft Authenticator (open the app and read the rotating 6-digit code —
this method does not send a push notification).

Verify success with:

```bash
az account show --output table   # HomeTenantId should read 2fd5e0d2-9d3e-4710-92da-6d48014bcd7b
```

## Diagnostic tools that cut through the ambiguity fast

- **Which tenant owns a domain** (no login needed):
  `curl -s "https://login.microsoftonline.com/<domain>/v2.0/.well-known/openid-configuration"`
  and read the `issuer` field's GUID. Returns a real `AADSTS90002` error for domains with
  no tenant, so a returned GUID is trustworthy. `legaldesk.dk` → `2fd5e0d2-...`.
- **Don't trust incognito/private browsing to isolate identity** — in this case even a
  fresh incognito window kept resolving to the wrong account, because the ambiguity lives
  in the account itself (multiple identities under one email + local MSAL token cache),
  not browser cookies.
- **Device-code flow (`az login --use-device-code`) is a dead end here** — a Conditional
  Access policy rejects that grant type outright (`AADSTS530036`, "authentication flows
  policy applies to all applications") before MFA is ever reached, regardless of tenant.
  Use the plain browser flow instead.
- If sign-in reaches a password prompt with **generic Microsoft branding** (no custom
  logo), that's consistent with landing in the real, unbranded "Default Directory" tenant.
  Foreign-company branding means the wrong (personal/guest) identity got picked.
- Known first-party app IDs seen in error messages, for context when reading logs:
  Azure Portal = `c44b4083-3bb0-49c1-b47d-974e53cbdf3c`, Azure CLI = `04b07795-8ddb-461a-bbee-02f9e1bf7b46`.

## When it's an admin-side problem, not a client-side one

Some symptoms can't be fixed from the client at all — escalate to **Vladica Ivanovski**
(`vladica@legaldesk.dk`, reachable via Slack DM) rather than continuing to retry logins:

- **AADSTS53003** at the Azure Portal specifically (sign-in succeeds, Portal access is
  then blocked) — a Conditional Access policy in the `2fd5e0d2-...` tenant, likely
  device-compliance-based (Anders's Linux machine shows as "unregistered/unmanaged" in
  the error detail). Ask Vladica to check Conditional Access policies for a
  compliant/managed-device requirement and add an exception, or get the device registered.
- **"You can't reset your own password... haven't registered for password reset"** — SSPR
  isn't enabled for the account. Vladica can reset the password directly from the Entra
  admin center without SSPR being configured.
- When asking Vladica to check sign-in logs, always give him the **Correlation ID** from
  the error page, not just the account name — the account name alone doesn't disambiguate
  which of Anders's three identities the failed attempt belongs to, which caused a lot of
  back-and-forth the first time this was diagnosed.

## Azure DevOps is a separate system

`dev.azure.com/legaldesk` (project "Legal Desk") is unrelated to the Portal/subscription
access above — it authenticates via a separate PAT (kept in a local key file), not the
`az login` identity:

```bash
tr -d ' \n\t' < <path-to-PAT-file> | az devops login --organization https://dev.azure.com/legaldesk
```

A working DevOps login says nothing about whether Portal/subscription access works, and
vice versa — don't let a DevOps success mask a still-broken Portal login, or a Portal fix
be expected to also fix DevOps.

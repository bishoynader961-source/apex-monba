# Plan: Consolidate Lemon Squeezy Webhook Handlers to `backend/app.py`

## 1. Goal

Delete three obsolete Lemon Squeezy webhook implementations and update `PROJECT_MAP.md` +
`FLOW_LOGIC.md` so they declare `backend/app.py` as the single source of truth and
`LEMON_SQUEEZEY_SIGNATURE_SECRET` as the definitive signature-verification env var.

## 2. Verified pre-conditions (checked against the repo — do not re-derive)

| Fact | Evidence |
|---|---|
| All 3 target files are git-tracked | `git ls-files api archive/licensing archive/license_server` |
| No module imports any of them | No `import webhook` / `from webhook` / `lemon_webhook` references in any `.py` |
| None are deployed | `.vercelignore` excludes `*.py` and `archive/`; `vercel.json` = `{"framework":"nextjs"}`. Only `app/api/webhooks/paddle/route.ts` is live |
| `api/lemon_webhook.py` and `archive/licensing/api/webhook.py` are identical | Both 108 lines, same content, both read `LEMON_SQUEEZY_WEBHOOK_SECRET` |
| `archive/license_server/api/webhook.py` reads `LEMON_WEBHOOK_SECRET` | Line 27 |
| `backend/` is untracked | `git status` → `?? backend/` |
| `__pycache__/` + `*.pyc` are gitignored | `.gitignore` lines 3-4 → `git add backend/` stages only the 2 `.py` files |
| Root tree block in `PROJECT_MAP.md` (lines 338-389) does **not** list `api/` | No tree edit needed for the removal |
| Doc typo | `PROJECT_MAP.md:1017` + `FLOW_LOGIC.md:121` say `test_webhook_lemon_squeeasy.py`; real name is `test_webhook_lemon_squeezy.py` |

## 3. Decisions made

1. **Document-only boundary for remaining legacy code.** `archive/license_server.py:269`
   still defines `@app.route("/webhook/lemonsqueezy")` and `archive/licensing/DEPLOY.md`
   still documents `/api/webhook`. Do **not** edit them. Instead, `PROJECT_MAP.md` will
   state that everything under `archive/` is historical and non-authoritative, naming that
   route as a known dormant remnant. Root `TESTING.md` is **not** archived and contradicts
   the claim, so it gets a scoped correction (Task 8).
2. **Stage `backend/` with the deletion** so the repo is never in a state where all
   Lemon Squeezy handlers are deleted but the replacement is untracked. Use `git rm` for
   the tracked deletions. **Do not commit** unless the user asks.

## 4. Hard constraints

- Do **not** modify `backend/app.py` or `backend/test_webhook_lemon_squeezy.py`.
- Do **not** modify `license_gate.py` or any desktop app file.
- Do **not** modify anything under `archive/` (docs or code).
- Do **not** add `LEMON_SQUEEZEY_SIGNATURE_SECRET` to `.env` or `.env.example`:
  `archive/exhaustive_verify.py:144` fails checks 1.9/1.10 if the string `"Lemon"` appears
  in either file. Document the variable in the maps only.
- Do not commit or push.

## 5. Ordered tasks

### Task 1 — Stage the replacement first
```powershell
git add backend/app.py backend/test_webhook_lemon_squeezy.py
```

### Task 2 — Delete the three legacy handlers
```powershell
git rm api/lemon_webhook.py archive/licensing/api/webhook.py archive/license_server/api/webhook.py
```

### Task 3 — Clean up leftovers
- `api/` is now empty → remove the directory if it still exists (`Remove-Item -LiteralPath "api" -Force` only if empty).
- Delete the stale gitignored artifact `archive/license_server/api/__pycache__/webhook.cpython-314.pyc`.
- Leave `activate.py`, `validate.py`, `index.py` in both archived `api/` folders untouched.

### Task 4 — `PROJECT_MAP.md`: replace section 7 (lines 1001-1021) entirely

Replace the whole `## 7. Licensing Backend` section with:

```markdown
## 7. Licensing Backend

### Canonical webhook handler — SINGLE SOURCE OF TRUTH

`backend/app.py` is the **sole** Lemon Squeezy webhook handler in this project. All other
Lemon Squeezy webhook implementations were deleted on 2026-08-06. No additional webhook
receiver may be introduced outside `backend/`.

| File | Purpose | Lines |
|---|---|---|
| `backend/app.py` | Flask app — `POST /webhooks/lemon-squeezy`, HMAC-SHA256 `X-Signature` verification → `order_created` license-key stub | ~120 |
| `backend/test_webhook_lemon_squeezy.py` | 6 unittest cases (Flask test client) covering the 401/400/200 paths | ~160 |

**Test result:** 6/6 pass (`python backend/test_webhook_lemon_squeezy.py`).

### Environment variables — definitive vs deprecated

| Variable | Status | Read by |
|---|---|---|
| `LEMON_SQUEEZEY_SIGNATURE_SECRET` | **DEFINITIVE** — the only variable used for Lemon Squeezy signature verification | `backend/app.py` |
| `LEMON_WEBHOOK_SECRET` | **DEPRECATED** — handler deleted | nothing |
| `LEMON_SQUEEZY_WEBHOOK_SECRET` | **DEPRECATED** — handlers deleted; a dormant reference survives in `archive/license_server.py` (non-authoritative) | nothing active |
| `LEMONSQUEEZY_WEBHOOK_SECRET` | **DEPRECATED** — archived documentation only | nothing |

There is **no fallback chain**: if `LEMON_SQUEEZEY_SIGNATURE_SECRET` is unset, `backend/app.py`
returns `500` rather than silently reading a legacy name. Operators must set it in the
`backend/` deployment environment.

> Do **not** add this variable to `.env` or `.env.example` — `archive/exhaustive_verify.py`
> checks 1.9/1.10 fail if the string "Lemon" appears in those files.

### Removed legacy handlers (2026-08-06)

| Deleted file | What it was | Replaced by |
|---|---|---|
| `api/lemon_webhook.py` | `BaseHTTPRequestHandler`, persisted licenses to Upstash Redis | `backend/app.py` |
| `archive/licensing/api/webhook.py` | Identical duplicate of the above | `backend/app.py` |
| `archive/license_server/api/webhook.py` | Vercel serverless, `PHARM-XXXX-XXXX-XXXX` keygen → Upstash Redis | `backend/app.py` |

None of these were ever deployed: `.vercelignore` excludes `*.py` and `archive/`, so the live
Vercel deployment has only ever served `app/api/webhooks/paddle/route.ts`.

### Other licensing components (non-Lemon-Squeezy)

| Component | Location | Stack | Role |
|---|---|---|---|
| Paddle webhook (live) | `app/api/webhooks/paddle/route.ts` | Next.js route handler | Paddle billing — a different gateway, not a Lemon Squeezy handler |
| License server (Paddle) | `archive/server_app.py` | Flask (PythonAnywhere) | `/api/validate`, `/api/activate`, `/api/create`, `/admin/api/*`, `/api/portal/*` |
| Desktop license gate | `license_gate.py` | CustomTkinter | Consumer of `/api/validate` + `/api/activate` |
| Local CLI | `hub.py` | argparse | `deploy`, `test-webhook` (Paddle), HWID utilities |

### `archive/` is non-authoritative

Everything under `archive/` is historical reference only — excluded from the Vercel
deployment and not part of the active architecture. Known dormant remnant:
`archive/license_server.py:269` still defines `@app.route("/webhook/lemonsqueezy")` reading
`LEMON_SQUEEZY_WEBHOOK_SECRET`, and `archive/licensing/DEPLOY.md` still describes an
`/api/webhook` Vercel deployment. Neither is deployed, imported, or maintained, and neither
counts as a webhook handler for the purposes of the single-source-of-truth rule above.
```

### Task 5 — `PROJECT_MAP.md`: annotate the M47 milestone row (line 945)

That row cites `licensing/api/` "activate/validate/webhook". Keep the historical record but
append, inside the description cell before the trailing `| ✅ Complete |`:

> **Superseded 2026-08-06:** the `webhook` endpoint (`archive/licensing/api/webhook.py`) was deleted; Lemon Squeezy webhooks are handled solely by `backend/app.py` — see §7.

### Task 6 — `PROJECT_MAP.md`: retire dead TODO rows (lines 892-893)

Change the Status cell of these two rows to
`Obsolete — \`licensing/\` archived; LS webhook consolidated into \`backend/app.py\` (§7)`:
- `| Deploy \`licensing/\` to Vercel |`
- `| Create Upstash Redis database + set env vars in Vercel |`

Leave lines 891 and 894 (API_BASE_URL placeholder, GitHub Pages) unchanged — out of scope.

### Task 7 — `FLOW_LOGIC.md`: rewrite the head of section 13 (lines 119-121)

Replace:
```markdown
## 13. Lemon Squeezy Webhook Backend (New — M66)

**Component:** `backend/app.py` (Flask) + `backend/test_webhook_lemon_squeeasy.py`.
```
with:
```markdown
## 13. Lemon Squeezy Webhook Backend (M66) — SINGLE SOURCE OF TRUTH

**Component:** `backend/app.py` (Flask) + `backend/test_webhook_lemon_squeezy.py`.

**Authority:** `backend/app.py` is the ONLY Lemon Squeezy webhook handler in this project.
The legacy handlers `api/lemon_webhook.py`, `archive/licensing/api/webhook.py`, and
`archive/license_server/api/webhook.py` were deleted on 2026-08-06. All new Lemon Squeezy
event handling must be added inside `backend/app.py`.

**Signature secret:** `LEMON_SQUEEZEY_SIGNATURE_SECRET` is the definitive and only supported
environment variable for Lemon Squeezy signature verification. `LEMON_WEBHOOK_SECRET`,
`LEMON_SQUEEZY_WEBHOOK_SECRET`, and `LEMONSQUEEZY_WEBHOOK_SECRET` are fully deprecated: no
active code reads them and no fallback chain exists.
```

Also, in the numbered data flow, extend step 4 to
`4. Read \`LEMON_SQUEEZEY_SIGNATURE_SECRET\` (env — no fallback to any legacy variable name).`

### Task 8 — `TESTING.md`: remove the contradicting live-doc reference

`TESTING.md` is a root (non-archived) doc that still tells readers to POST Lemon Squeezy
payloads to `http://localhost:5000/api/webhook/lemonsqueezy` (line 94) and to set
`LEMONSQUEEZY_WEBHOOK_SECRET` (line 200). That endpoint no longer exists in any active
server. Minimal correction:
- Replace the "Lemon Squeezy mock payload" `curl` block target with the canonical
  `http://localhost:5000/webhooks/lemon-squeezy` served by `backend/app.py`, and note the
  header is `X-Signature` over the raw body using `LEMON_SQUEEZEY_SIGNATURE_SECRET`.
- Drop `LEMONSQUEEZY_WEBHOOK_SECRET` from line 200, leaving `PADDLE_WEBHOOK_SECRET`.

If the user prefers TESTING.md untouched, skip this task and the maps remain correct —
TESTING.md just stays stale.

## 6. Validation

1. `git status --porcelain` shows exactly:
   `D api/lemon_webhook.py`, `D archive/licensing/api/webhook.py`,
   `D archive/license_server/api/webhook.py`, `A backend/app.py`,
   `A backend/test_webhook_lemon_squeezy.py`, `M PROJECT_MAP.md`, `M FLOW_LOGIC.md`
   (+ `M TESTING.md` if Task 8 is done). No other file changed.
2. `rg -n "lemon_webhook|licensing/api/webhook|license_server/api/webhook" --glob "!.kilo/**"`
   returns **zero** matches (`.kilo/plans/*` history is expected to still mention them).
3. `rg -n "LEMON_SQUEEZY_WEBHOOK_SECRET|LEMON_WEBHOOK_SECRET|LEMONSQUEEZY_WEBHOOK_SECRET" --glob "!archive/**" --glob "!.kilo/**"`
   returns matches only inside the "deprecated" tables of `PROJECT_MAP.md` / `FLOW_LOGIC.md`.
4. `python backend/test_webhook_lemon_squeezy.py` → 6/6 pass (proves the surviving handler is
   untouched and still green).
5. `Test-Path -LiteralPath "api"` → `False`.
6. Spot-read `PROJECT_MAP.md` §7 and `FLOW_LOGIC.md` §13 to confirm both name
   `backend/app.py` as sole handler and `LEMON_SQUEEZEY_SIGNATURE_SECRET` as definitive.

## 7. Risks and rollback

- **Risk: near-zero runtime impact.** The deleted files are unreferenced, untested, and
  excluded from every deployment path. The project moved to Paddle-only billing in commit
  `c40cfa4`, so no live Lemon Squeezy traffic depends on them.
- **Risk: unstaged-state gap.** Mitigated by Task 1 running before Task 2.
- **Rollback:** nothing is committed. `git restore --staged --worktree api/lemon_webhook.py
  archive/licensing/api/webhook.py archive/license_server/api/webhook.py` restores all three
  from `HEAD`; `git restore PROJECT_MAP.md FLOW_LOGIC.md TESTING.md` reverts the docs.

## 8. Explicitly out of scope (follow-ups, do not do here)

- `backend/app.py` has **no deployment target**: `.vercelignore` excludes `*.py`, so the
  canonical handler is not hosted anywhere yet. Choosing a host (PythonAnywhere alongside
  `server_app.py`, or converting to a Next.js route) is a separate decision.
- `generate_license_key()` in `backend/app.py` is still a stdout stub with no persistence.
- Removing the dormant `/webhook/lemonsqueezy` route from `archive/license_server.py`.
- Fixing `archive/licensing/DEPLOY.md`.
- Committing/pushing any of the above.

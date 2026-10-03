# DECISIONS.md — approved product decisions (Phase 2)

Date: 2026-10-03 · Every value below was explicitly approved by the owner via structured questions (Phase 0 + Phase 2). No invented values.

## Product identity

| Item | Approved value |
|---|---|
| App display name | **Pharmacy Suite** (matches `productName`, window title, `com.pharmacysuite.app`) |
| Publisher name | **Apex Software** |
| Support email | **pharmacypro.support@gmail.com** |
| Logo 512×512 PNG | **PENDING** — HUMAN_TODO §L2 open; Freemius product creation (HUMAN_TODO §P1 step 5) must wait for it |

## Pricing model — Option A: One-time perpetual license

| Item | Approved value |
|---|---|
| Model | One-time license per device (app never expires) |
| Price | **$149 one-time** |
| Optional renewal | **$59/year** for continued updates + support after the first included year (license itself never expires) |
| Free trial | **14 days** (confirmed) |
| Refund policy | **14 days, no questions asked** (confirmed) |
| Update policy | **Free updates for 1 year from purchase date** (confirmed) |
| Support policy | **Email support, 48-hour response time** (confirmed) |

## Market & currency

| Item | Approved value |
|---|---|
| Target market | **Egypt + Arab world** |
| Base currency | **USD** (buyer-facing local display handled by Freemius checkout; fees verified in Phase 3 with cited URLs) |

## Expiry behavior (from pricing model, carried into Phase 3.4 plan)

- Trial expired → read-only access + data export. Never a lockout.
- License lapsed (renewal unpaid) → the app itself keeps working forever; only *updates/support* stop. Read-only + export never applies to the perpetual license — it applies to the trial end state.

## Change log

- 2026-10-03: created from owner-approved answers (Phase 0 Q1–Q5 + Phase 2 confirmations). Trial/refund/update/support = playbook defaults, each explicitly confirmed by the owner.

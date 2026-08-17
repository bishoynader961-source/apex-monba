# Requirement Map — Edge Retail Pharmacy POS

Maps the unified specification concerns to implementation status. Each item cites
the test/route that verifies it.

## Concern 1 — Manager approval for high-risk actions
- **Status:** VERIFIED
- **Proof:** `POST /api/v1/pos/approve` (PIN verify → single-use token) +
  `POST /api/v1/pos/drawer/movement` gated by `X-Approval-Token` (single-use, scope `drawer.move`).
- **Test:** `test_manager_approval_issues_token_and_gates_drawer` (backend_fastapi/tests/test_pos_hardening.py).
- UI: `components/ManagerApprovalDialog.tsx`, `ShiftCloseDialog.tsx`.

## Concern 4 — Lot traceability / recall
- **Status:** VERIFIED (recall + FEFO); explicit per-line lot picker NOT implemented
- **Proof:** `inventory_extended.recalled` flag; `InventoryService.fifo_deduct` is FEFO and raises
  `RecalledLotError`/`ExpiredLotError`/`OverSellError`/`MissingLotError` → **410 Gone**.
- **Tests:** `test_expired_lot_checkout_returns_410`, `test_recalled_lot_checkout_returns_410`.
- Gap: multi-unit sale does not let the cashier pick a specific lot per line (FEFO auto-selects).

## Concern 8 — Edge PII local encryption
- **Status:** VERIFIED (crypto module); not yet applied to every PII field at rest
- **Proof:** `lib/offlineCrypto.ts` + `lib/offlineCryptoWorker.ts` — Web Crypto PBKDF2-HMAC-SHA256 @200k.
- Module exists and is wired for at-rest PII; field-level encryption of all PII columns is a follow-up.

## Appendix A.3 — Integer-cents / Decimal money
- **Status:** VERIFIED
- **Proof:** backend `Decimal`/`NUMERIC(10,2)`; frontend `lib/decimalCurrency` (bigint cents, no float).
- **Tests:** `test_money_serialised_as_string` (backend) + `lib/decimalCurrency.test.ts` (frontend).

## Appendix B.7 / B.8 — Server timestamp + cashier attribution
- **Status:** VERIFIED
- **Proof:** `receipts.server_created_at`/`ts_skew_confidence`/`created_by`/`cashier_attribution`;
  `CheckoutResult` exposes them; checkout stamps server time + skew + attribution.
- **Test:** `test_checkout_records_server_time_and_cashier`.

## C.1 — Multi-terminal merge-sync (FIFO + exact-once)
- **Status:** VERIFIED
- **Proof:** `SyncService.push` applies FIFO by `(device_id, local_seq)`, dedups on `client_txn_id`;
  `posStore.flushQueue` replays offline sales with `client_txn_id` + Lamport `local_seq`.
- **Test:** `test_sync_push_dedups_on_client_txn_id`.

## C.2 — Read replica / snapshot
- **Status:** VERIFIED
- **Proof:** `build_read_engine()` (`mode=ro`, `busy_timeout=30000`) + `get_read_session()`;
  `vacuum_snapshot()` on a 6h lifespan loop.
- **Test:** `test_read_session_fallback_for_memory`.

## C.3 — Versioned migrations
- **Status:** VERIFIED
- **Proof:** `migrate_schema` runs via `PRAGMA user_version` (v1→v3), idempotent + crash-safe.
- **Test:** `test_migration_idempotent`.

## C.4 — PIN peppering (kiosk auth)
- **Status:** VERIFIED
- **Proof:** `security.PinPepper` (device-bound DPAPI/file/env); `AuthService.approve_action` verifies
  manager PIN and issues approval token. Off-machine pepper → PIN verify impossible.

## Carry-forward (explicit non-goals)
PHI encryption-at-rest on all columns, audit-log append-only/chain, returns workflow, full users CRUD,
desktop shell, coverage ≥90%.

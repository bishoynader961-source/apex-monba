# Hardening Calibration

Operational tuning values for the edge kiosk. All values are also encoded in
`deployment/policies.json` and applied at deploy time.

## Crypto

| Parameter | Value | Rationale |
|---|---|---|
| PIN PBKDF2 iterations | 200,000 | ~120 ms on kiosk HW; throttles offline PIN brute-force. |
| Offline PII PBKDF2 iterations | 200,000 | Matches PIN KDF; key-derivation for at-rest PII. |
| KDF | PBKDF2-HMAC-SHA256 | Conservative, FIPS-friendly, no native dependency. |
| PIN pepper | Device-bound (DPAPI `LOCAL_MACHINE`) | DB exfiltrated off-machine cannot verify any PIN. |

## Concurrency / Locking

- `uvicorn --workers 1` is **mandatory**. The Lamport `local_seq` + in-process
  `asyncio.Lock` are single-process invariants; multiple workers would split the
  lock and break exact-once replay ordering. Multi-terminal scale-out uses the
  merge-sync hub, not multiple workers on one box.
- Cross-tab replay is serialized by the 3-tier `SyncLock` (in-memory →
  BroadcastChannel → server probe).

## Rate limiting

- SlowAPI limits applied to `/api/v1/auth/*` and `/api/v1/pos/checkout`.
- PIN lockout: 5 failed attempts → 15-minute lock; lockout counters are
  HMAC-sealed by the pepper so they cannot be reset by editing the DB offline.

## Backup / durability

- Snapshot cadence: `VACUUM INTO` every 360 minutes (6h), 7 copies retained.
- Sync outbox (`SyncOutbox`) is the durable record of terminal sales; the hub
  replays it FIFO by `(device_id, local_seq)` and dedups on `client_txn_id`.

## Money integrity

- All money is `Decimal`/`NUMERIC(10,2)` end-to-end. Frontend uses integer-cents
  (`bigint`) math — no floating point in pricing, tax, or totals.
- Over-sell / expired / recalled lots return **410 Gone**, never a silent 200.

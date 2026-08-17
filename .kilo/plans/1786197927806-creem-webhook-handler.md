# Plan: Creem Webhook Handler for Flask License Server

## Context
The deployed license server (`archive/server_app.py`, PythonAnywhere) provisions HWID‑bound
license keys from payment webhooks. It currently handles **Paddle** (`/api/webhook/paddle`,
lines 1086–1323) and **no Lemon Squeezy handler actually exists** in this file (despite the brief —
flagged as a follow‑up, out of scope here). We are adding **Creem** ($50/month Pro Plan) so a
Creem checkout provisions/revokes licenses exactly like Paddle.

Decision (confirmed with user): implement as an **inline section** in `server_app.py`, reusing
existing helpers — no new module/import coupling.

## Target file
`archive/server_app.py` (the deployed license server). All changes are additive.

## Reused existing building blocks (do NOT reimplement)
- `_generate_key("PHARM")`, `send_license_email(email, key)`, `send_sale_alert(email, amount, "creem", key)`
- `_get_db()`, `_log_request(endpoint, status)`, `logger`
- `_parse_expiry()`, `WEBHOOK_TEST_MODE`, `licenses` table (idempotency via `subscription_id` column)

## Changes

### 1. Add `import base64` (missing today)
Top imports: add `import base64` alongside `import hashlib` / `import hmac`.

### 2. Add config line (near `PADDLE_WEBHOOK_SECRET`, ~line 108)
```python
CREEM_WEBHOOK_SECRET = os.environ.get("CREEM_WEBHOOK_SECRET", "")
```

### 3. Add inline route `/api/webhook/creem` (after the Paddle webhook block, before `# ── Helpers ──`)
Signature: HMAC‑SHA256 over **raw bytes** of the request body, base64‑encoded, compared to the
`creem-signature` header via `hmac.compare_digest`. Skipped when `WEBHOOK_TEST_MODE=1`.

Events:
| Creem event | Action |
|---|---|
| `checkout.completed` | Create 30‑day license (idempotent by `subscription_id`), email + sale alert |
| `subscription.paid` | Extend expiry +30 days (renewal) |
| `subscription.active` / `subscription.resumed` | Reactivate (`status='active'`) |
| `subscription.canceled` / `subscription.expired` / `subscription.paused` | Revoke (`status='revoked'`) |
| (any other) | Log + return 200 `ignored` |

Field extraction is **defensive** (Creem uses camelCase `eventType` + `object`; some clients send
snake_case). Use:
- `event_type = payload.get("eventType") or payload.get("event_type", "")`
- `obj = payload.get("object", {}) or {}`
- `email` from `obj.customer.email` (if dict) else `obj.customer_email`
- `sub_id = str(obj.get("subscription_id") or obj.get("id") or "")`  ← `subscription.paid` puts the id in `object.id`
- `amount` from `obj.order.amount` / `obj.subscription.amount`, default `"50.00"`

**Reference implementation (paste verbatim, adjusting field paths after live validation):**
```python
@app.route("/api/webhook/creem", methods=["POST"])
def webhook_creem():
    """Handle Creem webhook (HMAC-SHA256/base64 over raw body, header `creem-signature`)."""
    if not CREEM_WEBHOOK_SECRET and not WEBHOOK_TEST_MODE:
        logger.warning("Creem webhook received but CREEM_WEBHOOK_SECRET not configured")
        _log_request("/api/webhook/creem", 500)
        return jsonify({"error": "Webhook not configured"}), 500

    raw_body = request.get_data()  # bytes — must match exactly what Creem signed
    signature = request.headers.get("creem-signature", "")

    if not signature and not WEBHOOK_TEST_MODE:
        _log_request("/api/webhook/creem", 400)
        return jsonify({"error": "Missing creem-signature header"}), 400

    if WEBHOOK_TEST_MODE:
        logger.info("Creem webhook — TEST MODE: signature verification skipped")
    else:
        expected = base64.b64encode(
            hmac.new(CREEM_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).digest()
        ).decode()
        if not hmac.compare_digest(expected, signature):
            logger.warning("Creem webhook signature mismatch")
            _log_request("/api/webhook/creem", 403)
            return jsonify({"error": "Invalid signature"}), 403

    try:
        payload = json.loads(raw_body.decode() or "{}")
        event_type = payload.get("eventType") or payload.get("event_type", "")
        obj = payload.get("object", {}) or {}

        customer = obj.get("customer", {}) or {}
        email = (customer.get("email", "") if isinstance(customer, dict) else "") or obj.get("customer_email", "")
        sub_id = str(obj.get("subscription_id") or obj.get("id") or "")
        amount = str(
            (obj.get("order", {}) or {}).get("amount", "")
            or (obj.get("subscription", {}) or {}).get("amount", "")
            or "50.00"
        )

        db = _get_db()
        now = datetime.now(timezone.utc)

        if event_type == "checkout.completed":
            if sub_id:
                existing = db.execute(
                    "SELECT license_key FROM licenses WHERE subscription_id = ?", (sub_id,)
                ).fetchone()
                if existing:
                    logger.info("Creem checkout.completed — duplicate sub %s, skipping", sub_id)
                    _log_request("/api/webhook/creem", 200)
                    return jsonify({"status": "ok", "license_key": existing["license_key"], "note": "already_exists"})
            license_key = _generate_key("PHARM")
            expires_at = now + timedelta(days=30)
            db.execute(
                "INSERT INTO licenses (license_key, email, status, created_at, expires_at, subscription_id) "
                "VALUES (?, ?, 'active', ?, ?, ?)",
                (license_key, email, now.isoformat(), expires_at.isoformat(), sub_id or None),
            )
            db.commit()
            email_sent = send_license_email(email, license_key)
            send_sale_alert(email, amount, "creem", license_key)
            logger.info("Creem checkout.completed — license: %s for %s (sub=%s)", license_key, email, sub_id)
            _log_request("/api/webhook/creem", 200)
            return jsonify({"status": "ok", "license_key": license_key})

        if event_type == "subscription.paid":
            if not sub_id:
                _log_request("/api/webhook/creem", 200)
                return jsonify({"status": "ignored", "reason": "no_subscription_id"})
            row = db.execute("SELECT license_key, expires_at FROM licenses WHERE subscription_id = ?", (sub_id,)).fetchone()
            if not row:
                logger.warning("Creem subscription.paid — no license for sub %s", sub_id)
                _log_request("/api/webhook/creem", 200)
                return jsonify({"status": "ignored", "reason": "license_not_found"})
            base = max(_parse_expiry(row["expires_at"]), now)
            new_expiry = base + timedelta(days=30)
            db.execute("UPDATE licenses SET expires_at = ?, status = 'active' WHERE license_key = ?",
                       (new_expiry.isoformat(), row["license_key"]))
            db.commit()
            logger.info("Creem subscription.paid — key=%s extended to %s (sub=%s)", row["license_key"], new_expiry.date(), sub_id)
            _log_request("/api/webhook/creem", 200)
            return jsonify({"status": "ok", "license_key": row["license_key"], "expires_at": new_expiry.isoformat()})

        if event_type in ("subscription.active", "subscription.resumed"):
            if not sub_id:
                _log_request("/api/webhook/creem", 200)
                return jsonify({"status": "ignored", "reason": "no_subscription_id"})
            row = db.execute("SELECT license_key FROM licenses WHERE subscription_id = ?", (sub_id,)).fetchone()
            if not row:
                _log_request("/api/webhook/creem", 200)
                return jsonify({"status": "ignored", "reason": "license_not_found"})
            db.execute("UPDATE licenses SET status = 'active' WHERE license_key = ?", (row["license_key"],))
            db.commit()
            logger.info("Creem %s — key=%s reactivated (sub=%s)", event_type, row["license_key"], sub_id)
            _log_request("/api/webhook/creem", 200)
            return jsonify({"status": "ok", "license_key": row["license_key"], "status": "active"})

        if event_type in ("subscription.canceled", "subscription.expired", "subscription.paused"):
            if not sub_id:
                _log_request("/api/webhook/creem", 200)
                return jsonify({"status": "ignored", "reason": "no_subscription_id"})
            row = db.execute("SELECT license_key FROM licenses WHERE subscription_id = ?", (sub_id,)).fetchone()
            if not row:
                _log_request("/api/webhook/creem", 200)
                return jsonify({"status": "ignored", "reason": "license_not_found"})
            db.execute("UPDATE licenses SET status = 'revoked' WHERE license_key = ?", (row["license_key"],))
            db.commit()
            logger.info("Creem %s — key=%s revoked (sub=%s)", event_type, row["license_key"], sub_id)
            _log_request("/api/webhook/creem", 200)
            return jsonify({"status": "ok", "license_key": row["license_key"], "status": "revoked"})

        logger.info("Creem webhook — unhandled event: %s", event_type)
        _log_request("/api/webhook/creem", 200)
        return jsonify({"status": "ignored", "event": event_type})

    except Exception:
        logger.exception("Creem webhook processing error")
        _log_request("/api/webhook/creem", 500)
        return jsonify({"error": "Webhook processing failed"}), 500
```

## Risks / open questions
- **Creem payload schema must be validated against a real sample.** The field paths
  (`eventType`, `object.customer.email`, `object.subscription_id` vs `object.id`) are best‑guess
  from Creem docs; defensive fallbacks are included but the implementing agent should POST one
  live test event and adjust paths if needed. This is the #1 thing to verify before going live.
- Secret must be set in the **PythonAnywhere env / `.env`** as `CREEM_WEBHOOK_SECRET` — never
  hardcoded, never committed.
- `base64` import is not present today — add it (step 1).

## Validation
1. Signature unit test: build a JSON payload, compute `creem-signature` with a test secret, POST to
   `/api/webhook/creem`, assert 200 + new `licenses` row; assert retry (same `subscription_id`)
   returns `already_exists` (no duplicate).
2. Mismatch test: wrong signature → 403.
3. `WEBHOOK_TEST_MODE=1` → signature skipped, still provisions.
4. Manual: set `CREEM_WEBHOOK_SECRET` on PythonAnywhere, point Creem dashboard webhook URL to
   `https://inventory1app1nn.pythonanywhere.com/api/webhook/creem`, send a test `checkout.completed`,
   confirm log line + DB row + license email (SMTP must be configured).

## Out of scope (flagged)
- The claimed Lemon Squeezy handler is absent from `server_app.py`; add separately if required.
- Creem customer‑portal / refund handling.

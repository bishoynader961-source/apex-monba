# End-to-End Testing Guide

This guide covers local and remote testing of the full license lifecycle:
**payment webhook → license creation → email delivery → client activation**.

---

## Prerequisites

| Tool | Purpose |
|---|---|
| Python 3.12+ | Run the Flask server locally |
| `ngrok` (optional) | Expose local server to the internet for live gateway webhooks |
| `hub.py` | Built-in test webhook tool (no external services needed) |
| SMTP credentials | For email delivery testing (or set `SMTP_*` vars to skip) |

Install dependencies:
```bash
cd archive
pip install -r ../requirements.txt
```

---

## 1. Local Server Startup

```bash
cd archive
python server_app.py
```

Server runs at `http://localhost:5000`. All webhook endpoints are available immediately.

### Verify health
```bash
curl http://localhost:5000/api/health
# → {"status": "ok"}
```

---

## 2. Enable Test Mode

Test mode skips HMAC-SHA256 signature verification so you can fire mock payloads without real webhook secrets.

Set in `archive/.env`:
```
WEBHOOK_TEST_MODE=1
```

Or export in your shell:
```bash
$env:WEBHOOK_TEST_MODE="1"   # PowerShell
export WEBHOOK_TEST_MODE=1    # bash
```

**Restart the server after changing this.**

---

## 3. Test with `hub.py` (Recommended)

`hub.py` includes a `test-webhook` command that fires properly formatted mock payloads.

### Lemon Squeezy test
```bash
python hub.py test-webhook --gateway lemonsqueezy
```

### Paddle test
```bash
python hub.py test-webhook --gateway paddle
```

### What happens
1. `hub.py` generates a mock `order_created` / `payment_success` payload with a test email
2. Signs it with your webhook secret (or sends unsigned in test mode)
3. POSTs to `http://localhost:5000/api/webhook/<gateway>`
4. Server creates a license key, inserts it into `licenses.db`, attempts email delivery
5. You see the response in the terminal

### Verify the license was created
```bash
curl http://localhost:5000/api/validate -X POST -H "Content-Type: application/json" \
  -d '{"license_key": "PHARM-XXXX-XXXX-XXXX", "device_id": "test-device-001"}'
```

---

## 4. Test with `curl` (Manual)

### Lemon Squeezy mock payload
```bash
curl -X POST http://localhost:5000/webhooks/lemon-squeezy \
  -H "Content-Type: application/json" \
  -H "X-Signature: <hmac-sha256-hex-digest>" \
  -d '{
    "meta": { "event_name": "order_created" },
    "data": {
      "id": "ord_123",
      "type": "order",
      "attributes": {
        "user_email": "test@example.com"
      }
    }
  }'
```

The `X-Signature` header is an HMAC-SHA256 hex digest of the raw request body, computed
using `LEMON_SQUEEZEY_SIGNATURE_SECRET`. In test mode, set
`LEMON_SQUEEZEY_SIGNATURE_SECRET` to a known value and compute the signature with
`hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()`.

### Paddle mock payload
```bash
curl -X POST http://localhost:5000/api/webhook/paddle \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "paddle-signature: test-signature" \
  -d "alert_name=payment_success&alert_status=active&email=test@example.com"
```

### Expected response
```json
{"status": "ok", "license_key": "PHARM-A1B2-C3D4-E5F6"}
```

---

## 5. Test Email Delivery

After a webhook creates a license, the server calls `send_license_email()`.

### Verify email was sent
Check `archive/server.log` for:
```
License email sent → test@example.com  key=PHARM-A1B2-C3D4-E5F6
```

### If email fails
The webhook still returns 200 (email failure never blocks the payment flow). Check:
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SENDER_EMAIL` in `.env`
- Gmail users: use an [App Password](https://support.google.com/accounts/answer/185833), not your main password
- Check `server.log` for the full traceback

### Skip email during testing
Leave `SMTP_*` vars empty — the server logs `SMTP not configured — skipping` and continues.

---

## 6. Test Full Client Activation

After creating a license via webhook, test the full activation flow:

### Step 1: Validate the key
```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{"license_key": "PHARM-XXXX-XXXX-XXXX", "device_id": "my-pc-001", "hwid": "test-hwid-abc"}'
```

### Step 2: Check the database
```bash
sqlite3 archive/licenses.db "SELECT license_key, email, hwid, status FROM licenses;"
```

### Step 3: Test HWID reset (customer portal)
```bash
# Login
curl -X POST http://localhost:5000/api/portal/login \
  -H "Content-Type: application/json" \
  -d '{"license_key": "PHARM-XXXX-XXXX-XXXX"}'
# → copy session_token from response

# Reset HWID
curl -X POST http://localhost:5000/api/portal/reset-hwid \
  -H "Authorization: Bearer <session_token>"
```

---

## 7. Test with Live Gateway Webhooks (ngrok)

To test with real Lemon Squeezy or Paddle sandbox webhooks:

### Step 1: Start local server
```bash
cd archive
python server_app.py
```

### Step 2: Expose with ngrok
```bash
ngrok http 5000
```
Copy the `https://xxxx.ngrok.io` URL.

### Step 3: Configure gateway webhook URL
- **Lemon Squeezy**: Dashboard → Settings → Webhooks → Add endpoint
  - URL: `https://xxxx.ngrok.io/webhooks/lemon-squeezy`
- **Paddle**: Dashboard → Developer Tools → Webhooks → Add endpoint
  - URL: `https://xxxx.ngrok.io/api/webhook/paddle`

### Step 4: Disable test mode (use real secrets)
```
WEBHOOK_TEST_MODE=0
```
Set your real `LEMON_SQUEEZEY_SIGNATURE_SECRET` and `PADDLE_WEBHOOK_SECRET` in `.env`.

### Step 5: Trigger a test payment
- **Lemon Squeezy**: Dashboard → Products → Duplicate a product → Buy it with test email
- **Paddle**: Dashboard → Catalog → Create sandbox checkout link

### Step 6: Verify
1. Check `server.log` for the webhook hit
2. Check `licenses.db` for the new license
3. Check your email for the license delivery

---

## 8. Admin Dashboard Testing

```bash
# Open in browser
start archive/admin/index.html

# Or serve locally
python -m http.server 8080 --directory archive/admin
```

Enter your `SERVER_ADMIN_SECRET` to log in. Verify:
- Stats cards show correct counts
- License table loads with search/filter
- HWID reset button works

---

## 9. Customer Portal Testing

```bash
start archive/customer/index.html
```

Enter a license key created during testing. Verify:
- License details display correctly
- HWID status shows correctly
- Reset button respects 30-day cooldown

---

## Quick Smoke Test Script

Run this entire flow in one go:

```bash
# 1. Start server (in separate terminal)
cd archive && python server_app.py

# 2. Fire test webhook
python hub.py test-webhook --gateway lemonsqueezy

# 3. Check the license was created
$licenseKey = (sqlite3 archive/licenses.db "SELECT license_key FROM licenses ORDER BY id DESC LIMIT 1;")

# 4. Validate it
curl -X POST http://localhost:5000/api/validate `
  -H "Content-Type: application/json" `
  -d "{`"license_key`": `"$licenseKey`", `"device_id`": `"test-001`", `"hwid`": `"test-hwid`"}"

# 5. Check database
sqlite3 archive/licenses.db "SELECT * FROM licenses ORDER BY id DESC LIMIT 3;"
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Webhook not configured` | Set `WEBHOOK_TEST_MODE=1` or set the webhook secret in `.env` |
| `Missing paddle-signature header` | Set `WEBHOOK_TEST_MODE=1` or send with the header |
| `Invalid signature` | Secret mismatch — check `.env` matches your gateway dashboard |
| Email not sent | Check `SMTP_*` vars in `.env` and `server.log` for errors |
| `License not found` | Key wasn't created — check webhook response and `licenses.db` |
| Database locked | Only one Flask process should access `licenses.db` at a time |

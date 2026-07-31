import os
import json
import hashlib
import hmac
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen

REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
WEBHOOK_SECRET = os.environ.get("LEMON_SQUEEZY_WEBHOOK_SECRET", "")


def _verify_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verify Lemon Squeezy webhook signature using HMAC-SHA256."""
    if not WEBHOOK_SECRET:
        raise RuntimeError("LEMON_SQUEEZY_WEBHOOK_SECRET must be set.")
    if not signature_header:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Verify signature
        signature = self.headers.get("x-signature", "")
        if not _verify_signature(body, signature):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid signature"}).encode())
            return

        # Parse payload
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return

        # Only process order_created events
        event_type = payload.get("meta", {}).get("event_name", "")
        if event_type != "order_created":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"message": f"Ignored event: {event_type}"}).encode())
            return

        # Extract license key and customer email
        try:
            custom_data = payload["data"]["attributes"]["custom_data"] or {}
            license_key = custom_data.get("license_key", "")
            customer_email = payload["data"]["attributes"]["user_email"] or ""

            if not license_key:
                license_key = payload["data"]["attributes"].get("identifier", "")

            if not license_key:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "No license key found in payload"}).encode())
                return
        except (KeyError, TypeError) as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Missing payload field: {str(e)}"}).encode())
            return

        # Save to Upstash Redis
        try:
            license_data = {
                "email": customer_email,
                "status": "active",
                "device_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            set_url = f"{REDIS_URL}/set/license:{license_key}"
            set_payload = json.dumps(license_data)
            set_req = Request(
                set_url,
                data=set_payload.encode(),
                headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                method="POST",
            )
            urlopen(set_req)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Redis save failed: {str(e)}"}).encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "message": "License created",
            "license_key": license_key,
            "email": customer_email,
        }).encode())

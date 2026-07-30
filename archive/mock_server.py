"""
mock_server.py — Lightweight local mock for the PharmacyPro license API.

Run:
    python mock_server.py

Endpoints:
    POST /api/activate   — binds a license key to a device
    POST /api/validate   — checks if a key is active & device matches

In-memory store — keys reset on restart. Pre-loaded with a demo key:
    PHARM-DEMO-1234-5678
"""
import hashlib
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── In-memory license store ──────────────────────────────────────────────
# Each entry: { "status": "active", "device_id": None|str }
LICENSE_STORE: dict[str, dict] = {
    "PHARM-DEMO-1234-5678": {"status": "active", "device_id": None},
}


# ── Routes ───────────────────────────────────────────────────────────────
@app.route("/api/activate", methods=["POST"])
def activate():
    """
    Activate a license key by binding it to a device.

    Expected JSON: { "license_key": "PHARM-...", "device_id": "<sha256>" }
    Returns: 200/404/403/409 with { "activated": bool, "message": str }
    """
    body = request.get_json(silent=True) or {}
    license_key = (body.get("license_key") or "").strip()
    device_id = (body.get("device_id") or "").strip()

    if not license_key or not device_id:
        return jsonify({"activated": False, "message": "Missing license_key or device_id"}), 400

    record = LICENSE_STORE.get(license_key)

    if record is None:
        return jsonify({"activated": False, "message": "License key not found"}), 404

    if record["status"] != "active":
        return jsonify({"activated": False, "message": "License key is not active"}), 403

    # Already bound to this device — idempotent re-activation
    if record["device_id"] == device_id:
        return jsonify({"activated": True, "message": "License already activated on this device"}), 200

    # Bound to a different device — reject
    if record["device_id"] and record["device_id"] != device_id:
        return jsonify({"activated": False, "message": "This license is already bound to another device"}), 409

    # Bind now
    record["device_id"] = device_id
    return jsonify({"activated": True, "message": "License activated successfully"}), 200


@app.route("/api/validate", methods=["POST"])
def validate():
    """
    Validate that a license key is active and matches the requesting device.

    Expected JSON: { "license_key": "PHARM-...", "device_id": "<sha256>" }
    Returns: 200 { "valid": true } or 403 { "valid": false, "message": "..." }
    """
    body = request.get_json(silent=True) or {}
    license_key = (body.get("license_key") or "").strip()
    device_id = (body.get("device_id") or "").strip()

    if not license_key or not device_id:
        return jsonify({"valid": False, "message": "Missing license_key or device_id"}), 400

    record = LICENSE_STORE.get(license_key)

    if record is None or record["status"] != "active":
        return jsonify({"valid": False, "message": "License key not found or inactive"}), 403

    bound_device = record["device_id"]
    if bound_device and bound_device != device_id:
        return jsonify({"valid": False, "message": "License is bound to a different device"}), 403

    return jsonify({"valid": True}), 200


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "keys_loaded": len(LICENSE_STORE)}), 200


if __name__ == "__main__":
    print("=" * 50)
    print("  PharmacyPro License Mock Server")
    print("  http://127.0.0.1:5000")
    print("  Pre-loaded key: PHARM-DEMO-1234-5678")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=True)

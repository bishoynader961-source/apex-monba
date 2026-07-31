# Upstash Redis Database Design — PharmacyPro Licensing

## Key-Value Schema

### License Key Storage

**Key Format:** `license:{license_key}`

**Example:** `license:PP-XXXX-XXXX-XXXX-XXXX`

**Value (JSON):**
```json
{
  "email": "customer@example.com",
  "status": "active",
  "activated_device_id": null,
  "created_at": "2026-07-15T12:00:00Z"
}
```

### Field Descriptions

| Field | Type | Description |
|---|---|---|
| `email` | string | Customer email from Lemon Squeezy order |
| `status` | string | `"active"` or `"revoked"` |
| `activated_device_id` | string \| null | Hardware fingerprint — starts `null`, binds to first device on activation |
| `created_at` | string (ISO 8601) | Timestamp when license was created via webhook |

## Operations

### On Order Created (Webhook)
```
SET license:PP-XXXX-XXXX-XXXX-XXXX '{"email":"...","status":"active","activated_device_id":null,"created_at":"..."}'
```

### On Activation Request (Validate)
```
GET license:{key}  →  parse JSON
IF activated_device_id IS null:
    SET activated_device_id = instance_id
    SAVE back to Redis
    RETURN valid: true
ELIF activated_device_id == instance_id:
    RETURN valid: true
ELSE:
    RETURN valid: false (different machine)
```

### On License Check (app startup)
```
GET license:{key}  →  parse JSON
IF status == "active" AND activated_device_id == instance_id:
    RETURN valid: true
ELSE:
    RETURN valid: false
```

## Environment Variables (Upstash Dashboard)

```
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=AXxx...
```

## TTL / Expiry

Licencies do NOT expire by default (lifetime license). To add expiry:
- Add `"expires_at": "2027-07-15T00:00:00Z"` to the value object
- Check `datetime.now() < expires_at` during validation

# pharmacy-hwid

Native Rust client for secure hardware fingerprinting and offline license token validation for PharmacyPro.

## Build

### Prerequisites
- [Rust](https://rustup.rs/) (stable toolchain)

### Compile
```bash
cd hwid-client
cargo build --release
```

Binary output: `target/release/pharmacy-hwid.exe` (Windows) or `target/release/pharmacy-hwid` (Linux/macOS).

### Cross-compile for Windows (from Linux/macOS)
```bash
rustup target add x86_64-pc-windows-msvc
cargo build --release --target x86_64-pc-windows-msvc
```

## Commands

### `gen-hwid`
Generate this machine's hardware ID (SHA-256 of CPU + motherboard + disk serials).

```bash
pharmacy-hwid gen-hwid
# HWID: 59a9723e48bb6d5f5c51e7985d32098c6dbf12316fbeaa8784aa994ab33fdea7
```

### `validate`
Validate a license key against the live server. Returns an offline token on success.

```bash
pharmacy-hwid validate --key PHARM-XXXX-XXXX-XXXX
pharmacy-hwid validate --key PHARM-XXXX --server https://custom-server.com/api
```

### `activate`
Activate a license key on this device. Binds the HWID to the key server-side.

```bash
pharmacy-hwid activate --key PHARM-XXXX-XXXX-XXXX
```

### `verify-token`
Verify an offline token locally (no server connection required). Tokens are valid for 7 days.

```bash
pharmacy-hwid verify-token --token <token_string>
pharmacy-hwid verify-token --cached    # reads from ~/.license_token
```

### `save-token`
Manually save a token to the local cache.

```bash
pharmacy-hwid save-token --token <token_string>
```

### `health`
Check server connectivity.

```bash
pharmacy-hwid health
```

## Server API Endpoints

The client communicates with the PythonAnywhere backend:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/validate` | POST | Validate license key + HWID, returns offline token |
| `/api/activate` | POST | Bind license to device, returns offline token |
| `/api/verify-token` | POST | Server-side token verification |
| `/api/health` | GET | Health check |

### Request/Response Format

**Validate:**
```json
POST /api/validate
{
  "license_key": "PHARM-XXXX-XXXX-XXXX",
  "device_id": "<sha256-hash>",
  "hwid": "<sha256-hash>"
}

Response 200:
{
  "valid": true,
  "message": "License valid",
  "offline_token": "<signed-jwt-like-token>",
  "offline_grace_days": 7
}
```

**Verify Token (offline):**
The client decodes the base64url payload and checks `expires_at` locally without contacting the server. For full cryptographic verification, use the `/api/verify-token` endpoint.

## Offline Token Structure

Tokens are issued as `{header}.{payload}.{signature}` (JWT-like format).

The payload contains:
```json
{
  "license_key": "PHARM-XXXX-XXXX-XXXX",
  "device_id": "abc123...",
  "hwid": "def456...",
  "expires_at": "2026-08-05T18:14:27.683640+00:00",
  "issued_at": "2026-07-29T18:14:27.683640+00:00"
}
```

Tokens are cached to `~/.license_token` automatically after successful validation/activation.

## CI/CD

A GitHub Actions workflow (`.github/workflows/build-rust.yml`) builds binaries for:
- Windows (x86_64-pc-windows-msvc)
- Linux (x86_64-unknown-linux-gnu)
- macOS (aarch64-apple-darwin)

Push a tag (`v*`) to trigger a release:
```bash
git tag v1.0.0
git push origin v1.0.0
```

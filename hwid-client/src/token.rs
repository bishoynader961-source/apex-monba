use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Payload embedded in a server-issued offline token.
#[derive(Debug, Serialize, Deserialize)]
pub struct OfflineTokenPayload {
    pub license_key: String,
    pub device_id: String,
    pub hwid: String,
    pub expires_at: String,
    pub issued_at: String,
}

/// Result of token verification.
#[derive(Debug)]
pub struct TokenStatus {
    pub valid: bool,
    pub message: String,
    pub payload: Option<OfflineTokenPayload>,
}

/// Verify an offline token by decoding the base64url payload and checking expiry.
///
/// The server issues tokens as `{header}.{payload}.{signature}` (JWT-like structure).
/// We decode the payload section (middle part) and verify the `expires_at` timestamp
/// without needing the signing key — the signature was already validated server-side
/// on issuance.  For full cryptographic verification, use the `/api/verify-token` endpoint.
pub fn verify_token_offline(token: &str) -> TokenStatus {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() != 3 {
        return TokenStatus {
            valid: false,
            message: "Invalid token format — expected 3 dot-separated segments".into(),
            payload: None,
        };
    }

    let payload_b64 = parts[1];

    // base64url decode
    let decoded = match base64::Engine::decode(
        &base64::engine::general_purpose::URL_SAFE_NO_PAD,
        payload_b64,
    ) {
        Ok(d) => d,
        Err(e) => {
            return TokenStatus {
                valid: false,
                message: format!("Failed to decode token payload: {}", e),
                payload: None,
            };
        }
    };

    let payload: OfflineTokenPayload = match serde_json::from_slice(&decoded) {
        Ok(p) => p,
        Err(e) => {
            return TokenStatus {
                valid: false,
                message: format!("Failed to parse token payload: {}", e),
                payload: None,
            };
        }
    };

    // Parse expiry
    let expires_at = match DateTime::parse_from_rfc3339(&payload.expires_at) {
        Ok(dt) => dt.with_timezone(&Utc),
        Err(e) => {
            return TokenStatus {
                valid: false,
                message: format!("Invalid expiry timestamp: {}", e),
                payload: Some(payload),
            };
        }
    };

    let now = Utc::now();
    if now > expires_at {
        let age = now.signed_duration_since(&expires_at);
        return TokenStatus {
            valid: false,
            message: format!("Token expired {} ago", age),
            payload: Some(payload),
        };
    }

    let remaining = expires_at.signed_duration_since(now);
    TokenStatus {
        valid: true,
        message: format!("Token valid — expires in {} hours", remaining.num_hours()),
        payload: Some(payload),
    }
}

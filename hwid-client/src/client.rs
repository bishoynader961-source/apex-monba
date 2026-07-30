use serde::{Deserialize, Serialize};
use std::time::Duration;

const DEFAULT_API_BASE: &str = "https://inventory1app1nn.pythonanywhere.com/api";
const TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Debug, Serialize)]
pub struct ValidateRequest {
    pub license_key: String,
    pub device_id: String,
    pub hwid: String,
}

#[derive(Debug, Deserialize)]
pub struct ValidateResponse {
    pub valid: bool,
    pub message: String,
    #[serde(default)]
    pub offline_token: Option<String>,
    #[serde(default)]
    pub offline_grace_days: Option<u32>,
}

#[derive(Debug, Serialize)]
pub struct ActivateRequest {
    pub license_key: String,
    pub device_id: String,
    pub hwid: String,
}

#[derive(Debug, Deserialize)]
pub struct ActivateResponse {
    pub activated: bool,
    pub message: String,
    #[serde(default)]
    pub offline_token: Option<String>,
    #[serde(default)]
    pub offline_grace_days: Option<u32>,
}

#[derive(Debug, Deserialize)]
pub struct VerifyTokenResponse {
    pub valid: bool,
    pub message: String,
    #[serde(default)]
    pub license_key: Option<String>,
    #[serde(default)]
    pub device_id: Option<String>,
    #[serde(default)]
    pub hwid: Option<String>,
    #[serde(default)]
    pub expires_at: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct HealthResponse {
    pub status: String,
}

/// Create an HTTP client with sensible defaults.
fn client() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(TIMEOUT)
        .danger_accept_invalid_certs(false)
        .build()
        .expect("Failed to build HTTP client")
}

/// Validate a license key against the server.
pub async fn validate(
    api_base: Option<&str>,
    key: &str,
    device_id: &str,
    hwid: &str,
) -> Result<ValidateResponse, String> {
    let base = api_base.unwrap_or(DEFAULT_API_BASE);
    let url = format!("{}/validate", base);

    let body = ValidateRequest {
        license_key: key.to_string(),
        device_id: device_id.to_string(),
        hwid: hwid.to_string(),
    };

    let resp = client()
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("Failed to read response: {}", e))?;

    if !status.is_success() {
        return Err(format!("HTTP {} — {}", status, text));
    }

    serde_json::from_str::<ValidateResponse>(&text)
        .map_err(|e| format!("Failed to parse response: {} — {}", e, text))
}

/// Activate a license key on this device.
pub async fn activate(
    api_base: Option<&str>,
    key: &str,
    device_id: &str,
    hwid: &str,
) -> Result<ActivateResponse, String> {
    let base = api_base.unwrap_or(DEFAULT_API_BASE);
    let url = format!("{}/activate", base);

    let body = ActivateRequest {
        license_key: key.to_string(),
        device_id: device_id.to_string(),
        hwid: hwid.to_string(),
    };

    let resp = client()
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("Failed to read response: {}", e))?;

    if !status.is_success() {
        return Err(format!("HTTP {} — {}", status, text));
    }

    serde_json::from_str::<ActivateResponse>(&text)
        .map_err(|e| format!("Failed to parse response: {} — {}", e, text))
}

/// Verify an offline token with the server.
pub async fn verify_token(
    api_base: Option<&str>,
    token: &str,
) -> Result<VerifyTokenResponse, String> {
    let base = api_base.unwrap_or(DEFAULT_API_BASE);
    let url = format!("{}/verify-token", base);

    let body = serde_json::json!({ "token": token });

    let resp = client()
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("Failed to read response: {}", e))?;

    if !status.is_success() {
        return Err(format!("HTTP {} — {}", status, text));
    }

    serde_json::from_str::<VerifyTokenResponse>(&text)
        .map_err(|e| format!("Failed to parse response: {} — {}", e, text))
}

/// Health check.
pub async fn health(api_base: Option<&str>) -> Result<HealthResponse, String> {
    let base = api_base.unwrap_or(DEFAULT_API_BASE);
    let url = format!("{}/health", base);

    let resp = client()
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("Failed to read response: {}", e))?;

    if !status.is_success() {
        return Err(format!("HTTP {} — {}", status, text));
    }

    serde_json::from_str::<HealthResponse>(&text)
        .map_err(|e| format!("Failed to parse response: {} — {}", e, text))
}

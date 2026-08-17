//! rust_crypto — Native Rust Fernet encryption for PharmacyPro.
//!
//! Provides `encrypt_py` and `decrypt_py` functions that implement the Fernet
//! token format (AES-128-CBC + HMAC-SHA256), matching the Python Fernet spec.
//!
//! Token format: base64url(0x80 || timestamp(8) || IV(16) || ciphertext || HMAC(32))
//!
//! These functions are called by crypto_utils.py's _RustBackend class:
//!     rust_crypto.encrypt_py(data_json_str, key_base64_str) -> token_str
//!     rust_crypto.decrypt_py(token_str, key_base64_str) -> data_json_str

use pyo3::prelude::*;
use aes::Aes128;
use aes::cipher::{block_padding::Pkcs7, BlockDecryptMut, BlockEncryptMut, KeyIvInit};
use aes::cipher::generic_array::GenericArray;
use hmac::{Hmac, Mac};
use sha2::Sha256;
use pbkdf2::pbkdf2_hmac;
use base64::engine::general_purpose::{URL_SAFE, URL_SAFE_NO_PAD};
use base64::Engine;
use rand::rng;
use rand::RngCore;
use std::time::{SystemTime, UNIX_EPOCH};

type AesCbcEnc = cbc::Encryptor<Aes128>;
type AesCbcDec = cbc::Decryptor<Aes128>;
type HmacSha256 = Hmac<Sha256>;

const TOKEN_VERSION: u8 = 0x80;

/// Encrypt data using Fernet (AES-128-CBC + HMAC-SHA256).
#[pyfunction]
fn encrypt_py(data: &str, key: &str) -> PyResult<String> {
    let raw_key = decode_key(key)?;
    let signing_key = &raw_key[0..16];
    let encryption_key = &raw_key[16..32];

    // Generate random 16-byte IV
    let mut iv = [0u8; 16];
    rng().fill_bytes(&mut iv);

    // AES-128-CBC encryption with PKCS7 padding
    let key_arr = GenericArray::from_slice(encryption_key);
    let iv_arr = GenericArray::from_slice(&iv);
    let cipher = AesCbcEnc::new(key_arr, iv_arr);
    let ciphertext = cipher.encrypt_padded_vec_mut::<Pkcs7>(data.as_bytes());

    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Clock err: {}", e)))?
        .as_secs() as u64;

    let mut content = Vec::with_capacity(1 + 8 + 16 + ciphertext.len());
    content.push(TOKEN_VERSION);
    content.extend_from_slice(&timestamp.to_be_bytes());
    content.extend_from_slice(&iv);
    content.extend_from_slice(&ciphertext);

    let mac = compute_hmac(signing_key, &content);
    content.extend_from_slice(&mac);

    Ok(URL_SAFE_NO_PAD.encode(&content))
}

/// Decrypt a Fernet token.
#[pyfunction]
fn decrypt_py(token: &str, key: &str) -> PyResult<String> {
    let raw_key = decode_key(key)?;
    let signing_key = &raw_key[0..16];
    let encryption_key = &raw_key[16..32];

    let token_bytes = URL_SAFE_NO_PAD.decode(token)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Bad base64: {}", e)))?;

    if token_bytes.len() < 57 {
        return Err(pyo3::exceptions::PyValueError::new_err("Token too short"));
    }

    let version = token_bytes[0];
    if version != TOKEN_VERSION {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Bad version: {} != 128", version)
        ));
    }

    let timestamp = u64::from_be_bytes([
        token_bytes[1], token_bytes[2], token_bytes[3], token_bytes[4],
        token_bytes[5], token_bytes[6], token_bytes[7], token_bytes[8],
    ]);

    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Clock err: {}", e)))?
        .as_secs() as u64;

    // TTL: 1 hour
    if now > timestamp + 3600 {
        return Err(pyo3::exceptions::PyValueError::new_err("Token expired"));
    }

    let iv = &token_bytes[9..25];
    let mac = &token_bytes[token_bytes.len() - 32..];
    let ciphertext = &token_bytes[25..token_bytes.len() - 32];

    let expected_mac = compute_hmac(signing_key, &token_bytes[..token_bytes.len() - 32]);
    if !hmac_verify(&expected_mac, mac) {
        return Err(pyo3::exceptions::PyValueError::new_err("HMAC mismatch"));
    }

    // AES-128-CBC decryption with PKCS7 unpadding
    let key_arr = GenericArray::from_slice(encryption_key);
    let iv_arr = GenericArray::from_slice(iv);
    let cipher = AesCbcDec::new(key_arr, iv_arr);
    let plaintext = cipher.decrypt_padded_vec_mut::<Pkcs7>(ciphertext)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Decrypt: {}", e)))?;

    String::from_utf8(plaintext)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("UTF-8: {}", e)))
}

/// Derive a Fernet key from the app secret via PBKDF2.
#[pyfunction]
fn derive_key(secret: &str, salt_b64: &str, iterations: u32) -> PyResult<String> {
    let salt_bytes = URL_SAFE.decode(salt_b64)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Bad salt: {}", e)))?;

    let mut key = [0u8; 32];
    pbkdf2_hmac::<Sha256>(secret.as_bytes(), &salt_bytes, iterations, &mut key);

    Ok(URL_SAFE_NO_PAD.encode(&key))
}

// ── Internal helpers ─────────────────────────────────────────────────────

fn decode_key(key: &str) -> PyResult<Vec<u8>> {
    URL_SAFE.decode(key)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Bad key: {}", e)))
}

fn compute_hmac(key: &[u8], data: &[u8]) -> [u8; 32] {
    let mut h = HmacSha256::new_from_slice(key).expect("HMAC accepts any key length");
    h.update(data);
    let result = h.finalize();
    let mut mac = [0u8; 32];
    mac.copy_from_slice(&result.into_bytes());
    mac
}

fn hmac_verify(a: &[u8; 32], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

/// Python module definition.
#[pymodule]
fn rust_crypto(m: Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(encrypt_py, &m)?)?;
    m.add_function(wrap_pyfunction!(decrypt_py, &m)?)?;
    m.add_function(wrap_pyfunction!(derive_key, &m)?)?;
    m.add("__version__", "1.0.0")?;
    Ok(())
}

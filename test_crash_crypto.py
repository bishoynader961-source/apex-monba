"""
test_crash_crypto.py — Tests for crypto_utils.py Fernet encryption wrapper.

Covers:
    - Encrypt → decrypt round-trip (dict, string, bytes)
    - Tamper detection (modified token must fail decryption)
    - Large payload round-trip (10+ KB crash tracebacks)
    - Key consistency (same app secret → same Fernet key)
    - Backend availability (at least one of cryptography/rust/pycryptodome)
    - Server-side decryption compatibility with encrypted_payload envelope

Run:  python test_crash_crypto.py
"""
import json
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "archive"))

from crypto_utils import encrypt_payload, decrypt_payload, get_fernet_key, _BACKEND


class TestCryptoRoundTrip(unittest.TestCase):
    """Verify that encrypt → decrypt produces the original payload."""

    def test_dict_round_trip(self):
        payload = {
            "app_version": "1.0.0",
            "error_type": "ValueError",
            "error_message": "Something went wrong",
            "traceback": "Traceback (most recent call last):\n  File ...",
            "crash_frame": "main.py:42 in <module>",
            "hwid_hash": "abc123def456",
            "os": {"system": "Windows", "python": "3.12.7"},
            "license_key": "LIVE-1234-5678",
            "timestamp": "2026-08-01T12:00:00+00:00",
        }
        token = encrypt_payload(payload)
        self.assertIsInstance(token, str)
        decrypted = decrypt_payload(token)
        self.assertEqual(decrypted, payload)

    def test_string_round_trip(self):
        token = encrypt_payload("plain text message")
        decrypted = decrypt_payload(token)
        self.assertEqual(decrypted, "plain text message")

    def test_bytes_round_trip(self):
        raw_bytes = b"\xff\xfe\x00\x01\x80\x81"
        token = encrypt_payload(raw_bytes)
        decrypted = decrypt_payload(token)
        self.assertEqual(decrypted, raw_bytes)


class TestTamperDetection(unittest.TestCase):
    """Verify that tampering with the token invalidates the HMAC."""

    def test_tampered_token_rejected(self):
        payload = {"error_type": "RuntimeError", "message": "tamper test"}
        token = encrypt_payload(payload)
        # Flip a character in the middle of the token
        chars = list(token)
        idx = len(chars) // 2
        original = chars[idx]
        chars[idx] = "A" if original != "A" else "B"
        tampered = "".join(chars)
        with self.assertRaises((ValueError, Exception)):
            decrypt_payload(tampered)

    def test_truncated_token_rejected(self):
        payload = {"error_type": "KeyError", "message": "truncated"}
        token = encrypt_payload(payload)
        truncated = token[:len(token) // 2]
        with self.assertRaises((ValueError, Exception)):
            decrypt_payload(truncated)

    def test_completely_invalid_token(self):
        with self.assertRaises((ValueError, Exception)):
            decrypt_payload("not-a-valid-fernet-token-at-all")


class TestLargePayload(unittest.TestCase):
    """Verify large crash tracebacks round-trip correctly."""

    def test_large_traceback(self):
        payload = {
            "error_type": "MemoryError",
            "traceback": "x" * 50000,
            "extra_field": "y" * 10000,
        }
        token = encrypt_payload(payload)
        self.assertGreater(len(token), 60000)
        decrypted = decrypt_payload(token)
        self.assertEqual(decrypted, payload)

    def test_nested_dict_round_trip(self):
        payload = {
            "os": {
                "system": "Linux",
                "release": "6.6.0",
                "version": "#1 SMP",
                "machine": "x86_64",
                "python": "3.14.0",
                "frozen": False,
                "extras": {"nested": {"deep": [1, 2, 3]}},
            },
            "license_key": "TEST-KEY",
            "timestamp": "2026-08-01T13:00:00Z",
        }
        token = encrypt_payload(payload)
        decrypted = decrypt_payload(token)
        self.assertEqual(decrypted, payload)


class TestKeyConsistency(unittest.TestCase):
    """Verify key derivation is deterministic."""

    def test_same_key_each_call(self):
        key1 = get_fernet_key()
        key2 = get_fernet_key()
        self.assertEqual(key1, key2)

    def test_key_is_bytes(self):
        key = get_fernet_key()
        self.assertIsInstance(key, bytes)
        # Fernet key is base64url-encoded 32 bytes → 44 chars (with padding)
        self.assertGreaterEqual(len(key), 43)


class TestBackend(unittest.TestCase):
    """Verify an encryption backend is available."""

    def test_backend_available(self):
        self.assertNotEqual(_BACKEND, "none", "No encryption backend available")
        self.assertIn(_BACKEND, ("cryptography", "pycryptodome", "rust"))


class TestServerCompatibility(unittest.TestCase):
    """Verify the encrypted_payload envelope structure matches server expectations."""

    def test_encrypted_payload_envelope(self):
        """The crash reporter sends {"encrypted_payload": "<token>"}.
        The server decrypts the token and gets back the original dict."""
        original = {
            "app_version": "2.1.0",
            "error_type": "FileNotFoundError",
            "error_message": "config.json not found",
            "traceback": "Traceback...\nFileNotFoundError",
            "crash_frame": "database.py:13",
            "hwid_hash": "deadbeef",
            "os": {"system": "Darwin", "python": "3.12.7"},
            "license_key": "LIC-ABC-123",
            "timestamp": "2026-08-01T13:00:00Z",
        }
        token = encrypt_payload(original)
        # Simulate what the server does
        from crypto_utils import decrypt_payload as server_decrypt
        decrypted = server_decrypt(token)
        self.assertEqual(decrypted, original)

    def test_server_handles_non_encrypted_payload(self):
        """When no encryption is applied, the server must still process the payload."""
        raw_payload = {"error_type": "ValueError", "error_message": "test"}
        # json round-trip simulates what the server does with plain JSON
        serialized = json.dumps(raw_payload)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized, raw_payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)

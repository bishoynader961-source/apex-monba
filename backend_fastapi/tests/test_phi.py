"""B5: PHI-at-rest encryption capability (machine-bound DPAPI)."""
from __future__ import annotations

import pytest

from app.shared.security import phi_decrypt, phi_encrypt


def test_phi_roundtrip() -> None:
    plaintext = "Jane Doe SSN 123-45-6789"
    ciphertext = phi_encrypt(plaintext)
    if ciphertext is None:
        pytest.skip("DPAPI unavailable on this platform")
    assert ciphertext != plaintext.encode("utf-8")
    assert phi_decrypt(ciphertext) == plaintext


def test_phi_undecryptable_off_machine() -> None:
    # A blob that was never produced by this machine's DPAPI must not yield PHI.
    assert phi_decrypt(b"not-a-valid-dpapi-blob") is None

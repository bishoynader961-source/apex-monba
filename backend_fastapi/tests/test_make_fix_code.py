"""Tests for scripts/make-fix-code.py (SPEC-09 Stage 2.3 toolkit).

The generator must be *bit-compatible* with the backend verifier, otherwise
every code an operator mints gets rejected with 403. These tests pin that
contract: the script's HMAC is cross-checked against
``support_fix_route.sign_payload`` and the emitted envelope is POSTed through
the real route.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.support_fix_route import sign_payload
from app.core.models import SystemSetting
from app.core.repositories import UserRepository
from app.shared.security import hash_password

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "make-fix-code.py"
URL = "/api/v1/support/fix-code/verify"
SECRET = "test-fix-code-secret"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("make_fix_code", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli() -> Any:
    return _load_module()


# ── Signature contract ────────────────────────────────────────────────────────


def test_envelope_signature_matches_backend(cli: Any) -> None:
    payload = {"key": "session_idle_minutes", "value": 60}
    envelope = cli.build_envelope("update_setting", payload, SECRET)
    assert envelope["sig"] == sign_payload(payload, SECRET)
    assert envelope["action"] == "update_setting"
    assert envelope["payload"] == payload


def test_typed_payload_signature_is_stable_across_json_round_trip(cli: Any) -> None:
    """A bool value must survive CLI → JSON → backend parse unchanged."""
    envelope = cli.build_envelope(
        "update_setting", {"key": "enable_receipts", "value": True}, SECRET
    )
    received = json.loads(json.dumps(envelope))
    assert isinstance(received["payload"]["value"], bool)
    assert received["sig"] == sign_payload(received["payload"], SECRET)


# ── Type casting ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("False", False),
        ("60", 60),
        ("0", 0),
        ("-5", -5),
        ("1.5", 1.5),
        ('{"a": 1}', {"a": 1}),
        ("[1, 2]", [1, 2]),
        ("null", None),
        ("enabled", "enabled"),
    ],
)
def test_cast_value(cli: Any, raw: str, expected: Any) -> None:
    assert cli.cast_value(raw) == expected and type(cli.cast_value(raw)) is type(expected)


# ── Secret resolution (fail-fast) ─────────────────────────────────────────────


def test_resolve_secret_reads_env_file(cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIX_CODE_SECRET", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n[section]\nOTHER=x\nFIX_CODE_SECRET=  from-file  \n", encoding="utf-8")
    assert cli.resolve_secret(None, env_file) == "from-file"


def test_explicit_secret_wins(cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIX_CODE_SECRET", "from-env")
    assert cli.resolve_secret("explicit", tmp_path / "missing.env") == "explicit"


def test_missing_secret_fails_fast(cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIX_CODE_SECRET", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.resolve_secret(None, tmp_path / "missing.env")
    assert exc.value.code == 1


# ── CLI surface ───────────────────────────────────────────────────────────────


def test_main_prints_compact_envelope(cli: Any, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["session_idle_minutes", "60", "--secret", SECRET]) == 0
    out = capsys.readouterr().out.strip()
    assert "\n" not in out  # pipe-friendly single line
    envelope = json.loads(out)
    assert envelope["payload"] == {"key": "session_idle_minutes", "value": 60}
    assert envelope["sig"] == sign_payload(envelope["payload"], SECRET)


def test_main_requires_key_and_value(cli: Any) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--secret", SECRET])
    with pytest.raises(SystemExit):
        cli.main(["only_key", "--secret", SECRET])


def test_reload_permissions_has_empty_payload(cli: Any) -> None:
    envelope = cli.build_envelope("reload_permissions", cli.build_payload("reload_permissions", None, None), SECRET)
    assert envelope["payload"] == {}
    assert envelope["sig"] == sign_payload({}, SECRET)


# ── End-to-end: generated code is accepted by the real route ──────────────────


@pytest.fixture
def backend_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    class _Cfg:
        fix_code_secret = SECRET

    monkeypatch.setattr("app.api.routers.support_fix_route.get_settings", lambda: _Cfg())
    return SECRET


async def _admin_token(client: AsyncClient, session: AsyncSession) -> str:
    await UserRepository(session).create("fixcli", "Fix CLI", hash_password("password123"), 1)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "fixcli", "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.anyio
async def test_generated_code_is_applied_end_to_end(
    cli: Any, client: AsyncClient, session: AsyncSession, backend_secret: str
) -> None:
    session.add(SystemSetting(key="session_idle_minutes", value=b"30"))
    await session.commit()
    token = await _admin_token(client, session)

    envelope = cli.build_envelope(
        "update_setting", {"key": "session_idle_minutes", "value": 60}, backend_secret
    )
    resp = await client.post(URL, json=envelope, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text

    session.expire_all()
    row = await session.get(SystemSetting, "session_idle_minutes")
    assert row.value.decode() == "60"


@pytest.mark.anyio
async def test_tampered_cli_code_is_rejected(
    cli: Any, client: AsyncClient, session: AsyncSession, backend_secret: str
) -> None:
    token = await _admin_token(client, session)
    envelope = cli.build_envelope(
        "update_setting", {"key": "session_idle_minutes", "value": 60}, backend_secret
    )
    envelope["payload"]["value"] = 9999  # edit after signing
    resp = await client.post(URL, json=envelope, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403

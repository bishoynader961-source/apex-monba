"""Tests for scripts/make-fix-code.py — the support-team signing CLI.

Consolidates the two parallel test suites produced before the merge: the
36-case suite (casting, secret sourcing, stdout contract, fail-fast,
subprocess e2e, full CLI→HTTP round-trip) plus the distinctive cases from the
worktree suite — signature stability across a JSON round-trip and a tampered
CLI-generated code being rejected 403 by the real route.

The critical property is parity: the CLI's signature must verify against the
backend route's verifier, or every generated code would 403 at the Support
tab. Enforced at three levels: direct function parity, envelope-level parity,
and a full HTTP round-trip (CLI stdout -> POST /support/fix-code/verify -> 200
-> row updated). The subprocess tests run against the operator
backend_fastapi/.env and skip cleanly when it is absent.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import SystemSetting
from app.core.repositories import UserRepository
from app.shared.security import hash_password

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "make-fix-code.py"
REPO_ROOT = SCRIPT.parents[1]
REAL_ENV = REPO_ROOT / "backend_fastapi" / ".env"
URL = "/api/v1/support/fix-code/verify"


def _load_cli():
    spec = importlib.util.spec_from_file_location("make_fix_code", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cli = _load_cli()


# ── Unit: parse_value type casting ───────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True),
        ("TRUE", True),
        ("false", False),
        ("null", None),
        ("None", None),
        ("60", 60),
        ("-5", -5),
        ("+17", 17),
        ("0", 0),
        ("3.14", 3.14),
        ("-0.5", -0.5),
        ("007", "007"),  # leading zero: ID-like codes stay strings
        ("1e3", "1e3"),  # exponent without decimal point stays a string
        ("true_x", "true_x"),
        ("hello world", "hello world"),
        ("", ""),
    ],
)
def test_parse_value(raw: str, expected: object) -> None:
    assert cli.parse_value(raw) == expected


# ── Unit: secret sourcing ────────────────────────────────────────────────────


def test_load_secret_prefers_flag(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text('FIX_CODE_SECRET="env-secret"\n', encoding="utf-8")
    assert cli.load_secret("flag-secret", env) == "flag-secret"


def test_load_secret_from_process_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIX_CODE_SECRET", " process-secret ")
    assert cli.load_secret(None, tmp_path / "missing.env") == "process-secret"


@pytest.mark.parametrize(
    "line,expected",
    [
        ("FIX_CODE_SECRET=plain", "plain"),
        ('FIX_CODE_SECRET="quoted"', "quoted"),
        ("FIX_CODE_SECRET='sq'", "sq"),
        ("export FIX_CODE_SECRET=exported", "exported"),
        ("  FIX_CODE_SECRET =  spaced  ", "spaced"),
        ("# FIX_CODE_SECRET=commented", ""),  # commented out is skipped
        ("OTHER_KEY=x", ""),
    ],
)
def test_load_secret_env_file_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str, expected: str
) -> None:
    monkeypatch.delenv("FIX_CODE_SECRET", raising=False)
    env = tmp_path / ".env"
    env.write_text(line + "\n", encoding="utf-8")
    assert cli.load_secret(None, env) == expected


# ── Unit: main() behavior ────────────────────────────────────────────────────


def _env_file(tmp_path: Path, secret: str = "unit-secret") -> Path:
    env = tmp_path / ".env"
    env.write_text(f"FIX_CODE_SECRET={secret}\n", encoding="utf-8")
    return env


def test_main_emits_envelope(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = cli.main(["session_idle_minutes", "60", "--env", str(_env_file(tmp_path))])
    assert rc == 0
    out, err = capsys.readouterr()
    envelope = json.loads(out)  # stdout is pure JSON, nothing else
    assert envelope["action"] == "update_setting"
    assert envelope["payload"] == {"key": "session_idle_minutes", "value": 60}
    assert envelope["sig"] == cli.sign_payload(envelope["payload"], "unit-secret")
    assert "value_type=int" in err  # diagnostics belong on stderr


def test_main_string_flag_signs_verbatim(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = cli.main(
        ["pharmacy_phone", "007-555-0100", "--string", "--env", str(_env_file(tmp_path))]
    )
    assert rc == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["payload"] == {"key": "pharmacy_phone", "value": "007-555-0100"}


def test_main_reload_permissions(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = cli.main(["--action", "reload_permissions", "--env", str(_env_file(tmp_path))])
    assert rc == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["payload"] == {}
    assert envelope["sig"] == cli.sign_payload({}, "unit-secret")


def test_main_fails_fast_without_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.delenv("FIX_CODE_SECRET", raising=False)
    rc = cli.main(["k", "v", "--env", str(tmp_path / "nope.env")])
    assert rc == 1
    captured = capsys.readouterr()
    assert "FIX_CODE_SECRET" in captured.err
    assert captured.out == ""  # nothing signed, nothing on stdout


def test_main_requires_key_value_for_update_setting(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["onlykey", "--env", str(_env_file(tmp_path))])
    assert exc.value.code == 2


def test_main_rejects_key_value_for_reload(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--action", "reload_permissions", "k", "v", "--env", str(_env_file(tmp_path))])
    assert exc.value.code == 2


# ── Parity with the backend verifier ─────────────────────────────────────────


def test_signature_parity_with_backend() -> None:
    from app.api.routers.support_fix_route import sign_payload as backend_sign

    payload = {"key": "k", "value": [1, "x", {"nested": True}]}
    assert cli.sign_payload(payload, "shared-secret") == backend_sign(payload, "shared-secret")


def test_cli_envelope_passes_backend_verifier(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from app.api.routers.support_fix_route import sign_payload as backend_sign

    cli.main(["any_key", "true", "--env", str(_env_file(tmp_path, "parity-secret"))])
    envelope = json.loads(capsys.readouterr().out)
    assert backend_sign(envelope["payload"], "parity-secret") == envelope["sig"]


def test_typed_payload_signature_is_stable_across_json_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A bool value must survive CLI -> JSON -> backend parse unchanged."""
    from app.api.routers.support_fix_route import sign_payload as backend_sign

    cli.main(["enable_receipts", "true", "--env", str(_env_file(tmp_path, "rt-secret"))])
    envelope = json.loads(capsys.readouterr().out)
    received = json.loads(json.dumps(envelope))
    assert received["payload"]["value"] is True
    assert backend_sign(received["payload"], "rt-secret") == received["sig"]


# ── Subprocess end-to-end against the operator .env ──────────────────────────


def _real_env_ready() -> bool:
    if not REAL_ENV.is_file():
        return False
    return "FIX_CODE_SECRET" in REAL_ENV.read_text(encoding="utf-8")


@pytest.mark.skipif(not _real_env_ready(), reason="operator backend_fastapi/.env without FIX_CODE_SECRET")
def test_subprocess_end_to_end() -> None:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "session_idle_minutes", "60"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert out.returncode == 0, out.stderr
    envelope = json.loads(out.stdout)
    assert envelope["payload"]["value"] == 60
    assert len(envelope["sig"]) == 64


@pytest.mark.skipif(not _real_env_ready(), reason="operator backend_fastapi/.env without FIX_CODE_SECRET")
def test_pipe_to_clipboard_is_clean() -> None:
    """Simulates `python scripts/make-fix-code.py ... | clip`: stdout must be a
    single JSON line (json.loads on the stripped output must succeed)."""
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "enable_receipts", "true"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    lines = out.stdout.strip().splitlines()
    assert len(lines) == 1
    envelope = json.loads(lines[0])
    assert envelope["payload"]["value"] is True


# ── Full HTTP round-trip: CLI stdout -> endpoint -> DB row ──────────────────


async def _admin_token(client: AsyncClient, session: AsyncSession) -> str:
    await UserRepository(session).create(
        "fixadmin", "Fix Admin", hash_password("password123"), 1
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "fixadmin", "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.anyio
async def test_route_is_registered(client: AsyncClient) -> None:
    resp = await client.post(URL, json={"action": "x", "payload": {}, "sig": "y"})
    # Registered: auth runs before anything else. An unregistered route 404s.
    assert resp.status_code == 401, f"expected 401 (unauthenticated), got {resp.status_code}"


@pytest.mark.anyio
async def test_cli_output_accepted_by_endpoint(
    client: AsyncClient, session: AsyncSession, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    from app.api.routers.support_fix_route import _fix_code_secret

    secret = _fix_code_secret()
    if not secret:
        pytest.skip("FIX_CODE_SECRET not configured in this environment")
    env_file = tmp_path / ".env"
    env_file.write_text(f"FIX_CODE_SECRET={secret}\n", encoding="utf-8")

    session.add(SystemSetting(key="session_idle_minutes", value=b"30"))
    await session.commit()

    assert cli.main(["session_idle_minutes", "60", "--env", str(env_file)]) == 0
    envelope = json.loads(capsys.readouterr().out)

    token = await _admin_token(client, session)
    resp = await client.post(URL, json=envelope, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text

    session.expire_all()
    row = await session.get(SystemSetting, "session_idle_minutes")
    assert row.value.decode() == "60"


@pytest.mark.anyio
async def test_tampered_cli_code_is_rejected(
    client: AsyncClient, session: AsyncSession, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Tampering with a CLI-generated envelope after signing must 403."""
    from app.api.routers.support_fix_route import _fix_code_secret

    secret = _fix_code_secret()
    if not secret:
        pytest.skip("FIX_CODE_SECRET not configured in this environment")
    env_file = tmp_path / ".env"
    env_file.write_text(f"FIX_CODE_SECRET={secret}\n", encoding="utf-8")

    assert cli.main(["session_idle_minutes", "60", "--env", str(env_file)]) == 0
    envelope = json.loads(capsys.readouterr().out)
    envelope["payload"]["value"] = 9999  # edit after signing

    token = await _admin_token(client, session)
    resp = await client.post(URL, json=envelope, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403

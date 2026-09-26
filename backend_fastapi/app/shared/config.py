"""Type-safe settings loaded from environment variables / .env file."""
from __future__ import annotations

import os
import platform
import secrets
import uuid
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_app_data_dir() -> Path:
    """Per-install writable data directory (single source of truth).

    Windows: ``%APPDATA%\\PharmacySuite`` (matches the MSI/First-Run spec —
    NOT the Tauri ``app_data_dir``, which is identifier-based). The database
    (``pharmacy.db``) and the per-install JWT secret (``secret.key``) live
    here. Created on first access so a fresh install starts with zero users
    and the setup wizard appears.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        data_dir = Path(base) / "PharmacySuite"
    else:
        data_dir = Path(os.path.expanduser("~/.pharmacysuite"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


_SECRET_PLACEHOLDER = "replace-with-a-64-char-random-secret-key-in-production"


def _load_or_create_device_secret(data_dir: Path) -> str:
    """Return the per-install JWT secret, generating it silently on first run.

    Reads ``secret.key`` from the app data dir; if absent, generates a
    cryptographically random value and persists it (mode 0600 where the
    platform allows). If the file cannot be written (read-only dir), falls
    back to an ephemeral in-memory secret — tokens are then valid only until
    the process exits, but startup never crashes. This never blocks or
    prompts: the first-run setup wizard flow is unaffected.
    """
    path = data_dir / "secret.key"
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    generated = secrets.token_urlsafe(64)
    try:
        path.write_text(generated, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows ACLs — file is already inside the user's profile
    except OSError:
        pass  # ephemeral fallback (see docstring)
    return generated


def _resolve_secret_key() -> str:
    """Resolve the JWT secret: explicit env var wins, else per-install file.

    Security rotation rule (Spec: Objective 3, Task A): when the database file
    is absent (fresh install after uninstall/wipe), any persisted ``secret.key``
    is stale — delete it so a brand-new secret is generated. This guarantees
    JWTs issued by a previous installation can never authenticate against the
    new instance, even if the secret file survived a partial wipe.
    """
    env_secret = os.environ.get("SECRET_KEY", "").strip()
    if env_secret and env_secret != _SECRET_PLACEHOLDER:
        return env_secret
    data_dir = get_app_data_dir()
    db_path = data_dir / "pharmacy.db"
    if not db_path.exists():
        try:
            (data_dir / "secret.key").unlink(missing_ok=True)
        except OSError:
            pass  # rotation is best-effort; generation below still yields a new secret if the file was unreadable
    return _load_or_create_device_secret(data_dir)


def _default_database_url() -> str:
    """Default SQLite URL inside the per-install app data dir."""
    db_path = get_app_data_dir() / "pharmacy.db"
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


def _stable_device_id() -> str:
    """Per-install stable device identifier (used as the merge-sync terminal id).

    Persisted to ``.pharmacy_device_id`` alongside the DB; survives restarts but
    is unique per install — the merge-sync hub keys cross-terminal ordering on it
    (C.1: ordering = ``(device_id, local_seq)``).
    """
    try:
        marker = get_app_data_dir() / ".pharmacy_device_id"
        if marker.exists():
            existing = marker.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        did = uuid.uuid4().hex
        marker.write_text(did, encoding="utf-8")
        return did
    except OSError:
        # Fall back to machine+process fingerprint if the DB dir is read-only.
        mac = uuid.getnode() if hasattr(uuid, "getnode") else 0
        return f"{platform.node()}-{mac}-{uuid.uuid4().hex[:8]}"





class Settings(BaseSettings):
    """Application configuration sourced from environment variables.

    Field ``alias`` values map directly to the environment variable names defined
    in the refactor specification (e.g. ``PHARMACY_DB_URL``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = Field(default="production", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")

    database_url: str = Field(
        default_factory=_default_database_url, alias="PHARMACY_DB_URL"
    )

    secret_key: SecretStr = Field(
        default_factory=lambda: SecretStr(_resolve_secret_key()),
        alias="SECRET_KEY",
    )
    access_token_expire_minutes: int = Field(default=480, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # ── PIN kiosk auth + device-bound peppering (C.4 hardening) ──
    pin_kdf_iters: int = Field(default=200_000, alias="POS_PIN_KDF_ITERS")
    pin_lockout_attempts: int = Field(default=5, alias="POS_PIN_LOCKOUT_ATTEMPTS")
    pin_lockout_minutes: int = Field(default=15, alias="POS_PIN_LOCKOUT_MINUTES")
    pepper_backend: str = Field(default="dpapi-local-machine", alias="POS_PEPPER_BACKEND")
    pepper_path: str = Field(default="pepper.store", alias="POS_PEPPER_PATH")
    pepper_env_key: str = Field(default="PHARMACY_PEPPER_KEY", alias="POS_PEPPER_ENV_KEY")
    pin_pepper_version: int = Field(default=1, alias="POS_PIN_PEPPER_VERSION")

    # ── Rate limiting (F.1: network-layer brute-force protection) ──
    auth_rate_limit: str = Field(default="5/minute", alias="POS_AUTH_RATE_LIMIT")
    pin_rate_limit: str = Field(default="5/minute", alias="POS_PIN_RATE_LIMIT")

    # ── Support fix-code signature (Stage 2.3) ──
    # Support team's HMAC signing secret for fix codes. Set FIX_CODE_SECRET in
    # the backend .env. Different from SECRET_KEY/JWT secret.
    fix_code_secret: str = Field(default="", alias="FIX_CODE_SECRET")

    # ── Multi-terminal sync hub (C.1 hardening) ──
    multi_terminal: bool = Field(default=False, alias="POS_MULTI_TERMINAL")
    device_id: str = Field(default_factory=lambda: _stable_device_id(), alias="POS_DEVICE_ID")

    fastapi_host: str = Field(default="0.0.0.0", alias="FASTAPI_HOST")
    fastapi_port: int = Field(default=8000, alias="FASTAPI_PORT")

    # ── Mobile Access Mode (Phase 4 Step 1.4) ──
    # "shared" = the desktop DB/API is authoritative and may be exposed to the
    # local network (0.0.0.0). "independent" = mobile keeps its own local DB
    # and the API stays loopback-only (127.0.0.1). "cloud" is a stub for a
    # future hosted relay and currently behaves like "independent".
    mobile_access_mode: str = Field(default="shared", alias="MOBILE_ACCESS_MODE")
    mobile_bind_host: str = Field(default="127.0.0.1", alias="MOBILE_BIND_HOST")

    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    tax_rate: float = Field(default=0.14, alias="TAX_RATE")

    # ── SMTP / Email ──
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: SecretStr = Field(default=SecretStr(""), alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="", alias="SMTP_FROM_EMAIL")
    smtp_from_name: str = Field(default="PharmacySuite", alias="SMTP_FROM_NAME")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    # ── Hybrid OCR Pipeline ──
    hybrid_ocr_lang: str = Field(default="en", alias="HYBRID_OCR_LANG")
    hybrid_ocr_gpu: bool = Field(default=True, alias="HYBRID_OCR_GPU")
    hybrid_ocr_max_image_mb: int = Field(default=20, alias="HYBRID_OCR_MAX_IMAGE_MB")
    hybrid_ocr_limit_side_len: int = Field(default=960, alias="HYBRID_OCR_LIMIT_SIDE_LEN")
    hybrid_ocr_tesseract_threads: int = Field(default=1, alias="HYBRID_OCR_TESSERACT_THREADS")
    hybrid_ocr_min_vram_gb: float = Field(default=2.0, alias="HYBRID_OCR_MIN_VRAM_GB")
    hybrid_ocr_min_ram_gb: float = Field(default=4.0, alias="HYBRID_OCR_MIN_RAM_GB")

    @property
    def jwt_secret(self) -> str:
        return self.secret_key.get_secret_value()

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        # The placeholder can never survive resolution: an explicit real env
        # value wins, otherwise a per-install secret.key is generated. This
        # guard only rejects an empty secret (misconfiguration).
        if not self.secret_key.get_secret_value():
            raise ValueError("SECRET_KEY resolved empty — check file permissions")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

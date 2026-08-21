"""Type-safe settings loaded from environment variables / .env file."""
from __future__ import annotations

import os
import platform
import uuid
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _stable_device_id() -> str:
    """Per-install stable device identifier (used as the merge-sync terminal id).

    Persisted to ``.pharmacy_device_id`` alongside the DB; survives restarts but
    is unique per install — the merge-sync hub keys cross-terminal ordering on it
    (C.1: ordering = ``(device_id, local_seq)``).
    """
    try:
        marker = Path("pharmacy.db").resolve().parent / ".pharmacy_device_id"
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

    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    database_url: str = Field(
        default="sqlite+aiosqlite:///./pharmacy.db", alias="PHARMACY_DB_URL"
    )

    secret_key: SecretStr = Field(
        default=SecretStr("replace-with-a-64-char-random-secret-key-in-production"),
        alias="SECRET_KEY",
    )
    access_token_expire_minutes: int = Field(default=480, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    license_gate_url: str = Field(default="http://localhost:5000", alias="LICENSE_GATE_URL")

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

    # ── Multi-terminal sync hub (C.1 hardening) ──
    multi_terminal: bool = Field(default=False, alias="POS_MULTI_TERMINAL")
    device_id: str = Field(default_factory=lambda: _stable_device_id(), alias="POS_DEVICE_ID")

    fastapi_host: str = Field(default="0.0.0.0", alias="FASTAPI_HOST")
    fastapi_port: int = Field(default=8000, alias="FASTAPI_PORT")

    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    tax_rate: float = Field(default=0.14, alias="TAX_RATE")

    # ── Creem Merchant-of-Record (MoR) ──
    creem_api_key: SecretStr = Field(
        default=SecretStr(""), alias="CREEM_API_KEY"
    )
    creem_webhook_secret: SecretStr = Field(
        default=SecretStr(""), alias="CREEM_WEBHOOK_SECRET"
    )
    creem_product_id: str = Field(default="", alias="CREEM_PRODUCT_ID")
    # Hours the app continues working without a server re-check (offline grace)
    license_offline_grace_hours: int = Field(default=72, alias="LICENSE_OFFLINE_GRACE_HOURS")

    @property
    def jwt_secret(self) -> str:
        return self.secret_key.get_secret_value()

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            placeholder = "replace-with-a-64-char-random-secret-key-in-production"
            if self.secret_key.get_secret_value() == placeholder:
                raise ValueError(
                    "SECRET_KEY must be set to a strong random value when APP_ENV=production"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

"""Staged config.py (v1) — OTA delta payload example.

Part of deployment/updates/; referenced by deployment/ota_manifest.json for the C.2
granular OTA applier. Not imported at runtime — it is a staged payload.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "production"


settings = Settings()

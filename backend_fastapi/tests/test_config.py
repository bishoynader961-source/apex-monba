from __future__ import annotations

from app.main import app
from app.shared.config import settings


def test_settings_defaults() -> None:
    assert settings.tax_rate == 0.14
    assert settings.access_token_expire_minutes == 480
    assert settings.frontend_url.startswith("http")


def test_app_metadata() -> None:
    assert app.title == "Pharmacy Suite API"

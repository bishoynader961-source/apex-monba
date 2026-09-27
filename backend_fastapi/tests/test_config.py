from __future__ import annotations

from app.main import app
from app.shared.config import settings


def test_settings_defaults() -> None:
    assert settings.tax_rate == 0.14
    # Sprint 1B: blueprint mandates ≤ 15 min access tokens. The setting itself
    # is env-overridable, so assert the hard code-level cap (env-proof).
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    from app.shared.security import create_access_token

    claims = pyjwt.decode(
        create_access_token("1", "admin", 1, ["*"]), settings.jwt_secret, algorithms=["HS256"]
    )
    expiry = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    assert expiry <= datetime.now(timezone.utc) + timedelta(minutes=15, seconds=30)
    assert settings.frontend_url.startswith("http")


def test_app_metadata() -> None:
    assert app.title == "Pharmacy Suite API"

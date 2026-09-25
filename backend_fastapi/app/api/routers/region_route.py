"""Region detection route.

GET /api/v1/region/detect — detect region from request IP or header.
GET /api/v1/region/{code} — get region configuration.
GET /api/v1/regions — list all available regions.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import get_current_user
from app.shared.schemas import CurrentUser
from app.services.region_service import (
    REGIONS,
    detect_region_from_ip,
    get_region_config,
    get_region_from_header,
)

router = APIRouter(prefix="/api/v1/region", tags=["region"])


@router.get("/detect")
async def detect_region(
    request: Request,
    x_vercel_ip_country: Optional[str] = Header(default=None),
    _auth: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Auto-detect region from IP or Vercel header."""
    client_ip = request.client.host if request.client else None
    if x_vercel_ip_country:
        code = get_region_from_header(x_vercel_ip_country)
    elif client_ip:
        code = detect_region_from_ip(client_ip)
    else:
        code = "US"

    config = get_region_config(code)
    return {
        "code": config.code,
        "name": config.name,
        "currency": config.currency,
        "currency_symbol": config.currency_symbol,
        "date_format": config.date_format,
        "tax_label": config.tax_label,
        "default_tax_rate": config.default_tax_rate,
        "supports_insurance": config.supports_insurance,
        "supports_workers_comp": config.supports_workers_comp,
        "rx_requires_ndc": config.rx_requires_ndc,
        "language": config.language,
    }


@router.get("/regions")
async def list_regions(
    _auth: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all supported regions."""
    return [
        {
            "code": r.code,
            "name": r.name,
            "currency": r.currency,
            "currency_symbol": r.currency_symbol,
        }
        for r in REGIONS.values()
    ]


@router.get("/{code}")
async def get_region(
    code: str,
    _auth: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Get configuration for a specific region."""
    config = get_region_config(code)
    return {
        "code": config.code,
        "name": config.name,
        "currency": config.currency,
        "currency_symbol": config.currency_symbol,
        "date_format": config.date_format,
        "tax_label": config.tax_label,
        "default_tax_rate": config.default_tax_rate,
        "supports_insurance": config.supports_insurance,
        "supports_workers_comp": config.supports_workers_comp,
        "rx_requires_ndc": config.rx_requires_ndc,
        "language": config.language,
    }

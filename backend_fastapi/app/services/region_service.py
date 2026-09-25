"""Region detection and configuration service.

Provides IP-based region detection and region-specific formatting rules
for currency, date, tax, and compliance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class RegionConfig:
    code: str
    name: str
    currency: str
    currency_symbol: str
    date_format: str
    tax_label: str
    default_tax_rate: float
    supports_insurance: bool
    supports_workers_comp: bool
    rx_requires_ndc: bool
    language: str


REGIONS: dict[str, RegionConfig] = {
    "US": RegionConfig(
        code="US", name="United States",
        currency="USD", currency_symbol="$",
        date_format="MM/DD/YYYY",
        tax_label="Sales Tax", default_tax_rate=0.0,
        supports_insurance=True, supports_workers_comp=True,
        rx_requires_ndc=True, language="en",
    ),
    "GB": RegionConfig(
        code="GB", name="United Kingdom",
        currency="GBP", currency_symbol="\u00a3",
        date_format="DD/MM/YYYY",
        tax_label="VAT", default_tax_rate=0.20,
        supports_insurance=False, supports_workers_comp=False,
        rx_requires_ndc=False, language="en",
    ),
    "DE": RegionConfig(
        code="DE", name="Germany",
        currency="EUR", currency_symbol="\u20ac",
        date_format="DD.MM.YYYY",
        tax_label="MwSt", default_tax_rate=0.19,
        supports_insurance=False, supports_workers_comp=False,
        rx_requires_ndc=False, language="de",
    ),
    "EG": RegionConfig(
        code="EG", name="Egypt",
        currency="EGP", currency_symbol="E£",
        date_format="DD/MM/YYYY",
        tax_label="VAT", default_tax_rate=0.14,
        supports_insurance=False, supports_workers_comp=False,
        rx_requires_ndc=False, language="en",
    ),
}

DEFAULT_REGION = "US"


def detect_region_from_ip(ip_address: str) -> str:
    """Detect region from IP address.

    Uses a simple GeoIP lookup via ip-api.com (free tier, no key required).
    Falls back to DEFAULT_REGION on any failure.
    """
    if not ip_address or ip_address in ("127.0.0.1", "::1", "localhost"):
        return DEFAULT_REGION

    try:
        import urllib.request
        import json

        url = f"http://ip-api.com/json/{ip_address}?fields=countryCode"
        req = urllib.request.Request(url, headers={"User-Agent": "PharmacySuite/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            code = data.get("countryCode", "").upper()
            if code in REGIONS:
                return code
    except Exception as e:
        log.debug("IP geolocation failed for %s: %s", ip_address, e)

    return DEFAULT_REGION


def get_region_config(code: str) -> RegionConfig:
    return REGIONS.get(code.upper(), REGIONS[DEFAULT_REGION])


def get_region_from_header(header_value: Optional[str]) -> str:
    """Map a country code header (e.g. x-vercel-ip-country) to a region code."""
    if not header_value:
        return DEFAULT_REGION
    code = header_value.upper()
    return code if code in REGIONS else DEFAULT_REGION

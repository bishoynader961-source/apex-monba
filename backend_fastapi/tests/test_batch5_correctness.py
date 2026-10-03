"""Batch 5 tests — correctness and polish findings L1, L6, L7.

L1  Decimal (ROUND_HALF_UP cents) pricing in bulk price adjust, Excel import,
    and vendor shipments — replaces float math that stored binary-float
    artifacts into money columns.
L6  Production CSP hardening in src-tauri/tauri.conf.json: no cdn.paddle.com
    in script-src (checkout is server-side webhooks), no blanket https: in
    img-src. ``style-src 'unsafe-inline'`` is intentionally retained — the two
    print-preview <style> blocks (app/print-label, app/dashboard/
    bulk-label-print) need it; removing it would break label printing.
L7  Single expiry-date semantic: ``today_iso()`` is the one helper that defines
    "today" for all expiration comparisons (local calendar date, ISO string).
"""
from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TAURI_CONF = REPO_ROOT / "src-tauri" / "tauri.conf.json"


# ── L1: Decimal price arithmetic ─────────────────────────────────────────────


class _FakeProduct:
    def __init__(self, price: float) -> None:
        self.price = price


class _FakeSession:
    """session.get(Product, id) double that records final price assignments."""

    def __init__(self, prices: dict[int, float]) -> None:
        self._prices = prices
        self.saved: dict[int, float] = {}

    async def get(self, _model: object, med_id: int) -> _FakeProduct:
        return _FakeProduct(self._prices.get(med_id, 0.0))

    async def commit(self) -> None:
        # _FakeProduct instances are mutated in place by the service; the
        # service then commits. Snapshot the mutated values here.
        return None


@pytest.mark.asyncio
async def test_batch_adjust_price_rounds_half_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """+15% on 10.10 -> 11.62 exactly; 0% on 2.675 -> 2.68 (HALF_UP).

    float math produced 11.615000000000002 (stored raw) and banker's-rounding
    surprises; the Decimal path is deterministic HALF_UP at cents.
    """
    import app.core.models as models
    from app.services.inventory_service import InventoryService

    products: dict[int, _FakeProduct] = {
        1: _FakeProduct(10.10),
        2: _FakeProduct(2.675),
    }

    class _Session:
        async def get(self, _model: object, med_id: int) -> _FakeProduct:
            return products[med_id]

        async def commit(self) -> None:
            pass

    monkeypatch.setattr(models, "Product", object(), raising=False)
    svc = InventoryService(_Session())  # type: ignore[arg-type]
    result = await svc.batch_adjust_price([1], 15.0)

    assert result["updated"] == 1
    assert products[1].price == 11.62  # not 11.615000000000002


@pytest.mark.asyncio
async def test_batch_adjust_price_zero_pct_requantizes_half_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A no-op adjustment still re-quantizes: 2.675 -> 2.68 (float round gives 2.67)."""
    import app.core.models as models
    from app.services.inventory_service import InventoryService

    products: dict[int, _FakeProduct] = {9: _FakeProduct(2.675)}

    class _Session:
        async def get(self, _model: object, med_id: int) -> _FakeProduct:
            return products[med_id]

        async def commit(self) -> None:
            pass

    monkeypatch.setattr(models, "Product", object(), raising=False)
    svc = InventoryService(_Session())  # type: ignore[arg-type]
    result = await svc.batch_adjust_price([9], 0.0)

    assert result["updated"] == 1
    assert products[9].price == 2.68  # float(2.675) round() would give 2.67


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4.10", "4.10"),
        ("4.10000000001", "4.10"),
        (4.0999999999999996, "4.10"),
        ("1.005", "1.01"),  # HALF_UP, not banker's rounding
        ("0", "0.00"),
        (7, "7.00"),
    ],
)
def test_excel_parse_price_exact_cents(raw: object, expected: str) -> None:
    from app.api.routers.excel_route import _parse_price

    assert _parse_price(raw) == Decimal(expected)


def test_excel_parse_price_rejects_garbage() -> None:
    from decimal import InvalidOperation

    from app.api.routers.excel_route import _parse_price

    with pytest.raises((InvalidOperation, ValueError, TypeError)):
        _parse_price("not-a-price")


def test_vendor_receive_binds_quantized_cost_everywhere() -> None:
    """products.price, purchase_history.unit_cost and the total all derive from
    the same intake-quantized Decimal (audit L1 regression pin)."""
    src = (REPO_ROOT / "backend_fastapi" / "app" / "api" / "routers" / "vendors_route.py").read_text(
        encoding="utf-8"
    )
    assert "unit_cost_dec" in src
    assert 'float(payload.unit_cost)' not in src, (
        "raw payload float must not reach products.price or purchase_history"
    )
    assert '"price": float(unit_cost_dec)' in src
    assert '"unit_cost": float(unit_cost_dec)' in src


# ── L6: CSP hardening ────────────────────────────────────────────────────────


def _csp() -> str:
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    return conf["app"]["security"]["csp"]


def test_csp_drops_paddle_and_wildcard_https_images() -> None:
    csp = _csp()
    assert "cdn.paddle.com" not in csp, "no client-side Paddle checkout exists"
    assert "script-src 'self' 'wasm-unsafe-eval' http://127.0.0.1:3000 http://localhost:3000" in csp
    assert "img-src 'self' data: http://127.0.0.1:3000 http://localhost:3000" in csp, (
        "blanket https: img-src removed; no remote <img> exists in the app"
    )


def test_csp_keeps_unsafe_inline_style_for_print_previews() -> None:
    csp = _csp()
    assert "style-src 'self' 'unsafe-inline'" in csp, (
        "print-label and bulk-label-print use JSX <style> blocks for printing"
    )


# ── L7: single expiry-date semantic ─────────────────────────────────────────


def test_today_iso_is_local_date_isoformat() -> None:
    from datetime import date

    from app.services.inventory_service import today_iso

    assert today_iso() == date.today().isoformat()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", today_iso())


def test_expiry_comparisons_use_today_iso_helper() -> None:
    """All expiry predicates in inventory_service route through today_iso()."""
    src = (REPO_ROOT / "backend_fastapi" / "app" / "services" / "inventory_service.py").read_text(
        encoding="utf-8"
    )
    assert src.count("today_iso()") >= 5, (
        "fifo_deduct / get_expired_lot / expiring_soon / stock_levels should "
        "all take 'today' from the one helper (audit L7)"
    )
    # date.today() may appear only in cutoff arithmetic (date.today() + timedelta)
    # and inside the helper itself; direct uses elsewhere would bypass it.
    body = src.split("def today_iso", 1)[1]
    body = body.split("return date.today().isoformat()", 1)[1]
    assert body.count("date.today().isoformat()") == 0, (
        "only cutoff arithmetic (date.today() + timedelta) may call date.today()"
    )

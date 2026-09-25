"""Mobile-specific routes: offline-ack + ESC/POS label rendering (§2.2, §2.3)."""
from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import SyncOutbox
from app.shared.schemas import (
    CurrentUser,
    MobileOfflineAckRequest,
    MobileOfflineAckResponse,
    MobileLabelRenderRequest,
    MobileLabelRenderResponse,
)

router = APIRouter(prefix="/api/v1", tags=["mobile"])


@router.post("/mobile/offline-ack", response_model=MobileOfflineAckResponse, status_code=status.HTTP_200_OK)
async def offline_ack(
    payload: MobileOfflineAckRequest,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> MobileOfflineAckResponse:
    """Acknowledge server-side persistence of synced events (§2.2).

    The mobile client calls this after confirming a ``POST /sync/push`` batch was
    accepted. The hub marks the corresponding ``sync_outbox`` rows as ``acked``
    so they can be garbage-collected on the next cycle.
    """
    if not payload.ack_client_txn_ids:
        return MobileOfflineAckResponse(purged_count=0)

    if len(payload.ack_client_txn_ids) > 500:
        raise ValueError("Too many ack IDs in a single request (max 500)")

    result = await session.execute(
        select(SyncOutbox)
        .where(
            SyncOutbox.device_id == payload.device_id,
            SyncOutbox.client_txn_id.in_(payload.ack_client_txn_ids),
        )
    )
    rows = result.scalars().all()
    purged = 0
    for row in rows:
        if row.status in ("pending", "merged"):
            row.status = "acked"
            session.add(row)
            purged += 1

    if purged > 0:
        await session.commit()

    return MobileOfflineAckResponse(purged_count=purged)


@router.post("/labels/render-mobile", response_model=MobileLabelRenderResponse, status_code=status.HTTP_200_OK)
async def render_mobile_label(
    payload: MobileLabelRenderRequest,
    user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> MobileLabelRenderResponse:
    """Render a label template (or product default) into ESC/POS base64 bytes (§2.3).

    The mobile client sends the desired template/product context + the barcode value.
    The server composes a minimal ESC/POS command stream (text + Code128 barcode)
    suitable for delivery over Bluetooth to a thermal label printer.
    """
    from app.services.label_template_service import LabelTemplateService

    svc = LabelTemplateService(session)
    elements: list[dict[str, Any]] = []

    if payload.template_id is not None:
        try:
            tpl = await svc.get_template(payload.template_id)
            elements = tpl.get("elements", [])
        except ValueError:
            elements = []

    if payload.product_id is not None:
        from app.core.repositories import ProductRepository
        product_label = await ProductRepository(session).get(payload.product_id)
        if product_label and not elements:
            elements = [
                {"type": "text", "text": product_label.name, "font": 0, "x": 0, "y": 0},
                {"type": "text", "text": str(product_label.price), "font": 0, "x": 0, "y": 24},
                {"type": "barcode", "data": payload.barcode_value, "symbology": "code128", "x": 0, "y": 48},
            ]

    if not elements:
        elements = [
            {"type": "text", "text": payload.barcode_value, "font": 0, "x": 0, "y": 0},
            {"type": "barcode", "data": payload.barcode_value, "symbology": "code128", "x": 0, "y": 16},
        ]

    escp = _render_elements_to_escp(elements, payload.print_density)
    b64 = base64.b64encode(escp).decode("ascii")

    return MobileLabelRenderResponse(
        format="ESCPOS_BASE64",
        payload=b64,
        byte_length=len(escp),
    )


def _render_elements_to_escp(elements: list[dict[str, Any]], density: str) -> bytes:
    """Compose a minimal ESC/POS byte stream from label template elements.

    Supports text and code128 barcode elements. Falls back to the raw barcode
    text if the printer doesn't support GS k (Code128).
    """
    ESC = b"\x1b"
    GS = b"\x1d"
    LF = b"\n"

    lines: list[bytes] = []
    lines.append(ESC + b"@")  # Initialize printer

    density_val = _parse_density(density)
    n = 0
    x = 0
    y = 0

    for elem in sorted(elements, key=lambda e: (e.get("y", 0), e.get("x", 0))):
        elem_type = elem.get("type", "")
        if elem_type == "text":
            text = str(elem.get("text", ""))
            font = int(elem.get("font", 0))
            lines.append(ESC + b"!" + bytes([font & 0x01]))  # Font selection
            lines.append(text.encode("utf-8", errors="replace") + LF)
            y += 24
        elif elem_type == "barcode":
            data = str(elem.get("data", ""))
            symbology = str(elem.get("symbology", "code128"))
            lines.append(_barcode_escp(data, symbology))
            y += 64
        n += 1

    lines.append(GS + b"V" + b"\x00")  # Feed and cut paper
    return b"".join(lines)


def _parse_density(density: str) -> int:
    """Parse '8dot/mm' → 8 (dots per mm)."""
    try:
        return int(float(density.split("dot")[0]))
    except (ValueError, IndexError):
        return 8


def _barcode_escp(data: str, symbology: str) -> bytes:
    """Render a barcode element into ESC/POS GS k command bytes."""
    GS = b"\x1d"
    if symbology == "code128":
        return GS + b"k" + b"\x4f\x01" + bytes([len(data)]) + data.encode("ascii") + b"\x00"
    if symbology == "upc_a":
        return GS + b"k" + b"\x41\x01" + bytes([len(data)]) + data.encode("ascii") + b"\x00"
    if symbology == "ean13":
        return GS + b"k" + b"\x43\x01" + bytes([len(data)]) + data.encode("ascii") + b"\x00"
    return data.encode("utf-8", errors="replace") + b"\n"

"""Invoice parsing routes: upload text/file and get structured data.

Endpoints:
  POST /text          — Parse raw invoice text via regex
  POST /file          — Parse uploaded .txt/.csv file via regex
  POST /hybrid        — Dual-engine OCR (PaddleOCR + Tesseract) with hardware gating
  GET  /hardware-status — Pre-flight hardware capability check
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.hardware_evaluator import HardwareEvaluator, HardwareProfile
from app.services.hybrid_ocr_engine import HybridOcrEngine, OcrHardwareError
from app.services.smart_parser import parse_invoice
from app.shared.config import settings
from app.shared.schemas import CurrentUser

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/invoice-parse", tags=["invoice-parse"])


# ── Existing: Text / File parsing ────────────────────────────────────────


class ParseTextRequest(BaseModel):
    text: str


class ParsedItem(BaseModel):
    product_name: str
    active_ingredient: str
    dosage_concentration: str
    quantity_received: int
    batch_number: str
    expiration_date: str


class ParseResponse(BaseModel):
    items: list[ParsedItem]
    count: int


@router.post("/text", response_model=ParseResponse, status_code=status.HTTP_200_OK)
async def parse_invoice_text(
    payload: ParseTextRequest,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
) -> ParseResponse:
    items = parse_invoice(payload.text)
    return ParseResponse(items=[ParsedItem(**i) for i in items], count=len(items))


@router.post("/file", response_model=ParseResponse, status_code=status.HTTP_200_OK)
async def parse_invoice_file(
    file: UploadFile = File(...),
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
) -> ParseResponse:
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    items = parse_invoice(text)
    return ParseResponse(items=[ParsedItem(**i) for i in items], count=len(items))


# ── New: Hybrid OCR pipeline ────────────────────────────────────────────


class HybridLineItem(BaseModel):
    description: str
    quantity: int
    unit_price: float


class HardwareStatus(BaseModel):
    gpu_available: bool
    gpu_name: str | None
    gpu_vram_gb: float
    ram_total_gb: float
    ram_available_gb: float
    cpu_threads: int
    cpu_physical_cores: int
    tier: str
    recommended_mode: str
    warnings: list[str]


class HybridParseResponse(BaseModel):
    invoice_number: str | None
    total_amount: float | None
    line_items: list[HybridLineItem]
    metadata: dict
    confidence: dict
    raw_text: str
    engines_used: list[str]
    processing_time_ms: float
    hardware_status: HardwareStatus
    warnings: list[str]


@router.get("/hardware-status", response_model=HardwareStatus)
async def get_hardware_status(
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
) -> HardwareStatus:
    """Pre-flight hardware check: returns GPU/RAM/CPU capabilities.

    Call this before uploading an image to let the frontend display
    the recommended OCR mode and any resource warnings.
    """
    profile = HardwareEvaluator.evaluate()
    return HardwareStatus(**profile.to_dict())


@router.post("/hybrid", response_model=HybridParseResponse, status_code=status.HTTP_200_OK)
async def parse_invoice_hybrid(
    file: UploadFile = File(...),
    mode: Literal["auto", "hybrid", "tesseract_only"] = Query(
        "auto",
        description=(
            "OCR routing mode. 'auto' uses hardware evaluation to pick the "
            "best mode. 'hybrid' forces both engines. 'tesseract_only' skips "
            "PaddleOCR for fast CPU-only processing."
        ),
    ),
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
) -> HybridParseResponse:
    """Dual-engine OCR extraction with hardware-aware dynamic routing.

    Accepts an invoice image, evaluates host hardware, and routes to the
    appropriate OCR engine(s). Returns structured invoice data alongside
    hardware status and resource warnings.
    """
    # ── Validate file type ──
    if not file.content_type or not (
        file.content_type.startswith("image/")
        or file.content_type == "application/pdf"
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Must be an image (PNG, JPG, TIFF, etc.).",
        )

    # ── Read and check size ──
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    max_bytes = settings.hybrid_ocr_max_image_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {settings.hybrid_ocr_max_image_mb} MB limit.",
        )

    # ── Run hybrid extraction ──
    try:
        result, profile = HybridOcrEngine.extract_hybrid(content, mode=mode)
    except OcrHardwareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        log.error("Hybrid OCR failed: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"OCR processing failed: {e}",
        )

    # ── Merge warnings from hardware evaluation + engine ──
    all_warnings = list(profile.warnings)

    return HybridParseResponse(
        invoice_number=result.invoice_number,
        total_amount=result.total_amount,
        line_items=[HybridLineItem(**item) for item in result.line_items],
        metadata=result.metadata,
        confidence=result.confidence,
        raw_text=result.raw_text,
        engines_used=result.engines_used,
        processing_time_ms=result.processing_time_ms,
        hardware_status=HardwareStatus(**profile.to_dict()),
        warnings=all_warnings,
    )


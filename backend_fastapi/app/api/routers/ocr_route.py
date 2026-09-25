"""OCR route: 4-tier cascade with confidence-based escalation.

POST /api/v1/ocr — accepts an image, returns extracted text with per-tier details.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from app.api.deps import get_current_user
from app.shared.schemas import CurrentUser
from app.services.ocr_cascade import run_cascade

import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])


@router.post("")
async def process_ocr(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be an image.")

    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file.")

        result = run_cascade(contents, cascade_id=current_user.username)
        return result.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        log.error("OCR cascade failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")

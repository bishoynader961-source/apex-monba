import io
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from PIL import Image, ImageOps

from app.api.deps import get_current_user
from app.shared.schemas import CurrentUser
import pytesseract
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])

@router.post("")
async def process_ocr(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be an image.")
    
    try:
        contents = await file.read()
        image: Image.Image = Image.open(io.BytesIO(contents))
        
        # Ensure it's in RGB or L
        if image.mode not in ("L", "RGB"):
            image = image.convert("RGB")
            
        # Basic preprocessing for better OCR
        gray = ImageOps.grayscale(image)
        processed = gray.point(lambda p: 0 if p < 128 else 255, mode="1")
        
        # Pytesseract extraction
        data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
        words = data.get("text", [])
        confs = data.get("conf", [])
        
        valid = [(w, c) for w, c in zip(words, confs) if w and w.strip()]
        
        if not valid:
             return {
                "text": "",
                "confidence": 0.0,
                "metadata": {
                    "word_count": 0
                }
            }

        text = " ".join(w for w, _ in valid)
        mean_conf = sum(c for _, c in valid) / len(valid) / 100.0 if valid else 0.0
        
        # Apply length penalty for very short results
        if len(text.strip()) < 5:
            mean_conf *= 0.7

        return {
            "text": text.strip(),
            "confidence": mean_conf,
            "metadata": {
                "word_count": len(valid)
            }
        }
    except Exception as e:
        log.error("OCR processing failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")

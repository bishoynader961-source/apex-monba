"""Hybrid OCR engine: PaddleOCR (GPU) + Tesseract (CPU) with dynamic routing.

Executes a dual-engine OCR pipeline with hardware-aware fallbacks:
- Capable GPU: PaddleOCR for tabular layout + Tesseract for flat metadata
- Constrained CPU: Tesseract-only mode with resource warnings
- Incompatible: Rejected with 503

Thread/memory guardrails:
- OMP_THREAD_LIMIT=1 for Tesseract (prevents CPU thrashing)
- Image downscale to limit_side_len=960 (prevents OOM on thin clients)
- PaddleOCR rec_batch_num=6 + max_text_length=256 (caps VRAM usage)
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from PIL import Image, ImageOps

from app.services.hardware_evaluator import HardwareEvaluator, HardwareProfile
from app.shared.config import settings

log = logging.getLogger(__name__)

_paddle_instance = None
_paddle_lock = threading.Lock()


@dataclass
class HybridOcrResult:
    """Structured output from the hybrid OCR pipeline."""

    invoice_number: str | None = None
    total_amount: float | None = None
    line_items: list[dict] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    raw_text: str = ""
    engines_used: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0


class HybridOcrEngine:
    """Dual-engine OCR with hardware-aware dynamic routing."""

    @classmethod
    def extract_hybrid(
        cls,
        image_bytes: bytes,
        mode: Literal["auto", "hybrid", "tesseract_only"] = "auto",
    ) -> tuple[HybridOcrResult, HardwareProfile]:
        """Run hybrid OCR on an image.

        Returns (result, hardware_profile).  The caller can inspect
        hardware_profile.warnings and pass them through to the frontend.
        """
        t0 = time.perf_counter()

        # ── Hardware evaluation ──
        profile = HardwareEvaluator.evaluate()

        if mode == "auto":
            mode = profile.recommended_mode

        if profile.tier == "incompatible":
            raise OcrHardwareError(
                status_code=503,
                detail=(
                    "System does not meet minimum hardware requirements for OCR. "
                    f"Required: >=2 GB RAM. Detected: {profile.ram_total_gb:.1f} GB."
                ),
            )

        # ── Open and validate image ──
        img = cls._open_image(image_bytes)
        img = cls._downscale_if_needed(img)

        engines_used: list[str] = []
        tesseract_text = ""
        paddle_items: list[dict] = []

        # ── Route to engines ──
        if mode == "hybrid":
            tesseract_text = cls._extract_metadata_tesseract(img)
            paddle_items = cls._extract_tabular_paddleocr(img)
            engines_used = ["tesseract", "paddleocr"]
        else:
            tesseract_text = cls._extract_tesseract_full(img)
            engines_used = ["tesseract"]

        # ── Regex structuring ──
        structured = InvoiceRegexParser.parse(tesseract_text, paddle_items)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        result = HybridOcrResult(
            invoice_number=structured["invoice_number"],
            total_amount=structured["total_amount"],
            line_items=structured["line_items"],
            metadata=structured["metadata"],
            confidence=structured["confidence"],
            raw_text=tesseract_text,
            engines_used=engines_used,
            processing_time_ms=round(elapsed_ms, 1),
        )

        log.info(
            "Hybrid OCR completed: mode=%s engines=%s items=%d time=%.0fms",
            mode,
            engines_used,
            len(result.line_items),
            elapsed_ms,
        )
        return result, profile

    # ── Image helpers ────────────────────────────────────────────────────

    @staticmethod
    def _open_image(image_bytes: bytes) -> Image.Image:
        try:
            img = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            raise OcrHardwareError(status_code=400, detail=f"Invalid image: {e}")
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")
        return img

    @staticmethod
    def _downscale_if_needed(img: Image.Image) -> Image.Image:
        """Downscale image to limit_side_len to prevent OOM on thin clients."""
        limit = settings.hybrid_ocr_limit_side_len
        w, h = img.size
        longest = max(w, h)
        if longest <= limit:
            return img
        scale = limit / longest
        new_w = int(w * scale)
        new_h = int(h * scale)
        log.info("Downscaling image: %dx%d -> %dx%d", w, h, new_w, new_h)
        return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # ── Tesseract engines ────────────────────────────────────────────────

    @staticmethod
    def _extract_metadata_tesseract(img: Image.Image) -> str:
        """CPU-only Tesseract for flat metadata (vendor, invoice#, date)."""
        os.environ["OMP_THREAD_LIMIT"] = str(settings.hybrid_ocr_tesseract_threads)
        try:
            import pytesseract

            text = pytesseract.image_to_string(img)
            return text.strip()
        except Exception as e:
            log.error("Tesseract metadata extraction failed: %s", e)
            return ""

    @staticmethod
    def _extract_tesseract_full(img: Image.Image) -> str:
        """Full Tesseract extraction for Tesseract-only mode."""
        os.environ["OMP_THREAD_LIMIT"] = str(settings.hybrid_ocr_tesseract_threads)
        try:
            from app.services.ocr_cascade import run_cascade

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            cascade = run_cascade(buf.getvalue(), cascade_id="hybrid-tesseract-only")
            return cascade.text
        except Exception as e:
            log.error("Tesseract full extraction failed: %s", e)
            return ""

    # ── PaddleOCR engine ─────────────────────────────────────────────────

    @classmethod
    def _extract_tabular_paddleocr(cls, img: Image.Image) -> list[dict]:
        """PaddleOCR for tabular line item extraction."""
        try:
            ocr = cls._get_paddleocr()
        except OcrHardwareError:
            return []
        except Exception as e:
            log.error("PaddleOCR init failed: %s", e)
            return []

        try:
            import numpy as np

            img_array = np.array(img)
            result = ocr.ocr(img_array, cls=True)
            return cls._parse_paddleocr_result(result)
        except Exception as e:
            log.error("PaddleOCR extraction failed: %s", e)
            return []

    @classmethod
    def _get_paddleocr(cls):
        """Singleton PaddleOCR instance with lock (prevents state corruption)."""
        global _paddle_instance
        if _paddle_instance is not None:
            return _paddle_instance

        with _paddle_lock:
            if _paddle_instance is not None:
                return _paddle_instance

            profile = HardwareEvaluator.evaluate()
            use_gpu = settings.hybrid_ocr_gpu and profile.gpu_available

            log.info(
                "Initializing PaddleOCR: gpu=%s lang=%s",
                use_gpu,
                settings.hybrid_ocr_lang,
            )

            from paddleocr import PaddleOCR

            instance = PaddleOCR(
                use_angle_cls=True,
                lang=settings.hybrid_ocr_lang,
                use_gpu=use_gpu,
                show_log=False,
                rec_batch_num=6,
                max_text_length=256,
            )
            _paddle_instance = instance
            return instance

    @staticmethod
    def _parse_paddleocr_result(result: Any) -> list[dict]:
        """Parse PaddleOCR output into line item dicts."""
        items: list[dict] = []
        if not result or not isinstance(result, list):
            return items

        for page in result:
            if not page:
                continue
            for line in page:
                if not line or len(line) < 2:
                    continue
                text_block = line[1]
                if isinstance(text_block, (list, tuple)) and len(text_block) >= 2:
                    text = str(text_block[0])
                    confidence = float(text_block[1])
                else:
                    text = str(text_block)
                    confidence = 0.0

                if confidence < 0.3 or len(text.strip()) < 2:
                    continue

                parsed = InvoiceRegexParser._parse_line_item(text)
                if parsed:
                    items.append(parsed)

        return items


class InvoiceRegexParser:
    """Strict regex parser for invoice fields from merged OCR text."""

    RE_INVOICE_NUM = re.compile(
        r"(?:invoice|inv)[#\s:]*([A-Z]{0,4}[-\s]?\d{3,20})", re.IGNORECASE,
    )
    RE_TOTAL = re.compile(
        r"(?:total|grand\s*total|amount\s*due|balance\s*due)[:\s]*"
        r"[\$£€]?\s*([\d,]+\.?\d{0,2})",
        re.IGNORECASE,
    )
    RE_DATE = re.compile(
        r"(?:date|invoice\s*date|dated)[:\s]*(\d{1,4}[/\-\.]\d{1,2}[/\-\.]\d{1,4})",
        re.IGNORECASE,
    )
    RE_VENDOR = re.compile(
        r"(?:from|vendor|supplier|sold\s*by|company)[:\s]*(.+?)(?:\n|$)",
        re.IGNORECASE,
    )
    RE_LINE_ITEM = re.compile(
        r"(.+?)\s+(\d{1,5})\s+[\$£€]?\s*([\d,]+\.?\d{0,2})\s*$",
    )

    @classmethod
    def parse(
        cls, tesseract_text: str, paddle_items: list[dict],
    ) -> dict[str, Any]:
        """Merge Tesseract metadata + PaddleOCR tabular items into structured JSON."""
        invoice_number = cls._extract_invoice_number(tesseract_text)
        total_amount = cls._extract_total(tesseract_text)
        date = cls._extract_date(tesseract_text)
        vendor = cls._extract_vendor(tesseract_text)

        # Merge line items: PaddleOCR takes priority, Tesseract as fallback
        line_items = list(paddle_items) if paddle_items else []
        if not line_items:
            line_items = cls._extract_line_items_from_text(tesseract_text)

        # Confidence scoring
        tesseract_conf = 0.85 if tesseract_text else 0.0
        paddle_conf = 0.0
        if paddle_items:
            paddle_conf = 0.90
        overall = max(tesseract_conf, paddle_conf) if (tesseract_conf or paddle_conf) else 0.0

        return {
            "invoice_number": invoice_number,
            "total_amount": total_amount,
            "line_items": line_items,
            "metadata": {
                k: v
                for k, v in {
                    "vendor": vendor,
                    "date": date,
                    "invoice_number": invoice_number,
                }.items()
                if v
            },
            "confidence": {
                "tesseract": round(tesseract_conf, 3),
                "paddleocr": round(paddle_conf, 3),
                "overall": round(overall, 3),
            },
        }

    @classmethod
    def _extract_invoice_number(cls, text: str) -> str | None:
        m = cls.RE_INVOICE_NUM.search(text)
        return m.group(1).strip() if m else None

    @classmethod
    def _extract_total(cls, text: str) -> float | None:
        m = cls.RE_TOTAL.search(text)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                return float(raw)
            except ValueError:
                pass
        return None

    @classmethod
    def _extract_date(cls, text: str) -> str | None:
        m = cls.RE_DATE.search(text)
        return m.group(1).strip() if m else None

    @classmethod
    def _extract_vendor(cls, text: str) -> str | None:
        m = cls.RE_VENDOR.search(text)
        return m.group(1).strip() if m else None

    @classmethod
    def _extract_line_items_from_text(cls, text: str) -> list[dict]:
        """Extract line items from raw text via regex."""
        items: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = cls.RE_LINE_ITEM.match(line)
            if m:
                desc = m.group(1).strip()
                qty_raw = m.group(2)
                price_raw = m.group(3).replace(",", "")
                try:
                    qty = int(qty_raw)
                    price = float(price_raw)
                except ValueError:
                    continue
                items.append({
                    "description": desc,
                    "quantity": qty,
                    "unit_price": price,
                })
        return items

    @staticmethod
    def _parse_line_item(text: str) -> dict | None:
        """Try to parse a single PaddleOCR text block as a line item."""
        text = text.strip()
        if len(text) < 3:
            return None

        # Try pattern: "Description Qty Price"
        m = re.match(
            r"(.+?)\s+(\d{1,5})\s+[\$£€]?\s*([\d,]+\.?\d{0,2})\s*$",
            text,
        )
        if m:
            try:
                return {
                    "description": m.group(1).strip(),
                    "quantity": int(m.group(2)),
                    "unit_price": float(m.group(3).replace(",", "")),
                }
            except ValueError:
                pass

        # Try pattern: "Description Qty x Price"
        m = re.match(
            r"(.+?)\s+(\d{1,5})\s*[xX×]\s*[\$£€]?\s*([\d,]+\.?\d{0,2})\s*$",
            text,
        )
        if m:
            try:
                return {
                    "description": m.group(1).strip(),
                    "quantity": int(m.group(2)),
                    "unit_price": float(m.group(3).replace(",", "")),
                }
            except ValueError:
                pass

        return None


class OcrHardwareError(Exception):
    """Raised when hardware requirements are not met."""

    def __init__(self, status_code: int = 503, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

"""Tests for hybrid OCR engine and invoice regex parser."""
from __future__ import annotations

import io
import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.services.hybrid_ocr_engine import (
    HybridOcrEngine,
    HybridOcrResult,
    InvoiceRegexParser,
    OcrHardwareError,
)
from app.services.hardware_evaluator import HardwareProfile


def _make_test_image(width: int = 100, height: int = 50, color: str = "white") -> bytes:
    """Create a minimal valid PNG image for testing."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── InvoiceRegexParser Tests ────────────────────────────────────────────────

class TestInvoiceRegexParser:
    def test_extract_invoice_number(self) -> None:
        text = "Invoice INV-1001 dated 2024-01-15"
        result = InvoiceRegexParser._extract_invoice_number(text)
        assert result == "INV-1001"

    def test_extract_invoice_number_no_match(self) -> None:
        text = "No invoice number here"
        result = InvoiceRegexParser._extract_invoice_number(text)
        assert result is None

    def test_extract_total(self) -> None:
        text = "Total: $1,234.56"
        result = InvoiceRegexParser._extract_total(text)
        assert result == 1234.56

    def test_extract_total_no_symbol(self) -> None:
        text = "Grand Total: 500.00"
        result = InvoiceRegexParser._extract_total(text)
        assert result == 500.00

    def test_extract_total_no_match(self) -> None:
        text = "No total here"
        result = InvoiceRegexParser._extract_total(text)
        assert result is None

    def test_extract_date(self) -> None:
        text = "Date: 2024-06-15"
        result = InvoiceRegexParser._extract_date(text)
        assert result == "2024-06-15"

    def test_extract_vendor(self) -> None:
        text = "Vendor: Acme Pharmaceuticals"
        result = InvoiceRegexParser._extract_vendor(text)
        assert result == "Acme Pharmaceuticals"

    def test_parse_line_item(self) -> None:
        result = InvoiceRegexParser._parse_line_item("Amoxicillin 500mg 100 5.50")
        assert result is not None
        assert result["description"] == "Amoxicillin 500mg"
        assert result["quantity"] == 100
        assert result["unit_price"] == 5.50

    def test_parse_line_item_with_currency(self) -> None:
        result = InvoiceRegexParser._parse_line_item("Paracetamol 250mg 200 $3.25")
        assert result is not None
        assert result["quantity"] == 200
        assert result["unit_price"] == 3.25

    def test_parse_line_item_no_match(self) -> None:
        result = InvoiceRegexParser._parse_line_item("Random text without numbers")
        assert result is None

    def test_extract_line_items_from_text(self) -> None:
        text = (
            "Amoxicillin 500mg 100 5.50\n"
            "Paracetamol 250mg 200 3.25\n"
        )
        items = InvoiceRegexParser._extract_line_items_from_text(text)
        assert len(items) == 2
        assert items[0]["description"] == "Amoxicillin 500mg"
        assert items[1]["quantity"] == 200

    def test_parse_merges_tesseract_and_paddle(self) -> None:
        tesseract_text = "Invoice INV-1001\nTotal: $500.00\nDate: 2024-01-15"
        paddle_items = [{"description": "Drug A", "quantity": 50, "unit_price": 10.0}]
        result = InvoiceRegexParser.parse(tesseract_text, paddle_items)
        assert result["invoice_number"] == "INV-1001"
        assert result["total_amount"] == 500.0
        assert result["metadata"]["date"] == "2024-01-15"
        assert len(result["line_items"]) == 1
        assert result["confidence"]["tesseract"] > 0
        assert result["confidence"]["paddleocr"] > 0


# ── HybridOcrEngine Tests ──────────────────────────────────────────────────

class TestHybridOcrEngine:
    def test_open_image_valid(self) -> None:
        img_bytes = _make_test_image()
        img = HybridOcrEngine._open_image(img_bytes)
        assert img.mode in ("L", "RGB")
        assert img.size == (100, 50)

    def test_open_image_invalid(self) -> None:
        with pytest.raises(OcrHardwareError, match="Invalid image"):
            HybridOcrEngine._open_image(b"not an image")

    def test_downscale_if_needed_no_downscale(self) -> None:
        img = Image.new("RGB", (500, 300))
        result = HybridOcrEngine._downscale_if_needed(img)
        assert result.size == (500, 300)

    def test_downscale_if_needed_large_image(self) -> None:
        img = Image.new("RGB", (2000, 1500))
        result = HybridOcrEngine._downscale_if_needed(img)
        assert max(result.size) <= 960

    @patch("app.services.hybrid_ocr_engine.HybridOcrEngine._extract_tabular_paddleocr", return_value=[])
    @patch("app.services.hybrid_ocr_engine.HybridOcrEngine._extract_metadata_tesseract", return_value="Test text")
    @patch("app.services.hybrid_ocr_engine.HardwareEvaluator.evaluate")
    def test_extract_hybrid_tesseract_only(self, mock_eval, mock_tess, mock_paddle) -> None:
        from app.services.hardware_evaluator import HardwareProfile
        mock_eval.return_value = HardwareProfile(
            tier="constrained", recommended_mode="tesseract_only",
            ram_total_gb=8.0, cpu_threads=4,
        )
        img_bytes = _make_test_image()
        result, profile = HybridOcrEngine.extract_hybrid(img_bytes, mode="tesseract_only")
        assert isinstance(result, HybridOcrResult)
        # Tesseract-only mode uses _extract_tesseract_full which calls ocr_cascade
        # On systems without Tesseract installed, this will return empty text
        assert "tesseract" in result.engines_used
        assert result.processing_time_ms > 0

    def test_hardware_error_attributes(self) -> None:
        err = OcrHardwareError(status_code=503, detail="No GPU")
        assert err.status_code == 503
        assert err.detail == "No GPU"
        assert str(err) == "No GPU"


# ── HardwareEvaluator Integration ──────────────────────────────────────────

class TestHardwareEvaluatorIntegration:
    def test_evaluate_returns_profile(self) -> None:
        from app.services.hardware_evaluator import HardwareEvaluator
        mock_psutil = MagicMock()
        mock_psutil.cpu_count.return_value = 4
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=int(8.0 * 1024**3), available=int(6.0 * 1024**3)
        )
        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            profile = HardwareEvaluator.evaluate(force=True)
            assert isinstance(profile, HardwareProfile)
            assert profile.tier in ("capable", "constrained", "incompatible")
            assert profile.recommended_mode in ("hybrid", "tesseract_only")

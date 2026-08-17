"""
ocr_engine.py — Core OCR Extraction Engine with Standardized Confidence Scores.

Provides an abstract OCR backend interface, concrete implementations for
available libraries (pytesseract, easyocr), and Pillow-based preprocessing
strategies. All extraction results use the standardized ExtractionResult
dataclass with a normalized confidence score (0.0–1.0).

Usage:
    from ocr_engine import OCRCascadeEngine, ExtractionResult

    engine = OCRCascadeEngine()
    result = engine.extract(image, strategy="standard")
    print(result.text, result.confidence, result.method)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from typing import Optional

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

log = logging.getLogger(__name__)

# ── Confidence thresholds per cascade tier ──────────────────────────────

CONF_HIGH = 0.90
CONF_MEDIUM = 0.70
CONF_LOW = 0.50
CONF_FALLBACK = 0.30


class OCRCapability(Enum):
    """Indicates which OCR backend produced the result, or NONE if unavailable."""
    TESSERACT = "tesseract"
    EASYOCR = "easyocr"
    PILLOW_PATTERN = "pillow_pattern"
    NONE = "none"


@dataclass
class ExtractionResult:
    """Standardized OCR extraction result with normalized confidence."""
    text: str
    confidence: float
    method: str
    engine: OCRCapability
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def needs_review(self) -> bool:
        """Flag results with low confidence for human review."""
        return self.confidence < CONF_FALLBACK


# ── Image Preprocessing ──────────────────────────────────────────────────

def load_image(source) -> Image.Image:
    """Load a PIL Image from a path, BytesIO, or existing Image."""
    if isinstance(source, Image.Image):
        return source
    if isinstance(source, (str, bytes, bytearray)):
        return Image.open(source)
    if hasattr(source, "read"):
        return Image.open(source)
    raise TypeError(f"Unsupported image source type: {type(source).__name__}")


def preprocess_image(image: Image.Image, strategy: str = "standard") -> Image.Image:
    """Apply preprocessing based on strategy name.

    Strategies:
        standard  — grayscale + binary threshold (Otsu)
        adaptive  — grayscale + adaptive threshold + contrast boost
        enhanced  — grayscale + contrast stretch + noise reduction
        minimal   — grayscale only
    """
    if image.mode not in ("L", "RGB"):
        image = image.convert("RGB")

    if strategy == "minimal":
        return image.convert("L")

    gray = ImageOps.grayscale(image)

    if strategy == "standard":
        # Otsu's threshold (single threshold auto-computed)
        return gray.point(lambda p: 0 if p < 128 else 255, mode="1")

    if strategy == "adaptive":
        # Enhance contrast first, then adaptive-like threshold
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(1.5)
        # Approximate adaptive threshold: use a high-contrast point transform
        return gray.point(lambda p: 0 if p < 140 else 255, mode="1")

    if strategy == "enhanced":
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(2.0)
        # Median filter for noise reduction (3x3 kernel)
        gray = gray.filter(ImageFilter.MedianFilter(size=3))
        return gray.point(lambda p: 0 if p < 128 else 255, mode="1")

    log.warning("Unknown preprocessing strategy '%s', falling back to 'standard'", strategy)
    return preprocess_image(image, "standard")


# ── OCR Engine Backends ──────────────────────────────────────────────────

class OCREngine:
    """Base class for OCR engines. Subclasses implement _extract()."""

    name: str = "base"

    def extract(self, image: Image.Image, strategy: str = "standard") -> ExtractionResult:
        """Extract text from image. Returns ExtractionResult with confidence."""
        try:
            processed = preprocess_image(image, strategy)
            return self._extract(processed)
        except Exception as exc:
            log.error("%s.extract failed: %s", self.name, exc)
            return ExtractionResult(
                text="", confidence=0.0, method=f"{self.name}_error",
                engine=self._capability(),
                metadata={"error": str(exc)},
            )

    def _extract(self, image: Image.Image) -> ExtractionResult:
        raise NotImplementedError

    def _capability(self) -> OCRCapability:
        raise NotImplementedError


class TesseractEngine(OCREngine):
    """Wraps pytesseract for OCR extraction."""

    name = "tesseract"

    def __init__(self):
        try:
            import pytesseract
            self._pt = pytesseract
        except ImportError:
            self._pt = None
            log.warning("pytesseract not installed; TesseractEngine unavailable")

    def _available(self) -> bool:
        return self._pt is not None

    def _capability(self) -> OCRCapability:
        return OCRCapability.TESSERACT if self._available() else OCRCapability.NONE

    def _extract(self, image: Image.Image) -> ExtractionResult:
        if not self._available():
            return ExtractionResult(
                text="", confidence=0.0, method="tesseract_unavailable",
                engine=OCRCapability.NONE,
                metadata={"reason": "pytesseract not installed"},
            )
        # pytesseract.image_to_data returns dict with confidence per word
        data = self._pt.image_to_data(image, output_type=self._pt.Output.DICT)
        words = data.get("text", [])
        confs = data.get("conf", [])

        # Filter out empty words
        valid = [(w, c) for w, c in zip(words, confs) if w and w.strip()]
        if not valid:
            return ExtractionResult(text="", confidence=0.0,
                                     method="tesseract_no_text",
                                     engine=OCRCapability.TESSERACT)

        text = " ".join(w for w, _ in valid)
        # pytesseract conf is 0-100; normalize to 0-1
        mean_conf = sum(c for _, c in valid) / len(valid) / 100.0
        # Apply length penalty for very short results
        if len(text.strip()) < 5:
            mean_conf *= 0.7
        return ExtractionResult(
            text=text.strip(), confidence=mean_conf,
            method="tesseract_image_to_data",
            engine=OCRCapability.TESSERACT,
            metadata={"word_count": len(valid)},
        )


class EasyOCREngine(OCREngine):
    """Wraps easyocr for OCR extraction."""

    name = "easyocr"

    def __init__(self):
        try:
            import easyocr
            self._easy = easyocr
            self._reader = None
        except ImportError:
            self._easy = None
            log.warning("easyocr not installed; EasyOCREngine unavailable")

    def _available(self) -> bool:
        return self._easy is not None

    def _capability(self) -> OCRCapability:
        return OCRCapability.EASYOCR if self._available() else OCRCapability.NONE

    def _extract(self, image: Image.Image) -> ExtractionResult:
        if not self._available():
            return ExtractionResult(
                text="", confidence=0.0, method="easyocr_unavailable",
                engine=OCRCapability.NONE,
                metadata={"reason": "easyocr not installed"},
            )
        if self._reader is None:
            self._reader = self._easy.Reader(["en"], gpu=False)

        # easyocr expects RGB numpy array; but we avoid numpy dependency
        # Convert to raw pixel data via BytesIO
        buf = BytesIO()
        # easyocr can accept PIL images directly in recent versions
        results = self._reader.readtext(image, detail=1)
        if not results:
            return ExtractionResult(text="", confidence=0.0,
                                     method="easyocr_no_text",
                                     engine=OCRCapability.EASYOCR)

        text_parts = [r[1] for r in results]
        confs = [r[2] for r in results]
        text = " ".join(text_parts)
        mean_conf = sum(confs) / len(confs) if confs else 0.0
        return ExtractionResult(
            text=text.strip(), confidence=float(mean_conf),
            method="easyocr_readtext",
            engine=OCRCapability.EASYOCR,
            metadata={"block_count": len(results)},
        )


class PillowPatternEngine(OCREngine):
    """Fallback engine using Pillow-based heuristics for barcode-like labels.

    When no OCR backend is available, this engine uses Pillow to identify
    dense rectangular regions (potential barcodes) and estimates confidence
    based on image characteristics (contrast, density).
    """

    name = "pillow_pattern"

    def _capability(self) -> OCRCapability:
        return OCRCapability.PILLOW_PATTERN

    def _extract(self, image: Image.Image) -> ExtractionResult:
        gray = image.convert("L") if image.mode != "L" else image

        # Compute image statistics for confidence estimation
        # Use a downscaled histogram-based analysis
        thumb = gray.resize((32, 32))
        pixels = list(thumb.getdata())
        total = len(pixels)
        dark = sum(1 for p in pixels if p < 128)
        light = total - dark
        density = max(dark / total, light / total)

        # Contrast estimation
        if total > 0:
            mean_val = sum(pixels) / total
            variance = sum((p - mean_val) ** 2 for p in pixels) / total
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0.0

        # Confidence: based on density (balanced black/white ratio) and contrast
        contrast_score = min(std_dev / 80.0, 1.0)
        density_score = 1.0 - abs(0.5 - density) * 2  # peaks at 50% density
        confidence = contrast_score * 0.6 + density_score * 0.4

        # If the image has reasonable structure, return a placeholder with confidence
        text = ""
        if confidence > CONF_FALLBACK:
            # We cannot extract real text without OCR, but we flag it as reviewable
            text = "[OCR engine not available — image requires manual review]"

        return ExtractionResult(
            text=text, confidence=confidence,
            method="pillow_pattern_analysis",
            engine=OCRCapability.PILLOW_PATTERN,
            metadata={
                "density": round(density, 3),
                "contrast_std": round(std_dev, 2),
                "image_mode": image.mode,
                "image_size": f"{image.width}x{image.height}",
            },
        )


class OCRCascadeEngine:
    """High-level engine that manages available backends and provides
    a simple single-call API for extraction."""

    def __init__(self):
        self._engines: list[OCREngine] = []
        self._tesseract = TesseractEngine()
        if self._tesseract._available():
            self._engines.append(self._tesseract)

        self._easyocr = EasyOCREngine()
        if self._easyocr._available():
            self._engines.append(self._easyocr)

        self._pillow = PillowPatternEngine()
        self._engines.append(self._pillow)

        log.info("OCREngine initialized with %d active backend(s): %s",
                 len(self._engines), [e.name for e in self._engines])

    @property
    def available_engines(self) -> list[str]:
        return [e.name for e in self._engines]

    @property
    def has_tesseract(self) -> bool:
        return self._tesseract._available()

    @property
    def has_easyocr(self) -> bool:
        return self._easyocr._available()

    def extract(self, image, strategy: str = "standard") -> ExtractionResult:
        """Run the first available engine on the image."""
        img = load_image(image)
        if not self._engines:
            return ExtractionResult(
                text="", confidence=0.0, method="no_engines",
                engine=OCRCapability.NONE,
                metadata={"error": "No OCR engines available"},
            )
        return self._engines[0].extract(img, strategy)

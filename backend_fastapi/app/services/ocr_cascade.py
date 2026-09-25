"""4-Tier OCR cascade with confidence-based escalation.

Tier 1: Tesseract Standard (binary threshold) — 90% cutoff
Tier 2: Tesseract Enhanced (contrast + noise) — 70% cutoff
Tier 3: Tesseract Adaptive (adaptive threshold) — 50% cutoff
Tier 4: Pillow Pattern (grayscale + edge detection) — 30% cutoff

Each tier returns immediately if confidence >= threshold. If all tiers fail,
the best result is returned with needs_review=True.
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

log = logging.getLogger(__name__)

CONF_HIGH = 0.90
CONF_MEDIUM = 0.70
CONF_LOW = 0.50
CONF_FALLBACK = 0.30


@dataclass
class TierResult:
    tier: int
    name: str
    text: str
    confidence: float
    passed: bool
    elapsed_ms: float


@dataclass
class CascadeResult:
    text: str
    confidence: float
    successful_tier: int
    successful_tier_name: str
    all_tiers: list[TierResult] = field(default_factory=list)
    needs_review: bool = False
    word_count: int = 0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "successful_tier": self.successful_tier,
            "successful_tier_name": self.successful_tier_name,
            "needs_review": self.needs_review,
            "word_count": self.word_count,
            "tiers": [
                {
                    "tier": t.tier,
                    "name": t.name,
                    "confidence": round(t.confidence, 3),
                    "passed": t.passed,
                    "elapsed_ms": round(t.elapsed_ms, 1),
                }
                for t in self.all_tiers
            ],
        }


def _preprocess_standard(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    return gray.point(lambda p: 0 if p < 128 else 255, mode="1")


def _preprocess_enhanced(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    enhanced = ImageEnhance.Contrast(gray).enhance(2.0)
    sharpened = enhanced.filter(ImageFilter.SHARPEN)
    return sharpened.point(lambda p: 0 if p < 100 else 255, mode="1")


def _preprocess_adaptive(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    enhanced = ImageEnhance.Contrast(gray).enhance(1.5)
    denoised = enhanced.filter(ImageFilter.MedianFilter(size=3))
    return denoised.point(lambda p: 0 if p < 120 else 255, mode="1")


def _preprocess_pillow(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    return ImageOps.invert(edges)


_PREPROCESSORS = {
    "standard": _preprocess_standard,
    "enhanced": _preprocess_enhanced,
    "adaptive": _preprocess_adaptive,
    "pillow": _preprocess_pillow,
}

_TIER_CONFIG = [
    {"name": "Tesseract (Standard)", "strategy": "standard", "threshold": CONF_HIGH},
    {"name": "Tesseract (Enhanced)", "strategy": "enhanced", "threshold": CONF_MEDIUM},
    {"name": "Tesseract (Adaptive)", "strategy": "adaptive", "threshold": CONF_LOW},
    {"name": "Pillow Pattern", "strategy": "pillow", "threshold": CONF_FALLBACK},
]


def _extract_with_tesseract(img: Image.Image) -> tuple[str, float]:
    """Run pytesseract and return (text, normalized_confidence)."""
    try:
        import pytesseract
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        words = data.get("text", [])
        confs = data.get("conf", [])
        valid = [(w, c) for w, c in zip(words, confs) if w and w.strip()]
        if not valid:
            return "", 0.0
        text = " ".join(w for w, _ in valid)
        mean_conf = sum(c for _, c in valid) / len(valid) / 100.0
        if len(text.strip()) < 5:
            mean_conf *= 0.7
        return text.strip(), max(0.0, min(1.0, mean_conf))
    except Exception as e:
        log.debug("Tesseract failed: %s", e)
        return "", 0.0


def _extract_pillow_pattern(img: Image.Image) -> tuple[str, float]:
    """Best-effort pattern analysis — returns empty text with low confidence.

    This tier exists as the final fallback. It cannot extract real text but
    signals that the image was processed and needs human review.
    """
    return "", 0.1


def run_cascade(image_bytes: bytes, cascade_id: str = "") -> CascadeResult:
    """Run the 4-tier OCR cascade on raw image bytes.

    Returns CascadeResult with the best text, per-tier details, and
    needs_review flag when confidence is below CONF_FALLBACK.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        log.error("Failed to open image: %s", e)
        return CascadeResult(
            text="", confidence=0.0, successful_tier=0,
            successful_tier_name="None", needs_review=True, word_count=0,
        )

    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")

    all_tiers: list[TierResult] = []
    best_text = ""
    best_conf = 0.0
    successful_tier = 0
    successful_name = "None"

    for idx, cfg in enumerate(_TIER_CONFIG):
        tier_num = idx + 1
        preprocessor = _PREPROCESSORS[cfg["strategy"]]
        processed = preprocessor(img)

        t0 = time.perf_counter()
        if cfg["strategy"] == "pillow":
            text, conf = _extract_pillow_pattern(processed)
        else:
            text, conf = _extract_with_tesseract(processed)
        elapsed = (time.perf_counter() - t0) * 1000.0

        passed = conf >= cfg["threshold"]
        tr = TierResult(
            tier=tier_num, name=cfg["name"],
            text=text, confidence=conf,
            passed=passed, elapsed_ms=elapsed,
        )
        all_tiers.append(tr)

        log.info(
            "[%s] Tier %d '%s': conf=%.3f threshold=%.2f %s %.1fms",
            cascade_id, tier_num, cfg["name"],
            conf, cfg["threshold"],
            "PASS" if passed else "FAIL", elapsed,
        )

        if conf > best_conf:
            best_text = text
            best_conf = conf

        if passed:
            successful_tier = tier_num
            successful_name = cfg["name"]
            best_text = text
            best_conf = conf
            break

    word_count = len(best_text.split()) if best_text else 0
    needs_review = best_conf < CONF_FALLBACK

    return CascadeResult(
        text=best_text,
        confidence=best_conf,
        successful_tier=successful_tier,
        successful_tier_name=successful_name,
        all_tiers=all_tiers,
        needs_review=needs_review,
        word_count=word_count,
    )

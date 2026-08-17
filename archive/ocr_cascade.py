"""
ocr_cascade.py — 4-Tier Confidence Cascade for OCR Text Extraction.

Implements a cascading fallback system that attempts extraction at increasing
levels of processing power / alternative methods. Each tier has a confidence
threshold; if the threshold is not met, the cascade falls through to the next tier.

Cascade Flow:
    ┌─────────────────────────────────────────────────────────────────────┐
    │ Tier 1: Tesseract (standard preprocessing) — 90% confidence cutoff  │
    │   ↳ Passes → return result                                          │
    │   ↳ Fails → Tier 2                                                │
    │                                                                     │
    │ Tier 2: Tesseract (enhanced preprocessing) — 70% confidence cutoff  │
    │   ↳ Passes → return result                                          │
    │   ↳ Fails → Tier 3                                                │
    │                                                                     │
    │ Tier 3: EasyOCR (if installed) — 50% confidence cutoff              │
    │   ↳ Passes → return result                                          │
    │   ↳ Fails → Tier 4                                                │
    │                                                                     │
    │ Tier 4: Pillow Pattern Analysis — 30% confidence cutoff           │
    │   ↳ Returns best available result (may need_review=True)          │
    └─────────────────────────────────────────────────────────────────────┘

Usage:
    from ocr_cascade import OCRCascade, CascadeResult

    cascade = OCRCascade()
    result = cascade.extract(image_path)
    print(result.text)
    print(result.confidence)
    print(result.successful_tier)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ocr_engine import (
    OCRCascadeEngine, ExtractionResult, OCRCapability,
    CONF_HIGH, CONF_MEDIUM, CONF_LOW, CONF_FALLBACK,
    load_image, preprocess_image,
    TesseractEngine, EasyOCREngine, PillowPatternEngine,
)

log = logging.getLogger(__name__)


@dataclass
class TierResult:
    """Result of a single cascade tier."""
    tier: int
    name: str
    confidence_threshold: float
    result: Optional[ExtractionResult] = None
    passed: bool = False
    elapsed_ms: float = 0.0


@dataclass
class CascadeResult:
    """Final result after running the cascade."""
    text: str
    confidence: float
    successful_tier: int
    successful_tier_name: str
    all_tier_results: list[TierResult] = field(default_factory=list)
    needs_review: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """True if any tier passed its confidence threshold."""
        return self.successful_tier > 0


def _build_tiers() -> list[dict]:
    """Build the 4-tier cascade configuration.

    Each tier specifies:
        - name: human-readable label
        - engine: OCREngine instance
        - strategy: preprocessing strategy
        - threshold: minimum confidence to pass this tier
        - skip_if_unavailable: tier is skipped (not failed) when engine is unavailable
    """
    tess = TesseractEngine()
    easy = EasyOCREngine()
    pillow = PillowPatternEngine()

    tiers = [
        {
            "name": "Tesseract (Standard)",
            "engine": tess,
            "strategy": "standard",
            "threshold": CONF_HIGH,
            "skip_if_unavailable": True,
        },
        {
            "name": "Tesseract (Enhanced)",
            "engine": tess,
            "strategy": "enhanced",
            "threshold": CONF_MEDIUM,
            "skip_if_unavailable": True,
        },
        {
            "name": "EasyOCR",
            "engine": easy,
            "strategy": "standard",
            "threshold": CONF_LOW,
            "skip_if_unavailable": True,
        },
        {
            "name": "Pillow Pattern Analysis",
            "engine": pillow,
            "strategy": "minimal",
            "threshold": CONF_FALLBACK,
            "skip_if_unavailable": False,
        },
    ]
    return tiers


class OCRCascade:
    """4-tier confidence cascade for OCR text extraction.

    Each tier attempts extraction with a different engine + preprocessing
    strategy. If the confidence falls below the tier's threshold, the cascade
    moves to the next tier. The final result includes all tier results for
    transparency and debugging.
    """

    TIER_NAMES = [
        "Tesseract (Standard)",
        "Tesseract (Enhanced)",
        "EasyOCR",
        "Pillow Pattern Analysis",
    ]

    THRESHOLDS = [CONF_HIGH, CONF_MEDIUM, CONF_LOW, CONF_FALLBACK]

    def __init__(self):
        self._tier_configs = _build_tiers()
        self._available_count = sum(
            1 for t in self._tier_configs
            if t["engine"]._capability() != OCRCapability.NONE
            or not t["skip_if_unavailable"]
        )
        log.info("OCRCascade initialized with %d active tier(s)", self._available_count)

    @property
    def available_tiers(self) -> list[str]:
        """Names of tiers whose engines are available."""
        return [
            t["name"] for t in self._tier_configs
            if t["engine"]._capability() != OCRCapability.NONE
            or not t["skip_if_unavailable"]
        ]

    def extract(self, image_source, cascade_id: str = "") -> CascadeResult:
        """Run the 4-tier cascade on an image.

        Args:
            image_source: Path, PIL Image, or file-like object.
            cascade_id: Optional identifier for logging/tracing.

        Returns:
            CascadeResult with final text, confidence, and per-tier details.
        """
        img = load_image(image_source)
        all_results: list[TierResult] = []
        best_result: Optional[ExtractionResult] = None
        successful_tier = 0

        for idx, cfg in enumerate(self._tier_configs):
            tier_num = idx + 1

            # Skip tiers whose engine is unavailable (when skip_if_unavailable=True)
            if (cfg["skip_if_unavailable"]
                    and cfg["engine"]._capability() == OCRCapability.NONE):
                tr = TierResult(
                    tier=tier_num, name=cfg["name"],
                    confidence_threshold=cfg["threshold"],
                    result=None, passed=False, elapsed_ms=0.0,
                )
                all_results.append(tr)
                log.debug("[%s] Tier %d '%s' skipped (engine unavailable)",
                          cascade_id, tier_num, cfg["name"])
                continue

            strategy = cfg["strategy"]
            threshold = cfg["threshold"]
            engine = cfg["engine"]

            t0 = time.perf_counter()
            result = engine.extract(img, strategy)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            passed = result.confidence >= threshold
            tr = TierResult(
                tier=tier_num, name=cfg["name"],
                confidence_threshold=threshold,
                result=result, passed=passed, elapsed_ms=elapsed_ms,
            )
            all_results.append(tr)

            log.info("[%s] Tier %d '%s': confidence=%.3f (threshold=%.2f) %s in %.1fms",
                      cascade_id, tier_num, cfg["name"],
                      result.confidence, threshold,
                      "PASS" if passed else "FAIL", elapsed_ms)

            if best_result is None or result.confidence > best_result.confidence:
                best_result = result

            if passed:
                successful_tier = tier_num
                break

        # Determine final result
        if best_result is None:
            best_result = ExtractionResult(
                text="", confidence=0.0, method="no_tiers_ran",
                engine=OCRCapability.NONE,
                metadata={"reason": "No OCR engines available"},
            )

        return CascadeResult(
            text=best_result.text,
            confidence=best_result.confidence,
            successful_tier=successful_tier,
            successful_tier_name=self.TIER_NAMES[successful_tier - 1] if successful_tier > 0 else "None",
            all_tier_results=all_results,
            needs_review=best_result.needs_review,
            metadata={
                "cascade_id": cascade_id,
                "best_method": best_result.method,
                "best_engine": best_result.engine.value,
                "engine_metadata": best_result.metadata,
                "total_tiers": len(all_results),
                "available_tiers": self.available_tiers,
            },
        )

    def extract_sync(self, image_source, cascade_id: str = "") -> CascadeResult:
        """Alias for extract() — named for clarity in async/sync contexts."""
        return self.extract(image_source, cascade_id)

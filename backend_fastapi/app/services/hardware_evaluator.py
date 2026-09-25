"""Pre-execution hardware evaluation for OCR resource management.

Profiles the host machine's GPU, RAM, and CPU before running heavy OCR
workloads to prevent OOM crashes on thin clients or low-VRAM environments.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

from app.shared.config import settings

log = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class HardwareProfile:
    """Snapshot of host machine hardware capabilities."""

    gpu_available: bool = False
    gpu_name: str | None = None
    gpu_vram_gb: float = 0.0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    cpu_threads: int = 0
    cpu_physical_cores: int = 0
    tier: Literal["capable", "constrained", "incompatible"] = "incompatible"
    recommended_mode: Literal["hybrid", "tesseract_only"] = "tesseract_only"
    warnings: list[str] = field(default_factory=list)
    evaluated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "gpu_available": self.gpu_available,
            "gpu_name": self.gpu_name,
            "gpu_vram_gb": round(self.gpu_vram_gb, 2),
            "ram_total_gb": round(self.ram_total_gb, 2),
            "ram_available_gb": round(self.ram_available_gb, 2),
            "cpu_threads": self.cpu_threads,
            "cpu_physical_cores": self.cpu_physical_cores,
            "tier": self.tier,
            "recommended_mode": self.recommended_mode,
            "warnings": list(self.warnings),
        }


class HardwareEvaluator:
    """Evaluates host hardware and caches the result for repeated calls."""

    _cache: HardwareProfile | None = None
    _cache_time: float = 0.0
    _lock = threading.Lock()

    @classmethod
    def evaluate(cls, force: bool = False) -> HardwareProfile:
        """Return a cached or fresh hardware profile.

        The result is cached for ``_CACHE_TTL_SECONDS`` so that rapid
        successive API calls (e.g. pre-flight check + upload) do not
        redundantly probe the hardware.
        """
        now = time.monotonic()
        if (
            not force
            and cls._cache is not None
            and (now - cls._cache_time) < _CACHE_TTL_SECONDS
        ):
            return cls._cache

        with cls._lock:
            now = time.monotonic()
            if (
                not force
                and cls._cache is not None
                and (now - cls._cache_time) < _CACHE_TTL_SECONDS
            ):
                return cls._cache

            profile = cls._probe()
            cls._cache = profile
            cls._cache_time = now
            log.info(
                "Hardware evaluation: tier=%s gpu=%s ram=%.1fGB cpu=%d threads",
                profile.tier,
                profile.gpu_name or "none",
                profile.ram_total_gb,
                profile.cpu_threads,
            )
            return profile

    @classmethod
    def _probe(cls) -> HardwareProfile:
        """Perform the actual hardware detection."""
        # psutil is a declared dependency, but degrade gracefully (conservative
        # CPU-tier defaults) if it is missing so evaluation never crashes.
        try:
            import psutil
        except ImportError:
            log.warning(
                "Hardware evaluation: psutil unavailable — using conservative defaults"
            )
            return HardwareProfile(
                tier="incompatible",
                gpu_name=None,
                ram_total_gb=0.0,
                ram_available_gb=0.0,
                cpu_threads=1,
                cpu_physical_cores=1,
                gpu_available=False,
                gpu_vram_gb=0.0,
                warnings=["psutil unavailable — hardware detection skipped"],
            )
        warnings: list[str] = []

        # ── CPU ──
        cpu_threads = psutil.cpu_count(logical=True) or 1
        cpu_physical = psutil.cpu_count(logical=False) or 1

        # ── RAM ──
        mem = psutil.virtual_memory()
        ram_total_gb = mem.total / (1024**3)
        ram_available_gb = mem.available / (1024**3)

        # ── GPU via PaddlePaddle ──
        gpu_available = False
        gpu_name: str | None = None
        gpu_vram_gb: float = 0.0

        if settings.hybrid_ocr_gpu:
            try:
                import paddle
                from paddle.device import cuda

                gpu_count = cuda.device_count()
                if gpu_count > 0:
                    gpu_available = True
                    gpu_name = paddle.device.get_device()
                    props = cuda.get_device_properties(0)
                    gpu_vram_gb = props.total_memory / (1024**3)
                    log.info(
                        "GPU detected: %s (%.1f GB VRAM)", gpu_name, gpu_vram_gb,
                    )
            except Exception as e:
                log.debug("GPU detection failed (falling back to CPU): %s", e)

        # ── Tier classification ──
        min_vram = settings.hybrid_ocr_min_vram_gb
        min_ram = settings.hybrid_ocr_min_ram_gb

        if ram_total_gb < 2.0:
            tier = "incompatible"
            warnings.append(
                f"System RAM critically low ({ram_total_gb:.1f} GB). "
                "Hybrid OCR cannot run on this machine."
            )
        elif gpu_available and gpu_vram_gb >= min_vram and ram_total_gb >= min_ram:
            tier = "capable"
        elif ram_total_gb < min_ram or (gpu_available and gpu_vram_gb < min_vram):
            tier = "constrained"
            if ram_total_gb < min_ram:
                warnings.append(
                    f"Low system RAM ({ram_total_gb:.1f} GB < {min_ram:.0f} GB). "
                    "Tesseract-only mode recommended to avoid OOM."
                )
            if gpu_available and gpu_vram_gb < min_vram:
                warnings.append(
                    f"Low GPU VRAM ({gpu_vram_gb:.1f} GB < {min_vram:.0f} GB). "
                    "PaddleOCR may run slowly or fail."
                )
        elif not gpu_available and cpu_threads < 4:
            tier = "constrained"
            warnings.append(
                f"No GPU detected and only {cpu_threads} CPU thread(s). "
                "Processing will be slower."
            )
        elif not gpu_available:
            tier = "constrained"
            warnings.append(
                "No GPU detected. PaddleOCR will run on CPU (slower)."
            )
        else:
            tier = "capable"

        # ── Recommended mode ──
        if tier == "capable":
            recommended_mode = "hybrid"
        else:
            recommended_mode = "tesseract_only"
            if tier == "constrained" and gpu_available:
                warnings.append(
                    "Running full hybrid OCR on constrained hardware will "
                    "consume high CPU/RAM resources. Do not run other heavy "
                    "applications concurrently."
                )

        return HardwareProfile(
            gpu_available=gpu_available,
            gpu_name=gpu_name,
            gpu_vram_gb=gpu_vram_gb,
            ram_total_gb=ram_total_gb,
            ram_available_gb=ram_available_gb,
            cpu_threads=cpu_threads,
            cpu_physical_cores=cpu_physical,
            tier=tier,
            recommended_mode=recommended_mode,
            warnings=warnings,
            evaluated_at=time.time(),
        )

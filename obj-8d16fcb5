"""Tests for hardware evaluator: GPU/RAM/CPU profiling and tier classification."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.services.hardware_evaluator import HardwareEvaluator, HardwareProfile


class TestHardwareProfile:
    def test_defaults(self) -> None:
        p = HardwareProfile()
        assert p.gpu_available is False
        assert p.gpu_vram_gb == 0.0
        assert p.ram_total_gb == 0.0
        assert p.cpu_threads == 0
        assert p.tier == "incompatible"
        assert p.recommended_mode == "tesseract_only"
        assert p.warnings == []

    def test_to_dict(self) -> None:
        p = HardwareProfile(
            gpu_available=True, gpu_name="RTX 3060", gpu_vram_gb=12.0,
            ram_total_gb=32.0, ram_available_gb=24.0,
            cpu_threads=16, cpu_physical_cores=8,
            tier="capable", recommended_mode="hybrid",
            warnings=["test warning"],
        )
        d = p.to_dict()
        assert d["gpu_available"] is True
        assert d["gpu_name"] == "RTX 3060"
        assert d["gpu_vram_gb"] == 12.0
        assert d["ram_total_gb"] == 32.0
        assert d["tier"] == "capable"
        assert d["recommended_mode"] == "hybrid"
        assert d["warnings"] == ["test warning"]


class TestHardwareEvaluator:
    def test_cache_hit(self) -> None:
        HardwareEvaluator._cache = None
        with patch.object(HardwareEvaluator, "_probe") as mock_probe:
            mock_probe.return_value = HardwareProfile(cpu_threads=4)
            p1 = HardwareEvaluator.evaluate(force=True)
            p2 = HardwareEvaluator.evaluate()
            assert mock_probe.call_count == 1
            assert p1 is p2

    def test_cache_bypass_with_force(self) -> None:
        HardwareEvaluator._cache = HardwareProfile(cpu_threads=4)
        with patch.object(HardwareEvaluator, "_probe") as mock_probe:
            mock_probe.return_value = HardwareProfile(cpu_threads=8)
            p = HardwareEvaluator.evaluate(force=True)
            assert mock_probe.call_count == 1
            assert p.cpu_threads == 8

    def test_tier_incompatible_low_ram(self) -> None:
        mock_psutil = MagicMock()
        mock_psutil.cpu_count.return_value = 2
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=int(1.5 * 1024**3), available=int(1.0 * 1024**3)
        )
        mock_settings = MagicMock()
        mock_settings.hybrid_ocr_gpu = False
        mock_settings.hybrid_ocr_min_vram_gb = 2.0
        mock_settings.hybrid_ocr_min_ram_gb = 4.0

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("app.services.hardware_evaluator.settings", mock_settings):
                p = HardwareEvaluator._probe()
                assert p.tier == "incompatible"
                assert p.recommended_mode == "tesseract_only"
                assert any("critically low" in w.lower() for w in p.warnings)

    def test_tier_constrained_no_gpu(self) -> None:
        mock_psutil = MagicMock()
        mock_psutil.cpu_count.return_value = 4
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=int(8.0 * 1024**3), available=int(6.0 * 1024**3)
        )
        mock_settings = MagicMock()
        mock_settings.hybrid_ocr_gpu = True
        mock_settings.hybrid_ocr_min_vram_gb = 2.0
        mock_settings.hybrid_ocr_min_ram_gb = 4.0

        # Mock paddle import to fail (no GPU)
        mock_paddle = MagicMock()
        mock_paddle.device.cuda.device_count.side_effect = Exception("No CUDA")

        with patch.dict(sys.modules, {"psutil": mock_psutil, "paddle": mock_paddle}):
            with patch("app.services.hardware_evaluator.settings", mock_settings):
                p = HardwareEvaluator._probe()
                assert p.tier == "constrained"
                assert p.recommended_mode == "tesseract_only"

    def test_tier_capable_with_gpu(self) -> None:
        mock_psutil = MagicMock()
        mock_psutil.cpu_count.return_value = 8
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=int(16.0 * 1024**3), available=int(12.0 * 1024**3)
        )
        mock_settings = MagicMock()
        mock_settings.hybrid_ocr_gpu = True
        mock_settings.hybrid_ocr_min_vram_gb = 2.0
        mock_settings.hybrid_ocr_min_ram_gb = 4.0

        # Create a proper paddle mock with device.cuda submodule
        mock_cuda = MagicMock()
        mock_cuda.device_count.return_value = 1
        mock_cuda.get_device_properties.return_value = MagicMock(
            total_memory=int(8.0 * 1024**3)
        )
        mock_device = MagicMock()
        mock_device.cuda = mock_cuda
        mock_device.get_device.return_value = "gpu:0"
        mock_paddle = MagicMock()
        mock_paddle.device = mock_device

        with patch.dict(sys.modules, {"psutil": mock_psutil, "paddle": mock_paddle, "paddle.device": mock_device}):
            with patch("app.services.hardware_evaluator.settings", mock_settings):
                p = HardwareEvaluator._probe()
                assert p.tier == "capable"
                assert p.recommended_mode == "hybrid"

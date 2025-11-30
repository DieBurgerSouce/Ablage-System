# -*- coding: utf-8 -*-
"""
Unit-Tests für Backend Manager Service.

Testet:
- Backend-Initialisierung
- Backend-Auswahl (mit A/B-Testing)
- Verarbeitung mit verschiedenen Backends
- Status-Abfragen
- GPU-Fallback-Logik
- Fehlerbehandlung

Feinpoliert und durchdacht - Umfassende Backend-Manager-Tests.
"""

import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import tempfile
import os

import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_surya_agent():
    """Create mock SuryaDoclingAgent."""
    agent = AsyncMock()
    agent.process = AsyncMock(return_value={
        "text": "Extrahierter deutscher Text mit Umlauten: ä, ö, ü",
        "confidence": 0.92,
        "pages": 1
    })
    agent.get_status = Mock(return_value={
        "name": "surya",
        "available": True,
        "gpu": False
    })
    agent.cleanup = AsyncMock()
    return agent


@pytest.fixture
def mock_deepseek_agent():
    """Create mock DeepSeekAgent."""
    agent = AsyncMock()
    agent.process = AsyncMock(return_value={
        "text": "Präziser Text mit Fraktur-Erkennung",
        "confidence": 0.97,
        "pages": 1
    })
    agent.get_status = Mock(return_value={
        "name": "deepseek",
        "available": True,
        "gpu": True,
        "vram_usage_mb": 8000
    })
    agent.cleanup = AsyncMock()
    return agent


@pytest.fixture
def mock_got_ocr_agent():
    """Create mock GOTOCRAgent."""
    agent = AsyncMock()
    agent.process = AsyncMock(return_value={
        "text": "Tabellen und Layout-Text",
        "confidence": 0.94,
        "pages": 1
    })
    agent.get_status = Mock(return_value={
        "name": "got_ocr",
        "available": True,
        "gpu": True,
        "vram_usage_mb": 6000
    })
    agent.cleanup = AsyncMock()
    return agent


@pytest.fixture
def mock_surya_gpu_agent():
    """Create mock SuryaGPUAgent."""
    agent = AsyncMock()
    agent.process = AsyncMock(return_value={
        "text": "GPU-beschleunigter Text",
        "confidence": 0.95,
        "pages": 1
    })
    agent.get_status = Mock(return_value={
        "name": "surya_gpu",
        "available": True,
        "gpu": True,
        "vram_usage_mb": 4000
    })
    agent.cleanup = AsyncMock()
    return agent


@pytest.fixture
def temp_document():
    """Create temporary test document."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 test content")
        temp_path = f.name

    yield Path(temp_path)

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_image():
    """Create temporary test image."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        # Minimal PNG header
        f.write(bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        ]))
        temp_path = f.name

    yield Path(temp_path)

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


# ========================= Backend Initialization Tests =========================


class TestBackendManagerInit:
    """Tests für Backend-Manager Initialisierung."""

    @patch("app.services.backend_manager.TORCH_AVAILABLE", False)
    @patch("app.services.backend_manager.SuryaDoclingAgent")
    def test_init_cpu_only(self, mock_surya_class, mock_surya_agent):
        """Test Initialisierung ohne GPU (nur CPU-Backend)."""
        mock_surya_class.return_value = mock_surya_agent

        from app.services.backend_manager import BackendManager

        manager = BackendManager()

        assert "surya" in manager.backends
        assert "deepseek" not in manager.backends
        assert "got_ocr" not in manager.backends

    @patch("app.services.backend_manager.TORCH_AVAILABLE", True)
    @patch("app.services.backend_manager.SuryaDoclingAgent")
    @patch("app.services.backend_manager.DeepSeekAgent")
    @patch("app.services.backend_manager.GOTOCRAgent")
    def test_init_with_gpu_backends(
        self,
        mock_got_class,
        mock_deepseek_class,
        mock_surya_class,
        mock_surya_agent,
        mock_deepseek_agent,
        mock_got_ocr_agent
    ):
        """Test Initialisierung mit GPU-Backends."""
        mock_surya_class.return_value = mock_surya_agent
        mock_deepseek_class.return_value = mock_deepseek_agent
        mock_got_class.return_value = mock_got_ocr_agent

        from app.services.backend_manager import BackendManager

        manager = BackendManager()

        # All backends should be initialized
        assert "surya" in manager.backends
        assert "deepseek" in manager.backends
        assert "got_ocr" in manager.backends

    @patch("app.services.backend_manager.TORCH_AVAILABLE", True)
    @patch("app.services.backend_manager.SuryaDoclingAgent")
    @patch("app.services.backend_manager.DeepSeekAgent")
    def test_init_partial_gpu_failure(
        self,
        mock_deepseek_class,
        mock_surya_class,
        mock_surya_agent
    ):
        """Test Initialisierung bei teilweisem GPU-Fehler."""
        mock_surya_class.return_value = mock_surya_agent
        mock_deepseek_class.side_effect = Exception("GPU nicht verfügbar")

        from app.services.backend_manager import BackendManager

        # Should not raise - graceful degradation
        manager = BackendManager()

        assert "surya" in manager.backends
        assert "deepseek" not in manager.backends


# ========================= Backend Selection Tests =========================


class TestBackendSelection:
    """Tests für Backend-Auswahl-Logik."""

    @pytest.fixture
    def manager_with_backends(
        self,
        mock_surya_agent,
        mock_deepseek_agent,
        mock_got_ocr_agent
    ):
        """Create manager with mocked backends."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_deepseek_agent
            got_cls.return_value = mock_got_ocr_agent

            from app.services.backend_manager import BackendManager
            manager = BackendManager()
            yield manager

    @pytest.mark.asyncio
    async def test_select_backend_pdf(self, manager_with_backends, temp_document):
        """Test Backend-Auswahl für PDF-Dokumente."""
        backend = await manager_with_backends.select_backend(
            image_path=str(temp_document),
            language="de",
            detect_layout=True
        )

        # Should select an available backend
        assert backend in ["got_ocr", "surya", "deepseek", "surya_gpu"]

    @pytest.mark.asyncio
    async def test_select_backend_german_text(
        self,
        manager_with_backends,
        temp_image
    ):
        """Test Backend-Auswahl für deutschen Text."""
        backend = await manager_with_backends.select_backend(
            image_path=str(temp_image),
            language="de",
            detect_layout=False,
            prefer_gpu=False  # Disable GPU preference for this test
        )

        # DeepSeek should be preferred for German text when no GPU preference
        assert backend in ["deepseek", "surya"]

    @pytest.mark.asyncio
    async def test_select_backend_no_gpu_preference(
        self,
        mock_surya_agent
    ):
        """Test Backend-Auswahl ohne GPU-Präferenz."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", False), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls:

            surya_cls.return_value = mock_surya_agent

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            # Create a temp file for the test
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(b"fake image")
                temp_path = f.name

            try:
                backend = await manager.select_backend(
                    image_path=temp_path,
                    prefer_gpu=False
                )

                assert backend == "surya"
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_select_backend_no_backends_raises(self):
        """Test dass Fehler bei keinen verfügbaren Backends geworfen wird."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", False), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls:

            surya_cls.side_effect = Exception("Init fehlgeschlagen")

            from app.services.backend_manager import BackendManager

            # BackendManager wirft RuntimeError im __init__ wenn keine Backends verfügbar
            with pytest.raises(RuntimeError, match="Kein OCR-Backend"):
                BackendManager()


# ========================= Backend Selection with A/B Testing =========================


class TestBackendSelectionABTesting:
    """Tests für Backend-Auswahl mit A/B-Testing."""

    @pytest.mark.asyncio
    async def test_select_backend_ab_test_active(
        self,
        mock_surya_agent,
        mock_deepseek_agent
    ):
        """Test Backend-Auswahl mit aktivem A/B-Test."""
        mock_experiment = Mock()
        mock_experiment.experiment_id = "exp-001"

        mock_variant = Mock()
        mock_variant.name = "variant_b"
        mock_variant.config = {"backend": "surya"}

        mock_ab_manager = Mock()
        mock_ab_manager.get_active_experiments.return_value = [mock_experiment]
        mock_ab_manager.get_variant.return_value = mock_variant

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent"), \
             patch("app.services.backend_manager.get_ab_test_manager") as mock_ab:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_deepseek_agent
            mock_ab.return_value = mock_ab_manager

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            # Create temp file
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(b"%PDF-1.4 test")
                temp_path = f.name

            try:
                backend = await manager.select_backend(
                    image_path=temp_path,
                    document_id="doc-123"
                )

                # Should use A/B test assigned backend
                assert backend == "surya"
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_select_backend_ab_test_unavailable_backend(
        self,
        mock_surya_agent
    ):
        """Test A/B-Test mit nicht verfügbarem Backend."""
        mock_experiment = Mock()
        mock_experiment.experiment_id = "exp-001"

        mock_variant = Mock()
        mock_variant.name = "variant_gpu"
        mock_variant.config = {"backend": "deepseek"}  # Not available in CPU mode

        mock_ab_manager = Mock()
        mock_ab_manager.get_active_experiments.return_value = [mock_experiment]
        mock_ab_manager.get_variant.return_value = mock_variant

        with patch("app.services.backend_manager.TORCH_AVAILABLE", False), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.get_ab_test_manager") as mock_ab:

            surya_cls.return_value = mock_surya_agent
            mock_ab.return_value = mock_ab_manager

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(b"%PDF-1.4 test")
                temp_path = f.name

            try:
                backend = await manager.select_backend(
                    image_path=temp_path,
                    document_id="doc-123"
                )

                # Should fall back to available backend
                assert backend == "surya"
            finally:
                os.unlink(temp_path)


# ========================= Backend Processing Tests =========================


class TestBackendProcessing:
    """Tests für Verarbeitung mit Backends."""

    @pytest.fixture
    def manager_with_surya(self, mock_surya_agent):
        """Create manager with only Surya backend."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", False), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls:

            surya_cls.return_value = mock_surya_agent

            from app.services.backend_manager import BackendManager
            manager = BackendManager()
            yield manager

    @pytest.mark.asyncio
    async def test_process_with_backend_success(
        self,
        manager_with_surya,
        temp_document
    ):
        """Test erfolgreiche Verarbeitung mit Backend."""
        result = await manager_with_surya.process_with_backend(
            backend_name="surya",
            image_path=str(temp_document),
            language="de"
        )

        assert "text" in result
        assert result["backend"] == "surya"
        assert "Umlauten" in result["text"]

    @pytest.mark.asyncio
    async def test_process_with_invalid_backend_raises(
        self,
        manager_with_surya,
        temp_document
    ):
        """Test Fehler bei ungültigem Backend."""
        with pytest.raises(ValueError, match="nicht verfügbar"):
            await manager_with_surya.process_with_backend(
                backend_name="nonexistent",
                image_path=str(temp_document)
            )

    @pytest.mark.asyncio
    async def test_process_with_fraktur_detection(
        self,
        mock_surya_agent
    ):
        """Test Verarbeitung mit Fraktur-Erkennung."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", False), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls:

            surya_cls.return_value = mock_surya_agent

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as f:
                f.write(b"fake tiff")
                temp_path = f.name

            try:
                result = await manager.process_with_backend(
                    backend_name="surya",
                    image_path=temp_path,
                    language="de",
                    detect_fraktur=True
                )

                # Verify fraktur flag was passed
                mock_surya_agent.process.assert_called_once()
                call_args = mock_surya_agent.process.call_args[0][0]
                assert call_args["detect_fraktur"] is True
            finally:
                os.unlink(temp_path)


# ========================= Backend Status Tests =========================


class TestBackendStatus:
    """Tests für Backend-Status-Abfragen."""

    @pytest.fixture
    def manager_with_multiple_backends(
        self,
        mock_surya_agent,
        mock_deepseek_agent
    ):
        """Create manager with multiple backends."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_deepseek_agent
            got_cls.side_effect = Exception("Init failed")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()
            yield manager

    @pytest.mark.asyncio
    async def test_get_backend_status_single(
        self,
        manager_with_multiple_backends
    ):
        """Test Status-Abfrage für einzelnes Backend."""
        status = await manager_with_multiple_backends.get_backend_status("surya")

        assert status["name"] == "surya"
        assert status["available"] is True
        assert status["gpu"] is False

    @pytest.mark.asyncio
    async def test_get_backend_status_all(
        self,
        manager_with_multiple_backends
    ):
        """Test Status-Abfrage für alle Backends."""
        status = await manager_with_multiple_backends.get_backend_status()

        assert "surya" in status
        assert "deepseek" in status
        assert "got_ocr" not in status

    @pytest.mark.asyncio
    async def test_get_backend_status_nonexistent(
        self,
        manager_with_multiple_backends
    ):
        """Test Status-Abfrage für nicht existierendes Backend."""
        status = await manager_with_multiple_backends.get_backend_status("fake")

        assert "error" in status

    def test_get_available_backends(self, manager_with_multiple_backends):
        """Test Abruf verfügbarer Backends."""
        backends = manager_with_multiple_backends.get_available_backends()

        assert isinstance(backends, list)
        assert "surya" in backends
        assert "deepseek" in backends


# ========================= Backend Cleanup Tests =========================


class TestBackendCleanup:
    """Tests für Backend-Cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_all_backends(
        self,
        mock_surya_agent,
        mock_deepseek_agent
    ):
        """Test Cleanup aller Backends."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_deepseek_agent
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            await manager.cleanup()

            mock_surya_agent.cleanup.assert_called_once()
            mock_deepseek_agent.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_failure(self, mock_surya_agent):
        """Test Cleanup bei Fehler in einem Backend."""
        mock_surya_agent.cleanup.side_effect = Exception("Cleanup fehlgeschlagen")

        with patch("app.services.backend_manager.TORCH_AVAILABLE", False), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls:

            surya_cls.return_value = mock_surya_agent

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            # Should not raise - logs error but continues
            await manager.cleanup()

            mock_surya_agent.cleanup.assert_called_once()


# ========================= Edge Cases =========================


# ========================= Health Check Tests =========================


class TestBackendHealthCheck:
    """Tests für Backend-Gesundheitsprüfung."""

    @pytest.fixture
    def manager_with_gpu_backend(self, mock_surya_agent, mock_deepseek_agent):
        """Create manager with GPU backend for health tests."""
        # Configure deepseek as GPU backend with status
        # VRAM check: available_gb (16-2=14) must be >= vram_gb * 0.85 (12*0.85=10.2)
        mock_deepseek_agent.get_status = Mock(return_value={
            "name": "deepseek",
            "available": True,
            "gpu_required": True,
            "vram_gb": 12,
            "gpu_info": {
                "available": True,
                "total_memory_gb": 16.0,
                "allocated_memory_gb": 2.0  # 14GB available > 10.2GB required
            }
        })

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_deepseek_agent
            got_cls.side_effect = Exception("Not available")

            # Also patch SuryaGPUAgent to prevent real GPU initialization
            with patch.dict('sys.modules', {'app.agents.ocr.surya_gpu_agent': MagicMock()}):
                from app.services.backend_manager import BackendManager
                manager = BackendManager()
                yield manager

    @pytest.mark.asyncio
    async def test_check_backend_health_healthy(self, manager_with_gpu_backend):
        """Test Gesundheitsprüfung für gesundes Backend."""
        health = await manager_with_gpu_backend.check_backend_health("deepseek")

        assert health["healthy"] is True
        assert "status" in health

    @pytest.mark.asyncio
    async def test_check_backend_health_nonexistent(self, manager_with_gpu_backend):
        """Test Gesundheitsprüfung für nicht existierendes Backend."""
        health = await manager_with_gpu_backend.check_backend_health("fake_backend")

        assert health["healthy"] is False
        assert "Backend not found" in health["reason"]

    @pytest.mark.asyncio
    async def test_check_backend_health_gpu_unavailable(self, mock_surya_agent):
        """Test Gesundheitsprüfung bei nicht verfügbarer GPU."""
        mock_gpu_backend = AsyncMock()
        mock_gpu_backend.get_status = Mock(return_value={
            "name": "gpu_backend",
            "gpu_required": True,
            "vram_gb": 12,
            "gpu_info": {
                "available": False
            }
        })

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_gpu_backend
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            health = await manager.check_backend_health("deepseek")

            assert health["healthy"] is False
            assert "GPU" in health["reason"]

    @pytest.mark.asyncio
    async def test_check_backend_health_insufficient_vram(self, mock_surya_agent):
        """Test Gesundheitsprüfung bei unzureichendem VRAM."""
        mock_gpu_backend = AsyncMock()
        mock_gpu_backend.get_status = Mock(return_value={
            "name": "gpu_backend",
            "gpu_required": True,
            "vram_gb": 12,
            "gpu_info": {
                "available": True,
                "total_memory_gb": 16.0,
                "allocated_memory_gb": 14.0  # Only 2GB free, need 12GB
            }
        })

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_gpu_backend
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            health = await manager.check_backend_health("deepseek")

            assert health["healthy"] is False
            assert "VRAM" in health["reason"]

    @pytest.mark.asyncio
    async def test_check_backend_health_exception_handling(self, mock_surya_agent):
        """Test Gesundheitsprüfung bei Exception im Backend."""
        mock_error_backend = AsyncMock()
        mock_error_backend.get_status = Mock(side_effect=Exception("Status error"))

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_error_backend
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            health = await manager.check_backend_health("deepseek")

            assert health["healthy"] is False
            assert "Status error" in health["reason"]


# ========================= Fallback Order Tests =========================


class TestFallbackOrder:
    """Tests für Fallback-Reihenfolge."""

    @pytest.fixture
    def manager_with_all_backends(
        self,
        mock_surya_agent,
        mock_deepseek_agent,
        mock_got_ocr_agent,
        mock_surya_gpu_agent
    ):
        """Create manager with all backends for fallback tests."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.torch") as mock_torch, \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.get_device_name.return_value = "RTX 4080"

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_deepseek_agent
            got_cls.return_value = mock_got_ocr_agent

            # Also mock the GPU surya import
            with patch.dict('sys.modules', {'app.agents.ocr.surya_gpu_agent': MagicMock()}):
                with patch("app.services.backend_manager.SuryaGPUAgent", create=True) as surya_gpu_cls:
                    surya_gpu_cls.return_value = mock_surya_gpu_agent

                    from app.services.backend_manager import BackendManager
                    manager = BackendManager()
                    # Manually add surya_gpu for testing
                    manager.backends["surya_gpu"] = mock_surya_gpu_agent
                    yield manager

    def test_fallback_order_preferred_first(self, manager_with_all_backends):
        """Test dass bevorzugtes Backend zuerst kommt."""
        order = manager_with_all_backends.get_fallback_order("got_ocr")

        assert order[0] == "got_ocr"

    def test_fallback_order_priority(self, manager_with_all_backends):
        """Test Prioritätsreihenfolge der Backends."""
        order = manager_with_all_backends.get_fallback_order("surya")

        # surya should be first (preferred)
        assert order[0] == "surya"

        # deepseek should come before got_ocr (priority order)
        deepseek_idx = order.index("deepseek")
        got_idx = order.index("got_ocr")
        assert deepseek_idx < got_idx

    def test_fallback_order_missing_backend(self, mock_surya_agent):
        """Test Fallback-Reihenfolge wenn bevorzugtes Backend fehlt."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", False), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls:

            surya_cls.return_value = mock_surya_agent

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            order = manager.get_fallback_order("deepseek")

            # deepseek not available, should fallback to surya
            assert "deepseek" not in order
            assert "surya" in order

    def test_fallback_order_all_backends_included(self, manager_with_all_backends):
        """Test dass alle verfügbaren Backends in der Fallback-Kette sind."""
        order = manager_with_all_backends.get_fallback_order("surya")

        available = manager_with_all_backends.get_available_backends()
        for backend in available:
            assert backend in order


# ========================= Process with Fallback Tests =========================


class TestProcessWithFallback:
    """Tests für Verarbeitung mit Fallback-Logik."""

    @pytest.fixture
    def manager_with_fallback_backends(self, mock_surya_agent, mock_deepseek_agent):
        """Create manager for fallback processing tests."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_deepseek_agent
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()
            yield manager, mock_surya_agent, mock_deepseek_agent

    @pytest.mark.asyncio
    async def test_process_with_fallback_success(
        self,
        manager_with_fallback_backends,
        temp_document
    ):
        """Test erfolgreiche Verarbeitung ohne Fallback."""
        manager, mock_surya, mock_deepseek = manager_with_fallback_backends

        result = await manager.process_with_backend(
            backend_name="surya",
            image_path=str(temp_document),
            enable_fallback=True
        )

        assert result["backend"] == "surya"
        assert "fallback_used" not in result

    @pytest.mark.asyncio
    async def test_process_with_fallback_triggered(
        self,
        mock_surya_agent
    ):
        """Test Fallback bei Fehler im primären Backend."""
        # Configure first backend to fail, second to succeed
        mock_failing_backend = AsyncMock()
        mock_failing_backend.process = AsyncMock(side_effect=Exception("Processing failed"))
        mock_failing_backend.get_status = Mock(return_value={
            "name": "deepseek",
            "gpu_required": False
        })
        mock_failing_backend.cleanup = AsyncMock()

        mock_surya_agent.get_status = Mock(return_value={
            "name": "surya",
            "gpu_required": False
        })

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_failing_backend
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(b"%PDF-1.4 test")
                temp_path = f.name

            try:
                result = await manager.process_with_backend(
                    backend_name="deepseek",
                    image_path=temp_path,
                    enable_fallback=True
                )

                # Should have used fallback
                assert result["fallback_used"] is True
                assert result["original_backend"] == "deepseek"
                assert result["backend"] == "surya"
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_process_without_fallback_raises(self, mock_surya_agent):
        """Test dass ohne Fallback Fehler geworfen wird."""
        mock_failing_backend = AsyncMock()
        mock_failing_backend.process = AsyncMock(side_effect=Exception("Processing failed"))
        mock_failing_backend.get_status = Mock(return_value={
            "name": "deepseek",
            "gpu_required": False
        })

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_failing_backend
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(b"%PDF-1.4 test")
                temp_path = f.name

            try:
                with pytest.raises(RuntimeError, match="Alle OCR-Backends fehlgeschlagen"):
                    await manager.process_with_backend(
                        backend_name="deepseek",
                        image_path=temp_path,
                        enable_fallback=False
                    )
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_process_skips_unhealthy_backends(self, mock_surya_agent):
        """Test dass ungesunde Backends übersprungen werden."""
        # Configure deepseek as unhealthy (GPU not available)
        mock_unhealthy_backend = AsyncMock()
        mock_unhealthy_backend.get_status = Mock(return_value={
            "name": "deepseek",
            "gpu_required": True,
            "vram_gb": 12,
            "gpu_info": {
                "available": False
            }
        })

        mock_surya_agent.get_status = Mock(return_value={
            "name": "surya",
            "gpu_required": False
        })

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_unhealthy_backend
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(b"%PDF-1.4 test")
                temp_path = f.name

            try:
                result = await manager.process_with_backend(
                    backend_name="deepseek",
                    image_path=temp_path,
                    enable_fallback=True
                )

                # Should skip unhealthy deepseek and use surya
                assert result["fallback_used"] is True
                assert result["backend"] == "surya"
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_all_backends_fail_raises(self, mock_surya_agent):
        """Test dass Fehler geworfen wird wenn alle Backends fehlschlagen."""
        # Both backends fail
        mock_failing_backend1 = AsyncMock()
        mock_failing_backend1.process = AsyncMock(side_effect=Exception("Failed 1"))
        mock_failing_backend1.get_status = Mock(return_value={"gpu_required": False})

        mock_failing_backend2 = AsyncMock()
        mock_failing_backend2.process = AsyncMock(side_effect=Exception("Failed 2"))
        mock_failing_backend2.get_status = Mock(return_value={"gpu_required": False})

        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_failing_backend1
            deepseek_cls.return_value = mock_failing_backend2
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(b"%PDF-1.4 test")
                temp_path = f.name

            try:
                with pytest.raises(RuntimeError, match="Alle OCR-Backends fehlgeschlagen"):
                    await manager.process_with_backend(
                        backend_name="surya",
                        image_path=temp_path,
                        enable_fallback=True
                    )
            finally:
                os.unlink(temp_path)


# ========================= Edge Cases =========================


class TestBackendManagerEdgeCases:
    """Tests für Grenzfälle."""

    @pytest.mark.asyncio
    async def test_select_backend_large_file(self, mock_surya_agent, mock_deepseek_agent):
        """Test Backend-Auswahl für große Dateien."""
        with patch("app.services.backend_manager.TORCH_AVAILABLE", True), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls, \
             patch("app.services.backend_manager.DeepSeekAgent") as deepseek_cls, \
             patch("app.services.backend_manager.GOTOCRAgent") as got_cls:

            surya_cls.return_value = mock_surya_agent
            deepseek_cls.return_value = mock_deepseek_agent
            got_cls.side_effect = Exception("Not available")

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            # Create a "large" file (> 5MB check in select_backend)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                # Write > 5MB of data
                f.write(b"x" * (6 * 1024 * 1024))
                temp_path = f.name

            try:
                backend = await manager.select_backend(
                    image_path=temp_path,
                    detect_layout=True,
                    prefer_gpu=False  # Disable surya_gpu preference
                )

                # DeepSeek should be preferred for large complex documents when no GPU preference
                assert backend in ["deepseek", "surya"]
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_async_status_handling(self, mock_surya_agent):
        """Test Handling von asynchronen Status-Methoden."""
        # Make get_status return a coroutine
        async def async_status():
            return {"name": "surya", "async": True}

        mock_surya_agent.get_status = async_status

        with patch("app.services.backend_manager.TORCH_AVAILABLE", False), \
             patch("app.services.backend_manager.SuryaDoclingAgent") as surya_cls:

            surya_cls.return_value = mock_surya_agent

            from app.services.backend_manager import BackendManager
            manager = BackendManager()

            status = await manager.get_backend_status("surya")

            assert status["async"] is True

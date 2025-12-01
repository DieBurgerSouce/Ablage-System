# -*- coding: utf-8 -*-
"""
Unit Tests fuer Model Pre-Loading Service.

Testet:
- PreloadConfig Konstanten
- PreloadStatus Enum
- ModelPreloader Singleton
- Model-Loading mit Timeout
- GPU/VRAM-Pruefung
- Status-Ermittlung
- Cleanup
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.model_preloader import (
    PreloadStatus,
    PreloadConfig,
    ModelPreloader,
    get_model_preloader,
    preload_ocr_models,
)


class TestPreloadStatus:
    """Tests fuer PreloadStatus Enum."""

    def test_all_status_values_defined(self):
        """Alle Status-Werte sind definiert."""
        assert PreloadStatus.PENDING == "pending"
        assert PreloadStatus.LOADING == "loading"
        assert PreloadStatus.LOADED == "loaded"
        assert PreloadStatus.FAILED == "failed"
        assert PreloadStatus.SKIPPED == "skipped"


class TestPreloadConfig:
    """Tests fuer PreloadConfig."""

    def test_default_models_defined(self):
        """Standard-Modelle sind definiert."""
        assert len(PreloadConfig.DEFAULT_PRELOAD_MODELS) > 0
        assert "surya_docling" in PreloadConfig.DEFAULT_PRELOAD_MODELS

    def test_gpu_models_defined(self):
        """GPU-Modelle sind definiert."""
        assert len(PreloadConfig.GPU_PRELOAD_MODELS) > 0

    def test_timeout_positive(self):
        """Timeout ist positiv."""
        assert PreloadConfig.MODEL_LOAD_TIMEOUT_SECONDS > 0

    def test_min_vram_positive(self):
        """Min-VRAM ist positiv."""
        assert PreloadConfig.MIN_FREE_VRAM_GB > 0


class TestModelPreloaderSingleton:
    """Tests fuer ModelPreloader Singleton."""

    def test_get_instance_returns_same_instance(self):
        """get_instance() gibt gleiche Instanz zurueck."""
        # Reset singleton for test
        ModelPreloader._instance = None

        instance1 = ModelPreloader.get_instance()
        instance2 = ModelPreloader.get_instance()

        assert instance1 is instance2

    def test_new_instance_has_empty_status(self):
        """Neue Instanz hat leeren Status."""
        # Reset singleton
        ModelPreloader._instance = None

        preloader = ModelPreloader.get_instance()

        assert preloader._status == {}
        assert preloader._load_times == {}
        assert preloader._errors == {}
        assert preloader._preload_started is False
        assert preloader._preload_completed is False


class TestModelPreloaderPreload:
    """Tests fuer preload_models()."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        ModelPreloader._instance = None
        yield
        ModelPreloader._instance = None

    @pytest.mark.asyncio
    async def test_disabled_preload_returns_empty(self):
        """Deaktiviertes Preload gibt leeres Dict zurueck."""
        preloader = ModelPreloader.get_instance()

        with patch.object(PreloadConfig, 'ENABLED', False):
            result = await preloader.preload_models()

        assert result == {}

    @pytest.mark.asyncio
    @patch.object(ModelPreloader, '_check_gpu_available', return_value=False)
    @patch.object(ModelPreloader, '_load_single_model')
    async def test_loads_default_models_without_gpu(self, mock_load, mock_gpu):
        """Laedt Standard-Modelle ohne GPU."""
        mock_load.return_value = None
        preloader = ModelPreloader.get_instance()

        result = await preloader.preload_models(include_gpu_models=True)

        # Sollte nur Default-Modelle laden wenn keine GPU
        loaded_models = [call[0][0] for call in mock_load.call_args_list]
        assert "surya_docling" in loaded_models
        # GPU-Modelle sollten nicht dabei sein
        for gpu_model in PreloadConfig.GPU_PRELOAD_MODELS:
            assert gpu_model not in loaded_models

    @pytest.mark.asyncio
    @patch.object(ModelPreloader, '_check_gpu_available', return_value=True)
    @patch.object(ModelPreloader, '_load_single_model')
    async def test_loads_gpu_models_with_gpu(self, mock_load, mock_gpu):
        """Laedt GPU-Modelle wenn GPU verfuegbar."""
        mock_load.return_value = None
        preloader = ModelPreloader.get_instance()

        result = await preloader.preload_models(include_gpu_models=True)

        # Sollte auch GPU-Modelle laden
        loaded_models = [call[0][0] for call in mock_load.call_args_list]
        assert "surya_docling" in loaded_models
        # Mindestens ein GPU-Modell sollte dabei sein
        gpu_loaded = any(m in loaded_models for m in PreloadConfig.GPU_PRELOAD_MODELS)
        assert gpu_loaded

    @pytest.mark.asyncio
    @patch.object(ModelPreloader, '_load_single_model')
    async def test_specific_models_only(self, mock_load):
        """Laedt nur spezifizierte Modelle."""
        mock_load.return_value = None
        preloader = ModelPreloader.get_instance()

        result = await preloader.preload_models(models=["got_ocr"])

        # Sollte nur got_ocr laden
        assert mock_load.call_count == 1
        mock_load.assert_called_with("got_ocr")

    @pytest.mark.asyncio
    @patch.object(ModelPreloader, '_load_single_model')
    async def test_deduplicates_models(self, mock_load):
        """Dedupliziert Modell-Liste."""
        mock_load.return_value = None
        preloader = ModelPreloader.get_instance()

        result = await preloader.preload_models(models=["got_ocr", "got_ocr", "got_ocr"])

        # Sollte nur einmal laden
        assert mock_load.call_count == 1

    @pytest.mark.asyncio
    @patch.object(ModelPreloader, '_load_single_model')
    async def test_background_loading_returns_immediately(self, mock_load):
        """Background-Loading gibt sofort zurueck."""
        # Verzoegerung im Loading
        async def slow_load(model):
            await asyncio.sleep(1)

        mock_load.side_effect = slow_load
        preloader = ModelPreloader.get_instance()

        start = asyncio.get_event_loop().time()
        result = await preloader.preload_models(
            models=["surya_docling"],
            background=True
        )
        duration = asyncio.get_event_loop().time() - start

        # Sollte sofort zurueckkehren (nicht 1s warten)
        assert duration < 0.5
        assert result["surya_docling"] == PreloadStatus.LOADING

    @pytest.mark.asyncio
    @patch.object(ModelPreloader, '_load_single_model')
    async def test_sets_preload_flags(self, mock_load):
        """Setzt Preload-Flags korrekt."""
        mock_load.return_value = None
        preloader = ModelPreloader.get_instance()

        assert preloader._preload_started is False
        assert preloader._preload_completed is False

        await preloader.preload_models(models=["surya_docling"])

        assert preloader._preload_started is True
        assert preloader._preload_completed is True


class TestModelPreloaderLoadSingleModel:
    """Tests fuer _load_single_model()."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        ModelPreloader._instance = None
        yield
        ModelPreloader._instance = None

    @pytest.mark.asyncio
    async def test_unknown_model_skipped(self):
        """Unbekannte Modelle werden uebersprungen."""
        preloader = ModelPreloader.get_instance()

        await preloader._load_single_model("unknown_model")

        assert preloader._status.get("unknown_model") == PreloadStatus.SKIPPED


class TestModelPreloaderTimeout:
    """Tests fuer Timeout-Handling."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        ModelPreloader._instance = None
        yield
        ModelPreloader._instance = None

    @pytest.mark.asyncio
    @patch.object(PreloadConfig, 'MODEL_LOAD_TIMEOUT_SECONDS', 0.1)
    async def test_timeout_marks_as_failed(self):
        """Timeout markiert Model als fehlgeschlagen."""
        preloader = ModelPreloader.get_instance()

        # Mock langsames Loading
        async def slow_load(model):
            await asyncio.sleep(10)

        with patch.object(preloader, '_load_single_model', slow_load):
            result = await preloader._preload_all(["slow_model"])

        assert result["slow_model"] == PreloadStatus.FAILED
        assert "Timeout" in preloader._errors.get("slow_model", "")


class TestModelPreloaderGPUCheck:
    """Tests fuer GPU/VRAM-Pruefung."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        ModelPreloader._instance = None
        yield
        ModelPreloader._instance = None

    def test_gpu_check_returns_boolean(self):
        """GPU-Check gibt boolean zurueck."""
        preloader = ModelPreloader.get_instance()
        result = preloader._check_gpu_available()
        assert isinstance(result, bool)

    def test_vram_check_returns_boolean(self):
        """VRAM-Check gibt boolean zurueck."""
        preloader = ModelPreloader.get_instance()
        result = preloader._check_vram_available(8.0)
        assert isinstance(result, bool)

    def test_vram_check_with_high_requirement_returns_false(self):
        """VRAM-Check mit hoher Anforderung gibt False zurueck."""
        preloader = ModelPreloader.get_instance()
        # 1000GB - sollte auf jeder Hardware False geben
        result = preloader._check_vram_available(1000.0)
        assert result is False


class TestModelPreloaderStatus:
    """Tests fuer get_status()."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        ModelPreloader._instance = None
        yield
        ModelPreloader._instance = None

    def test_status_structure(self):
        """Status hat korrekte Struktur."""
        preloader = ModelPreloader.get_instance()
        status = preloader.get_status()

        assert "enabled" in status
        assert "preload_started" in status
        assert "preload_completed" in status
        assert "models" in status
        assert "summary" in status

    def test_summary_counts_correct(self):
        """Summary-Zaehler sind korrekt."""
        preloader = ModelPreloader.get_instance()

        # Simuliere verschiedene Status
        preloader._status = {
            "model1": PreloadStatus.LOADED,
            "model2": PreloadStatus.LOADED,
            "model3": PreloadStatus.FAILED,
            "model4": PreloadStatus.SKIPPED,
        }

        status = preloader.get_status()

        assert status["summary"]["total"] == 4
        assert status["summary"]["loaded"] == 2
        assert status["summary"]["failed"] == 1
        assert status["summary"]["skipped"] == 1


class TestModelPreloaderHelpers:
    """Tests fuer Helper-Funktionen."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        ModelPreloader._instance = None
        yield
        ModelPreloader._instance = None

    def test_is_model_loaded_true(self):
        """is_model_loaded() gibt True zurueck wenn geladen."""
        preloader = ModelPreloader.get_instance()
        preloader._status["test_model"] = PreloadStatus.LOADED

        assert preloader.is_model_loaded("test_model") is True

    def test_is_model_loaded_false(self):
        """is_model_loaded() gibt False zurueck wenn nicht geladen."""
        preloader = ModelPreloader.get_instance()
        preloader._status["test_model"] = PreloadStatus.FAILED

        assert preloader.is_model_loaded("test_model") is False

    def test_is_model_loaded_unknown(self):
        """is_model_loaded() gibt False zurueck fuer unbekannte Models."""
        preloader = ModelPreloader.get_instance()

        assert preloader.is_model_loaded("unknown") is False

    def test_get_preloaded_agent_returns_agent(self):
        """get_preloaded_agent() gibt Agent zurueck."""
        preloader = ModelPreloader.get_instance()
        mock_agent = MagicMock()
        preloader._loaded_agents["test_model"] = mock_agent

        result = preloader.get_preloaded_agent("test_model")

        assert result is mock_agent

    def test_get_preloaded_agent_returns_none(self):
        """get_preloaded_agent() gibt None zurueck wenn nicht vorhanden."""
        preloader = ModelPreloader.get_instance()

        result = preloader.get_preloaded_agent("unknown")

        assert result is None


class TestModelPreloaderCleanup:
    """Tests fuer cleanup()."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        ModelPreloader._instance = None
        yield
        ModelPreloader._instance = None

    @pytest.mark.asyncio
    async def test_cleanup_calls_agent_cleanup(self):
        """cleanup() ruft Agent-Cleanup auf."""
        preloader = ModelPreloader.get_instance()

        mock_agent = MagicMock()
        mock_agent.cleanup = AsyncMock()
        preloader._loaded_agents["test_model"] = mock_agent
        preloader._status["test_model"] = PreloadStatus.LOADED
        preloader._load_times["test_model"] = 1.5
        preloader._preload_started = True
        preloader._preload_completed = True

        await preloader.cleanup()

        mock_agent.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_clears_all_state(self):
        """cleanup() loescht allen State."""
        preloader = ModelPreloader.get_instance()

        preloader._status["test"] = PreloadStatus.LOADED
        preloader._load_times["test"] = 1.0
        preloader._errors["test"] = "error"
        preloader._loaded_agents["test"] = MagicMock()
        preloader._preload_started = True
        preloader._preload_completed = True

        await preloader.cleanup()

        assert preloader._status == {}
        assert preloader._load_times == {}
        assert preloader._errors == {}
        assert preloader._loaded_agents == {}
        assert preloader._preload_started is False
        assert preloader._preload_completed is False

    @pytest.mark.asyncio
    async def test_cleanup_handles_agent_error(self):
        """cleanup() behandelt Agent-Fehler graceful."""
        preloader = ModelPreloader.get_instance()

        mock_agent = MagicMock()
        mock_agent.cleanup = AsyncMock(side_effect=Exception("Cleanup failed"))
        preloader._loaded_agents["test_model"] = mock_agent

        # Sollte nicht werfen
        await preloader.cleanup()

        # State sollte trotzdem geloescht sein
        assert preloader._loaded_agents == {}


class TestConvenienceFunctions:
    """Tests fuer Convenience-Funktionen."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        ModelPreloader._instance = None
        yield
        ModelPreloader._instance = None

    def test_get_model_preloader_returns_singleton(self):
        """get_model_preloader() gibt Singleton zurueck."""
        preloader1 = get_model_preloader()
        preloader2 = get_model_preloader()

        assert preloader1 is preloader2

    @pytest.mark.asyncio
    @patch.object(ModelPreloader, 'preload_models')
    async def test_preload_ocr_models_calls_preloader(self, mock_preload):
        """preload_ocr_models() ruft Preloader auf."""
        mock_preload.return_value = {"surya_docling": PreloadStatus.LOADED}

        result = await preload_ocr_models(include_gpu=False, background=True)

        mock_preload.assert_called_once_with(
            include_gpu_models=False,
            background=True
        )

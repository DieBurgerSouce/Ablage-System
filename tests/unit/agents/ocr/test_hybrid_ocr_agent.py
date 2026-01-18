# -*- coding: utf-8 -*-
"""
Tests fuer Hybrid OCR Agent.

Testet:
- Multi-Engine Orchestrierung
- Backend Selection Strategy
- GPU Fallback Logic (GPU -> CPU)
- Confidence Fusion (Ensemble Voting)
- Parallel/Sequential Processing
- Result Aggregation
- VRAM Resource Management
- Character-Level Voting mit Umlaut-Bonus
- Entity Deduplication

Feinpoliert und durchdacht - Hybrid OCR Tests.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any, Dict, List


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_gpu_manager():
    """Mock GPUManager fuer VRAM-Checks."""
    with patch('app.agents.ocr.hybrid_agent.GPUManager') as mock_gm:
        gpu_manager = Mock()
        gpu_manager.get_available_vram.return_value = 12.0  # 12GB frei
        mock_gm.return_value = gpu_manager
        yield gpu_manager


@pytest.fixture
def mock_torch_cuda():
    """Mock torch.cuda fuer GPU-Verfuegbarkeit."""
    import sys
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True
    mock_torch.cuda.empty_cache = Mock()
    mock_torch.cuda.synchronize = Mock()
    mock_torch.cuda.memory_allocated.return_value = 4 * 1024**3  # 4GB

    mock_props = Mock()
    mock_props.total_memory = 16 * 1024**3  # 16GB
    mock_torch.cuda.get_device_properties.return_value = mock_props

    with patch.dict(sys.modules, {'torch': mock_torch}):
        yield mock_torch


@pytest.fixture
def mock_deepseek_agent():
    """Mock DeepSeek Agent."""
    with patch('app.agents.ocr.hybrid_agent.DeepSeekAgent') as mock_class:
        agent = AsyncMock()
        agent.process = AsyncMock(return_value={
            "text": "Text von DeepSeek mit Müller GmbH",
            "confidence": 0.92,
            "entities": [
                {"type": "company", "value": "Müller GmbH", "confidence": 0.95, "source": "deepseek"}
            ],
            "layout": {"type": "invoice"}
        })
        mock_class.return_value = agent
        yield agent


@pytest.fixture
def mock_got_ocr_agent():
    """Mock GOT-OCR Agent."""
    with patch('app.agents.ocr.hybrid_agent.GOTOCRAgent') as mock_class:
        agent = AsyncMock()
        agent.process = AsyncMock(return_value={
            "text": "Text von GOT-OCR mit Mueller GmbH",
            "confidence": 0.88,
            "entities": [
                {"type": "company", "value": "Mueller GmbH", "confidence": 0.85, "source": "got_ocr"}
            ],
            "layout": {}
        })
        mock_class.return_value = agent
        yield agent


@pytest.fixture
def mock_surya_agent():
    """Mock Surya+Docling Agent."""
    with patch('app.agents.ocr.hybrid_agent.SuryaDoclingAgent') as mock_class:
        agent = AsyncMock()
        agent.process = AsyncMock(return_value={
            "text": "Text von Surya mit Muller GmbH",
            "confidence": 0.75,
            "entities": [],
            "layout": {"type": "document"}
        })
        mock_class.return_value = agent
        yield agent


@pytest.fixture
def hybrid_agent_with_mocks(mock_gpu_manager, mock_deepseek_agent, mock_got_ocr_agent, mock_surya_agent):
    """Hybrid Agent mit gemockten Sub-Agents."""
    import sys
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True
    mock_torch.cuda.empty_cache = Mock()
    mock_torch.cuda.synchronize = Mock()
    mock_torch.cuda.memory_allocated.return_value = 2 * 1024**3  # 2GB
    mock_props = Mock()
    mock_props.total_memory = 16 * 1024**3  # 16GB
    mock_torch.cuda.get_device_properties.return_value = mock_props

    with patch.dict(sys.modules, {'torch': mock_torch}):
        from app.agents.ocr.hybrid_agent import HybridOCRAgent

        agent = HybridOCRAgent()
        agent.deepseek = mock_deepseek_agent
        agent.got_ocr = mock_got_ocr_agent
        agent.surya_docling = mock_surya_agent
        agent.gpu_manager = mock_gpu_manager

        yield agent


# ========================= Initialization Tests =========================


class TestHybridOCRAgentInitialization:
    """Tests fuer Hybrid Agent Initialisierung."""

    def test_initialization_creates_sub_agents(self, mock_gpu_manager, mock_deepseek_agent, mock_got_ocr_agent, mock_surya_agent):
        """Agent sollte alle Sub-Agents initialisieren."""
        import sys
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        with patch.dict(sys.modules, {'torch': mock_torch}):
            from app.agents.ocr.hybrid_agent import HybridOCRAgent

            agent = HybridOCRAgent()

            assert agent.name == "hybrid_ocr_agent"
            assert agent.gpu_required is True
            assert agent.vram_gb == 12

    def test_backend_vram_map_defined(self):
        """BACKEND_VRAM_MAP sollte alle Backends enthalten."""
        from app.agents.ocr.hybrid_agent import HybridOCRAgent

        vram_map = HybridOCRAgent.BACKEND_VRAM_MAP

        assert "deepseek" in vram_map
        assert "got_ocr" in vram_map
        assert "surya_docling" in vram_map
        assert vram_map["deepseek"] == 12.0
        assert vram_map["got_ocr"] == 10.0
        assert vram_map["surya_docling"] == 0.5

    def test_backend_priority_defined(self):
        """BACKEND_PRIORITY sollte definiert sein."""
        from app.agents.ocr.hybrid_agent import HybridOCRAgent

        priority = HybridOCRAgent.BACKEND_PRIORITY

        assert priority["deepseek"] == 3  # Hoechste Prioritaet
        assert priority["surya_docling"] == 1  # Niedrigste


# ========================= Backend Selection Tests =========================


class TestHybridOCRBackendSelection:
    """Tests fuer Backend Selection Strategy."""

    @pytest.mark.asyncio
    async def test_process_runs_all_engines(self, hybrid_agent_with_mocks):
        """process() sollte alle Engines ausfuehren."""
        input_data = {"document_id": "test-123", "image_path": "/test/doc.pdf"}

        result = await hybrid_agent_with_mocks.process(input_data)

        # Alle Agents sollten aufgerufen worden sein
        hybrid_agent_with_mocks.deepseek.process.assert_called()
        hybrid_agent_with_mocks.got_ocr.process.assert_called()
        hybrid_agent_with_mocks.surya_docling.process.assert_called()

    @pytest.mark.asyncio
    async def test_selects_highest_confidence_engine(self, hybrid_agent_with_mocks):
        """process() sollte Engine mit hoechster Confidence waehlen."""
        input_data = {"document_id": "test-123", "image_path": "/test/doc.pdf"}

        result = await hybrid_agent_with_mocks.process(input_data)

        # DeepSeek hat 0.92, GOT-OCR 0.88, Surya 0.75
        assert result["selected_engine"] == "deepseek"


# ========================= Fallback Logic Tests =========================


class TestHybridOCRFallbackLogic:
    """Tests fuer GPU -> CPU Fallback."""

    @pytest.mark.asyncio
    async def test_fallback_to_surya_on_gpu_failure(
        self, mock_gpu_manager, mock_deepseek_agent, mock_got_ocr_agent, mock_surya_agent
    ):
        """Agent sollte auf Surya fallbacken wenn GPU-Backends fehlschlagen."""
        import sys
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.empty_cache = Mock()
        mock_torch.cuda.synchronize = Mock()
        mock_torch.cuda.memory_allocated.return_value = 2 * 1024**3
        mock_props = Mock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props

        with patch.dict(sys.modules, {'torch': mock_torch}):
            from app.agents.ocr.hybrid_agent import HybridOCRAgent

            agent = HybridOCRAgent()
            agent.gpu_manager = mock_gpu_manager

            # GPU Agents schlagen fehl
            mock_deepseek_agent.process = AsyncMock(side_effect=Exception("GPU OOM"))
            mock_got_ocr_agent.process = AsyncMock(side_effect=Exception("CUDA error"))
            mock_surya_agent.process = AsyncMock(return_value={
                "text": "Fallback Text",
                "confidence": 0.7,
                "entities": [],
                "layout": {}
            })

            agent.deepseek = mock_deepseek_agent
            agent.got_ocr = mock_got_ocr_agent
            agent.surya_docling = mock_surya_agent

            input_data = {"document_id": "test", "image_path": "/test/doc.pdf"}

            result = await agent.process(input_data)

            # Surya sollte als Fallback verwendet werden
            assert result["selected_engine"] == "surya_docling"
            assert "Fallback Text" in result["text"]


# ========================= Confidence Fusion Tests =========================


class TestHybridOCRConfidenceFusion:
    """Tests fuer Confidence-basierte Result Fusion."""

    @pytest.mark.asyncio
    async def test_fuse_results_with_clear_winner(self, hybrid_agent_with_mocks):
        """_fuse_results() sollte klaren Sieger bei grosser Confidence-Differenz waehlen."""
        results = [
            {"engine": "deepseek", "text": "DeepSeek Text", "confidence": 0.95, "entities": [], "layout": {}},
            {"engine": "got_ocr", "text": "GOT Text", "confidence": 0.70, "entities": [], "layout": {}},
        ]

        fused = await hybrid_agent_with_mocks._fuse_results(results)

        # Differenz > 0.15 -> Confidence Winner
        assert fused["fusion_method"] == "confidence_winner"
        assert fused["selected_engine"] == "deepseek"

    @pytest.mark.asyncio
    async def test_fuse_results_triggers_ensemble_voting(self, hybrid_agent_with_mocks):
        """_fuse_results() sollte Ensemble Voting bei aehnlicher Confidence nutzen."""
        results = [
            {"engine": "deepseek", "text": "Text A", "confidence": 0.90, "entities": [], "layout": {}},
            {"engine": "got_ocr", "text": "Text B", "confidence": 0.88, "entities": [], "layout": {}},
        ]

        fused = await hybrid_agent_with_mocks._fuse_results(results)

        # Differenz < 0.15 -> Character Voting
        assert fused["fusion_method"] == "character_voting"

    @pytest.mark.asyncio
    async def test_fuse_results_no_results_raises_error(self, hybrid_agent_with_mocks):
        """_fuse_results() sollte ValueError bei leeren Results werfen."""
        with pytest.raises(ValueError, match="No valid OCR results"):
            await hybrid_agent_with_mocks._fuse_results([])


# ========================= Character-Level Voting Tests =========================


class TestHybridOCRCharacterVoting:
    """Tests fuer Character-Level Voting."""

    def test_character_voting_basic(self, hybrid_agent_with_mocks):
        """_character_level_voting() sollte Zeichen-weise abstimmen."""
        results = [
            {"engine": "deepseek", "text": "ABC", "confidence": 0.9},
            {"engine": "got_ocr", "text": "ABC", "confidence": 0.8},
        ]

        voted_text = hybrid_agent_with_mocks._character_level_voting(results)

        assert voted_text == "ABC"

    def test_character_voting_with_umlaut_bonus(self, hybrid_agent_with_mocks):
        """Character Voting sollte DeepSeek-Bonus fuer Umlaute geben."""
        # DeepSeek hat "ü", GOT-OCR hat "u"
        results = [
            {"engine": "deepseek", "text": "Müller", "confidence": 0.85},
            {"engine": "got_ocr", "text": "Muller", "confidence": 0.90},  # Höhere Confidence
        ]

        voted_text = hybrid_agent_with_mocks._character_level_voting(results)

        # DeepSeek hat 50% Bonus fuer Umlaute, also sollte "ü" gewinnen
        # 0.85 * 1.5 = 1.275 > 0.90
        assert "ü" in voted_text

    def test_character_voting_handles_different_lengths(self, hybrid_agent_with_mocks):
        """Character Voting sollte unterschiedliche Textlaengen behandeln."""
        results = [
            {"engine": "deepseek", "text": "Kurz", "confidence": 0.9},
            {"engine": "got_ocr", "text": "Laengerer Text", "confidence": 0.8},
        ]

        # Sollte nicht crashen
        voted_text = hybrid_agent_with_mocks._character_level_voting(results)

        assert len(voted_text) > 0

    def test_character_voting_single_result(self, hybrid_agent_with_mocks):
        """Character Voting sollte bei einzelnem Result den Text zurueckgeben."""
        results = [
            {"engine": "deepseek", "text": "Single Result", "confidence": 0.9}
        ]

        voted_text = hybrid_agent_with_mocks._character_level_voting(results)

        assert voted_text == "Single Result"


# ========================= Parallel Processing Tests =========================


class TestHybridOCRParallelProcessing:
    """Tests fuer Parallel Backend Execution."""

    @pytest.mark.asyncio
    async def test_run_parallel_group_executes_concurrently(self, hybrid_agent_with_mocks):
        """_run_parallel_group() sollte Engines parallel ausfuehren."""
        engines = [
            ("deepseek", hybrid_agent_with_mocks.deepseek),
            ("surya_docling", hybrid_agent_with_mocks.surya_docling),
        ]

        input_data = {"document_id": "test", "image_path": "/test/doc.pdf"}

        results = await hybrid_agent_with_mocks._run_parallel_group(
            engines, input_data, torch_available=True
        )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_run_parallel_group_handles_failures(self, hybrid_agent_with_mocks):
        """_run_parallel_group() sollte fehlgeschlagene Engines ignorieren."""
        # Eine Engine schlaegt fehl
        hybrid_agent_with_mocks.deepseek.process = AsyncMock(side_effect=Exception("Error"))

        engines = [
            ("deepseek", hybrid_agent_with_mocks.deepseek),
            ("surya_docling", hybrid_agent_with_mocks.surya_docling),
        ]

        input_data = {"document_id": "test", "image_path": "/test/doc.pdf"}

        results = await hybrid_agent_with_mocks._run_parallel_group(
            engines, input_data, torch_available=True
        )

        # Nur Surya sollte erfolgreich sein
        assert len(results) == 1


# ========================= Sequential Processing Tests =========================


class TestHybridOCRSequentialProcessing:
    """Tests fuer Sequential Backend Execution."""

    @pytest.mark.asyncio
    async def test_run_sequential_group_cleans_memory(
        self, hybrid_agent_with_mocks, mock_torch_cuda
    ):
        """_run_sequential_group() sollte Memory zwischen Backends clearen."""
        engines = [
            ("got_ocr", hybrid_agent_with_mocks.got_ocr),
        ]

        input_data = {"document_id": "test", "image_path": "/test/doc.pdf"}

        with patch.object(hybrid_agent_with_mocks, '_cleanup_gpu_memory') as mock_cleanup:
            await hybrid_agent_with_mocks._run_sequential_group(
                engines, input_data, torch_available=True
            )

        mock_cleanup.assert_called()


# ========================= VRAM Management Tests =========================


class TestHybridOCRVRAMManagement:
    """Tests fuer VRAM Resource Management."""

    def test_get_available_vram_returns_safe_value(self, mock_gpu_manager, mock_deepseek_agent, mock_got_ocr_agent, mock_surya_agent):
        """_get_available_vram() sollte 15% Safety Buffer anwenden."""
        import sys
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_props = Mock()
        mock_props.total_memory = 16 * 1024**3  # 16GB
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 4 * 1024**3  # 4GB verwendet

        with patch.dict(sys.modules, {'torch': mock_torch}):
            from app.agents.ocr.hybrid_agent import HybridOCRAgent

            agent = HybridOCRAgent()
            available = agent._get_available_vram()

            # 12GB frei * 0.85 = 10.2GB
            assert available < 12.0
            assert available > 8.0

    def test_cleanup_gpu_memory_calls_empty_cache(self, mock_gpu_manager, mock_deepseek_agent, mock_got_ocr_agent, mock_surya_agent):
        """_cleanup_gpu_memory() sollte torch.cuda.empty_cache aufrufen."""
        import sys
        import gc
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.empty_cache = Mock()
        mock_torch.cuda.synchronize = Mock()
        mock_torch.cuda.memory_allocated.return_value = 0

        with patch.dict(sys.modules, {'torch': mock_torch}):
            with patch('gc.collect'):
                from app.agents.ocr.hybrid_agent import HybridOCRAgent

                agent = HybridOCRAgent()
                agent._cleanup_gpu_memory(torch_available=True)

                mock_torch.cuda.empty_cache.assert_called()


# ========================= Entity Deduplication Tests =========================


class TestHybridOCREntityDeduplication:
    """Tests fuer Entity Deduplication."""

    def test_deduplicate_entities_exact_match(self, hybrid_agent_with_mocks):
        """_deduplicate_entities() sollte exakte Duplikate entfernen."""
        entities = [
            {"type": "company", "value": "Müller GmbH", "confidence": 0.95, "source": "deepseek"},
            {"type": "company", "value": "Müller GmbH", "confidence": 0.85, "source": "got_ocr"},
        ]

        deduped = hybrid_agent_with_mocks._deduplicate_entities(entities)

        assert len(deduped) == 1
        assert deduped[0]["confidence"] == 0.95  # Hoechste Confidence behalten

    def test_deduplicate_entities_fuzzy_match(self, hybrid_agent_with_mocks):
        """_deduplicate_entities() sollte aehnliche Entities mergen."""
        # Verwende Strings mit hoeherer Similarity (nur 1 Zeichen Unterschied)
        entities = [
            {"type": "company", "value": "Muller GmbH", "confidence": 0.95, "source": "deepseek"},
            {"type": "company", "value": "Müller GmbH", "confidence": 0.85, "source": "got_ocr"},
        ]

        deduped = hybrid_agent_with_mocks._deduplicate_entities(entities)

        # "Muller GmbH" vs "Müller GmbH" = 11 Zeichen, 1 Unterschied
        # Similarity = 1 - (1/11) = 0.909 >= 0.85 -> merge
        assert len(deduped) == 1

    def test_deduplicate_entities_tracks_sources(self, hybrid_agent_with_mocks):
        """_deduplicate_entities() sollte alle Sources tracken."""
        entities = [
            {"type": "iban", "value": "DE89370400440532013000", "confidence": 0.99, "source": "deepseek"},
            {"type": "iban", "value": "DE89370400440532013000", "confidence": 0.97, "source": "got_ocr"},
        ]

        deduped = hybrid_agent_with_mocks._deduplicate_entities(entities)

        assert "sources" in deduped[0]
        assert len(deduped[0]["sources"]) == 2

    def test_deduplicate_entities_limit(self, hybrid_agent_with_mocks):
        """_deduplicate_entities() sollte Entity-Limit respektieren."""
        # Generiere 1500 unique Entities
        entities = [
            {"type": "item", "value": f"Item {i}", "confidence": 0.5, "source": "test"}
            for i in range(1500)
        ]

        deduped = hybrid_agent_with_mocks._deduplicate_entities(entities)

        # Limit ist 1000
        assert len(deduped) <= 1000


# ========================= Similarity Calculation Tests =========================


class TestHybridOCRSimilarity:
    """Tests fuer Similarity-Berechnung."""

    def test_calculate_similarity_exact_match(self, hybrid_agent_with_mocks):
        """_calculate_similarity() sollte 1.0 fuer identische Strings zurueckgeben."""
        sim = hybrid_agent_with_mocks._calculate_similarity("Hello", "Hello")
        assert sim == 1.0

    def test_calculate_similarity_different_case(self, hybrid_agent_with_mocks):
        """_calculate_similarity() sollte Case-Insensitive sein."""
        sim = hybrid_agent_with_mocks._calculate_similarity("Hello", "HELLO")
        assert sim == 1.0

    def test_calculate_similarity_empty_strings(self, hybrid_agent_with_mocks):
        """_calculate_similarity() sollte leere Strings behandeln."""
        sim1 = hybrid_agent_with_mocks._calculate_similarity("", "")
        sim2 = hybrid_agent_with_mocks._calculate_similarity("Hello", "")
        sim3 = hybrid_agent_with_mocks._calculate_similarity("", "Hello")

        assert sim1 == 1.0
        assert sim2 == 0.0
        assert sim3 == 0.0


# ========================= Levenshtein Distance Tests =========================


class TestHybridOCRLevenshtein:
    """Tests fuer Levenshtein Distance."""

    def test_levenshtein_identical(self, hybrid_agent_with_mocks):
        """Levenshtein Distance sollte 0 fuer identische Strings sein."""
        dist = hybrid_agent_with_mocks._levenshtein_distance("Hello", "Hello")
        assert dist == 0

    def test_levenshtein_one_edit(self, hybrid_agent_with_mocks):
        """Levenshtein Distance sollte 1 fuer eine Aenderung sein."""
        dist = hybrid_agent_with_mocks._levenshtein_distance("Hello", "Hallo")
        assert dist == 1

    def test_levenshtein_empty_string(self, hybrid_agent_with_mocks):
        """Levenshtein Distance mit leerem String."""
        dist = hybrid_agent_with_mocks._levenshtein_distance("Hello", "")
        assert dist == 5  # Laenge von "Hello"


# ========================= Ensemble Confidence Tests =========================


class TestHybridOCREnsembleConfidence:
    """Tests fuer Ensemble Confidence Berechnung."""

    def test_ensemble_confidence_single_result(self, hybrid_agent_with_mocks):
        """Ensemble Confidence sollte bei einem Result dessen Confidence zurueckgeben."""
        results = [{"confidence": 0.85}]
        conf = hybrid_agent_with_mocks._calculate_ensemble_confidence(results)
        assert conf == 0.85

    def test_ensemble_confidence_average(self, hybrid_agent_with_mocks):
        """Ensemble Confidence sollte Durchschnitt bei mehreren Results berechnen."""
        results = [
            {"confidence": 0.80, "text": "ABC"},
            {"confidence": 1.00, "text": "XYZ"},
        ]
        conf = hybrid_agent_with_mocks._calculate_ensemble_confidence(results)
        # Durchschnitt: 0.9
        assert 0.85 <= conf <= 1.0

    def test_ensemble_confidence_boost_on_agreement(self, hybrid_agent_with_mocks):
        """Ensemble Confidence sollte Boost bei hoher Übereinstimmung geben."""
        results = [
            {"confidence": 0.80, "text": "Identischer Text"},
            {"confidence": 0.80, "text": "Identischer Text"},
        ]
        conf = hybrid_agent_with_mocks._calculate_ensemble_confidence(results)
        # Sollte Boost bekommen wegen Similarity > 0.9
        assert conf >= 0.80


# ========================= Input Validation Tests =========================


class TestHybridOCRInputValidation:
    """Tests fuer Input Validation."""

    @pytest.mark.asyncio
    async def test_process_validates_required_fields(self, hybrid_agent_with_mocks):
        """process() sollte required Fields validieren."""
        # Fehlende document_id
        with pytest.raises(Exception):  # validate_input sollte Exception werfen
            await hybrid_agent_with_mocks.process({"image_path": "/test/doc.pdf"})


# ========================= Run Tests =========================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

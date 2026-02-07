"""
Unit tests for DeepSeek-Janus-Pro OCR Agent.

Tests:
- Model initialization and loading
- GPU allocation and fallback
- Entity extraction (IBAN, VAT ID, dates, currency, business terms)
- Layout detection (invoice, letter, contract, report)
- German text processing with umlauts
- Batch processing
- Error handling and OOM recovery
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List
import re

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# Sample texts for entity and layout testing
SAMPLE_INVOICE_TEXT = """
Müller GmbH & Co. KG
Hauptstraße 123
80331 München

Rechnung Nr.: 2024-001
Rechnungsdatum: 15.03.2024
Leistungszeitraum: 01.02.2024 - 28.02.2024

Rechnungsempfänger:
Beispiel AG
USt-IdNr.: DE123456789

Nettobetrag: 2.500,00 €
MwSt. 19%: 475,00 €
Bruttobetrag: 2.975,00 €

Bankverbindung:
IBAN: DE89 3704 0044 0532 0130 00
BIC: COBADEFFXXX

Mit freundlichen Grüßen
Max Müller
Geschäftsführer
"""

SAMPLE_CONTRACT_TEXT = """
VERTRAG

zwischen

Müller GmbH (im Folgenden "Auftragnehmer")
und
Beispiel AG (im Folgenden "Auftraggeber")

§ 1 Vertragsgegenstand
Der Auftragnehmer verpflichtet sich zur Erbringung von Softwareentwicklungsleistungen.

§ 2 Haftung
Die Haftung des Auftragnehmers ist auf grobe Fahrlässigkeit beschränkt.

§ 3 Kündigungsfrist
Die Kündigungsfrist beträgt 3 Monate zum Monatsende.

Unterschrift Auftragnehmer: _________________
Unterschrift Auftraggeber: _________________
"""


class TestDeepSeekAgentInitialization:
    """Test DeepSeek agent initialization."""

    @pytest.fixture
    def mock_gpu_manager(self):
        """Mock GPUManager."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager') as mock:
            gpu_manager = Mock()
            gpu_manager.allocate_for_backend.return_value = {"success": True, "mode": "gpu"}
            gpu_manager.deallocate_backend = Mock()
            gpu_manager.handle_oom_error.return_value = {"recovered": True}
            gpu_manager.get_optimal_batch_size.return_value = 4
            mock.return_value = gpu_manager
            yield gpu_manager

    @pytest.fixture
    def mock_torch(self):
        """Mock torch for CUDA tests."""
        with patch('app.agents.ocr.deepseek_agent.torch') as mock_torch:
            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.get_device_name.return_value = "NVIDIA GeForce RTX 4080"
            mock_torch.cuda.get_device_properties.return_value = MagicMock(total_memory=16 * 1024**3)
            mock_torch.cuda.memory_allocated.return_value = 2 * 1024**3
            mock_torch.cuda.memory_reserved.return_value = 3 * 1024**3
            mock_torch.cuda.empty_cache = MagicMock()
            mock_torch.cuda.synchronize = MagicMock()
            mock_torch.cuda.OutOfMemoryError = RuntimeError
            mock_torch.bfloat16 = 'bfloat16'
            mock_torch.float32 = 'float32'
            mock_torch.is_tensor = lambda x: False
            mock_torch.no_grad.return_value.__enter__ = Mock()
            mock_torch.no_grad.return_value.__exit__ = Mock()
            yield mock_torch

    @pytest.fixture
    def agent(self, mock_gpu_manager, mock_torch):
        """Create DeepSeek agent with mocks."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        return DeepSeekAgent()

    @pytest.mark.unit
    def test_agent_initialization(self, agent):
        """Test agent initializes with correct defaults."""
        assert agent.name == "deepseek_ocr_agent"
        assert agent.gpu_required == True
        assert agent.vram_gb == 24  # Full model requires 24GB
        assert agent.ENABLE_QUANTIZATION == True  # Enabled for RTX 4080
        assert agent._model_loaded == False

    @pytest.mark.unit
    def test_agent_model_configuration(self, agent):
        """Test model configuration constants."""
        assert "deepseek" in agent.MODEL_NAME.lower() or "janus" in agent.MODEL_NAME.lower()
        assert agent.MAX_BATCH_SIZE == 4

    @pytest.mark.unit
    def test_agent_status(self, agent, mock_torch):
        """Test agent status returns correct information."""
        status = agent.get_status()

        assert status["name"] == "deepseek_ocr_agent"
        assert status["model_loaded"] == False
        assert "model_name" in status
        assert "quantization_enabled" in status
        assert "gpu_info" in status


class TestDeepSeekEntityExtraction:
    """Test entity extraction functionality."""

    @pytest.fixture
    def agent_for_entity_tests(self):
        """Create agent without full mocking for entity extraction tests."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager'):
            from app.agents.ocr.deepseek_agent import DeepSeekAgent
            return DeepSeekAgent()

    @pytest.mark.unit
    def test_extract_iban(self, agent_for_entity_tests):
        """Test IBAN extraction from German text."""
        text = "Bitte überweisen Sie auf IBAN: DE89 3704 0044 0532 0130 00"
        entities = agent_for_entity_tests._extract_entities(text)

        iban_entities = [e for e in entities if e["type"] == "IBAN"]
        assert len(iban_entities) >= 1
        assert "DE89" in iban_entities[0]["value"]

    @pytest.mark.unit
    def test_extract_vat_id(self, agent_for_entity_tests):
        """Test VAT ID (USt-IdNr.) extraction."""
        text = "USt-IdNr.: DE123456789"
        entities = agent_for_entity_tests._extract_entities(text)

        vat_entities = [e for e in entities if e["type"] == "VAT_ID"]
        assert len(vat_entities) >= 1
        assert vat_entities[0]["value"] == "DE123456789"

    @pytest.mark.unit
    def test_extract_dates(self, agent_for_entity_tests):
        """Test German date format extraction."""
        text = "Rechnungsdatum: 15.03.2024, Lieferdatum: 01.04.2024"
        entities = agent_for_entity_tests._extract_entities(text)

        date_entities = [e for e in entities if e["type"] == "DATE"]
        assert len(date_entities) >= 2

    @pytest.mark.unit
    def test_extract_currency(self, agent_for_entity_tests):
        """Test German currency format extraction."""
        text = "Gesamtbetrag: 1.234,56 € inkl. MwSt."
        entities = agent_for_entity_tests._extract_entities(text)

        currency_entities = [e for e in entities if e["type"] == "CURRENCY"]
        assert len(currency_entities) >= 1

    @pytest.mark.unit
    def test_extract_email(self, agent_for_entity_tests):
        """Test email address extraction."""
        text = "Kontakt: info@mueller-gmbh.de oder support@beispiel.com"
        entities = agent_for_entity_tests._extract_entities(text)

        email_entities = [e for e in entities if e["type"] == "EMAIL"]
        assert len(email_entities) >= 2

    @pytest.mark.unit
    def test_extract_from_invoice(self, agent_for_entity_tests):
        """Test comprehensive entity extraction from invoice text."""
        entities = agent_for_entity_tests._extract_entities(SAMPLE_INVOICE_TEXT)

        entity_types = set(e["type"] for e in entities)
        assert "IBAN" in entity_types
        assert "DATE" in entity_types
        assert "CURRENCY" in entity_types

    @pytest.mark.unit
    def test_empty_text_handling(self, agent_for_entity_tests):
        """Test handling of empty or minimal text."""
        entities = agent_for_entity_tests._extract_entities("")
        assert entities == []

        entities = agent_for_entity_tests._extract_entities("Hi")
        assert entities == []

    @pytest.mark.unit
    def test_entities_sorted_by_position(self, agent_for_entity_tests):
        """Test that entities are sorted by position in text."""
        text = "IBAN: DE89370400440532013000 am 15.03.2024 für 100,00 €"
        entities = agent_for_entity_tests._extract_entities(text)

        # Check that start positions are in ascending order
        positions = [e.get("start", 0) for e in entities]
        assert positions == sorted(positions)


class TestDeepSeekLayoutDetection:
    """Test layout detection functionality."""

    @pytest.fixture
    def agent_for_layout_tests(self):
        """Create agent for layout tests."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager'):
            from app.agents.ocr.deepseek_agent import DeepSeekAgent
            return DeepSeekAgent()

    @pytest.mark.unit
    def test_detect_invoice_layout(self, agent_for_layout_tests):
        """Test invoice document type detection."""
        layout = agent_for_layout_tests._detect_layout(SAMPLE_INVOICE_TEXT)

        assert layout["type"] == "invoice"
        assert layout["confidence"] >= 0.5
        assert layout["has_signature"] == True

    @pytest.mark.unit
    def test_detect_contract_layout(self, agent_for_layout_tests):
        """Test contract document type detection."""
        layout = agent_for_layout_tests._detect_layout(SAMPLE_CONTRACT_TEXT)

        assert layout["type"] == "contract"
        assert layout["confidence"] >= 0.5

    @pytest.mark.unit
    def test_detect_letter_layout(self, agent_for_layout_tests):
        """Test letter document type detection."""
        letter_text = """
        Sehr geehrte Frau Schröder,

        vielen Dank für Ihre Anfrage vom 10. März 2024.
        Gerne unterbreiten wir Ihnen ein individuelles Angebot.

        Mit freundlichen Grüßen
        Max Müller
        """
        layout = agent_for_layout_tests._detect_layout(letter_text)

        assert layout["type"] == "letter"
        assert layout["has_signature"] == True

    @pytest.mark.unit
    def test_detect_list_structure(self, agent_for_layout_tests):
        """Test list detection in document."""
        text_with_list = """
        Leistungsumfang:
        - Beratung
        - Entwicklung
        - Testing
        - Dokumentation
        """
        layout = agent_for_layout_tests._detect_layout(text_with_list)

        assert layout["has_lists"] == True

    @pytest.mark.unit
    def test_detect_table_structure(self, agent_for_layout_tests):
        """Test table detection using tab-delimited data."""
        text_with_table = "Artikel\tMenge\tPreis\nA\t10\t100\nB\t5\t50\nC\t20\t200"
        layout = agent_for_layout_tests._detect_layout(text_with_table)

        assert layout["has_tables"] == True

    @pytest.mark.unit
    def test_detect_header(self, agent_for_layout_tests):
        """Test header detection."""
        layout = agent_for_layout_tests._detect_layout(SAMPLE_INVOICE_TEXT)
        assert layout["has_header"] == True

    @pytest.mark.unit
    def test_empty_text_layout(self, agent_for_layout_tests):
        """Test layout detection for empty text."""
        layout = agent_for_layout_tests._detect_layout("")
        assert layout["type"] == "unknown"
        assert layout["confidence"] == 0.0

    @pytest.mark.unit
    def test_layout_includes_metrics(self, agent_for_layout_tests):
        """Test that layout includes text metrics."""
        layout = agent_for_layout_tests._detect_layout(SAMPLE_INVOICE_TEXT)

        assert "line_count" in layout
        assert "word_count" in layout
        assert layout["line_count"] > 0
        assert layout["word_count"] > 0


class TestDeepSeekPromptBuilding:
    """Test prompt building for OCR."""

    @pytest.fixture
    def agent(self):
        """Create agent for prompt tests."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager'):
            from app.agents.ocr.deepseek_agent import DeepSeekAgent
            return DeepSeekAgent()

    @pytest.mark.unit
    @pytest.mark.skip(reason="API geaendert: _build_prompt() Methode hat neue Signatur mit strukturiertem JSON-Format")
    def test_german_prompt(self, agent):
        """Test German language prompt generation."""
        prompt = agent._build_prompt("de", {})

        assert "Extrahiere" in prompt or "extrahiere" in prompt.lower()
        assert "Umlaute" in prompt or "umlaute" in prompt.lower()
        assert "ä" in prompt and "ö" in prompt and "ü" in prompt

    @pytest.mark.unit
    @pytest.mark.skip(reason="API geaendert: _build_prompt() Methode hat neue Signatur mit strukturiertem JSON-Format")
    def test_english_prompt(self, agent):
        """Test English language prompt generation."""
        prompt = agent._build_prompt("en", {})

        assert "Extract" in prompt

    @pytest.mark.unit
    @pytest.mark.skip(reason="API geaendert: _build_prompt() Methode hat neue Signatur mit strukturiertem JSON-Format")
    def test_table_extraction_option(self, agent):
        """Test prompt with table extraction option."""
        prompt = agent._build_prompt("de", {"extract_tables": True})

        assert "table" in prompt.lower() or "Tabelle" in prompt

    @pytest.mark.unit
    @pytest.mark.skip(reason="API geaendert: _build_prompt() Methode hat neue Signatur mit strukturiertem JSON-Format")
    def test_handwriting_extraction_option(self, agent):
        """Test prompt with handwriting extraction option."""
        prompt = agent._build_prompt("de", {"extract_handwriting": True})

        assert "handwrit" in prompt.lower()


class TestDeepSeekProcessing:
    """Test document processing."""

    @pytest.fixture
    def fully_mocked_agent(self):
        """Create fully mocked agent for processing tests."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager') as mock_gm, \
             patch('app.agents.ocr.deepseek_agent.torch') as mock_torch, \
             patch('app.agents.ocr.deepseek_agent.Image') as mock_image:

            mock_gm.return_value.allocate_for_backend.return_value = {"success": True}
            mock_gm.return_value.deallocate_backend = Mock()

            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.empty_cache = Mock()

            from app.agents.ocr.deepseek_agent import DeepSeekAgent
            agent = DeepSeekAgent()

            # Mock the model loading and inference
            agent._model_loaded = True
            agent.model = Mock()
            agent.processor = Mock()

            yield agent

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_validates_input(self, fully_mocked_agent):
        """Test that process validates required input fields."""
        with pytest.raises(ValueError, match="Missing required input keys"):
            await fully_mocked_agent.process({})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_validates_document_id(self, fully_mocked_agent):
        """Test that process requires document_id."""
        with pytest.raises(ValueError, match="document_id"):
            await fully_mocked_agent.process({"image_path": "/some/path.png"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_validates_image_path(self, fully_mocked_agent):
        """Test that process requires image_path."""
        with pytest.raises(ValueError, match="image_path"):
            await fully_mocked_agent.process({"document_id": "doc123"})


class TestDeepSeekGPUManagement:
    """Test GPU resource management."""

    @pytest.fixture
    def mock_gpu_setup(self):
        """Setup GPU mocks."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager') as mock_gm, \
             patch('app.agents.ocr.deepseek_agent.torch') as mock_torch:

            gpu_manager = Mock()
            mock_gm.return_value = gpu_manager

            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.empty_cache = Mock()
            mock_torch.cuda.synchronize = Mock()

            yield {
                'gpu_manager': gpu_manager,
                'torch': mock_torch
            }

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_gpu_allocation_required(self, mock_gpu_setup):
        """Test that GPU allocation is required before processing."""
        mock_gpu_setup['gpu_manager'].allocate_for_backend.return_value = {
            "success": False,
            "reason": "Insufficient VRAM"
        }

        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        agent = DeepSeekAgent()

        from app.agents.base import AgentResourceError
        with pytest.raises(AgentResourceError, match="Failed to allocate GPU"):
            await agent._ensure_gpu_allocated()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_gpu_cleanup(self, mock_gpu_setup):
        """Test GPU resource cleanup."""
        mock_gpu_setup['gpu_manager'].allocate_for_backend.return_value = {"success": True}

        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        agent = DeepSeekAgent()
        agent._model_loaded = True
        agent.model = Mock()
        agent.processor = Mock()

        await agent.cleanup()

        assert agent._model_loaded == False
        assert agent.model is None
        assert agent.processor is None
        mock_gpu_setup['torch'].cuda.empty_cache.assert_called()
        mock_gpu_setup['gpu_manager'].deallocate_backend.assert_called_with("deepseek")


class TestDeepSeekBatchProcessing:
    """Test batch processing functionality."""

    @pytest.fixture
    def batch_agent(self):
        """Create agent for batch tests."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager') as mock_gm:
            mock_gm.return_value.get_optimal_batch_size.return_value = 4
            mock_gm.return_value.allocate_for_backend.return_value = {"success": True}

            from app.agents.ocr.deepseek_agent import DeepSeekAgent
            agent = DeepSeekAgent()
            yield agent

    @pytest.mark.unit
    def test_batch_size_respects_max(self, batch_agent):
        """Test that batch size doesn't exceed maximum."""
        assert batch_agent.MAX_BATCH_SIZE == 4

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_batch_processing_structure(self, batch_agent):
        """Test batch processing returns correct structure."""
        # Mock the process method
        batch_agent.process = AsyncMock(return_value={
            "result": {"text": "Test", "confidence": 0.9}
        })

        documents = [
            {"document_id": f"doc{i}", "image_path": f"/path/doc{i}.png"}
            for i in range(3)
        ]

        results = await batch_agent.process_batch(documents)

        assert len(results) == 3


class TestDeepSeekImageLoading:
    """Test image loading functionality."""

    @pytest.fixture
    def agent(self):
        """Create agent for image tests."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager'):
            from app.agents.ocr.deepseek_agent import DeepSeekAgent
            return DeepSeekAgent()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_nonexistent_image(self, agent):
        """Test error handling for non-existent image."""
        with pytest.raises(FileNotFoundError):
            await agent._load_image(Path("/nonexistent/image.png"))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_valid_image(self, agent, tmp_path):
        """Test loading a valid image file."""
        from PIL import Image

        img_path = tmp_path / "test.png"
        img = Image.new('RGB', (800, 600), color='white')
        img.save(img_path)

        loaded = await agent._load_image(Path(img_path))

        assert loaded.size == (800, 600)
        assert loaded.mode == "RGB"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])

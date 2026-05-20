"""Unit-Tests für SuryaDoclingEnhancedAgent.

Tests für:
- Agent-Initialisierung
- Layout-Integration mit Docling
- Lesereihenfolge-Anwendung
- Tabellen-Extraktion
- Fallback-Verhalten
- Deutsche Umlaut-Erkennung
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Dict, Any, List

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from app.agents.ocr.surya_docling_enhanced_agent import SuryaDoclingEnhancedAgent
from app.agents.ocr.models.layout_models import (
    DocumentLayout,
    PageLayout,
    LayoutElement,
    LayoutElementType,
    BoundingBox,
    TableStructure,
    TableCell,
)


# Sample German texts for testing
SAMPLE_GERMAN_TEXT = """
Müller GmbH & Co. KG
Hauptstraße 123
80331 München

Rechnung Nr.: 2024-001
Rechnungsdatum: 15.03.2024

Nettobetrag: 2.500,00 €
MwSt. 19%: 475,00 €
Bruttobetrag: 2.975,00 €
"""

GERMAN_UMLAUTS = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']


def create_mock_text_line(text: str, confidence: float = 0.95, bbox: list = None):
    """Erstelle Mock-Text-Line."""
    mock_line = MagicMock()
    mock_line.text = text
    mock_line.confidence = confidence
    mock_line.bbox = bbox or [10, 10, 200, 50]
    return mock_line


def create_mock_ocr_result(text_lines: List[str], confidences: List[float] = None):
    """Erstelle Mock-OCR-Ergebnis."""
    if confidences is None:
        confidences = [0.95] * len(text_lines)

    mock_result = MagicMock()
    mock_result.text_lines = [
        create_mock_text_line(text, conf, [i*10, i*10, i*10+100, i*10+30])
        for i, (text, conf) in enumerate(zip(text_lines, confidences))
    ]
    return mock_result


class TestSuryaDoclingEnhancedAgentInit:
    """Tests für Agent-Initialisierung."""

    def test_default_initialization(self):
        """Standard-Initialisierung testen."""
        agent = SuryaDoclingEnhancedAgent()

        assert agent.name == "surya_docling_enhanced_agent"
        assert agent.gpu_required is False
        assert agent.vram_gb == 0
        assert agent.default_language == "de"
        assert agent._enable_layout is True
        assert agent._extract_tables is True
        assert agent._preserve_reading_order is True

    def test_custom_config(self):
        """Benutzerdefinierte Konfiguration testen."""
        config = {
            "enable_layout_analysis": False,
            "extract_tables": False,
            "preserve_reading_order": False,
            "fallback_on_layout_error": False,
        }
        agent = SuryaDoclingEnhancedAgent(config=config)

        assert agent._enable_layout is False
        assert agent._extract_tables is False
        assert agent._preserve_reading_order is False
        assert agent._fallback_on_error is False

    def test_get_status_not_loaded(self):
        """Status wenn Modelle nicht geladen."""
        agent = SuryaDoclingEnhancedAgent()
        status = agent.get_status()

        assert status["name"] == "surya_docling_enhanced_agent"
        assert status["gpu_required"] is False
        assert status["vram_gb"] == 0
        assert status["surya_models_loaded"] is False
        assert status["status"] == "not_loaded"
        assert status["config"]["layout_analysis_enabled"] is True


class TestSuryaDoclingEnhancedAgentProcess:
    """Tests für Verarbeitung."""

    @pytest.fixture
    def agent(self):
        """Agent mit gemockten Modellen."""
        agent = SuryaDoclingEnhancedAgent()
        return agent

    @pytest.fixture
    def mock_surya_models(self):
        """Mock Surya-Modelle."""
        with patch('surya.detection.DetectionPredictor') as mock_det, \
             patch('surya.recognition.RecognitionPredictor') as mock_rec, \
             patch('surya.foundation.FoundationPredictor') as mock_found, \
             patch('surya.common.surya.schema.TaskNames') as mock_tasks:

            mock_tasks.ocr_with_boxes = "ocr_with_boxes"

            yield {
                'det': mock_det,
                'rec': mock_rec,
                'found': mock_found,
                'tasks': mock_tasks,
            }

    @pytest.mark.asyncio
    async def test_process_missing_image_path(self, agent: SuryaDoclingEnhancedAgent):
        """Fehler bei fehlendem image_path."""
        result = await agent.process({})

        assert result["success"] is False
        assert "image_path" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_process_file_not_found(self, agent: SuryaDoclingEnhancedAgent):
        """Fehler bei nicht existierender Datei."""
        with patch.object(agent, '_ensure_initialized', new_callable=AsyncMock):
            result = await agent.process({
                "image_path": "/nicht/existierende/datei.pdf"
            })

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_process_with_layout_disabled(self, agent: SuryaDoclingEnhancedAgent, tmp_path: Path):
        """Verarbeitung ohne Layout-Analyse."""
        agent._enable_layout = False

        # Test-Bild erstellen
        test_image = tmp_path / "test.png"

        # Mock PIL Image
        mock_image = MagicMock()

        # Mock OCR-Ergebnis
        mock_ocr_result = create_mock_ocr_result(["Müller GmbH", "Rechnung"])

        with patch.object(agent, '_ensure_initialized', new_callable=AsyncMock):
            with patch.object(agent, '_load_images', new_callable=AsyncMock, return_value=[mock_image]):
                with patch.object(agent, '_run_surya_ocr', new_callable=AsyncMock, return_value=[
                    {
                        "page_number": 1,
                        "text_blocks": [
                            {"text": "Müller GmbH", "confidence": 0.95, "bbox": [0, 0, 100, 30]},
                            {"text": "Rechnung", "confidence": 0.92, "bbox": [0, 40, 100, 70]},
                        ],
                        "full_text": "Müller GmbH\nRechnung",
                        "confidence": 0.935,
                    }
                ]):
                    result = await agent.process({
                        "image_path": str(test_image),
                        "language": "de",
                    })

        assert result["success"] is True
        assert result["layout_analysis_used"] is False
        assert "Müller" in result["text"]


class TestLayoutMerging:
    """Tests für Layout-Zusammenführung."""

    @pytest.fixture
    def agent(self):
        """Agent für Tests."""
        return SuryaDoclingEnhancedAgent()

    def test_merge_results_no_layout(self, agent: SuryaDoclingEnhancedAgent):
        """Zusammenführung ohne Layout."""
        ocr_results = [
            {
                "page_number": 1,
                "text_blocks": [
                    {"text": "Text 1", "confidence": 0.95, "bbox": [0, 0, 100, 30]},
                ],
                "full_text": "Text 1",
                "confidence": 0.95,
            }
        ]

        merged = agent._merge_results(ocr_results, None)

        assert "Text 1" in merged["text"]
        assert merged["reading_order_applied"] is False
        assert merged["layout_summary"] is None

    def test_merge_results_with_layout(self, agent: SuryaDoclingEnhancedAgent):
        """Zusammenführung mit Layout."""
        ocr_results = [
            {
                "page_number": 1,
                "text_blocks": [
                    {"text": "Überschrift", "confidence": 0.95, "bbox": [50, 50, 200, 80]},
                    {"text": "Inhalt", "confidence": 0.92, "bbox": [50, 100, 200, 150]},
                ],
                "full_text": "Überschrift\nInhalt",
                "confidence": 0.935,
            }
        ]

        # Layout mit Elementen erstellen
        layout = DocumentLayout(
            pages=[
                PageLayout(
                    page_number=1,
                    width=612,
                    height=792,
                    elements=[
                        LayoutElement(
                            element_type=LayoutElementType.HEADING,
                            bbox=BoundingBox(x0=50, y0=50, x1=200, y1=80),
                            reading_order=0,
                            page_number=1,
                            text="",
                        ),
                        LayoutElement(
                            element_type=LayoutElementType.TEXT,
                            bbox=BoundingBox(x0=50, y0=100, x1=200, y1=150),
                            reading_order=1,
                            page_number=1,
                            text="",
                        ),
                    ],
                    num_columns=1,
                )
            ],
            total_elements=2,
            table_count=0,
            figure_count=0,
        )

        merged = agent._merge_results(ocr_results, layout)

        assert merged["reading_order_applied"] is True
        assert merged["layout_summary"] is not None


class TestReadingOrderApplication:
    """Tests für Lesereihenfolge-Anwendung."""

    @pytest.fixture
    def agent(self):
        """Agent für Tests."""
        return SuryaDoclingEnhancedAgent()

    def test_apply_reading_order_simple(self, agent: SuryaDoclingEnhancedAgent):
        """Einfache Lesereihenfolge."""
        text_blocks = [
            {"text": "Block 1", "bbox": [50, 50, 150, 80]},
            {"text": "Block 2", "bbox": [50, 100, 150, 130]},
        ]

        page_layout = PageLayout(
            page_number=1,
            width=612,
            height=792,
            elements=[
                LayoutElement(
                    element_type=LayoutElementType.TEXT,
                    bbox=BoundingBox(x0=50, y0=50, x1=150, y1=80),
                    reading_order=0,
                    page_number=1,
                ),
                LayoutElement(
                    element_type=LayoutElementType.TEXT,
                    bbox=BoundingBox(x0=50, y0=100, x1=150, y1=130),
                    reading_order=1,
                    page_number=1,
                ),
            ],
        )

        result = agent._apply_reading_order(text_blocks, page_layout)

        assert "Block 1" in result
        assert "Block 2" in result

    def test_apply_reading_order_empty(self, agent: SuryaDoclingEnhancedAgent):
        """Leere Element-Liste."""
        text_blocks = [
            {"text": "Block 1", "bbox": [50, 50, 150, 80]},
        ]

        page_layout = PageLayout(
            page_number=1,
            width=612,
            height=792,
            elements=[],
        )

        result = agent._apply_reading_order(text_blocks, page_layout)
        assert "Block 1" in result


class TestTableExtraction:
    """Tests für Tabellen-Extraktion."""

    @pytest.fixture
    def agent(self):
        """Agent für Tests."""
        return SuryaDoclingEnhancedAgent()

    def test_extract_page_tables(self, agent: SuryaDoclingEnhancedAgent):
        """Tabellen von Seite extrahieren."""
        table = TableStructure(
            num_rows=2,
            num_cols=2,
            cells=[
                TableCell(row=0, col=0, text="Header 1", is_header=True),
                TableCell(row=0, col=1, text="Header 2", is_header=True),
                TableCell(row=1, col=0, text="Wert 1"),
                TableCell(row=1, col=1, text="Wert 2"),
            ],
            has_header=True,
        )

        page_layout = PageLayout(
            page_number=1,
            width=612,
            height=792,
            elements=[
                LayoutElement(
                    element_type=LayoutElementType.TABLE,
                    bbox=BoundingBox(x0=50, y0=100, x1=400, y1=300),
                    reading_order=0,
                    page_number=1,
                    table=table,
                ),
            ],
        )

        ocr_page = {
            "text_blocks": [],
        }

        tables = agent._extract_page_tables(page_layout, ocr_page)

        assert len(tables) == 1
        assert tables[0]["rows"] == 2
        assert tables[0]["cols"] == 2
        assert tables[0]["has_header"] is True


class TestBBoxOverlap:
    """Tests für BBox-Überlappungs-Berechnung."""

    @pytest.fixture
    def agent(self):
        """Agent für Tests."""
        return SuryaDoclingEnhancedAgent()

    def test_calculate_bbox_overlap_full(self, agent: SuryaDoclingEnhancedAgent):
        """Volle Überlappung."""
        bbox1 = BoundingBox(x0=0, y0=0, x1=100, y1=100)
        bbox2 = [0, 0, 100, 100]

        overlap = agent._calculate_bbox_overlap(bbox1, bbox2)
        assert overlap == 1.0

    def test_calculate_bbox_overlap_partial(self, agent: SuryaDoclingEnhancedAgent):
        """Teilweise Überlappung."""
        bbox1 = BoundingBox(x0=0, y0=0, x1=100, y1=100)
        bbox2 = [50, 0, 150, 100]

        overlap = agent._calculate_bbox_overlap(bbox1, bbox2)
        assert 0.3 < overlap < 0.4

    def test_calculate_bbox_overlap_none(self, agent: SuryaDoclingEnhancedAgent):
        """Keine Überlappung."""
        bbox1 = BoundingBox(x0=0, y0=0, x1=100, y1=100)
        bbox2 = [200, 200, 300, 300]

        overlap = agent._calculate_bbox_overlap(bbox1, bbox2)
        assert overlap == 0.0

    def test_calculate_bbox_overlap_invalid(self, agent: SuryaDoclingEnhancedAgent):
        """Ungültige BBox."""
        bbox1 = BoundingBox(x0=0, y0=0, x1=100, y1=100)
        bbox2 = [0, 0]  # Zu wenig Koordinaten

        overlap = agent._calculate_bbox_overlap(bbox1, bbox2)
        assert overlap == 0.0


class TestUmlautDetection:
    """Tests für Umlaut-Erkennung."""

    @pytest.fixture
    def agent(self):
        """Agent für Tests."""
        return SuryaDoclingEnhancedAgent()

    def test_check_umlauts_present(self, agent: SuryaDoclingEnhancedAgent):
        """Umlaute vorhanden."""
        text = "Müller GmbH aus München"
        assert agent._check_umlauts(text) is True

    def test_check_umlauts_missing(self, agent: SuryaDoclingEnhancedAgent):
        """Keine Umlaute."""
        text = "Mueller GmbH from Munich"
        assert agent._check_umlauts(text) is False

    def test_check_umlauts_special(self, agent: SuryaDoclingEnhancedAgent):
        """Spezielle deutsche Zeichen."""
        text = "Größe und Maße"
        assert agent._check_umlauts(text) is True  # ö und ß


class TestCleanup:
    """Tests für Cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_resets_models(self):
        """Cleanup sollte Modelle zurücksetzen."""
        agent = SuryaDoclingEnhancedAgent()
        agent._surya_models_loaded = True
        agent._det_predictor = MagicMock()
        agent._rec_predictor = MagicMock()
        agent._foundation_predictor = MagicMock()

        await agent.cleanup()

        assert agent._surya_models_loaded is False
        assert agent._det_predictor is None
        assert agent._rec_predictor is None
        assert agent._foundation_predictor is None


class TestPlainResultCreation:
    """Tests für Plain-Result-Erstellung."""

    @pytest.fixture
    def agent(self):
        """Agent für Tests."""
        return SuryaDoclingEnhancedAgent()

    def test_create_plain_result_single_page(self, agent: SuryaDoclingEnhancedAgent):
        """Einzelseiten-Ergebnis."""
        ocr_results = [
            {
                "page_number": 1,
                "text_blocks": [{"text": "Text", "confidence": 0.95}],
                "full_text": "Text auf Seite 1",
                "confidence": 0.95,
            }
        ]

        result = agent._create_plain_result(ocr_results)

        assert result["text"] == "Text auf Seite 1"
        assert result["confidence"] == 0.95
        assert result["reading_order_applied"] is False

    def test_create_plain_result_multi_page(self, agent: SuryaDoclingEnhancedAgent):
        """Mehrseitiges Ergebnis."""
        ocr_results = [
            {
                "page_number": 1,
                "text_blocks": [],
                "full_text": "Seite 1",
                "confidence": 0.95,
            },
            {
                "page_number": 2,
                "text_blocks": [],
                "full_text": "Seite 2",
                "confidence": 0.90,
            },
        ]

        result = agent._create_plain_result(ocr_results)

        assert "Seite 1" in result["text"]
        assert "Seite 2" in result["text"]
        assert "Seitenumbruch" in result["text"]
        assert result["confidence"] == 0.925  # Durchschnitt

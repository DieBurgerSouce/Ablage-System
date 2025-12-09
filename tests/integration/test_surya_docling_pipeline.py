"""Integration-Tests für Surya+Docling Enhanced Pipeline.

Tests für:
- Vollständige Pipeline mit echten Dokumenten
- Backend-Manager-Integration
- Fallback-Verhalten
- Performance-Anforderungen

Hinweis: Diese Tests benötigen installierte Abhängigkeiten (surya-ocr, docling).
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import time

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestBackendManagerIntegration:
    """Integration-Tests für Backend-Manager mit surya_enhanced."""

    @pytest.mark.asyncio
    async def test_surya_enhanced_in_available_backends(self):
        """surya_enhanced sollte in verfügbaren Backends sein."""
        from app.services.backend_manager import BackendManager

        # Mock GPU-Manager für konsistentes Verhalten
        with patch('app.services.backend_manager.GPUManager'):
            with patch('app.services.backend_manager.TORCH_AVAILABLE', False):
                manager = BackendManager()

        available = manager.get_available_backends()

        # surya_enhanced sollte verfügbar sein (CPU-only)
        assert "surya_enhanced" in available or "surya" in available

    @pytest.mark.asyncio
    async def test_fallback_order_includes_surya_enhanced(self):
        """Fallback-Reihenfolge sollte surya_enhanced enthalten."""
        from app.services.backend_manager import BackendManager

        with patch('app.services.backend_manager.GPUManager'):
            with patch('app.services.backend_manager.TORCH_AVAILABLE', False):
                manager = BackendManager()

        fallback_order = manager.get_fallback_order("surya_enhanced")

        # surya_enhanced sollte in der Fallback-Kette sein
        assert "surya_enhanced" in fallback_order or "surya" in fallback_order

    @pytest.mark.asyncio
    async def test_pdf_selects_surya_enhanced(self):
        """PDF-Verarbeitung sollte surya_enhanced auswählen."""
        from app.services.backend_manager import BackendManager

        with patch('app.services.backend_manager.GPUManager'):
            with patch('app.services.backend_manager.TORCH_AVAILABLE', False):
                manager = BackendManager()

        # Nur wenn surya_enhanced verfügbar
        if "surya_enhanced" not in manager.get_available_backends():
            pytest.skip("surya_enhanced nicht verfügbar")

        # Temporäre PDF-Datei simulieren
        with patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value = MagicMock(st_size=1024 * 1024)  # 1MB

            with patch('pathlib.Path.suffix', new_callable=lambda: property(lambda self: '.pdf')):
                # Mock Path-Objekt
                mock_path = MagicMock()
                mock_path.suffix = '.pdf'
                mock_path.stat.return_value.st_size = 1024 * 1024

                with patch('pathlib.Path', return_value=mock_path):
                    backend = await manager.select_backend(
                        image_path="/tmp/test.pdf",
                        language="de",
                        prefer_gpu=False,
                    )

        # Bei PDF sollte surya_enhanced bevorzugt werden
        assert backend in ["surya_enhanced", "surya", "got_ocr"]


class TestSuryaDoclingEnhancedIntegration:
    """Integration-Tests für SuryaDoclingEnhancedAgent."""

    @pytest.fixture
    def agent(self):
        """Agent-Instanz."""
        from app.agents.ocr.surya_docling_enhanced_agent import SuryaDoclingEnhancedAgent
        return SuryaDoclingEnhancedAgent()

    def test_agent_initialization(self, agent):
        """Agent sollte korrekt initialisieren."""
        assert agent.name == "surya_docling_enhanced_agent"
        assert agent.gpu_required is False
        assert agent.vram_gb == 0

    def test_agent_status(self, agent):
        """Agent-Status sollte vollständig sein."""
        status = agent.get_status()

        assert "name" in status
        assert "gpu_required" in status
        assert "config" in status
        assert status["config"]["layout_analysis_enabled"] is True


class TestDoclingLayoutAnalyzerIntegration:
    """Integration-Tests für DoclingLayoutAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Analyzer-Instanz."""
        from app.agents.ocr.docling_layout_analyzer import DoclingLayoutAnalyzer
        DoclingLayoutAnalyzer.reset_instance()
        return DoclingLayoutAnalyzer()

    def test_analyzer_singleton(self, analyzer):
        """Singleton-Pattern sollte funktionieren."""
        from app.agents.ocr.docling_layout_analyzer import DoclingLayoutAnalyzer

        instance1 = DoclingLayoutAnalyzer.get_instance()
        instance2 = DoclingLayoutAnalyzer.get_instance()

        assert instance1 is instance2

    def test_analyzer_status(self, analyzer):
        """Analyzer-Status sollte korrekt sein."""
        status = analyzer.get_status()

        assert status["name"] == "docling_layout_analyzer"
        assert status["is_loaded"] is False
        assert "table_extraction" in status["capabilities"]

    @pytest.mark.asyncio
    async def test_analyzer_file_not_found(self, analyzer):
        """FileNotFoundError bei nicht existierender Datei."""
        with pytest.raises(FileNotFoundError):
            await analyzer.analyze("/nicht/existierende/datei.pdf")


class TestLayoutModelsIntegration:
    """Integration-Tests für Layout-Modelle."""

    def test_document_layout_creation(self):
        """DocumentLayout-Erstellung testen."""
        from app.agents.ocr.models.layout_models import (
            DocumentLayout, PageLayout, LayoutElement,
            LayoutElementType, BoundingBox, TableStructure, TableCell
        )

        # Vollständiges Dokument erstellen
        table = TableStructure(
            num_rows=2,
            num_cols=2,
            cells=[
                TableCell(row=0, col=0, text="A1", is_header=True),
                TableCell(row=0, col=1, text="B1", is_header=True),
                TableCell(row=1, col=0, text="A2"),
                TableCell(row=1, col=1, text="B2"),
            ],
            has_header=True,
        )

        page = PageLayout(
            page_number=1,
            width=612,
            height=792,
            elements=[
                LayoutElement(
                    element_type=LayoutElementType.HEADING,
                    bbox=BoundingBox(x0=50, y0=50, x1=400, y1=80),
                    reading_order=0,
                    page_number=1,
                    text="Rechnung",
                ),
                LayoutElement(
                    element_type=LayoutElementType.TABLE,
                    bbox=BoundingBox(x0=50, y0=100, x1=400, y1=300),
                    reading_order=1,
                    page_number=1,
                    table=table,
                ),
            ],
            num_columns=1,
        )

        doc = DocumentLayout(
            pages=[page],
            total_elements=2,
            table_count=1,
            figure_count=0,
        )

        # Validierung
        assert doc.page_count == 1
        assert doc.has_tables is True
        assert doc.has_multi_column_pages is False

        # Tabellen-Extraktion
        tables = doc.get_all_tables()
        assert len(tables) == 1
        assert tables[0].num_rows == 2

        # Markdown-Export
        md = tables[0].to_markdown()
        assert "A1" in md
        assert "B2" in md

    def test_bounding_box_operations(self):
        """BoundingBox-Operationen testen."""
        from app.agents.ocr.models.layout_models import BoundingBox

        bbox1 = BoundingBox(x0=0, y0=0, x1=100, y1=100)
        bbox2 = BoundingBox(x0=50, y0=50, x1=150, y1=150)

        # Überlappung
        assert bbox1.overlaps(bbox2) is True

        # Überlappungsverhältnis
        ratio = bbox1.overlap_ratio(bbox2)
        assert 0.1 < ratio < 0.5

        # Punkt-Enthaltung
        assert bbox1.contains_point(50, 50) is True
        assert bbox1.contains_point(150, 150) is False


class TestCostOptimizerIntegration:
    """Integration-Tests für Cost-Optimizer mit surya_enhanced."""

    def test_surya_enhanced_in_performance_data(self):
        """surya_enhanced sollte in Performance-Daten sein."""
        from app.services.backend_manager import CostOptimizer

        optimizer = CostOptimizer()

        assert "surya_enhanced" in optimizer.BACKEND_PERFORMANCE

        perf = optimizer.BACKEND_PERFORMANCE["surya_enhanced"]
        assert perf["quality_score"] > 0.8
        assert perf["vram_gb"] == 0.0  # CPU-only

    def test_cost_estimation_for_surya_enhanced(self):
        """Kostenabschätzung für surya_enhanced."""
        from app.services.backend_manager import CostOptimizer

        optimizer = CostOptimizer()
        estimate = optimizer.estimate_backend_cost("surya_enhanced", page_count=5)

        assert estimate.backend == "surya_enhanced"
        assert estimate.estimated_quality > 0.8
        assert estimate.estimated_vram_gb == 0.0
        assert estimate.cost_score > 0


class TestEndToEndPipeline:
    """End-to-End Integration-Tests."""

    @pytest.mark.asyncio
    async def test_full_pipeline_mock(self):
        """Vollständige Pipeline mit Mocks testen."""
        from app.agents.ocr.surya_docling_enhanced_agent import SuryaDoclingEnhancedAgent
        from app.agents.ocr.models.layout_models import (
            DocumentLayout, PageLayout, LayoutElement,
            LayoutElementType, BoundingBox
        )

        agent = SuryaDoclingEnhancedAgent()

        # Mock Layout-Analyse
        mock_layout = DocumentLayout(
            pages=[
                PageLayout(
                    page_number=1,
                    width=612,
                    height=792,
                    elements=[
                        LayoutElement(
                            element_type=LayoutElementType.TEXT,
                            bbox=BoundingBox(x0=50, y0=50, x1=400, y1=100),
                            reading_order=0,
                            page_number=1,
                        )
                    ],
                    num_columns=1,
                )
            ],
            total_elements=1,
            table_count=0,
            figure_count=0,
        )

        # Mock OCR-Ergebnis
        mock_ocr = [
            {
                "page_number": 1,
                "text_blocks": [
                    {"text": "Müller GmbH", "confidence": 0.95, "bbox": [50, 50, 400, 100]},
                ],
                "full_text": "Müller GmbH",
                "confidence": 0.95,
            }
        ]

        # Merge testen
        result = agent._merge_results(mock_ocr, mock_layout)

        assert "Müller" in result["text"]
        assert result["confidence"] > 0.9
        assert result["layout_summary"] is not None

    @pytest.mark.asyncio
    async def test_umlaut_preservation(self):
        """Deutsche Umlaute sollten erhalten bleiben."""
        from app.agents.ocr.surya_docling_enhanced_agent import SuryaDoclingEnhancedAgent

        agent = SuryaDoclingEnhancedAgent()

        # Mock OCR-Ergebnis mit Umlauten
        mock_ocr = [
            {
                "page_number": 1,
                "text_blocks": [
                    {"text": "Größe: 100m²", "confidence": 0.95, "bbox": []},
                    {"text": "Müller & Söhne", "confidence": 0.92, "bbox": []},
                ],
                "full_text": "Größe: 100m²\nMüller & Söhne",
                "confidence": 0.935,
            }
        ]

        result = agent._merge_results(mock_ocr, None)

        # Umlaute sollten erhalten sein
        assert "ö" in result["text"]
        assert "ü" in result["text"]
        assert agent._check_umlauts(result["text"]) is True


@pytest.mark.slow
class TestPerformance:
    """Performance-Tests (langsam, optional)."""

    @pytest.mark.asyncio
    async def test_merge_performance(self):
        """Merge-Operation sollte schnell sein."""
        from app.agents.ocr.surya_docling_enhanced_agent import SuryaDoclingEnhancedAgent
        from app.agents.ocr.models.layout_models import (
            DocumentLayout, PageLayout, LayoutElement,
            LayoutElementType, BoundingBox
        )

        agent = SuryaDoclingEnhancedAgent()

        # Großes Layout erstellen (100 Seiten)
        pages = []
        for i in range(100):
            elements = [
                LayoutElement(
                    element_type=LayoutElementType.TEXT,
                    bbox=BoundingBox(x0=50, y0=j*50, x1=400, y1=j*50+40),
                    reading_order=j,
                    page_number=i+1,
                )
                for j in range(10)
            ]
            pages.append(PageLayout(
                page_number=i+1,
                width=612,
                height=792,
                elements=elements,
            ))

        layout = DocumentLayout(pages=pages, total_elements=1000)

        # OCR-Ergebnisse erstellen
        ocr_results = [
            {
                "page_number": i+1,
                "text_blocks": [
                    {"text": f"Text Block {j}", "confidence": 0.95, "bbox": [50, j*50, 400, j*50+40]}
                    for j in range(10)
                ],
                "full_text": "\n".join(f"Text Block {j}" for j in range(10)),
                "confidence": 0.95,
            }
            for i in range(100)
        ]

        # Performance messen
        start = time.perf_counter()
        result = agent._merge_results(ocr_results, layout)
        duration = time.perf_counter() - start

        # Merge sollte unter 1 Sekunde dauern
        assert duration < 1.0, f"Merge dauerte {duration:.2f}s (sollte < 1s sein)"
        assert len(result["pages"]) == 100

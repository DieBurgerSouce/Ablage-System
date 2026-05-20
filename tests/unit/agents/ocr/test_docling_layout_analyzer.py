"""Unit-Tests für DoclingLayoutAnalyzer.

Tests für:
- Singleton-Pattern
- Layout-Analyse mit Mocks
- Tabellen-Extraktion
- Spalten-Erkennung
- Fehlerbehandlung
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from app.agents.ocr.docling_layout_analyzer import DoclingLayoutAnalyzer
from app.agents.ocr.models.layout_models import (
    DocumentLayout,
    LayoutElementType,
)


class TestDoclingLayoutAnalyzerSingleton:
    """Tests für Singleton-Pattern."""

    def setup_method(self):
        """Reset singleton vor jedem Test."""
        DoclingLayoutAnalyzer.reset_instance()

    def test_singleton_returns_same_instance(self):
        """Singleton sollte immer dieselbe Instanz zurückgeben."""
        instance1 = DoclingLayoutAnalyzer.get_instance()
        instance2 = DoclingLayoutAnalyzer.get_instance()

        assert instance1 is instance2

    def test_reset_creates_new_instance(self):
        """Reset sollte neue Instanz ermöglichen."""
        instance1 = DoclingLayoutAnalyzer.get_instance()
        DoclingLayoutAnalyzer.reset_instance()
        instance2 = DoclingLayoutAnalyzer.get_instance()

        assert instance1 is not instance2


class TestDoclingLayoutAnalyzer:
    """Unit-Tests für DoclingLayoutAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Frischer Analyzer für jeden Test."""
        DoclingLayoutAnalyzer.reset_instance()
        return DoclingLayoutAnalyzer()

    @pytest.fixture
    def mock_docling(self):
        """Mock Docling-Module."""
        with patch.dict('sys.modules', {
            'docling': MagicMock(),
            'docling.document_converter': MagicMock(),
            'docling.datamodel': MagicMock(),
            'docling.datamodel.pipeline_options': MagicMock(),
            'docling.datamodel.base_models': MagicMock(),
        }):
            yield

    def test_initialization(self, analyzer: DoclingLayoutAnalyzer):
        """Initialisierung testen."""
        assert analyzer._is_loaded is False
        assert analyzer._converter is None

    def test_get_status_not_loaded(self, analyzer: DoclingLayoutAnalyzer):
        """Status wenn nicht geladen."""
        status = analyzer.get_status()

        assert status["name"] == "docling_layout_analyzer"
        assert status["is_loaded"] is False
        assert "table_extraction" in status["capabilities"]

    @pytest.mark.asyncio
    async def test_analyze_file_not_found(self, analyzer: DoclingLayoutAnalyzer):
        """Fehler bei nicht existierender Datei."""
        with pytest.raises(FileNotFoundError):
            await analyzer.analyze("/nicht/existierende/datei.pdf")

    @pytest.mark.asyncio
    async def test_analyze_returns_document_layout(self, analyzer: DoclingLayoutAnalyzer, tmp_path: Path):
        """Analyse sollte DocumentLayout zurückgeben."""
        # Dummy-PDF erstellen
        test_pdf = tmp_path / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 dummy content")

        # Mock Docling-Konvertierung
        mock_document = MagicMock()
        mock_document.pages = [MagicMock()]
        mock_document.pages[0].size = MagicMock()
        mock_document.pages[0].size.width = 612
        mock_document.pages[0].size.height = 792

        # Leere Iteration
        mock_document.iterate_items = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.document = mock_document

        with patch.object(analyzer, '_convert_document', return_value=mock_result):
            with patch.object(analyzer, 'load_converter', new_callable=AsyncMock):
                result = await analyzer.analyze(test_pdf)

        assert isinstance(result, DocumentLayout)
        assert result.page_count >= 0

    @pytest.mark.asyncio
    async def test_analyze_with_options(self, analyzer: DoclingLayoutAnalyzer, tmp_path: Path):
        """Analyse mit Optionen testen."""
        test_pdf = tmp_path / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 dummy content")

        mock_document = MagicMock()
        mock_document.pages = []
        mock_document.iterate_items = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.document = mock_document

        with patch.object(analyzer, '_convert_document', return_value=mock_result):
            with patch.object(analyzer, 'load_converter', new_callable=AsyncMock):
                result = await analyzer.analyze(
                    test_pdf,
                    options={
                        "extract_tables": False,
                        "extract_figures": False,
                    }
                )

        assert isinstance(result, DocumentLayout)


class TestElementTypeMapping:
    """Tests für Element-Typ-Mapping."""

    @pytest.fixture
    def analyzer(self):
        """Frischer Analyzer."""
        DoclingLayoutAnalyzer.reset_instance()
        return DoclingLayoutAnalyzer()

    def test_table_item_mapping(self, analyzer: DoclingLayoutAnalyzer):
        """TableItem sollte auf TABLE gemappt werden."""
        mock_item = MagicMock()
        mock_item.__class__.__name__ = "TableItem"

        element_type = analyzer._get_element_type(mock_item)
        assert element_type == LayoutElementType.TABLE

    def test_text_item_mapping(self, analyzer: DoclingLayoutAnalyzer):
        """TextItem sollte auf TEXT gemappt werden."""
        mock_item = MagicMock()
        mock_item.__class__.__name__ = "TextItem"

        element_type = analyzer._get_element_type(mock_item)
        assert element_type == LayoutElementType.TEXT

    def test_figure_item_mapping(self, analyzer: DoclingLayoutAnalyzer):
        """FigureItem sollte auf FIGURE gemappt werden."""
        mock_item = MagicMock()
        mock_item.__class__.__name__ = "FigureItem"

        element_type = analyzer._get_element_type(mock_item)
        assert element_type == LayoutElementType.FIGURE

    def test_header_label_mapping(self, analyzer: DoclingLayoutAnalyzer):
        """Label-basierte Header-Erkennung."""
        mock_item = MagicMock()
        mock_item.__class__.__name__ = "UnknownItem"
        mock_item.label = "page_header"

        element_type = analyzer._get_element_type(mock_item)
        assert element_type == LayoutElementType.HEADER

    def test_footer_label_mapping(self, analyzer: DoclingLayoutAnalyzer):
        """Label-basierte Footer-Erkennung."""
        mock_item = MagicMock()
        mock_item.__class__.__name__ = "UnknownItem"
        mock_item.label = "page_footer"

        element_type = analyzer._get_element_type(mock_item)
        assert element_type == LayoutElementType.FOOTER

    def test_unknown_item_mapping(self, analyzer: DoclingLayoutAnalyzer):
        """Unbekannte Items sollten auf TEXT fallen."""
        mock_item = MagicMock()
        mock_item.__class__.__name__ = "CompletelyUnknownItem"

        # Kein label Attribut
        if hasattr(mock_item, 'label'):
            del mock_item.label

        element_type = analyzer._get_element_type(mock_item)
        assert element_type == LayoutElementType.TEXT


class TestColumnDetection:
    """Tests für Spalten-Erkennung."""

    @pytest.fixture
    def analyzer(self):
        """Frischer Analyzer."""
        DoclingLayoutAnalyzer.reset_instance()
        return DoclingLayoutAnalyzer()

    def test_single_column_detection(self, analyzer: DoclingLayoutAnalyzer):
        """Einspaltiges Layout erkennen."""
        from app.agents.ocr.models.layout_models import LayoutElement, BoundingBox

        elements = [
            LayoutElement(
                element_type=LayoutElementType.TEXT,
                bbox=BoundingBox(x0=50, y0=100, x1=500, y1=150),
                reading_order=0,
                page_number=1,
            ),
            LayoutElement(
                element_type=LayoutElementType.TEXT,
                bbox=BoundingBox(x0=50, y0=160, x1=500, y1=210),
                reading_order=1,
                page_number=1,
            ),
        ]

        columns = analyzer._detect_columns(elements)
        assert columns == 1

    def test_two_column_detection(self, analyzer: DoclingLayoutAnalyzer):
        """Zweispaltiges Layout erkennen."""
        from app.agents.ocr.models.layout_models import LayoutElement, BoundingBox

        # Linke Spalte
        elements = [
            LayoutElement(
                element_type=LayoutElementType.TEXT,
                bbox=BoundingBox(x0=50, y0=100, x1=250, y1=150),
                reading_order=0,
                page_number=1,
            ),
            LayoutElement(
                element_type=LayoutElementType.TEXT,
                bbox=BoundingBox(x0=52, y0=160, x1=250, y1=210),
                reading_order=1,
                page_number=1,
            ),
            # Rechte Spalte (mit großer Lücke)
            LayoutElement(
                element_type=LayoutElementType.TEXT,
                bbox=BoundingBox(x0=350, y0=100, x1=550, y1=150),
                reading_order=2,
                page_number=1,
            ),
            LayoutElement(
                element_type=LayoutElementType.TEXT,
                bbox=BoundingBox(x0=352, y0=160, x1=550, y1=210),
                reading_order=3,
                page_number=1,
            ),
        ]

        columns = analyzer._detect_columns(elements)
        assert columns == 2

    def test_empty_elements(self, analyzer: DoclingLayoutAnalyzer):
        """Leere Element-Liste sollte 1 Spalte zurückgeben."""
        columns = analyzer._detect_columns([])
        assert columns == 1


class TestBoundingBoxExtraction:
    """Tests für Bounding-Box-Extraktion."""

    @pytest.fixture
    def analyzer(self):
        """Frischer Analyzer."""
        DoclingLayoutAnalyzer.reset_instance()
        return DoclingLayoutAnalyzer()

    def test_bbox_extraction_with_prov(self, analyzer: DoclingLayoutAnalyzer):
        """BBox aus prov extrahieren."""
        mock_item = MagicMock()
        mock_prov = MagicMock()
        mock_bbox = MagicMock()
        mock_bbox.l = 10
        mock_bbox.t = 20
        mock_bbox.r = 110
        mock_bbox.b = 70

        mock_prov.bbox = mock_bbox
        mock_item.prov = [mock_prov]

        bbox = analyzer._get_bbox(mock_item)

        assert bbox is not None
        assert bbox.x0 == 10
        assert bbox.y0 == 20
        assert bbox.x1 == 110
        assert bbox.y1 == 70

    def test_bbox_extraction_no_prov(self, analyzer: DoclingLayoutAnalyzer):
        """Keine BBox wenn kein prov."""
        mock_item = MagicMock()
        mock_item.prov = None

        bbox = analyzer._get_bbox(mock_item)
        assert bbox is None

    def test_bbox_extraction_empty_prov(self, analyzer: DoclingLayoutAnalyzer):
        """Keine BBox bei leerem prov."""
        mock_item = MagicMock()
        mock_item.prov = []

        bbox = analyzer._get_bbox(mock_item)
        assert bbox is None


class TestTextExtraction:
    """Tests für Text-Extraktion."""

    @pytest.fixture
    def analyzer(self):
        """Frischer Analyzer."""
        DoclingLayoutAnalyzer.reset_instance()
        return DoclingLayoutAnalyzer()

    def test_text_from_text_attribute(self, analyzer: DoclingLayoutAnalyzer):
        """Text aus text-Attribut extrahieren."""
        mock_item = MagicMock()
        mock_item.text = "Deutscher Text mit Umlauten: äöüß"

        text = analyzer._get_text(mock_item)
        assert text == "Deutscher Text mit Umlauten: äöüß"

    def test_text_from_export_method(self, analyzer: DoclingLayoutAnalyzer):
        """Text aus export_to_plaintext extrahieren."""
        mock_item = MagicMock()
        del mock_item.text  # Kein text-Attribut
        mock_item.export_to_plaintext = MagicMock(return_value="Exportierter Text")

        text = analyzer._get_text(mock_item)
        assert text == "Exportierter Text"

    def test_text_empty_fallback(self, analyzer: DoclingLayoutAnalyzer):
        """Leerer String wenn keine Text-Quelle."""
        mock_item = MagicMock()
        del mock_item.text
        del mock_item.export_to_plaintext

        text = analyzer._get_text(mock_item)
        assert text == ""


class TestTableStructureExtraction:
    """Tests für Tabellen-Struktur-Extraktion."""

    @pytest.fixture
    def analyzer(self):
        """Frischer Analyzer."""
        DoclingLayoutAnalyzer.reset_instance()
        return DoclingLayoutAnalyzer()

    def test_table_with_grid(self, analyzer: DoclingLayoutAnalyzer):
        """Tabelle mit Grid-Daten extrahieren."""
        mock_item = MagicMock()
        mock_item.prov = None

        # Grid-Struktur
        mock_cell1 = MagicMock()
        mock_cell1.text = "Header 1"
        mock_cell1.row_span = 1
        mock_cell1.col_span = 1

        mock_cell2 = MagicMock()
        mock_cell2.text = "Header 2"
        mock_cell2.row_span = 1
        mock_cell2.col_span = 1

        mock_cell3 = MagicMock()
        mock_cell3.text = "Wert 1"
        mock_cell3.row_span = 1
        mock_cell3.col_span = 1

        mock_cell4 = MagicMock()
        mock_cell4.text = "Wert 2"
        mock_cell4.row_span = 1
        mock_cell4.col_span = 1

        mock_item.data = MagicMock()
        mock_item.data.grid = [
            [mock_cell1, mock_cell2],
            [mock_cell3, mock_cell4],
        ]

        table = analyzer._extract_table_structure(mock_item)

        assert table is not None
        assert table.num_rows == 2
        assert table.num_cols == 2
        assert len(table.cells) == 4

    def test_table_no_data(self, analyzer: DoclingLayoutAnalyzer):
        """Keine Tabelle wenn keine Daten."""
        mock_item = MagicMock()
        mock_item.data = None

        table = analyzer._extract_table_structure(mock_item)
        assert table is None


class TestCleanup:
    """Tests für Cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_resets_state(self):
        """Cleanup sollte Zustand zurücksetzen."""
        DoclingLayoutAnalyzer.reset_instance()
        analyzer = DoclingLayoutAnalyzer()
        analyzer._is_loaded = True
        analyzer._converter = MagicMock()

        await analyzer.cleanup()

        assert analyzer._is_loaded is False
        assert analyzer._converter is None

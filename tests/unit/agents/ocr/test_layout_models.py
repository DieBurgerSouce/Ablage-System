"""Unit-Tests für Layout-Modelle.

Tests für:
- BoundingBox Operationen
- TableStructure und TableCell
- PageLayout und DocumentLayout
- Serialisierung und Deserialisierung
"""

import pytest
from typing import List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from app.agents.ocr.models.layout_models import (
    BoundingBox,
    LayoutElementType,
    TableCell,
    TableStructure,
    LayoutElement,
    PageLayout,
    DocumentLayout,
)


class TestBoundingBox:
    """Tests für BoundingBox-Klasse."""

    def test_basic_properties(self):
        """Grundlegende Eigenschaften testen."""
        bbox = BoundingBox(x0=10, y0=20, x1=110, y1=70)

        assert bbox.width == 100
        assert bbox.height == 50
        assert bbox.area == 5000
        assert bbox.center == (60, 45)

    def test_contains_point(self):
        """Punkt-in-Box Test."""
        bbox = BoundingBox(x0=0, y0=0, x1=100, y1=100)

        assert bbox.contains_point(50, 50) is True
        assert bbox.contains_point(0, 0) is True
        assert bbox.contains_point(100, 100) is True
        assert bbox.contains_point(150, 50) is False
        assert bbox.contains_point(-10, 50) is False

    def test_overlaps(self):
        """Überlappungs-Test."""
        bbox1 = BoundingBox(x0=0, y0=0, x1=100, y1=100)
        bbox2 = BoundingBox(x0=50, y0=50, x1=150, y1=150)
        bbox3 = BoundingBox(x0=200, y0=200, x1=300, y1=300)

        assert bbox1.overlaps(bbox2) is True
        assert bbox2.overlaps(bbox1) is True
        assert bbox1.overlaps(bbox3) is False

    def test_overlap_ratio(self):
        """Überlappungsverhältnis-Test."""
        bbox1 = BoundingBox(x0=0, y0=0, x1=100, y1=100)
        bbox2 = BoundingBox(x0=0, y0=0, x1=100, y1=100)  # Identisch

        assert bbox1.overlap_ratio(bbox2) == 1.0

        bbox3 = BoundingBox(x0=50, y0=0, x1=150, y1=100)
        ratio = bbox1.overlap_ratio(bbox3)
        assert 0.3 < ratio < 0.4  # ~33% Überlappung

        bbox4 = BoundingBox(x0=200, y0=200, x1=300, y1=300)
        assert bbox1.overlap_ratio(bbox4) == 0.0

    def test_to_dict(self):
        """Dictionary-Serialisierung testen."""
        bbox = BoundingBox(x0=10, y0=20, x1=110, y1=70)
        d = bbox.to_dict()

        assert d["x0"] == 10
        assert d["y0"] == 20
        assert d["x1"] == 110
        assert d["y1"] == 70
        assert d["width"] == 100
        assert d["height"] == 50

    def test_from_list(self):
        """Erstellung aus Liste testen."""
        bbox = BoundingBox.from_list([10, 20, 110, 70])

        assert bbox.x0 == 10
        assert bbox.y0 == 20
        assert bbox.x1 == 110
        assert bbox.y1 == 70

    def test_from_list_invalid(self):
        """Ungültige Liste sollte Fehler werfen."""
        with pytest.raises(ValueError):
            BoundingBox.from_list([10, 20])


class TestTableCell:
    """Tests für TableCell-Klasse."""

    def test_basic_cell(self):
        """Einfache Zelle testen."""
        cell = TableCell(row=0, col=0, text="Header", is_header=True)

        assert cell.row == 0
        assert cell.col == 0
        assert cell.text == "Header"
        assert cell.is_header is True
        assert cell.row_span == 1
        assert cell.col_span == 1

    def test_merged_cell(self):
        """Zusammengeführte Zelle testen."""
        cell = TableCell(row=0, col=0, text="Merged", row_span=2, col_span=3)

        assert cell.row_span == 2
        assert cell.col_span == 3

    def test_to_dict(self):
        """Dictionary-Serialisierung testen."""
        bbox = BoundingBox(x0=0, y0=0, x1=100, y1=50)
        cell = TableCell(row=1, col=2, text="Wert", bbox=bbox, confidence=0.95)

        d = cell.to_dict()
        assert d["row"] == 1
        assert d["col"] == 2
        assert d["text"] == "Wert"
        assert d["bbox"] is not None


class TestTableStructure:
    """Tests für TableStructure-Klasse."""

    @pytest.fixture
    def sample_table(self) -> TableStructure:
        """Beispiel-Tabelle erstellen."""
        cells = [
            TableCell(row=0, col=0, text="Name", is_header=True),
            TableCell(row=0, col=1, text="Preis", is_header=True),
            TableCell(row=1, col=0, text="Produkt A"),
            TableCell(row=1, col=1, text="10,00 €"),
            TableCell(row=2, col=0, text="Produkt B"),
            TableCell(row=2, col=1, text="20,00 €"),
        ]
        return TableStructure(num_rows=3, num_cols=2, cells=cells, has_header=True)

    def test_get_cell(self, sample_table: TableStructure):
        """Zellen-Zugriff testen."""
        cell = sample_table.get_cell(0, 0)
        assert cell is not None
        assert cell.text == "Name"

        cell = sample_table.get_cell(1, 1)
        assert cell.text == "10,00 €"

        cell = sample_table.get_cell(99, 99)
        assert cell is None

    def test_get_row(self, sample_table: TableStructure):
        """Zeilen-Zugriff testen."""
        row = sample_table.get_row(0)
        assert len(row) == 2
        assert row[0].text == "Name"
        assert row[1].text == "Preis"

    def test_get_column(self, sample_table: TableStructure):
        """Spalten-Zugriff testen."""
        col = sample_table.get_column(0)
        assert len(col) == 3
        assert col[0].text == "Name"
        assert col[1].text == "Produkt A"
        assert col[2].text == "Produkt B"

    def test_to_grid(self, sample_table: TableStructure):
        """Grid-Konvertierung testen."""
        grid = sample_table.to_grid()

        assert len(grid) == 3  # 3 Zeilen
        assert len(grid[0]) == 2  # 2 Spalten
        assert grid[0][0] == "Name"
        assert grid[1][1] == "10,00 €"

    def test_to_markdown(self, sample_table: TableStructure):
        """Markdown-Konvertierung testen."""
        md = sample_table.to_markdown()

        assert "| Name | Preis |" in md
        assert "| --- | --- |" in md  # Header-Separator
        assert "| Produkt A | 10,00 € |" in md

    def test_to_dict(self, sample_table: TableStructure):
        """Dictionary-Serialisierung testen."""
        d = sample_table.to_dict()

        assert d["num_rows"] == 3
        assert d["num_cols"] == 2
        assert d["has_header"] is True
        assert "grid" in d
        assert "markdown" in d
        assert len(d["cells"]) == 6


class TestLayoutElement:
    """Tests für LayoutElement-Klasse."""

    def test_text_element(self):
        """Text-Element testen."""
        element = LayoutElement(
            element_type=LayoutElementType.TEXT,
            bbox=BoundingBox(x0=0, y0=0, x1=100, y1=50),
            reading_order=0,
            page_number=1,
            text="Deutscher Text mit Umlauten: äöü",
            confidence=0.95,
        )

        assert element.is_text is True
        assert element.is_structural is False
        assert element.element_type == LayoutElementType.TEXT

    def test_structural_element(self):
        """Strukturelles Element testen."""
        element = LayoutElement(
            element_type=LayoutElementType.HEADER,
            bbox=BoundingBox(x0=0, y0=0, x1=612, y1=50),
            reading_order=0,
            page_number=1,
            text="Seitenkopf",
        )

        assert element.is_text is False
        assert element.is_structural is True

    def test_table_element(self):
        """Tabellen-Element testen."""
        table = TableStructure(num_rows=2, num_cols=2, cells=[], has_header=True)
        element = LayoutElement(
            element_type=LayoutElementType.TABLE,
            bbox=BoundingBox(x0=0, y0=100, x1=400, y1=300),
            reading_order=1,
            page_number=1,
            table=table,
        )

        assert element.element_type == LayoutElementType.TABLE
        assert element.table is not None
        assert element.is_text is False

    def test_to_dict(self):
        """Dictionary-Serialisierung testen."""
        element = LayoutElement(
            element_type=LayoutElementType.HEADING,
            bbox=BoundingBox(x0=0, y0=0, x1=400, y1=30),
            reading_order=0,
            page_number=1,
            text="Überschrift",
            confidence=0.98,
        )

        d = element.to_dict()
        assert d["element_type"] == "heading"
        assert d["text"] == "Überschrift"
        assert d["reading_order"] == 0


class TestPageLayout:
    """Tests für PageLayout-Klasse."""

    @pytest.fixture
    def sample_page(self) -> PageLayout:
        """Beispiel-Seite erstellen."""
        elements = [
            LayoutElement(
                element_type=LayoutElementType.HEADING,
                bbox=BoundingBox(x0=50, y0=50, x1=500, y1=80),
                reading_order=0,
                page_number=1,
                text="Rechnungstitel",
            ),
            LayoutElement(
                element_type=LayoutElementType.TEXT,
                bbox=BoundingBox(x0=50, y0=100, x1=500, y1=200),
                reading_order=1,
                page_number=1,
                text="Rechnungsdetails...",
            ),
            LayoutElement(
                element_type=LayoutElementType.TABLE,
                bbox=BoundingBox(x0=50, y0=220, x1=500, y1=400),
                reading_order=2,
                page_number=1,
                table=TableStructure(num_rows=3, num_cols=2, cells=[]),
            ),
            LayoutElement(
                element_type=LayoutElementType.FOOTER,
                bbox=BoundingBox(x0=50, y0=750, x1=500, y1=780),
                reading_order=3,
                page_number=1,
                text="Seite 1",
            ),
        ]

        return PageLayout(
            page_number=1,
            width=612,
            height=792,
            elements=elements,
            num_columns=1,
            has_header=False,
            has_footer=True,
        )

    def test_text_elements(self, sample_page: PageLayout):
        """Text-Elemente filtern."""
        text_elements = sample_page.text_elements
        assert len(text_elements) == 2  # HEADING und TEXT

    def test_tables(self, sample_page: PageLayout):
        """Tabellen filtern."""
        tables = sample_page.tables
        assert len(tables) == 1

    def test_get_elements_in_reading_order(self, sample_page: PageLayout):
        """Elemente in Lesereihenfolge."""
        ordered = sample_page.get_elements_in_reading_order()

        assert len(ordered) == 4
        assert ordered[0].element_type == LayoutElementType.HEADING
        assert ordered[1].element_type == LayoutElementType.TEXT
        assert ordered[2].element_type == LayoutElementType.TABLE
        assert ordered[3].element_type == LayoutElementType.FOOTER

    def test_get_full_text(self, sample_page: PageLayout):
        """Volltext-Extraktion testen."""
        text = sample_page.get_full_text(include_tables=False)

        assert "Rechnungstitel" in text
        assert "Rechnungsdetails" in text

    def test_to_dict(self, sample_page: PageLayout):
        """Dictionary-Serialisierung testen."""
        d = sample_page.to_dict()

        assert d["page_number"] == 1
        assert d["width"] == 612
        assert d["height"] == 792
        assert d["element_count"] == 4
        assert d["table_count"] == 1


class TestDocumentLayout:
    """Tests für DocumentLayout-Klasse."""

    @pytest.fixture
    def sample_document(self) -> DocumentLayout:
        """Beispiel-Dokument erstellen."""
        pages = [
            PageLayout(
                page_number=1,
                width=612,
                height=792,
                elements=[
                    LayoutElement(
                        element_type=LayoutElementType.TEXT,
                        bbox=BoundingBox(x0=0, y0=0, x1=100, y1=50),
                        reading_order=0,
                        page_number=1,
                        text="Seite 1 Text",
                    ),
                ],
                num_columns=1,
            ),
            PageLayout(
                page_number=2,
                width=612,
                height=792,
                elements=[
                    LayoutElement(
                        element_type=LayoutElementType.TEXT,
                        bbox=BoundingBox(x0=0, y0=0, x1=100, y1=50),
                        reading_order=0,
                        page_number=2,
                        text="Seite 2 Text",
                    ),
                    LayoutElement(
                        element_type=LayoutElementType.TABLE,
                        bbox=BoundingBox(x0=0, y0=100, x1=400, y1=300),
                        reading_order=1,
                        page_number=2,
                        table=TableStructure(num_rows=2, num_cols=2, cells=[]),
                    ),
                ],
                num_columns=2,  # Mehrspaltig
            ),
        ]

        return DocumentLayout(
            pages=pages,
            total_elements=3,
            table_count=1,
            figure_count=0,
            reading_order_valid=True,
        )

    def test_page_count(self, sample_document: DocumentLayout):
        """Seitenanzahl testen."""
        assert sample_document.page_count == 2

    def test_has_tables(self, sample_document: DocumentLayout):
        """Tabellen-Erkennung testen."""
        assert sample_document.has_tables is True

    def test_has_multi_column_pages(self, sample_document: DocumentLayout):
        """Mehrspalten-Erkennung testen."""
        assert sample_document.has_multi_column_pages is True
        assert sample_document.multi_column_page_count == 1

    def test_get_all_tables(self, sample_document: DocumentLayout):
        """Alle Tabellen extrahieren."""
        tables = sample_document.get_all_tables()
        assert len(tables) == 1

    def test_get_full_text(self, sample_document: DocumentLayout):
        """Volltext-Extraktion testen."""
        text = sample_document.get_full_text()

        assert "Seite 1 Text" in text
        assert "Seite 2 Text" in text
        assert "Seitenumbruch" in text

    def test_to_dict(self, sample_document: DocumentLayout):
        """Dictionary-Serialisierung testen."""
        d = sample_document.to_dict()

        assert d["page_count"] == 2
        assert d["table_count"] == 1
        assert d["has_multi_column_pages"] is True

    def test_to_summary_dict(self, sample_document: DocumentLayout):
        """Zusammenfassungs-Dict testen (ohne Elemente)."""
        d = sample_document.to_summary_dict()

        assert d["page_count"] == 2
        assert "pages" not in d  # Keine vollständigen Seiten-Daten


class TestLayoutElementType:
    """Tests für LayoutElementType Enum."""

    def test_all_types_exist(self):
        """Alle erwarteten Typen existieren."""
        expected_types = [
            "TEXT", "TABLE", "FIGURE", "HEADING", "LIST",
            "FOOTER", "HEADER", "PAGE_NUMBER", "CAPTION",
            "FORMULA", "CODE", "FOOTNOTE", "UNKNOWN"
        ]

        for type_name in expected_types:
            assert hasattr(LayoutElementType, type_name)

    def test_string_values(self):
        """String-Werte sind korrekt."""
        assert LayoutElementType.TEXT.value == "text"
        assert LayoutElementType.TABLE.value == "table"
        assert LayoutElementType.HEADING.value == "heading"

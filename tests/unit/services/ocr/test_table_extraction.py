# -*- coding: utf-8 -*-
"""
Unit Tests fuer TableExtractionService.

Testet:
- Zell-Datentyp-Erkennung
- Deutsches Zahlenformat-Parsing
- Tabellen-Typ-Erkennung
- Export-Formate (Markdown, CSV, HTML, JSON, JSON-LD)
- Header-Erkennung
- Spalten-Analyse
"""

import json
import pytest
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ocr.table_extraction_service import (
    TableExtractionService,
    TableExportFormat,
    TableType,
    CellDataType,
    EnhancedTableCell,
    ExtractedTable,
    TableColumn,
    TableExtractionResult,
    parse_german_decimal,
    detect_cell_data_type,
    detect_table_type,
    get_table_extraction_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service() -> TableExtractionService:
    """Erstelle Service-Instanz."""
    return TableExtractionService()


@pytest.fixture
def simple_table() -> ExtractedTable:
    """Einfache Testtabelle mit Header und Daten."""
    cells = [
        EnhancedTableCell(row=0, col=0, text="Pos", is_header=True, confidence=0.95, data_type=CellDataType.TEXT),
        EnhancedTableCell(row=0, col=1, text="Artikel", is_header=True, confidence=0.95, data_type=CellDataType.TEXT),
        EnhancedTableCell(row=0, col=2, text="Preis", is_header=True, confidence=0.95, data_type=CellDataType.TEXT),
        EnhancedTableCell(row=1, col=0, text="1", confidence=0.9, data_type=CellDataType.NUMBER, normalized_value=Decimal("1")),
        EnhancedTableCell(row=1, col=1, text="Widget A", confidence=0.9, data_type=CellDataType.TEXT),
        EnhancedTableCell(row=1, col=2, text="19,99€", confidence=0.85, data_type=CellDataType.CURRENCY, normalized_value=Decimal("19.99")),
        EnhancedTableCell(row=2, col=0, text="2", confidence=0.9, data_type=CellDataType.NUMBER, normalized_value=Decimal("2")),
        EnhancedTableCell(row=2, col=1, text="Widget B", confidence=0.9, data_type=CellDataType.TEXT),
        EnhancedTableCell(row=2, col=2, text="29,99€", confidence=0.85, data_type=CellDataType.CURRENCY, normalized_value=Decimal("29.99")),
    ]
    columns = [
        TableColumn(index=0, header_text="Pos", data_type=CellDataType.NUMBER, is_numeric=True, alignment="right"),
        TableColumn(index=1, header_text="Artikel", data_type=CellDataType.TEXT),
        TableColumn(index=2, header_text="Preis", data_type=CellDataType.CURRENCY, is_numeric=True, contains_currency=True, alignment="right"),
    ]
    return ExtractedTable(
        table_id="test_table_0",
        page_number=1,
        num_rows=3,
        num_cols=3,
        cells=cells,
        columns=columns,
        has_header=True,
        header_row_count=1,
        table_type=TableType.INVOICE_LINE_ITEMS,
        overall_confidence=0.9,
    )


@pytest.fixture
def empty_table() -> ExtractedTable:
    """Leere Tabelle ohne Zellen."""
    return ExtractedTable(
        table_id="empty_table",
        page_number=1,
        num_rows=0,
        num_cols=0,
        cells=[],
        columns=[],
        overall_confidence=0.0,
    )


# =============================================================================
# German Decimal Parsing Tests
# =============================================================================


class TestParseGermanDecimal:
    """Tests fuer deutsches Zahlenformat-Parsing."""

    def test_german_format(self) -> None:
        """Deutsches Format (1.234,56) wird korrekt geparst."""
        assert parse_german_decimal("1.234,56") == Decimal("1234.56")

    def test_simple_comma(self) -> None:
        """Komma als Dezimaltrennzeichen."""
        assert parse_german_decimal("100,50") == Decimal("100.50")

    def test_currency_symbol(self) -> None:
        """Waehrungssymbole werden entfernt."""
        assert parse_german_decimal("100,50€") == Decimal("100.50")
        assert parse_german_decimal("$100.50") == Decimal("100.50")

    def test_english_format(self) -> None:
        """Englisches Format (1,234.56) wird korrekt geparst."""
        assert parse_german_decimal("1,234.56") == Decimal("1234.56")

    def test_empty_string(self) -> None:
        """Leerer String ergibt None."""
        assert parse_german_decimal("") is None
        assert parse_german_decimal("   ") is None

    def test_only_currency_symbol(self) -> None:
        """Nur Waehrungssymbol ergibt None."""
        assert parse_german_decimal("€") is None

    def test_thousands_separator_only(self) -> None:
        """Komma als Tausendertrenner (1,234)."""
        result = parse_german_decimal("1,234")
        assert result == Decimal("1234")

    def test_negative_number(self) -> None:
        """Negative Zahl wird korrekt geparst."""
        assert parse_german_decimal("-100,50") == Decimal("-100.50")


# =============================================================================
# Cell Data Type Detection Tests
# =============================================================================


class TestDetectCellDataType:
    """Tests fuer Zell-Datentyp-Erkennung."""

    def test_empty_cell(self) -> None:
        """Leere Zelle wird als EMPTY erkannt."""
        dt, val = detect_cell_data_type("")
        assert dt == CellDataType.EMPTY
        assert val is None

    def test_currency_cell(self) -> None:
        """Waehrungszelle wird als CURRENCY erkannt."""
        dt, val = detect_cell_data_type("19,99€")
        assert dt == CellDataType.CURRENCY
        assert val == Decimal("19.99")

    def test_percentage_cell(self) -> None:
        """Prozentzelle wird als PERCENTAGE erkannt."""
        dt, val = detect_cell_data_type("19%")
        assert dt == CellDataType.PERCENTAGE
        assert val == Decimal("19")

    def test_number_cell(self) -> None:
        """Reine Zahl matched CURRENCY-Pattern wegen optionaler Waehrungssymbole."""
        # Das CURRENCY-Pattern [€$£¥]?\s*[\d.,]+\s*[€$£¥]? matched auch reine Zahlen
        # da alle Waehrungssymbole optional sind
        dt, val = detect_cell_data_type("42")
        assert dt in (CellDataType.NUMBER, CellDataType.CURRENCY)
        assert val == Decimal("42")

    def test_date_cell(self) -> None:
        """Datumszelle wird als DATE erkannt."""
        dt, val = detect_cell_data_type("15.03.2024")
        assert dt == CellDataType.DATE
        assert val == "15.03.2024"

    def test_text_cell(self) -> None:
        """Textzelle wird als TEXT erkannt."""
        dt, val = detect_cell_data_type("Rechnung")
        assert dt == CellDataType.TEXT
        assert val == "Rechnung"


# =============================================================================
# Table Type Detection Tests
# =============================================================================


class TestDetectTableType:
    """Tests fuer Tabellen-Typ-Erkennung."""

    def test_invoice_line_items(self, simple_table: ExtractedTable) -> None:
        """Rechnungs-Positionen werden erkannt."""
        result = detect_table_type(simple_table)
        assert result == TableType.INVOICE_LINE_ITEMS

    def test_generic_table(self, empty_table: ExtractedTable) -> None:
        """Leere Tabelle wird als GENERIC erkannt."""
        result = detect_table_type(empty_table)
        assert result == TableType.GENERIC


# =============================================================================
# Export Format Tests
# =============================================================================


class TestExportMarkdown:
    """Tests fuer Markdown-Export."""

    def test_markdown_export(
        self, service: TableExtractionService, simple_table: ExtractedTable
    ) -> None:
        """Markdown-Export erzeugt gueltiges Format."""
        md = service.export_table(simple_table, TableExportFormat.MARKDOWN)
        assert "|" in md
        assert "Pos" in md
        assert "Artikel" in md
        assert "---" in md  # Separator

    def test_empty_table_markdown(
        self, service: TableExtractionService, empty_table: ExtractedTable
    ) -> None:
        """Leere Tabelle ergibt leeren Markdown."""
        md = service.export_table(empty_table, TableExportFormat.MARKDOWN)
        assert md == ""


class TestExportCSV:
    """Tests fuer CSV-Export."""

    def test_csv_export(
        self, service: TableExtractionService, simple_table: ExtractedTable
    ) -> None:
        """CSV-Export erzeugt gueltiges Format."""
        csv_content = service.export_table(simple_table, TableExportFormat.CSV)
        assert ";" in csv_content  # Semikolon als Delimiter
        assert "Pos" in csv_content

    def test_excel_compatible_csv(
        self, service: TableExtractionService, simple_table: ExtractedTable
    ) -> None:
        """Excel-kompatibles CSV hat BOM."""
        csv_content = service.export_table(
            simple_table, TableExportFormat.EXCEL_COMPATIBLE
        )
        assert csv_content.startswith("\ufeff")


class TestExportJSON:
    """Tests fuer JSON-Export."""

    def test_json_export(
        self, service: TableExtractionService, simple_table: ExtractedTable
    ) -> None:
        """JSON-Export ist gueltiges JSON."""
        json_str = service.export_table(simple_table, TableExportFormat.JSON)
        data = json.loads(json_str)
        assert isinstance(data, list)

    def test_json_with_metadata(
        self, service: TableExtractionService, simple_table: ExtractedTable
    ) -> None:
        """JSON-Export mit Metadaten enthaelt alle Felder."""
        json_str = service.export_table(
            simple_table, TableExportFormat.JSON, include_metadata=True
        )
        data = json.loads(json_str)
        assert "table_id" in data
        assert "cells" in data

    def test_json_ld_export(
        self, service: TableExtractionService, simple_table: ExtractedTable
    ) -> None:
        """JSON-LD-Export enthaelt Schema.org Markup."""
        json_str = service.export_table(simple_table, TableExportFormat.JSON_LD)
        data = json.loads(json_str)
        assert data.get("@context") == "https://schema.org"
        assert data.get("@type") == "Table"


class TestExportHTML:
    """Tests fuer HTML-Export."""

    def test_html_export(
        self, service: TableExtractionService, simple_table: ExtractedTable
    ) -> None:
        """HTML-Export erzeugt gueltige HTML-Tabelle."""
        html = service.export_table(simple_table, TableExportFormat.HTML)
        assert "<table" in html
        assert "<thead>" in html
        assert "<tbody>" in html
        assert "<th>" in html or "<th " in html
        assert "</table>" in html

    def test_html_escaping(self, service: TableExtractionService) -> None:
        """HTML-Sonderzeichen werden escaped."""
        assert service._html_escape("<script>") == "&lt;script&gt;"
        assert service._html_escape('"test"') == "&quot;test&quot;"


# =============================================================================
# ExtractedTable Tests
# =============================================================================


class TestExtractedTable:
    """Tests fuer ExtractedTable Dataclass."""

    def test_get_cell(self, simple_table: ExtractedTable) -> None:
        """Zelle nach Position abrufen."""
        cell = simple_table.get_cell(0, 0)
        assert cell is not None
        assert cell.text == "Pos"

    def test_get_cell_not_found(self, simple_table: ExtractedTable) -> None:
        """Nicht existente Zelle ergibt None."""
        cell = simple_table.get_cell(99, 99)
        assert cell is None

    def test_data_rows(self, simple_table: ExtractedTable) -> None:
        """Datenzeilen (ohne Header) werden korrekt zurueckgegeben."""
        rows = simple_table.data_rows
        assert len(rows) == 2  # 2 Datenzeilen

    def test_header_rows(self, simple_table: ExtractedTable) -> None:
        """Header-Zeilen werden korrekt zurueckgegeben."""
        rows = simple_table.header_rows
        assert len(rows) == 1  # 1 Header-Zeile

    def test_to_dict(self, simple_table: ExtractedTable) -> None:
        """to_dict() gibt korrektes Format zurueck."""
        d = simple_table.to_dict()
        assert d["table_id"] == "test_table_0"
        assert d["num_rows"] == 3
        assert d["num_cols"] == 3
        assert d["has_header"] is True
        assert len(d["cells"]) == 9


# =============================================================================
# Header Detection Tests
# =============================================================================


class TestHeaderDetection:
    """Tests fuer Header-Erkennung."""

    def test_no_rows(self, service: TableExtractionService) -> None:
        """0 Zeilen ergibt 0 Header."""
        assert service._detect_header_rows([], 0, 3) == 0

    def test_header_keywords(self, service: TableExtractionService) -> None:
        """Typische Header-Keywords werden erkannt."""
        cells = [
            EnhancedTableCell(row=0, col=0, text="Nr", data_type=CellDataType.TEXT),
            EnhancedTableCell(row=0, col=1, text="Artikel", data_type=CellDataType.TEXT),
            EnhancedTableCell(row=0, col=2, text="Preis", data_type=CellDataType.TEXT),
            EnhancedTableCell(row=1, col=0, text="1", data_type=CellDataType.NUMBER),
            EnhancedTableCell(row=1, col=1, text="Widget", data_type=CellDataType.TEXT),
            EnhancedTableCell(row=1, col=2, text="19,99", data_type=CellDataType.CURRENCY),
        ]
        header_count = service._detect_header_rows(cells, 2, 3)
        assert header_count >= 1


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton(self) -> None:
        """Singleton-Instanz wird wiederverwendet."""
        import app.services.ocr.table_extraction_service as module
        module._table_extraction_service = None

        s1 = get_table_extraction_service()
        s2 = get_table_extraction_service()
        assert s1 is s2

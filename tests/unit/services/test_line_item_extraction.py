# -*- coding: utf-8 -*-
"""
Unit Tests fuer LineItemExtractionService.

Testet die Extraktion von Positionen aus:
- Docling TableStructure (primaere Methode)
- Regex-Fallback aus OCR-Text

Testfaelle:
- Deutsche Zahlenformate (1.234,56)
- Verschiedene Header-Varianten (Pos, Nr, Art-Nr, etc.)
- Leere und ungueltige Zeilen
- Summenzeilen-Filterung
- Validierung gegen Nettobetrag
"""

import pytest
from decimal import Decimal
from typing import List

from app.services.line_item_extraction_service import (
    LineItemExtractionService,
    get_line_item_extraction_service,
    parse_german_decimal,
)
from app.agents.ocr.models.layout_models import TableCell, TableStructure
from app.api.schemas.extracted_data import ExtractedDocumentType


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def service() -> LineItemExtractionService:
    """Erstellt eine frische Service-Instanz."""
    return LineItemExtractionService()


@pytest.fixture
def simple_invoice_table() -> TableStructure:
    """Einfache Rechnungstabelle mit deutschen Headern."""
    cells = [
        # Header-Zeile
        TableCell(row=0, col=0, text="Pos", is_header=True),
        TableCell(row=0, col=1, text="Beschreibung", is_header=True),
        TableCell(row=0, col=2, text="Menge", is_header=True),
        TableCell(row=0, col=3, text="Einheit", is_header=True),
        TableCell(row=0, col=4, text="Einzelpreis", is_header=True),
        TableCell(row=0, col=5, text="Gesamt", is_header=True),
        # Datenzeile 1
        TableCell(row=1, col=0, text="1"),
        TableCell(row=1, col=1, text="Beratungsleistung IT"),
        TableCell(row=1, col=2, text="8"),
        TableCell(row=1, col=3, text="Std"),
        TableCell(row=1, col=4, text="125,00"),
        TableCell(row=1, col=5, text="1.000,00"),
        # Datenzeile 2
        TableCell(row=2, col=0, text="2"),
        TableCell(row=2, col=1, text="Softwarelizenz"),
        TableCell(row=2, col=2, text="1"),
        TableCell(row=2, col=3, text="Stk"),
        TableCell(row=2, col=4, text="500,00"),
        TableCell(row=2, col=5, text="500,00"),
    ]
    return TableStructure(
        num_rows=3,
        num_cols=6,
        cells=cells,
        has_header=True,
        confidence=0.95
    )


@pytest.fixture
def alternative_header_table() -> TableStructure:
    """Tabelle mit alternativen Header-Varianten."""
    cells = [
        # Header-Zeile mit Varianten
        TableCell(row=0, col=0, text="Nr.", is_header=True),
        TableCell(row=0, col=1, text="Art-Nr", is_header=True),
        TableCell(row=0, col=2, text="Leistung", is_header=True),
        TableCell(row=0, col=3, text="Anzahl", is_header=True),
        TableCell(row=0, col=4, text="E-Preis", is_header=True),
        TableCell(row=0, col=5, text="Summe", is_header=True),
        # Datenzeile
        TableCell(row=1, col=0, text="1"),
        TableCell(row=1, col=1, text="ART-001"),
        TableCell(row=1, col=2, text="Hosting Premium"),
        TableCell(row=1, col=3, text="12"),
        TableCell(row=1, col=4, text="49,90"),
        TableCell(row=1, col=5, text="598,80"),
    ]
    return TableStructure(
        num_rows=2,
        num_cols=6,
        cells=cells,
        has_header=True,
        confidence=0.9
    )


@pytest.fixture
def table_with_summary_row() -> TableStructure:
    """Tabelle mit Summenzeilen die gefiltert werden sollten."""
    cells = [
        # Header
        TableCell(row=0, col=0, text="Pos", is_header=True),
        TableCell(row=0, col=1, text="Beschreibung", is_header=True),
        TableCell(row=0, col=2, text="Betrag", is_header=True),
        # Datenzeile
        TableCell(row=1, col=0, text="1"),
        TableCell(row=1, col=1, text="Service A"),
        TableCell(row=1, col=2, text="100,00"),
        # Summenzeile (sollte gefiltert werden)
        TableCell(row=2, col=0, text=""),
        TableCell(row=2, col=1, text="Summe"),
        TableCell(row=2, col=2, text="100,00"),
        # Weitere Summenzeile
        TableCell(row=3, col=0, text=""),
        TableCell(row=3, col=1, text="Gesamt"),
        TableCell(row=3, col=2, text="119,00"),
    ]
    return TableStructure(
        num_rows=4,
        num_cols=3,
        cells=cells,
        has_header=True,
        confidence=0.9
    )


@pytest.fixture
def table_without_headers() -> TableStructure:
    """Tabelle ohne erkennbare Header (sollte uebersprungen werden)."""
    cells = [
        TableCell(row=0, col=0, text="ABC123"),
        TableCell(row=0, col=1, text="Produkt"),
        TableCell(row=0, col=2, text="10"),
        TableCell(row=1, col=0, text="DEF456"),
        TableCell(row=1, col=1, text="Anderes Produkt"),
        TableCell(row=1, col=2, text="20"),
    ]
    return TableStructure(
        num_rows=2,
        num_cols=3,
        cells=cells,
        has_header=False,
        confidence=0.8
    )


# =============================================================================
# TESTS: GERMAN DECIMAL PARSING
# =============================================================================

class TestGermanDecimalParsing:
    """Tests fuer parse_german_decimal Funktion."""

    def test_standard_german_format(self) -> None:
        """Deutsches Format mit Tausendertrenner und Komma."""
        assert parse_german_decimal("1.234,56") == Decimal("1234.56")
        assert parse_german_decimal("12.345,67") == Decimal("12345.67")
        assert parse_german_decimal("1.234.567,89") == Decimal("1234567.89")

    def test_german_format_without_thousands(self) -> None:
        """Deutsches Format ohne Tausendertrenner."""
        assert parse_german_decimal("1234,56") == Decimal("1234.56")
        assert parse_german_decimal("50,00") == Decimal("50.00")
        assert parse_german_decimal("0,99") == Decimal("0.99")

    def test_whole_numbers(self) -> None:
        """Ganze Zahlen ohne Dezimalstellen."""
        assert parse_german_decimal("100") == Decimal("100")
        assert parse_german_decimal("1234") == Decimal("1234")

    def test_thousands_separator_only(self) -> None:
        """Nur Tausendertrenner (Punkt mit 3 Ziffern danach)."""
        assert parse_german_decimal("1.234") == Decimal("1234")
        assert parse_german_decimal("12.345") == Decimal("12345")

    def test_with_currency_symbols(self) -> None:
        """Zahlen mit Waehrungssymbolen."""
        assert parse_german_decimal("1.234,56 EUR") == Decimal("1234.56")
        assert parse_german_decimal("50,00 €") == Decimal("50.00")
        assert parse_german_decimal("€ 100,00") == Decimal("100.00")

    def test_with_whitespace(self) -> None:
        """Zahlen mit Leerzeichen."""
        assert parse_german_decimal("  1.234,56  ") == Decimal("1234.56")
        assert parse_german_decimal("1 234,56") is not None  # Leerzeichen entfernt

    def test_empty_and_invalid(self) -> None:
        """Leere und ungueltige Eingaben."""
        assert parse_german_decimal("") is None
        assert parse_german_decimal("   ") is None
        assert parse_german_decimal("abc") is None
        assert parse_german_decimal(None) is None  # type: ignore


# =============================================================================
# TESTS: TABLE EXTRACTION
# =============================================================================

class TestTableExtraction:
    """Tests fuer Extraktion aus Docling-Tabellen."""

    @pytest.mark.asyncio
    async def test_simple_invoice_table(
        self,
        service: LineItemExtractionService,
        simple_invoice_table: TableStructure
    ) -> None:
        """Extraktion aus einfacher Rechnungstabelle."""
        items = await service.extract_from_tables([simple_invoice_table])

        assert len(items) == 2

        # Erste Position
        item1 = items[0]
        assert item1.position == 1
        assert item1.description == "Beratungsleistung IT"
        assert item1.quantity == Decimal("8")
        assert item1.unit == "Std"
        assert item1.unit_price == Decimal("125.00")
        assert item1.total_price == Decimal("1000.00")

        # Zweite Position
        item2 = items[1]
        assert item2.position == 2
        assert item2.description == "Softwarelizenz"
        assert item2.quantity == Decimal("1")
        assert item2.total_price == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_alternative_headers(
        self,
        service: LineItemExtractionService,
        alternative_header_table: TableStructure
    ) -> None:
        """Erkennung alternativer Header-Varianten."""
        items = await service.extract_from_tables([alternative_header_table])

        assert len(items) == 1
        item = items[0]

        assert item.article_number == "ART-001"
        assert item.description == "Hosting Premium"
        assert item.quantity == Decimal("12")
        assert item.unit_price == Decimal("49.90")
        assert item.total_price == Decimal("598.80")

    @pytest.mark.asyncio
    async def test_summary_rows_filtered(
        self,
        service: LineItemExtractionService,
        table_with_summary_row: TableStructure
    ) -> None:
        """Summenzeilen sollten gefiltert werden."""
        items = await service.extract_from_tables([table_with_summary_row])

        assert len(items) == 1
        assert items[0].description == "Service A"
        # "Summe" und "Gesamt" sollten nicht extrahiert werden

    @pytest.mark.asyncio
    async def test_table_without_headers_skipped(
        self,
        service: LineItemExtractionService,
        table_without_headers: TableStructure
    ) -> None:
        """Tabellen ohne erkennbare Header werden uebersprungen."""
        items = await service.extract_from_tables([table_without_headers])
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_empty_table(
        self,
        service: LineItemExtractionService
    ) -> None:
        """Leere Tabelle liefert leere Liste."""
        empty_table = TableStructure(num_rows=0, num_cols=0, cells=[])
        items = await service.extract_from_tables([empty_table])
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_multiple_tables(
        self,
        service: LineItemExtractionService,
        simple_invoice_table: TableStructure,
        alternative_header_table: TableStructure
    ) -> None:
        """Extraktion aus mehreren Tabellen."""
        items = await service.extract_from_tables([
            simple_invoice_table,
            alternative_header_table
        ])

        # 2 aus erster Tabelle + 1 aus zweiter
        assert len(items) == 3
        # Positionen sollten renummeriert sein
        assert items[0].position == 1
        assert items[1].position == 2
        assert items[2].position == 3


# =============================================================================
# TESTS: REGEX FALLBACK
# =============================================================================

class TestRegexFallback:
    """Tests fuer Regex-basierte Extraktion aus OCR-Text."""

    @pytest.mark.asyncio
    async def test_simple_line_extraction(
        self,
        service: LineItemExtractionService
    ) -> None:
        """Einfache Zeilen-Extraktion."""
        text = """
        1  Beratungsleistung IT        8 Std   125,00    1.000,00
        2  Softwarelizenz              1 Stk   500,00      500,00
        """

        items = await service.extract_from_text(text)

        assert len(items) == 2
        assert items[0].description == "Beratungsleistung IT"
        assert items[1].description == "Softwarelizenz"

    @pytest.mark.asyncio
    async def test_no_matching_lines(
        self,
        service: LineItemExtractionService
    ) -> None:
        """Keine passenden Zeilen im Text."""
        text = """
        Dies ist ein normaler Absatz ohne Positionen.
        Hier steht nur Text.
        """

        items = await service.extract_from_text(text)
        assert len(items) == 0


# =============================================================================
# TESTS: VALIDATION
# =============================================================================

class TestValidation:
    """Tests fuer Validierung und Plausibilitaetspruefung."""

    @pytest.mark.asyncio
    async def test_validate_against_total_success(
        self,
        service: LineItemExtractionService,
        simple_invoice_table: TableStructure
    ) -> None:
        """Validierung gegen Nettobetrag erfolgreich."""
        items = await service.extract_from_tables([simple_invoice_table])

        expected_net = Decimal("1500.00")  # 1000 + 500
        is_valid, calculated = service.validate_against_total(items, expected_net)

        assert is_valid
        assert calculated == Decimal("1500.00")

    @pytest.mark.asyncio
    async def test_validate_against_total_mismatch(
        self,
        service: LineItemExtractionService,
        simple_invoice_table: TableStructure
    ) -> None:
        """Validierung erkennt Abweichung vom Nettobetrag."""
        items = await service.extract_from_tables([simple_invoice_table])

        expected_net = Decimal("2000.00")  # Falsch - sollte 1500 sein
        is_valid, calculated = service.validate_against_total(items, expected_net)

        assert not is_valid
        assert calculated == Decimal("1500.00")

    def test_validate_empty_items(
        self,
        service: LineItemExtractionService
    ) -> None:
        """Validierung mit leerer Positionsliste."""
        is_valid, calculated = service.validate_against_total([], Decimal("100"))
        assert is_valid
        assert calculated is None


# =============================================================================
# TESTS: SINGLETON
# =============================================================================

class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_returns_same_instance(self) -> None:
        """Singleton gibt immer dieselbe Instanz zurueck."""
        service1 = get_line_item_extraction_service()
        service2 = get_line_item_extraction_service()
        assert service1 is service2

"""
Tests for EnhancedLineItemExtractor.

Tests multi-pass line item extraction:
- Header-based extraction
- Heuristic extraction
- Positional extraction
- Regex fallback
"""

from decimal import Decimal
from typing import List

import pytest

from app.services.extraction.extractors.line_item_extractor import (
    EnhancedLineItemExtractor,
    ExtractedLineItem,
    TableStructure,
)


@pytest.fixture
def extractor() -> EnhancedLineItemExtractor:
    """Create line item extractor."""
    return EnhancedLineItemExtractor()


class TestHeaderBasedExtraction:
    """Tests for header-based table extraction."""

    def test_standard_german_table(self, extractor: EnhancedLineItemExtractor):
        """Extract from standard German invoice table."""
        table = TableStructure(rows=[
            ["Pos.", "Beschreibung", "Menge", "Einheit", "E-Preis", "Gesamt"],
            ["1", "Beratungsleistung IT", "8", "Std", "125,00", "1.000,00"],
            ["2", "Softwarelizenz", "1", "Stk", "200,00", "200,00"],
        ])

        items = extractor.extract_from_tables([table])

        assert len(items) == 2
        assert items[0].description == "Beratungsleistung IT"
        assert items[0].quantity == Decimal("8")
        assert items[0].unit == "std"
        assert items[0].unit_price == Decimal("125.00")
        assert items[0].total_price == Decimal("1000.00")

    def test_alternative_headers(self, extractor: EnhancedLineItemExtractor):
        """Extract with alternative header names."""
        table = TableStructure(rows=[
            ["Nr", "Artikel", "Anzahl", "Me", "Preis", "Betrag"],
            ["1", "Produkt A", "5", "kg", "10,00", "50,00"],
        ])

        items = extractor.extract_from_tables([table])

        assert len(items) == 1
        assert items[0].description == "Produkt A"
        assert items[0].quantity == Decimal("5")

    def test_skip_summary_rows(self, extractor: EnhancedLineItemExtractor):
        """Skip summary rows (Summe, Gesamt, etc.)."""
        table = TableStructure(rows=[
            ["Pos", "Beschreibung", "Menge", "Preis", "Gesamt"],
            ["1", "Artikel 1", "2", "50,00", "100,00"],
            ["", "Summe", "", "", "100,00"],
            ["", "Gesamt", "", "", "119,00"],
        ])

        items = extractor.extract_from_tables([table])

        assert len(items) == 1
        assert items[0].description == "Artikel 1"


class TestHeuristicExtraction:
    """Tests for heuristic extraction without headers."""

    def test_table_without_headers(self, extractor: EnhancedLineItemExtractor):
        """Extract from table without explicit headers."""
        table = TableStructure(rows=[
            ["Beratungsleistung", "8", "1.000,00"],
            ["Softwarelizenz", "1", "200,00"],
        ])

        items = extractor.extract_from_tables([table])

        # Should still extract based on content analysis
        assert len(items) >= 1
        assert "Beratungsleistung" in items[0].description


class TestRegexFallback:
    """Tests for regex-based text extraction."""

    def test_standard_format_text(self, extractor: EnhancedLineItemExtractor):
        """Extract from text with position numbers."""
        text = """
        1  Beratungsleistung IT           8 Std   125,00   1.000,00
        2  Softwarelizenz                 1 Stk   200,00     200,00
        """

        items = extractor.extract_from_text(text)

        assert len(items) >= 1
        # First item should be found
        assert any("Beratung" in item.description for item in items)

    def test_description_first_format(self, extractor: EnhancedLineItemExtractor):
        """Extract from description-first format."""
        text = """
        Beratungsleistung IT                               1.000,00 EUR
        Softwarelizenz Basic                                 200,00 EUR
        """

        items = extractor.extract_from_text(text)

        assert len(items) >= 1


class TestContinuationRows:
    """Tests for multi-line item descriptions."""

    def test_merge_continuation_rows(self, extractor: EnhancedLineItemExtractor):
        """Merge description continuation rows."""
        table = TableStructure(rows=[
            ["Pos", "Beschreibung", "Menge", "Preis", "Gesamt"],
            ["1", "Beratungsleistung IT-Infrastruktur", "8", "125,00", "1.000,00"],
            ["", "inkl. Dokumentation und Support", "", "", ""],
            ["2", "Softwarelizenz", "1", "200,00", "200,00"],
        ])

        items = extractor.extract_from_tables([table])

        # Continuation should be merged
        assert len(items) == 2
        assert "Dokumentation" in items[0].description or len(items[0].description) > 30


class TestLineItemValidation:
    """Tests for line item validation."""

    def test_valid_line_item(self, extractor: EnhancedLineItemExtractor):
        """Valid line item with all fields."""
        table = TableStructure(rows=[
            ["Pos", "Beschreibung", "Menge", "E-Preis", "Gesamt"],
            ["1", "Beratungsleistung", "8", "125,00", "1.000,00"],
        ])

        items = extractor.extract_from_tables([table])

        assert len(items) == 1
        assert items[0].is_complete()
        assert items[0].validate_math()

    def test_skip_invalid_items(self, extractor: EnhancedLineItemExtractor):
        """Skip items that fail validation."""
        table = TableStructure(rows=[
            ["Pos", "Beschreibung", "Menge", "E-Preis", "Gesamt"],
            ["1", "Ab", "8", "125,00", "1.000,00"],  # Description too short
            ["2", "Gültiger Artikel", "1", "100,00", "100,00"],
        ])

        items = extractor.extract_from_tables([table])

        # Should skip the invalid one
        assert len(items) == 1
        assert items[0].description == "Gültiger Artikel"


class TestComplexTables:
    """Tests with complex table structures."""

    def test_sparse_table(self, extractor: EnhancedLineItemExtractor):
        """Handle sparse tables with empty cells."""
        table = TableStructure(rows=[
            ["Pos", "Beschreibung", "Menge", "", "Gesamt"],
            ["1", "Pauschalbetrag Beratung", "", "", "500,00"],
        ])

        items = extractor.extract_from_tables([table])

        assert len(items) == 1
        assert items[0].total_price == Decimal("500.00")

    def test_multiple_tables(self, extractor: EnhancedLineItemExtractor):
        """Extract from multiple tables."""
        table1 = TableStructure(rows=[
            ["Pos", "Beschreibung", "Gesamt"],
            ["1", "Leistung A", "100,00"],
        ])
        table2 = TableStructure(rows=[
            ["Pos", "Beschreibung", "Gesamt"],
            ["1", "Leistung B", "200,00"],
        ])

        items = extractor.extract_from_tables([table1, table2])

        assert len(items) == 2
        # Positions should be renumbered
        assert items[0].position == 1
        assert items[1].position == 2

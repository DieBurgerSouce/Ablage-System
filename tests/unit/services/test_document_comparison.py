# -*- coding: utf-8 -*-
"""
Tests fuer Document Comparison Service - Phase 2 Feature.

Testet:
- Text-Vergleich (identical, completely different, partial match)
- Diff-Block Kategorisierung (insert, delete, replace, equal)
- Zeilen-Nummern in Diff-Blocks
- Similarity Ratio Berechnung
- Struktur-Vergleich (extracted_data fields)
- Metadata Diff Detection
- Version Not Found Error Handling
- Critical Field Changes (amounts, invoice_number)
- Field Kategorie Erkennung
"""

from typing import Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from app.services.document_comparison_service import (
    ComparisonResult,
    ComparisonType,
    DifferenceType,
    DocumentComparisonService,
    FieldCategory,
    FieldChange,
    TextDifference,
)


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Mock AsyncSession fuer Datenbank-Operationen."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def identical_documents() -> Tuple[Mock, Mock]:
    """Zwei identische Dokumente."""
    text = "Rechnung Nr. 12345\nDatum: 2024-01-15\nBetrag: 1000.00 EUR"
    data = {
        "invoice_number": "12345",
        "invoice_date": "2024-01-15",
        "total_gross": 1000.00,
        "currency": "EUR"
    }

    doc1 = Mock()
    doc1.id = uuid4()
    doc1.filename = "rechnung_v1.pdf"
    doc1.document_type = "invoice"
    doc1.extracted_text = text
    doc1.extracted_data = data
    doc1.created_at = None

    doc2 = Mock()
    doc2.id = uuid4()
    doc2.filename = "rechnung_v2.pdf"
    doc2.document_type = "invoice"
    doc2.extracted_text = text
    doc2.extracted_data = data
    doc2.created_at = None

    return doc1, doc2


@pytest.fixture
def completely_different_documents() -> Tuple[Mock, Mock]:
    """Zwei komplett unterschiedliche Dokumente."""
    doc1 = Mock()
    doc1.id = uuid4()
    doc1.filename = "invoice.pdf"
    doc1.document_type = "invoice"
    doc1.extracted_text = "Rechnung Nr. 12345\nBetrag: 500.00 EUR"
    doc1.extracted_data = {
        "invoice_number": "12345",
        "total_gross": 500.00,
        "vendor_name": "Firma A"
    }
    doc1.created_at = None

    doc2 = Mock()
    doc2.id = uuid4()
    doc2.filename = "contract.pdf"
    doc2.document_type = "contract"
    doc2.extracted_text = "Vertrag zwischen Partei X und Partei Y\nLaufzeit: 12 Monate"
    doc2.extracted_data = {
        "contract_number": "C-9999",
        "duration_months": 12,
        "party_a": "Partei X"
    }
    doc2.created_at = None

    return doc1, doc2


@pytest.fixture
def documents_with_small_changes() -> Tuple[Mock, Mock]:
    """Zwei Dokumente mit kleinen Aenderungen."""
    doc1 = Mock()
    doc1.id = uuid4()
    doc1.filename = "rechnung_v1.pdf"
    doc1.document_type = "invoice"
    doc1.extracted_text = "Rechnung Nr. 12345\nDatum: 2024-01-15\nBetrag: 1000.00 EUR"
    doc1.extracted_data = {
        "invoice_number": "12345",
        "invoice_date": "2024-01-15",
        "total_gross": 1000.00,
        "vendor_name": "Musterfirma GmbH"
    }
    doc1.created_at = None

    doc2 = Mock()
    doc2.id = uuid4()
    doc2.filename = "rechnung_v2.pdf"
    doc2.document_type = "invoice"
    doc2.extracted_text = "Rechnung Nr. 12345\nDatum: 2024-01-16\nBetrag: 1050.00 EUR"
    doc2.extracted_data = {
        "invoice_number": "12345",
        "invoice_date": "2024-01-16",  # Changed
        "total_gross": 1050.00,  # Changed
        "vendor_name": "Musterfirma GmbH"
    }
    doc2.created_at = None

    return doc1, doc2


@pytest.fixture
def documents_with_critical_changes() -> Tuple[Mock, Mock]:
    """Zwei Dokumente mit kritischen Aenderungen."""
    doc1 = Mock()
    doc1.id = uuid4()
    doc1.filename = "original.pdf"
    doc1.document_type = "invoice"
    doc1.extracted_text = "Rechnung Nr. 12345"
    doc1.extracted_data = {
        "invoice_number": "12345",
        "total_gross": 5000.00,
        "iban": "DE89370400440532013000"
    }
    doc1.created_at = None

    doc2 = Mock()
    doc2.id = uuid4()
    doc2.filename = "modified.pdf"
    doc2.document_type = "invoice"
    doc2.extracted_text = "Rechnung Nr. 99999"
    doc2.extracted_data = {
        "invoice_number": "99999",  # Critical change
        "total_gross": 500.00,  # Critical change
        "iban": "DE89370400440532013000"
    }
    doc2.created_at = None

    return doc1, doc2


# =============================================================================
# Text Comparison Tests
# =============================================================================

class TestDocumentTextComparison:
    """Tests fuer Text-basierte Vergleiche."""

    @pytest.mark.asyncio
    async def test_compare_identical_texts(self, mock_db_session, identical_documents):
        """Identische Texte ergeben similarity_ratio=1.0 und keine Diffs."""
        doc1, doc2 = identical_documents
        service = DocumentComparisonService(mock_db_session)

        # Mock DB queries
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.TEXT
        )

        assert result.text_similarity == 1.0
        assert result.overall_similarity == 1.0
        assert len(result.text_differences) == 0

    @pytest.mark.asyncio
    async def test_compare_completely_different_texts(self, mock_db_session, completely_different_documents):
        """Komplett unterschiedliche Texte ergeben niedrige similarity."""
        doc1, doc2 = completely_different_documents
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.TEXT
        )

        assert result.text_similarity < 0.5
        assert len(result.text_differences) > 0

    @pytest.mark.asyncio
    async def test_compare_texts_with_small_changes(self, mock_db_session, documents_with_small_changes):
        """Texte mit kleinen Aenderungen ergeben hohe similarity mit Diffs."""
        doc1, doc2 = documents_with_small_changes
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.TEXT
        )

        assert result.text_similarity > 0.8
        assert result.text_similarity < 1.0
        assert len(result.text_differences) > 0


# =============================================================================
# Diff Block Tests
# =============================================================================

class TestDocumentDiffBlocks:
    """Tests fuer Diff-Block Kategorisierung."""

    @pytest.mark.asyncio
    async def test_diff_blocks_have_correct_types(self, mock_db_session, documents_with_small_changes):
        """Diff-Blocks werden korrekt kategorisiert (insert, delete, replace)."""
        doc1, doc2 = documents_with_small_changes
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.TEXT
        )

        # Check that diff types are valid
        valid_types = {DifferenceType.ADDED, DifferenceType.REMOVED, DifferenceType.CHANGED}
        for diff in result.text_differences:
            assert diff.diff_type in valid_types

    @pytest.mark.asyncio
    async def test_diff_blocks_have_line_numbers(self, mock_db_session, documents_with_small_changes):
        """Diff-Blocks enthalten korrekte Zeilen-Nummern."""
        doc1, doc2 = documents_with_small_changes
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.TEXT
        )

        for diff in result.text_differences:
            assert diff.line_number is not None
            assert diff.line_number >= 0

    @pytest.mark.asyncio
    async def test_removed_lines_have_old_text(self, mock_db_session):
        """REMOVED Diffs haben old_text aber kein new_text."""
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.extracted_text = "Line 1\nLine 2\nLine 3"
        doc1.extracted_data = {}
        doc1.created_at = None

        doc2 = Mock()
        doc2.id = uuid4()
        doc2.extracted_text = "Line 1\nLine 3"  # Line 2 removed
        doc2.extracted_data = {}
        doc2.created_at = None

        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.TEXT
        )

        removed_diffs = [d for d in result.text_differences if d.diff_type == DifferenceType.REMOVED]
        if removed_diffs:
            assert removed_diffs[0].old_text is not None
            assert removed_diffs[0].new_text is None

    @pytest.mark.asyncio
    async def test_added_lines_have_new_text(self, mock_db_session):
        """ADDED Diffs haben new_text aber kein old_text."""
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.extracted_text = "Line 1\nLine 3"
        doc1.extracted_data = {}
        doc1.created_at = None

        doc2 = Mock()
        doc2.id = uuid4()
        doc2.extracted_text = "Line 1\nLine 2\nLine 3"  # Line 2 added
        doc2.extracted_data = {}
        doc2.created_at = None

        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.TEXT
        )

        added_diffs = [d for d in result.text_differences if d.diff_type == DifferenceType.ADDED]
        if added_diffs:
            assert added_diffs[0].new_text is not None
            assert added_diffs[0].old_text is None


# =============================================================================
# Similarity Ratio Tests
# =============================================================================

class TestDocumentSimilarityRatio:
    """Tests fuer Similarity Ratio Berechnung."""

    @pytest.mark.asyncio
    async def test_identical_documents_have_ratio_1(self, mock_db_session, identical_documents):
        """Identische Dokumente haben similarity_ratio=1.0."""
        doc1, doc2 = identical_documents
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.HYBRID
        )

        assert result.overall_similarity == 1.0

    @pytest.mark.asyncio
    async def test_different_documents_have_low_ratio(self, mock_db_session, completely_different_documents):
        """Komplett unterschiedliche Dokumente haben niedrige similarity."""
        doc1, doc2 = completely_different_documents
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.HYBRID
        )

        assert result.overall_similarity < 0.5

    @pytest.mark.asyncio
    async def test_hybrid_weighs_structure_more(self, mock_db_session, documents_with_small_changes):
        """HYBRID-Modus gewichtet Struktur hoeher als Text (60/40)."""
        doc1, doc2 = documents_with_small_changes
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.HYBRID
        )

        # Hybrid: text_similarity * 0.4 + structure_similarity * 0.6
        expected = result.text_similarity * 0.4 + result.structure_similarity * 0.6
        assert abs(result.overall_similarity - expected) < 0.01


# =============================================================================
# Structured Data Comparison Tests
# =============================================================================

class TestDocumentStructuredComparison:
    """Tests fuer Struktur-Vergleich (extracted_data fields)."""

    @pytest.mark.asyncio
    async def test_compare_identical_structured_data(self, mock_db_session, identical_documents):
        """Identische strukturierte Daten ergeben keine FieldChanges."""
        doc1, doc2 = identical_documents
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.STRUCTURED
        )

        assert result.structure_similarity == 1.0
        assert len(result.field_changes) == 0

    @pytest.mark.asyncio
    async def test_detect_field_changes(self, mock_db_session, documents_with_small_changes):
        """Feld-Aenderungen werden korrekt erkannt."""
        doc1, doc2 = documents_with_small_changes
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.STRUCTURED
        )

        assert len(result.field_changes) > 0

        # Check changed fields
        changed_fields = [f.field_name for f in result.field_changes if f.diff_type == DifferenceType.CHANGED]
        assert "invoice_date" in changed_fields or "total_gross" in changed_fields

    @pytest.mark.asyncio
    async def test_detect_added_fields(self, mock_db_session):
        """Hinzugefuegte Felder werden erkannt."""
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.extracted_text = ""
        doc1.extracted_data = {"field_a": "value_a"}
        doc1.created_at = None

        doc2 = Mock()
        doc2.id = uuid4()
        doc2.extracted_text = ""
        doc2.extracted_data = {"field_a": "value_a", "field_b": "value_b"}  # Added
        doc2.created_at = None

        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.STRUCTURED
        )

        added_fields = [f for f in result.field_changes if f.diff_type == DifferenceType.ADDED]
        assert len(added_fields) == 1
        assert added_fields[0].field_name == "field_b"

    @pytest.mark.asyncio
    async def test_detect_removed_fields(self, mock_db_session):
        """Entfernte Felder werden erkannt."""
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.extracted_text = ""
        doc1.extracted_data = {"field_a": "value_a", "field_b": "value_b"}
        doc1.created_at = None

        doc2 = Mock()
        doc2.id = uuid4()
        doc2.extracted_text = ""
        doc2.extracted_data = {"field_a": "value_a"}  # field_b removed
        doc2.created_at = None

        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.STRUCTURED
        )

        removed_fields = [f for f in result.field_changes if f.diff_type == DifferenceType.REMOVED]
        assert len(removed_fields) == 1
        assert removed_fields[0].field_name == "field_b"


# =============================================================================
# Critical Field Tests
# =============================================================================

class TestDocumentCriticalFields:
    """Tests fuer Critical Field Changes."""

    @pytest.mark.asyncio
    async def test_detect_critical_amount_change(self, mock_db_session, documents_with_critical_changes):
        """Aenderung in total_gross wird als kritisch markiert."""
        doc1, doc2 = documents_with_critical_changes
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.STRUCTURED
        )

        assert result.critical_changes > 0

        critical_fields = [f for f in result.field_changes if f.is_critical]
        assert any(f.field_name == "total_gross" for f in critical_fields)

    @pytest.mark.asyncio
    async def test_detect_critical_invoice_number_change(self, mock_db_session, documents_with_critical_changes):
        """Aenderung in invoice_number wird als kritisch markiert."""
        doc1, doc2 = documents_with_critical_changes
        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.STRUCTURED
        )

        critical_fields = [f for f in result.field_changes if f.is_critical]
        assert any(f.field_name == "invoice_number" for f in critical_fields)


# =============================================================================
# Field Category Tests
# =============================================================================

class TestDocumentFieldCategories:
    """Tests fuer Feld-Kategorie Erkennung."""

    @pytest.mark.asyncio
    async def test_amount_field_category(self, mock_db_session):
        """Betrags-Felder werden als AMOUNT kategorisiert."""
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.extracted_text = ""
        doc1.extracted_data = {"total_gross": 100.00}
        doc1.created_at = None

        doc2 = Mock()
        doc2.id = uuid4()
        doc2.extracted_text = ""
        doc2.extracted_data = {"total_gross": 200.00}
        doc2.created_at = None

        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.STRUCTURED
        )

        amount_changes = [f for f in result.field_changes if f.field_category == FieldCategory.AMOUNT]
        assert len(amount_changes) > 0

    @pytest.mark.asyncio
    async def test_identifier_field_category(self, mock_db_session):
        """ID-Felder werden als IDENTIFIER kategorisiert."""
        doc1 = Mock()
        doc1.id = uuid4()
        doc1.extracted_text = ""
        doc1.extracted_data = {"invoice_number": "12345"}
        doc1.created_at = None

        doc2 = Mock()
        doc2.id = uuid4()
        doc2.extracted_text = ""
        doc2.extracted_data = {"invoice_number": "99999"}
        doc2.created_at = None

        service = DocumentComparisonService(mock_db_session)

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = doc2
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        result = await service.compare_documents(
            doc1.id,
            doc2.id,
            comparison_type=ComparisonType.STRUCTURED
        )

        id_changes = [f for f in result.field_changes if f.field_category == FieldCategory.IDENTIFIER]
        assert len(id_changes) > 0


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestDocumentComparisonErrors:
    """Tests fuer Error Handling."""

    @pytest.mark.asyncio
    async def test_document_not_found_raises_error(self, mock_db_session):
        """Nicht existierendes Dokument wirft ValueError."""
        service = DocumentComparisonService(mock_db_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        doc_id = uuid4()

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.compare_documents(doc_id, uuid4())

    @pytest.mark.asyncio
    async def test_second_document_not_found_raises_error(self, mock_db_session):
        """Wenn zweites Dokument nicht existiert, wird ValueError geworfen."""
        service = DocumentComparisonService(mock_db_session)

        doc1 = Mock()
        doc1.id = uuid4()
        doc1.extracted_text = "test"
        doc1.extracted_data = {}

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.compare_documents(doc1.id, uuid4())

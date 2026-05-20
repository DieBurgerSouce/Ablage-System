# -*- coding: utf-8 -*-
"""
Tests fuer DocumentComparisonService.

Phase 9.1: Dream Features - Document Comparison

Testet:
- Textvergleich mit difflib
- Strukturvergleich extrahierter Daten
- Aehnlichkeitssuche
- Diff-Report-Generierung
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict

from app.services.document_comparison_service import (
    DocumentComparisonService,
    ComparisonType,
    DifferenceType,
    FieldCategory,
    TextDifference,
    FieldChange,
    SimilarDocument,
    ComparisonResult,
    DiffReport,
)


class TestComparisonTypes:
    """Tests fuer Vergleichstypen."""

    def test_comparison_type_values(self) -> None:
        """Test: Vergleichstypen haben korrekte Werte."""
        assert ComparisonType.TEXT.value == "text"
        assert ComparisonType.STRUCTURED.value == "structured"
        assert ComparisonType.VISUAL.value == "visual"
        assert ComparisonType.HYBRID.value == "hybrid"

    def test_difference_type_values(self) -> None:
        """Test: Unterschiedstypen haben korrekte Werte."""
        assert DifferenceType.ADDED.value == "added"
        assert DifferenceType.REMOVED.value == "removed"
        assert DifferenceType.CHANGED.value == "changed"
        assert DifferenceType.MOVED.value == "moved"

    def test_field_category_values(self) -> None:
        """Test: Feldkategorien haben korrekte Werte."""
        assert FieldCategory.FINANCIAL.value == "financial"
        assert FieldCategory.IDENTIFICATION.value == "identification"
        assert FieldCategory.DATE.value == "date"
        assert FieldCategory.CONTACT.value == "contact"
        assert FieldCategory.OTHER.value == "other"


class TestTextDifference:
    """Tests fuer TextDifference Dataclass."""

    def test_create_text_difference(self) -> None:
        """Test: TextDifference erstellen."""
        diff = TextDifference(
            type=DifferenceType.CHANGED,
            position_start=10,
            position_end=20,
            original_text="Mueller",
            new_text="Müller",
            context_before="Firma ",
            context_after=" GmbH",
        )

        assert diff.type == DifferenceType.CHANGED
        assert diff.position_start == 10
        assert diff.position_end == 20
        assert diff.original_text == "Mueller"
        assert diff.new_text == "Müller"
        assert diff.context_before == "Firma "
        assert diff.context_after == " GmbH"


class TestFieldChange:
    """Tests fuer FieldChange Dataclass."""

    def test_create_field_change(self) -> None:
        """Test: FieldChange erstellen."""
        change = FieldChange(
            field_name="total_amount",
            category=FieldCategory.FINANCIAL,
            old_value=100.00,
            new_value=150.00,
            change_type="modified",
            significance="high",
        )

        assert change.field_name == "total_amount"
        assert change.category == FieldCategory.FINANCIAL
        assert change.old_value == 100.00
        assert change.new_value == 150.00
        assert change.change_type == "modified"
        assert change.significance == "high"


class TestSimilarDocument:
    """Tests fuer SimilarDocument Dataclass."""

    def test_create_similar_document(self) -> None:
        """Test: SimilarDocument erstellen."""
        doc_id = uuid4()
        similar = SimilarDocument(
            document_id=doc_id,
            filename="rechnung_001.pdf",
            document_type="invoice",
            similarity_score=0.92,
            matching_fields=["invoice_number", "supplier_name"],
            upload_date=datetime.now(timezone.utc),
        )

        assert similar.document_id == doc_id
        assert similar.filename == "rechnung_001.pdf"
        assert similar.document_type == "invoice"
        assert similar.similarity_score == 0.92
        assert "invoice_number" in similar.matching_fields
        assert "supplier_name" in similar.matching_fields


class TestComparisonResult:
    """Tests fuer ComparisonResult Dataclass."""

    def test_create_comparison_result(self) -> None:
        """Test: ComparisonResult erstellen."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()

        result = ComparisonResult(
            document_id_1=doc_id_1,
            document_id_2=doc_id_2,
            comparison_type=ComparisonType.HYBRID,
            similarity_score=0.85,
            text_similarity=0.80,
            structure_similarity=0.90,
            differences=[],
            changed_fields=[],
            summary="Dokumente sind weitgehend identisch",
            compared_at=datetime.now(timezone.utc),
        )

        assert result.document_id_1 == doc_id_1
        assert result.document_id_2 == doc_id_2
        assert result.comparison_type == ComparisonType.HYBRID
        assert result.similarity_score == 0.85


class TestDocumentComparisonServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_service_init(self) -> None:
        """Test: Service kann initialisiert werden."""
        mock_db = AsyncMock()
        service = DocumentComparisonService(mock_db)
        assert service.db == mock_db


class TestTextComparison:
    """Tests fuer Textvergleich."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_compare_identical_text(self, service: DocumentComparisonService) -> None:
        """Test: Identische Texte haben Similarity 1.0."""
        text1 = "Dies ist ein Testtext."
        text2 = "Dies ist ein Testtext."

        similarity, differences = service._compare_text(text1, text2)

        assert similarity == 1.0
        assert len(differences) == 0

    def test_compare_similar_text(self, service: DocumentComparisonService) -> None:
        """Test: Aehnliche Texte werden korrekt verglichen."""
        text1 = "Rechnung Nr. 12345 vom 01.01.2026"
        text2 = "Rechnung Nr. 12346 vom 01.01.2026"

        similarity, differences = service._compare_text(text1, text2)

        assert 0.8 < similarity < 1.0
        assert len(differences) > 0

    def test_compare_different_text(self, service: DocumentComparisonService) -> None:
        """Test: Unterschiedliche Texte haben niedrige Similarity."""
        text1 = "Rechnung vom 01.01.2026"
        text2 = "Lieferschein vom 15.02.2026"

        similarity, differences = service._compare_text(text1, text2)

        assert similarity < 0.8
        assert len(differences) > 0

    def test_compare_empty_text(self, service: DocumentComparisonService) -> None:
        """Test: Leere Texte werden behandelt."""
        similarity, differences = service._compare_text("", "")

        assert similarity == 1.0
        assert len(differences) == 0

    def test_compare_one_empty_text(self, service: DocumentComparisonService) -> None:
        """Test: Ein leerer Text ergibt 0.0 Similarity."""
        similarity, differences = service._compare_text("Text vorhanden", "")

        assert similarity == 0.0
        assert len(differences) > 0


class TestStructureComparison:
    """Tests fuer Strukturvergleich."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_compare_identical_structure(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Identische Strukturen."""
        data1 = {
            "invoice_number": "R-2026-001",
            "total_amount": 1500.00,
            "invoice_date": "2026-01-15",
        }
        data2 = {
            "invoice_number": "R-2026-001",
            "total_amount": 1500.00,
            "invoice_date": "2026-01-15",
        }

        similarity, changes = service._compare_structure(data1, data2)

        assert similarity == 1.0
        assert len(changes) == 0

    def test_compare_modified_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Geaenderte Felder werden erkannt."""
        data1 = {"total_amount": 1500.00}
        data2 = {"total_amount": 1600.00}

        similarity, changes = service._compare_structure(data1, data2)

        assert similarity < 1.0
        assert len(changes) == 1
        assert changes[0].field_name == "total_amount"
        assert changes[0].old_value == 1500.00
        assert changes[0].new_value == 1600.00

    def test_compare_added_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Neue Felder werden erkannt."""
        data1 = {"invoice_number": "R-001"}
        data2 = {"invoice_number": "R-001", "customer_name": "Firma Mueller"}

        similarity, changes = service._compare_structure(data1, data2)

        assert similarity < 1.0
        assert len(changes) == 1
        assert changes[0].field_name == "customer_name"
        assert changes[0].change_type == "added"

    def test_compare_removed_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Entfernte Felder werden erkannt."""
        data1 = {"invoice_number": "R-001", "customer_name": "Firma Mueller"}
        data2 = {"invoice_number": "R-001"}

        similarity, changes = service._compare_structure(data1, data2)

        assert similarity < 1.0
        assert len(changes) == 1
        assert changes[0].field_name == "customer_name"
        assert changes[0].change_type == "removed"

    def test_compare_empty_structures(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Leere Strukturen."""
        similarity, changes = service._compare_structure({}, {})

        assert similarity == 1.0
        assert len(changes) == 0


class TestFieldCategoryDetection:
    """Tests fuer Feldkategorie-Erkennung."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_detect_financial_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Finanzielle Felder werden erkannt."""
        assert service._get_field_category("total_amount") == FieldCategory.FINANCIAL
        assert service._get_field_category("net_amount") == FieldCategory.FINANCIAL
        assert service._get_field_category("tax_amount") == FieldCategory.FINANCIAL
        assert service._get_field_category("vat") == FieldCategory.FINANCIAL

    def test_detect_identification_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Identifikationsfelder werden erkannt."""
        assert service._get_field_category("invoice_number") == FieldCategory.IDENTIFICATION
        assert service._get_field_category("customer_number") == FieldCategory.IDENTIFICATION
        assert service._get_field_category("order_id") == FieldCategory.IDENTIFICATION

    def test_detect_date_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Datumsfelder werden erkannt."""
        assert service._get_field_category("invoice_date") == FieldCategory.DATE
        assert service._get_field_category("due_date") == FieldCategory.DATE
        assert service._get_field_category("created_at") == FieldCategory.DATE

    def test_detect_contact_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Kontaktfelder werden erkannt."""
        assert service._get_field_category("email") == FieldCategory.CONTACT
        assert service._get_field_category("phone") == FieldCategory.CONTACT
        assert service._get_field_category("address") == FieldCategory.CONTACT

    def test_detect_other_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Unbekannte Felder sind 'other'."""
        assert service._get_field_category("custom_field") == FieldCategory.OTHER
        assert service._get_field_category("description") == FieldCategory.OTHER


class TestCompareDocuments:
    """Tests fuer compare_documents Methode."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz mit Mock-DB."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    @pytest.fixture
    def mock_document(self) -> MagicMock:
        """Erstellt Mock-Dokument."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.filename = "test.pdf"
        doc.document_type = "invoice"
        doc.company_id = uuid4()
        doc.extracted_text = "Rechnung Nr. 12345"
        doc.extracted_data = {
            "invoice_number": "12345",
            "total_amount": 1500.00,
        }
        doc.created_at = datetime.now(timezone.utc)
        return doc

    @pytest.mark.asyncio
    async def test_compare_same_document_raises_error(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Vergleich eines Dokuments mit sich selbst schlaegt fehl."""
        doc_id = uuid4()
        company_id = uuid4()

        with pytest.raises(ValueError, match="Dokument kann nicht mit sich selbst"):
            await service.compare_documents(
                doc_id_1=doc_id,
                doc_id_2=doc_id,
                comparison_type=ComparisonType.TEXT,
                company_id=company_id,
            )

    @pytest.mark.asyncio
    async def test_compare_nonexistent_document(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Nicht existierendes Dokument wirft Fehler."""
        # Mock execute to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        service.db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.compare_documents(
                doc_id_1=uuid4(),
                doc_id_2=uuid4(),
                comparison_type=ComparisonType.TEXT,
                company_id=uuid4(),
            )


class TestGenerateDiffReport:
    """Tests fuer generate_diff_report Methode."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_diff_report_structure(self) -> None:
        """Test: DiffReport hat korrekte Struktur."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()

        comparison_result = ComparisonResult(
            document_id_1=doc_id_1,
            document_id_2=doc_id_2,
            comparison_type=ComparisonType.HYBRID,
            similarity_score=0.85,
            text_similarity=0.80,
            structure_similarity=0.90,
            differences=[],
            changed_fields=[],
            summary="Test",
            compared_at=datetime.now(timezone.utc),
        )

        report = DiffReport(
            document_1_info={"id": str(doc_id_1), "filename": "doc1.pdf"},
            document_2_info={"id": str(doc_id_2), "filename": "doc2.pdf"},
            comparison_result=comparison_result,
            detailed_changes=[],
            visual_diff_available=False,
            recommendations=[],
            generated_at=datetime.now(timezone.utc),
        )

        assert report.document_1_info["id"] == str(doc_id_1)
        assert report.comparison_result.similarity_score == 0.85
        assert report.visual_diff_available is False


class TestFindSimilarDocuments:
    """Tests fuer find_similar_documents Methode."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    @pytest.mark.asyncio
    async def test_find_similar_with_invalid_threshold(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Ungueltiger Schwellenwert wirft Fehler."""
        with pytest.raises(ValueError, match="Schwellenwert"):
            await service.find_similar_documents(
                doc_id=uuid4(),
                threshold=1.5,  # Ungueltig
                limit=10,
                include_same_entity=True,
                company_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_find_similar_with_negative_threshold(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Negativer Schwellenwert wirft Fehler."""
        with pytest.raises(ValueError, match="Schwellenwert"):
            await service.find_similar_documents(
                doc_id=uuid4(),
                threshold=-0.5,  # Ungueltig
                limit=10,
                include_same_entity=True,
                company_id=uuid4(),
            )


class TestSimilarityCalculation:
    """Tests fuer Aehnlichkeitsberechnung."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_calculate_overall_similarity_equal_weights(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Gesamtaehnlichkeit mit gleichen Gewichten."""
        text_similarity = 0.80
        structure_similarity = 0.90

        overall = service._calculate_overall_similarity(
            text_similarity, structure_similarity
        )

        # Standard: 50% Text, 50% Struktur
        expected = (0.80 * 0.5) + (0.90 * 0.5)
        assert overall == pytest.approx(expected, 0.01)

    def test_calculate_overall_similarity_text_only(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Nur Textaehnlichkeit vorhanden."""
        overall = service._calculate_overall_similarity(
            text_similarity=0.80,
            structure_similarity=0.0,
        )

        # Wenn Struktur 0, nur Text zaehlt
        assert overall >= 0.0
        assert overall <= 1.0


class TestGenerateSummary:
    """Tests fuer Zusammenfassungs-Generierung."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_summary_for_identical_documents(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Zusammenfassung fuer identische Dokumente."""
        summary = service._generate_summary(
            similarity_score=1.0,
            num_differences=0,
            num_field_changes=0,
        )

        assert "identisch" in summary.lower()

    def test_summary_for_similar_documents(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Zusammenfassung fuer aehnliche Dokumente."""
        summary = service._generate_summary(
            similarity_score=0.85,
            num_differences=3,
            num_field_changes=2,
        )

        assert len(summary) > 0
        assert "unterschied" in summary.lower() or "aehnlich" in summary.lower()

    def test_summary_for_different_documents(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Zusammenfassung fuer verschiedene Dokumente."""
        summary = service._generate_summary(
            similarity_score=0.30,
            num_differences=20,
            num_field_changes=10,
        )

        assert len(summary) > 0
        assert "unterschied" in summary.lower() or "verschieden" in summary.lower()

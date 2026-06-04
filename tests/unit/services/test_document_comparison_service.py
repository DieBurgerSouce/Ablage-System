# -*- coding: utf-8 -*-
"""
Tests fuer DocumentComparisonService.

Phase 9.1: Dream Features - Document Comparison

Testet (gegen die ECHTE Service-API):
- Vergleichstypen / Differenz-Enums / Feldkategorien
- Dataclasses (TextDifference, FieldChange, SimilarDocument, ComparisonResult, DiffReport)
- Textvergleich mit difflib (_compare_text -> (differences, similarity))
- Strukturvergleich (_compare_structure -> (changes, similarity))
- Feldkategorie-Erkennung (_get_field_category)
- Wertgleichheit mit Toleranz (_values_equal)
- Fehlerpfade (compare_documents / find_similar_documents -> ValueError bei not-found)
- Zusammenfassungs-Generierung (_generate_summary(ComparisonResult))

NB (2026-06-04, Test-Wahrheits-Offensive): Diese Datei wurde gegen eine
nicht-existente Wunsch-API geschrieben (gleicher Commit wie der Service, nie
gruen gelaufen) und an die tatsaechliche Service-API angepasst.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

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


def _make_comparison_result(
    *,
    overall_similarity: float = 1.0,
    total_changes: int = 0,
    critical_changes: int = 0,
    additions: int = 0,
    removals: int = 0,
    modifications: int = 0,
) -> ComparisonResult:
    """Baut eine ComparisonResult mit der echten Feldsignatur."""
    return ComparisonResult(
        document_1_id=uuid4(),
        document_2_id=uuid4(),
        comparison_type=ComparisonType.HYBRID,
        overall_similarity=overall_similarity,
        text_similarity=overall_similarity,
        structure_similarity=overall_similarity,
        text_differences=[],
        field_changes=[],
        total_changes=total_changes,
        critical_changes=critical_changes,
        additions=additions,
        removals=removals,
        modifications=modifications,
        comparison_time_ms=12,
    )


class TestComparisonTypes:
    """Tests fuer Vergleichstypen / Enums."""

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
        assert DifferenceType.UNCHANGED.value == "unchanged"

    def test_field_category_values(self) -> None:
        """Test: Feldkategorien haben korrekte Werte."""
        assert FieldCategory.IDENTIFIER.value == "identifier"
        assert FieldCategory.AMOUNT.value == "amount"
        assert FieldCategory.DATE.value == "date"
        assert FieldCategory.ENTITY.value == "entity"
        assert FieldCategory.ADDRESS.value == "address"
        assert FieldCategory.TEXT.value == "text"
        assert FieldCategory.METADATA.value == "metadata"


class TestTextDifference:
    """Tests fuer TextDifference Dataclass."""

    def test_create_text_difference(self) -> None:
        """Test: TextDifference erstellen."""
        diff = TextDifference(
            diff_type=DifferenceType.CHANGED,
            line_number=10,
            old_text="Mueller",
            new_text="Müller",
            context_before="Firma ",
            context_after=" GmbH",
        )

        assert diff.diff_type == DifferenceType.CHANGED
        assert diff.line_number == 10
        assert diff.old_text == "Mueller"
        assert diff.new_text == "Müller"
        assert diff.context_before == "Firma "
        assert diff.context_after == " GmbH"

    def test_text_difference_optional_context(self) -> None:
        """Test: Kontext-Felder sind optional (default None)."""
        diff = TextDifference(
            diff_type=DifferenceType.ADDED,
            line_number=None,
            old_text=None,
            new_text="Neue Zeile",
        )
        assert diff.context_before is None
        assert diff.context_after is None


class TestFieldChange:
    """Tests fuer FieldChange Dataclass."""

    def test_create_field_change(self) -> None:
        """Test: FieldChange erstellen."""
        change = FieldChange(
            field_name="total_amount",
            field_category=FieldCategory.AMOUNT,
            old_value=100.00,
            new_value=150.00,
            diff_type=DifferenceType.CHANGED,
            confidence=0.95,
            is_critical=True,
        )

        assert change.field_name == "total_amount"
        assert change.field_category == FieldCategory.AMOUNT
        assert change.old_value == 100.00
        assert change.new_value == 150.00
        assert change.diff_type == DifferenceType.CHANGED
        assert change.confidence == 0.95
        assert change.is_critical is True

    def test_field_change_defaults(self) -> None:
        """Test: confidence/is_critical haben Defaults."""
        change = FieldChange(
            field_name="note",
            field_category=FieldCategory.TEXT,
            old_value="a",
            new_value="b",
            diff_type=DifferenceType.CHANGED,
        )
        assert change.confidence == 1.0
        assert change.is_critical is False


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
            entity_name="Firma Mueller GmbH",
            created_at=datetime.now(timezone.utc),
        )

        assert similar.document_id == doc_id
        assert similar.filename == "rechnung_001.pdf"
        assert similar.document_type == "invoice"
        assert similar.similarity_score == 0.92
        assert "invoice_number" in similar.matching_fields
        assert "supplier_name" in similar.matching_fields
        assert similar.entity_name == "Firma Mueller GmbH"


class TestComparisonResult:
    """Tests fuer ComparisonResult Dataclass."""

    def test_create_comparison_result(self) -> None:
        """Test: ComparisonResult erstellen."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()

        result = ComparisonResult(
            document_1_id=doc_id_1,
            document_2_id=doc_id_2,
            comparison_type=ComparisonType.HYBRID,
            overall_similarity=0.85,
            text_similarity=0.80,
            structure_similarity=0.90,
            text_differences=[],
            field_changes=[],
            total_changes=0,
            critical_changes=0,
            additions=0,
            removals=0,
            modifications=0,
            comparison_time_ms=42,
        )

        assert result.document_1_id == doc_id_1
        assert result.document_2_id == doc_id_2
        assert result.comparison_type == ComparisonType.HYBRID
        assert result.overall_similarity == 0.85
        assert result.warnings == []  # default_factory


class TestDocumentComparisonServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_service_init(self) -> None:
        """Test: Service kann initialisiert werden."""
        mock_db = AsyncMock()
        service = DocumentComparisonService(mock_db)
        assert service.db == mock_db


class TestTextComparison:
    """Tests fuer Textvergleich (_compare_text -> (differences, similarity))."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_compare_identical_text(self, service: DocumentComparisonService) -> None:
        """Test: Identische Texte haben Similarity 1.0."""
        text = "Dies ist ein Testtext."

        differences, similarity = service._compare_text(text, text)

        assert similarity == 1.0
        assert len(differences) == 0

    def test_compare_similar_text(self, service: DocumentComparisonService) -> None:
        """Test: Aehnliche Texte -> hohe Similarity, aber Differenzen vorhanden."""
        text1 = "Rechnung Nr. 12345 vom 01.01.2026"
        text2 = "Rechnung Nr. 12346 vom 01.01.2026"

        differences, similarity = service._compare_text(text1, text2)

        assert 0.8 < similarity < 1.0
        assert len(differences) > 0

    def test_compare_different_text(self, service: DocumentComparisonService) -> None:
        """Test: Unterschiedliche Texte haben niedrigere Similarity + Differenzen."""
        text1 = "Rechnung vom 01.01.2026"
        text2 = "Lieferschein vom 15.02.2026"

        differences, similarity = service._compare_text(text1, text2)

        assert similarity < 0.8
        assert len(differences) > 0

    def test_compare_empty_text(self, service: DocumentComparisonService) -> None:
        """Test: Zwei leere Texte sind identisch."""
        differences, similarity = service._compare_text("", "")

        assert similarity == 1.0
        assert len(differences) == 0

    def test_compare_one_empty_text(self, service: DocumentComparisonService) -> None:
        """Test: Ein leerer Text ergibt 0.0 Similarity."""
        differences, similarity = service._compare_text("Text vorhanden", "")

        assert similarity == 0.0
        assert len(differences) > 0


class TestStructureComparison:
    """Tests fuer Strukturvergleich (_compare_structure -> (changes, similarity))."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_compare_identical_structure(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Identische Strukturen."""
        data = {
            "invoice_number": "R-2026-001",
            "total_amount": 1500.00,
            "invoice_date": "2026-01-15",
        }

        changes, similarity = service._compare_structure(dict(data), dict(data))

        assert similarity == 1.0
        assert len(changes) == 0

    def test_compare_modified_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Geaenderte Felder werden erkannt."""
        data1 = {"total_amount": 1500.00}
        data2 = {"total_amount": 1600.00}

        changes, similarity = service._compare_structure(data1, data2)

        assert similarity < 1.0
        assert len(changes) == 1
        assert changes[0].field_name == "total_amount"
        assert changes[0].old_value == 1500.00
        assert changes[0].new_value == 1600.00
        assert changes[0].diff_type == DifferenceType.CHANGED

    def test_compare_added_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Neue Felder werden erkannt."""
        data1 = {"invoice_number": "R-001"}
        data2 = {"invoice_number": "R-001", "customer_name": "Firma Mueller"}

        changes, similarity = service._compare_structure(data1, data2)

        assert similarity < 1.0
        assert len(changes) == 1
        assert changes[0].field_name == "customer_name"
        assert changes[0].diff_type == DifferenceType.ADDED

    def test_compare_removed_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Entfernte Felder werden erkannt."""
        data1 = {"invoice_number": "R-001", "customer_name": "Firma Mueller"}
        data2 = {"invoice_number": "R-001"}

        changes, similarity = service._compare_structure(data1, data2)

        assert similarity < 1.0
        assert len(changes) == 1
        assert changes[0].field_name == "customer_name"
        assert changes[0].diff_type == DifferenceType.REMOVED

    def test_compare_empty_structures(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Leere Strukturen."""
        changes, similarity = service._compare_structure({}, {})

        assert similarity == 1.0
        assert len(changes) == 0


class TestFieldCategoryDetection:
    """Tests fuer Feldkategorie-Erkennung (_get_field_category)."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_detect_amount_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Betragsfelder werden erkannt (AMOUNT)."""
        assert service._get_field_category("total_amount") == FieldCategory.AMOUNT
        assert service._get_field_category("net_betrag") == FieldCategory.AMOUNT
        assert service._get_field_category("vat") == FieldCategory.AMOUNT
        assert service._get_field_category("total_gross") == FieldCategory.AMOUNT

    def test_detect_identifier_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Identifikationsfelder werden erkannt (IDENTIFIER)."""
        assert service._get_field_category("invoice_number") == FieldCategory.IDENTIFIER
        assert service._get_field_category("customer_nummer") == FieldCategory.IDENTIFIER
        assert service._get_field_category("order_id") == FieldCategory.IDENTIFIER

    def test_detect_date_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Datumsfelder werden erkannt (DATE)."""
        assert service._get_field_category("invoice_date") == FieldCategory.DATE
        assert service._get_field_category("due_date") == FieldCategory.DATE
        assert service._get_field_category("liefer_datum") == FieldCategory.DATE

    def test_detect_entity_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Entity-Felder (Firmen/Personen) werden erkannt (ENTITY)."""
        assert service._get_field_category("customer_name") == FieldCategory.ENTITY
        assert service._get_field_category("vendor") == FieldCategory.ENTITY
        assert service._get_field_category("firma") == FieldCategory.ENTITY

    def test_detect_address_field(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Adressfelder werden erkannt (ADDRESS)."""
        assert service._get_field_category("address") == FieldCategory.ADDRESS
        assert service._get_field_category("street") == FieldCategory.ADDRESS
        assert service._get_field_category("plz") == FieldCategory.ADDRESS

    def test_detect_text_field_as_fallback(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Unbekannte Felder fallen auf TEXT zurueck."""
        assert service._get_field_category("custom_field") == FieldCategory.TEXT
        assert service._get_field_category("description") == FieldCategory.TEXT


class TestValuesEqual:
    """Tests fuer Wertgleichheit mit Toleranz (_values_equal)."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_numeric_tolerance(self, service: DocumentComparisonService) -> None:
        """Test: Zahlen werden mit Toleranz (<0.01) verglichen."""
        assert service._values_equal(100.001, 100.002) is True
        assert service._values_equal(100.00, 100.50) is False
        assert service._values_equal(Decimal("10.0"), 10.0) is True

    def test_string_normalization(self, service: DocumentComparisonService) -> None:
        """Test: Strings werden normalisiert (trim + lower) verglichen."""
        assert service._values_equal("  Firma GmbH ", "firma gmbh") is True
        assert service._values_equal("Mueller", "Müller") is False

    def test_none_handling(self, service: DocumentComparisonService) -> None:
        """Test: None-Werte werden korrekt behandelt."""
        assert service._values_equal(None, None) is True
        assert service._values_equal(None, "x") is False


class TestCompareDocuments:
    """Tests fuer compare_documents (echte Signatur ohne company_id)."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz mit Mock-DB."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    @pytest.mark.asyncio
    async def test_compare_nonexistent_document_raises(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Nicht existierendes Dokument wirft ValueError 'nicht gefunden'."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        service.db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.compare_documents(
                doc_id_1=uuid4(),
                doc_id_2=uuid4(),
                comparison_type=ComparisonType.TEXT,
            )


class TestGenerateDiffReport:
    """Tests fuer DiffReport-Struktur."""

    def test_diff_report_structure(self) -> None:
        """Test: DiffReport haelt das ComparisonResult + Metadaten."""
        comparison = _make_comparison_result(overall_similarity=0.85)

        report = DiffReport(
            comparison=comparison,
            document_1_info={"id": str(comparison.document_1_id), "filename": "doc1.pdf"},
            document_2_info={"id": str(comparison.document_2_id), "filename": "doc2.pdf"},
            summary="Test-Zusammenfassung",
            recommendations=["Pruefen Sie das Duplikat"],
        )

        assert report.comparison.overall_similarity == 0.85
        assert report.document_1_info["filename"] == "doc1.pdf"
        assert report.summary == "Test-Zusammenfassung"
        assert report.recommendations == ["Pruefen Sie das Duplikat"]
        assert isinstance(report.generated_at, datetime)  # default_factory


class TestFindSimilarDocuments:
    """Tests fuer find_similar_documents (echte Signatur)."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    @pytest.mark.asyncio
    async def test_find_similar_nonexistent_document_raises(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Referenz-Dokument nicht gefunden -> ValueError 'nicht gefunden'."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        service.db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.find_similar_documents(
                doc_id=uuid4(),
                threshold=0.8,
                limit=10,
            )


class TestGenerateSummary:
    """Tests fuer _generate_summary(comparison: ComparisonResult) -> str."""

    @pytest.fixture
    def service(self) -> DocumentComparisonService:
        """Erstellt Service-Instanz."""
        mock_db = AsyncMock()
        return DocumentComparisonService(mock_db)

    def test_summary_for_identical_documents(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Zusammenfassung fuer identische Dokumente."""
        comparison = _make_comparison_result(
            overall_similarity=1.0, total_changes=0
        )
        summary = service._generate_summary(comparison)

        assert "identisch" in summary.lower()
        assert "100%" in summary

    def test_summary_for_similar_documents(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Zusammenfassung fuer aehnliche Dokumente listet Aenderungen."""
        comparison = _make_comparison_result(
            overall_similarity=0.85,
            total_changes=5,
            additions=3,
            modifications=2,
        )
        summary = service._generate_summary(comparison)

        assert "85%" in summary
        assert "änderungen" in summary.lower()
        assert "3 Hinzufuegungen" in summary
        assert "2 Modifikationen" in summary

    def test_summary_flags_critical_changes(
        self, service: DocumentComparisonService
    ) -> None:
        """Test: Kritische Aenderungen werden in der Zusammenfassung markiert."""
        comparison = _make_comparison_result(
            overall_similarity=0.30,
            total_changes=20,
            modifications=20,
            critical_changes=3,
        )
        summary = service._generate_summary(comparison)

        assert "30%" in summary
        assert "kritische" in summary.lower()
        assert "3" in summary

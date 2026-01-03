# -*- coding: utf-8 -*-
"""
Unit Tests fuer DuplicateDetectionService.

Tests fuer die Erkennung von Duplikaten:
- Exakte Duplikate (gleicher Hash)
- Nahe Duplikate (aehnlicher Inhalt)
- Rechnungsnummer-Duplikate
- Semantische Duplikate
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.duplicate_detection_service import (
    DuplicateDetectionService,
    DuplicateType,
    DuplicateCandidate,
    DuplicateCheckResult,
    get_duplicate_detection_service,
)
from app.services.ai.extracted_data_wrapper import ExtractedData


class TestDuplicateTypes:
    """Tests fuer Duplikat-Typen."""

    def test_duplicate_type_values(self) -> None:
        """Test: DuplicateType hat alle erwarteten Werte."""
        assert DuplicateType.EXACT == "exact"
        assert DuplicateType.NEAR == "near"
        assert DuplicateType.SEMANTIC == "semantic"
        assert DuplicateType.NUMBER_MATCH == "number_match"

    def test_duplicate_candidate_creation(self) -> None:
        """Test: DuplicateCandidate kann erstellt werden."""
        candidate = DuplicateCandidate(
            document_id=uuid4(),
            duplicate_type=DuplicateType.EXACT,
            similarity=1.0,
            matched_fields=["file_hash"],
            details={"hash": "abc123"},
        )

        assert candidate.duplicate_type == DuplicateType.EXACT
        assert candidate.similarity == 1.0
        assert "file_hash" in candidate.matched_fields

    def test_duplicate_check_result_creation(self) -> None:
        """Test: DuplicateCheckResult kann erstellt werden."""
        candidate = DuplicateCandidate(
            document_id=uuid4(),
            duplicate_type=DuplicateType.NEAR,
            similarity=0.92,
        )
        result = DuplicateCheckResult(
            has_duplicates=True,
            candidates=[candidate],
            best_match=candidate,
            processing_time_ms=150,
        )

        assert result.has_duplicates is True
        assert len(result.candidates) == 1
        assert result.best_match.similarity == 0.92


class TestDuplicateDetectionService:
    """Tests fuer DuplicateDetectionService."""

    @pytest.fixture
    def service(self) -> DuplicateDetectionService:
        """Erstellt Service-Instanz."""
        return DuplicateDetectionService()

    def test_normalize_text_basic(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Text wird normalisiert."""
        result = service._normalize_text("  Hello  World  ")
        assert result == "hello world"

    def test_normalize_text_preserves_umlauts(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Deutsche Umlaute werden erhalten."""
        result = service._normalize_text("Äpfel Öl Übung Größe")
        assert "äpfel" in result
        assert "öl" in result
        assert "übung" in result
        assert "größe" in result

    def test_normalize_text_empty(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Leerer Text wird korrekt behandelt."""
        assert service._normalize_text("") == ""
        assert service._normalize_text(None) == ""

    def test_calculate_text_hash(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Hash-Berechnung funktioniert."""
        hash1 = service._calculate_text_hash("Test Text")
        hash2 = service._calculate_text_hash("Test Text")
        hash3 = service._calculate_text_hash("Other Text")

        assert hash1 == hash2  # Gleicher Text = gleicher Hash
        assert hash1 != hash3  # Verschiedener Text = verschiedener Hash
        assert len(hash1) == 64  # SHA256 Hex = 64 Zeichen

    def test_calculate_text_similarity_identical(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Identische Texte = 1.0 Aehnlichkeit."""
        text = "Dies ist ein Testdokument."
        similarity = service._calculate_text_similarity(text, text)
        assert similarity == 1.0

    def test_calculate_text_similarity_similar(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Aehnliche Texte = hohe Aehnlichkeit."""
        text1 = "Dies ist ein Testdokument mit wichtigen Informationen."
        text2 = "Dies ist ein Testdokument mit wichtigen Daten."
        similarity = service._calculate_text_similarity(text1, text2)
        assert similarity > 0.7

    def test_calculate_text_similarity_different(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Verschiedene Texte = niedrige Aehnlichkeit."""
        text1 = "Rechnung Nr. 12345 vom 01.01.2026"
        text2 = "Vertrag zwischen Partei A und Partei B"
        similarity = service._calculate_text_similarity(text1, text2)
        assert similarity < 0.5

    def test_calculate_text_similarity_empty(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Leere Texte = 0.0 Aehnlichkeit."""
        similarity = service._calculate_text_similarity("", "Test")
        assert similarity == 0.0


class TestFieldSimilarity:
    """Tests fuer Feld-basierte Aehnlichkeit."""

    @pytest.fixture
    def service(self) -> DuplicateDetectionService:
        return DuplicateDetectionService()

    @pytest.fixture
    def invoice_data_1(self) -> ExtractedData:
        """Sample Rechnungsdaten 1."""
        return ExtractedData(
            document_id=uuid4(),
            raw_data={
                "invoice_number": "RE-2026-001",
                "invoice_date": "2026-01-03",
                "total_gross": "1190.00",
                "supplier_name": "Lieferant GmbH",
            }
        )

    @pytest.fixture
    def invoice_data_2(self) -> ExtractedData:
        """Sample Rechnungsdaten 2 (gleiche Nummer)."""
        return ExtractedData(
            document_id=uuid4(),
            raw_data={
                "invoice_number": "RE-2026-001",  # Gleiche Nummer
                "invoice_date": "2026-01-03",
                "total_gross": "1190.00",
                "supplier_name": "Lieferant GmbH",
            }
        )

    @pytest.fixture
    def invoice_data_different(self) -> ExtractedData:
        """Sample Rechnungsdaten (verschieden)."""
        return ExtractedData(
            document_id=uuid4(),
            raw_data={
                "invoice_number": "RE-2026-999",
                "invoice_date": "2026-12-31",
                "total_gross": "5000.00",
                "supplier_name": "Andere Firma AG",
            }
        )

    def test_field_similarity_identical(
        self,
        service: DuplicateDetectionService,
        invoice_data_1: ExtractedData,
        invoice_data_2: ExtractedData,
    ) -> None:
        """Test: Identische Felder = hohe Aehnlichkeit."""
        similarity, matched = service._calculate_field_similarity(
            invoice_data_1, invoice_data_2
        )
        assert similarity > 0.8
        assert "invoice_number" in matched

    def test_field_similarity_different(
        self,
        service: DuplicateDetectionService,
        invoice_data_1: ExtractedData,
        invoice_data_different: ExtractedData,
    ) -> None:
        """Test: Verschiedene Felder = niedrige Aehnlichkeit."""
        similarity, matched = service._calculate_field_similarity(
            invoice_data_1, invoice_data_different
        )
        assert similarity < 0.3
        assert "invoice_number" not in matched

    def test_field_similarity_partial_number_match(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Partielle Rechnungsnummer-Uebereinstimmung."""
        data1 = ExtractedData(
            document_id=uuid4(),
            raw_data={"invoice_number": "RE-001"}
        )
        data2 = ExtractedData(
            document_id=uuid4(),
            raw_data={"invoice_number": "RE-001-A"}
        )
        similarity, matched = service._calculate_field_similarity(data1, data2)
        assert "invoice_number_partial" in matched or "invoice_number" in matched


class TestCheckDocument:
    """Tests fuer check_document Methode."""

    @pytest.fixture
    def service(self) -> DuplicateDetectionService:
        return DuplicateDetectionService()

    @pytest.mark.asyncio
    async def test_check_document_no_document(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: Kein Dokument gefunden."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))

        result = await service.check_document(
            db=db,
            document_id=uuid4(),
            company_id=uuid4(),
        )

        assert isinstance(result, DuplicateCheckResult)
        assert result.has_duplicates is False

    @pytest.mark.asyncio
    async def test_check_document_returns_result(
        self,
        service: DuplicateDetectionService,
    ) -> None:
        """Test: check_document gibt DuplicateCheckResult zurueck."""
        db = AsyncMock(spec=AsyncSession)

        # Mock Document
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.checksum = "abc123"  # Document model uses checksum, not file_hash
        mock_doc.extracted_text = "Test Text"
        mock_doc.extracted_data = {}
        mock_doc.created_at = None

        # Mock execute für verschiedene Queries
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_doc),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        result = await service.check_document(
            db=db,
            document_id=mock_doc.id,
            company_id=uuid4(),
            include_near=False,
        )

        assert isinstance(result, DuplicateCheckResult)
        assert result.processing_time_ms >= 0


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_duplicate_detection_service_returns_same_instance(self) -> None:
        """Test: get_duplicate_detection_service gibt immer dieselbe Instanz zurueck."""
        service1 = get_duplicate_detection_service()
        service2 = get_duplicate_detection_service()
        assert service1 is service2

    def test_service_instance_type(self) -> None:
        """Test: Singleton ist DuplicateDetectionService."""
        service = get_duplicate_detection_service()
        assert isinstance(service, DuplicateDetectionService)

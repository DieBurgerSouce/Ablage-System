# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Document Comparison API Endpoints.

Phase 9.1: Dream Features - Document Comparison

Testet:
- POST /compare/documents - Dokumente vergleichen
- GET /compare/diff/{doc_id_1}/{doc_id_2} - Diff-Report
- GET /compare/similar/{doc_id} - Aehnliche Dokumente finden
- POST /compare/batch - Batch-Vergleich
- GET /compare/duplicates - Duplikate finden
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from fastapi import HTTPException, status
from pydantic import ValidationError


# ========================= Test Fixtures =========================


@pytest.fixture
def sample_user() -> MagicMock:
    """Create mock User with company_id."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_active = True
    user.company_id = uuid4()
    return user


@pytest.fixture
def sample_document_1(sample_user: MagicMock) -> MagicMock:
    """Create first mock Document."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.owner_id = sample_user.id
    doc.company_id = sample_user.company_id
    doc.deleted_at = None
    doc.filename = "rechnung_001.pdf"
    doc.document_type = "invoice"
    doc.extracted_text = "Rechnung Nr. 12345 vom 01.01.2026. Betrag: 1500,00 EUR."
    doc.extracted_data = {
        "invoice_number": "12345",
        "total_amount": 1500.00,
        "invoice_date": "2026-01-01",
    }
    doc.created_at = datetime.now(timezone.utc)
    doc.business_entity_id = uuid4()
    return doc


@pytest.fixture
def sample_document_2(sample_user: MagicMock) -> MagicMock:
    """Create second mock Document (similar to first)."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.owner_id = sample_user.id
    doc.company_id = sample_user.company_id
    doc.deleted_at = None
    doc.filename = "rechnung_002.pdf"
    doc.document_type = "invoice"
    doc.extracted_text = "Rechnung Nr. 12346 vom 01.01.2026. Betrag: 1600,00 EUR."
    doc.extracted_data = {
        "invoice_number": "12346",
        "total_amount": 1600.00,
        "invoice_date": "2026-01-01",
    }
    doc.created_at = datetime.now(timezone.utc)
    doc.business_entity_id = uuid4()
    return doc


# ========================= Request Schema Tests =========================


class TestCompareDocumentsRequest:
    """Tests fuer CompareDocumentsRequest Schema."""

    def test_valid_request(self) -> None:
        """Test: Gueltige Request wird akzeptiert."""
        from app.api.v1.compare import CompareDocumentsRequest, ComparisonType

        request = CompareDocumentsRequest(
            document_id_1=uuid4(),
            document_id_2=uuid4(),
            comparison_type=ComparisonType.HYBRID,
        )

        assert request.document_id_1 is not None
        assert request.document_id_2 is not None
        assert request.comparison_type == ComparisonType.HYBRID

    def test_default_comparison_type(self) -> None:
        """Test: Standard-Vergleichstyp ist HYBRID."""
        from app.api.v1.compare import CompareDocumentsRequest, ComparisonType

        request = CompareDocumentsRequest(
            document_id_1=uuid4(),
            document_id_2=uuid4(),
        )

        assert request.comparison_type == ComparisonType.HYBRID


class TestFindSimilarRequest:
    """Tests fuer FindSimilarRequest Schema."""

    def test_valid_request(self) -> None:
        """Test: Gueltige Request wird akzeptiert."""
        from app.api.v1.compare import FindSimilarRequest

        request = FindSimilarRequest(
            threshold=0.9,
            limit=20,
            include_same_entity=False,
        )

        assert request.threshold == 0.9
        assert request.limit == 20
        assert request.include_same_entity is False

    def test_default_values(self) -> None:
        """Test: Standard-Werte werden verwendet."""
        from app.api.v1.compare import FindSimilarRequest

        request = FindSimilarRequest()

        assert request.threshold == 0.8
        assert request.limit == 10
        assert request.include_same_entity is True

    def test_threshold_validation(self) -> None:
        """Test: Threshold muss zwischen 0 und 1 sein."""
        from app.api.v1.compare import FindSimilarRequest

        # Gueltige Werte
        valid = FindSimilarRequest(threshold=0.0)
        assert valid.threshold == 0.0

        valid = FindSimilarRequest(threshold=1.0)
        assert valid.threshold == 1.0


# ========================= Response Schema Tests =========================


class TestComparisonResultResponse:
    """Tests fuer ComparisonResultResponse Schema."""

    def test_create_response(self) -> None:
        """Test: Response kann erstellt werden."""
        from app.api.v1.compare import ComparisonResultResponse

        doc_id_1 = uuid4()
        doc_id_2 = uuid4()

        response = ComparisonResultResponse(
            document_id_1=doc_id_1,
            document_id_2=doc_id_2,
            comparison_type="hybrid",
            similarity_score=0.85,
            text_similarity=0.80,
            structure_similarity=0.90,
            text_differences=[],
            field_changes=[],
            summary="Dokumente sind weitgehend aehnlich",
            compared_at=datetime.now(timezone.utc).isoformat(),
        )

        assert response.document_id_1 == doc_id_1
        assert response.similarity_score == 0.85


class TestSimilarDocumentResponse:
    """Tests fuer SimilarDocumentResponse Schema."""

    def test_create_response(self) -> None:
        """Test: Response kann erstellt werden."""
        from app.api.v1.compare import SimilarDocumentResponse

        doc_id = uuid4()

        response = SimilarDocumentResponse(
            document_id=doc_id,
            filename="rechnung_002.pdf",
            document_type="invoice",
            similarity_score=0.92,
            matching_fields=["invoice_date", "supplier_name"],
            upload_date=datetime.now(timezone.utc).isoformat(),
        )

        assert response.document_id == doc_id
        assert response.similarity_score == 0.92
        assert "invoice_date" in response.matching_fields


# ========================= Endpoint Tests =========================


class TestCompareDocumentsEndpoint:
    """Tests fuer POST /compare/documents Endpoint."""

    @pytest.mark.asyncio
    async def test_compare_same_document_returns_error(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Vergleich eines Dokuments mit sich selbst schlaegt fehl."""
        from app.api.v1.compare import compare_documents, CompareDocumentsRequest
        from app.services.document_comparison_service import ComparisonType

        doc_id = uuid4()
        request = CompareDocumentsRequest(
            document_id_1=doc_id,
            document_id_2=doc_id,
            comparison_type=ComparisonType.TEXT,
        )

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            with patch(
                "app.api.v1.compare.DocumentComparisonService"
            ) as MockService:
                mock_service = MockService.return_value
                mock_service.compare_documents.side_effect = ValueError(
                    "Dokument kann nicht mit sich selbst verglichen werden"
                )

                await compare_documents(
                    request=request,
                    db=mock_db,
                    current_user=sample_user,
                )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_compare_documents_not_found(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Nicht existierende Dokumente werfen 404."""
        from app.api.v1.compare import compare_documents, CompareDocumentsRequest
        from app.services.document_comparison_service import ComparisonType

        request = CompareDocumentsRequest(
            document_id_1=uuid4(),
            document_id_2=uuid4(),
            comparison_type=ComparisonType.TEXT,
        )

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            with patch(
                "app.api.v1.compare.DocumentComparisonService"
            ) as MockService:
                mock_service = MockService.return_value
                mock_service.compare_documents.side_effect = ValueError(
                    "Dokument nicht gefunden"
                )

                await compare_documents(
                    request=request,
                    db=mock_db,
                    current_user=sample_user,
                )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_compare_documents_permission_denied(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Keine Berechtigung fuer Dokument wirft 403."""
        from app.api.v1.compare import compare_documents, CompareDocumentsRequest
        from app.services.document_comparison_service import ComparisonType

        request = CompareDocumentsRequest(
            document_id_1=uuid4(),
            document_id_2=uuid4(),
            comparison_type=ComparisonType.TEXT,
        )

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            with patch(
                "app.api.v1.compare.DocumentComparisonService"
            ) as MockService:
                mock_service = MockService.return_value
                mock_service.compare_documents.side_effect = PermissionError(
                    "Keine Berechtigung"
                )

                await compare_documents(
                    request=request,
                    db=mock_db,
                    current_user=sample_user,
                )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestGetDiffReportEndpoint:
    """Tests fuer GET /compare/diff/{doc_id_1}/{doc_id_2} Endpoint."""

    @pytest.mark.asyncio
    async def test_get_diff_report_not_found(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Nicht existierende Dokumente werfen 404."""
        from app.api.v1.compare import get_diff_report
        from app.services.document_comparison_service import ComparisonType

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            with patch(
                "app.api.v1.compare.DocumentComparisonService"
            ) as MockService:
                mock_service = MockService.return_value
                mock_service.generate_diff_report.side_effect = ValueError(
                    "Dokument nicht gefunden"
                )

                await get_diff_report(
                    doc_id_1=uuid4(),
                    doc_id_2=uuid4(),
                    comparison_type=ComparisonType.HYBRID,
                    db=mock_db,
                    current_user=sample_user,
                )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestFindSimilarDocumentsEndpoint:
    """Tests fuer GET /compare/similar/{doc_id} Endpoint."""

    @pytest.mark.asyncio
    async def test_find_similar_not_found(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Nicht existierendes Dokument wirft 404."""
        from app.api.v1.compare import find_similar_documents

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            with patch(
                "app.api.v1.compare.DocumentComparisonService"
            ) as MockService:
                mock_service = MockService.return_value
                mock_service.find_similar_documents.side_effect = ValueError(
                    "Dokument nicht gefunden"
                )

                await find_similar_documents(
                    doc_id=uuid4(),
                    threshold=0.8,
                    limit=10,
                    include_same_entity=True,
                    db=mock_db,
                    current_user=sample_user,
                )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestBatchCompareEndpoint:
    """Tests fuer POST /compare/batch Endpoint."""

    @pytest.mark.asyncio
    async def test_batch_compare_too_many_documents(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Zu viele Dokumente werden abgelehnt."""
        from app.api.v1.compare import batch_compare_documents
        from app.services.document_comparison_service import ComparisonType

        mock_db = AsyncMock()

        # 25 Dokumente - mehr als erlaubt (20)
        compare_doc_ids = [uuid4() for _ in range(25)]

        with pytest.raises(HTTPException) as exc_info:
            await batch_compare_documents(
                reference_doc_id=uuid4(),
                compare_doc_ids=compare_doc_ids,
                comparison_type=ComparisonType.HYBRID,
                db=mock_db,
                current_user=sample_user,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "20" in str(exc_info.value.detail)


class TestFindDuplicatesEndpoint:
    """Tests fuer GET /compare/duplicates Endpoint."""

    @pytest.mark.asyncio
    async def test_find_duplicates_with_defaults(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Duplikate finden mit Standardwerten."""
        from app.api.v1.compare import find_potential_duplicates

        mock_db = AsyncMock()

        # Mock execute um leere Liste zurueckzugeben
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await find_potential_duplicates(
            threshold=0.95,
            days_back=30,
            limit=50,
            db=mock_db,
            current_user=sample_user,
        )

        assert result == []


# ========================= Edge Cases =========================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    def test_compare_type_enum_values(self) -> None:
        """Test: ComparisonType Enum hat richtige Werte."""
        from app.services.document_comparison_service import ComparisonType

        assert ComparisonType.TEXT.value == "text"
        assert ComparisonType.STRUCTURED.value == "structured"
        assert ComparisonType.VISUAL.value == "visual"
        assert ComparisonType.HYBRID.value == "hybrid"

    def test_field_change_response_optional_fields(self) -> None:
        """Test: FieldChangeResponse mit optionalen Feldern."""
        from app.api.v1.compare import FieldChangeResponse

        response = FieldChangeResponse(
            field_name="new_field",
            category="other",
            old_value=None,
            new_value="new_value",
            change_type="added",
            significance="low",
        )

        assert response.old_value is None
        assert response.new_value == "new_value"

    def test_text_difference_response_empty_strings(self) -> None:
        """Test: TextDifferenceResponse mit leeren Strings."""
        from app.api.v1.compare import TextDifferenceResponse

        response = TextDifferenceResponse(
            type="added",
            position_start=0,
            position_end=10,
            original_text="",
            new_text="Neuer Text",
            context_before="",
            context_after="",
        )

        assert response.original_text == ""
        assert response.new_text == "Neuer Text"

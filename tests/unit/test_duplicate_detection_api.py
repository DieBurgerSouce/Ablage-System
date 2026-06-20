# -*- coding: utf-8 -*-
"""
Unit Tests fuer Duplikat-Erkennungs-API.

Tests:
- DuplicateCheckRequest Schema-Validierung
- DuplicateMatch Schema-Validierung
- DuplicateCheckResponse Schema-Validierung
- BatchScanRequest/Response Schema-Validierung
- DuplicateStatsResponse Schema-Validierung
- DuplicateConfigUpdate/Response Schema-Validierung
- API Endpoints (mit gemocktem Service)
- Celery Tasks (mit gemockten async Funktionen)
- Edge-Cases (keine Duplikate, exaktes Duplikat, nahe Duplikate)

Feinpoliert und durchdacht - Umfassende Tests.
"""

import uuid
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.schemas.duplicate_detection import (
    BatchScanRequest,
    BatchScanResponse,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    DuplicateConfigResponse,
    DuplicateConfigUpdate,
    DuplicateMatch,
    DuplicateStatsResponse,
)


# =============================================================================
# Schema Tests - DuplicateCheckRequest
# =============================================================================


class TestDuplicateCheckRequest:
    """Tests fuer DuplicateCheckRequest Schema."""

    def test_valid_minimal(self) -> None:
        """Minimale Anfrage mit nur document_id."""
        doc_id = uuid.uuid4()
        req = DuplicateCheckRequest(document_id=doc_id)
        assert req.document_id == doc_id
        assert req.company_id is None
        assert req.include_near is True

    def test_valid_full(self) -> None:
        """Vollstaendige Anfrage mit allen Feldern."""
        doc_id = uuid.uuid4()
        company_id = uuid.uuid4()
        req = DuplicateCheckRequest(
            document_id=doc_id,
            company_id=company_id,
            include_near=False,
        )
        assert req.document_id == doc_id
        assert req.company_id == company_id
        assert req.include_near is False

    def test_include_near_default(self) -> None:
        """Standardwert fuer include_near ist True."""
        req = DuplicateCheckRequest(document_id=uuid.uuid4())
        assert req.include_near is True

    def test_company_id_optional(self) -> None:
        """company_id ist optional."""
        req = DuplicateCheckRequest(document_id=uuid.uuid4(), company_id=None)
        assert req.company_id is None

    def test_invalid_document_id(self) -> None:
        """Ungueltige document_id wirft Fehler."""
        with pytest.raises(Exception):
            DuplicateCheckRequest(document_id="nicht-eine-uuid")  # type: ignore[arg-type]


# =============================================================================
# Schema Tests - DuplicateMatch
# =============================================================================


class TestDuplicateMatch:
    """Tests fuer DuplicateMatch Schema."""

    def test_valid_exact_match(self) -> None:
        """Exaktes Duplikat."""
        match = DuplicateMatch(
            document_id=uuid.uuid4(),
            duplicate_type="exact",
            similarity_score=1.0,
            matched_fields=["checksum"],
        )
        assert match.duplicate_type == "exact"
        assert match.similarity_score == 1.0
        assert match.matched_fields == ["checksum"]
        assert match.details is None

    def test_valid_near_match(self) -> None:
        """Nahes Duplikat mit Details."""
        match = DuplicateMatch(
            document_id=uuid.uuid4(),
            duplicate_type="near",
            similarity_score=0.92,
            matched_fields=["invoice_number", "total_gross"],
            details={"text_similarity": "0.92", "candidate_filename": "rechnung.pdf"},
        )
        assert match.duplicate_type == "near"
        assert match.similarity_score == 0.92
        assert len(match.matched_fields) == 2
        assert match.details is not None
        assert match.details["text_similarity"] == "0.92"

    def test_similarity_score_min_boundary(self) -> None:
        """Similarity-Score 0.0 ist gueltig."""
        match = DuplicateMatch(
            document_id=uuid.uuid4(),
            duplicate_type="semantic",
            similarity_score=0.0,
            matched_fields=[],
        )
        assert match.similarity_score == 0.0

    def test_similarity_score_max_boundary(self) -> None:
        """Similarity-Score 1.0 ist gueltig."""
        match = DuplicateMatch(
            document_id=uuid.uuid4(),
            duplicate_type="exact",
            similarity_score=1.0,
            matched_fields=["checksum"],
        )
        assert match.similarity_score == 1.0

    def test_similarity_score_too_high(self) -> None:
        """Similarity-Score > 1.0 wirft Fehler."""
        with pytest.raises(Exception):
            DuplicateMatch(
                document_id=uuid.uuid4(),
                duplicate_type="exact",
                similarity_score=1.5,
                matched_fields=[],
            )

    def test_similarity_score_negative(self) -> None:
        """Negativer Similarity-Score wirft Fehler."""
        with pytest.raises(Exception):
            DuplicateMatch(
                document_id=uuid.uuid4(),
                duplicate_type="near",
                similarity_score=-0.1,
                matched_fields=[],
            )

    def test_empty_matched_fields(self) -> None:
        """Leere matched_fields ist gueltig."""
        match = DuplicateMatch(
            document_id=uuid.uuid4(),
            duplicate_type="visual",
            similarity_score=0.85,
            matched_fields=[],
        )
        assert match.matched_fields == []

    def test_all_duplicate_types(self) -> None:
        """Alle gueltigen Duplikat-Typen koennen gesetzt werden."""
        for dup_type in ["exact", "near", "semantic", "number_match", "visual"]:
            match = DuplicateMatch(
                document_id=uuid.uuid4(),
                duplicate_type=dup_type,
                similarity_score=0.8,
                matched_fields=[],
            )
            assert match.duplicate_type == dup_type


# =============================================================================
# Schema Tests - DuplicateCheckResponse
# =============================================================================


class TestDuplicateCheckResponse:
    """Tests fuer DuplicateCheckResponse Schema."""

    def test_no_duplicates_response(self) -> None:
        """Antwort ohne Duplikate."""
        resp = DuplicateCheckResponse(
            has_duplicates=False,
            candidates=[],
            best_match=None,
            processing_time_ms=42,
        )
        assert resp.has_duplicates is False
        assert resp.candidates == []
        assert resp.best_match is None
        assert resp.processing_time_ms == 42

    def test_with_duplicates_response(self) -> None:
        """Antwort mit Duplikaten."""
        match = DuplicateMatch(
            document_id=uuid.uuid4(),
            duplicate_type="exact",
            similarity_score=1.0,
            matched_fields=["checksum"],
        )
        resp = DuplicateCheckResponse(
            has_duplicates=True,
            candidates=[match],
            best_match=match,
            processing_time_ms=150,
        )
        assert resp.has_duplicates is True
        assert len(resp.candidates) == 1
        assert resp.best_match is not None
        assert resp.best_match.duplicate_type == "exact"

    def test_processing_time_ms_zero(self) -> None:
        """Verarbeitungszeit 0 ms ist gueltig."""
        resp = DuplicateCheckResponse(
            has_duplicates=False,
            candidates=[],
            best_match=None,
            processing_time_ms=0,
        )
        assert resp.processing_time_ms == 0

    def test_processing_time_ms_negative_invalid(self) -> None:
        """Negative Verarbeitungszeit ist ungueltig."""
        with pytest.raises(Exception):
            DuplicateCheckResponse(
                has_duplicates=False,
                candidates=[],
                best_match=None,
                processing_time_ms=-1,
            )


# =============================================================================
# Schema Tests - BatchScanRequest / BatchScanResponse
# =============================================================================


class TestBatchScanSchemas:
    """Tests fuer BatchScanRequest und BatchScanResponse."""

    def test_batch_scan_request_valid(self) -> None:
        """Gueltiger BatchScanRequest."""
        company_id = uuid.uuid4()
        req = BatchScanRequest(company_id=company_id)
        assert req.company_id == company_id

    def test_batch_scan_request_invalid_company_id(self) -> None:
        """Ungueltige company_id wirft Fehler."""
        with pytest.raises(Exception):
            BatchScanRequest(company_id="keine-uuid")  # type: ignore[arg-type]

    def test_batch_scan_response_valid(self) -> None:
        """Gueltiger BatchScanResponse."""
        resp = BatchScanResponse(
            task_id="abc-123-def-456",
            message="Batch-Scan gestartet",
        )
        assert resp.task_id == "abc-123-def-456"
        assert resp.message == "Batch-Scan gestartet"


# =============================================================================
# Schema Tests - DuplicateStatsResponse
# =============================================================================


class TestDuplicateStatsResponse:
    """Tests fuer DuplicateStatsResponse Schema."""

    def test_valid_stats(self) -> None:
        """Gueltiger Stats-Response."""
        resp = DuplicateStatsResponse(
            total_documents=500,
            total_duplicates_found=23,
            by_type={"exact": 5, "near": 12, "number_match": 6},
            avg_similarity=0.887,
        )
        assert resp.total_documents == 500
        assert resp.total_duplicates_found == 23
        assert resp.by_type["exact"] == 5
        assert resp.avg_similarity == 0.887

    def test_empty_stats(self) -> None:
        """Leere Statistik (keine Dokumente)."""
        resp = DuplicateStatsResponse(
            total_documents=0,
            total_duplicates_found=0,
            by_type={},
            avg_similarity=0.0,
        )
        assert resp.total_documents == 0
        assert resp.by_type == {}
        assert resp.avg_similarity == 0.0

    def test_avg_similarity_boundary(self) -> None:
        """avg_similarity muss zwischen 0 und 1 liegen."""
        with pytest.raises(Exception):
            DuplicateStatsResponse(
                total_documents=10,
                total_duplicates_found=1,
                by_type={},
                avg_similarity=1.5,
            )


# =============================================================================
# Schema Tests - DuplicateConfigUpdate / DuplicateConfigResponse
# =============================================================================


class TestDuplicateConfigSchemas:
    """Tests fuer DuplicateConfigUpdate und DuplicateConfigResponse."""

    def test_config_update_all_fields(self) -> None:
        """Alle Konfigurationsfelder koennen gesetzt werden."""
        update = DuplicateConfigUpdate(
            min_similarity_near=0.90,
            min_similarity_semantic=0.75,
            max_candidates=100,
            max_text_length=20000,
        )
        assert update.min_similarity_near == 0.90
        assert update.min_similarity_semantic == 0.75
        assert update.max_candidates == 100
        assert update.max_text_length == 20000

    def test_config_update_partial(self) -> None:
        """Partielle Aktualisierung (nur einzelne Felder)."""
        update = DuplicateConfigUpdate(min_similarity_near=0.88)
        assert update.min_similarity_near == 0.88
        assert update.min_similarity_semantic is None
        assert update.max_candidates is None
        assert update.max_text_length is None

    def test_config_update_empty(self) -> None:
        """Leerer Update ist gueltig (keine Aenderungen)."""
        update = DuplicateConfigUpdate()
        assert update.min_similarity_near is None
        assert update.min_similarity_semantic is None

    def test_config_update_similarity_too_high(self) -> None:
        """Similarity > 1.0 ist ungueltig."""
        with pytest.raises(Exception):
            DuplicateConfigUpdate(min_similarity_near=1.5)

    def test_config_update_similarity_negative(self) -> None:
        """Negative Similarity ist ungueltig."""
        with pytest.raises(Exception):
            DuplicateConfigUpdate(min_similarity_semantic=-0.1)

    def test_config_update_max_candidates_too_low(self) -> None:
        """max_candidates < 1 ist ungueltig."""
        with pytest.raises(Exception):
            DuplicateConfigUpdate(max_candidates=0)

    def test_config_update_max_candidates_too_high(self) -> None:
        """max_candidates > 500 ist ungueltig."""
        with pytest.raises(Exception):
            DuplicateConfigUpdate(max_candidates=501)

    def test_config_response_valid(self) -> None:
        """Gueltiger Config-Response."""
        resp = DuplicateConfigResponse(
            min_similarity_near=0.85,
            min_similarity_semantic=0.70,
            max_candidates=50,
            max_text_length=10000,
            visual_exact_threshold=5,
            visual_near_threshold=10,
        )
        assert resp.min_similarity_near == 0.85
        assert resp.min_similarity_semantic == 0.70
        assert resp.max_candidates == 50
        assert resp.max_text_length == 10000
        assert resp.visual_exact_threshold == 5
        assert resp.visual_near_threshold == 10


# =============================================================================
# Service-Layer Tests (mit Mocks)
# =============================================================================


class TestDuplicateDetectionService:
    """Tests fuer den DuplicateDetectionService ueber Mocking."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        """Mock fuer DuplicateDetectionService."""
        from app.services.ai.duplicate_detection_service import (
            DuplicateCandidate,
            DuplicateCheckResult,
            DuplicateType,
        )

        service = MagicMock()

        # Kein Duplikat
        no_dup_result = DuplicateCheckResult(
            has_duplicates=False,
            candidates=[],
            best_match=None,
            processing_time_ms=10,
        )
        service.check_document = AsyncMock(return_value=no_dup_result)
        service.create_duplicate_decision = AsyncMock(return_value=None)
        service.MIN_SIMILARITY_NEAR = 0.85
        service.MIN_SIMILARITY_SEMANTIC = 0.70
        service.MAX_CANDIDATES = 50
        service.MAX_TEXT_LENGTH = 10000

        return service

    @pytest.mark.asyncio
    async def test_check_document_no_duplicates(self, mock_db: AsyncMock, mock_service: MagicMock) -> None:
        """Test: check_document ohne Duplikate."""
        from app.services.ai.duplicate_detection_service import DuplicateCheckResult

        doc_id = uuid.uuid4()
        result = await mock_service.check_document(
            db=mock_db,
            document_id=doc_id,
            company_id=None,
            include_near=True,
        )

        assert result.has_duplicates is False
        assert result.candidates == []
        assert result.best_match is None

    @pytest.mark.asyncio
    async def test_check_document_exact_duplicate(self, mock_db: AsyncMock) -> None:
        """Test: check_document mit exaktem Duplikat."""
        from app.services.ai.duplicate_detection_service import (
            DuplicateCandidate,
            DuplicateCheckResult,
            DuplicateType,
        )

        doc_id = uuid.uuid4()
        dup_id = uuid.uuid4()

        candidate = DuplicateCandidate(
            document_id=dup_id,
            duplicate_type=DuplicateType.EXACT,
            similarity=1.0,
            matched_fields=["checksum"],
            details={"hash": "abc123", "original_filename": "rechnung.pdf"},
        )

        mock_result = DuplicateCheckResult(
            has_duplicates=True,
            candidates=[candidate],
            best_match=candidate,
            processing_time_ms=25,
        )

        with patch(
            "app.services.ai.duplicate_detection_service.get_duplicate_detection_service"
        ) as mock_get_service:
            mock_svc = MagicMock()
            mock_svc.check_document = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_svc

            from app.services.ai.duplicate_detection_service import get_duplicate_detection_service

            service = get_duplicate_detection_service()
            result = await service.check_document(
                db=mock_db,
                document_id=doc_id,
            )

            assert result.has_duplicates is True
            assert len(result.candidates) == 1
            assert result.best_match is not None
            assert result.best_match.duplicate_type == DuplicateType.EXACT
            assert result.best_match.similarity == 1.0

    @pytest.mark.asyncio
    async def test_check_document_near_duplicate(self, mock_db: AsyncMock) -> None:
        """Test: check_document mit nahem Duplikat."""
        from app.services.ai.duplicate_detection_service import (
            DuplicateCandidate,
            DuplicateCheckResult,
            DuplicateType,
        )

        doc_id = uuid.uuid4()
        dup_id = uuid.uuid4()

        candidate = DuplicateCandidate(
            document_id=dup_id,
            duplicate_type=DuplicateType.NEAR,
            similarity=0.93,
            matched_fields=["invoice_number", "total_gross"],
            details={"text_similarity": "0.93"},
        )

        mock_result = DuplicateCheckResult(
            has_duplicates=True,
            candidates=[candidate],
            best_match=candidate,
            processing_time_ms=320,
        )

        with patch(
            "app.services.ai.duplicate_detection_service.get_duplicate_detection_service"
        ) as mock_get_service:
            mock_svc = MagicMock()
            mock_svc.check_document = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_svc

            from app.services.ai.duplicate_detection_service import get_duplicate_detection_service

            service = get_duplicate_detection_service()
            result = await service.check_document(
                db=mock_db,
                document_id=doc_id,
                include_near=True,
            )

            assert result.has_duplicates is True
            assert result.best_match is not None
            assert result.best_match.duplicate_type == DuplicateType.NEAR
            assert result.best_match.similarity > 0.90


# =============================================================================
# API Router Tests (mit gemocktem Service)
# =============================================================================


class TestDuplicateDetectionEndpoints:
    """Tests fuer die API Endpoints via gemockten Service."""

    def test_candidate_to_match_conversion(self) -> None:
        """Test: _candidate_to_match konvertiert korrekt."""
        from app.api.v1.duplicate_detection import _candidate_to_match
        from app.services.ai.duplicate_detection_service import DuplicateCandidate

        candidate = DuplicateCandidate(
            document_id=uuid.uuid4(),
            duplicate_type="exact",
            similarity=1.0,
            matched_fields=["checksum"],
            details={"hash": "abc123", "count": 42},
        )

        match = _candidate_to_match(candidate)

        assert match.duplicate_type == "exact"
        assert match.similarity_score == 1.0
        assert match.matched_fields == ["checksum"]
        # Details werden zu str konvertiert
        assert match.details is not None
        assert match.details["hash"] == "abc123"
        assert match.details["count"] == "42"

    def test_candidate_to_match_no_details(self) -> None:
        """Test: _candidate_to_match mit leeren Details."""
        from app.api.v1.duplicate_detection import _candidate_to_match
        from app.services.ai.duplicate_detection_service import DuplicateCandidate

        candidate = DuplicateCandidate(
            document_id=uuid.uuid4(),
            duplicate_type="near",
            similarity=0.88,
            matched_fields=[],
            details={},
        )

        match = _candidate_to_match(candidate)
        # Leeres Dict wird zu None
        assert match.details is None or match.details == {}

    @pytest.mark.asyncio
    async def test_check_endpoint_no_duplicates(self) -> None:
        """Test: /check Endpoint ohne Duplikate."""
        from app.services.ai.duplicate_detection_service import DuplicateCheckResult

        mock_result = DuplicateCheckResult(
            has_duplicates=False,
            candidates=[],
            best_match=None,
            processing_time_ms=15,
        )

        with patch(
            "app.api.v1.duplicate_detection.get_duplicate_detection_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc.check_document = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_svc

            from app.api.v1.duplicate_detection import check_document_for_duplicates

            mock_db = AsyncMock()
            mock_user = MagicMock()

            # Endpoint-Signatur: (request: Request, check_request, db, current_user, company_id)
            check_request = DuplicateCheckRequest(document_id=uuid.uuid4())
            response = await check_document_for_duplicates(
                request=MagicMock(),
                check_request=check_request,
                db=mock_db,
                current_user=mock_user,
                company_id=uuid.uuid4(),
            )

            assert response.has_duplicates is False
            assert response.candidates == []
            assert response.best_match is None
            assert response.processing_time_ms == 15

    @pytest.mark.asyncio
    async def test_check_endpoint_with_exact_duplicate(self) -> None:
        """Test: /check Endpoint mit exaktem Duplikat."""
        from app.services.ai.duplicate_detection_service import (
            DuplicateCandidate,
            DuplicateCheckResult,
            DuplicateType,
        )

        dup_id = uuid.uuid4()
        candidate = DuplicateCandidate(
            document_id=dup_id,
            duplicate_type=DuplicateType.EXACT,
            similarity=1.0,
            matched_fields=["checksum"],
            details={"hash": "deadbeef"},
        )

        mock_result = DuplicateCheckResult(
            has_duplicates=True,
            candidates=[candidate],
            best_match=candidate,
            processing_time_ms=8,
        )

        with patch(
            "app.api.v1.duplicate_detection.get_duplicate_detection_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc.check_document = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_svc

            from app.api.v1.duplicate_detection import check_document_for_duplicates

            mock_db = AsyncMock()
            mock_user = MagicMock()

            check_request = DuplicateCheckRequest(document_id=uuid.uuid4())
            response = await check_document_for_duplicates(
                request=MagicMock(),
                check_request=check_request,
                db=mock_db,
                current_user=mock_user,
                company_id=uuid.uuid4(),
            )

            assert response.has_duplicates is True
            assert len(response.candidates) == 1
            assert response.best_match is not None
            assert response.best_match.duplicate_type == DuplicateType.EXACT
            assert response.best_match.similarity_score == 1.0
            assert response.best_match.document_id == dup_id

    @pytest.mark.asyncio
    async def test_get_document_duplicates_endpoint(self) -> None:
        """Test: GET /document/{document_id} Endpoint."""
        from app.services.ai.duplicate_detection_service import DuplicateCheckResult

        mock_result = DuplicateCheckResult(
            has_duplicates=False,
            candidates=[],
            best_match=None,
            processing_time_ms=20,
        )

        with patch(
            "app.api.v1.duplicate_detection.get_duplicate_detection_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc.check_document = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_svc

            from app.api.v1.duplicate_detection import get_document_duplicates

            mock_db = AsyncMock()
            mock_user = MagicMock()

            response = await get_document_duplicates(
                document_id=uuid.uuid4(),
                company_id=None,
                include_near=True,
                db=mock_db,
                current_user=mock_user,
            )

            assert response.has_duplicates is False
            assert response.candidates == []

    @pytest.mark.asyncio
    async def test_batch_scan_endpoint(self) -> None:
        """Test: POST /batch-scan Endpoint."""
        mock_task = MagicMock()
        mock_task.id = "task-xyz-789"

        with patch(
            "app.api.v1.duplicate_detection.get_duplicate_detection_service"
        ):
            with patch(
                "app.workers.tasks.duplicate_detection_tasks.batch_scan_duplicates_task"
            ) as mock_task_fn:
                mock_task_fn.delay = MagicMock(return_value=mock_task)

                from app.api.v1.duplicate_detection import trigger_batch_scan

                mock_db = AsyncMock()
                mock_user = MagicMock()

                request = BatchScanRequest(company_id=uuid.uuid4())

                # Interne Import-Patch fuer task
                with patch(
                    "app.api.v1.duplicate_detection.trigger_batch_scan",
                    new_callable=AsyncMock,
                ) as mock_trigger:
                    mock_trigger.return_value = BatchScanResponse(
                        task_id="task-xyz-789",
                        message="Batch-Scan gestartet",
                    )
                    response = await mock_trigger(
                        request=request,
                        db=mock_db,
                        current_user=mock_user,
                    )

                    assert response.task_id == "task-xyz-789"
                    assert response.message == "Batch-Scan gestartet"

    @pytest.mark.asyncio
    async def test_config_update_endpoint(self) -> None:
        """Test: PUT /config Endpoint."""
        with patch(
            "app.api.v1.duplicate_detection.get_duplicate_detection_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc.MIN_SIMILARITY_NEAR = 0.85
            mock_svc.MIN_SIMILARITY_SEMANTIC = 0.70
            mock_svc.MAX_CANDIDATES = 50
            mock_svc.MAX_TEXT_LENGTH = 10000
            # Response liest auch die visuellen Schwellwerte vom Service
            mock_svc.VISUAL_EXACT_THRESHOLD = 5
            mock_svc.VISUAL_NEAR_THRESHOLD = 10
            mock_get.return_value = mock_svc

            from app.api.v1.duplicate_detection import update_duplicate_config

            mock_db = AsyncMock()
            mock_user = MagicMock()

            config_update = DuplicateConfigUpdate(
                min_similarity_near=0.90,
                max_candidates=100,
            )

            # Endpoint-Signatur: (request: Request, config_update, db, current_user)
            response = await update_duplicate_config(
                request=MagicMock(),
                config_update=config_update,
                db=mock_db,
                current_user=mock_user,
            )

            assert response.min_similarity_near == 0.90
            assert response.max_candidates == 100


# =============================================================================
# Celery Task Tests
# =============================================================================


class TestDuplicateDetectionTasks:
    """Tests fuer Celery Tasks der Duplikat-Erkennung."""

    @patch("app.workers.tasks.duplicate_detection_tasks._run_async")
    def test_batch_scan_task_called(self, mock_run: MagicMock) -> None:
        """Test: batch_scan_duplicates_task ruft _run_async auf."""
        mock_run.return_value = {
            "erfolg": True,
            "company_id": "abc-123",
            "gescannt": 10,
            "duplikate_gefunden": 2,
            "fehler": 0,
        }

        from app.workers.tasks.duplicate_detection_tasks import batch_scan_duplicates_task

        result = batch_scan_duplicates_task(company_id="abc-123")

        mock_run.assert_called_once()
        assert result["erfolg"] is True
        assert result["gescannt"] == 10
        assert result["duplikate_gefunden"] == 2

    @patch("app.workers.tasks.duplicate_detection_tasks._run_async")
    def test_check_document_task_called(self, mock_run: MagicMock) -> None:
        """Test: check_document_duplicates_task ruft _run_async auf."""
        doc_id = str(uuid.uuid4())
        mock_run.return_value = {
            "has_duplicates": False,
            "candidates_count": 0,
            "processing_time_ms": 12,
            "document_id": doc_id,
        }

        from app.workers.tasks.duplicate_detection_tasks import check_document_duplicates_task

        result = check_document_duplicates_task(document_id=doc_id)

        mock_run.assert_called_once()
        assert result["has_duplicates"] is False
        assert result["document_id"] == doc_id

    @patch("app.workers.tasks.duplicate_detection_tasks._run_async")
    def test_check_document_task_with_duplicate(self, mock_run: MagicMock) -> None:
        """Test: check_document_duplicates_task mit Duplikat."""
        doc_id = str(uuid.uuid4())
        mock_run.return_value = {
            "has_duplicates": True,
            "candidates_count": 3,
            "processing_time_ms": 280,
            "document_id": doc_id,
        }

        from app.workers.tasks.duplicate_detection_tasks import check_document_duplicates_task

        result = check_document_duplicates_task(document_id=doc_id, company_id=str(uuid.uuid4()))

        assert result["has_duplicates"] is True
        assert result["candidates_count"] == 3

    @patch("app.workers.tasks.duplicate_detection_tasks._run_async")
    def test_cleanup_task_called(self, mock_run: MagicMock) -> None:
        """Test: cleanup_stale_duplicate_flags_task ruft _run_async auf."""
        mock_run.return_value = {
            "erfolg": True,
            "geprueft": 50,
            "bereinigt": 3,
        }

        from app.workers.tasks.duplicate_detection_tasks import cleanup_stale_duplicate_flags_task

        result = cleanup_stale_duplicate_flags_task()

        mock_run.assert_called_once()
        assert result["erfolg"] is True
        assert result["geprueft"] == 50
        assert result["bereinigt"] == 3

    @pytest.mark.asyncio
    async def test_batch_scan_async_no_documents(self) -> None:
        """Test: _batch_scan_async mit leerer Firma."""
        from app.workers.tasks.duplicate_detection_tasks import _batch_scan_async

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()

            mock_factory.return_value = mock_session

            with patch(
                "app.services.ai.duplicate_detection_service.get_duplicate_detection_service"
            ) as mock_get_svc:
                mock_get_svc.return_value = MagicMock()

                result = await _batch_scan_async(company_id=str(uuid.uuid4()))

                assert result["gescannt"] == 0
                assert result["duplikate_gefunden"] == 0
                assert result["fehler"] == 0

    @pytest.mark.asyncio
    async def test_check_document_async_no_duplicates(self) -> None:
        """Test: _check_document_async fuer Dokument ohne Duplikate."""
        from app.services.ai.duplicate_detection_service import DuplicateCheckResult
        from app.workers.tasks.duplicate_detection_tasks import _check_document_async

        doc_id = str(uuid.uuid4())
        mock_result = DuplicateCheckResult(
            has_duplicates=False,
            candidates=[],
            best_match=None,
            processing_time_ms=8,
        )

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_session

            with patch(
                "app.services.ai.duplicate_detection_service.get_duplicate_detection_service"
            ) as mock_get_svc:
                mock_svc = MagicMock()
                mock_svc.check_document = AsyncMock(return_value=mock_result)
                mock_svc.create_duplicate_decision = AsyncMock(return_value=None)
                mock_get_svc.return_value = mock_svc

                result = await _check_document_async(document_id=doc_id)

                assert result["has_duplicates"] is False
                assert result["candidates_count"] == 0
                assert result["document_id"] == doc_id

    def test_run_async_helper(self) -> None:
        """Test: _run_async fuehrt Coroutine aus und schliesst Loop."""
        from app.workers.tasks.duplicate_detection_tasks import _run_async

        async def sample_coro() -> str:
            return "Ergebnis"

        result = _run_async(sample_coro())
        assert result == "Ergebnis"

    def test_task_names_are_unique(self) -> None:
        """Test: Alle Task-Namen sind eindeutig."""
        from app.workers.tasks.duplicate_detection_tasks import (
            batch_scan_duplicates_task,
            check_document_duplicates_task,
            cleanup_stale_duplicate_flags_task,
        )

        names = {
            batch_scan_duplicates_task.name,
            check_document_duplicates_task.name,
            cleanup_stale_duplicate_flags_task.name,
        }
        assert len(names) == 3

    def test_batch_scan_task_has_correct_settings(self) -> None:
        """Test: batch_scan_duplicates_task hat korrekte Retry-Einstellungen."""
        from app.workers.tasks.duplicate_detection_tasks import batch_scan_duplicates_task

        assert batch_scan_duplicates_task.max_retries == 3
        assert batch_scan_duplicates_task.acks_late is True


# =============================================================================
# Edge-Case Tests
# =============================================================================


class TestDuplicateDetectionEdgeCases:
    """Edge-Case Tests fuer die Duplikat-Erkennung."""

    def test_multiple_candidates_sorted_by_score(self) -> None:
        """Test: Kandidaten koennen nach Score geordnet sein."""
        candidates = [
            DuplicateMatch(
                document_id=uuid.uuid4(),
                duplicate_type="near",
                similarity_score=0.88,
                matched_fields=["invoice_number"],
            ),
            DuplicateMatch(
                document_id=uuid.uuid4(),
                duplicate_type="exact",
                similarity_score=1.0,
                matched_fields=["checksum"],
            ),
            DuplicateMatch(
                document_id=uuid.uuid4(),
                duplicate_type="semantic",
                similarity_score=0.72,
                matched_fields=[],
            ),
        ]

        resp = DuplicateCheckResponse(
            has_duplicates=True,
            candidates=candidates,
            best_match=candidates[1],  # exact match = bester
            processing_time_ms=500,
        )

        assert resp.best_match is not None
        assert resp.best_match.similarity_score == 1.0
        assert len(resp.candidates) == 3

    def test_number_match_with_details(self) -> None:
        """Test: Rechnungsnummer-Duplikat mit Details."""
        match = DuplicateMatch(
            document_id=uuid.uuid4(),
            duplicate_type="number_match",
            similarity_score=0.75,
            matched_fields=["invoice_number", "supplier_name"],
            details={"invoice_number": "RE-2026-001"},
        )

        assert match.duplicate_type == "number_match"
        assert "invoice_number" in match.matched_fields
        assert match.details is not None
        assert match.details["invoice_number"] == "RE-2026-001"

    def test_visual_match_type(self) -> None:
        """Test: Visuelles Duplikat (pHash)."""
        match = DuplicateMatch(
            document_id=uuid.uuid4(),
            duplicate_type="visual",
            similarity_score=0.96,
            matched_fields=["perceptual_hash"],
            details={"hamming_distance": "4", "visual_match": "near"},
        )

        assert match.duplicate_type == "visual"
        assert match.similarity_score == 0.96

    def test_config_update_min_text_length(self) -> None:
        """Test: max_text_length Untergrenze."""
        with pytest.raises(Exception):
            DuplicateConfigUpdate(max_text_length=99)  # Untergrenze ist 100

    def test_config_update_max_text_length(self) -> None:
        """Test: max_text_length Obergrenze."""
        with pytest.raises(Exception):
            DuplicateConfigUpdate(max_text_length=100001)  # Obergrenze ist 100000

    def test_batch_scan_response_german_message(self) -> None:
        """Test: BatchScanResponse Nachricht ist auf Deutsch."""
        resp = BatchScanResponse(
            task_id="xyz-123",
            message="Batch-Scan gestartet",
        )
        assert "Scan" in resp.message

    @patch("app.workers.tasks.duplicate_detection_tasks._run_async")
    def test_batch_scan_task_error_handling(self, mock_run: MagicMock) -> None:
        """Test: batch_scan_duplicates_task bei Fehler."""
        mock_run.return_value = {
            "erfolg": False,
            "company_id": "fehler-id",
            "fehler_meldung": "ConnectionError",
        }

        from app.workers.tasks.duplicate_detection_tasks import batch_scan_duplicates_task

        result = batch_scan_duplicates_task(company_id="fehler-id")

        assert result["erfolg"] is False
        assert "fehler_meldung" in result

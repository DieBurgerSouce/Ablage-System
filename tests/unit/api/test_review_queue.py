# -*- coding: utf-8 -*-
"""
Unit Tests fuer Review Queue API Endpoints.

Testet:
- GET  /review-queue (Dokumente mit unsicherer Auto-Zuordnung)
- POST /documents/{id}/confirm-filing (Zuordnung bestaetigen/korrigieren)
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    """Mock authentifizierter Benutzer."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "reviewer@ablage.local"
    user.company_id = uuid4()
    return user


@pytest.fixture
def mock_document():
    """Mock Document mit AI-Metadata und Pipeline-Result."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.filename = "rechnung_2026.pdf"
    doc.company_id = uuid4()
    doc.category = "rechnung"
    doc.created_at = datetime.now(timezone.utc)
    doc.ai_metadata = {
        "pipeline_result": {
            "requires_review": True,
            "review_confirmed": False,
            "status": "requires_review",
            "document_type": "invoice",
            "review_reasons": ["Niedrige Konfidenz", "Mehrdeutige Kategorie"],
            "category": {
                "name": "rechnung",
                "confidence": 0.45,
            },
            "linked_entity": {
                "id": str(uuid4()),
                "name": "Mueller GmbH",
            },
            "assigned_project": {
                "id": str(uuid4()),
                "name": "Projekt Alpha",
            },
        }
    }
    return doc


# =============================================================================
# Review Queue Tests (use select/and_/func/text patches)
# =============================================================================


class TestGetReviewQueue:
    """Tests fuer GET /review-queue."""

    def _queue_patches(self):
        """Erstellt Standard-Patches fuer get_review_queue SQLAlchemy-Ausdruecke."""
        mock_query = MagicMock()
        mock_query.select_from.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query

        # Document Mock mit ai_metadata Attribut
        mock_doc_cls = MagicMock()
        mock_doc_cls.company_id = MagicMock()
        mock_doc_cls.ai_metadata = MagicMock()
        mock_doc_cls.ai_metadata.isnot.return_value = True
        mock_doc_cls.created_at = MagicMock()
        mock_doc_cls.created_at.desc.return_value = "desc"

        mock_func = MagicMock()
        mock_func.count.return_value = MagicMock()

        return (
            patch("app.api.v1.review_queue.select", return_value=mock_query),
            patch("app.api.v1.review_queue.Document", mock_doc_cls),
            patch("app.api.v1.review_queue.func", mock_func),
            patch("app.api.v1.review_queue.and_", side_effect=lambda *args: args),
            patch("app.api.v1.review_queue.text", side_effect=lambda x: x),
        )

    @pytest.mark.asyncio
    async def test_get_review_queue_success(self, mock_db, mock_user, mock_document):
        """Review-Queue wird mit Items zurueckgegeben."""
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [mock_document]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        p1, p2, p3, p4, p5 = self._queue_patches()
        with p1, p2, p3, p4, p5:
            from app.api.v1.review_queue import get_review_queue

            result = await get_review_queue(
                page=1,
                page_size=20,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.total == 1
            assert len(result.items) == 1
            assert result.items[0].filename == "rechnung_2026.pdf"
            assert result.items[0].confidence == 0.45
            assert len(result.items[0].review_reasons) == 2
            assert result.page == 1
            assert result.page_size == 20

    @pytest.mark.asyncio
    async def test_get_review_queue_empty(self, mock_db, mock_user):
        """Leere Queue bei keinen Review-Dokumenten."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        p1, p2, p3, p4, p5 = self._queue_patches()
        with p1, p2, p3, p4, p5:
            from app.api.v1.review_queue import get_review_queue

            result = await get_review_queue(
                page=1,
                page_size=20,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.total == 0
            assert result.items == []

    @pytest.mark.asyncio
    async def test_get_review_queue_pagination(self, mock_db, mock_user):
        """Paginierung funktioniert korrekt."""
        count_result = MagicMock()
        count_result.scalar.return_value = 50

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        p1, p2, p3, p4, p5 = self._queue_patches()
        with p1, p2, p3, p4, p5:
            from app.api.v1.review_queue import get_review_queue

            result = await get_review_queue(
                page=3,
                page_size=10,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.total == 50
            assert result.page == 3
            assert result.page_size == 10

    @pytest.mark.asyncio
    async def test_get_review_queue_db_error(self, mock_db, mock_user):
        """500 bei Datenbankfehler."""
        from fastapi import HTTPException

        mock_db.execute = AsyncMock(side_effect=Exception("DB connection lost"))

        p1, p2, p3, p4, p5 = self._queue_patches()
        with p1, p2, p3, p4, p5:
            from app.api.v1.review_queue import get_review_queue

            with pytest.raises(HTTPException) as exc_info:
                await get_review_queue(
                    page=1,
                    page_size=20,
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_get_review_queue_missing_ai_metadata(self, mock_db, mock_user):
        """Dokument ohne ai_metadata wird korrekt behandelt."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.filename = "unknown.pdf"
        doc.created_at = datetime.now(timezone.utc)
        doc.ai_metadata = None

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [doc]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        p1, p2, p3, p4, p5 = self._queue_patches()
        with p1, p2, p3, p4, p5:
            from app.api.v1.review_queue import get_review_queue

            result = await get_review_queue(
                page=1,
                page_size=20,
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result.items) == 1
            assert result.items[0].confidence == 0.0
            assert result.items[0].review_reasons == []


# =============================================================================
# Confirm Filing Tests
# =============================================================================


class TestConfirmFiling:
    """Tests fuer POST /documents/{id}/confirm-filing."""

    def _setup_confirm_patches(self):
        """Erstellt Patches fuer select/and_ in confirm_filing."""
        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        return patch("app.api.v1.review_queue.select", return_value=mock_query), \
               patch("app.api.v1.review_queue.and_", side_effect=lambda *args: args)

    @pytest.mark.asyncio
    async def test_confirm_filing_success(self, mock_db, mock_user, mock_document):
        """Zuordnung wird erfolgreich bestaetigt."""
        mock_document.company_id = mock_user.company_id

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_document
        mock_db.execute = AsyncMock(return_value=result_mock)

        p1, p2 = self._setup_confirm_patches()
        with p1, p2:
            from app.api.v1.review_queue import confirm_filing, ConfirmFilingRequest

            request = ConfirmFilingRequest(
                category="rechnung",
                is_correction=False,
            )

            result = await confirm_filing(
                document_id=mock_document.id,
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.status == "bestaetigt"
            assert result.applied_category == "rechnung"
            assert result.correction_recorded is False
            mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirm_filing_not_found(self, mock_db, mock_user):
        """404 wenn Dokument nicht gefunden."""
        from fastapi import HTTPException

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        p1, p2 = self._setup_confirm_patches()
        with p1, p2:
            from app.api.v1.review_queue import confirm_filing, ConfirmFilingRequest

            request = ConfirmFilingRequest(category="rechnung")

            with pytest.raises(HTTPException) as exc_info:
                await confirm_filing(
                    document_id=uuid4(),
                    request=request,
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_confirm_filing_with_entity_and_project(self, mock_db, mock_user, mock_document):
        """Entity- und Projekt-Zuordnung werden angewandt."""
        mock_document.company_id = mock_user.company_id
        mock_document.entity_id = None
        mock_document.project_id = None

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_document
        mock_db.execute = AsyncMock(return_value=result_mock)

        p1, p2 = self._setup_confirm_patches()
        with p1, p2:
            from app.api.v1.review_queue import confirm_filing, ConfirmFilingRequest

            entity_id = str(uuid4())
            project_id = str(uuid4())

            request = ConfirmFilingRequest(
                category="rechnung",
                entity_id=entity_id,
                project_id=project_id,
            )

            result = await confirm_filing(
                document_id=mock_document.id,
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.applied_entity_id == entity_id
            assert result.applied_project_id == project_id

    @pytest.mark.asyncio
    async def test_confirm_filing_db_error(self, mock_db, mock_user, mock_document):
        """500 bei Datenbankfehler waehrend Bestaetigung."""
        from fastapi import HTTPException

        mock_document.company_id = mock_user.company_id

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_document
        mock_db.execute = AsyncMock(return_value=result_mock)
        mock_db.commit = AsyncMock(side_effect=Exception("DB write error"))

        p1, p2 = self._setup_confirm_patches()
        with p1, p2:
            from app.api.v1.review_queue import confirm_filing, ConfirmFilingRequest

            request = ConfirmFilingRequest(category="rechnung")

            with pytest.raises(HTTPException) as exc_info:
                await confirm_filing(
                    document_id=mock_document.id,
                    request=request,
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_confirm_filing_no_category(self, mock_db, mock_user, mock_document):
        """Bestaetigung ohne Kategorie-Aenderung funktioniert."""
        mock_document.company_id = mock_user.company_id

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_document
        mock_db.execute = AsyncMock(return_value=result_mock)

        p1, p2 = self._setup_confirm_patches()
        with p1, p2:
            from app.api.v1.review_queue import confirm_filing, ConfirmFilingRequest

            request = ConfirmFilingRequest()

            result = await confirm_filing(
                document_id=mock_document.id,
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.status == "bestaetigt"
            assert result.applied_category is None


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestReviewQueueSchemas:
    """Tests fuer Pydantic-Schema-Validierung."""

    def test_review_queue_item_defaults(self):
        """ReviewQueueItem hat korrekte Standardwerte."""
        from app.api.v1.review_queue import ReviewQueueItem

        item = ReviewQueueItem(
            document_id=str(uuid4()),
            filename="test.pdf",
            created_at="2026-01-01T00:00:00Z",
        )
        assert item.confidence == 0.0
        assert item.review_reasons == []
        assert item.pipeline_status == "requires_review"

    def test_confirm_filing_request_defaults(self):
        """ConfirmFilingRequest hat korrekte Standardwerte."""
        from app.api.v1.review_queue import ConfirmFilingRequest

        req = ConfirmFilingRequest()
        assert req.category is None
        assert req.entity_id is None
        assert req.project_id is None
        assert req.is_correction is False

    def test_confirm_filing_response_fields(self):
        """ConfirmFilingResponse enthaelt alle Felder."""
        from app.api.v1.review_queue import ConfirmFilingResponse

        resp = ConfirmFilingResponse(
            document_id=str(uuid4()),
            status="bestaetigt",
            applied_category="rechnung",
        )
        assert resp.correction_recorded is False

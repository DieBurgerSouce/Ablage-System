# -*- coding: utf-8 -*-
"""
Unit Tests fuer Document Quality API Endpoints.

Testet:
- GET /{document_id}/score - Qualitaets-Score fuer ein Dokument
- GET /overview - Unternehmensweite Qualitaetsuebersicht

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from uuid import UUID

from fastapi import HTTPException
from starlette.requests import Request

from app.services.ocr.document_quality_score_service import (
    DocumentQualityScore,
    CompanyQualityOverview,
    QualityDimension,
    AmpelColor,
)


# Test-Konstanten
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")
TEST_DOC_UUID = UUID("00000000-0000-0000-0000-000000000007")

pytestmark = [pytest.mark.unit, pytest.mark.api, pytest.mark.asyncio]


# ========================= Rate Limiter Bypass =========================


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """Rate-Limiter fuer Unit-Tests deaktivieren (kein Redis noetig)."""
    from app.core.rate_limiting import limiter

    original = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = original


# ========================= Mock Fixtures =========================


def _make_starlette_request(path: str = "/api/v1/document-quality") -> Request:
    """Erzeugt ein minimales Starlette Request-Objekt fuer den Rate-Limiter."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


@pytest.fixture
def mock_user() -> Mock:
    """Mock-Benutzer fuer Authentifizierung."""
    user = Mock()
    user.id = TEST_USER_UUID
    user.company_id = TEST_COMPANY_UUID
    return user


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock Database Session."""
    return AsyncMock()


@pytest.fixture
def mock_quality_score() -> DocumentQualityScore:
    """Mock Qualitaets-Score fuer ein Dokument."""
    return DocumentQualityScore(
        document_id=str(TEST_DOC_UUID),
        score=0.85,
        ampel_color=AmpelColor.GRUEN,
        ampel_label="Vollstaendig und vertrauenswuerdig",
        dimensions=[
            QualityDimension(
                name="OCR-Konfidenz",
                score=0.92,
                weight=0.40,
                details="Gute OCR-Qualitaet",
                sub_scores={"raw_confidence": 0.92},
            ),
            QualityDimension(
                name="Feld-Vollstaendigkeit",
                score=0.80,
                weight=0.35,
                details="Alle Pflichtfelder vorhanden",
                sub_scores={},
            ),
            QualityDimension(
                name="Verarbeitungs-Status",
                score=0.67,
                weight=0.25,
                details="Teilweise verarbeitet",
                sub_scores={
                    "ocr_completed": 1.0,
                    "categorized": 0.0,
                    "classified": 1.0,
                },
            ),
        ],
        recommendations=["Stichprobenartige Pruefung des OCR-Textes empfohlen"],
    )


@pytest.fixture
def mock_company_overview() -> CompanyQualityOverview:
    """Mock Unternehmensweite Qualitaetsuebersicht."""
    return CompanyQualityOverview(
        total_documents=50,
        average_score=0.78,
        gruen_count=30,
        gelb_count=15,
        rot_count=5,
        gruen_percent=60.0,
        gelb_percent=30.0,
        rot_percent=10.0,
    )


@pytest.fixture
def mock_company_overview_empty() -> CompanyQualityOverview:
    """Mock leere Qualitaetsuebersicht (keine Dokumente)."""
    return CompanyQualityOverview(
        total_documents=0,
        average_score=0.0,
        gruen_count=0,
        gelb_count=0,
        rot_count=0,
        gruen_percent=0.0,
        gelb_percent=0.0,
        rot_percent=0.0,
    )


# ========================= Document Quality Score Endpoint =========================


class TestGetDocumentQualityScore:
    """Tests fuer GET /document-quality/{document_id}/score."""

    async def test_get_document_quality_score_success(
        self,
        mock_db_session: AsyncMock,
        mock_user: Mock,
        mock_quality_score: DocumentQualityScore,
    ) -> None:
        """Erfolgreicher Abruf eines Qualitaets-Scores."""
        from app.api.v1.document_quality import get_document_quality_score

        mock_service = AsyncMock()
        mock_service.calculate_quality_score.return_value = mock_quality_score

        request = _make_starlette_request(f"/api/v1/document-quality/{TEST_DOC_UUID}/score")

        with patch(
            "app.services.ocr.document_quality_score_service.get_document_quality_service",
            return_value=mock_service,
        ):
            result = await get_document_quality_score(
                request=request,
                document_id=TEST_DOC_UUID,
                current_user=mock_user,
                db=mock_db_session,
            )

        assert result.document_id == str(TEST_DOC_UUID)
        assert result.score == 0.85
        assert result.ampel_color == "gruen"
        assert result.ampel_label == "Vollstaendig und vertrauenswuerdig"
        assert len(result.dimensions) == 3
        assert len(result.recommendations) == 1
        mock_service.calculate_quality_score.assert_awaited_once_with(
            str(TEST_DOC_UUID), mock_db_session
        )

    async def test_get_document_quality_not_found(
        self,
        mock_db_session: AsyncMock,
        mock_user: Mock,
    ) -> None:
        """ValueError vom Service fuehrt zu HTTP 404."""
        from app.api.v1.document_quality import get_document_quality_score

        mock_service = AsyncMock()
        mock_service.calculate_quality_score.side_effect = ValueError(
            "Dokument nicht gefunden"
        )

        request = _make_starlette_request(f"/api/v1/document-quality/{TEST_DOC_UUID}/score")

        with patch(
            "app.services.ocr.document_quality_score_service.get_document_quality_service",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_document_quality_score(
                    request=request,
                    document_id=TEST_DOC_UUID,
                    current_user=mock_user,
                    db=mock_db_session,
                )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Dokument nicht gefunden"

    async def test_get_document_quality_server_error(
        self,
        mock_db_session: AsyncMock,
        mock_user: Mock,
    ) -> None:
        """Generischer Fehler vom Service fuehrt zu HTTP 500."""
        from app.api.v1.document_quality import get_document_quality_score

        mock_service = AsyncMock()
        mock_service.calculate_quality_score.side_effect = RuntimeError(
            "Datenbankfehler"
        )

        request = _make_starlette_request(f"/api/v1/document-quality/{TEST_DOC_UUID}/score")

        with patch(
            "app.services.ocr.document_quality_score_service.get_document_quality_service",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_document_quality_score(
                    request=request,
                    document_id=TEST_DOC_UUID,
                    current_user=mock_user,
                    db=mock_db_session,
                )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Qualitaetsbewertung fehlgeschlagen"

    async def test_get_document_quality_all_dimensions_present(
        self,
        mock_db_session: AsyncMock,
        mock_user: Mock,
        mock_quality_score: DocumentQualityScore,
    ) -> None:
        """Alle 3 Qualitaetsdimensionen sind in der Antwort enthalten."""
        from app.api.v1.document_quality import get_document_quality_score

        mock_service = AsyncMock()
        mock_service.calculate_quality_score.return_value = mock_quality_score

        request = _make_starlette_request(f"/api/v1/document-quality/{TEST_DOC_UUID}/score")

        with patch(
            "app.services.ocr.document_quality_score_service.get_document_quality_service",
            return_value=mock_service,
        ):
            result = await get_document_quality_score(
                request=request,
                document_id=TEST_DOC_UUID,
                current_user=mock_user,
                db=mock_db_session,
            )

        dimension_names = [d.name for d in result.dimensions]
        assert "OCR-Konfidenz" in dimension_names
        assert "Feld-Vollstaendigkeit" in dimension_names
        assert "Verarbeitungs-Status" in dimension_names

        # Verify sub_scores on the processing status dimension
        status_dim = next(d for d in result.dimensions if d.name == "Verarbeitungs-Status")
        assert status_dim.sub_scores["ocr_completed"] == 1.0
        assert status_dim.sub_scores["categorized"] == 0.0
        assert status_dim.sub_scores["classified"] == 1.0


# ========================= Company Quality Overview Endpoint =========================


class TestGetCompanyQualityOverview:
    """Tests fuer GET /document-quality/overview."""

    async def test_get_company_quality_overview_success(
        self,
        mock_db_session: AsyncMock,
        mock_user: Mock,
        mock_company_overview: CompanyQualityOverview,
    ) -> None:
        """Erfolgreicher Abruf der Qualitaetsuebersicht."""
        from app.api.v1.document_quality import get_company_quality_overview

        mock_service = AsyncMock()
        mock_service.get_company_quality_overview.return_value = mock_company_overview

        request = _make_starlette_request("/api/v1/document-quality/overview")

        with patch(
            "app.services.ocr.document_quality_score_service.get_document_quality_service",
            return_value=mock_service,
        ):
            result = await get_company_quality_overview(
                request=request,
                current_user=mock_user,
                db=mock_db_session,
                company_id=TEST_COMPANY_UUID,
            )

        assert result.total_documents == 50
        assert result.average_score == 0.78
        assert result.verteilung.gruen.anzahl == 30
        assert result.verteilung.gruen.prozent == 60.0
        assert result.verteilung.gelb.anzahl == 15
        assert result.verteilung.gelb.prozent == 30.0
        assert result.verteilung.rot.anzahl == 5
        assert result.verteilung.rot.prozent == 10.0

        mock_service.get_company_quality_overview.assert_awaited_once_with(
            str(TEST_COMPANY_UUID), mock_db_session
        )

    async def test_get_company_quality_overview_empty(
        self,
        mock_db_session: AsyncMock,
        mock_user: Mock,
        mock_company_overview_empty: CompanyQualityOverview,
    ) -> None:
        """Leere Uebersicht wenn keine Dokumente vorhanden."""
        from app.api.v1.document_quality import get_company_quality_overview

        mock_service = AsyncMock()
        mock_service.get_company_quality_overview.return_value = mock_company_overview_empty

        request = _make_starlette_request("/api/v1/document-quality/overview")

        with patch(
            "app.services.ocr.document_quality_score_service.get_document_quality_service",
            return_value=mock_service,
        ):
            result = await get_company_quality_overview(
                request=request,
                current_user=mock_user,
                db=mock_db_session,
            )

        assert result.total_documents == 0
        assert result.average_score == 0.0
        assert result.verteilung.gruen.anzahl == 0
        assert result.verteilung.gelb.anzahl == 0
        assert result.verteilung.rot.anzahl == 0

    async def test_get_company_quality_overview_server_error(
        self,
        mock_db_session: AsyncMock,
        mock_user: Mock,
    ) -> None:
        """Generischer Fehler fuehrt zu HTTP 500."""
        from app.api.v1.document_quality import get_company_quality_overview

        mock_service = AsyncMock()
        mock_service.get_company_quality_overview.side_effect = RuntimeError(
            "DB-Verbindung verloren"
        )

        request = _make_starlette_request("/api/v1/document-quality/overview")

        with patch(
            "app.services.ocr.document_quality_score_service.get_document_quality_service",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_company_quality_overview(
                    request=request,
                    current_user=mock_user,
                    db=mock_db_session,
                )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Qualitaetsübersicht konnte nicht berechnet werden"

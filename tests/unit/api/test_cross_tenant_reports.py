# -*- coding: utf-8 -*-
"""
Unit Tests fuer Cross-Tenant Reports API Endpoints.

Testet:
- GET /api/v1/cross-tenant/overview   - Aggregierte Firmen-Statistiken
- GET /api/v1/cross-tenant/financial-summary - Finanz-Uebersicht pro Firma

Beide Endpoints erfordern Superuser-Berechtigung und aktivieren RLS-Bypass.

Feinpoliert und durchdacht - Multi-Tenant Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, call, patch
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.datastructures import Headers

from app.db.models import User, Company, Document, ProcessingStatus
from app.api.v1.cross_tenant_reports import (
    CompanyOverviewStats,
    CompanyFinancialSummary,
    CrossTenantOverviewResponse,
    CrossTenantFinancialResponse,
    get_cross_tenant_overview,
    get_cross_tenant_financial_summary,
)


# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Constants
# =============================================================================

TEST_ADMIN_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_1_UUID = UUID("00000000-0000-0000-0000-000000000010")
TEST_COMPANY_2_UUID = UUID("00000000-0000-0000-0000-000000000011")


# =============================================================================
# Helpers
# =============================================================================


def _make_admin_user() -> MagicMock:
    """Erstellt einen Mock Superuser/Admin."""
    user = MagicMock(spec=User)
    user.id = TEST_ADMIN_UUID
    user.email = "admin@ablage-system.de"
    user.is_superuser = True
    user.is_active = True
    return user


def _make_company(
    company_id: UUID,
    name: str,
    is_active: bool = True,
) -> MagicMock:
    """Erstellt ein Mock Company Objekt."""
    company = MagicMock(spec=Company)
    company.id = company_id
    company.name = name
    company.is_active = is_active
    return company


def _make_scalar_result(value: object) -> MagicMock:
    """Erstellt ein Mock Result mit .scalar() Rueckgabewert."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _make_scalars_result(items: list) -> MagicMock:
    """Erstellt ein Mock Result mit .scalars().all() Rueckgabewert."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result.scalars.return_value = scalars_mock
    return result


def _make_starlette_request(path: str = "/api/v1/cross-tenant/overview") -> Request:
    """Erstellt ein echtes Starlette Request Objekt (benoetigt fuer slowapi Rate Limiter).

    Setzt state-Attribute die slowapi nach _check_request_limit erwartet.
    """
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": Headers({}).raw,
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    # slowapi erwartet diese State-Attribute nach dem Rate-Limit-Check
    request.state.view_rate_limit = None
    request.state._rate_limiting_complete = True
    return request


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _bypass_rate_limiter():
    """Deaktiviert den slowapi Rate Limiter (kein Redis in Unit Tests).

    Da der @limiter.limit Decorator bereits bei Import angewendet wird,
    muss die interne _check_request_limit Methode gepatcht werden.
    """
    with patch(
        "app.core.rate_limiting.limiter._check_request_limit",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def admin_user() -> MagicMock:
    """Mock Admin/Superuser."""
    return _make_admin_user()


@pytest.fixture
def mock_request() -> Request:
    """Echtes Starlette Request Objekt (slowapi validiert isinstance-Check)."""
    return _make_starlette_request()


@pytest.fixture
def company_1() -> MagicMock:
    """Erste Test-Firma."""
    return _make_company(TEST_COMPANY_1_UUID, "Test Firma GmbH", is_active=True)


@pytest.fixture
def company_2() -> MagicMock:
    """Zweite Test-Firma."""
    return _make_company(TEST_COMPANY_2_UUID, "Zweite Firma AG", is_active=True)


# =============================================================================
# Tests: GET /api/v1/cross-tenant/overview
# =============================================================================


class TestGetCrossTenantOverview:
    """Tests fuer den Overview-Endpoint."""

    @pytest.mark.asyncio
    async def test_get_overview_success(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
        company_1: MagicMock,
    ) -> None:
        """Erfolgreicher Abruf der Firmen-Uebersicht mit Dokumenten-Statistiken."""
        db = AsyncMock(spec=AsyncSession)

        last_upload = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)

        # db.execute calls in order:
        # 1. SET LOCAL app.rls_bypass = true
        # 2. select(Company).order_by(Company.name) -> returns [company_1]
        # Per company (company_1):
        # 3. count total_documents -> 42
        # 4. count documents_this_month -> 5
        # 5. count archived_documents -> 10
        # 6. max upload_date -> last_upload
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([company_1]),  # Companies query
                _make_scalar_result(42),  # total_documents
                _make_scalar_result(5),  # documents_this_month
                _make_scalar_result(10),  # archived_documents
                _make_scalar_result(last_upload),  # last_upload_date
            ]
        )

        result = await get_cross_tenant_overview(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        assert isinstance(result, CrossTenantOverviewResponse)
        assert result.total_companies == 1
        assert result.active_companies == 1
        assert len(result.companies) == 1

        stats = result.companies[0]
        assert stats.company_id == TEST_COMPANY_1_UUID
        assert stats.company_name == "Test Firma GmbH"
        assert stats.is_active is True
        assert stats.total_documents == 42
        assert stats.documents_this_month == 5
        assert stats.archived_documents == 10
        assert stats.last_upload_date == last_upload

    @pytest.mark.asyncio
    async def test_get_overview_empty(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
    ) -> None:
        """Leeres Ergebnis wenn keine Firmen im System vorhanden."""
        db = AsyncMock(spec=AsyncSession)

        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([]),  # Keine Firmen
            ]
        )

        result = await get_cross_tenant_overview(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        assert isinstance(result, CrossTenantOverviewResponse)
        assert result.total_companies == 0
        assert result.active_companies == 0
        assert result.companies == []

    @pytest.mark.asyncio
    async def test_get_overview_multiple_companies(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
        company_1: MagicMock,
        company_2: MagicMock,
    ) -> None:
        """Mehrere Firmen mit unterschiedlichen Statistiken."""
        db = AsyncMock(spec=AsyncSession)

        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([company_1, company_2]),  # 2 Firmen
                # Company 1 counts
                _make_scalar_result(100),  # total_documents
                _make_scalar_result(15),  # documents_this_month
                _make_scalar_result(30),  # archived_documents
                _make_scalar_result(None),  # last_upload_date (kein Upload)
                # Company 2 counts
                _make_scalar_result(50),  # total_documents
                _make_scalar_result(3),  # documents_this_month
                _make_scalar_result(0),  # archived_documents
                _make_scalar_result(
                    datetime(2026, 1, 20, 8, 0, 0, tzinfo=timezone.utc)
                ),  # last_upload_date
            ]
        )

        result = await get_cross_tenant_overview(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        assert result.total_companies == 2
        assert result.active_companies == 2
        assert len(result.companies) == 2

        # Erste Firma
        assert result.companies[0].company_name == "Test Firma GmbH"
        assert result.companies[0].total_documents == 100
        assert result.companies[0].last_upload_date is None

        # Zweite Firma
        assert result.companies[1].company_name == "Zweite Firma AG"
        assert result.companies[1].total_documents == 50
        assert result.companies[1].documents_this_month == 3

    @pytest.mark.asyncio
    async def test_get_overview_counts_active_companies(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
    ) -> None:
        """active_companies zaehlt nur Firmen mit is_active=True."""
        active_company = _make_company(
            TEST_COMPANY_1_UUID, "Aktive Firma GmbH", is_active=True
        )
        inactive_company = _make_company(
            TEST_COMPANY_2_UUID, "Inaktive Firma AG", is_active=False
        )

        db = AsyncMock(spec=AsyncSession)

        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([active_company, inactive_company]),
                # Active company counts
                _make_scalar_result(20),  # total_documents
                _make_scalar_result(2),  # documents_this_month
                _make_scalar_result(5),  # archived_documents
                _make_scalar_result(None),  # last_upload_date
                # Inactive company counts
                _make_scalar_result(0),  # total_documents
                _make_scalar_result(0),  # documents_this_month
                _make_scalar_result(0),  # archived_documents
                _make_scalar_result(None),  # last_upload_date
            ]
        )

        result = await get_cross_tenant_overview(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        assert result.total_companies == 2
        assert result.active_companies == 1  # Nur aktive Firma

        # Inaktive Firma trotzdem in der Liste
        inactive = [c for c in result.companies if not c.is_active]
        assert len(inactive) == 1
        assert inactive[0].company_name == "Inaktive Firma AG"

    @pytest.mark.asyncio
    async def test_overview_sets_rls_bypass(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
    ) -> None:
        """Verifiziert, dass RLS-Bypass als erster DB-Call gesetzt wird."""
        db = AsyncMock(spec=AsyncSession)

        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([]),  # Keine Firmen
            ]
        )

        await get_cross_tenant_overview(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        # Erster execute-Call muss RLS bypass sein
        first_call_args = db.execute.call_args_list[0]
        rls_statement = first_call_args[0][0]
        # text() erzeugt ein TextClause - wir pruefen den String-Inhalt
        assert "rls_bypass" in str(rls_statement)
        assert "true" in str(rls_statement).lower()


# =============================================================================
# Tests: GET /api/v1/cross-tenant/financial-summary
# =============================================================================


class TestGetCrossTenantFinancialSummary:
    """Tests fuer den Financial-Summary-Endpoint."""

    @pytest.mark.asyncio
    async def test_get_financial_summary_success(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
        company_1: MagicMock,
    ) -> None:
        """Erfolgreicher Abruf der Finanz-Uebersicht."""
        db = AsyncMock(spec=AsyncSession)

        # db.execute calls in order:
        # 1. SET LOCAL app.rls_bypass = true
        # 2. select(Company).order_by(Company.name) -> returns [company_1]
        # Per company:
        # 3. count invoices -> 15
        # 4. count queued -> 3
        # 5. count completed -> 40
        # 6. count failed -> 2
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([company_1]),  # Companies
                _make_scalar_result(15),  # total_invoices
                _make_scalar_result(3),  # processing_queued
                _make_scalar_result(40),  # processing_completed
                _make_scalar_result(2),  # processing_failed
            ]
        )

        result = await get_cross_tenant_financial_summary(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        assert isinstance(result, CrossTenantFinancialResponse)
        assert result.total_companies == 1
        assert result.active_companies == 1
        assert len(result.companies) == 1

        summary = result.companies[0]
        assert summary.company_id == TEST_COMPANY_1_UUID
        assert summary.company_name == "Test Firma GmbH"
        assert summary.is_active is True
        assert summary.total_invoices == 15
        assert summary.processing_queued == 3
        assert summary.processing_completed == 40
        assert summary.processing_failed == 2

    @pytest.mark.asyncio
    async def test_get_financial_summary_with_invoices(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
    ) -> None:
        """Zaehlt Rechnungsdokumente (document_type=invoice) korrekt."""
        company = _make_company(
            TEST_COMPANY_1_UUID, "Rechnungs-Firma GmbH", is_active=True
        )

        db = AsyncMock(spec=AsyncSession)

        # Firma hat 250 Rechnungen, aber nur wenige in Verarbeitung
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([company]),
                _make_scalar_result(250),  # total_invoices (hoch)
                _make_scalar_result(0),  # processing_queued
                _make_scalar_result(248),  # processing_completed
                _make_scalar_result(0),  # processing_failed
            ]
        )

        result = await get_cross_tenant_financial_summary(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        summary = result.companies[0]
        assert summary.total_invoices == 250
        assert summary.processing_completed == 248
        assert summary.processing_queued == 0
        assert summary.processing_failed == 0

    @pytest.mark.asyncio
    async def test_get_financial_summary_processing_states(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
    ) -> None:
        """Zaehlt queued/completed/failed Processing-Status korrekt."""
        company = _make_company(
            TEST_COMPANY_1_UUID, "Verarbeitungs-Firma GmbH", is_active=True
        )

        db = AsyncMock(spec=AsyncSession)

        # Firma mit vielen Dokumenten in verschiedenen Zustaenden
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([company]),
                _make_scalar_result(30),  # total_invoices
                _make_scalar_result(12),  # processing_queued (PENDING + QUEUED)
                _make_scalar_result(85),  # processing_completed
                _make_scalar_result(7),  # processing_failed
            ]
        )

        result = await get_cross_tenant_financial_summary(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        summary = result.companies[0]
        assert summary.processing_queued == 12
        assert summary.processing_completed == 85
        assert summary.processing_failed == 7

        # Gesamtverarbeitung = queued + completed + failed
        total_processing = (
            summary.processing_queued
            + summary.processing_completed
            + summary.processing_failed
        )
        assert total_processing == 104

    @pytest.mark.asyncio
    async def test_financial_summary_null_counts_default_to_zero(
        self,
        admin_user: MagicMock,
        mock_request: MagicMock,
    ) -> None:
        """Null-Rueckgaben von scalar() werden als 0 behandelt."""
        company = _make_company(
            TEST_COMPANY_1_UUID, "Leere Firma GmbH", is_active=True
        )

        db = AsyncMock(spec=AsyncSession)

        # Alle Counts geben None zurueck (keine Dokumente)
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # RLS bypass
                _make_scalars_result([company]),
                _make_scalar_result(None),  # total_invoices -> 0
                _make_scalar_result(None),  # processing_queued -> 0
                _make_scalar_result(None),  # processing_completed -> 0
                _make_scalar_result(None),  # processing_failed -> 0
            ]
        )

        result = await get_cross_tenant_financial_summary(
            request=mock_request,
            admin=admin_user,
            db=db,
        )

        summary = result.companies[0]
        assert summary.total_invoices == 0
        assert summary.processing_queued == 0
        assert summary.processing_completed == 0
        assert summary.processing_failed == 0

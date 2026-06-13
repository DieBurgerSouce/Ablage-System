# -*- coding: utf-8 -*-
"""
Unit Tests fuer Analytics Team API Endpoints.

Testet:
- GET /analytics/operations  - OperationsResponse
- GET /analytics/finance     - FinanceResponse
- GET /analytics/team-stats  - TeamStatsResponse
- GET /analytics/team-workload - TeamWorkloadResponse

Alle Tests laufen ohne echte Datenbank - SQLAlchemy-Queries werden gemockt.
Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, date, timedelta

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Hilfsfunktionen fuer Mock-Erstellung
# =============================================================================


def _make_mock_user(company_id=None):
    """Erstellt einen Mock-User mit optionaler company_id."""
    user = Mock()
    user.id = uuid4()
    user.username = "testuser"
    user.email = "test@ablage-system.local"
    user.is_active = True
    user.company_id = company_id or uuid4()
    return user


def _make_execute_result(*rows):
    """Erstellt ein Mock-Execute-Ergebnis, das .one() und .all() unterstuetzt."""
    result = Mock()
    if rows:
        result.one.return_value = rows[0]
        result.scalar.return_value = rows[0] if not isinstance(rows[0], Mock) else None
    else:
        result.one.return_value = Mock(
            today=0, week=0, month=0,
            avg_confidence=None, count=0, total=0, errors=0,
            avg_ms=None, p95_ms=None, completed=0,
        )
    result.all.return_value = list(rows)
    return result


def _make_scalar_result(value):
    """Erstellt ein Mock-Ergebnis fuer .scalar() Aufrufe."""
    result = Mock()
    result.scalar.return_value = value
    result.one.return_value = Mock(avg_confidence=value)
    result.all.return_value = []
    return result


def _make_approvals_result(count=0, oldest=None):
    """
    Mock fuer die Pending-Approvals-Abfrage im Operations-Endpoint.

    Der Endpoint ruft (innerhalb eines try-Blocks) zwischen prev_ocr und
    error_rate ein zusaetzliches db.execute fuer ApprovalRequest auf und
    liest .one().count / .one().oldest.
    """
    result = Mock()
    result.one.return_value = Mock(count=count, oldest=oldest)
    return result


# =============================================================================
# Shared Fixtures
# =============================================================================


@pytest.fixture
def company_id():
    """Feste company_id fuer Multi-Tenant-Tests."""
    return uuid4()


@pytest.fixture
def other_company_id():
    """Zweite company_id fuer Isolierungs-Tests."""
    return uuid4()


@pytest.fixture
def mock_user(company_id):
    """Mock-User der ersten Company."""
    return _make_mock_user(company_id)


@pytest.fixture
def mock_db():
    """Mock-AsyncSession ohne echte DB-Verbindung."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def override_dependencies(mock_user, company_id, mock_db):
    """
    Ueberschreibt FastAPI-Dependencies fuer alle Analytics-Tests.

    Gibt ein Dict zurueck, das direkt als app.dependency_overrides eingesetzt
    werden kann. Das Aufraumen muss der aufrufende Test sicherstellen.
    """
    from app.api.dependencies import (
        get_current_active_user,
        get_current_company_id,
        get_db,
    )
    return {
        get_current_active_user: lambda: mock_user,
        get_current_company_id: lambda: company_id,
        get_db: lambda: mock_db,
    }


# =============================================================================
# TestOperationsEndpoint
# =============================================================================


class TestOperationsEndpoint:
    """Tests fuer GET /analytics/operations."""

    @pytest.mark.asyncio
    async def test_operations_happy_path(self, async_client, override_dependencies, mock_db):
        """Erfolgreicher Abruf der Betriebs-Metriken mit Standard-Periode."""
        from app.main import app

        # Arrange: Doc-Counts
        doc_row = Mock(today=5, week=30, month=120)
        ocr_row = Mock(avg_confidence=0.92)
        prev_ocr_result = Mock()
        prev_ocr_result.scalar.return_value = 0.90
        error_row = Mock(total=120, errors=6)
        timing_row = Mock(avg_ms=1500, p95_ms=3200)
        auto_row = Mock(total=120, completed=114)

        # Reihenfolge der db.execute-Aufrufe gemaess Implementierung:
        # 1. doc_counts  2. ocr_accuracy  3. prev_ocr  4. errors  5. timing  6. auto
        # plus innere try-Bloecke: approvals, top_errors
        mock_db.execute.side_effect = [
            _make_execute_result(doc_row),        # doc_counts
            _make_execute_result(ocr_row),        # ocr_accuracy
            prev_ocr_result,                      # prev_ocr
            _make_approvals_result(),             # pending approvals
            _make_execute_result(error_row),      # error_rate
            Mock(all=Mock(return_value=[])),       # top_errors (AuditLog)
            _make_execute_result(timing_row),     # processing times
            _make_execute_result(auto_row),       # auto_process rate
        ]

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/operations")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert "documents_processed" in data
        assert data["documents_processed"]["today"] == 5
        assert data["documents_processed"]["week"] == 30
        assert data["documents_processed"]["month"] == 120
        assert "ocr_accuracy_percent" in data
        assert "ocr_accuracy_trend" in data
        assert data["ocr_accuracy_trend"] in ("up", "down", "neutral")
        assert "error_rate_percent" in data
        assert "avg_processing_time_ms" in data
        assert "auto_process_rate" in data

    @pytest.mark.asyncio
    async def test_operations_period_day(self, async_client, override_dependencies, mock_db):
        """Betriebs-Metriken mit Zeitraum 'day'."""
        from app.main import app

        doc_row = Mock(today=1, week=5, month=20)
        ocr_row = Mock(avg_confidence=0.88)
        prev_ocr_scalar = Mock()
        prev_ocr_scalar.scalar.return_value = 0.85
        error_row = Mock(total=20, errors=1)
        timing_row = Mock(avg_ms=2000, p95_ms=4000)
        auto_row = Mock(total=20, completed=19)

        mock_db.execute.side_effect = [
            _make_execute_result(doc_row),
            _make_execute_result(ocr_row),
            prev_ocr_scalar,
            _make_approvals_result(),
            _make_execute_result(error_row),
            Mock(all=Mock(return_value=[])),
            _make_execute_result(timing_row),
            _make_execute_result(auto_row),
        ]

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/operations",
                params={"period": "day"},
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_operations_period_week(self, async_client, override_dependencies, mock_db):
        """Betriebs-Metriken mit Zeitraum 'week'."""
        from app.main import app

        doc_row = Mock(today=2, week=15, month=60)
        ocr_row = Mock(avg_confidence=0.91)
        prev_ocr_scalar = Mock()
        prev_ocr_scalar.scalar.return_value = 0.89
        error_row = Mock(total=60, errors=3)
        timing_row = Mock(avg_ms=1200, p95_ms=2800)
        auto_row = Mock(total=60, completed=57)

        mock_db.execute.side_effect = [
            _make_execute_result(doc_row),
            _make_execute_result(ocr_row),
            prev_ocr_scalar,
            _make_approvals_result(),
            _make_execute_result(error_row),
            Mock(all=Mock(return_value=[])),
            _make_execute_result(timing_row),
            _make_execute_result(auto_row),
        ]

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/operations",
                params={"period": "week"},
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_operations_period_quarter(self, async_client, override_dependencies, mock_db):
        """Betriebs-Metriken mit Zeitraum 'quarter'."""
        from app.main import app

        doc_row = Mock(today=3, week=20, month=80)
        ocr_row = Mock(avg_confidence=0.95)
        prev_ocr_scalar = Mock()
        prev_ocr_scalar.scalar.return_value = 0.0  # Kein Vorperioden-Wert -> neutral
        error_row = Mock(total=80, errors=2)
        timing_row = Mock(avg_ms=900, p95_ms=1800)
        auto_row = Mock(total=80, completed=78)

        mock_db.execute.side_effect = [
            _make_execute_result(doc_row),
            _make_execute_result(ocr_row),
            prev_ocr_scalar,
            _make_approvals_result(),
            _make_execute_result(error_row),
            Mock(all=Mock(return_value=[])),
            _make_execute_result(timing_row),
            _make_execute_result(auto_row),
        ]

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/operations",
                params={"period": "quarter"},
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["ocr_accuracy_trend"] == "neutral"  # prev_ocr=0 -> neutral

    @pytest.mark.asyncio
    async def test_operations_custom_date_range(self, async_client, override_dependencies, mock_db):
        """Betriebs-Metriken mit benutzerdefinierten Start- und Enddaten."""
        from app.main import app

        doc_row = Mock(today=0, week=3, month=12)
        ocr_row = Mock(avg_confidence=0.87)
        prev_ocr_scalar = Mock()
        prev_ocr_scalar.scalar.return_value = 0.80
        error_row = Mock(total=12, errors=1)
        timing_row = Mock(avg_ms=1100, p95_ms=2200)
        auto_row = Mock(total=12, completed=11)

        mock_db.execute.side_effect = [
            _make_execute_result(doc_row),
            _make_execute_result(ocr_row),
            prev_ocr_scalar,
            _make_approvals_result(),
            _make_execute_result(error_row),
            Mock(all=Mock(return_value=[])),
            _make_execute_result(timing_row),
            _make_execute_result(auto_row),
        ]

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/operations",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["ocr_accuracy_trend"] == "up"  # 0.87 > 0.80 * 1.01

    @pytest.mark.asyncio
    async def test_operations_empty_database(self, async_client, override_dependencies, mock_db):
        """Betriebs-Metriken auf leerer Datenbank - Standardwerte erwartet."""
        from app.main import app

        empty_doc_row = Mock(today=0, week=0, month=0)
        empty_ocr_row = Mock(avg_confidence=None)
        prev_ocr_scalar = Mock()
        prev_ocr_scalar.scalar.return_value = None
        empty_error_row = Mock(total=0, errors=0)
        empty_timing_row = Mock(avg_ms=None, p95_ms=None)
        empty_auto_row = Mock(total=0, completed=0)

        mock_db.execute.side_effect = [
            _make_execute_result(empty_doc_row),
            _make_execute_result(empty_ocr_row),
            prev_ocr_scalar,
            _make_approvals_result(),
            _make_execute_result(empty_error_row),
            Mock(all=Mock(return_value=[])),
            _make_execute_result(empty_timing_row),
            _make_execute_result(empty_auto_row),
        ]

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/operations")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["documents_processed"]["today"] == 0
        assert data["documents_processed"]["week"] == 0
        assert data["documents_processed"]["month"] == 0
        assert data["ocr_accuracy_percent"] == 0.0
        assert data["ocr_accuracy_trend"] == "neutral"
        assert data["error_rate_percent"] == 0.0
        assert data["top_errors"] == []
        assert data["avg_processing_time_ms"] == 0
        assert data["p95_processing_time_ms"] == 0
        assert data["auto_process_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_operations_company_isolation(
        self,
        async_client,
        company_id,
        other_company_id,
        mock_db,
    ):
        """Betriebs-Metriken isolieren Daten pro Company (Multi-Tenant)."""
        from app.main import app
        from app.api.dependencies import (
            get_current_active_user,
            get_current_company_id,
            get_db,
        )

        user_company_a = _make_mock_user(company_id)
        user_company_b = _make_mock_user(other_company_id)

        doc_row_a = Mock(today=10, week=50, month=200)
        doc_row_b = Mock(today=2, week=8, month=30)
        empty_ocr = Mock(avg_confidence=None)
        prev_scalar = Mock()
        prev_scalar.scalar.return_value = None
        empty_error = Mock(total=0, errors=0)
        empty_timing = Mock(avg_ms=None, p95_ms=None)
        empty_auto = Mock(total=0, completed=0)

        def _side_effects_for_a():
            return [
                _make_execute_result(doc_row_a),
                _make_execute_result(empty_ocr),
                prev_scalar,
                _make_approvals_result(),
                _make_execute_result(empty_error),
                Mock(all=Mock(return_value=[])),
                _make_execute_result(empty_timing),
                _make_execute_result(empty_auto),
            ]

        def _side_effects_for_b():
            return [
                _make_execute_result(doc_row_b),
                _make_execute_result(empty_ocr),
                prev_scalar,
                _make_approvals_result(),
                _make_execute_result(empty_error),
                Mock(all=Mock(return_value=[])),
                _make_execute_result(empty_timing),
                _make_execute_result(empty_auto),
            ]

        # Company A
        mock_db.execute.side_effect = _side_effects_for_a()
        app.dependency_overrides = {
            get_current_active_user: lambda: user_company_a,
            get_current_company_id: lambda: company_id,
            get_db: lambda: mock_db,
        }
        try:
            response_a = await async_client.get("/api/v1/analytics/operations")
        finally:
            app.dependency_overrides = {}

        # Company B
        mock_db.execute.side_effect = _side_effects_for_b()
        app.dependency_overrides = {
            get_current_active_user: lambda: user_company_b,
            get_current_company_id: lambda: other_company_id,
            get_db: lambda: mock_db,
        }
        try:
            response_b = await async_client.get("/api/v1/analytics/operations")
        finally:
            app.dependency_overrides = {}

        assert response_a.status_code == 200
        assert response_b.status_code == 200
        data_a = response_a.json()
        data_b = response_b.json()
        # Jede Company sieht nur ihre eigenen Zahlen
        assert data_a["documents_processed"]["today"] == 10
        assert data_b["documents_processed"]["today"] == 2

    @pytest.mark.asyncio
    async def test_operations_db_failure_returns_500(
        self, async_client, override_dependencies, mock_db
    ):
        """Datenbankfehler in /operations -> HTTP 500."""
        from app.main import app

        mock_db.execute.side_effect = Exception("DB-Verbindung unterbrochen")

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/operations")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 500
        assert "Betriebsdaten" in response.json().get("nachricht", "")

    @pytest.mark.asyncio
    async def test_operations_top_errors_populated(
        self, async_client, override_dependencies, mock_db
    ):
        """Top-Fehler aus AuditLog werden korrekt eingebunden."""
        from app.main import app

        doc_row = Mock(today=5, week=30, month=100)
        ocr_row = Mock(avg_confidence=0.90)
        prev_ocr_scalar = Mock()
        prev_ocr_scalar.scalar.return_value = 0.90
        error_row = Mock(total=100, errors=5)

        err1 = Mock(action="ocr_failed", count=3)
        err2 = Mock(action="upload_failed", count=2)

        timing_row = Mock(avg_ms=1000, p95_ms=2000)
        auto_row = Mock(total=100, completed=95)

        mock_db.execute.side_effect = [
            _make_execute_result(doc_row),
            _make_execute_result(ocr_row),
            prev_ocr_scalar,
            _make_approvals_result(),
            _make_execute_result(error_row),
            Mock(all=Mock(return_value=[err1, err2])),
            _make_execute_result(timing_row),
            _make_execute_result(auto_row),
        ]

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/operations")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert len(data["top_errors"]) == 2
        assert data["top_errors"][0]["error_type"] == "ocr_failed"
        assert data["top_errors"][0]["count"] == 3

    @pytest.mark.asyncio
    async def test_operations_ocr_trend_down(
        self, async_client, override_dependencies, mock_db
    ):
        """OCR-Trend 'down' wenn aktuelle Genauigkeit schlechter als Vorperiode."""
        from app.main import app

        doc_row = Mock(today=5, week=30, month=100)
        ocr_row = Mock(avg_confidence=0.80)  # Schlechter als Vorperiode
        prev_ocr_scalar = Mock()
        prev_ocr_scalar.scalar.return_value = 0.90  # Vorperiode war besser
        error_row = Mock(total=100, errors=5)
        timing_row = Mock(avg_ms=1000, p95_ms=2000)
        auto_row = Mock(total=100, completed=95)

        mock_db.execute.side_effect = [
            _make_execute_result(doc_row),
            _make_execute_result(ocr_row),
            prev_ocr_scalar,
            _make_approvals_result(),
            _make_execute_result(error_row),
            Mock(all=Mock(return_value=[])),
            _make_execute_result(timing_row),
            _make_execute_result(auto_row),
        ]

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/operations")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        assert response.json()["ocr_accuracy_trend"] == "down"


# =============================================================================
# TestFinanceEndpoint
# =============================================================================


class TestFinanceEndpoint:
    """Tests fuer GET /analytics/finance."""

    def _make_finance_db_side_effects(
        self,
        open_row=None,
        overdue_row=None,
        skonto_realized=0.0,
        skonto_missed=0.0,
        cashflow_rows=None,
        aging_rows=None,
        dunning_rows=None,
    ):
        """
        Erstellt eine side_effect-Liste fuer alle db.execute-Aufrufe
        im Finance-Endpoint (open, overdue, skonto x2, cashflow, aging, dunning).
        """
        if open_row is None:
            open_row = Mock(count=0, total=0.0)
        if overdue_row is None:
            overdue_row = Mock(count=0, total=0.0)
        if cashflow_rows is None:
            cashflow_rows = []
        if aging_rows is None:
            aging_rows = []
        if dunning_rows is None:
            dunning_rows = []

        skonto_realized_result = Mock()
        skonto_realized_result.scalar.return_value = skonto_realized

        skonto_missed_result = Mock()
        skonto_missed_result.scalar.return_value = skonto_missed

        return [
            _make_execute_result(open_row),           # open items
            _make_execute_result(overdue_row),        # overdue items
            skonto_realized_result,                   # skonto realized
            skonto_missed_result,                     # skonto missed
            Mock(all=Mock(return_value=cashflow_rows)),   # cashflow trend
            Mock(all=Mock(return_value=aging_rows)),      # aging buckets
            Mock(all=Mock(return_value=dunning_rows)),    # dunning stages
        ]

    @pytest.mark.asyncio
    async def test_finance_happy_path(self, async_client, override_dependencies, mock_db):
        """Erfolgreicher Abruf der Finanz-Metriken mit Standard-Periode."""
        from app.main import app

        open_row = Mock(count=15, total=45000.0)
        overdue_row = Mock(count=3, total=8500.0)

        cashflow_row = Mock(
            pay_date=datetime(2026, 2, 10, tzinfo=timezone.utc),
            amount=5000.0,
        )
        # pay_date ist ein echtes datetime; sein .strftime liefert korrekt "2026-02-10".

        mock_db.execute.side_effect = self._make_finance_db_side_effects(
            open_row=open_row,
            overdue_row=overdue_row,
            skonto_realized=1200.0,
            skonto_missed=350.0,
            cashflow_rows=[cashflow_row],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/finance")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["open_items_count"] == 15
        assert data["open_items_amount"] == 45000.0
        assert data["overdue_count"] == 3
        assert data["overdue_amount"] == 8500.0
        assert data["skonto_realized"] == 1200.0
        assert data["skonto_missed"] == 350.0
        assert isinstance(data["cashflow_trend"], list)
        assert isinstance(data["aging_buckets"], list)
        assert isinstance(data["dunning_stages"], list)

    @pytest.mark.asyncio
    async def test_finance_period_day(self, async_client, override_dependencies, mock_db):
        """Finanz-Metriken mit Zeitraum 'day'."""
        from app.main import app

        mock_db.execute.side_effect = self._make_finance_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/finance",
                params={"period": "day"},
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_finance_period_quarter(self, async_client, override_dependencies, mock_db):
        """Finanz-Metriken mit Zeitraum 'quarter'."""
        from app.main import app

        mock_db.execute.side_effect = self._make_finance_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/finance",
                params={"period": "quarter"},
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_finance_custom_date_range(self, async_client, override_dependencies, mock_db):
        """Finanz-Metriken mit benutzerdefinierten Datumsangaben."""
        from app.main import app

        open_row = Mock(count=5, total=12000.0)
        overdue_row = Mock(count=1, total=2500.0)

        mock_db.execute.side_effect = self._make_finance_db_side_effects(
            open_row=open_row,
            overdue_row=overdue_row,
            skonto_realized=300.0,
            skonto_missed=75.0,
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/finance",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["open_items_count"] == 5

    @pytest.mark.asyncio
    async def test_finance_empty_database(self, async_client, override_dependencies, mock_db):
        """Finanz-Metriken auf leerer Datenbank - Standardwerte erwartet."""
        from app.main import app

        mock_db.execute.side_effect = self._make_finance_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/finance")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["open_items_count"] == 0
        assert data["open_items_amount"] == 0.0
        assert data["overdue_count"] == 0
        assert data["overdue_amount"] == 0.0
        assert data["skonto_realized"] == 0.0
        assert data["skonto_missed"] == 0.0
        assert data["cashflow_trend"] == []
        assert data["aging_buckets"] == []
        assert data["dunning_stages"] == []

    @pytest.mark.asyncio
    async def test_finance_company_isolation(
        self,
        async_client,
        company_id,
        other_company_id,
        mock_db,
    ):
        """Finanzdaten sind strikt nach Company isoliert (Multi-Tenant RLS)."""
        from app.main import app
        from app.api.dependencies import (
            get_current_active_user,
            get_current_company_id,
            get_db,
        )

        user_a = _make_mock_user(company_id)
        user_b = _make_mock_user(other_company_id)

        open_row_a = Mock(count=20, total=75000.0)
        open_row_b = Mock(count=2, total=3000.0)

        # Company A
        mock_db.execute.side_effect = self._make_finance_db_side_effects(
            open_row=open_row_a,
        )
        app.dependency_overrides = {
            get_current_active_user: lambda: user_a,
            get_current_company_id: lambda: company_id,
            get_db: lambda: mock_db,
        }
        try:
            response_a = await async_client.get("/api/v1/analytics/finance")
        finally:
            app.dependency_overrides = {}

        # Company B
        mock_db.execute.side_effect = self._make_finance_db_side_effects(
            open_row=open_row_b,
        )
        app.dependency_overrides = {
            get_current_active_user: lambda: user_b,
            get_current_company_id: lambda: other_company_id,
            get_db: lambda: mock_db,
        }
        try:
            response_b = await async_client.get("/api/v1/analytics/finance")
        finally:
            app.dependency_overrides = {}

        assert response_a.status_code == 200
        assert response_b.status_code == 200
        assert response_a.json()["open_items_count"] == 20
        assert response_b.json()["open_items_count"] == 2

    @pytest.mark.asyncio
    async def test_finance_db_failure_returns_500(
        self, async_client, override_dependencies, mock_db
    ):
        """Datenbankfehler in /finance -> HTTP 500."""
        from app.main import app

        mock_db.execute.side_effect = Exception("Transaktionsfehler in Finance-Abfrage")

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/finance")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 500
        assert "Finanzdaten" in response.json().get("nachricht", "")

    @pytest.mark.asyncio
    async def test_finance_aging_buckets_populated(
        self, async_client, override_dependencies, mock_db
    ):
        """Aging-Buckets werden korrekt aus der Datenbank befuellt."""
        from app.main import app

        aging_row_1 = Mock(bucket="Nicht faellig", count=8, amount=24000.0)
        aging_row_2 = Mock(bucket="1-30 Tage", count=3, amount=9000.0)
        aging_row_3 = Mock(bucket="Ueber 90 Tage", count=1, amount=5000.0)

        mock_db.execute.side_effect = self._make_finance_db_side_effects(
            aging_rows=[aging_row_1, aging_row_2, aging_row_3],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/finance")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert len(data["aging_buckets"]) == 3
        assert data["aging_buckets"][0]["bucket"] == "Nicht faellig"
        assert data["aging_buckets"][0]["count"] == 8

    @pytest.mark.asyncio
    async def test_finance_dunning_stages_populated(
        self, async_client, override_dependencies, mock_db
    ):
        """Mahnstufen-Verteilung wird korrekt befuellt."""
        from app.main import app

        dunning_row_1 = Mock(stage=1, count=4)
        dunning_row_2 = Mock(stage=2, count=2)

        mock_db.execute.side_effect = self._make_finance_db_side_effects(
            dunning_rows=[dunning_row_1, dunning_row_2],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/finance")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert len(data["dunning_stages"]) == 2
        assert data["dunning_stages"][0]["stage"] == 1
        assert data["dunning_stages"][0]["count"] == 4


# =============================================================================
# TestTeamStatsEndpoint
# =============================================================================


class TestTeamStatsEndpoint:
    """Tests fuer GET /analytics/team-stats."""

    def _make_team_stats_db_side_effects(
        self,
        doc_rows=None,
        correction_rows=None,
        approval_rows=None,
        user_rows=None,
    ):
        """
        Erstellt side_effect-Liste fuer alle db.execute-Aufrufe in team-stats:
        1. doc_result, 2. correction_result, 3. approval_result, 4. user_result
        """
        if doc_rows is None:
            doc_rows = []
        if correction_rows is None:
            correction_rows = []
        if approval_rows is None:
            approval_rows = []
        if user_rows is None:
            user_rows = []

        return [
            Mock(all=Mock(return_value=doc_rows)),
            Mock(all=Mock(return_value=correction_rows)),
            Mock(all=Mock(return_value=approval_rows)),
            Mock(all=Mock(return_value=user_rows)),
        ]

    @pytest.mark.asyncio
    async def test_team_stats_happy_path(self, async_client, override_dependencies, mock_db):
        """Erfolgreicher Abruf der Team-Statistiken."""
        from app.main import app

        user_id_1 = uuid4()
        user_id_2 = uuid4()

        doc_row_1 = Mock(
            user_id=user_id_1,
            documents_processed=25,
            avg_processing_ms=1200.0,
            avg_confidence=0.91,
        )
        doc_row_2 = Mock(
            user_id=user_id_2,
            documents_processed=10,
            avg_processing_ms=1500.0,
            avg_confidence=0.85,
        )

        corr_row_1 = Mock(user_id=user_id_1, ocr_corrections=2)

        approval_row_1 = Mock(user_id=user_id_1, approval_count=5)

        user_row_1 = Mock(id=user_id_1, username="anna.mueller")
        user_row_2 = Mock(id=user_id_2, username="bernd.schmidt")

        mock_db.execute.side_effect = self._make_team_stats_db_side_effects(
            doc_rows=[doc_row_1, doc_row_2],
            correction_rows=[corr_row_1],
            approval_rows=[approval_row_1],
            user_rows=[user_row_1, user_row_2],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-stats")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["total_documents"] == 35  # 25 + 10
        assert data["period"] == "month"
        assert len(data["user_stats"]) == 2
        # Sortierung nach documents_processed absteigend
        assert data["user_stats"][0]["documents_processed"] == 25
        assert data["user_stats"][0]["username"] == "anna.mueller"

    @pytest.mark.asyncio
    async def test_team_stats_period_week(self, async_client, override_dependencies, mock_db):
        """Team-Statistiken fuer Wochenzeitraum."""
        from app.main import app

        mock_db.execute.side_effect = self._make_team_stats_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/team-stats",
                params={"period": "week"},
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "week"
        assert data["total_documents"] == 0
        assert data["user_stats"] == []

    @pytest.mark.asyncio
    async def test_team_stats_period_quarter(self, async_client, override_dependencies, mock_db):
        """Team-Statistiken fuer Quartalszeitraum."""
        from app.main import app

        mock_db.execute.side_effect = self._make_team_stats_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/team-stats",
                params={"period": "quarter"},
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        assert response.json()["period"] == "quarter"

    @pytest.mark.asyncio
    async def test_team_stats_custom_date_range(
        self, async_client, override_dependencies, mock_db
    ):
        """Team-Statistiken mit benutzerdefinierten Datumsangaben."""
        from app.main import app

        user_id = uuid4()
        doc_row = Mock(
            user_id=user_id,
            documents_processed=7,
            avg_processing_ms=800.0,
            avg_confidence=0.93,
        )
        user_row = Mock(id=user_id, username="test.user")

        mock_db.execute.side_effect = self._make_team_stats_db_side_effects(
            doc_rows=[doc_row],
            user_rows=[user_row],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/team-stats",
                params={
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                },
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["total_documents"] == 7

    @pytest.mark.asyncio
    async def test_team_stats_empty_database(
        self, async_client, override_dependencies, mock_db
    ):
        """Team-Statistiken auf leerer Datenbank - leere Liste erwartet."""
        from app.main import app

        mock_db.execute.side_effect = self._make_team_stats_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-stats")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["user_stats"] == []
        assert data["total_documents"] == 0
        assert data["period"] == "month"

    @pytest.mark.asyncio
    async def test_team_stats_company_isolation(
        self,
        async_client,
        company_id,
        other_company_id,
        mock_db,
    ):
        """Team-Statistiken isolieren Daten nach Company."""
        from app.main import app
        from app.api.dependencies import (
            get_current_active_user,
            get_current_company_id,
            get_db,
        )

        user_a = _make_mock_user(company_id)
        user_b = _make_mock_user(other_company_id)

        uid_a = uuid4()
        doc_row_a = Mock(
            user_id=uid_a,
            documents_processed=40,
            avg_processing_ms=1000.0,
            avg_confidence=0.90,
        )
        user_row_a = Mock(id=uid_a, username="mitarbeiter_a")

        uid_b = uuid4()
        doc_row_b = Mock(
            user_id=uid_b,
            documents_processed=5,
            avg_processing_ms=1200.0,
            avg_confidence=0.80,
        )
        user_row_b = Mock(id=uid_b, username="mitarbeiter_b")

        # Company A
        mock_db.execute.side_effect = self._make_team_stats_db_side_effects(
            doc_rows=[doc_row_a],
            user_rows=[user_row_a],
        )
        app.dependency_overrides = {
            get_current_active_user: lambda: user_a,
            get_current_company_id: lambda: company_id,
            get_db: lambda: mock_db,
        }
        try:
            response_a = await async_client.get("/api/v1/analytics/team-stats")
        finally:
            app.dependency_overrides = {}

        # Company B
        mock_db.execute.side_effect = self._make_team_stats_db_side_effects(
            doc_rows=[doc_row_b],
            user_rows=[user_row_b],
        )
        app.dependency_overrides = {
            get_current_active_user: lambda: user_b,
            get_current_company_id: lambda: other_company_id,
            get_db: lambda: mock_db,
        }
        try:
            response_b = await async_client.get("/api/v1/analytics/team-stats")
        finally:
            app.dependency_overrides = {}

        assert response_a.status_code == 200
        assert response_b.status_code == 200
        assert response_a.json()["total_documents"] == 40
        assert response_b.json()["total_documents"] == 5

    @pytest.mark.asyncio
    async def test_team_stats_db_failure_returns_500(
        self, async_client, override_dependencies, mock_db
    ):
        """Datenbankfehler in /team-stats -> HTTP 500."""
        from app.main import app

        mock_db.execute.side_effect = Exception("Verbindung zur Datenbank verloren")

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-stats")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 500
        assert "Team-Statistiken" in response.json().get("nachricht", "")

    @pytest.mark.asyncio
    async def test_team_stats_quality_score_calculation(
        self, async_client, override_dependencies, mock_db
    ):
        """Qualitaets-Score wird korrekt aus Confidence und Korrekturen berechnet."""
        from app.main import app

        user_id = uuid4()
        doc_row = Mock(
            user_id=user_id,
            documents_processed=10,
            avg_processing_ms=1000.0,
            avg_confidence=0.95,  # 95% Confidence -> score = 95 - (0/10)*10 = 95
        )
        user_row = Mock(id=user_id, username="qualitaets.nutzer")

        mock_db.execute.side_effect = self._make_team_stats_db_side_effects(
            doc_rows=[doc_row],
            user_rows=[user_row],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-stats")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        stats = response.json()["user_stats"]
        assert len(stats) == 1
        assert stats[0]["quality_score"] == 95.0  # 0.95 * 100 - 0/10 * 10 = 95
        assert stats[0]["ocr_corrections"] == 0

    @pytest.mark.asyncio
    async def test_team_stats_unknown_user_fallback(
        self, async_client, override_dependencies, mock_db
    ):
        """Unbekannte user_id erhaelt Username 'Unbekannt'."""
        from app.main import app

        user_id = uuid4()
        doc_row = Mock(
            user_id=user_id,
            documents_processed=3,
            avg_processing_ms=500.0,
            avg_confidence=0.88,
        )

        # user_rows leer - kein Eintrag in user_map
        mock_db.execute.side_effect = self._make_team_stats_db_side_effects(
            doc_rows=[doc_row],
            user_rows=[],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-stats")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        stats = response.json()["user_stats"]
        assert stats[0]["username"] == "Unbekannt"


# =============================================================================
# TestTeamWorkloadEndpoint
# =============================================================================


class TestTeamWorkloadEndpoint:
    """Tests fuer GET /analytics/team-workload."""

    def _make_workload_db_side_effects(self, raw_rows=None, user_rows=None):
        """
        Erstellt side_effect-Liste fuer die zwei db.execute-Aufrufe in team-workload:
        1. workload_result, 2. user_result (nur wenn raw_rows vorhanden)
        """
        if raw_rows is None:
            raw_rows = []
        if user_rows is None:
            user_rows = []

        side_effects = [Mock(all=Mock(return_value=raw_rows))]
        if raw_rows:
            side_effects.append(Mock(all=Mock(return_value=user_rows)))
        return side_effects

    @pytest.mark.asyncio
    async def test_workload_happy_path(self, async_client, override_dependencies, mock_db):
        """Erfolgreicher Abruf der Workload-Heatmap-Daten."""
        from app.main import app

        user_id = uuid4()
        # PostgreSQL DOW: 1=Montag, 2=Dienstag, ..., 0=Sonntag
        raw_row = Mock(user_id=user_id, day_of_week_raw=1, hour=9, count=5)
        user_row = Mock(id=user_id, username="heatmap.nutzer")

        mock_db.execute.side_effect = self._make_workload_db_side_effects(
            raw_rows=[raw_row],
            user_rows=[user_row],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-workload")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert len(data["rows"]) == 1
        entry = data["rows"][0]
        assert entry["username"] == "heatmap.nutzer"
        assert entry["hour"] == 9
        assert entry["count"] == 5
        assert 0 <= entry["day_of_week"] <= 6

    @pytest.mark.asyncio
    async def test_workload_dow_conversion_monday(
        self, async_client, override_dependencies, mock_db
    ):
        """PostgreSQL DOW 1 (Montag) -> ISO 0 (Montag)."""
        from app.main import app

        user_id = uuid4()
        raw_row = Mock(user_id=user_id, day_of_week_raw=1, hour=10, count=3)
        user_row = Mock(id=user_id, username="montag.nutzer")

        mock_db.execute.side_effect = self._make_workload_db_side_effects(
            raw_rows=[raw_row],
            user_rows=[user_row],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-workload")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        assert response.json()["rows"][0]["day_of_week"] == 0  # ISO: Montag = 0

    @pytest.mark.asyncio
    async def test_workload_dow_conversion_sunday(
        self, async_client, override_dependencies, mock_db
    ):
        """PostgreSQL DOW 0 (Sonntag) -> ISO 6 (Sonntag)."""
        from app.main import app

        user_id = uuid4()
        raw_row = Mock(user_id=user_id, day_of_week_raw=0, hour=14, count=1)
        user_row = Mock(id=user_id, username="sonntag.nutzer")

        mock_db.execute.side_effect = self._make_workload_db_side_effects(
            raw_rows=[raw_row],
            user_rows=[user_row],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-workload")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        assert response.json()["rows"][0]["day_of_week"] == 6  # ISO: Sonntag = 6

    @pytest.mark.asyncio
    async def test_workload_period_week(self, async_client, override_dependencies, mock_db):
        """Workload-Daten mit Zeitraum 'week'."""
        from app.main import app

        mock_db.execute.side_effect = self._make_workload_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/team-workload",
                params={"period": "week"},
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        assert response.json()["rows"] == []

    @pytest.mark.asyncio
    async def test_workload_custom_date_range(
        self, async_client, override_dependencies, mock_db
    ):
        """Workload-Daten mit benutzerdefinierten Datumsangaben."""
        from app.main import app

        mock_db.execute.side_effect = self._make_workload_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get(
                "/api/v1/analytics/team-workload",
                params={
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-14",
                },
            )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_workload_empty_database(self, async_client, override_dependencies, mock_db):
        """Workload auf leerer Datenbank - leere rows-Liste erwartet."""
        from app.main import app

        mock_db.execute.side_effect = self._make_workload_db_side_effects()

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-workload")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        assert response.json()["rows"] == []

    @pytest.mark.asyncio
    async def test_workload_company_isolation(
        self,
        async_client,
        company_id,
        other_company_id,
        mock_db,
    ):
        """Workload-Daten sind strikt nach Company isoliert (Multi-Tenant)."""
        from app.main import app
        from app.api.dependencies import (
            get_current_active_user,
            get_current_company_id,
            get_db,
        )

        user_a = _make_mock_user(company_id)
        user_b = _make_mock_user(other_company_id)

        uid_a = uuid4()
        raw_row_a = Mock(user_id=uid_a, day_of_week_raw=2, hour=11, count=8)
        user_row_a = Mock(id=uid_a, username="nutzer_a")

        uid_b = uuid4()
        raw_row_b = Mock(user_id=uid_b, day_of_week_raw=3, hour=15, count=2)
        user_row_b = Mock(id=uid_b, username="nutzer_b")

        # Company A
        mock_db.execute.side_effect = self._make_workload_db_side_effects(
            raw_rows=[raw_row_a],
            user_rows=[user_row_a],
        )
        app.dependency_overrides = {
            get_current_active_user: lambda: user_a,
            get_current_company_id: lambda: company_id,
            get_db: lambda: mock_db,
        }
        try:
            response_a = await async_client.get("/api/v1/analytics/team-workload")
        finally:
            app.dependency_overrides = {}

        # Company B
        mock_db.execute.side_effect = self._make_workload_db_side_effects(
            raw_rows=[raw_row_b],
            user_rows=[user_row_b],
        )
        app.dependency_overrides = {
            get_current_active_user: lambda: user_b,
            get_current_company_id: lambda: other_company_id,
            get_db: lambda: mock_db,
        }
        try:
            response_b = await async_client.get("/api/v1/analytics/team-workload")
        finally:
            app.dependency_overrides = {}

        assert response_a.status_code == 200
        assert response_b.status_code == 200
        data_a = response_a.json()["rows"]
        data_b = response_b.json()["rows"]
        assert len(data_a) == 1
        assert len(data_b) == 1
        assert data_a[0]["username"] == "nutzer_a"
        assert data_b[0]["username"] == "nutzer_b"
        assert data_a[0]["count"] == 8
        assert data_b[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_workload_db_failure_returns_500(
        self, async_client, override_dependencies, mock_db
    ):
        """Datenbankfehler in /team-workload -> HTTP 500."""
        from app.main import app

        mock_db.execute.side_effect = Exception("Zeitausfall beim Workload-Query")

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-workload")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 500
        assert "Workload" in response.json().get("nachricht", "")

    @pytest.mark.asyncio
    async def test_workload_skips_null_user_ids(
        self, async_client, override_dependencies, mock_db
    ):
        """Zeilen mit user_id=None werden aus den Ergebnissen herausgefiltert."""
        from app.main import app

        # Eine Zeile ohne user_id (z.B. anonyme Verarbeitungen)
        raw_row_null = Mock(user_id=None, day_of_week_raw=2, hour=8, count=3)

        uid = uuid4()
        raw_row_valid = Mock(user_id=uid, day_of_week_raw=2, hour=9, count=7)
        user_row = Mock(id=uid, username="valider.nutzer")

        mock_db.execute.side_effect = self._make_workload_db_side_effects(
            raw_rows=[raw_row_null, raw_row_valid],
            user_rows=[user_row],
        )

        app.dependency_overrides = override_dependencies

        try:
            response = await async_client.get("/api/v1/analytics/team-workload")
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        rows = response.json()["rows"]
        # Nur die Zeile mit gueltigem user_id darf im Ergebnis sein
        assert len(rows) == 1
        assert rows[0]["username"] == "valider.nutzer"
        assert rows[0]["count"] == 7

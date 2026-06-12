"""Regressionstests für die 10 Schemathesis-5xx-Bugs (W1-004).

Quelle: docs/qa-reports/2026-06-10-schemathesis-baseline.md
Jeder Test bildet einen der 10 reproduzierbaren Funde ab:

 #1  POST /accounting/fx-gain-loss/calculate  (Denormal-Float, Währung "000")
 #2  POST /activity/filter                    (leerer Body {})
 #3  POST /admin/integration-sync/datev/writeback (leere Pflichtfelder)
 #4  POST /admin/jobs/queue/clear?status=AAA  (ungültiges Enum)
 #5  POST /admin/rate-limits/bulk/reset       (nicht existente UUID)
 #6  POST /admin/roles                        (kaputter Audit-Logger-Aufruf)
 #7  POST /admin/system/gpu/clear-cache       (ohne GPU-Kontext)
 #8  POST /ai/contracts/analyze               (Minimal-Text "00")
 #9  POST /cashflow-prediction/scenario       (fremde/nicht existente IDs)
 #10 POST /lifecycle/destruction-protocols    (nicht existente Dokumente)

Muster: Mini-FastAPI-App + dependency_overrides (wie test_search_api.py).
"""

import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api import dependencies as deps

pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures & Helpers
# =============================================================================


@pytest.fixture
def mock_user():
    """Mock-User (aktiv, Superuser fuer Admin-Endpunkte)."""
    user = Mock()
    user.id = uuid4()
    user.email = "admin@test.de"
    user.username = "admin"
    user.full_name = "Admin Test"
    user.is_active = True
    user.is_superuser = True
    user.role = "admin"
    return user


@pytest.fixture
def company_id():
    return uuid4()


def _empty_scalars_result():
    """DB-Result-Mock: leere Treffermenge (scalars().all() -> [])."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = 0
    result.all.return_value = []
    return result


@pytest.fixture
def mock_db():
    """AsyncSession-Mock, der per Default keine Treffer liefert."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_empty_scalars_result())
    return db


def _build_app(router, overrides):
    """Mini-App mit Router + Dependency-Overrides (Muster test_search_api)."""
    test_app = FastAPI()
    for dep, value in overrides.items():
        test_app.dependency_overrides[dep] = value
    test_app.include_router(router)
    return test_app


def _client(test_app):
    return AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test")


def _user_overrides(mock_user, mock_db, company_id):
    """Standard-Overrides fuer get_db / User- / Company-Dependencies."""

    async def override_user():
        return mock_user

    async def override_db():
        yield mock_db

    async def override_company():
        return company_id

    return {
        deps.get_current_user: override_user,
        deps.get_current_active_user: override_user,
        deps.get_current_superuser: override_user,
        deps.get_db: override_db,
        deps.get_user_company_id_dep: override_company,
        deps.get_company_id: override_company,
    }


# =============================================================================
# #1 POST /accounting/fx-gain-loss/calculate
# =============================================================================


class TestFXGainLossCalculate:
    """Denormal-Float 5e-324 / Währung "000" -> 422 statt 500."""

    def _app(self, mock_user, mock_db, company_id):
        from app.api.v1.accounting import router

        return _build_app(router, _user_overrides(mock_user, mock_db, company_id))

    @pytest.mark.asyncio
    async def test_denormal_float_rate_returns_422(self, mock_user, mock_db, company_id):
        """Schemathesis-Repro: booking_rate=5e-324 -> 422 (vorher 500)."""
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.post(
                "/accounting/fx-gain-loss/calculate",
                json={
                    "booking_rate": 5e-324,
                    "original_amount": 1.0,
                    "original_currency": "000",
                    "settlement_rate": 5e-324,
                },
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_numeric_currency_returns_422(self, mock_user, mock_db, company_id):
        """Währung "000" ist kein ISO-4217-Alphacode -> 422."""
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.post(
                "/accounting/fx-gain-loss/calculate",
                json={
                    "booking_rate": "1.10",
                    "original_amount": "100.00",
                    "original_currency": "000",
                    "settlement_rate": "1.05",
                },
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_request_returns_200(self, mock_user, mock_db, company_id):
        """Gültige Anfrage rechnet weiterhin korrekt (kein Verhaltensbruch)."""
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.post(
                "/accounting/fx-gain-loss/calculate",
                json={
                    "booking_rate": "1.10",
                    "original_amount": "100.00",
                    "original_currency": "USD",
                    "settlement_rate": "1.05",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["original_currency"] == "USD"
        assert body["gain_loss_account"] in ("2650", "2150")


# =============================================================================
# #2 POST /activity/filter (leerer Body)
# =============================================================================


class TestActivityFilter:
    """Document.created_by_id existiert nicht -> owner_id (vorher 500)."""

    @pytest.mark.asyncio
    async def test_empty_filter_body_returns_200(self, mock_user, mock_db, company_id):
        """Schemathesis-Repro: {} als Body -> 200 mit leerer Timeline."""
        from app.api.v1.activity_timeline import router

        test_app = _build_app(router, _user_overrides(mock_user, mock_db, company_id))
        async with _client(test_app) as client:
            response = await client.post("/activity/filter?per_page=50", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []

    @pytest.mark.asyncio
    async def test_service_uses_owner_id_not_created_by_id(self, mock_db):
        """Service-Query baut ohne AttributeError (owner_id statt created_by_id)."""
        from app.services.activity_timeline_service import ActivityTimelineService

        service = ActivityTimelineService(mock_db)
        activities = await service.get_my_activities(
            user_id=uuid4(), company_id=uuid4(), filters=None
        )
        assert activities == []


# =============================================================================
# #3 POST /admin/integration-sync/datev/writeback
# =============================================================================


class TestDATEVWriteback:
    """Leere Pflichtfelder -> 422 statt 500 (datetime.fromisoformat(""))."""

    @pytest.mark.asyncio
    async def test_empty_required_fields_return_422(self, mock_user, mock_db, company_id):
        """Schemathesis-Repro: leere Strings + betrag=false -> 422."""
        from app.api.v1.admin.integration_sync import router

        test_app = _build_app(router, _user_overrides(mock_user, mock_db, company_id))
        async with _client(test_app) as client:
            response = await client.post(
                "/admin/integration-sync/datev/writeback",
                json={
                    "entries": [
                        {
                            "belegdatum": "",
                            "betrag": False,
                            "buchungstext": "",
                            "document_id": "",
                            "haben_konto": "",
                            "soll_konto": "",
                        }
                    ]
                },
            )
        assert response.status_code == 422

    def test_valid_entry_schema_passes(self):
        """Gültige Buchung validiert weiterhin (kein Verhaltensbruch)."""
        from app.api.v1.admin.integration_sync import DATEVWritebackEntryRequest

        entry = DATEVWritebackEntryRequest(
            document_id=str(uuid4()),
            soll_konto="4400",
            haben_konto="1200",
            betrag=119.0,
            belegdatum="2026-06-01",
            buchungstext="Testbuchung",
        )
        assert entry.belegdatum == date(2026, 6, 1)

    def test_zero_betrag_rejected(self):
        from pydantic import ValidationError

        from app.api.v1.admin.integration_sync import DATEVWritebackEntryRequest

        with pytest.raises(ValidationError):
            DATEVWritebackEntryRequest(
                document_id=str(uuid4()),
                soll_konto="4400",
                haben_konto="1200",
                betrag=0,
                belegdatum="2026-06-01",
                buchungstext="Testbuchung",
            )


# =============================================================================
# #4 POST /admin/jobs/queue/clear?status=AAA
# =============================================================================


class TestJobsQueueClear:
    """Ungültiges Status-Enum -> 422, auch wenn Rate-Limiter nicht verfügbar."""

    def _app(self, mock_user, mock_db, company_id):
        from app.api.v1.admin.jobs import router

        return _build_app(router, _user_overrides(mock_user, mock_db, company_id))

    @pytest.mark.asyncio
    async def test_invalid_status_enum_returns_422(self, mock_user, mock_db, company_id):
        """Schemathesis-Repro: ?status=AAA -> 422 (vorher 503 vor Validierung)."""
        # Rate-Limiter-Storage absichtlich "nicht verfügbar" - die
        # Param-Validierung muss trotzdem zuerst greifen.
        with patch(
            "app.core.rate_limiting.get_redis_storage",
            new=AsyncMock(return_value=None),
        ):
            async with _client(self._app(mock_user, mock_db, company_id)) as client:
                response = await client.post("/jobs/queue/clear?status=AAA")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_status_still_fail_closed_503(self, mock_user, mock_db, company_id):
        """Fail-Closed bleibt: valider Status ohne Rate-Limiter -> 503."""
        with patch(
            "app.core.rate_limiting.get_redis_storage",
            new=AsyncMock(return_value=None),
        ):
            async with _client(self._app(mock_user, mock_db, company_id)) as client:
                response = await client.post("/jobs/queue/clear?status=pending")
        assert response.status_code == 503


# =============================================================================
# #5 POST /admin/rate-limits/bulk/reset
# =============================================================================


class TestRateLimitsBulkReset:
    """Nicht existente UUIDs -> 404 bzw. Teilerfolg statt 500."""

    def _app(self, mock_user, mock_db, company_id):
        from app.api.v1.admin.rate_limits import router

        return _build_app(router, _user_overrides(mock_user, mock_db, company_id))

    @pytest.mark.asyncio
    async def test_unknown_user_ids_return_404(self, mock_user, mock_db, company_id):
        """Schemathesis-Repro: Liste mit nicht existenter UUID -> 404."""
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.post(
                "/rate-limits/bulk/reset",
                json=[str(uuid4())],
            )
        assert response.status_code == 404
        assert "gefunden" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_partial_success_schema(self, mock_user, mock_db, company_id):
        """Mix aus existenten/nicht existenten IDs -> Teilerfolg-Schema."""
        existing_id = uuid4()
        missing_id = uuid4()

        result = MagicMock()
        result.all.return_value = [(existing_id,)]
        mock_db.execute = AsyncMock(return_value=result)

        with patch(
            "app.api.v1.admin.rate_limits.RateLimitService.reset_usage",
            new=AsyncMock(return_value=True),
        ):
            async with _client(self._app(mock_user, mock_db, company_id)) as client:
                response = await client.post(
                    "/rate-limits/bulk/reset",
                    json=[str(existing_id), str(missing_id)],
                )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] == [str(existing_id)]
        assert body["not_found"] == [str(missing_id)]
        assert body["not_found_count"] == 1


# =============================================================================
# #6 POST /admin/roles
# =============================================================================


class TestRoleCreateAudit:
    """AuditLogger.log_async / ROLE_ASSIGNED existieren nicht -> 500 nach
    JEDER erfolgreichen Rollenerstellung. Fix: SecurityAuditLogger.log_event."""

    def _mock_role(self):
        role = Mock()
        role.id = uuid4()
        role.name = "0" * 49
        role.display_name = "00"
        role.description = None
        role.priority = 0
        role.is_system = False
        role.is_active = True
        role.color = "#6B7280"
        role.created_at = datetime.now(UTC)
        role.updated_at = datetime.now(UTC)
        role.permissions = []
        role.users = []
        return role

    @pytest.mark.asyncio
    async def test_create_role_no_attribute_error(self, mock_user, mock_db):
        """Schemathesis-Repro: 49-Zeichen-Name -> 201-Pfad ohne AttributeError."""
        from app.api.v1.admin import roles as roles_module

        mock_role = self._mock_role()
        with patch.object(roles_module, "PermissionService") as svc_cls:
            svc = svc_cls.return_value
            svc.create_role = AsyncMock(return_value=mock_role)
            svc.get_role_by_id = AsyncMock(return_value=mock_role)

            request = roles_module.RoleCreateRequest(
                name="0" * 49, display_name="00"
            )
            result = await roles_module.create_role(
                request=request, current_user=mock_user, db=mock_db
            )

        assert result.name == "0" * 49

    def test_module_uses_existing_audit_api(self):
        """Die genutzten Audit-Symbole existieren wirklich (Regression)."""
        import inspect

        from app.api.v1.admin import roles as roles_module
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        source = inspect.getsource(roles_module)
        assert ".log_async(" not in source
        assert hasattr(SecurityAuditLogger, "log_event")
        assert hasattr(SecurityEventType, "ROLE_CHANGED")


# =============================================================================
# #7 POST /admin/system/gpu/clear-cache
# =============================================================================


class TestGPUClearCache:
    """Service liefert bool; .get() darauf -> AttributeError (500)."""

    @pytest.mark.asyncio
    async def test_no_gpu_returns_503(self, mock_user):
        """Schemathesis-Repro: ohne GPU-Kontext -> 503 statt 500."""
        from app.api.v1.admin.system import clear_gpu_cache

        with patch(
            "app.api.v1.admin.system.SystemStatusService.clear_gpu_cache",
            new=AsyncMock(return_value=False),
        ), pytest.raises(HTTPException) as exc_info:
            await clear_gpu_cache(admin=mock_user)
        assert exc_info.value.status_code == 503
        assert "GPU" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_gpu_available_returns_message(self, mock_user):
        from app.api.v1.admin.system import clear_gpu_cache

        with patch(
            "app.api.v1.admin.system.SystemStatusService.clear_gpu_cache",
            new=AsyncMock(return_value=True),
        ):
            result = await clear_gpu_cache(admin=mock_user)
        assert result.message == "GPU-Cache wurde geleert"


# =============================================================================
# #8 POST /ai/contracts/analyze
# =============================================================================


class TestContractAnalyze:
    """Minimal-Text "00" -> 422 statt Durchreichen an Ollama (503)."""

    @pytest.mark.asyncio
    async def test_minimal_text_returns_422(self, mock_user, mock_db, company_id):
        """Schemathesis-Repro: text="00" -> 422."""
        from app.api.v1 import ai as ai_module

        overrides = _user_overrides(mock_user, mock_db, company_id)
        overrides[ai_module.get_service] = lambda: Mock()
        test_app = _build_app(ai_module.router, overrides)

        async with _client(test_app) as client:
            response = await client.post(
                "/ai/contracts/analyze", json={"text": "00"}
            )
        assert response.status_code == 422

    def test_schema_rejects_short_text(self):
        from pydantic import ValidationError

        from app.api.v1.ai import ContractAnalysisRequest

        with pytest.raises(ValidationError):
            ContractAnalysisRequest(text="00")

        # Realistischer Vertragstext bleibt gültig
        valid = ContractAnalysisRequest(text="Mietvertrag vom 01.01.2026 ...")
        assert valid.text.startswith("Mietvertrag")


# =============================================================================
# #9 POST /cashflow-prediction/scenario
# =============================================================================


class TestCashflowScenario:
    """Fremde/nicht existente IDs -> 404 (kein Tenant-Existenz-Oracle)."""

    def _app(self, mock_user, mock_db, company_id):
        from app.api.v1.cashflow_prediction import router

        return _build_app(router, _user_overrides(mock_user, mock_db, company_id))

    @pytest.mark.asyncio
    async def test_unknown_entity_returns_404(self, mock_user, mock_db, company_id):
        """Schemathesis-Repro: nicht existente entity_id -> 404 (Deutsch)."""
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.post(
                "/cashflow-prediction/scenario",
                json={
                    "scenario_type": "customer_late_payment",
                    "parameters": {
                        "entity_id": "123e4567-e89b-12d3-a456-426614174000",
                        "delay_days": 14,
                    },
                },
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "Geschäftspartner nicht gefunden"

    @pytest.mark.asyncio
    async def test_unknown_invoice_returns_404(self, mock_user, mock_db, company_id):
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.post(
                "/cashflow-prediction/scenario",
                json={
                    "scenario_type": "delay_outgoing",
                    "parameters": {"invoice_id": str(uuid4()), "delay_days": 7},
                },
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "Rechnung nicht gefunden"

    @pytest.mark.asyncio
    async def test_late_payment_confidence_no_type_error(self):
        """float * Decimal warf TypeError, sobald Forderungen existierten."""
        from app.services.ai.cashflow_prediction_service import (
            CashflowForecast,
            CashflowPredictionService,
        )

        entity_id = uuid4()
        company = uuid4()
        due = date.today() + timedelta(days=5)

        service = CashflowPredictionService(AsyncMock())
        receivables = [
            {
                "amount": Decimal("100.00"),
                "due_date": due,
                "entity_id": entity_id,
                "invoice_id": uuid4(),
                "delay_stats": None,
                "dunning_level": 0,
            }
        ]
        base_forecasts = [
            CashflowForecast(
                date=due,
                predicted_balance=Decimal("1000.00"),
                lower_bound=Decimal("900.00"),
                upper_bound=Decimal("1100.00"),
                incoming=Decimal("100.00"),
                outgoing=Decimal("0.00"),
                confidence=0.8,
            )
        ]

        with patch.object(
            service, "_get_open_receivables", new=AsyncMock(return_value=receivables)
        ):
            result = await service._simulate_customer_late_payment(
                company, base_forecasts, {"entity_id": entity_id, "delay_days": 14}
            )

        assert result.new_forecasts, "Simulation muss Forecasts liefern"
        assert result.new_forecasts[0].confidence == pytest.approx(0.72)


# =============================================================================
# #10 POST /lifecycle/destruction-protocols
# =============================================================================


class TestDestructionProtocols:
    """Nicht existente Dokumente -> 404 statt generischem 500."""

    @pytest.mark.asyncio
    async def test_unknown_documents_return_404(self, mock_user, mock_db, company_id):
        """Schemathesis-Repro: fremde/nicht existente document_ids -> 404."""
        from app.api.v1.lifecycle_engine import router

        test_app = _build_app(router, _user_overrides(mock_user, mock_db, company_id))
        async with _client(test_app) as client:
            response = await client.post(
                "/lifecycle/destruction-protocols",
                json={
                    "document_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                    "reason": "Aufbewahrungsfrist abgelaufen gemaess Paragraf 147 AO",
                },
            )
        assert response.status_code == 404
        assert "nicht gefunden" in response.json()["detail"]

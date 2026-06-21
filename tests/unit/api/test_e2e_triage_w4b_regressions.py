"""Regressionstests fuer die E2E-Triage-Bugs B2/B3/B4/B12/B6 (W4b, 2026-06-12).

 B2  Banking-Routen riefen company_id-Services mit user_id= auf -> TypeError/500
     (36 Call-Sites: account/import/transaction/reconciliation/mahn_task/
      dunning_stage). payment_service + aging_report_service erwarten weiterhin
      user_id und wurden bewusst NICHT umgestellt.
 B3  websocket.py nutzte settings.JWT_ALGORITHM (existiert nicht) -> 500 beim
     WS-Handshake. Kanonisch ist settings.ALGORITHM.
 B4  RATE_LIMIT_ENABLED=false wurde wie Redis-Ausfall behandelt -> 503 auf
     Upload/Suche. Disabled => No-Op; Fail-Closed bei enabled+Ausfall BLEIBT.
 B12 /workflows/stats/*: lokaler Integer-Import shadowte Modulimport
     (UnboundLocalError) + WorkflowExecution.user_id existiert nicht
     (AttributeError). Scope jetzt ueber Workflow-Ownership-Subquery.
 B6  app/api/v1/rag/-Package shadowte app/api/v1/rag.py -> dessen Routen
     (/rag/ai/*, /rag/bi/*, /rag/customer-cards, /rag/models, /rag/health)
     waren nie registriert (Frontend-Dauer-404). Jetzt rag/legacy.py.

Muster: Mini-FastAPI-App + dependency_overrides
(wie tests/unit/api/test_schemathesis_5xx_regressions.py).
"""

import inspect
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import jwt as pyjwt
import pytest

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api import dependencies as deps
from app.core.config import settings

pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures & Helpers
# =============================================================================


@pytest.fixture
def mock_user():
    user = Mock()
    user.id = uuid4()
    user.email = "admin@test.de"
    user.username = "admin"
    user.is_active = True
    user.is_superuser = True
    user.role = "admin"
    return user


@pytest.fixture
def company_id():
    return uuid4()


def _empty_scalars_result():
    """DB-Result-Mock: leere Treffermenge."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = 0
    result.all.return_value = []
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_empty_scalars_result())
    return db


def _build_app(router, overrides):
    test_app = FastAPI()
    for dep, value in overrides.items():
        test_app.dependency_overrides[dep] = value
    test_app.include_router(router)
    return test_app


def _client(test_app):
    return AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test")


def _user_overrides(mock_user, mock_db, company_id):
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
    }


def _extract_call_block(source: str, needle: str) -> list:
    """Liefert die Argument-Bloecke aller `await <needle>(`-Aufrufe."""
    blocks = []
    start = 0
    token = "await " + needle + "("
    while True:
        i = source.find(token, start)
        if i == -1:
            break
        open_paren = source.index("(", i + len(token) - 1)
        depth, j = 0, open_paren
        while j < len(source):
            if source[j] == "(":
                depth += 1
            elif source[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        blocks.append(source[open_paren:j])
        start = i + 1
    return blocks


# =============================================================================
# B2: Banking user_id= -> company_id=
# =============================================================================

# Services, deren Methoden company_id erwarten (Signaturen verifiziert).
COMPANY_SCOPED_CALLS = [
    "account_service.create_account",
    "account_service.get_accounts",
    "account_service.get_accounts_with_stats",
    "account_service.get_account",
    "account_service.update_account",
    "account_service.delete_account",
    "import_service.import_file",
    "import_service.get_import_history",
    "transaction_service.get_transactions",
    "transaction_service.get_unmatched_transactions",
    "transaction_service.get_transaction_stats",
    "transaction_service.get_monthly_summary",
    "transaction_service.get_top_counterparties",
    "transaction_service.get_transaction",
    "transaction_service.update_transaction",
    "transaction_service.set_reconciliation_status",
    "reconciliation_service.find_matches",
    "reconciliation_service.manual_match",
    "reconciliation_service.unmatch_transaction",
    "reconciliation_service.split_transaction",
    "reconciliation_service.batch_reconcile",
    "reconciliation_service.auto_reconcile_transaction",
    "mahn_task_service.log_phone_call",
    "mahn_task_service.get_phone_call_history",
    "mahn_task_service.list_tasks",
    "mahn_task_service.get_pending_tasks_summary",
    "mahn_task_service.assign_task",
    "mahn_task_service.snooze_task",
    "mahn_task_service.complete_task",
    # dunning_stage_service write-Pfade passieren company_id=company_id; die
    # read-Pfade get_stages/get_auto_dunning_settings sind USER-scoped (F-31,
    # Commit 8dce67679) und stehen in DUNNING_USER_VALUE_CALLS.
    "dunning_stage_service.create_stage",
    "dunning_stage_service.update_stage",
    "dunning_stage_service.reorder_stages",
    "dunning_stage_service.update_auto_dunning_settings",
    # PaymentService wurde auf company-scope migriert (Service-Signaturen
    # erwarten company_id=, Route passiert company_id=company_id).
    "payment_service.list_payments",
    "payment_service.get_pending_payments",
]

# Services, deren Call-Sites weiterhin user_id=current_user.id passieren
# (kein Overshoot!). aging_report_service erwartet weiterhin user_id.
USER_SCOPED_CALLS = [
    "aging_report_service.get_receivables_aging",
    "aging_report_service.calculate_dso",
]

# F-31 (Commit 8dce67679): DunningStageConfig hat eine user_id-Spalte und KEINE
# company_id-Spalte; der Service filtert intern DunningStageConfig.user_id ==
# <param> (Parameter heisst missverstaendlich company_id). Die read-Pfade
# passieren daher absichtlich company_id=current_user.id (User-Wert).
DUNNING_USER_VALUE_CALLS = [
    "dunning_stage_service.get_stages",
    "dunning_stage_service.get_auto_dunning_settings",
]


class TestB2BankingCompanyScope:
    """E2E-Repro: GET /banking/accounts -> 500 TypeError get_accounts() got
    an unexpected keyword argument 'user_id'."""

    def _app(self, mock_user, mock_db, company_id):
        from app.api.v1.banking.routes import router

        return _build_app(router, _user_overrides(mock_user, mock_db, company_id))

    @pytest.mark.asyncio
    async def test_list_accounts_returns_200(self, mock_user, mock_db, company_id):
        """B2-Kernrepro: GET /banking/accounts -> 200 (vorher 500)."""
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.get("/banking/accounts")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_accounts_with_stats_returns_200(self, mock_user, mock_db, company_id):
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.get("/banking/accounts/with-stats")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_transactions_returns_200(self, mock_user, mock_db, company_id):
        """B2-Live-Repro #2: GET /banking/transactions -> 200 (vorher 500)."""
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.get("/banking/transactions")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["items"] == []

    @pytest.mark.asyncio
    async def test_import_history_returns_200(self, mock_user, mock_db, company_id):
        async with _client(self._app(mock_user, mock_db, company_id)) as client:
            response = await client.get("/banking/import/history")
        assert response.status_code == 200
        assert response.json() == []

    def test_all_company_scoped_calls_pass_company_id(self):
        """Statisches Netz: KEIN company-scoped Service-Call passiert mehr
        user_id=; alle passieren company_id=company_id (36 Call-Sites)."""
        from app.api.v1 import banking

        source = inspect.getsource(banking.routes)
        total_calls = 0
        for target in COMPANY_SCOPED_CALLS:
            blocks = _extract_call_block(source, target)
            assert blocks, f"Call-Site fuer {target} nicht gefunden"
            for block in blocks:
                total_calls += 1
                # \b-Grenze: assigned_user_id= (legitimer Parameter) darf bleiben
                assert not re.search(r"(?<![\w])user_id=", block), (
                    f"{target} passiert noch user_id= (Service erwartet company_id)"
                )
                assert "company_id=company_id" in block, (
                    f"{target} passiert kein company_id=company_id"
                )
        assert total_calls == 36

    def test_user_scoped_services_untouched(self):
        """Kein Overshoot: aging_report_service erwartet weiterhin user_id -
        seine Call-Sites passieren weiterhin user_id=current_user.id."""
        from app.api.v1 import banking

        source = inspect.getsource(banking.routes)
        for target in USER_SCOPED_CALLS:
            blocks = _extract_call_block(source, target)
            assert blocks, f"Call-Site fuer {target} nicht gefunden"
            for block in blocks:
                assert "user_id=current_user.id" in block, (
                    f"{target} passiert kein user_id mehr (Service erwartet es!)"
                )

    def test_dunning_read_paths_pass_user_value(self):
        """F-31: DunningStageConfig ist user-scoped (user_id-Spalte, KEINE
        company_id-Spalte). Die read-Pfade passieren company_id=current_user.id
        (User-Wert), NICHT company_id=company_id."""
        from app.api.v1 import banking

        source = inspect.getsource(banking.routes)
        for target in DUNNING_USER_VALUE_CALLS:
            blocks = _extract_call_block(source, target)
            assert blocks, f"Call-Site fuer {target} nicht gefunden"
            for block in blocks:
                assert "company_id=current_user.id" in block, (
                    f"{target} passiert nicht company_id=current_user.id "
                    "(DunningStageConfig ist user-scoped, F-31)"
                )


# =============================================================================
# B3: WebSocket JWT-Algorithmus
# =============================================================================


class TestB3WebsocketJWT:
    """settings.JWT_ALGORITHM existiert nicht -> AttributeError beim
    WS-Handshake. Kanonische Quelle: settings.ALGORITHM."""

    @staticmethod
    def _secret() -> str:
        key = settings.SECRET_KEY
        return key.get_secret_value() if hasattr(key, "get_secret_value") else key

    def _token(self, user_id: str, **extra) -> str:
        return pyjwt.encode(
            {"sub": user_id, "email": "a@b.de", "company_id": None, **extra},
            self._secret(),
            algorithm=settings.ALGORITHM,
        )

    @pytest.mark.asyncio
    async def test_valid_token_decodes(self):
        """Token-Decode-Pfad laeuft ohne AttributeError/TypeError durch.

        Deckt BEIDE Handshake-Bugs ab: das nicht existente Algorithmus-
        Attribut UND SecretStr-als-Key (PyJWT braucht str)."""
        from app.api.v1.websocket import get_user_from_token

        user_id = str(uuid4())
        user = await get_user_from_token(self._token(user_id))
        assert user is not None
        assert user["id"] == user_id

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        from app.api.v1.websocket import get_user_from_token

        assert await get_user_from_token("kein-jwt") is None

    @pytest.mark.asyncio
    async def test_chat_ws_authenticate_decodes_token(self, mock_user):
        """Zusatzbefund: rag/chat_ws hatte denselben SecretStr-Bug."""
        import datetime as dt

        from app.api.v1.rag import chat_ws as chat_ws_module

        token = pyjwt.encode(
            {
                "sub": str(mock_user.id),
                "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5),
            },
            self._secret(),
            algorithm=settings.ALGORITHM,
        )

        session_ctx = AsyncMock()
        db = AsyncMock()
        db.get = AsyncMock(return_value=mock_user)
        session_ctx.__aenter__.return_value = db
        with patch.object(
            chat_ws_module, "get_async_session_context", return_value=session_ctx
        ):
            user, error = await chat_ws_module.authenticate_websocket(token)
        assert error is None
        assert user is mock_user

    def test_canonical_algorithm_source_used(self):
        """Regression: Decode nutzt settings.ALGORITHM; das frueher genutzte
        Phantom-Attribut existiert nicht in Settings."""
        from app.api.v1 import websocket as ws_module

        source = inspect.getsource(ws_module)
        assert "algorithms=[settings.ALGORITHM]" in source
        assert "JWT_ALGORITHM" not in source
        assert hasattr(settings, "ALGORITHM")
        assert not hasattr(settings, "JWT_ALGORITHM")


# =============================================================================
# B4: Rate-Limiting disabled vs. Redis-Ausfall
# =============================================================================


def _request_mock():
    """Request-Mock mit nicht-whitelisteter Public-IP (TEST-NET-3)."""
    request = Mock()
    request.client = Mock(host="203.0.113.10")
    request.headers = {}
    return request


class TestB4RateLimitDisabledVsOutage:
    """ENABLED=false => sauberer No-Op; Fail-Closed bei Ausfall BLEIBT."""

    @pytest.mark.asyncio
    async def test_disabled_check_rate_limit_passes(self, mock_user, monkeypatch):
        """E2E-Repro: ENABLED=false fuehrte zu 503 auf Upload/Suche."""
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        result = await deps.check_rate_limit(_request_mock(), mock_user)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_disabled_ocr_rate_limit_passes(self, mock_user, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        result = await deps.check_ocr_rate_limit(_request_mock(), mock_user)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_disabled_batch_rate_limit_passes(self, mock_user, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        result = await deps.check_batch_rate_limit(_request_mock(), mock_user)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_disabled_destructive_admin_passes(self, mock_user, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        result = await deps.check_destructive_admin_rate_limit(_request_mock(), mock_user)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_disabled_rate_limit_dependency_passes(self, mock_user, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        dep = deps.RateLimitDependency(requests_per_hour=1, key_prefix="w4b_test")
        result = await dep(_request_mock(), mock_user)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_enabled_storage_down_stays_fail_closed_503(self, mock_user, monkeypatch):
        """SECURITY: Redis-Ausfall bei AKTIVIERTEM Limiter -> 503 (unveraendert!)."""
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
        with patch(
            "app.core.rate_limiting.get_redis_storage",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await deps.check_rate_limit(_request_mock(), mock_user)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_enabled_storage_unavailable_stays_fail_closed_503(
        self, mock_user, monkeypatch
    ):
        """Auch storage.is_available=False (Connect-Fehler) -> 503."""
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
        storage = Mock()
        storage.is_available = False
        with patch(
            "app.core.rate_limiting.get_redis_storage",
            new=AsyncMock(return_value=storage),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await deps.check_rate_limit(_request_mock(), mock_user)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_enabled_storage_up_within_limit_passes(self, mock_user, monkeypatch):
        """Sanity: aktivierter Limiter mit verfuegbarem Redis laesst durch."""
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
        storage = Mock()
        storage.is_available = True
        storage.increment = AsyncMock(return_value=1)
        with patch(
            "app.core.rate_limiting.get_redis_storage",
            new=AsyncMock(return_value=storage),
        ):
            result = await deps.check_rate_limit(_request_mock(), mock_user)
        assert result is mock_user


# =============================================================================
# B12: Workflows-Statistik
# =============================================================================


class TestB12WorkflowStats:
    """UnboundLocalError (Integer-Shadow) + WorkflowExecution.user_id."""

    def _app(self, mock_user, mock_db, company_id):
        from app.api.v1.workflows import router

        return _build_app(router, _user_overrides(mock_user, mock_db, company_id))

    @pytest.fixture
    def stats_db(self):
        """DB-Mock fuer Aggregat-Queries (.one() liefert Null-Zeile)."""
        row = Mock(total=0, active=0, today=0, completed=0)
        result = MagicMock()
        result.one.return_value = row
        result.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        return db

    @pytest.mark.asyncio
    async def test_stats_overview_returns_200(self, mock_user, stats_db, company_id):
        """E2E-Repro: UnboundLocalError 'Integer' -> 500. Jetzt 200."""
        async with _client(self._app(mock_user, stats_db, company_id)) as client:
            response = await client.get("/workflows/stats/overview")
        assert response.status_code == 200
        body = response.json()
        assert body["total_workflows"] == 0
        assert body["total_executions"] == 0

    @pytest.mark.asyncio
    async def test_execution_history_returns_200(self, mock_user, stats_db, company_id):
        """E2E-Repro: WorkflowExecution.user_id (AttributeError) -> 500. Jetzt 200."""
        async with _client(self._app(mock_user, stats_db, company_id)) as client:
            response = await client.get("/workflows/stats/execution-history?days=30")
        assert response.status_code == 200
        assert response.json() == []

    def test_no_phantom_user_id_reference(self):
        """Regression: WorkflowExecution hat kein user_id; Modul darf es
        nicht referenzieren und keinen lokalen Integer-Import mehr haben."""
        from app.api.v1 import workflows as wf_module
        from app.db.models_workflow import WorkflowExecution

        assert not hasattr(WorkflowExecution, "user_id")
        source = inspect.getsource(wf_module)
        assert "WorkflowExecution.user_id" not in source
        # Der Bug war ein lokaler Integer-Import NACH der Nutzung in
        # get_overview_stats (shadowte den Modulimport -> UnboundLocalError).
        overview_source = inspect.getsource(wf_module.get_overview_stats)
        assert "from sqlalchemy import Integer" not in overview_source


# =============================================================================
# B6: rag-Modul-Shadowing
# =============================================================================

LEGACY_RAG_PATHS = [
    ("GET", "/rag/ai/context"),
    ("GET", "/rag/ai/actions"),
    ("POST", "/rag/ai/actions/execute"),
    ("POST", "/rag/ai/actions/confirm"),
    ("POST", "/rag/bi/query"),
    ("POST", "/rag/bi/invoices"),
    ("POST", "/rag/bi/trends"),
    ("POST", "/rag/bi/chat"),
    ("GET", "/rag/bi/entity/{entity_id}"),
    ("GET", "/rag/bi/entity/search/{name}"),
    ("GET", "/rag/bi/payment-prediction/{entity_id}"),
    ("GET", "/rag/customer-cards"),
    ("GET", "/rag/customer-cards/{customer_id}"),
    ("POST", "/rag/customer-cards/{customer_id}/refresh"),
    ("GET", "/rag/models"),
    ("GET", "/rag/health"),
]


class TestB6RagShadowing:
    """Package shadowte rag.py -> /rag/ai/* etc. waren NIE registriert."""

    def _route_set(self):
        from app.api.v1.rag import router

        pairs = set()
        for route in router.routes:
            methods = getattr(route, "methods", None) or set()
            for m in methods:
                pairs.add((m, route.path))
        return pairs

    def test_legacy_routes_registered(self):
        """Alle frueher geshadowten Routen sind jetzt im Package-Router."""
        registered = self._route_set()
        for method, path in LEGACY_RAG_PATHS:
            assert (method, path) in registered, f"{method} {path} fehlt"

    def test_legacy_routes_unique(self):
        """Keine Pfad-Kollisionen der Legacy-Routen im Package."""
        from app.api.v1.rag import router

        counted = {}
        for route in router.routes:
            for m in getattr(route, "methods", None) or set():
                key = (m, route.path)
                counted[key] = counted.get(key, 0) + 1
        for key in LEGACY_RAG_PATHS:
            assert counted.get(key) == 1, f"Kollision/Fehlen: {key}"

    def test_shadowed_module_removed(self):
        """app/api/v1/rag.py existiert nicht mehr (Shadowing-Quelle weg)."""
        import app.api.v1 as v1_pkg

        v1_dir = Path(v1_pkg.__file__).parent
        assert not (v1_dir / "rag.py").exists()
        # app.api.v1.rag ist (und bleibt) das Package
        import app.api.v1.rag as rag_pkg

        assert hasattr(rag_pkg, "__path__")

    @pytest.mark.asyncio
    async def test_rag_models_endpoint_works(self, mock_user, mock_db, company_id):
        """Funktional: GET /rag/models -> 200 (vorher 404)."""
        from app.api.v1.rag import router
        from app.db.session import get_async_session

        overrides = _user_overrides(mock_user, mock_db, company_id)

        async def override_session():
            yield mock_db

        overrides[get_async_session] = override_session
        test_app = _build_app(router, overrides)
        async with _client(test_app) as client:
            response = await client.get("/rag/models")
        assert response.status_code == 200
        assert response.json() == []

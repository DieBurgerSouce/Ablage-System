"""Sweep-Regressionstests: InvoiceTracking-Spalten-Drift in restlichen Services.

Hintergrund (Manifest w3-backend, Befund 2, 2026-06-12): ``InvoiceTracking``
hat KEINE Spalten ``invoice_type``/``total_amount``/``business_entity_id``
(und ebenso wenig ``is_paid``/``paid_date``/``is_incoming``/``is_outgoing``/
``gross_amount``/``amount_total``/``days_until_payment``). Alle betroffenen
Query-Pfade liefen zur Laufzeit in ``AttributeError`` (HTTP 500).

Diese Tests rufen pro Service den umgestellten Query-Pfad mit gemockter
Session auf und pruefen das kompilierte SQL: Richtung via Entity-JOIN
(customer -> outgoing, supplier -> incoming, Helper
``app/services/invoice_direction.py``), Betrag via ``amount``,
Entity-Verknuepfung via ``entity_id``, Zahlstatus via ``status``/``paid_at``.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import List, Optional, Sequence, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio

_PHANTOM_SPALTEN = (
    "invoice_type",
    "total_amount",
    "business_entity_id",
    "is_paid",
    "paid_date",
    "is_incoming",
    "is_outgoing",
    "gross_amount",
    "amount_total",
    "days_until_payment",
)


# ============================================================================
# Test-Doubles
# ============================================================================


class _FakeScalars:
    def __init__(self, items: Sequence[object]) -> None:
        self._items = list(items)

    def all(self) -> List[object]:
        return self._items

    def first(self) -> Optional[object]:
        return self._items[0] if self._items else None


class _FakeResult:
    """Minimaler Ersatz fuer ein SQLAlchemy-Result."""

    def __init__(
        self,
        scalars: Optional[Sequence[object]] = None,
        one: Optional[object] = None,
        scalar: Optional[object] = None,
        rows: Optional[Sequence[object]] = None,
    ) -> None:
        self._scalars = scalars or []
        self._one = one
        self._scalar = scalar
        self._rows = rows or []

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._scalars)

    def one(self) -> Optional[object]:
        return self._one

    def one_or_none(self) -> Optional[object]:
        return self._one

    def first(self) -> Optional[object]:
        return self._one

    def scalar(self) -> Optional[object]:
        return self._scalar

    def scalar_one_or_none(self) -> Optional[object]:
        return self._scalar

    def all(self) -> List[object]:
        return list(self._rows)

    def fetchall(self) -> List[object]:
        return list(self._rows)


def _make_db(
    results: Optional[Sequence[_FakeResult]] = None,
    repeat: Optional[_FakeResult] = None,
) -> Tuple[MagicMock, List[object]]:
    """Gemockte AsyncSession, die ausgefuehrte Statements mitschreibt."""
    captured: List[object] = []
    queue = list(results or [])

    async def _execute(stmt: object, *args: object, **kwargs: object) -> _FakeResult:
        captured.append(stmt)
        if queue:
            return queue.pop(0)
        if repeat is not None:
            return repeat
        raise AssertionError("Unerwartete zusaetzliche Query")

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    return db, captured


def _compiled(stmt: object) -> Tuple[str, List[object]]:
    """Kompiliert ein Statement und liefert (SQL-Text, Parameterwerte)."""
    compiled = stmt.compile()
    return str(compiled), list(compiled.params.values())


def _assert_keine_phantom_spalten(sql: str) -> None:
    for spalte in _PHANTOM_SPALTEN:
        # Labels wie "AS total_amount" sind erlaubt — nur echte
        # Spaltenreferenzen "invoice_tracking.<spalte>" sind der Bug.
        assert f"invoice_tracking.{spalte}" not in sql, spalte


# ============================================================================
# (1) PaymentAutomationService — Eingangsrechnungen via Supplier-Join
# ============================================================================


async def test_payment_automation_suggestions_nutzt_supplier_join() -> None:
    from app.services.banking.payment_automation_service import (
        PaymentAutomationService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = PaymentAutomationService()

    result = await service.generate_payment_suggestions(db, uuid.uuid4())

    assert result == []
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "business_entities" in sql
    assert "supplier" in params
    assert "invoice_tracking.status" in sql  # offen = Status-Allowlist


# ============================================================================
# (2) HoldingKPIService — Forderungen/Verbindlichkeiten konsolidiert
# ============================================================================


async def test_holding_kpi_financials_nutzt_entity_richtung() -> None:
    from app.services.holding.holding_kpi_service import HoldingKPIService

    db, captured = _make_db(repeat=_FakeResult(scalar=None))
    service = HoldingKPIService(db)

    financials = await service._get_consolidated_financials([uuid.uuid4()])

    assert financials["total_receivables"] == 0.0
    assert len(captured) == 4
    sql_recv, params_recv = _compiled(captured[0])
    sql_pay, params_pay = _compiled(captured[1])
    for sql in (sql_recv, sql_pay):
        _assert_keine_phantom_spalten(sql)
    assert "customer" in params_recv
    assert "supplier" in params_pay


# ============================================================================
# (3) PredictiveCashFlowService (finanzki) — erwartete Eingaenge
# ============================================================================


async def test_finanzki_cashflow_inflows_nutzt_customer_join() -> None:
    from app.services.finanzki.predictive_cashflow_service import (
        PredictiveCashFlowService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = PredictiveCashFlowService(db)

    inflows = await service._get_expected_inflows(uuid.uuid4(), days=30)

    assert inflows == []
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "business_entities" in sql
    assert "customer" in params


# ============================================================================
# (4) DigitalTwinService — Richtung war VERTAUSCHT (Forderung != incoming)
# ============================================================================


async def test_digital_twin_receivables_payables_richtung_korrigiert() -> None:
    from app.services.digital_twin_service import DigitalTwinService

    db, captured = _make_db(repeat=_FakeResult(scalar=0))
    service = DigitalTwinService(db)

    section = await service._get_financial_health_section(uuid.uuid4())

    assert section is not None
    # captured[1] = Forderungen, captured[2] = Verbindlichkeiten
    sql_recv, params_recv = _compiled(captured[1])
    sql_pay, params_pay = _compiled(captured[2])
    for sql in (sql_recv, sql_pay):
        _assert_keine_phantom_spalten(sql)
    assert "customer" in params_recv  # Forderung = Ausgangsrechnung (Kunde)
    assert "supplier" in params_pay  # Verbindlichkeit = Eingangsrechnung


# ============================================================================
# (5) CashflowPredictorService (predictive) — Forderungen mit Probabilities
# ============================================================================


async def test_cashflow_predictor_receivables_nutzt_customer_join() -> None:
    from app.services.predictive.cashflow_predictor_service import (
        CashflowPredictorService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = CashflowPredictorService(db)

    receivables = await service._get_receivables_with_probabilities(
        uuid.uuid4(), days=30
    )

    assert receivables == []
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "customer" in params


# ============================================================================
# (6) SkontoOptimizer — Richtungs-KOMMENTARE waren vertauscht
# ============================================================================


async def test_skonto_optimizer_inflows_sind_ausgangsrechnungen() -> None:
    from app.services.insights.skonto_optimizer import SkontoOptimizer

    db, captured = _make_db([_FakeResult(scalars=[])])
    optimizer = SkontoOptimizer()

    inflows = await optimizer._get_expected_inflows(db, uuid.uuid4(), 30)

    assert inflows == {}
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    # Forderung (Zahlungseingang) = Kunde, NICHT "incoming"
    assert "customer" in params
    # Phantom-Status "pending" raus, echte Status-Allowlist rein
    assert "pending" not in params


async def test_skonto_optimizer_outflows_sind_eingangsrechnungen() -> None:
    from app.services.insights.skonto_optimizer import SkontoOptimizer

    db, captured = _make_db([_FakeResult(scalars=[])])
    optimizer = SkontoOptimizer()

    outflows = await optimizer._get_expected_outflows(db, uuid.uuid4(), 30)

    assert outflows == {}
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "supplier" in params
    assert "pending" not in params


# ============================================================================
# (7) IndustryBenchmarkService — Rechnungsstatistiken via amount
# ============================================================================


async def test_industry_benchmark_metrics_nutzt_amount() -> None:
    from app.services.analytics.industry_benchmark_service import (
        IndustryBenchmarkService,
    )

    row = SimpleNamespace(
        total=0,
        paid=0,
        dunned=0,
        cancelled=0,
        skonto_used=0,
        total_amount=None,
        outstanding=None,
    )
    db, captured = _make_db([
        _FakeResult(one=row),
        _FakeResult(scalar=0),
        _FakeResult(scalar=None),
    ])
    service = IndustryBenchmarkService(db)

    metrics = await service._calculate_company_metrics(uuid.uuid4(), 365)

    assert metrics["punctuality_rate"] == 0.0
    sql, _ = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.amount" in sql


# ============================================================================
# (8) TrendAnalyzer (CEO-Dashboard) — Tagesumsaetze via amount
# ============================================================================


async def test_trend_analyzer_invoices_nutzt_amount() -> None:
    from app.services.ceo_dashboard.trend_analyzer import TrendAnalyzer

    db, captured = _make_db([_FakeResult(scalar=0)])
    analyzer = TrendAnalyzer()
    start = datetime.now(timezone.utc) - timedelta(days=1)

    points = await analyzer._analyze_invoices(
        uuid.uuid4(), start, start + timedelta(days=1), 1, db
    )

    assert len(points) == 1
    sql, _ = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.amount" in sql


# ============================================================================
# (9) CompanyMetricsService — Aggregationen via amount
# ============================================================================


async def test_company_metrics_invoices_nutzt_amount() -> None:
    from app.services.company_metrics_service import CompanyMetricsService

    db, captured = _make_db([
        _FakeResult(one=(0, None, None, None)),
        _FakeResult(one=(0, None)),
        _FakeResult(scalar=None),
    ])
    service = CompanyMetricsService()

    metrics = await service._get_invoice_metrics(db, uuid.uuid4())

    assert metrics.total_invoices == 0
    sql, _ = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.amount" in sql


# ============================================================================
# (10) CustomerLTVService — Umsatz = Ausgangsrechnungen (Phantom is_incoming)
# ============================================================================


async def test_customer_ltv_metrics_nutzt_customer_join() -> None:
    from app.services.dashboard.customer_ltv_service import CustomerLTVService

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = CustomerLTVService()
    customer = SimpleNamespace(id=uuid.uuid4(), name="Testkunde")

    metrics = await service._calculate_customer_metrics(
        db, customer, date.today() - timedelta(days=365), date.today(), None
    )

    assert metrics.entity_name == "Testkunde"
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "customer" in params


# ============================================================================
# (11) SupplierPerformanceService — Eingangsrechnungen (Phantom is_incoming)
# ============================================================================


async def test_supplier_performance_metrics_nutzt_supplier_join() -> None:
    from app.services.dashboard.supplier_performance_service import (
        SupplierPerformanceService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = SupplierPerformanceService()
    supplier = SimpleNamespace(id=uuid.uuid4(), name="Testlieferant")

    metrics = await service._calculate_supplier_metrics(
        db, supplier, date.today() - timedelta(days=365), None
    )

    assert metrics.entity_name == "Testlieferant"
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "supplier" in params


# ============================================================================
# (12) FraudDetectionService — runde Betraege via amount
# ============================================================================


async def test_fraud_detection_round_amounts_nutzt_amount() -> None:
    from app.services.finanzki.fraud_detection_service import (
        FraudDetectionService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = FraudDetectionService(db)
    now = datetime.now(timezone.utc)

    alerts = await service._detect_round_amounts(
        uuid.uuid4(), now - timedelta(days=90), now
    )

    assert alerts == []
    sql, _ = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.amount" in sql


# ============================================================================
# (13) RiskIntelligenceService — Phantom days_until_payment ersetzt
# ============================================================================


async def test_risk_intelligence_internal_data_berechnet_zahlungsdauer() -> None:
    from app.services.finanzki.risk_intelligence_service import (
        RiskIntelligenceService,
    )

    row = SimpleNamespace(
        total_invoices=0,
        total_volume=None,
        avg_payment_days=None,
        dunning_count=0,
        paid_count=0,
    )
    db, captured = _make_db([_FakeResult(one=row)])
    service = RiskIntelligenceService(db)

    data = await service._analyze_internal_data(uuid.uuid4(), uuid.uuid4())

    assert data["total_invoices"] == 0
    sql, _ = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    # Zahlungsdauer jetzt echt: paid_at - invoice_date
    assert "invoice_tracking.paid_at" in sql
    assert "invoice_tracking.amount" in sql


# ============================================================================
# (14) ProactiveDunningService — entity_id + Status statt Phantomspalten
# ============================================================================


async def test_proactive_dunning_overdue_nutzt_status_und_richtung() -> None:
    from app.services.banking.proactive_dunning_service import (
        ProactiveDunningService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = ProactiveDunningService(db)

    invoices = await service._get_overdue_invoices(uuid.uuid4())

    assert invoices == []
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "customer" in params  # Mahnwesen = Forderungen = Ausgangsrechnung
    assert "invoice_tracking.status" in sql


async def test_proactive_dunning_history_nutzt_entity_id() -> None:
    from app.services.banking.proactive_dunning_service import (
        ProactiveDunningService,
    )

    db, captured = _make_db([
        _FakeResult(scalars=[]),  # _get_entity
        _FakeResult(scalars=[]),  # Rechnungen
    ])
    service = ProactiveDunningService(db)

    history = await service._get_payment_history(uuid.uuid4())

    assert history.total_invoices == 0
    sql, _ = _compiled(captured[1])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.entity_id" in sql


# ============================================================================
# (15) DocumentPipelineOrchestrator — entity_id + amount im Anomalie-Check
# ============================================================================


async def test_pipeline_amount_anomaly_nutzt_entity_id_und_amount() -> None:
    from app.services.pipeline.document_pipeline_orchestrator import (
        DocumentPipelineOrchestrator,
    )

    db, captured = _make_db([_FakeResult(rows=[])])
    orchestrator = DocumentPipelineOrchestrator(db)

    result = await orchestrator._check_amount_anomaly(
        "Gesamt: 1.234,56 EUR", uuid.uuid4()
    )

    assert result is None  # keine Historie -> keine Anomalie
    assert len(captured) == 1
    sql, _ = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.entity_id" in sql
    assert "invoice_tracking.amount" in sql


# ============================================================================
# (16) PredictiveActionService — Skonto-Aktionen (Eingangsrechnungen)
# ============================================================================


async def test_predictive_action_skonto_nutzt_supplier_join() -> None:
    from app.services.ai.predictive_action_service import (
        PredictiveActionService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = PredictiveActionService()

    actions = await service._generate_skonto_actions(db, uuid.uuid4())

    assert actions == []
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "supplier" in params


# ============================================================================
# (17) FraudFeatureExtractor (ML) — historische Statistiken via amount
# ============================================================================


async def test_fraud_ml_historical_stats_nutzt_amount() -> None:
    from app.services.ai.fraud_ml_model import FraudFeatureExtractor

    db, captured = _make_db([_FakeResult(one=None)])
    extractor = FraudFeatureExtractor(db)

    stats = await extractor._get_historical_stats(uuid.uuid4())

    assert stats == {"mean": 0, "std": 1, "median": 0}
    sql, _ = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.amount" in sql


# ============================================================================
# (18) ActionExecutorService — Transaktions-Matching via amount/Status
# ============================================================================


async def test_action_executor_matching_nutzt_amount_und_status() -> None:
    from app.services.ai.action_executor_service import (
        ActionContext,
        ActionExecutorService,
    )

    tx = SimpleNamespace(
        id=uuid.uuid4(), amount=100.0, matched_document_id=None, matched_at=None
    )
    db, captured = _make_db([
        _FakeResult(scalars=[tx]),  # unzugeordnete Transaktionen
        _FakeResult(scalar=None),  # keine passende Rechnung
    ])
    service = ActionExecutorService(db)
    context = ActionContext(
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        user_role="admin",
        session_id="test",
    )

    result = await service._execute_match_transactions(uuid.uuid4(), {}, context)

    assert result.success is True
    assert result.affected_count == 0
    # Transaktions-Query: BankTransaction hat kein company_id —
    # Company-Scope via bank_accounts-JOIN
    sql_tx, _ = _compiled(captured[0])
    assert "bank_accounts" in sql_tx
    assert "matched_document_id" in sql_tx
    sql, params = _compiled(captured[1])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.amount" in sql
    assert "pending" not in params  # Phantom-Status ersetzt


# ============================================================================
# (19a) CashFlowForecastService — Phantom is_incoming ersetzt
# ============================================================================


async def test_cash_flow_forecast_receivables_nutzt_customer_join() -> None:
    from app.services.dashboard.cash_flow_forecast_service import (
        CashFlowForecastService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = CashFlowForecastService()

    receivables = await service._get_open_receivables(
        db, uuid.uuid4(), uuid.uuid4(), date.today(), 30
    )

    assert receivables == []
    sql, params = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "customer" in params  # Forderungen = Ausgangsrechnungen


# ============================================================================
# (19) NLQService — Aggregationen via amount
# ============================================================================


async def test_nlq_aggregate_nutzt_amount() -> None:
    from app.services.ai.nlq_service import NLQService

    db, captured = _make_db([_FakeResult(scalar=None)])
    service = NLQService(db)

    result = await service._process_aggregate_query("summe", [], uuid.uuid4())

    assert result.success is True
    sql, _ = _compiled(captured[0])
    _assert_keine_phantom_spalten(sql)
    assert "invoice_tracking.amount" in sql

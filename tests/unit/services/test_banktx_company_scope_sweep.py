# -*- coding: utf-8 -*-
"""Sweep-Regressionstests: BankTransaction-Spalten-Drift (W4, 2026-06-12).

Hintergrund: ``BankTransaction`` (app/db/models_banking.py) hat KEINE Spalten
``company_id``/``matched_invoice_id`` — Migration 232 hat ``bank_transactions``
beim Company-Scoping uebersehen. Ebenso wenig existieren ``purpose``/
``partner_name``/``reconciled``/``linked_entity_id``/``business_entity_id``/
``account_number``/``bank_code``/``sender_name``/``sender_iban``. Alle
betroffenen Query-Pfade liefen zur Laufzeit in ``AttributeError`` (HTTP 500).

Umstellungs-Muster (analog test_invoice_direction_sweep.py):

- Company-Scope via JOIN: ``BankTransaction.bank_account_id ==
  BankAccount.id`` + ``BankAccount.company_id == ...`` (bzw. ``.in_(...)``)
- Entity-Bezug via gematchtes Dokument: ``matched_document_id`` ->
  ``documents.business_entity_id``
- Verwendungszweck via ``reference_text``, Gegenpartei via ``counterparty_*``
- Unzugeordnet = ``matched_document_id IS NULL`` (kein ``reconciled``-Flag)

Die Tests rufen pro Service den umgestellten Query-Pfad mit gemockter
Session auf und pruefen das kompilierte SQL — ohne Datenbank.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import List, Optional, Sequence, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio

_PHANTOM_BANKTX_SPALTEN = (
    "company_id",
    "matched_invoice_id",
    "purpose",
    "partner_name",
    "reconciled",
    "linked_entity_id",
    "business_entity_id",
    "account_number",
    "bank_code",
    "sender_name",
    "sender_iban",
)


# ============================================================================
# Test-Doubles (Muster aus test_invoice_direction_sweep.py)
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


def _assert_keine_banktx_phantome(sql: str) -> None:
    for spalte in _PHANTOM_BANKTX_SPALTEN:
        # Nur echte Spaltenreferenzen "bank_transactions.<spalte>" sind
        # der Bug — gleichnamige Spalten anderer Tabellen sind erlaubt.
        assert f"bank_transactions.{spalte}" not in sql, spalte


def _assert_company_scope_via_join(sql: str) -> None:
    """Company-Scope muss ueber den BankAccount-JOIN laufen."""
    _assert_keine_banktx_phantome(sql)
    assert "JOIN bank_accounts" in sql
    assert "bank_transactions.bank_account_id = bank_accounts.id" in sql
    assert "bank_accounts.company_id" in sql


# ============================================================================
# (1) LiquidityForecastService — Anomalie-Erkennung
# ============================================================================


async def test_liquidity_forecast_anomalien_nutzt_bankaccount_join() -> None:
    from app.services.banking.liquidity_forecast_service import (
        LiquidityForecastService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = LiquidityForecastService(cash_flow_service=MagicMock())

    anomalies = await service._detect_payment_anomalies(db, uuid.uuid4(), None)

    assert anomalies == []
    sql, _ = _compiled(captured[0])
    _assert_company_scope_via_join(sql)


# ============================================================================
# (2) SmartReconciliationService — unzugeordnete Transaktionen + offene
#     Rechnungen
# ============================================================================


async def test_smart_reconciliation_unreconciled_nutzt_bankaccount_join() -> None:
    from app.services.banking.smart_reconciliation_service import (
        SmartReconciliationService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = SmartReconciliationService(db)

    transactions = await service._get_unreconciled_transactions(uuid.uuid4(), 30)

    assert transactions == []
    sql, _ = _compiled(captured[0])
    _assert_company_scope_via_join(sql)
    # Unzugeordnet = kein gematchtes Dokument (kein "reconciled"-Flag)
    assert "bank_transactions.matched_document_id IS NULL" in sql


async def test_smart_reconciliation_open_invoices_nutzt_entity_richtung() -> None:
    from app.services.banking.smart_reconciliation_service import (
        SmartReconciliationService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = SmartReconciliationService(db)

    invoices = await service._get_open_invoices(uuid.uuid4())

    assert invoices == []
    sql, params = _compiled(captured[0])
    assert "invoice_tracking.is_paid" not in sql
    assert "invoice_tracking.is_outgoing" not in sql
    assert "invoice_tracking.status" in sql  # offen = Status-Allowlist
    assert "customer" in params  # Ausgangsrechnung = Kunde


# ============================================================================
# (3) CompanyMetricsService — Banking-Metriken (3 Aggregate)
# ============================================================================


async def test_company_metrics_banking_nutzt_bankaccount_join() -> None:
    from app.services.company_metrics_service import CompanyMetricsService

    db, captured = _make_db(repeat=_FakeResult(scalar=0))
    service = CompanyMetricsService()

    metrics = await service._get_banking_metrics(db, uuid.uuid4())

    assert metrics.unmatched_transactions == 0
    assert len(captured) == 3
    for stmt in captured:
        sql, _ = _compiled(stmt)
        _assert_company_scope_via_join(sql)


# ============================================================================
# (4) TaxAuthorityExportService — GoBD-Export Bankbewegungen
# ============================================================================


async def test_tax_export_bankbewegungen_nutzt_bankaccount_join(tmp_path) -> None:
    from app.services.compliance.tax_authority_export_service import (
        TaxAuthorityExportService,
    )

    db, captured = _make_db([_FakeResult(rows=[])])
    service = TaxAuthorityExportService(db)

    count, file_path = await service._export_bank_transactions(
        uuid.uuid4(), date(2026, 1, 1), date(2026, 3, 31), str(tmp_path)
    )

    assert count == 0
    assert file_path.endswith("bankbewegungen.csv")
    sql, _ = _compiled(captured[0])
    _assert_company_scope_via_join(sql)
    # Konto-Identifikation kommt vom Konto (nicht von Phantom-Spalten)
    assert "bank_accounts.iban" in sql


async def test_tax_export_count_nutzt_bankaccount_join() -> None:
    from app.services.compliance.tax_authority_export_service import (
        TaxAuthorityExportService,
    )

    db, captured = _make_db(repeat=_FakeResult(scalar=0))
    service = TaxAuthorityExportService(db)

    counts = await service.count_records_by_category(
        uuid.uuid4(), date(2026, 1, 1), date(2026, 3, 31)
    )

    assert counts["bankbewegungen"] == 0
    # Query 2 = Bankbewegungen (1=Rechnungen, 3=Dokumente, 4=Audit-Logs)
    sql, _ = _compiled(captured[1])
    _assert_company_scope_via_join(sql)


# ============================================================================
# (5) KnowledgeGraphService — Finanzkette (Entity-Bezug via Dokument)
# ============================================================================


async def test_graph_financial_chain_nutzt_dokument_und_konto_join() -> None:
    from app.services.knowledge_graph.graph_service import KnowledgeGraphService

    company_id = uuid.uuid4()
    entity = SimpleNamespace(company_id=company_id, name="Testfirma GmbH")
    db, captured = _make_db(
        [_FakeResult(scalars=[]), _FakeResult(scalars=[])]
    )
    db.get = AsyncMock(return_value=entity)
    service = KnowledgeGraphService()

    chain = await service.get_financial_chain(uuid.uuid4(), company_id, db)

    assert chain["matchStatus"] == "none"
    # captured[0] = Rechnungen, captured[1] = Transaktionen
    sql, _ = _compiled(captured[1])
    _assert_company_scope_via_join(sql)
    assert "JOIN documents" in sql
    assert "documents.business_entity_id" in sql


# ============================================================================
# (6) HoldingKPIService — konsolidierte Banking-Metriken (.in_-Variante)
# ============================================================================


async def test_holding_kpi_banking_nutzt_bankaccount_join() -> None:
    from app.services.holding.holding_kpi_service import HoldingKPIService

    db, captured = _make_db(repeat=_FakeResult(scalar=0))
    service = HoldingKPIService(db)

    metrics = await service._get_banking_metrics([uuid.uuid4()])

    assert metrics["transactions_last_30d"] == 0
    assert len(captured) == 3
    # Saldo: BankAccount-Spalte heisst current_balance (kein "balance")
    sql_balance, _ = _compiled(captured[0])
    assert "bank_accounts.current_balance" in sql_balance
    # Transaktions-Count: Company-Scope via JOIN + IN-Liste
    sql_tx, _ = _compiled(captured[2])
    _assert_company_scope_via_join(sql_tx)
    assert "bank_accounts.company_id IN" in sql_tx


# ============================================================================
# (7) IntercompanyReconciliationService — IC-Transaktionen (.in_-Variante)
# ============================================================================


async def test_intercompany_ic_transaktionen_nutzt_bankaccount_join() -> None:
    from app.services.holding.intercompany_reconciliation_service import (
        IntercompanyReconciliationService,
    )

    company_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db, captured = _make_db(
        [
            _FakeResult(rows=[("DE89370400440532013000", company_id)]),
            _FakeResult(rows=[]),
        ]
    )
    service = IntercompanyReconciliationService(db)

    ic_transactions = await service._find_ic_bank_transactions(
        [company_id], now - timedelta(days=30), now, {company_id: "A GmbH"}
    )

    assert ic_transactions == []
    sql, _ = _compiled(captured[1])
    _assert_company_scope_via_join(sql)
    assert "bank_accounts.company_id IN" in sql


# ============================================================================
# (8) CashflowPredictor (insights) — Saldo, Recurring, Pending Invoices
# ============================================================================


async def test_cashflow_predictor_saldo_nutzt_bankaccount_join() -> None:
    from app.services.insights.cashflow_predictor import CashflowPredictor

    db, captured = _make_db([_FakeResult(scalar=0)])
    service = CashflowPredictor()

    balance = await service._get_current_balance(db, uuid.uuid4())

    assert balance == Decimal("0")
    sql, _ = _compiled(captured[0])
    _assert_company_scope_via_join(sql)


async def test_cashflow_predictor_recurring_nutzt_reale_spalten() -> None:
    from app.services.insights.cashflow_predictor import CashflowPredictor

    db, captured = _make_db([_FakeResult(rows=[])])
    service = CashflowPredictor()

    recurring = await service._identify_recurring_payments(db, uuid.uuid4())

    assert recurring == []
    sql, _ = _compiled(captured[0])
    _assert_company_scope_via_join(sql)
    # Verwendungszweck/Partner = reale Spalten (kein purpose/partner_name)
    assert "bank_transactions.reference_text" in sql
    assert "bank_transactions.counterparty_name" in sql


async def test_cashflow_predictor_pending_invoices_ohne_invoice_type() -> None:
    from app.services.insights.cashflow_predictor import CashflowPredictor

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = CashflowPredictor()

    pending = await service._get_pending_invoices(db, uuid.uuid4())

    assert pending == []
    sql, params = _compiled(captured[0])
    assert "invoice_tracking.invoice_type" not in sql
    assert "invoice_tracking.status" in sql  # offen = Status-Allowlist
    assert "pending" not in params  # Phantom-Status existiert nicht


# ============================================================================
# (9) SkontoOptimizer — Saldo
# ============================================================================


async def test_skonto_optimizer_saldo_nutzt_bankaccount_join() -> None:
    from app.services.insights.skonto_optimizer import SkontoOptimizer

    db, captured = _make_db([_FakeResult(scalar=0)])
    service = SkontoOptimizer()

    balance = await service._get_current_balance(db, uuid.uuid4())

    assert balance == Decimal("0")
    sql, _ = _compiled(captured[0])
    _assert_company_scope_via_join(sql)


# ============================================================================
# (10) AnomalyInvestigationService — Entity-Transaktionen via Dokument
# ============================================================================


async def test_anomaly_investigation_transaktionen_nutzt_dokument_join() -> None:
    from app.services.orchestration.anomaly_investigation_service import (
        AnomalyInvestigationService,
    )

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = AnomalyInvestigationService()

    related = await service._collect_related_transactions(
        db, uuid.uuid4(), uuid.uuid4()
    )

    assert related == []
    sql, _ = _compiled(captured[0])
    _assert_company_scope_via_join(sql)
    assert "JOIN documents" in sql
    assert "documents.business_entity_id" in sql


# ============================================================================
# (11) SeasonalDetectorService — Monatsstatistiken
# ============================================================================


async def test_seasonal_detector_monatsstatistik_nutzt_bankaccount_join() -> None:
    from app.services.orchestration.seasonal_detector_service import (
        SeasonalDetectorService,
    )

    db, captured = _make_db(repeat=_FakeResult(rows=[]))
    service = SeasonalDetectorService()

    stats = await service._collect_monthly_stats(db, uuid.uuid4())

    assert stats == []
    # captured[0] = Einnahmen (InvoiceTracking), captured[1] = Ausgaben
    sql_revenue, _ = _compiled(captured[0])
    assert "invoice_tracking.gross_amount" not in sql_revenue
    assert "invoice_tracking.amount" in sql_revenue
    sql_expense, _ = _compiled(captured[1])
    _assert_company_scope_via_join(sql_expense)

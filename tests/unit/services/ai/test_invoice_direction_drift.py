"""Regressionstests: Rechnungsrichtung via Entity-JOIN statt invoice_type-Spalte.

Hintergrund (Manifest w2-api, 2026-06-11): ``InvoiceTracking`` hat KEINE
Spalten ``invoice_type``/``total_amount``/``business_entity_id``. Die alten
Service-Queries warfen deshalb zur Laufzeit ``AttributeError`` (HTTP 500).

Entscheidung (bindend): Richtung wird ueber ``BusinessEntity.entity_type``
abgeleitet (customer -> Ausgangsrechnung, supplier -> Eingangsrechnung),
KEINE neue Spalte/Migration. Rechnungen ohne ``entity_id`` werden
ausgeschlossen.

Diese Tests bauen die Queries mit gemockter Session und pruefen das
kompilierte SQL — vor dem Fix schlugen die Methoden bereits beim
Query-Aufbau mit AttributeError fehl.
"""

import uuid
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.invoice_direction import is_incoming_invoice, is_outgoing_invoice

pytestmark = pytest.mark.asyncio


# ============================================================================
# Test-Doubles
# ============================================================================


class _FakeScalars:
    def __init__(self, items: Sequence[object]) -> None:
        self._items = list(items)

    def all(self) -> List[object]:
        return self._items


class _FakeResult:
    """Minimaler Ersatz fuer ein SQLAlchemy-Result."""

    def __init__(
        self,
        scalars: Optional[Sequence[object]] = None,
        one: Optional[Tuple[object, ...]] = None,
        scalar: Optional[object] = None,
        rows: Optional[Sequence[object]] = None,
    ) -> None:
        self._scalars = scalars or []
        self._one = one
        self._scalar = scalar
        self._rows = rows or []

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._scalars)

    def one(self) -> Optional[Tuple[object, ...]]:
        return self._one

    def scalar(self) -> Optional[object]:
        return self._scalar

    def all(self) -> List[object]:
        return list(self._rows)


def _make_db(results: Sequence[_FakeResult]) -> Tuple[MagicMock, List[object]]:
    """Gemockte AsyncSession, die ausgefuehrte Statements mitschreibt."""
    captured: List[object] = []
    queue = list(results)

    async def _execute(stmt: object, *args: object, **kwargs: object) -> _FakeResult:
        captured.append(stmt)
        return queue.pop(0)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db, captured


def _compiled(stmt: object) -> Tuple[str, List[object]]:
    """Kompiliert ein Statement und liefert (SQL-Text, Parameterwerte)."""
    compiled = stmt.compile()
    return str(compiled), list(compiled.params.values())


# ============================================================================
# Helper-Funktionen (app/services/invoice_direction.py)
# ============================================================================


async def test_outgoing_filter_ist_customer_semi_join() -> None:
    sql, params = _compiled(is_outgoing_invoice())
    assert "business_entities" in sql
    assert "entity_id IN" in sql
    assert "customer" in params


async def test_incoming_filter_ist_supplier_semi_join() -> None:
    sql, params = _compiled(is_incoming_invoice())
    assert "business_entities" in sql
    assert "entity_id IN" in sql
    assert "supplier" in params


# ============================================================================
# CashflowPredictionService
# ============================================================================


async def test_cashflow_receivables_nutzt_customer_join() -> None:
    from app.services.ai.cashflow_prediction_service import CashflowPredictionService

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = CashflowPredictionService(db)

    result = await service._get_open_receivables(uuid.uuid4(), days=30)

    assert result == []
    assert len(captured) == 1
    sql, params = _compiled(captured[0])
    assert "invoice_type" not in sql
    assert "business_entities" in sql
    assert "customer" in params


async def test_cashflow_payables_nutzt_supplier_join() -> None:
    from app.services.ai.cashflow_prediction_service import CashflowPredictionService

    db, captured = _make_db([_FakeResult(scalars=[])])
    service = CashflowPredictionService(db)

    result = await service._get_open_payables(uuid.uuid4(), days=30)

    assert result == []
    sql, params = _compiled(captured[0])
    assert "invoice_type" not in sql
    assert "business_entities" in sql
    assert "supplier" in params


# ============================================================================
# InsightGeneratorService
# ============================================================================


async def test_insight_overdue_queries_kompilieren_mit_entity_join() -> None:
    from app.services.ai.insight_generator_service import (
        InsightContext,
        InsightGeneratorService,
    )

    db, captured = _make_db([
        _FakeResult(one=(0, None, None)),  # Forderungen (count, sum, avg)
        _FakeResult(one=(0, None)),        # Verbindlichkeiten (count, sum)
    ])
    service = InsightGeneratorService(db)
    context = InsightContext(company_id=uuid.uuid4(), user_id=uuid.uuid4())

    insights = await service._generate_overdue_insights(context)

    assert insights == []
    assert len(captured) == 2
    sql_recv, params_recv = _compiled(captured[0])
    sql_pay, params_pay = _compiled(captured[1])
    # Spalten-Drift behoben: amount statt total_amount
    assert "total_amount" not in sql_recv
    assert "total_amount" not in sql_pay
    assert "customer" in params_recv
    assert "supplier" in params_pay


async def test_insight_risk_nutzt_entity_id_statt_business_entity_id() -> None:
    from app.services.ai.insight_generator_service import (
        InsightContext,
        InsightGeneratorService,
    )

    db, captured = _make_db([
        _FakeResult(scalars=[]),  # keine High-Risk-Entities
        _FakeResult(rows=[]),     # Konzentrations-Query (top customers)
    ])
    service = InsightGeneratorService(db)
    context = InsightContext(company_id=uuid.uuid4(), user_id=uuid.uuid4())

    insights = await service._generate_risk_insights(context)

    assert insights == []
    # Konzentrations-Query: group_by auf entity_id + Richtung customer
    sql, params = _compiled(captured[1])
    assert "business_entity_id" not in sql
    assert "entity_id" in sql
    assert "customer" in params


# ============================================================================
# FinanceAssistantService
# ============================================================================


async def test_finance_explain_cash_flow_filtert_beide_richtungen() -> None:
    from app.services.ai.finance_assistant_service import (
        AssistantContext,
        FinanceAssistantService,
    )

    db, captured = _make_db([
        _FakeResult(scalar=Decimal("0")),  # Einnahmen
        _FakeResult(scalar=Decimal("0")),  # Ausgaben
    ])
    service = FinanceAssistantService(db)
    context = AssistantContext(user_id=uuid.uuid4(), company_id=uuid.uuid4())

    insight = await service._explain_cash_flow(context)

    assert insight.category == "cash_flow"
    assert len(captured) == 2
    sql_income, params_income = _compiled(captured[0])
    sql_expense, params_expense = _compiled(captured[1])
    # Einnahmen muessen jetzt explizit auf Ausgangsrechnungen gefiltert sein
    assert "customer" in params_income
    assert "supplier" in params_expense
    assert "total_amount" not in sql_income
    assert "total_amount" not in sql_expense


async def test_finance_prediction_case_nutzt_entity_richtung() -> None:
    from app.services.ai.finance_assistant_service import (
        AssistantContext,
        FinanceAssistantService,
    )

    db, captured = _make_db([_FakeResult(rows=[])])
    service = FinanceAssistantService(db)
    context = AssistantContext(user_id=uuid.uuid4(), company_id=uuid.uuid4())

    response = await service._handle_prediction_request("Prognose", context)

    # Zu wenig Daten -> ehrliche deutsche Meldung
    assert response.success is False
    assert "3 Monate" in response.message
    sql, params = _compiled(captured[0])
    assert "invoice_type" not in sql
    assert "total_amount" not in sql
    assert "customer" in params
    assert "supplier" in params

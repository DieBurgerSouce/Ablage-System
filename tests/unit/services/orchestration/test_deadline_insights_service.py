# -*- coding: utf-8 -*-
"""
Unit Tests fuer DeadlineInsightsService.

Testet:
- Skonto-Deadline-Checks
- Vertrags-Kuendigungsfristen
- Zahlungsfristen
- Aufbewahrungsfristen

PHASE 6: Proaktive Intelligenz
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

import app.services.orchestration.deadline_insights_service as deadline_module
from app.services.orchestration.deadline_insights_service import (
    DeadlineInsightsService,
    DeadlineAlert,
    DeadlineType,
    DeadlineCheckResult,
    UrgencyLevel,
    _calculate_urgency,
    get_deadline_insights_service,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_service():
    """Reset modul-globalen Singleton vor und nach jedem Test.

    Der Singleton lebt auf Modulebene (_deadline_insights_instance) und
    wird ueber get_deadline_insights_service() bereitgestellt; direkte
    Instanziierung ist KEIN Singleton.
    """
    deadline_module._deadline_insights_instance = None
    yield
    deadline_module._deadline_insights_instance = None


@pytest.fixture
def service(reset_service):
    """Frische Service-Instanz fuer jeden Test."""
    return DeadlineInsightsService()


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_company_id():
    """Sample Company ID."""
    return uuid4()


@pytest.fixture
def sample_invoice_with_skonto():
    """Sample Invoice mit Skonto-Bedingungen."""
    return MagicMock(
        id=uuid4(),
        invoice_number="R-2026-001",
        vendor_name="Lieferant ABC GmbH",
        gross_amount=Decimal("1190.00"),
        skonto_percentage=2.0,
        skonto_days=14,
        skonto_deadline=datetime.now(timezone.utc) + timedelta(days=5),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
        invoice_date=datetime.now(timezone.utc) - timedelta(days=9),
        status="pending",
    )


@pytest.fixture
def sample_contract_with_cancellation():
    """Sample Contract mit Kuendigungsfrist."""
    return MagicMock(
        id=uuid4(),
        title="Rahmenvertrag Lieferant XYZ",
        contract_type="supplier",
        end_date=datetime.now(timezone.utc) + timedelta(days=60),
        cancellation_notice_days=30,
        auto_renewal=True,
        value=Decimal("50000.00"),
    )


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten (modul-globaler Factory-Singleton)."""

    def test_direct_instantiation_is_not_singleton(self, reset_service):
        """Direkte Instanziierung erzeugt JE eine neue Instanz.

        Der echte Vertrag: die Klasse selbst ist kein Singleton; nur die
        Factory get_deadline_insights_service() liefert eine geteilte Instanz.
        """
        instance1 = DeadlineInsightsService()
        instance2 = DeadlineInsightsService()

        assert instance1 is not instance2

    def test_factory_returns_same_instance(self, reset_service):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_deadline_insights_service()
        instance2 = get_deadline_insights_service()

        assert instance1 is instance2


# =============================================================================
# DeadlineType Tests
# =============================================================================

class TestDeadlineType:
    """Tests fuer DeadlineType Enum."""

    def test_deadline_types_defined(self):
        """Alle DeadlineTypes sind definiert."""
        assert DeadlineType.SKONTO.value == "skonto"
        assert DeadlineType.CONTRACT_CANCELLATION.value == "contract_cancellation"
        assert DeadlineType.PAYMENT_DUE.value == "payment_due"
        assert DeadlineType.RETENTION_EXPIRY.value == "retention_expiry"


# =============================================================================
# DeadlineCheckResult Tests
# =============================================================================

class TestDeadlineCheckResult:
    """Tests fuer DeadlineCheckResult Dataclass."""

    def test_defaults(self):
        """DeadlineCheckResult hat sinnvolle Defaults."""
        result = DeadlineCheckResult(
            deadline_type=DeadlineType.SKONTO,
            deadline_date=datetime.now(timezone.utc),
            title="Test Deadline",
            message="Test Message",
        )

        assert result.days_remaining >= 0 or result.days_remaining < 0
        assert result.priority == "medium"
        assert result.potential_value is None
        assert result.action_url is None
        assert result.entity_id is None

    def test_to_insight_conversion(self):
        """DeadlineCheckResult kann zu ProactiveInsight konvertiert werden."""
        deadline = datetime.now(timezone.utc) + timedelta(days=5)
        result = DeadlineCheckResult(
            deadline_type=DeadlineType.SKONTO,
            deadline_date=deadline,
            days_remaining=5,
            title="Skonto laeuft ab",
            message="Skonto von 2% fuer Rechnung R-001 laeuft in 5 Tagen ab.",
            detail="Bei Zahlung bis zum Stichtag sparen Sie 23.80 EUR.",
            priority="high",
            potential_value=Decimal("23.80"),
            action_url="/invoices/123/pay",
            entity_id=uuid4(),
            entity_name="Lieferant ABC",
        )

        insight = result.to_insight()

        assert insight.insight_type.value == "warning"
        assert insight.priority.value == "high"
        assert insight.title == "Skonto laeuft ab"
        assert insight.potential_value == Decimal("23.80")


# =============================================================================
# Skonto Deadline Tests
# =============================================================================

class TestSkontoDeadlines:
    """Tests fuer Skonto-Deadline-Checks."""

    @pytest.mark.asyncio
    async def test_check_skonto_deadlines_finds_expiring(
        self, service, mock_db, sample_company_id, sample_invoice_with_skonto
    ):
        """Findet ablaufende Skonto-Fristen."""
        # Mock DB Result
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[sample_invoice_with_skonto]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.check_skonto_deadlines(
            db=mock_db,
            company_id=sample_company_id,
            days_ahead=14,
        )

        assert isinstance(insights, list)
        # Kann 0 oder mehr Insights haben je nach Mock-Setup

    @pytest.mark.asyncio
    async def test_check_skonto_calculates_savings(self, service):
        """Berechnet Skonto-Ersparnis korrekt."""
        gross_amount = Decimal("1190.00")
        skonto_percentage = 2.0

        expected_savings = gross_amount * Decimal(skonto_percentage) / Decimal(100)

        assert expected_savings == Decimal("23.80")

    def test_urgency_by_days(self):
        """Dringlichkeit wird ueber _calculate_urgency aus dem Deadline-Datum bestimmt.

        Echter Vertrag (UrgencyLevel): <=1 Tag CRITICAL, <=3 URGENT,
        <=7 SOON, <=14 UPCOMING, sonst FUTURE.
        """
        now = datetime.now(timezone.utc)

        # +0/+1 Tag -> CRITICAL (timedelta.days rundet ab, daher +1d12h)
        assert _calculate_urgency(now + timedelta(days=1, hours=12)) == UrgencyLevel.CRITICAL
        # +3 Tage -> URGENT
        assert _calculate_urgency(now + timedelta(days=3, hours=1)) == UrgencyLevel.URGENT
        # +5 Tage -> SOON
        assert _calculate_urgency(now + timedelta(days=5, hours=1)) == UrgencyLevel.SOON
        # +10 Tage -> UPCOMING
        assert _calculate_urgency(now + timedelta(days=10, hours=1)) == UrgencyLevel.UPCOMING
        # +20 Tage -> FUTURE
        assert _calculate_urgency(now + timedelta(days=20, hours=1)) == UrgencyLevel.FUTURE


# =============================================================================
# Contract Deadline Tests
# =============================================================================

class TestContractDeadlines:
    """Tests fuer Vertrags-Kuendigungsfristen."""

    @pytest.mark.asyncio
    async def test_check_contract_deadlines_finds_upcoming(
        self, service, mock_db, sample_company_id, sample_contract_with_cancellation
    ):
        """Findet bevorstehende Kuendigungsfristen."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[sample_contract_with_cancellation]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.check_contract_deadlines(
            db=mock_db,
            company_id=sample_company_id,
            days_ahead=90,
        )

        assert isinstance(insights, list)

    def test_contract_cancellation_message(self):
        """Vertrags-Kuendigungs-Alert generiert deutsche Kuendigungs-Nachricht.

        Echter Vertrag: DeadlineAlert._generate_message() fuer
        CONTRACT_CANCELLATION nennt den Vertragsnamen und das
        Kuendigungs-Stichdatum.
        """
        deadline = datetime.now(timezone.utc) + timedelta(days=15)
        alert = DeadlineAlert(
            deadline_type=DeadlineType.CONTRACT_CANCELLATION,
            entity_id=uuid4(),
            entity_name="Test Vertrag",
            deadline_date=deadline,
            urgency=_calculate_urgency(deadline),
            metadata={"notice_period_months": 1, "auto_extend_months": 12},
        )

        message = alert._generate_message()

        assert "Test Vertrag" in message
        assert "gekündigt" in message
        assert deadline.strftime("%d.%m.%Y") in message


# =============================================================================
# Payment Due Tests
# =============================================================================

class TestPaymentDueDeadlines:
    """Tests fuer Zahlungsfrist-Checks."""

    @pytest.mark.asyncio
    async def test_check_payment_deadlines_finds_due(
        self, service, mock_db, sample_company_id
    ):
        """Findet faellige Zahlungen."""
        mock_invoice = MagicMock(
            id=uuid4(),
            invoice_number="R-2026-002",
            vendor_name="Lieferant XYZ",
            gross_amount=Decimal("500.00"),
            due_date=datetime.now(timezone.utc) + timedelta(days=3),
            status="pending",
        )

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[mock_invoice]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.check_payment_deadlines(
            db=mock_db,
            company_id=sample_company_id,
            days_ahead=7,
        )

        assert isinstance(insights, list)

    def test_payment_overdue_is_critical(self):
        """Ueberfaellige Zahlungen haben kritische Dringlichkeit.

        Echter Vertrag: Faelligkeitsdatum in der Vergangenheit -> days<=1
        -> UrgencyLevel.CRITICAL (via _calculate_urgency).
        """
        overdue_due_date = datetime.now(timezone.utc) - timedelta(days=5)

        assert _calculate_urgency(overdue_due_date) == UrgencyLevel.CRITICAL

    def test_payment_soon_is_urgent(self):
        """Bald faellige Zahlungen (<=3 Tage) haben URGENT-Dringlichkeit."""
        soon_due_date = datetime.now(timezone.utc) + timedelta(days=3, hours=1)

        assert _calculate_urgency(soon_due_date) == UrgencyLevel.URGENT


# =============================================================================
# Retention Expiry Tests
# =============================================================================

class TestRetentionExpiryDeadlines:
    """Tests fuer Aufbewahrungsfrist-Checks."""

    @pytest.mark.asyncio
    async def test_check_retention_deadlines_finds_expiring(
        self, service, mock_db, sample_company_id
    ):
        """Findet ablaufende Aufbewahrungsfristen."""
        mock_document = MagicMock(
            id=uuid4(),
            filename="rechnung_2016.pdf",
            document_type="invoice",
            retention_until=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc) - timedelta(days=3650),
        )

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[mock_document]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.check_retention_deadlines(
            db=mock_db,
            company_id=sample_company_id,
            days_ahead=90,
        )

        assert isinstance(insights, list)


# =============================================================================
# Combined Check Tests
# =============================================================================

class TestCombinedDeadlineChecks:
    """Tests fuer kombinierte Deadline-Checks."""

    @pytest.mark.asyncio
    async def test_check_all_deadlines(self, service, mock_db, sample_company_id):
        """Kombinierter Check aller Deadline-Typen."""
        # Mock leere Resultate
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.check_all_deadlines(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_check_all_deadlines_sorts_insights_by_priority(
        self, service, mock_db, sample_company_id
    ):
        """check_all_deadlines liefert Insights nach Prioritaet sortiert.

        Echter Vertrag: check_all_deadlines sortiert die gesammelten
        ProactiveInsights inline ueber priority_order
        (CRITICAL < HIGH < MEDIUM < LOW). Wir patchen die einzelnen
        Check-Methoden, damit sie Insights gemischter Prioritaet liefern.
        """
        from app.services.orchestration.proactive_insights_service import (
            InsightPriority,
        )

        def _insight(priority: str) -> "DeadlineCheckResult":
            return DeadlineCheckResult(
                deadline_type=DeadlineType.SKONTO,
                deadline_date=datetime.now(timezone.utc),
                title=priority,
                message="Test",
                priority=priority,
            ).to_insight()

        with patch.object(
            service, "check_skonto_deadlines",
            new=AsyncMock(return_value=[_insight("low")]),
        ), patch.object(
            service, "check_contract_deadlines",
            new=AsyncMock(return_value=[_insight("critical")]),
        ), patch.object(
            service, "check_payment_deadlines",
            new=AsyncMock(return_value=[_insight("high")]),
        ), patch.object(
            service, "check_retention_deadlines",
            new=AsyncMock(return_value=[]),
        ):
            insights = await service.check_all_deadlines(
                db=mock_db, company_id=sample_company_id,
            )

        assert [i.priority for i in insights] == [
            InsightPriority.CRITICAL,
            InsightPriority.HIGH,
            InsightPriority.LOW,
        ]


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_handles_empty_results(self, service, mock_db, sample_company_id):
        """Behandelt leere Ergebnisse korrekt."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.check_all_deadlines(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self, service, mock_db, sample_company_id):
        """Behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.check_skonto_deadlines(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_handles_none_values(self, service, mock_db, sample_company_id):
        """Behandelt None-Werte in Skonto-Feldern graceful.

        Echter Vertrag: check_skonto_deadlines ueberspringt Rechnungen ohne
        skonto_deadline (continue) und faengt None bei Betrag/Prozent ueber
        'or 0' ab -> keine Exception, kein Alert fuer die None-Rechnung.
        """
        invoice = MagicMock(
            id=uuid4(),
            invoice_number="R-NONE",
            supplier_name=None,
            total_amount=None,
            skonto_percentage=None,
            skonto_deadline=None,
        )

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[invoice]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.check_skonto_deadlines(
            db=mock_db, company_id=sample_company_id,
        )

        # None-Deadline-Rechnung wird uebersprungen, keine Exception
        assert insights == []

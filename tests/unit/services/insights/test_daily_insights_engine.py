# -*- coding: utf-8 -*-
"""
Unit Tests fuer DailyInsightsEngine.

Vision 2026 Q4: Tests fuer die proaktive Insight-Generierung.

W3 (2026-06-12): Komplett auf den ECHTEN Service-Vertrag modernisiert.
Die alte Fassung testete eine nie implementierte API
(`DailyInsight(message=..., explanation=..., impact_value=...)`,
`engine.get_generator_configs()`, `InsightGeneratorConfig(name=...)`).
Realer Vertrag (app/services/insights/daily_insights_engine.py):
- DailyInsight: dataclass mit title/summary/detail/recommendation,
  predicted_date/predicted_amount, factors als List[InsightFactorDict]
- InsightGeneratorConfig: Schwellenwert-Konfiguration (cashflow_warning_days, ...)
- Engine: generate_daily_insights(company_id, data_providers) + register_generator
- DB-Convenience: generate_all_insights_from_db / generate_insights_by_type_from_db
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Union
from uuid import UUID, uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.insights.daily_insights_engine import (
    BaseInsightGenerator,
    CashflowWarningGenerator,
    ContractExpiringGenerator,
    DailyInsight,
    DailyInsightsEngine,
    DailyInsightType as InsightType,
    DataProvidersResult,
    InsightFactorDict as InsightFactor,
    InsightGeneratorConfig,
    InsightSeverity,
    InsightStatus,
    generate_all_insights_from_db,
    generate_insights_by_type_from_db,
    get_daily_insights_engine,
)


class TestInsightType:
    """Tests fuer InsightType Enum."""

    def test_insight_type_enum_values(self) -> None:
        """Test: InsightType Enum hat alle erwarteten Werte."""
        assert InsightType.CASHFLOW_WARNING.value == "cashflow_warning"
        assert InsightType.CONTRACT_EXPIRING.value == "contract_expiring"
        assert InsightType.PAYMENT_RISK.value == "payment_risk"
        assert InsightType.SKONTO_DEADLINE.value == "skonto_deadline"
        assert InsightType.UNUSUAL_PATTERN.value == "unusual_pattern"
        assert InsightType.COMPLIANCE_REMINDER.value == "compliance_reminder"
        assert InsightType.OVERDUE_INVOICE.value == "overdue_invoice"


class TestInsightSeverity:
    """Tests fuer InsightSeverity Enum."""

    def test_severity_values(self) -> None:
        """Test: Severity hat korrekte Werte."""
        assert InsightSeverity.LOW.value == "low"
        assert InsightSeverity.MEDIUM.value == "medium"
        assert InsightSeverity.HIGH.value == "high"
        assert InsightSeverity.CRITICAL.value == "critical"


class TestInsightFactor:
    """Tests fuer InsightFactorDict (TypedDict, KEINE Klasse mit Attributen)."""

    def test_factor_creation(self) -> None:
        """Test: InsightFactor ist ein TypedDict mit Key-Zugriff."""
        factor = InsightFactor(
            name="Zahlungshistorie",
            contribution=0.45,
            value="15 Tage Durchschnitt",
            explanation="Kunde zahlt durchschnittlich 15 Tage nach Faelligkeit",
        )
        assert factor["name"] == "Zahlungshistorie"
        assert factor["contribution"] == 0.45
        assert factor["value"] == "15 Tage Durchschnitt"
        assert "15 Tage" in factor["explanation"]


class TestDailyInsight:
    """Tests fuer DailyInsight (echter dataclass-Vertrag)."""

    def test_daily_insight_creation(self) -> None:
        """Test: DailyInsight kann mit echten Feldern erstellt werden."""
        deadline = datetime.now(timezone.utc) + timedelta(days=14)
        insight = DailyInsight(
            insight_type=InsightType.CASHFLOW_WARNING,
            severity=InsightSeverity.HIGH,
            title="Liquiditätsengpass möglich",
            summary="In 14 Tagen könnte der Kontostand negativ werden.",
            detail="Basierend auf offenen Rechnungen und Zahlungen.",
            recommendation="Zahlungseingänge beschleunigen.",
            factors=[
                InsightFactor(
                    name="Kontostand",
                    contribution=0.5,
                    value="5.000 EUR",
                    explanation="Aktueller Kontostand",
                )
            ],
            confidence=0.85,
            predicted_amount=Decimal("2500.00"),
            predicted_date=deadline,
        )

        assert isinstance(insight.id, UUID)  # auto-generiert
        assert insight.insight_type == InsightType.CASHFLOW_WARNING
        assert insight.severity == InsightSeverity.HIGH
        assert insight.status == InsightStatus.NEW  # Default
        assert insight.confidence == 0.85
        assert insight.predicted_amount == Decimal("2500.00")
        assert insight.predicted_date == deadline
        assert len(insight.factors) == 1
        assert insight.factors[0]["name"] == "Kontostand"

    def test_daily_insight_to_dict(self) -> None:
        """Test: to_dict() serialisiert UUIDs/Datetimes/Decimals korrekt."""
        company_id = uuid4()
        deadline = datetime.now(timezone.utc) + timedelta(days=3)
        insight = DailyInsight(
            insight_type=InsightType.SKONTO_DEADLINE,
            severity=InsightSeverity.CRITICAL,
            company_id=company_id,
            title="Skonto-Frist",
            summary="Skonto verfällt morgen.",
            predicted_amount=Decimal("42.50"),
            predicted_date=deadline,
        )

        d = insight.to_dict()
        assert d["id"] == str(insight.id)
        assert d["insight_type"] == "skonto_deadline"
        assert d["severity"] == "critical"
        assert d["status"] == "new"
        assert d["company_id"] == str(company_id)
        assert d["predicted_amount"] == 42.5
        assert d["predicted_date"] == deadline.isoformat()
        assert d["created_at"] == insight.created_at.isoformat()


class TestInsightGeneratorConfig:
    """Tests fuer InsightGeneratorConfig (Schwellenwert-Konfiguration)."""

    def test_config_creation_with_defaults(self) -> None:
        """Test: Config mit Standardwerten erstellen."""
        config = InsightGeneratorConfig()
        assert config.cashflow_warning_days == 14
        assert config.cashflow_critical_threshold == Decimal("0")
        assert config.cashflow_warning_threshold == Decimal("5000")
        assert config.contract_warning_days == 30
        assert config.contract_critical_days == 7
        assert config.skonto_warning_days == 3
        assert config.skonto_critical_days == 1
        assert config.risk_score_high_threshold == 75
        assert config.risk_score_critical_threshold == 90

    def test_config_creation_with_custom_values(self) -> None:
        """Test: Config mit benutzerdefinierten Schwellenwerten."""
        config = InsightGeneratorConfig(
            cashflow_warning_days=7,
            contract_warning_days=60,
            skonto_warning_days=5,
            unusual_pattern_threshold=0.5,
        )
        assert config.cashflow_warning_days == 7
        assert config.contract_warning_days == 60
        assert config.skonto_warning_days == 5
        assert config.unusual_pattern_threshold == 0.5


class _FixedInsightGenerator(BaseInsightGenerator):
    """Test-Generator der genau einen festen Insight liefert."""

    insight_type = InsightType.MISSING_DOCUMENT

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        return [
            DailyInsight(
                insight_type=self.insight_type,
                severity=InsightSeverity.MEDIUM,
                company_id=company_id,
                title="Test-Insight",
                summary="Vom Test-Generator erzeugt.",
            )
        ]


class TestDailyInsightsEngine:
    """Tests fuer DailyInsightsEngine (echter Vertrag: data_providers)."""

    @pytest.fixture
    def engine(self) -> DailyInsightsEngine:
        """Erstellt Engine-Instanz fuer Tests."""
        return DailyInsightsEngine()

    async def test_generate_with_empty_providers(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: Ohne Daten werden keine Insights generiert."""
        company_id = uuid4()
        result = await engine.generate_daily_insights(company_id, {})

        assert result.company_id == company_id
        assert result.total_insights == 0
        assert result.insights == []
        assert result.generation_time_seconds >= 0

    async def test_generate_mixed_severities_sorted(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: Insights aus mehreren Generatoren, sortiert nach Severity."""
        company_id = uuid4()
        now = datetime.now(timezone.utc)

        def cashflow_provider() -> List[Dict[str, Union[str, int, float]]]:
            # Negativer Saldo -> CRITICAL
            return [{
                "date": (now + timedelta(days=10)).isoformat(),
                "predicted_balance": -1000.0,
                "confidence": 0.9,
            }]

        async def skonto_provider() -> List[Dict[str, Union[str, int, float]]]:
            # 2-3 Tage Restfrist -> HIGH (warning_days=3, critical_days=1)
            return [{
                "invoice_id": str(uuid4()),
                "invoice_number": "RE-2026-001",
                "skonto_deadline": (now + timedelta(days=3)).isoformat(),
                "skonto_amount": 51.30,
                "supplier_name": "Muster GmbH",
            }]

        def pattern_provider() -> List[Dict[str, Union[str, int, float]]]:
            # Negative Abweichung -> LOW
            return [{
                "category": "Bürobedarf",
                "current_amount": 300.0,
                "avg_amount": 500.0,
                "deviation_percent": -40.0,
            }]

        result = await engine.generate_daily_insights(
            company_id,
            {
                "cashflow_predictions": cashflow_provider,
                "upcoming_skonto": skonto_provider,  # async Provider
                "spending_patterns": pattern_provider,
            },
        )

        assert result.total_insights == 3
        severities = [i.severity for i in result.insights]
        assert severities == [
            InsightSeverity.CRITICAL,
            InsightSeverity.HIGH,
            InsightSeverity.LOW,
        ]
        assert result.insights_by_severity == {
            "critical": 1, "high": 1, "low": 1,
        }
        assert result.insights_by_type["cashflow_warning"] == 1
        assert result.insights_by_type["skonto_deadline"] == 1
        assert result.insights_by_type["unusual_pattern"] == 1
        # Alle Insights gehoeren zur Company
        assert all(i.company_id == company_id for i in result.insights)

    async def test_failing_provider_is_tolerated(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: Ein crashender Data Provider bricht die Generierung NICHT ab."""
        company_id = uuid4()

        def broken_provider() -> List[Dict[str, Union[str, int, float]]]:
            raise ValueError("Provider kaputt")

        def cashflow_provider() -> List[Dict[str, Union[str, int, float]]]:
            return [{
                "date": datetime.now(timezone.utc).isoformat(),
                "predicted_balance": -1.0,
                "confidence": 0.9,
            }]

        result = await engine.generate_daily_insights(
            company_id,
            {
                "spending_patterns": broken_provider,
                "cashflow_predictions": cashflow_provider,
            },
        )

        # Der intakte Provider liefert weiterhin seinen Insight
        assert result.total_insights == 1
        assert result.insights[0].insight_type == InsightType.CASHFLOW_WARNING

    async def test_register_custom_generator(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: Zusaetzliche Generatoren koennen registriert werden."""
        company_id = uuid4()
        engine.register_generator(_FixedInsightGenerator(engine.config))

        result = await engine.generate_daily_insights(company_id, {})

        assert result.total_insights == 1
        assert result.insights[0].title == "Test-Insight"
        assert result.insights_by_type["missing_document"] == 1

    async def test_get_critical_insights_limits(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: get_critical_insights respektiert max_insights."""
        company_id = uuid4()

        def cashflow_provider() -> List[Dict[str, Union[str, int, float]]]:
            return [
                {
                    "date": datetime.now(timezone.utc).isoformat(),
                    "predicted_balance": -100.0 * (n + 1),
                    "confidence": 0.9,
                }
                for n in range(5)
            ]

        insights = await engine.get_critical_insights(
            company_id,
            {"cashflow_predictions": cashflow_provider},
            max_insights=2,
        )
        assert len(insights) == 2


class TestDbConvenienceFunctions:
    """Tests fuer die DB-Convenience-Funktionen (gemockte AsyncSession)."""

    @pytest.fixture
    def engine(self) -> DailyInsightsEngine:
        return DailyInsightsEngine()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock-Session: alle Queries liefern leere Ergebnisse."""
        db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        return db

    async def test_generate_all_insights_empty_db(
        self, engine: DailyInsightsEngine, mock_db: AsyncMock
    ) -> None:
        """Test: Leere DB -> leere Insight-Liste, kein Crash."""
        insights = await generate_all_insights_from_db(engine, mock_db, uuid4())
        assert isinstance(insights, list)
        assert insights == []
        # Die DB-Provider haben tatsaechlich Queries abgesetzt
        assert mock_db.execute.await_count >= 1

    async def test_generate_insights_by_type(
        self, engine: DailyInsightsEngine, mock_db: AsyncMock
    ) -> None:
        """Test: Typ-Filter liefert nur Insights des angefragten Typs."""
        insights = await generate_insights_by_type_from_db(
            engine, mock_db, uuid4(), InsightType.CASHFLOW_WARNING
        )
        assert isinstance(insights, list)
        for insight in insights:
            assert insight.insight_type == InsightType.CASHFLOW_WARNING


class TestGetDailyInsightsEngine:
    """Tests fuer Factory-Funktion."""

    def test_get_daily_insights_engine_singleton(self) -> None:
        """Test: Factory gibt Singleton-Instanz zurueck."""
        engine1 = get_daily_insights_engine()
        engine2 = get_daily_insights_engine()

        assert engine1 is engine2

    def test_get_daily_insights_engine_with_config_creates_new(self) -> None:
        """Test: Mit expliziter Config wird eine neue Instanz erstellt."""
        engine1 = get_daily_insights_engine()
        engine2 = get_daily_insights_engine(
            config=InsightGeneratorConfig(cashflow_warning_days=7)
        )
        assert engine2.config.cashflow_warning_days == 7
        assert engine1 is not engine2

    def test_get_daily_insights_engine_type(self) -> None:
        """Test: Factory gibt korrekte Instanz zurueck."""
        engine = get_daily_insights_engine()
        assert isinstance(engine, DailyInsightsEngine)


class TestInsightTypeDescriptions:
    """Tests fuer deutsche Insight-Texte (Critical Rule 2, echte Generatoren)."""

    async def test_cashflow_warning_description(self) -> None:
        """Test: Cashflow-Warnung hat deutschen Titel + Empfehlung."""
        gen = CashflowWarningGenerator(InsightGeneratorConfig())
        insights = await gen.generate(uuid4(), {
            "cashflow_predictions": [{
                "date": datetime.now(timezone.utc).isoformat(),
                "predicted_balance": -500.0,
                "confidence": 0.9,
            }],
        })

        assert len(insights) == 1
        assert "Liquiditaetsengpass" in insights[0].title
        assert insights[0].severity == InsightSeverity.CRITICAL
        assert "Zahlung" in insights[0].recommendation
        assert insights[0].primary_action_label == "Zahlungen optimieren"

    async def test_contract_expiring_description(self) -> None:
        """Test: Vertragsablauf hat sinnvolle deutsche Beschreibung."""
        gen = ContractExpiringGenerator(InsightGeneratorConfig())
        now = datetime.now(timezone.utc)
        insights = await gen.generate(uuid4(), {
            "expiring_contracts": [{
                "id": str(uuid4()),
                "title": "Mietvertrag Lager",
                "notice_date": (now + timedelta(days=5)).isoformat(),
                "monthly_cost": 1200.0,
            }],
        })

        assert len(insights) == 1
        assert "Kündigungsfrist" in insights[0].title
        assert "Mietvertrag Lager" in insights[0].title
        # <= contract_critical_days (7) -> CRITICAL
        assert insights[0].severity == InsightSeverity.CRITICAL
        assert "Tagen" in insights[0].summary
        assert insights[0].primary_action_label == "Vertrag prüfen"


class TestInsightSorting:
    """Tests fuer Insight-Sortierung (durch die Engine selbst)."""

    async def test_insights_sorted_by_severity(self) -> None:
        """Test: Engine sortiert Insights nach Schweregrad (critical zuerst)."""
        engine = DailyInsightsEngine()
        now = datetime.now(timezone.utc)

        def pattern_provider() -> List[Dict[str, Union[str, int, float]]]:
            # LOW (negative Abweichung) — wird von der Engine ans Ende sortiert
            return [{
                "category": "Reisekosten",
                "current_amount": 100.0,
                "avg_amount": 400.0,
                "deviation_percent": -75.0,
            }]

        def cashflow_provider() -> List[Dict[str, Union[str, int, float]]]:
            # CRITICAL — muss trotz spaeterem Generator-Lauf vorne stehen
            return [{
                "date": (now + timedelta(days=7)).isoformat(),
                "predicted_balance": -2000.0,
                "confidence": 0.95,
            }]

        result = await engine.generate_daily_insights(
            uuid4(),
            {
                "spending_patterns": pattern_provider,
                "cashflow_predictions": cashflow_provider,
            },
        )

        assert result.total_insights == 2
        assert result.insights[0].severity == InsightSeverity.CRITICAL
        assert result.insights[-1].severity == InsightSeverity.LOW

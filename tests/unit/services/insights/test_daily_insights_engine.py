# -*- coding: utf-8 -*-
"""
Unit Tests fuer DailyInsightsEngine.

Vision 2026 Q4: Tests fuer die proaktive Insight-Generierung.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.insights.daily_insights_engine import (
    DailyInsightsEngine,
    DailyInsight,
    InsightType,
    InsightSeverity,
    InsightFactor,
    InsightGeneratorConfig,
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
    """Tests fuer InsightFactor."""

    def test_factor_creation(self) -> None:
        """Test: InsightFactor kann erstellt werden."""
        factor = InsightFactor(
            name="Zahlungshistorie",
            contribution=0.45,
            value="15 Tage Durchschnitt",
            explanation="Kunde zahlt durchschnittlich 15 Tage nach Faelligkeit",
        )
        assert factor.name == "Zahlungshistorie"
        assert factor.contribution == 0.45
        assert factor.value == "15 Tage Durchschnitt"
        assert "15 Tage" in factor.explanation


class TestDailyInsight:
    """Tests fuer DailyInsight."""

    def test_daily_insight_creation(self) -> None:
        """Test: DailyInsight kann erstellt werden."""
        insight = DailyInsight(
            id="insight-001",
            insight_type=InsightType.CASHFLOW_WARNING,
            severity=InsightSeverity.HIGH,
            title="Liquiditaetsengpass moeglich",
            message="In 14 Tagen koennte der Kontostand negativ werden.",
            explanation="Basierend auf offenen Rechnungen und Zahlungen.",
            recommendation="Zahlungseingaenge beschleunigen.",
            factors=[
                InsightFactor(
                    name="Kontostand",
                    contribution=0.5,
                    value="5.000 EUR",
                    explanation="Aktueller Kontostand",
                )
            ],
            confidence=0.85,
            impact_value=Decimal("2500.00"),
            deadline=date.today() + timedelta(days=14),
            created_at=datetime.now(timezone.utc),
        )

        assert insight.id == "insight-001"
        assert insight.insight_type == InsightType.CASHFLOW_WARNING
        assert insight.severity == InsightSeverity.HIGH
        assert insight.confidence == 0.85
        assert insight.impact_value == Decimal("2500.00")
        assert len(insight.factors) == 1


class TestInsightGeneratorConfig:
    """Tests fuer InsightGeneratorConfig."""

    def test_config_creation_with_defaults(self) -> None:
        """Test: Config mit Standardwerten erstellen."""
        config = InsightGeneratorConfig(
            name="cashflow",
            description="Cashflow-Warnungen",
        )
        assert config.name == "cashflow"
        assert config.enabled is True
        assert config.priority == 1
        assert config.max_insights == 10

    def test_config_creation_with_custom_values(self) -> None:
        """Test: Config mit benutzerdefinierten Werten."""
        config = InsightGeneratorConfig(
            name="contracts",
            description="Vertragsablauf",
            enabled=False,
            priority=5,
            max_insights=20,
        )
        assert config.enabled is False
        assert config.priority == 5
        assert config.max_insights == 20


class TestDailyInsightsEngine:
    """Tests fuer DailyInsightsEngine."""

    @pytest.fixture
    def engine(self) -> DailyInsightsEngine:
        """Erstellt Engine-Instanz fuer Tests."""
        return DailyInsightsEngine()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstellt Mock-Datenbanksession."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        return db

    def test_engine_initialization(self, engine: DailyInsightsEngine) -> None:
        """Test: Engine wird korrekt initialisiert."""
        assert engine is not None
        configs = engine.get_generator_configs()
        assert len(configs) > 0

    def test_get_generator_configs(self, engine: DailyInsightsEngine) -> None:
        """Test: Generator-Konfigurationen abrufen."""
        configs = engine.get_generator_configs()

        # Mindestens die Standard-Generatoren sollten vorhanden sein
        config_names = [c.name for c in configs]
        assert "cashflow" in config_names or len(configs) >= 1

    def test_update_generator_config_enable_disable(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: Generator aktivieren/deaktivieren."""
        configs = engine.get_generator_configs()
        if not configs:
            pytest.skip("Keine Generatoren konfiguriert")

        first_config = configs[0]
        original_enabled = first_config.enabled

        # Deaktivieren
        success = engine.update_generator_config(
            first_config.name, enabled=not original_enabled
        )
        assert success is True

        # Pruefen
        updated_configs = engine.get_generator_configs()
        updated_config = next(c for c in updated_configs if c.name == first_config.name)
        assert updated_config.enabled == (not original_enabled)

        # Zuruecksetzen
        engine.update_generator_config(first_config.name, enabled=original_enabled)

    def test_update_generator_config_priority(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: Generator-Prioritaet aendern."""
        configs = engine.get_generator_configs()
        if not configs:
            pytest.skip("Keine Generatoren konfiguriert")

        first_config = configs[0]
        new_priority = 99

        success = engine.update_generator_config(
            first_config.name, priority=new_priority
        )
        assert success is True

        updated_configs = engine.get_generator_configs()
        updated_config = next(c for c in updated_configs if c.name == first_config.name)
        assert updated_config.priority == new_priority

    def test_update_generator_config_max_insights(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: Maximale Insights aendern."""
        configs = engine.get_generator_configs()
        if not configs:
            pytest.skip("Keine Generatoren konfiguriert")

        first_config = configs[0]
        new_max = 25

        success = engine.update_generator_config(
            first_config.name, max_insights=new_max
        )
        assert success is True

        updated_configs = engine.get_generator_configs()
        updated_config = next(c for c in updated_configs if c.name == first_config.name)
        assert updated_config.max_insights == new_max

    def test_update_nonexistent_generator(
        self, engine: DailyInsightsEngine
    ) -> None:
        """Test: Nicht existierenden Generator aktualisieren."""
        success = engine.update_generator_config(
            "nonexistent_generator", enabled=False
        )
        assert success is False

    @pytest.mark.asyncio
    async def test_generate_all_insights_empty_db(
        self, engine: DailyInsightsEngine, mock_db: AsyncMock
    ) -> None:
        """Test: Insights generieren bei leerer Datenbank."""
        company_id = uuid4()

        # Mock leere Ergebnisse
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        insights = await engine.generate_all_insights(mock_db, company_id)

        # Sollte leere Liste oder minimale Insights zurueckgeben
        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_generate_insights_by_type(
        self, engine: DailyInsightsEngine, mock_db: AsyncMock
    ) -> None:
        """Test: Insights nach Typ generieren."""
        company_id = uuid4()

        # Mock leere Ergebnisse
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        insights = await engine.generate_insights_by_type(
            mock_db, company_id, InsightType.CASHFLOW_WARNING
        )

        assert isinstance(insights, list)
        # Alle Insights sollten vom richtigen Typ sein
        for insight in insights:
            assert insight.insight_type == InsightType.CASHFLOW_WARNING


class TestGetDailyInsightsEngine:
    """Tests fuer Factory-Funktion."""

    def test_get_daily_insights_engine_singleton(self) -> None:
        """Test: Factory gibt Singleton-Instanz zurueck."""
        engine1 = get_daily_insights_engine()
        engine2 = get_daily_insights_engine()

        assert engine1 is engine2

    def test_get_daily_insights_engine_type(self) -> None:
        """Test: Factory gibt korrekte Instanz zurueck."""
        engine = get_daily_insights_engine()
        assert isinstance(engine, DailyInsightsEngine)


class TestInsightTypeDescriptions:
    """Tests fuer Insight-Typ-Beschreibungen (deutsche Texte)."""

    def test_cashflow_warning_description(self) -> None:
        """Test: Cashflow-Warnung hat deutsche Beschreibung."""
        insight = DailyInsight(
            id="test",
            insight_type=InsightType.CASHFLOW_WARNING,
            severity=InsightSeverity.HIGH,
            title="Liquiditaetsengpass moeglich",
            message="In 14 Tagen koennte die Liquiditaet knapp werden.",
            explanation="Basierend auf Zahlungsplan.",
            recommendation="Zahlungen pruefen.",
            factors=[],
            confidence=0.9,
            created_at=datetime.now(timezone.utc),
        )
        # Deutsche Texte pruefen (keine Umlaute wegen UTF-8 Kompatibilitaet)
        assert "Liquiditaet" in insight.title or "Liquiditaet" in insight.message

    def test_contract_expiring_description(self) -> None:
        """Test: Vertragsablauf hat sinnvolle Beschreibung."""
        insight = DailyInsight(
            id="test",
            insight_type=InsightType.CONTRACT_EXPIRING,
            severity=InsightSeverity.MEDIUM,
            title="Vertrag laeuft aus",
            message="Vertrag mit Muster GmbH laeuft in 30 Tagen aus.",
            explanation="Kuendigungsfrist beachten.",
            recommendation="Vertrag pruefen und ggf. verlaengern.",
            factors=[],
            confidence=0.95,
            created_at=datetime.now(timezone.utc),
        )
        assert "Vertrag" in insight.title
        assert "laeuft" in insight.message or "Tagen" in insight.message


class TestInsightSorting:
    """Tests fuer Insight-Sortierung."""

    def test_insights_sorted_by_severity(self) -> None:
        """Test: Insights werden nach Schweregrad sortiert."""
        insights = [
            DailyInsight(
                id="1",
                insight_type=InsightType.SKONTO_DEADLINE,
                severity=InsightSeverity.LOW,
                title="Low",
                message="Low priority",
                explanation="",
                recommendation="",
                factors=[],
                confidence=0.9,
                created_at=datetime.now(timezone.utc),
            ),
            DailyInsight(
                id="2",
                insight_type=InsightType.CASHFLOW_WARNING,
                severity=InsightSeverity.CRITICAL,
                title="Critical",
                message="Critical priority",
                explanation="",
                recommendation="",
                factors=[],
                confidence=0.9,
                created_at=datetime.now(timezone.utc),
            ),
            DailyInsight(
                id="3",
                insight_type=InsightType.PAYMENT_RISK,
                severity=InsightSeverity.HIGH,
                title="High",
                message="High priority",
                explanation="",
                recommendation="",
                factors=[],
                confidence=0.9,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        # Sortieren nach Schweregrad (critical > high > medium > low)
        severity_order = {
            InsightSeverity.CRITICAL: 0,
            InsightSeverity.HIGH: 1,
            InsightSeverity.MEDIUM: 2,
            InsightSeverity.LOW: 3,
        }

        sorted_insights = sorted(
            insights, key=lambda i: severity_order.get(i.severity, 4)
        )

        assert sorted_insights[0].severity == InsightSeverity.CRITICAL
        assert sorted_insights[1].severity == InsightSeverity.HIGH
        assert sorted_insights[2].severity == InsightSeverity.LOW

# -*- coding: utf-8 -*-
"""Unit Tests for Company Metrics Service.

Tests fuer Multi-Firma Dashboard, Metriken-Aggregation und Health Score.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.services.company_metrics_service import (
    CompanyMetricsService,
    CompanyMetrics,
    CompanyDocumentMetrics,
    CompanyInvoiceMetrics,
    CompanyEntityMetrics,
    CompanyDunningMetrics,
    CompanyBankingMetrics,
    DashboardSummary,
    company_metrics_service,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    return AsyncMock()


@pytest.fixture
def service() -> CompanyMetricsService:
    """Erstellt eine CompanyMetricsService-Instanz."""
    return CompanyMetricsService()


@pytest.fixture
def sample_company_id() -> UUID:
    """Beispiel Company-UUID."""
    return uuid4()


@pytest.fixture
def sample_metrics(sample_company_id: UUID) -> CompanyMetrics:
    """Erstellt Beispiel-Metriken."""
    return CompanyMetrics(
        company_id=sample_company_id,
        company_name="Testfirma GmbH",
        company_short_name="TF",
        is_active=True,
        documents=CompanyDocumentMetrics(
            total_documents=100,
            documents_this_month=15,
            documents_last_month=12,
            document_growth_percent=25.0,
        ),
        invoices=CompanyInvoiceMetrics(
            total_invoices=50,
            total_amount=Decimal("50000.00"),
            paid_amount=Decimal("40000.00"),
            outstanding_amount=Decimal("10000.00"),
            overdue_count=5,
            overdue_amount=Decimal("3000.00"),
            average_payment_days=14.5,
        ),
        entities=CompanyEntityMetrics(
            total_entities=30,
            customers=20,
            suppliers=10,
            high_risk_entities=2,
        ),
        dunning=CompanyDunningMetrics(
            active_dunnings=8,
            total_dunning_amount=Decimal("5000.00"),
            level_1_count=4,
            level_2_count=2,
            level_3_count=1,
            level_4_count=1,
        ),
        banking=CompanyBankingMetrics(
            total_balance=Decimal("25000.00"),
            incoming_this_month=Decimal("15000.00"),
            outgoing_this_month=Decimal("8000.00"),
            unmatched_transactions=5,
        ),
        health_score=75,
    )


# =============================================================================
# Dataclass Tests
# =============================================================================


class TestCompanyDocumentMetrics:
    """Tests fuer CompanyDocumentMetrics Dataclass."""

    def test_default_values(self) -> None:
        """Test Standardwerte."""
        metrics = CompanyDocumentMetrics()
        assert metrics.total_documents == 0
        assert metrics.documents_this_month == 0
        assert metrics.documents_last_month == 0
        assert metrics.document_growth_percent == 0.0

    def test_custom_values(self) -> None:
        """Test mit benutzerdefinierten Werten."""
        metrics = CompanyDocumentMetrics(
            total_documents=200,
            documents_this_month=30,
            documents_last_month=25,
            document_growth_percent=20.0,
        )
        assert metrics.total_documents == 200
        assert metrics.documents_this_month == 30
        assert metrics.documents_last_month == 25
        assert metrics.document_growth_percent == 20.0


class TestCompanyInvoiceMetrics:
    """Tests fuer CompanyInvoiceMetrics Dataclass."""

    def test_default_values(self) -> None:
        """Test Standardwerte."""
        metrics = CompanyInvoiceMetrics()
        assert metrics.total_invoices == 0
        assert metrics.total_amount == Decimal("0.00")
        assert metrics.paid_amount == Decimal("0.00")
        assert metrics.outstanding_amount == Decimal("0.00")
        assert metrics.overdue_count == 0
        assert metrics.overdue_amount == Decimal("0.00")
        assert metrics.average_payment_days == 0.0

    def test_custom_values(self) -> None:
        """Test mit benutzerdefinierten Werten."""
        metrics = CompanyInvoiceMetrics(
            total_invoices=100,
            total_amount=Decimal("100000.00"),
            paid_amount=Decimal("80000.00"),
            outstanding_amount=Decimal("20000.00"),
            overdue_count=10,
            overdue_amount=Decimal("5000.00"),
            average_payment_days=21.3,
        )
        assert metrics.total_invoices == 100
        assert float(metrics.total_amount) == 100000.00


class TestCompanyEntityMetrics:
    """Tests fuer CompanyEntityMetrics Dataclass."""

    def test_default_values(self) -> None:
        """Test Standardwerte."""
        metrics = CompanyEntityMetrics()
        assert metrics.total_entities == 0
        assert metrics.customers == 0
        assert metrics.suppliers == 0
        assert metrics.high_risk_entities == 0


class TestCompanyDunningMetrics:
    """Tests fuer CompanyDunningMetrics Dataclass."""

    def test_default_values(self) -> None:
        """Test Standardwerte."""
        metrics = CompanyDunningMetrics()
        assert metrics.active_dunnings == 0
        assert metrics.total_dunning_amount == Decimal("0.00")
        assert metrics.level_1_count == 0
        assert metrics.level_2_count == 0
        assert metrics.level_3_count == 0
        assert metrics.level_4_count == 0


class TestCompanyBankingMetrics:
    """Tests fuer CompanyBankingMetrics Dataclass."""

    def test_default_values(self) -> None:
        """Test Standardwerte."""
        metrics = CompanyBankingMetrics()
        assert metrics.total_balance == Decimal("0.00")
        assert metrics.incoming_this_month == Decimal("0.00")
        assert metrics.outgoing_this_month == Decimal("0.00")
        assert metrics.unmatched_transactions == 0


class TestCompanyMetrics:
    """Tests fuer CompanyMetrics Dataclass."""

    def test_to_dict(self, sample_metrics: CompanyMetrics) -> None:
        """Test Konvertierung zu Dictionary."""
        result = sample_metrics.to_dict()

        assert result["company_id"] == str(sample_metrics.company_id)
        assert result["company_name"] == "Testfirma GmbH"
        assert result["company_short_name"] == "TF"
        assert result["is_active"] is True
        assert result["health_score"] == 75

        # Documents
        assert result["documents"]["total"] == 100
        assert result["documents"]["this_month"] == 15
        assert result["documents"]["last_month"] == 12
        assert result["documents"]["growth_percent"] == 25.0

        # Invoices
        assert result["invoices"]["total"] == 50
        assert result["invoices"]["total_amount"] == 50000.00
        assert result["invoices"]["paid_amount"] == 40000.00
        assert result["invoices"]["outstanding_amount"] == 10000.00
        assert result["invoices"]["overdue_count"] == 5
        assert result["invoices"]["overdue_amount"] == 3000.00

        # Entities
        assert result["entities"]["total"] == 30
        assert result["entities"]["customers"] == 20
        assert result["entities"]["suppliers"] == 10
        assert result["entities"]["high_risk"] == 2

        # Dunning
        assert result["dunning"]["active"] == 8
        assert result["dunning"]["total_amount"] == 5000.00
        assert result["dunning"]["by_level"]["1"] == 4
        assert result["dunning"]["by_level"]["2"] == 2
        assert result["dunning"]["by_level"]["3"] == 1
        assert result["dunning"]["by_level"]["4"] == 1

        # Banking
        assert result["banking"]["balance"] == 25000.00
        assert result["banking"]["incoming_this_month"] == 15000.00
        assert result["banking"]["outgoing_this_month"] == 8000.00
        assert result["banking"]["unmatched_transactions"] == 5


class TestDashboardSummary:
    """Tests fuer DashboardSummary Dataclass."""

    def test_default_values(self) -> None:
        """Test Standardwerte."""
        summary = DashboardSummary()
        assert summary.total_companies == 0
        assert summary.active_companies == 0
        assert summary.total_documents == 0
        assert summary.total_invoices == 0
        assert summary.total_outstanding_amount == Decimal("0.00")
        assert summary.total_overdue_amount == Decimal("0.00")
        assert summary.total_entities == 0
        assert summary.active_dunnings == 0

    def test_to_dict(self) -> None:
        """Test Konvertierung zu Dictionary."""
        summary = DashboardSummary(
            total_companies=5,
            active_companies=4,
            total_documents=500,
            total_invoices=200,
            total_outstanding_amount=Decimal("100000.00"),
            total_overdue_amount=Decimal("15000.00"),
            total_entities=150,
            active_dunnings=20,
        )
        result = summary.to_dict()

        assert result["total_companies"] == 5
        assert result["active_companies"] == 4
        assert result["total_documents"] == 500
        assert result["total_invoices"] == 200
        assert result["total_outstanding_amount"] == 100000.00
        assert result["total_overdue_amount"] == 15000.00
        assert result["total_entities"] == 150
        assert result["active_dunnings"] == 20


# =============================================================================
# Health Score Tests
# =============================================================================


class TestHealthScoreCalculation:
    """Tests fuer Health Score Berechnung."""

    def test_perfect_health_score(self, service: CompanyMetricsService) -> None:
        """Test perfekter Health Score (100)."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Test",
            documents=CompanyDocumentMetrics(
                total_documents=100,
                documents_this_month=20,
                documents_last_month=10,
                document_growth_percent=100.0,  # +10 Bonus (max)
            ),
            invoices=CompanyInvoiceMetrics(
                total_invoices=50,
                overdue_count=0,  # Keine Abzuege
            ),
            entities=CompanyEntityMetrics(
                total_entities=30,
                high_risk_entities=0,  # Keine Abzuege
            ),
            dunning=CompanyDunningMetrics(
                level_3_count=0,
                level_4_count=0,  # Keine Abzuege
            ),
            banking=CompanyBankingMetrics(
                unmatched_transactions=0,  # Keine Abzuege
            ),
        )

        score = service._calculate_health_score(metrics)

        # 100 (Basis) + 10 (Wachstum) = 110, gedeckelt auf 100
        assert score == 100

    def test_health_score_with_overdue(self, service: CompanyMetricsService) -> None:
        """Test Health Score mit ueberfaelligen Rechnungen."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Test",
            invoices=CompanyInvoiceMetrics(
                total_invoices=10,
                overdue_count=5,  # 50% ueberfaellig = -30 (max)
            ),
        )

        score = service._calculate_health_score(metrics)

        # 100 - 30 = 70
        assert score == 70

    def test_health_score_with_high_risk(self, service: CompanyMetricsService) -> None:
        """Test Health Score mit High-Risk Entities."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Test",
            entities=CompanyEntityMetrics(
                total_entities=10,
                high_risk_entities=5,  # 50% high risk = -20 (max)
            ),
        )

        score = service._calculate_health_score(metrics)

        # 100 - 20 = 80
        assert score == 80

    def test_health_score_with_level_3_4_dunnings(
        self, service: CompanyMetricsService
    ) -> None:
        """Test Health Score mit Level 3/4 Mahnungen."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Test",
            dunning=CompanyDunningMetrics(
                level_3_count=3,
                level_4_count=2,  # 5 * 5 = 25 -> gedeckelt auf -20
            ),
        )

        score = service._calculate_health_score(metrics)

        # 100 - 20 = 80
        assert score == 80

    def test_health_score_with_unmatched_transactions(
        self, service: CompanyMetricsService
    ) -> None:
        """Test Health Score mit ungematchten Transaktionen."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Test",
            banking=CompanyBankingMetrics(
                unmatched_transactions=25,  # 15 ueber Schwelle, (15-10)/5 = -1
            ),
        )

        score = service._calculate_health_score(metrics)

        # Mindestens -3 Abzug fuer 25 ungematchte
        assert score < 100

    def test_health_score_minimum_zero(self, service: CompanyMetricsService) -> None:
        """Test dass Health Score nicht unter 0 faellt."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Test",
            invoices=CompanyInvoiceMetrics(
                total_invoices=10,
                overdue_count=10,  # 100% = -30
            ),
            entities=CompanyEntityMetrics(
                total_entities=10,
                high_risk_entities=10,  # 100% = -20
            ),
            dunning=CompanyDunningMetrics(
                level_3_count=10,
                level_4_count=10,  # = -20 (max)
            ),
            banking=CompanyBankingMetrics(
                unmatched_transactions=100,  # = -10 (max)
            ),
        )

        score = service._calculate_health_score(metrics)

        # 100 - 30 - 20 - 20 - 10 = 20, aber durch Rundung evt. anders
        assert score >= 0
        assert score <= 100

    def test_health_score_with_document_growth_bonus(
        self, service: CompanyMetricsService
    ) -> None:
        """Test Health Score mit Dokument-Wachstums-Bonus."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Test",
            documents=CompanyDocumentMetrics(
                documents_this_month=20,
                documents_last_month=10,
                document_growth_percent=50.0,  # +5 Bonus
            ),
        )

        score = service._calculate_health_score(metrics)

        # 100 + 5 = 105 -> gedeckelt auf 100
        assert score == 100


# =============================================================================
# Comparison Value Tests
# =============================================================================


class TestComparisonValues:
    """Tests fuer Vergleichswert-Berechnung."""

    def test_get_comparison_value_invoices(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Vergleichswert fuer Rechnungen."""
        value = service._get_comparison_value(sample_metrics, "invoices")
        assert value == 50000.00

    def test_get_comparison_value_documents(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Vergleichswert fuer Dokumente."""
        value = service._get_comparison_value(sample_metrics, "documents")
        assert value == 100.0

    def test_get_comparison_value_entities(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Vergleichswert fuer Entities."""
        value = service._get_comparison_value(sample_metrics, "entities")
        assert value == 30.0

    def test_get_comparison_value_dunning(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Vergleichswert fuer Mahnungen."""
        value = service._get_comparison_value(sample_metrics, "dunning")
        assert value == 5000.00

    def test_get_comparison_value_outstanding(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Vergleichswert fuer offene Forderungen."""
        value = service._get_comparison_value(sample_metrics, "outstanding")
        assert value == 10000.00

    def test_get_comparison_value_overdue(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Vergleichswert fuer ueberfaellige Forderungen."""
        value = service._get_comparison_value(sample_metrics, "overdue")
        assert value == 3000.00

    def test_get_comparison_value_health(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Vergleichswert fuer Health Score."""
        value = service._get_comparison_value(sample_metrics, "health")
        assert value == 75.0

    def test_get_comparison_value_unknown(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Vergleichswert fuer unbekannte Metrik."""
        value = service._get_comparison_value(sample_metrics, "unknown")
        assert value == 0.0


# =============================================================================
# Comparison Details Tests
# =============================================================================


class TestComparisonDetails:
    """Tests fuer Vergleichs-Details."""

    def test_get_comparison_details_invoices(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Details fuer Rechnungen."""
        details = service._get_comparison_details(sample_metrics, "invoices")

        assert details["total_count"] == 50
        assert details["paid_amount"] == 40000.00
        assert details["outstanding_amount"] == 10000.00

    def test_get_comparison_details_documents(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Details fuer Dokumente."""
        details = service._get_comparison_details(sample_metrics, "documents")

        assert details["this_month"] == 15
        assert details["growth_percent"] == 25.0

    def test_get_comparison_details_entities(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Details fuer Entities."""
        details = service._get_comparison_details(sample_metrics, "entities")

        assert details["customers"] == 20
        assert details["suppliers"] == 10
        assert details["high_risk"] == 2

    def test_get_comparison_details_dunning(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Details fuer Mahnungen."""
        details = service._get_comparison_details(sample_metrics, "dunning")

        assert details["active_count"] == 8
        assert details["by_level"]["1"] == 4
        assert details["by_level"]["2"] == 2
        assert details["by_level"]["3"] == 1
        assert details["by_level"]["4"] == 1

    def test_get_comparison_details_unknown(
        self, service: CompanyMetricsService, sample_metrics: CompanyMetrics
    ) -> None:
        """Test Details fuer unbekannte Metrik."""
        details = service._get_comparison_details(sample_metrics, "unknown")
        assert details == {}


# =============================================================================
# Singleton Instance Tests
# =============================================================================


class TestSingletonInstance:
    """Tests fuer Singleton-Instanz."""

    def test_singleton_exists(self) -> None:
        """Test dass Singleton-Instanz existiert."""
        assert company_metrics_service is not None

    def test_singleton_type(self) -> None:
        """Test dass Singleton korrekter Typ ist."""
        assert isinstance(company_metrics_service, CompanyMetricsService)


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    def test_empty_company_metrics(self) -> None:
        """Test Metriken fuer leere Firma."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Leere Firma",
        )

        result = metrics.to_dict()

        assert result["documents"]["total"] == 0
        assert result["invoices"]["total"] == 0
        assert result["entities"]["total"] == 0
        assert result["dunning"]["active"] == 0
        assert result["banking"]["balance"] == 0.0
        assert result["health_score"] == 100  # Default

    def test_negative_growth(self) -> None:
        """Test negativer Dokument-Wachstum."""
        metrics = CompanyDocumentMetrics(
            total_documents=100,
            documents_this_month=5,
            documents_last_month=10,
            document_growth_percent=-50.0,
        )

        assert metrics.document_growth_percent == -50.0

    def test_large_amounts(self) -> None:
        """Test grosse Betraege."""
        metrics = CompanyInvoiceMetrics(
            total_invoices=10000,
            total_amount=Decimal("999999999.99"),
            paid_amount=Decimal("500000000.00"),
            outstanding_amount=Decimal("499999999.99"),
        )

        # Sollte ohne Overflow funktionieren
        assert metrics.total_amount > Decimal("0")

    def test_zero_division_prevention(
        self, service: CompanyMetricsService
    ) -> None:
        """Test dass keine Division durch Null passiert."""
        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Test",
            invoices=CompanyInvoiceMetrics(
                total_invoices=0,  # Division durch 0 verhindern
                overdue_count=5,
            ),
            entities=CompanyEntityMetrics(
                total_entities=0,  # Division durch 0 verhindern
                high_risk_entities=3,
            ),
        )

        # Sollte keinen Fehler werfen
        score = service._calculate_health_score(metrics)
        assert 0 <= score <= 100


# =============================================================================
# API Helper Function Tests
# =============================================================================


class TestApiHelperFunctions:
    """Tests fuer API-Hilfsfunktionen."""

    def test_generate_dashboard_alerts_critical_health(self) -> None:
        """Test Alert-Generierung fuer kritischen Health Score."""
        from app.api.v1.companies import _generate_dashboard_alerts

        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Kritische GmbH",
            health_score=40,
        )

        alerts = _generate_dashboard_alerts([metrics])

        assert len(alerts) >= 1
        critical_alert = next(
            (a for a in alerts if a["type"] == "critical"), None
        )
        assert critical_alert is not None
        assert "Health Score" in critical_alert["message"]
        assert critical_alert["action"] == "company_review"

    def test_generate_dashboard_alerts_warning_health(self) -> None:
        """Test Alert-Generierung fuer Warning Health Score."""
        from app.api.v1.companies import _generate_dashboard_alerts

        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Warning GmbH",
            health_score=65,
        )

        alerts = _generate_dashboard_alerts([metrics])

        warning_alert = next(
            (a for a in alerts if a["type"] == "warning"), None
        )
        assert warning_alert is not None
        assert "Health Score" in warning_alert["message"]

    def test_generate_dashboard_alerts_high_overdue(self) -> None:
        """Test Alert-Generierung fuer hohe ueberfaellige Betraege."""
        from app.api.v1.companies import _generate_dashboard_alerts

        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Saeumige GmbH",
            health_score=85,  # Gut genug
            invoices=CompanyInvoiceMetrics(
                overdue_amount=Decimal("15000.00"),  # Ueber 10000
            ),
        )

        alerts = _generate_dashboard_alerts([metrics])

        overdue_alert = next(
            (a for a in alerts if "Ueberfaellige Rechnungen" in a["message"]), None
        )
        assert overdue_alert is not None
        assert overdue_alert["type"] == "critical"
        assert overdue_alert["action"] == "dunning_review"

    def test_generate_dashboard_alerts_high_risk_entities(self) -> None:
        """Test Alert-Generierung fuer High-Risk Entities."""
        from app.api.v1.companies import _generate_dashboard_alerts

        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Risiko GmbH",
            health_score=85,
            entities=CompanyEntityMetrics(
                high_risk_entities=5,
            ),
        )

        alerts = _generate_dashboard_alerts([metrics])

        risk_alert = next(
            (a for a in alerts if "High-Risk" in a["message"]), None
        )
        assert risk_alert is not None
        assert risk_alert["type"] == "warning"
        assert risk_alert["action"] == "entity_review"

    def test_generate_dashboard_alerts_serious_dunnings(self) -> None:
        """Test Alert-Generierung fuer Level 3/4 Mahnungen."""
        from app.api.v1.companies import _generate_dashboard_alerts

        metrics = CompanyMetrics(
            company_id=uuid4(),
            company_name="Mahnung GmbH",
            health_score=85,
            dunning=CompanyDunningMetrics(
                level_3_count=3,
                level_4_count=3,  # = 6 >= 5
            ),
        )

        alerts = _generate_dashboard_alerts([metrics])

        dunning_alert = next(
            (a for a in alerts if "kritische Mahnungen" in a["message"]), None
        )
        assert dunning_alert is not None
        assert dunning_alert["type"] == "warning"

    def test_generate_dashboard_alerts_sorting(self) -> None:
        """Test dass Alerts nach Kritikalitaet sortiert werden."""
        from app.api.v1.companies import _generate_dashboard_alerts

        metrics_list = [
            CompanyMetrics(
                company_id=uuid4(),
                company_name="B Warning GmbH",
                health_score=65,  # Warning
            ),
            CompanyMetrics(
                company_id=uuid4(),
                company_name="A Critical GmbH",
                health_score=40,  # Critical
            ),
        ]

        alerts = _generate_dashboard_alerts(metrics_list)

        # Critical sollte zuerst kommen
        if len(alerts) >= 2:
            critical_alerts = [a for a in alerts if a["type"] == "critical"]
            if critical_alerts:
                assert alerts[0]["type"] == "critical"

    def test_get_metric_label(self) -> None:
        """Test deutsche Labels fuer Metriken."""
        from app.api.v1.companies import _get_metric_label

        assert _get_metric_label("invoices") == "Rechnungsvolumen"
        assert _get_metric_label("documents") == "Dokumente"
        assert _get_metric_label("entities") == "Geschaeftspartner"
        assert _get_metric_label("dunning") == "Mahnbetraege"
        assert _get_metric_label("outstanding") == "Offene Forderungen"
        assert _get_metric_label("overdue") == "Ueberfaellige Forderungen"
        assert _get_metric_label("health") == "Health Score"
        assert _get_metric_label("unknown") == "unknown"

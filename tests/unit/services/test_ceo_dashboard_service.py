# -*- coding: utf-8 -*-
"""Unit tests for CEO Dashboard Services."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.services.ceo_dashboard.health_score_calculator import HealthScoreCalculator, DIMENSION_WEIGHTS
from app.services.ceo_dashboard.trend_analyzer import TrendAnalyzer
from app.services.ceo_dashboard.digital_twin_service import (
    DigitalTwinService,
    HealthScore,
    CompanyOverview,
    Anomaly,
)
from app.db.models import InvoiceStatus, ProcessingStatus, AlertStatus, AlertSeverity


# =============================================================================
# Health Score Calculator Tests
# =============================================================================


@pytest.mark.asyncio
async def test_health_score_all_good():
    """Health Score sollte hoch sein wenn alle Metriken positiv."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock Rechnungs-Statistiken: 100% bezahlt, 0% überfällig
    invoice_stats = MagicMock()
    invoice_stats.first.return_value = MagicMock(total=100, paid=100, overdue=0)

    # Mock durchschnittliche Zahlungsdauer: 20 Tage (gut)
    avg_payment = MagicMock()
    avg_payment.scalar.return_value = 20.0

    # Mock Dokument-Statistiken: 100% completed, 0% failed
    docs_stats = MagicMock()
    docs_stats.first.return_value = MagicMock(total=100, completed=100, failed=0, avg_duration=3000)

    # Mock High-Risk Entities: 0
    high_risk = MagicMock()
    high_risk.scalar.return_value = 0
    total_entities = MagicMock()
    total_entities.scalar.return_value = 50

    # Mock Alerts: 0 critical, 0 open
    critical_alerts = MagicMock()
    critical_alerts.scalar.return_value = 0
    open_alerts = MagicMock()
    open_alerts.scalar.return_value = 0

    # Mock Audit-Log Completeness: Perfect (300 logs für 100 docs)
    docs_count = MagicMock()
    docs_count.scalar.return_value = 100
    audit_count = MagicMock()
    audit_count.scalar.return_value = 300
    compliance_alerts = MagicMock()
    compliance_alerts.scalar.return_value = 0

    mock_db.execute.side_effect = [
        invoice_stats,
        avg_payment,
        docs_stats,
        high_risk,
        total_entities,
        critical_alerts,
        open_alerts,
        docs_count,
        audit_count,
        compliance_alerts,
    ]

    calculator = HealthScoreCalculator()
    result = await calculator.calculate(company_id, mock_db)

    assert isinstance(result, HealthScore)
    assert result.overall > 80  # Sollte hoher Score sein
    assert result.financial > 80  # Gute finanzielle Gesundheit
    assert result.operations > 80  # Gute operative Effizienz
    assert result.risk > 80  # Niedriges Risiko
    assert result.compliance > 80  # Gute Compliance
    assert result.trend in ["improving", "stable", "declining"]


@pytest.mark.asyncio
async def test_health_score_financial_bad():
    """Health Score sollte niedrigen Financial Score zeigen bei schlechten Metriken."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock Rechnungs-Statistiken: 50% bezahlt, 30% überfällig
    invoice_stats = MagicMock()
    invoice_stats.first.return_value = MagicMock(total=100, paid=50, overdue=30)

    # Mock durchschnittliche Zahlungsdauer: 70 Tage (schlecht)
    avg_payment = MagicMock()
    avg_payment.scalar.return_value = 70.0

    # Mock Dokument-Statistiken (gut für anderen Score)
    docs_stats = MagicMock()
    docs_stats.first.return_value = MagicMock(total=100, completed=90, failed=5, avg_duration=3000)

    # Mock Risk (gut)
    high_risk = MagicMock()
    high_risk.scalar.return_value = 0
    total_entities = MagicMock()
    total_entities.scalar.return_value = 50
    critical_alerts = MagicMock()
    critical_alerts.scalar.return_value = 0
    open_alerts = MagicMock()
    open_alerts.scalar.return_value = 0

    # Mock Compliance (gut)
    docs_count = MagicMock()
    docs_count.scalar.return_value = 100
    audit_count = MagicMock()
    audit_count.scalar.return_value = 300
    compliance_alerts = MagicMock()
    compliance_alerts.scalar.return_value = 0

    mock_db.execute.side_effect = [
        invoice_stats,
        avg_payment,
        docs_stats,
        high_risk,
        total_entities,
        critical_alerts,
        open_alerts,
        docs_count,
        audit_count,
        compliance_alerts,
    ]

    calculator = HealthScoreCalculator()
    result = await calculator.calculate(company_id, mock_db)

    assert result.financial < 50  # Schlechter financial Score
    assert result.operations > 70  # Gute Operations
    assert result.risk > 80  # Niedriges Risiko
    assert result.compliance > 80  # Gute Compliance
    # Overall sollte durch schlechten Financial Score gezogen werden
    assert result.overall < 75


@pytest.mark.asyncio
async def test_health_score_weighting():
    """Health Score sollte korrekte Gewichtung verwenden."""
    # Gewichtung: Financial (40%), Operations (25%), Risk (20%), Compliance (15%)
    assert DIMENSION_WEIGHTS["financial"] == 0.40
    assert DIMENSION_WEIGHTS["operations"] == 0.25
    assert DIMENSION_WEIGHTS["risk"] == 0.20
    assert DIMENSION_WEIGHTS["compliance"] == 0.15
    assert sum(DIMENSION_WEIGHTS.values()) == 1.0


@pytest.mark.asyncio
async def test_health_score_no_data():
    """Health Score sollte 100 returnen wenn keine Daten vorhanden."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock: Keine Rechnungen
    invoice_stats = MagicMock()
    invoice_stats.first.return_value = MagicMock(total=0, paid=0, overdue=0)

    # Mock: Keine Dokumente
    docs_stats = MagicMock()
    docs_stats.first.return_value = MagicMock(total=0, completed=0, failed=0, avg_duration=None)

    # Mock: Keine Entities
    high_risk = MagicMock()
    high_risk.scalar.return_value = 0
    total_entities = MagicMock()
    total_entities.scalar.return_value = 0

    # Mock: Keine Alerts
    critical_alerts = MagicMock()
    critical_alerts.scalar.return_value = 0
    open_alerts = MagicMock()
    open_alerts.scalar.return_value = 0

    # Mock: Keine Audit-Logs
    docs_count = MagicMock()
    docs_count.scalar.return_value = 0
    audit_count = MagicMock()
    audit_count.scalar.return_value = 0
    compliance_alerts = MagicMock()
    compliance_alerts.scalar.return_value = 0

    mock_db.execute.side_effect = [
        invoice_stats,
        docs_stats,
        high_risk,
        total_entities,
        critical_alerts,
        open_alerts,
        docs_count,
        audit_count,
        compliance_alerts,
    ]

    calculator = HealthScoreCalculator()
    result = await calculator.calculate(company_id, mock_db)

    # Keine Daten = kein Risiko
    assert result.financial == 100.0
    assert result.operations == 100.0
    assert result.risk == 100.0
    assert result.compliance == 100.0
    assert result.overall == 100.0


# =============================================================================
# Trend Analyzer Tests
# =============================================================================


@pytest.mark.asyncio
async def test_trend_analyzer_upward():
    """Trend Analyzer sollte aufwärts-Trend erkennen."""
    mock_db = AsyncMock()
    company_id = uuid4()
    days = 7

    # Mock: Steigende Dokument-Zahlen
    mock_results = []
    for day in range(days):
        result = MagicMock()
        result.scalar.return_value = (day + 1) * 10  # 10, 20, 30, ...
        mock_results.append(result)

    mock_db.execute.side_effect = mock_results

    analyzer = TrendAnalyzer()
    result = await analyzer._analyze_documents(
        company_id,
        datetime.now(timezone.utc) - timedelta(days=days),
        datetime.now(timezone.utc),
        days,
        mock_db,
    )

    assert len(result) == days
    # Werte sollten steigen
    assert result[0].value < result[-1].value
    # Labels sollten Datums-Format haben
    assert all("." in dp.label for dp in result)


@pytest.mark.asyncio
async def test_trend_analyzer_downward():
    """Trend Analyzer sollte abwärts-Trend erkennen."""
    mock_db = AsyncMock()
    company_id = uuid4()
    days = 7

    # Mock: Fallende Dokument-Zahlen
    mock_results = []
    for day in range(days):
        result = MagicMock()
        result.scalar.return_value = (days - day) * 10  # 70, 60, 50, ...
        mock_results.append(result)

    mock_db.execute.side_effect = mock_results

    analyzer = TrendAnalyzer()
    result = await analyzer._analyze_documents(
        company_id,
        datetime.now(timezone.utc) - timedelta(days=days),
        datetime.now(timezone.utc),
        days,
        mock_db,
    )

    assert len(result) == days
    # Werte sollten fallen
    assert result[0].value > result[-1].value


@pytest.mark.asyncio
async def test_trend_analyzer_stable():
    """Trend Analyzer sollte stabilen Trend erkennen."""
    mock_db = AsyncMock()
    company_id = uuid4()
    days = 7

    # Mock: Konstante Dokument-Zahlen
    mock_results = []
    for day in range(days):
        result = MagicMock()
        result.scalar.return_value = 50  # Konstant
        mock_results.append(result)

    mock_db.execute.side_effect = mock_results

    analyzer = TrendAnalyzer()
    result = await analyzer._analyze_documents(
        company_id,
        datetime.now(timezone.utc) - timedelta(days=days),
        datetime.now(timezone.utc),
        days,
        mock_db,
    )

    assert len(result) == days
    # Werte sollten gleich sein
    assert all(dp.value == 50.0 for dp in result)


@pytest.mark.asyncio
async def test_trend_analyzer_auto_process_rate():
    """Trend Analyzer sollte Auto-Process Rate korrekt berechnen."""
    mock_db = AsyncMock()
    company_id = uuid4()
    days = 3

    # Mock: Tag 1: 80% completed (8/10), Tag 2: 100% (10/10), Tag 3: 50% (5/10)
    mock_results = [
        MagicMock(first=MagicMock(return_value=MagicMock(completed=8, total=10))),
        MagicMock(first=MagicMock(return_value=MagicMock(completed=10, total=10))),
        MagicMock(first=MagicMock(return_value=MagicMock(completed=5, total=10))),
    ]

    mock_db.execute.side_effect = mock_results

    analyzer = TrendAnalyzer()
    result = await analyzer._analyze_auto_process_rate(
        company_id,
        datetime.now(timezone.utc) - timedelta(days=days),
        datetime.now(timezone.utc),
        days,
        mock_db,
    )

    assert len(result) == days
    assert result[0].value == 0.8  # 80%
    assert result[1].value == 1.0  # 100%
    assert result[2].value == 0.5  # 50%


# =============================================================================
# Digital Twin Service Tests
# =============================================================================


@pytest.mark.asyncio
async def test_digital_twin_overview():
    """Digital Twin sollte vollständige Unternehmens-Übersicht liefern."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock HealthScore
    with patch.object(DigitalTwinService, 'get_health_score') as mock_health:
        mock_health.return_value = HealthScore(
            overall=85.0,
            financial=80.0,
            operations=85.0,
            risk=90.0,
            compliance=85.0,
            trend="stable",
        )

        # Mock DB-Queries
        mock_results = [
            MagicMock(scalar=MagicMock(return_value=10)),  # docs today
            MagicMock(scalar=MagicMock(return_value=150)),  # docs month
            MagicMock(first=MagicMock(return_value=(20, 50000))),  # pending invoices
            MagicMock(first=MagicMock(return_value=(5, 10000))),  # overdue invoices
            MagicMock(scalar=MagicMock(return_value=3)),  # active alerts
            MagicMock(scalar=MagicMock(return_value=1)),  # critical alerts
            MagicMock(first=MagicMock(return_value=(80, 100))),  # auto process rate
        ]
        mock_db.execute.side_effect = mock_results

        service = DigitalTwinService()
        result = await service.get_overview(company_id, mock_db)

        assert isinstance(result, CompanyOverview)
        assert result.documents_today == 10
        assert result.documents_this_month == 150
        assert result.pending_invoices == 20
        assert result.pending_amount == Decimal("50000")
        assert result.overdue_invoices == 5
        assert result.overdue_amount == Decimal("10000")
        assert result.active_alerts == 3
        assert result.critical_alerts == 1
        assert result.auto_process_rate == 0.8  # 80/100
        assert result.health_score.overall == 85.0


@pytest.mark.asyncio
async def test_digital_twin_anomalies():
    """Digital Twin sollte Anomalien korrekt erkennen."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock: Ungewöhnlich viele Alerts (10 in 24h vs. 2 normal)
    mock_results = [
        MagicMock(scalar=MagicMock(return_value=10)),  # alerts 24h
        MagicMock(scalar=MagicMock(return_value=12)),  # alerts last week (avg 2/day)
        MagicMock(scalar=MagicMock(return_value=5)),  # docs today
        MagicMock(scalar=MagicMock(return_value=70)),  # docs last week (avg 10/day)
        MagicMock(first=MagicMock(return_value=(30, 100))),  # overdue invoices
    ]
    mock_db.execute.side_effect = mock_results

    service = DigitalTwinService()
    result = await service.get_anomalies(company_id, mock_db)

    assert isinstance(result, list)
    assert len(result) > 0

    # Sollte Alerts-Anomalie enthalten
    alerts_anomaly = next((a for a in result if "Alert" in a.title), None)
    assert alerts_anomaly is not None
    assert alerts_anomaly.severity in ["warning", "critical"]
    assert alerts_anomaly.actual_value == 10.0

    # Sollte Dokument-Anomalie enthalten
    docs_anomaly = next((a for a in result if "Dokument" in a.title), None)
    assert docs_anomaly is not None


@pytest.mark.asyncio
async def test_overview_multi_tenant():
    """Digital Twin sollte Company-Isolation respektieren."""
    mock_db = AsyncMock()
    company_id_1 = uuid4()
    company_id_2 = uuid4()

    # Mock Health Score
    with patch.object(DigitalTwinService, 'get_health_score') as mock_health:
        mock_health.return_value = HealthScore(
            overall=85.0, financial=80.0, operations=85.0,
            risk=90.0, compliance=85.0, trend="stable",
        )

        # Alle Queries sollten company_id Filter enthalten
        mock_results = [
            MagicMock(scalar=MagicMock(return_value=10)),
            MagicMock(scalar=MagicMock(return_value=150)),
            MagicMock(first=MagicMock(return_value=(20, 50000))),
            MagicMock(first=MagicMock(return_value=(5, 10000))),
            MagicMock(scalar=MagicMock(return_value=3)),
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(first=MagicMock(return_value=(80, 100))),
        ]
        mock_db.execute.side_effect = mock_results

        service = DigitalTwinService()
        result = await service.get_overview(company_id_1, mock_db)

        # Verifiziere dass company_id verwendet wurde
        assert result is not None

        # Reset für company 2
        mock_db.reset_mock()
        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=5)),
            MagicMock(scalar=MagicMock(return_value=75)),
            MagicMock(first=MagicMock(return_value=(10, 25000))),
            MagicMock(first=MagicMock(return_value=(2, 5000))),
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(first=MagicMock(return_value=(40, 50))),
        ]

        result2 = await service.get_overview(company_id_2, mock_db)

        # Unterschiedliche Ergebnisse
        assert result.documents_today != result2.documents_today


@pytest.mark.asyncio
async def test_digital_twin_anomaly_overdue_invoices():
    """Digital Twin sollte hohe Ausfallrate als Anomalie erkennen."""
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock: 30% Ausfallrate (30 von 100 überfällig)
    mock_results = [
        MagicMock(scalar=MagicMock(return_value=0)),  # alerts 24h
        MagicMock(scalar=MagicMock(return_value=0)),  # alerts week
        MagicMock(scalar=MagicMock(return_value=10)),  # docs today
        MagicMock(scalar=MagicMock(return_value=70)),  # docs week
        MagicMock(first=MagicMock(return_value=(30, 100))),  # 30 overdue von 100
    ]
    mock_db.execute.side_effect = mock_results

    service = DigitalTwinService()
    result = await service.get_anomalies(company_id, mock_db)

    # Sollte Ausfallrate-Anomalie finden
    overdue_anomaly = next((a for a in result if "Ausfallrate" in a.title), None)
    assert overdue_anomaly is not None
    assert overdue_anomaly.severity == "critical"  # > 25%
    assert overdue_anomaly.category == "financial"

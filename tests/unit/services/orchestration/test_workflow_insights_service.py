# -*- coding: utf-8 -*-
"""
Unit Tests fuer WorkflowInsightsService.

Testet die ECHTE API des Services (app.services.orchestration.workflow_insights_service):

- Batch-Genehmigungs-Vorschlaege (suggest_batch_approvals)
- Bottleneck-Erkennung (detect_bottlenecks)
- Automatisierungs-Vorschlaege (suggest_automation)
- Veraltete Items (detect_stale_items)
- Workload-Verteilung (analyze_workload_distribution)
- Kombinierte Analyse (check_all_workflow_insights)
- Datenklassen WorkflowInsight / WorkflowCheckResult und ihre Konvertierung

PHASE 6: Proaktive Intelligenz
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.orchestration.workflow_insights_service import (
    WorkflowInsightsService,
    WorkflowInsightType,
    WorkflowInsight,
    WorkflowCheckResult,
    BottleneckSeverity,
    get_workflow_insights_service,
)
from app.services.orchestration.proactive_insights_service import (
    InsightType,
    InsightPriority,
    ProactiveInsight,
)


# =============================================================================
# Helfer fuer DB-Mocks
# =============================================================================

def _result_with_rows(rows):
    """Erzeugt ein Mock-Result, dessen fetchall() die uebergebenen Zeilen liefert."""
    result = MagicMock()
    result.fetchall = MagicMock(return_value=rows)
    result.fetchone = MagicMock(return_value=rows[0] if rows else None)
    result.scalar = MagicMock(return_value=0)
    return result


def _doc_mock(*, total_amount=Decimal("100.00"), document_type="invoice"):
    """Erzeugt ein Document-Mock mit den vom Service genutzten Attributen."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.total_amount = total_amount
    doc.document_type = document_type
    return doc


def _approval_mock(*, document_id=None, created_at=None):
    """Erzeugt ein ApprovalRequest-Mock."""
    approval = MagicMock()
    approval.id = uuid4()
    approval.document_id = document_id or uuid4()
    approval.created_at = created_at or (datetime.now(timezone.utc) - timedelta(days=1))
    return approval


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service():
    """Frische Service-Instanz fuer jeden Test."""
    return WorkflowInsightsService()


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
def sample_user_id():
    """Sample User ID."""
    return uuid4()


# =============================================================================
# Factory / Singleton Tests (ECHTES Verhalten)
# =============================================================================

class TestServiceConstruction:
    """Tests fuer Konstruktion und Factory-Funktion.

    Der Service ist KEIN __new__-Singleton: jeder Konstruktoraufruf liefert
    eine neue Instanz. Nur die Factory cached eine Modul-Singleton-Instanz.
    """

    def test_direct_construction_yields_new_instances(self):
        """Direkter Konstruktoraufruf liefert jeweils eine NEUE Instanz."""
        instance1 = WorkflowInsightsService()
        instance2 = WorkflowInsightsService()

        assert instance1 is not instance2

    def test_factory_returns_cached_instance(self):
        """Factory-Funktion gibt eine gecachte (gleiche) Instanz zurueck."""
        instance1 = get_workflow_insights_service()
        instance2 = get_workflow_insights_service()

        assert instance1 is instance2
        assert isinstance(instance1, WorkflowInsightsService)

    def test_default_thresholds_set(self, service):
        """Service initialisiert sinnvolle Default-Schwellwerte."""
        assert service._batch_threshold == 3
        assert service._bottleneck_threshold == 5
        assert service._stale_threshold_hours == 48
        assert service._overload_threshold == 10


# =============================================================================
# WorkflowInsightType Tests
# =============================================================================

class TestWorkflowInsightType:
    """Tests fuer WorkflowInsightType Enum."""

    def test_insight_types_defined(self):
        """Alle InsightTypes sind definiert."""
        assert WorkflowInsightType.BATCH_APPROVAL.value == "batch_approval"
        assert WorkflowInsightType.BOTTLENECK.value == "bottleneck"
        assert WorkflowInsightType.AUTOMATION_POSSIBLE.value == "automation_possible"
        assert WorkflowInsightType.DELEGATION_SUGGESTED.value == "delegation_suggested"
        assert WorkflowInsightType.STALE_ITEMS.value == "stale_items"
        assert WorkflowInsightType.WORKLOAD_IMBALANCE.value == "workload_imbalance"

    def test_bottleneck_severity_levels(self):
        """BottleneckSeverity hat die erwarteten Stufen."""
        assert BottleneckSeverity.CRITICAL.value == "critical"
        assert BottleneckSeverity.HIGH.value == "high"
        assert BottleneckSeverity.MEDIUM.value == "medium"
        assert BottleneckSeverity.LOW.value == "low"


# =============================================================================
# WorkflowCheckResult Tests
# =============================================================================

class TestWorkflowCheckResult:
    """Tests fuer WorkflowCheckResult Dataclass."""

    def test_defaults(self):
        """WorkflowCheckResult hat sinnvolle Defaults."""
        result = WorkflowCheckResult(
            insight_type=WorkflowInsightType.BATCH_APPROVAL,
            title="Test Workflow",
            message="Test Message",
        )

        assert result.detail == ""
        assert result.priority == "medium"
        assert result.affected_items == []
        assert result.suggested_action is None
        assert result.potential_time_savings_minutes is None

    def test_to_insight_conversion(self):
        """WorkflowCheckResult kann zu ProactiveInsight konvertiert werden.

        Beschreibt das KORREKTE Vertrags-Verhalten: Konvertierung liefert einen
        gueltigen ProactiveInsight mit Empfehlungs-Typ. Der Code verletzt dies,
        weil InsightType.SUGGESTION nicht existiert (siehe xfail-reason).
        """
        result = WorkflowCheckResult(
            insight_type=WorkflowInsightType.BATCH_APPROVAL,
            title="Batch-Genehmigung moeglich",
            message="3 Rechnungen vom gleichen Lieferanten koennen gemeinsam genehmigt werden.",
            detail="Lieferant ABC: 3 offene Rechnungen ueber insgesamt 1.550 EUR.",
            priority="high",
            affected_items=[uuid4(), uuid4(), uuid4()],
            suggested_action="batch_approve",
            potential_time_savings_minutes=15,
        )

        insight = result.to_insight()

        assert isinstance(insight, ProactiveInsight)
        assert insight.priority.value == "high"
        assert insight.title == "Batch-Genehmigung moeglich"


# =============================================================================
# WorkflowInsight Tests (aktiv genutzte Datenklasse)
# =============================================================================

class TestWorkflowInsight:
    """Tests fuer WorkflowInsight Dataclass und ihre Konvertierung."""

    def test_defaults(self):
        """WorkflowInsight hat sinnvolle Defaults."""
        insight = WorkflowInsight(
            insight_type=WorkflowInsightType.BOTTLENECK,
            title="Stau",
            description="Beschreibung",
        )

        assert insight.affected_users == []
        assert insight.affected_documents == []
        assert insight.pending_count == 0
        assert insight.avg_wait_time_hours == 0.0
        assert insight.potential_time_savings_hours == 0.0
        assert insight.metadata == {}

    def test_batch_approval_maps_to_optimization(self):
        """BATCH_APPROVAL wird als Optimierung mit mittlerer Prioritaet abgebildet."""
        insight = WorkflowInsight(
            insight_type=WorkflowInsightType.BATCH_APPROVAL,
            title="Batch-Genehmigung: Lieferant ABC",
            description="3 Rechnungen warten auf Genehmigung.",
            pending_count=3,
        )

        proactive = insight.to_proactive_insight()

        assert isinstance(proactive, ProactiveInsight)
        assert proactive.insight_type == InsightType.OPTIMIZATION
        assert proactive.priority == InsightPriority.MEDIUM
        assert proactive.title == "Batch-Genehmigung: Lieferant ABC"
        assert proactive.source_rule == "workflow_batch_approval"

    def test_bottleneck_maps_to_warning_high(self):
        """BOTTLENECK wird als Warnung mit hoher Prioritaet abgebildet."""
        insight = WorkflowInsight(
            insight_type=WorkflowInsightType.BOTTLENECK,
            title="Genehmigungsstau",
            description="25 Dokumente warten.",
            pending_count=25,
            avg_wait_time_hours=50.0,
        )

        proactive = insight.to_proactive_insight()

        assert proactive.insight_type == InsightType.WARNING
        assert proactive.priority == InsightPriority.HIGH

    def test_detail_text_contains_pending_count(self):
        """Detail-Text enthaelt Anzahl wartender Elemente und Wartezeit."""
        insight = WorkflowInsight(
            insight_type=WorkflowInsightType.STALE_ITEMS,
            title="Veraltet",
            description="Beschreibung",
            pending_count=4,
            avg_wait_time_hours=48.0,
        )

        detail = insight._generate_detail()

        assert "Wartende Elemente: 4" in detail
        # 48h >= 24h -> Tage-Darstellung
        assert "Tage" in detail


# =============================================================================
# Batch Approval Tests
# =============================================================================

class TestBatchApprovalSuggestions:
    """Tests fuer Batch-Genehmigungs-Vorschlaege (suggest_batch_approvals)."""

    @pytest.mark.asyncio
    async def test_suggest_batch_approvals_by_supplier(
        self, service, mock_db, sample_company_id
    ):
        """Schlaegt Batch-Genehmigung fuer gleichen Lieferanten vor.

        3 Rechnungen desselben Lieferanten (>= _batch_threshold=3) ergeben
        genau einen BATCH_APPROVAL-Insight (Optimierung).
        """
        rows = [
            (_approval_mock(), _doc_mock(total_amount=Decimal("500.00")), "Lieferant ABC"),
            (_approval_mock(), _doc_mock(total_amount=Decimal("750.00")), "Lieferant ABC"),
            (_approval_mock(), _doc_mock(total_amount=Decimal("300.00")), "Lieferant ABC"),
        ]
        mock_db.execute = AsyncMock(return_value=_result_with_rows(rows))

        insights = await service.suggest_batch_approvals(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)
        # Genau eine Lieferanten-Gruppe mit 3 Items -> 1 Insight
        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.OPTIMIZATION
        assert "Lieferant ABC" in insights[0].title

    @pytest.mark.asyncio
    async def test_no_batch_for_too_few_items(
        self, service, mock_db, sample_company_id
    ):
        """Keine Batch-Empfehlung bei zu wenigen Items (unter Schwellwert)."""
        rows = [
            (_approval_mock(), _doc_mock(), "Einzellieferant"),
            (_approval_mock(), _doc_mock(), "Einzellieferant"),
        ]
        mock_db.execute = AsyncMock(return_value=_result_with_rows(rows))

        insights = await service.suggest_batch_approvals(
            db=mock_db,
            company_id=sample_company_id,
        )

        # Nur 2 Items (< Schwellwert 3) -> keine Batch-Empfehlung
        assert insights == []

    @pytest.mark.asyncio
    async def test_user_specific_batch(
        self, service, mock_db, sample_company_id, sample_user_id
    ):
        """Batch-Vorschlag respektiert optionale user_id ohne Fehler."""
        rows = [
            (_approval_mock(), _doc_mock(), "Lieferant X"),
            (_approval_mock(), _doc_mock(), "Lieferant X"),
            (_approval_mock(), _doc_mock(), "Lieferant X"),
        ]
        mock_db.execute = AsyncMock(return_value=_result_with_rows(rows))

        insights = await service.suggest_batch_approvals(
            db=mock_db,
            company_id=sample_company_id,
            user_id=sample_user_id,
        )

        assert isinstance(insights, list)
        assert len(insights) == 1

    @pytest.mark.asyncio
    async def test_empty_queue_returns_empty(
        self, service, mock_db, sample_company_id
    ):
        """Leere Queue ergibt keine Vorschlaege."""
        mock_db.execute = AsyncMock(return_value=_result_with_rows([]))

        insights = await service.suggest_batch_approvals(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Bottleneck Detection Tests
# =============================================================================

class TestBottleneckDetection:
    """Tests fuer Bottleneck-Erkennung (detect_bottlenecks)."""

    @pytest.mark.asyncio
    async def test_detect_bottlenecks(self, service, mock_db, sample_company_id):
        """Erkennt Engpaesse bei Benutzern oberhalb des Schwellwerts.

        Erste DB-Abfrage liefert User-Statistiken, zweite den Benutzernamen.
        Ein User mit 25 wartenden Genehmigungen (>= _bottleneck_threshold=5)
        ergibt einen BOTTLENECK-Insight (Warnung, hohe Prioritaet).
        """
        assignee_id = uuid4()
        now = datetime.now(timezone.utc)
        oldest = now - timedelta(days=3)

        stats_result = MagicMock()
        # (assignee_id, pending_count, oldest, avg_wait_hours)
        stats_result.fetchall = MagicMock(
            return_value=[(assignee_id, 25, oldest, 50.0)]
        )

        user_result = MagicMock()
        # (email, full_name)
        user_result.fetchone = MagicMock(
            return_value=("user1@test.com", "Max Mustermann")
        )

        mock_db.execute = AsyncMock(side_effect=[stats_result, user_result])

        insights = await service.detect_bottlenecks(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)
        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.WARNING
        assert insights[0].priority == InsightPriority.HIGH
        assert "Max Mustermann" in insights[0].title

    @pytest.mark.asyncio
    async def test_no_bottleneck_below_threshold(
        self, service, mock_db, sample_company_id
    ):
        """Kein Bottleneck unterhalb des Schwellwerts (5)."""
        assignee_id = uuid4()
        now = datetime.now(timezone.utc)

        stats_result = MagicMock()
        # nur 3 wartende -> unter Schwellwert 5
        stats_result.fetchall = MagicMock(
            return_value=[(assignee_id, 3, now - timedelta(hours=2), 2.0)]
        )
        mock_db.execute = AsyncMock(return_value=stats_result)

        insights = await service.detect_bottlenecks(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Automation Suggestion Tests
# =============================================================================

class TestAutomationSuggestions:
    """Tests fuer Automatisierungs-Vorschlaege (suggest_automation)."""

    @pytest.mark.asyncio
    async def test_suggest_automation_for_recurring(
        self, service, mock_db, sample_company_id
    ):
        """Schlaegt Automatisierung vor, wenn ein Lieferant haeufig genehmigt
        wurde UND aktuell mehrere Dokumente warten.
        """
        entity_id = uuid4()

        history_result = MagicMock()
        # (entity_id, entity_name, approved_count, avg_amount, max_amount)
        history_result.fetchall = MagicMock(
            return_value=[
                (entity_id, "Lieferant Auto", 12, Decimal("200.00"), Decimal("500.00"))
            ]
        )

        pending_result = MagicMock()
        pending_result.scalar = MagicMock(return_value=4)  # 4 wartende >= 3

        mock_db.execute = AsyncMock(side_effect=[history_result, pending_result])

        insights = await service.suggest_automation(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)
        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.RECOMMENDATION
        assert "Lieferant Auto" in insights[0].title

    @pytest.mark.asyncio
    async def test_no_automation_without_pending(
        self, service, mock_db, sample_company_id
    ):
        """Keine Automatisierung, wenn keine wartenden Dokumente vorliegen."""
        entity_id = uuid4()

        history_result = MagicMock()
        history_result.fetchall = MagicMock(
            return_value=[
                (entity_id, "Lieferant Y", 15, Decimal("100.00"), Decimal("300.00"))
            ]
        )

        pending_result = MagicMock()
        pending_result.scalar = MagicMock(return_value=0)

        mock_db.execute = AsyncMock(side_effect=[history_result, pending_result])

        insights = await service.suggest_automation(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_no_automation_for_empty_history(
        self, service, mock_db, sample_company_id
    ):
        """Keine Automatisierung ohne historische Muster."""
        history_result = MagicMock()
        history_result.fetchall = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=history_result)

        insights = await service.suggest_automation(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Stale Items Tests
# =============================================================================

class TestStaleItemsDetection:
    """Tests fuer veraltete Items (detect_stale_items)."""

    @pytest.mark.asyncio
    async def test_detect_stale_items(self, service, mock_db, sample_company_id):
        """Erkennt veraltete, wartende Items und gruppiert nach Alter.

        2 Items aelter als 7 Tage -> ein STALE_ITEMS-Insight (very_old).
        """
        now = datetime.now(timezone.utc)
        rows = [
            (_approval_mock(created_at=now - timedelta(days=9)), "rechnung1.pdf"),
            (_approval_mock(created_at=now - timedelta(days=8)), "rechnung2.pdf"),
        ]
        mock_db.execute = AsyncMock(return_value=_result_with_rows(rows))

        insights = await service.detect_stale_items(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)
        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.WARNING
        assert "7 Tagen" in insights[0].title

    @pytest.mark.asyncio
    async def test_no_stale_items_when_empty(
        self, service, mock_db, sample_company_id
    ):
        """Keine veralteten Items -> leere Liste."""
        mock_db.execute = AsyncMock(return_value=_result_with_rows([]))

        insights = await service.detect_stale_items(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Workload Distribution Tests
# =============================================================================

class TestWorkloadDistribution:
    """Tests fuer Workload-Verteilung (analyze_workload_distribution)."""

    @pytest.mark.asyncio
    async def test_analyze_workload_distribution_detects_imbalance(
        self, service, mock_db, sample_company_id
    ):
        """Erkennt Ungleichgewicht: ein User stark ueberlastet, einer kaum belastet.

        Counts [50, 5, 30]: avg=28.3, max=50 (>2*avg? nein, 56.6) ...
        Damit max > 2*avg UND min < 0.5*avg erfuellt ist, nutzen wir [100, 5, 15].
        """
        u1, u2, u3 = uuid4(), uuid4(), uuid4()

        workload_result = MagicMock()
        # (assignee_id, pending_count)
        workload_result.fetchall = MagicMock(
            return_value=[(u1, 100), (u2, 5), (u3, 15)]
        )

        names_result = MagicMock()
        # (id, full_name, email)
        names_result.fetchall = MagicMock(
            return_value=[
                (u1, "Ueberlastet User", "u1@test.com"),
                (u2, "Frei User", "u2@test.com"),
            ]
        )

        mock_db.execute = AsyncMock(side_effect=[workload_result, names_result])

        insights = await service.analyze_workload_distribution(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)
        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.INFORMATION
        assert insights[0].priority == InsightPriority.LOW

    @pytest.mark.asyncio
    async def test_no_imbalance_for_single_user(
        self, service, mock_db, sample_company_id
    ):
        """Bei weniger als 2 Benutzern keine Imbalance-Analyse."""
        workload_result = MagicMock()
        workload_result.fetchall = MagicMock(return_value=[(uuid4(), 50)])
        mock_db.execute = AsyncMock(return_value=workload_result)

        insights = await service.analyze_workload_distribution(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_no_imbalance_for_balanced_team(
        self, service, mock_db, sample_company_id
    ):
        """Gleichmaessig verteilte Last erzeugt keine Imbalance-Warnung."""
        workload_result = MagicMock()
        workload_result.fetchall = MagicMock(
            return_value=[(uuid4(), 10), (uuid4(), 11), (uuid4(), 9)]
        )
        mock_db.execute = AsyncMock(return_value=workload_result)

        insights = await service.analyze_workload_distribution(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Combined Analysis Tests
# =============================================================================

class TestCombinedWorkflowAnalysis:
    """Tests fuer kombinierte Workflow-Analyse (check_all_workflow_insights)."""

    @pytest.mark.asyncio
    async def test_check_all_workflow_insights_empty(
        self, service, mock_db, sample_company_id, sample_user_id
    ):
        """Kombinierte Analyse ohne Daten liefert leere Liste."""
        empty_result = MagicMock()
        empty_result.fetchall = MagicMock(return_value=[])
        empty_result.fetchone = MagicMock(return_value=None)
        empty_result.scalar = MagicMock(return_value=0)
        mock_db.execute = AsyncMock(return_value=empty_result)

        insights = await service.check_all_workflow_insights(
            db=mock_db,
            company_id=sample_company_id,
            user_id=sample_user_id,
        )

        assert isinstance(insights, list)
        assert insights == []

    @pytest.mark.asyncio
    async def test_check_all_aggregates_and_sorts(
        self, service, mock_db, sample_company_id
    ):
        """Kombinierte Analyse aggregiert Teil-Insights und sortiert nach Prioritaet.

        Wir liefern fuer JEDE Teil-Abfrage dieselben (leeren) Bottleneck-Daten,
        ausser fuer Batch: 3 Rechnungen desselben Lieferanten -> 1 Insight.
        check_all ruft mehrere Sub-Checks parallel auf; ein gemeinsamer
        Result-Mock muss alle genutzten Result-Zugriffe bedienen.
        """
        batch_rows = [
            (_approval_mock(), _doc_mock(), "Lieferant Z"),
            (_approval_mock(), _doc_mock(), "Lieferant Z"),
            (_approval_mock(), _doc_mock(), "Lieferant Z"),
        ]

        generic = MagicMock()
        # fetchall liefert die Batch-Rows (von Batch genutzt), alle anderen
        # Sub-Checks interpretieren dieselben Rows ueber ihre eigene Logik;
        # entscheidend ist, dass mind. ein Insight entsteht und sortiert wird.
        generic.fetchall = MagicMock(return_value=batch_rows)
        generic.fetchone = MagicMock(return_value=("e@test.com", "Name"))
        generic.scalar = MagicMock(return_value=0)
        mock_db.execute = AsyncMock(return_value=generic)

        insights = await service.check_all_workflow_insights(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)
        # Mindestens der Batch-Insight muss enthalten sein.
        assert any(i.source_rule == "workflow_batch_approval" for i in insights)
        # Sortierung: Prioritaeten in nicht-absteigender Reihenfolge
        order = {
            InsightPriority.CRITICAL: 0,
            InsightPriority.HIGH: 1,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 3,
        }
        priorities = [order[i.priority] for i in insights]
        assert priorities == sorted(priorities)


# =============================================================================
# Workflow Summary Tests
# =============================================================================

class TestWorkflowSummary:
    """Tests fuer die Zusammenfassung (get_workflow_summary)."""

    @pytest.mark.asyncio
    async def test_summary_structure_for_empty(
        self, service, mock_db, sample_company_id
    ):
        """Zusammenfassung hat die erwartete Struktur (auch bei 0 Insights)."""
        empty_result = MagicMock()
        empty_result.fetchall = MagicMock(return_value=[])
        empty_result.fetchone = MagicMock(return_value=None)
        empty_result.scalar = MagicMock(return_value=0)
        mock_db.execute = AsyncMock(return_value=empty_result)

        summary = await service.get_workflow_summary(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert summary["total_count"] == 0
        assert summary["by_type"] == {}
        assert summary["by_priority"] == {}


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_batch_handles_db_error_gracefully(
        self, service, mock_db, sample_company_id
    ):
        """suggest_batch_approvals behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.suggest_batch_approvals(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_bottleneck_handles_db_error_gracefully(
        self, service, mock_db, sample_company_id
    ):
        """detect_bottlenecks behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_bottlenecks(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_automation_handles_db_error_gracefully(
        self, service, mock_db, sample_company_id
    ):
        """suggest_automation behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.suggest_automation(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_stale_handles_db_error_gracefully(
        self, service, mock_db, sample_company_id
    ):
        """detect_stale_items behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_stale_items(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_workload_handles_db_error_gracefully(
        self, service, mock_db, sample_company_id
    ):
        """analyze_workload_distribution behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.analyze_workload_distribution(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

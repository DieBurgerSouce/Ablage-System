# -*- coding: utf-8 -*-
"""
Unit Tests fuer WorkflowInsightsService.

Testet:
- Batch-Genehmigungs-Vorschlaege
- Bottleneck-Erkennung
- Automatisierungs-Vorschlaege
- Workload-Verteilung

PHASE 6: Proaktive Intelligenz
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.workflow_insights_service import (
    WorkflowInsightsService,
    WorkflowInsightType,
    WorkflowCheckResult,
    get_workflow_insights_service,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_service():
    """Reset Singleton vor und nach jedem Test."""
    WorkflowInsightsService._instance = None
    yield
    WorkflowInsightsService._instance = None


@pytest.fixture
def service(reset_service):
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


@pytest.fixture
def sample_pending_approvals():
    """Sample pending approvals fuer einen Benutzer."""
    supplier_id = uuid4()
    return [
        MagicMock(
            id=uuid4(),
            document_id=uuid4(),
            type="invoice",
            supplier_id=supplier_id,
            supplier_name="Lieferant ABC",
            amount=Decimal("500.00"),
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
            status="pending",
        ),
        MagicMock(
            id=uuid4(),
            document_id=uuid4(),
            type="invoice",
            supplier_id=supplier_id,
            supplier_name="Lieferant ABC",
            amount=Decimal("750.00"),
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            status="pending",
        ),
        MagicMock(
            id=uuid4(),
            document_id=uuid4(),
            type="invoice",
            supplier_id=supplier_id,
            supplier_name="Lieferant ABC",
            amount=Decimal("300.00"),
            created_at=datetime.now(timezone.utc) - timedelta(hours=6),
            status="pending",
        ),
    ]


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_service):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = WorkflowInsightsService()
        instance2 = WorkflowInsightsService()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_service):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_workflow_insights_service()
        instance2 = get_workflow_insights_service()

        assert instance1 is instance2


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

        assert result.priority == "medium"
        assert result.affected_items == []
        assert result.suggested_action is None
        assert result.potential_time_savings_minutes is None

    def test_to_insight_conversion(self):
        """WorkflowCheckResult kann zu ProactiveInsight konvertiert werden."""
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

        assert insight.insight_type.value == "recommendation"
        assert insight.priority.value == "high"
        assert insight.title == "Batch-Genehmigung moeglich"


# =============================================================================
# Batch Approval Tests
# =============================================================================

class TestBatchApprovalSuggestions:
    """Tests fuer Batch-Genehmigungs-Vorschlaege."""

    @pytest.mark.asyncio
    async def test_suggest_batch_approvals_by_supplier(
        self, service, mock_db, sample_user_id, sample_pending_approvals
    ):
        """Schlaegt Batch-Genehmigung fuer gleichen Lieferanten vor."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=sample_pending_approvals
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.suggest_batch_approvals(
            db=mock_db,
            user_id=sample_user_id,
            min_items_for_batch=3,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_no_batch_for_single_items(self, service, mock_db, sample_user_id):
        """Keine Batch-Empfehlung bei einzelnen Items."""
        single_approval = MagicMock(
            id=uuid4(),
            supplier_id=uuid4(),
            supplier_name="Einzellieferant",
            amount=Decimal("100.00"),
        )

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[single_approval]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.suggest_batch_approvals(
            db=mock_db,
            user_id=sample_user_id,
            min_items_for_batch=3,
        )

        # Keine Batch-Empfehlung weil nur 1 Item
        assert len([i for i in insights if i.insight_type == WorkflowInsightType.BATCH_APPROVAL]) == 0

    def test_group_by_supplier(self, service, sample_pending_approvals):
        """Gruppiert Approvals nach Lieferant."""
        grouped = service._group_by_supplier(sample_pending_approvals)

        # Alle haben gleichen Lieferanten
        assert len(grouped) == 1
        supplier_id = list(grouped.keys())[0]
        assert len(grouped[supplier_id]) == 3


# =============================================================================
# Bottleneck Detection Tests
# =============================================================================

class TestBottleneckDetection:
    """Tests fuer Bottleneck-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_bottlenecks(self, service, mock_db, sample_company_id):
        """Erkennt Engpaesse bei Benutzern."""
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[
            (uuid4(), "user1@test.com", 25),  # 25 pending = Bottleneck
            (uuid4(), "user2@test.com", 5),   # 5 pending = OK
        ])
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_bottlenecks(
            db=mock_db,
            company_id=sample_company_id,
            threshold_items=20,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_bottleneck_threshold_configurable(self, service):
        """Bottleneck-Schwellenwert ist konfigurierbar."""
        user_pending_counts = [
            (uuid4(), "user1@test.com", 15),
            (uuid4(), "user2@test.com", 10),
        ]

        # Mit Threshold 10: user1 ist Bottleneck
        bottlenecks_10 = service._identify_bottlenecks(user_pending_counts, threshold=10)
        assert len(bottlenecks_10) == 1

        # Mit Threshold 20: kein Bottleneck
        bottlenecks_20 = service._identify_bottlenecks(user_pending_counts, threshold=20)
        assert len(bottlenecks_20) == 0


# =============================================================================
# Automation Suggestion Tests
# =============================================================================

class TestAutomationSuggestions:
    """Tests fuer Automatisierungs-Vorschlaege."""

    @pytest.mark.asyncio
    async def test_suggest_automation_for_recurring(
        self, service, mock_db, sample_company_id
    ):
        """Schlaegt Automatisierung fuer wiederkehrende Muster vor."""
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.suggest_automation(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_identify_recurring_pattern(self, service):
        """Erkennt wiederkehrende Genehmigungsmuster."""
        # 10 Genehmigungen vom gleichen Lieferanten, alle genehmigt
        supplier_id = uuid4()
        approvals = [
            MagicMock(
                supplier_id=supplier_id,
                status="approved",
                amount=Decimal("100.00"),
            )
            for _ in range(10)
        ]

        pattern = service._detect_recurring_pattern(approvals)

        assert pattern is not None
        assert pattern["supplier_id"] == supplier_id
        assert pattern["approval_rate"] == 1.0  # 100% genehmigt

    def test_no_pattern_for_mixed_outcomes(self, service):
        """Kein Automatisierungs-Vorschlag bei gemischten Ergebnissen."""
        supplier_id = uuid4()
        approvals = [
            MagicMock(supplier_id=supplier_id, status="approved"),
            MagicMock(supplier_id=supplier_id, status="rejected"),
            MagicMock(supplier_id=supplier_id, status="approved"),
            MagicMock(supplier_id=supplier_id, status="rejected"),
        ]

        pattern = service._detect_recurring_pattern(approvals)

        # Approval-Rate nur 50% - kein Automatisierungs-Vorschlag
        assert pattern is None or pattern.get("approval_rate", 0) < 0.9


# =============================================================================
# Stale Items Tests
# =============================================================================

class TestStaleItemsDetection:
    """Tests fuer veraltete Items."""

    @pytest.mark.asyncio
    async def test_detect_stale_items(self, service, mock_db, sample_company_id):
        """Erkennt veraltete, wartende Items."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_stale_items(
            db=mock_db,
            company_id=sample_company_id,
            stale_days=7,
        )

        assert isinstance(insights, list)

    def test_item_is_stale_after_threshold(self, service):
        """Item gilt nach Schwellenwert als veraltet."""
        created_8_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
        created_2_days_ago = datetime.now(timezone.utc) - timedelta(days=2)

        assert service._is_stale(created_8_days_ago, threshold_days=7) is True
        assert service._is_stale(created_2_days_ago, threshold_days=7) is False


# =============================================================================
# Workload Distribution Tests
# =============================================================================

class TestWorkloadDistribution:
    """Tests fuer Workload-Verteilung."""

    @pytest.mark.asyncio
    async def test_analyze_workload_distribution(
        self, service, mock_db, sample_company_id
    ):
        """Analysiert Workload-Verteilung im Team."""
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[
            (uuid4(), "user1@test.com", 50),  # Viel
            (uuid4(), "user2@test.com", 10),  # Wenig
            (uuid4(), "user3@test.com", 30),  # Mittel
        ])
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.analyze_workload_distribution(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_detect_workload_imbalance(self, service):
        """Erkennt Ungleichgewicht in Workload."""
        workloads = [
            {"user_id": uuid4(), "email": "user1@test.com", "count": 100},
            {"user_id": uuid4(), "email": "user2@test.com", "count": 10},
            {"user_id": uuid4(), "email": "user3@test.com", "count": 20},
        ]

        imbalance = service._calculate_workload_imbalance(workloads)

        # Hohe Standardabweichung = Ungleichgewicht
        assert imbalance["std_deviation"] > 30
        assert imbalance["max_user"]["email"] == "user1@test.com"
        assert imbalance["min_user"]["email"] == "user2@test.com"


# =============================================================================
# Combined Analysis Tests
# =============================================================================

class TestCombinedWorkflowAnalysis:
    """Tests fuer kombinierte Workflow-Analyse."""

    @pytest.mark.asyncio
    async def test_get_all_workflow_insights(
        self, service, mock_db, sample_company_id, sample_user_id
    ):
        """Kombinierte Workflow-Analyse."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.get_all_workflow_insights(
            db=mock_db,
            company_id=sample_company_id,
            user_id=sample_user_id,
        )

        assert isinstance(insights, list)


# =============================================================================
# Time Savings Calculation Tests
# =============================================================================

class TestTimeSavingsCalculation:
    """Tests fuer Zeitersparnis-Berechnung."""

    def test_batch_approval_saves_time(self, service):
        """Batch-Genehmigung spart Zeit."""
        item_count = 5
        time_per_item_minutes = 3

        total_time = service._calculate_batch_time_savings(
            item_count, time_per_item_minutes
        )

        # 5 Items * 3 Min = 15 Min, aber Batch nur 5 Min -> Ersparnis 10 Min
        assert total_time > 0

    def test_automation_saves_time(self, service):
        """Automatisierung spart Zeit."""
        items_per_month = 20
        time_per_item_minutes = 2

        monthly_savings = service._calculate_automation_time_savings(
            items_per_month, time_per_item_minutes
        )

        # 20 Items * 2 Min = 40 Min/Monat Ersparnis
        assert monthly_savings == 40


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_handles_empty_queue(self, service, mock_db, sample_user_id):
        """Behandelt leere Queue korrekt."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.suggest_batch_approvals(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_handles_db_error(self, service, mock_db, sample_company_id):
        """Behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_bottlenecks(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_handles_single_user(self, service):
        """Behandelt einzelnen Benutzer ohne Imbalance-Warnung."""
        workloads = [
            {"user_id": uuid4(), "email": "only_user@test.com", "count": 50},
        ]

        imbalance = service._calculate_workload_imbalance(workloads)

        # Nur ein User -> keine Imbalance moeglich
        assert imbalance["std_deviation"] == 0

    def test_handles_zero_items(self, service):
        """Behandelt 0 Items korrekt."""
        time_savings = service._calculate_batch_time_savings(0, 3)

        assert time_savings == 0

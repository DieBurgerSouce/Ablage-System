"""Tests fuer den Workflow Engine Service.

Testet:
- Regel-Evaluation
- Bedingungspruefung
- Aktions-Ausfuehrung
- Eskalation

WICHTIG: Diese Tests sind an die tatsaechliche Service-API angepasst.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.workflow import workflow_engine_service
from app.services.workflow.workflow_engine_service import (
    WorkflowEngineService,
    WorkflowCondition,
    WorkflowAction,
)
from app.db.models import ApprovalRule, ApprovalRequest


class TestConditionMatching:
    """Tests fuer Bedingungspruefung.

    Die _matches_conditions Methode ist synchron und kann direkt getestet werden.
    """

    def setup_method(self) -> None:
        self.service = WorkflowEngineService(db=MagicMock())

    def test_amount_greater_than_match(self) -> None:
        """amount_greater_than Bedingung matcht."""
        entity = MagicMock()
        entity.amount = Decimal("10000")
        conditions = {"amount_greater_than": 5000}

        result = self.service._matches_conditions(entity, conditions)

        assert result is True

    def test_amount_greater_than_no_match(self) -> None:
        """amount_greater_than Bedingung matcht nicht."""
        entity = MagicMock()
        entity.amount = Decimal("3000")
        conditions = {"amount_greater_than": 5000}

        result = self.service._matches_conditions(entity, conditions)

        assert result is False

    def test_amount_less_than_match(self) -> None:
        """amount_less_than Bedingung matcht."""
        entity = MagicMock()
        entity.amount = Decimal("100")
        conditions = {"amount_less_than": 500}

        result = self.service._matches_conditions(entity, conditions)

        assert result is True

    def test_amount_less_than_no_match(self) -> None:
        """amount_less_than Bedingung matcht nicht."""
        entity = MagicMock()
        entity.amount = Decimal("600")
        conditions = {"amount_less_than": 500}

        result = self.service._matches_conditions(entity, conditions)

        assert result is False

    def test_category_match(self) -> None:
        """category Bedingung matcht."""
        entity = MagicMock()
        entity.category = "IT"
        conditions = {"category": "IT"}

        result = self.service._matches_conditions(entity, conditions)

        assert result is True

    def test_category_no_match(self) -> None:
        """category Bedingung matcht nicht."""
        entity = MagicMock()
        entity.category = "Marketing"
        conditions = {"category": "IT"}

        result = self.service._matches_conditions(entity, conditions)

        assert result is False

    def test_category_in_match(self) -> None:
        """category_in Bedingung matcht."""
        entity = MagicMock()
        entity.category = "IT"
        conditions = {"category_in": ["IT", "HR", "Finance"]}

        result = self.service._matches_conditions(entity, conditions)

        assert result is True

    def test_category_in_no_match(self) -> None:
        """category_in Bedingung matcht nicht."""
        entity = MagicMock()
        entity.category = "Marketing"
        conditions = {"category_in": ["IT", "HR", "Finance"]}

        result = self.service._matches_conditions(entity, conditions)

        assert result is False

    def test_supplier_risk_match(self) -> None:
        """supplier_risk_level Bedingung matcht."""
        entity = MagicMock()
        entity.supplier_risk_level = "high"
        conditions = {"supplier_risk_level": "high"}

        result = self.service._matches_conditions(entity, conditions)

        assert result is True

    def test_multiple_conditions_all_match(self) -> None:
        """Alle Bedingungen muessen matchen."""
        entity = MagicMock()
        entity.amount = Decimal("10000")
        entity.category = "IT"

        conditions = {
            "amount_greater_than": 5000,
            "category": "IT",
        }

        result = self.service._matches_conditions(entity, conditions)

        assert result is True

    def test_multiple_conditions_partial_match(self) -> None:
        """Bei Teilmatch matcht nicht."""
        entity = MagicMock()
        entity.amount = Decimal("10000")
        entity.category = "Marketing"

        conditions = {
            "amount_greater_than": 5000,  # matcht
            "category": "IT",  # matcht nicht
        }

        result = self.service._matches_conditions(entity, conditions)

        assert result is False

    def test_empty_conditions_always_match(self) -> None:
        """Leere Bedingungen matchen immer."""
        entity = MagicMock()
        conditions = {}

        result = self.service._matches_conditions(entity, conditions)

        assert result is True

    def test_amount_uses_total_amount_fallback(self) -> None:
        """Falls amount nicht vorhanden, wird total_amount genutzt."""
        entity = MagicMock()
        entity.amount = None
        entity.total_amount = Decimal("15000")
        conditions = {"amount_greater_than": 10000}

        result = self.service._matches_conditions(entity, conditions)

        assert result is True


class TestRuleEvaluation:
    """Tests fuer Regel-Evaluation."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> WorkflowEngineService:
        return WorkflowEngineService(db=mock_db)

    @pytest.mark.asyncio
    async def test_evaluate_entity_matches_rule(
        self, service: WorkflowEngineService
    ) -> None:
        """Entity die Regeln matcht loest Aktionen aus."""
        company_id = uuid4()
        entity_type = "invoice"
        entity_id = uuid4()

        # Mock rule that matches
        mock_rule = MagicMock(spec=ApprovalRule)
        mock_rule.id = uuid4()
        mock_rule.name = "High Value Invoice"
        mock_rule.conditions = {"amount_greater_than": 5000}
        mock_rule.approval_chain = [{"role": "manager", "required": True}]

        # Mock entity
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.amount = Decimal("10000")  # > 5000

        with patch.object(
            workflow_engine_service, "logger"
        ), patch.object(
            service, "_get_matching_rules", return_value=[mock_rule]
        ), patch.object(
            service, "_get_entity", return_value=mock_entity
        ), patch.object(
            service, "_execute_rule_actions", return_value=[uuid4()]
        ) as mock_execute:

            result = await service.evaluate_entity(
                company_id, entity_type, entity_id, "created"
            )

            mock_execute.assert_called_once()
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_evaluate_entity_no_matching_rules(
        self, service: WorkflowEngineService
    ) -> None:
        """Entity ohne passende Regeln loest keine Aktionen aus."""
        company_id = uuid4()
        entity_type = "invoice"
        entity_id = uuid4()

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.amount = Decimal("1000")  # < 5000

        mock_rule = MagicMock(spec=ApprovalRule)
        mock_rule.id = uuid4()
        mock_rule.name = "High Value"
        mock_rule.conditions = {"amount_greater_than": 5000}
        mock_rule.approval_chain = [{"role": "manager", "required": True}]

        with patch.object(
            workflow_engine_service, "logger"
        ), patch.object(
            service, "_get_matching_rules", return_value=[mock_rule]
        ), patch.object(
            service, "_get_entity", return_value=mock_entity
        ), patch.object(
            service, "_execute_rule_actions", return_value=[]
        ) as mock_execute:

            result = await service.evaluate_entity(
                company_id, entity_type, entity_id, "created"
            )

            # _execute_rule_actions should NOT be called weil Bedingung nicht matcht
            mock_execute.assert_not_called()
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_evaluate_entity_not_found(
        self, service: WorkflowEngineService
    ) -> None:
        """Wenn Entity nicht gefunden wird, leere Liste zurueck."""
        company_id = uuid4()
        entity_type = "invoice"
        entity_id = uuid4()

        mock_rule = MagicMock(spec=ApprovalRule)
        mock_rule.conditions = {"amount_greater_than": 5000}

        with patch.object(
            workflow_engine_service, "logger"
        ), patch.object(
            service, "_get_matching_rules", return_value=[mock_rule]
        ), patch.object(
            service, "_get_entity", return_value=None
        ):

            result = await service.evaluate_entity(
                company_id, entity_type, entity_id, "created"
            )

            assert result == []


class TestApprovalRequestCreation:
    """Tests fuer Genehmigungsanfrage-Erstellung."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> WorkflowEngineService:
        return WorkflowEngineService(db=mock_db)

    @pytest.mark.asyncio
    async def test_execute_rule_actions_creates_request(
        self, service: WorkflowEngineService, mock_db: AsyncMock
    ) -> None:
        """_execute_rule_actions erstellt ApprovalRequest."""
        company_id = uuid4()
        entity_id = uuid4()

        entity = MagicMock()
        entity.id = entity_id
        entity.amount = Decimal("15000")

        rule = MagicMock(spec=ApprovalRule)
        rule.id = uuid4()
        rule.name = "Test Rule"
        rule.approval_chain = [{"role": "manager", "required": True}]
        rule.sla_hours = 48
        rule.escalation_after_hours = 72

        with patch.object(
            service, "_create_approval_request", return_value=uuid4()
        ) as mock_create:
            result = await service._execute_rule_actions(
                company_id, entity, "invoice", entity_id, rule
            )

            mock_create.assert_called_once()
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_execute_rule_actions_no_chain(
        self, service: WorkflowEngineService, mock_db: AsyncMock
    ) -> None:
        """Ohne approval_chain wird kein Request erstellt."""
        company_id = uuid4()
        entity_id = uuid4()

        entity = MagicMock()
        entity.id = entity_id

        rule = MagicMock(spec=ApprovalRule)
        rule.id = uuid4()
        rule.approval_chain = None  # Keine Chain

        result = await service._execute_rule_actions(
            company_id, entity, "invoice", entity_id, rule
        )

        assert result == []


class TestRuleManagement:
    """Tests fuer Regel-Verwaltung."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> WorkflowEngineService:
        return WorkflowEngineService(db=mock_db)

    @pytest.mark.asyncio
    async def test_create_rule(
        self, service: WorkflowEngineService, mock_db: AsyncMock
    ) -> None:
        """Regel wird erstellt."""
        company_id = uuid4()

        rule = await service.create_rule(
            company_id=company_id,
            name="High Value Invoice Approval",
            entity_types=["invoice"],
            conditions={"amount_greater_than": Decimal("10000")},
            approval_chain=[{"role": "manager", "required": True}],
        )

        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        assert isinstance(rule, ApprovalRule)
        assert rule.name == "High Value Invoice Approval"
        assert rule.company_id == company_id


class TestServiceInitialization:
    """Tests fuer Service-Initialisierung."""

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Service kann mit AsyncSession initialisiert werden."""
        mock_db = AsyncMock()
        service = WorkflowEngineService(mock_db)

        assert service.db is mock_db

    @pytest.mark.asyncio
    async def test_service_methods_exist(self) -> None:
        """Service hat alle erwarteten Methoden."""
        mock_db = AsyncMock()
        service = WorkflowEngineService(mock_db)

        # Public methods
        assert hasattr(service, "evaluate_entity")
        assert hasattr(service, "create_rule")
        assert hasattr(service, "approve_step")
        assert hasattr(service, "reject_step")
        assert hasattr(service, "escalate_request")

        # Private methods
        assert hasattr(service, "_matches_conditions")
        assert hasattr(service, "_execute_rule_actions")
        assert hasattr(service, "_create_approval_request")
        assert hasattr(service, "_get_matching_rules")
        assert hasattr(service, "_get_entity")


class TestWorkflowConditionDataclass:
    """Tests fuer WorkflowCondition Dataclass."""

    def test_condition_creation(self) -> None:
        """WorkflowCondition kann erstellt werden."""
        condition = WorkflowCondition(
            field="amount",
            operator="gt",
            value=Decimal("5000"),
        )

        assert condition.field == "amount"
        assert condition.operator == "gt"
        assert condition.value == Decimal("5000")

    def test_condition_with_list_value(self) -> None:
        """WorkflowCondition mit Liste als Wert."""
        condition = WorkflowCondition(
            field="category",
            operator="in",
            value=["IT", "HR", "Finance"],
        )

        assert condition.field == "category"
        assert condition.operator == "in"
        assert condition.value == ["IT", "HR", "Finance"]


class TestWorkflowActionDataclass:
    """Tests fuer WorkflowAction Dataclass."""

    def test_action_creation(self) -> None:
        """WorkflowAction kann erstellt werden."""
        action = WorkflowAction(
            action_type="require_approval",
            approver_role="manager",
        )

        assert action.action_type == "require_approval"
        assert action.approver_role == "manager"

    def test_action_with_escalation(self) -> None:
        """WorkflowAction mit Eskalation."""
        action = WorkflowAction(
            action_type="escalate",
            escalate_to_role="director",
        )

        assert action.escalate_to_role == "director"

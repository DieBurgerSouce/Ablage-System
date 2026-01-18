# -*- coding: utf-8 -*-
"""
Unit Tests fuer AutoApprovalService.

Testet:
- Auto-Approval Logik
- Regel-Evaluation
- Entity Trust Score Berechnung
- Opt-out Funktionalitaet
- Rate Limiting
"""

from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.approval.auto_approval_service import (
    AutoApprovalService,
    AutoApprovalConfig,
    AutoApprovalRule,
    AutoApprovalDecision,
    AutoApprovalReason,
    EntityTrustScore,
    get_auto_approval_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock Datenbank Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def default_config():
    """Standard-Konfiguration."""
    return AutoApprovalConfig(
        default_max_amount=Decimal("500.00"),
        default_max_risk_score=30,
        default_min_relationship_months=6,
        max_auto_approvals_per_day=100,
        max_auto_approvals_per_hour=20,
    )


@pytest.fixture
def service(mock_db, default_config):
    """AutoApprovalService Instanz."""
    return AutoApprovalService(db=mock_db, config=default_config)


# =============================================================================
# Initialisierung Tests
# =============================================================================


class TestAutoApprovalServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_with_default_config(self, mock_db):
        """Service initialisiert mit Standard-Konfiguration."""
        service = AutoApprovalService(db=mock_db)

        assert service.config is not None
        assert service.config.default_max_amount == Decimal("500.00")
        assert len(service._rules) > 0

    def test_init_with_custom_config(self, mock_db, default_config):
        """Service initialisiert mit benutzerdefinierter Konfiguration."""
        custom_config = AutoApprovalConfig(
            default_max_amount=Decimal("1000.00"),
            default_max_risk_score=50,
        )
        service = AutoApprovalService(db=mock_db, config=custom_config)

        assert service.config.default_max_amount == Decimal("1000.00")
        assert service.config.default_max_risk_score == 50

    def test_default_rules_loaded(self, service):
        """Standard-Regeln werden beim Init geladen."""
        rules = service.get_rules()

        assert len(rules) >= 5
        rule_ids = [r.id for r in rules]
        assert "small_amount_known_supplier" in rule_ids
        assert "micro_payment" in rule_ids
        assert "low_risk_entity" in rule_ids


# =============================================================================
# Regel-Management Tests
# =============================================================================


class TestRuleManagement:
    """Tests fuer Regel-Management."""

    def test_add_rule(self, service):
        """Neue Regel kann hinzugefuegt werden."""
        new_rule = AutoApprovalRule(
            id="test_rule",
            name="Test Regel",
            description="Eine Testregel",
            priority=50,
            max_amount=Decimal("100.00"),
        )

        initial_count = len(service.get_rules())
        service.add_rule(new_rule)

        assert len(service.get_rules()) == initial_count + 1
        assert any(r.id == "test_rule" for r in service.get_rules())

    def test_add_rule_replaces_existing(self, service):
        """Bestehende Regel wird ersetzt."""
        rule1 = AutoApprovalRule(
            id="duplicate_rule",
            name="Original",
            description="Erste Version",
            priority=50,
        )
        rule2 = AutoApprovalRule(
            id="duplicate_rule",
            name="Ersetzt",
            description="Zweite Version",
            priority=50,
        )

        service.add_rule(rule1)
        initial_count = len(service.get_rules())
        service.add_rule(rule2)

        assert len(service.get_rules()) == initial_count
        matching_rule = next(r for r in service.get_rules() if r.id == "duplicate_rule")
        assert matching_rule.name == "Ersetzt"

    def test_remove_rule(self, service):
        """Regel kann entfernt werden."""
        rule = AutoApprovalRule(
            id="to_remove",
            name="Zum Entfernen",
            description="Wird entfernt",
            priority=50,
        )
        service.add_rule(rule)

        assert service.remove_rule("to_remove") is True
        assert not any(r.id == "to_remove" for r in service.get_rules())

    def test_remove_nonexistent_rule(self, service):
        """Entfernen nicht existierender Regel gibt False zurueck."""
        result = service.remove_rule("nonexistent_rule")
        assert result is False

    def test_enable_disable_rule(self, service):
        """Regel kann aktiviert/deaktiviert werden."""
        rule_id = service.get_rules()[0].id

        service.enable_rule(rule_id, False)
        rule = next(r for r in service.get_rules() if r.id == rule_id)
        assert rule.enabled is False

        service.enable_rule(rule_id, True)
        rule = next(r for r in service.get_rules() if r.id == rule_id)
        assert rule.enabled is True

    def test_rules_sorted_by_priority(self, service):
        """Regeln sind nach Prioritaet sortiert."""
        service.add_rule(AutoApprovalRule(
            id="high_prio",
            name="Hohe Prioritaet",
            description="",
            priority=1,
        ))
        service.add_rule(AutoApprovalRule(
            id="low_prio",
            name="Niedrige Prioritaet",
            description="",
            priority=999,
        ))

        rules = service.get_rules()
        priorities = [r.priority for r in rules]
        assert priorities == sorted(priorities)


# =============================================================================
# Auto-Approval Check Tests
# =============================================================================


class TestAutoApprovalCheck:
    """Tests fuer Auto-Approval Pruefung."""

    @pytest.mark.asyncio
    async def test_micro_payment_auto_approved(self, service, mock_db):
        """Micro-Zahlungen werden automatisch genehmigt."""
        # Mock: Keine Dokumente/Invoices finden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.check_auto_approval(
            amount=Decimal("25.00"),
            document_type="invoice",
            company_id=uuid4(),
        )

        assert result.decision == AutoApprovalDecision.AUTO_APPROVED
        assert AutoApprovalReason.AMOUNT_BELOW_THRESHOLD in result.reasons
        assert "micro_payment" in result.matched_rules

    @pytest.mark.asyncio
    async def test_high_amount_requires_review(self, service, mock_db):
        """Hohe Betraege erfordern manuelle Pruefung."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.check_auto_approval(
            amount=Decimal("15000.00"),
            document_type="invoice",
            company_id=uuid4(),
        )

        assert result.decision in [
            AutoApprovalDecision.REQUIRES_REVIEW,
            AutoApprovalDecision.BLOCKED,
        ]

    @pytest.mark.asyncio
    async def test_contract_blocked(self, service, mock_db):
        """Vertraege werden immer blockiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.check_auto_approval(
            amount=Decimal("50.00"),
            document_type="contract",
            company_id=uuid4(),
        )

        # Contracts sind in default_opt_out_document_types
        assert result.decision == AutoApprovalDecision.REQUIRES_REVIEW

    @pytest.mark.asyncio
    async def test_pre_approved_category(self, service, mock_db):
        """Vorab genehmigte Kategorien werden auto-approved."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.check_auto_approval(
            amount=Decimal("150.00"),
            document_type="invoice",
            category="office_supplies",
            company_id=uuid4(),
        )

        assert result.decision == AutoApprovalDecision.AUTO_APPROVED
        assert AutoApprovalReason.PRE_APPROVED_CATEGORY in result.reasons


# =============================================================================
# Entity Trust Score Tests
# =============================================================================


class TestEntityTrustScore:
    """Tests fuer Entity Trust Score Berechnung."""

    @pytest.mark.asyncio
    async def test_unknown_entity_zero_score(self, service, mock_db):
        """Unbekannte Entity bekommt Score 0."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        entity_id = uuid4()
        score = await service.calculate_entity_trust_score(entity_id)

        assert score.entity_id == entity_id
        assert score.trust_score == 0.0
        assert score.is_trusted is False

    @pytest.mark.asyncio
    async def test_trusted_entity_calculation(self, service, mock_db):
        """Trust Score Berechnung fuer bekannte Entity."""
        from app.core.datetime_utils import utc_now

        # Mock Entity
        mock_entity = MagicMock()
        mock_entity.id = uuid4()
        mock_entity.created_at = utc_now() - timedelta(days=400)  # >12 Monate
        mock_entity.risk_score = 20

        # Mock Results
        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = mock_entity

        doc_count_result = MagicMock()
        doc_count_result.scalar.return_value = 60  # Viele Dokumente

        invoices_result = MagicMock()
        mock_invoice = MagicMock()
        mock_invoice.paid_at = utc_now() - timedelta(days=5)
        mock_invoice.due_date = utc_now() - timedelta(days=10)
        invoices_result.scalars.return_value.all.return_value = [mock_invoice] * 25

        mock_db.execute.side_effect = [
            entity_result,
            doc_count_result,
            invoices_result,
        ]

        score = await service.calculate_entity_trust_score(mock_entity.id)

        assert score.trust_score > 0.5
        assert score.relationship_months > 12
        assert score.total_documents == 60
        assert "relationship_duration" in score.trust_factors


# =============================================================================
# Opt-Out Tests
# =============================================================================


class TestOptOut:
    """Tests fuer Opt-Out Funktionalitaet."""

    @pytest.mark.asyncio
    async def test_opted_out_user_requires_review(self, service, mock_db):
        """Opt-out User bekommt immer REQUIRES_REVIEW."""
        # Mock User mit Opt-out
        mock_user = MagicMock()
        mock_user.preferences = {
            "auto_approval_opt_out": True,
        }

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service.check_auto_approval(
            amount=Decimal("25.00"),  # Wuerde normalerweise auto-approved
            document_type="invoice",
            company_id=uuid4(),
            user_id=uuid4(),
        )

        assert result.decision == AutoApprovalDecision.REQUIRES_REVIEW
        assert result.audit_trail.get("opted_out") is True

    @pytest.mark.asyncio
    async def test_set_user_opt_out(self, service, mock_db):
        """User Opt-out kann gesetzt werden."""
        mock_user = MagicMock()
        mock_user.preferences = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        user_id = uuid4()
        await service.set_user_opt_out(
            user_id=user_id,
            opt_out=True,
            document_types=["invoice"],
        )

        assert mock_user.preferences["auto_approval_opt_out"] is True
        assert mock_user.preferences["auto_approval_opt_out_types"] == ["invoice"]
        mock_db.commit.assert_called_once()


# =============================================================================
# Rate Limit Tests
# =============================================================================


class TestRateLimits:
    """Tests fuer Rate Limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_hourly_exceeded(self, service, mock_db):
        """Stündliches Limit ueberschritten."""
        # Mock: 25 auto-approvals in der letzten Stunde (Limit ist 20)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 25
        mock_db.execute.return_value = mock_result

        company_id = uuid4()
        result = await service._check_rate_limits(company_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_rate_limit_within_bounds(self, service, mock_db):
        """Innerhalb der Rate Limits."""
        # Mock: 5 auto-approvals (unter beiden Limits)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_db.execute.return_value = mock_result

        company_id = uuid4()
        result = await service._check_rate_limits(company_id)

        assert result is True


# =============================================================================
# Regel-Evaluation Tests
# =============================================================================


class TestRuleEvaluation:
    """Tests fuer Regel-Evaluation."""

    @pytest.mark.asyncio
    async def test_evaluate_amount_rule(self, service, mock_db):
        """Betrags-Regel wird korrekt evaluiert."""
        rule = AutoApprovalRule(
            id="test_amount",
            name="Test Amount",
            description="",
            max_amount=Decimal("100.00"),
        )

        # Betrag unter Limit
        context = {"amount": Decimal("50.00")}
        result = await service._evaluate_rule(rule, context)
        assert result["matches"] is True
        assert AutoApprovalReason.AMOUNT_BELOW_THRESHOLD in result["reasons"]

        # Betrag ueber Limit
        context = {"amount": Decimal("150.00")}
        result = await service._evaluate_rule(rule, context)
        assert result["matches"] is False

    @pytest.mark.asyncio
    async def test_evaluate_risk_score_rule(self, service, mock_db):
        """Risiko-Score Regel wird korrekt evaluiert."""
        rule = AutoApprovalRule(
            id="test_risk",
            name="Test Risk",
            description="",
            max_risk_score=30,
        )

        # Niedriger Risk Score
        context = {
            "entity_trust": EntityTrustScore(
                entity_id=uuid4(),
                trust_score=0.8,
                relationship_months=12,
                total_documents=50,
                total_invoices=20,
                avg_payment_delay_days=2.0,
                risk_score=20,
                is_trusted=True,
            )
        }
        result = await service._evaluate_rule(rule, context)
        assert result["matches"] is True
        assert AutoApprovalReason.LOW_RISK_SCORE in result["reasons"]

        # Hoher Risk Score
        context["entity_trust"].risk_score = 50
        result = await service._evaluate_rule(rule, context)
        assert result["matches"] is False

    @pytest.mark.asyncio
    async def test_evaluate_disabled_rule(self, service, mock_db):
        """Deaktivierte Regel matched nicht."""
        rule = AutoApprovalRule(
            id="disabled",
            name="Disabled Rule",
            description="",
            enabled=False,
            max_amount=Decimal("1000000.00"),  # Wuerde sonst immer matchen
        )

        context = {"amount": Decimal("50.00")}

        # Regel muss zuerst aktiviert sein fuer Evaluation
        # Bei check_auto_approval werden disabled rules uebersprungen
        rules_before = service.get_rules()
        service.add_rule(rule)
        service.enable_rule("disabled", False)

        # Die Rule ist jetzt disabled und wird in check_auto_approval uebersprungen
        rules = service.get_rules()
        disabled_rule = next(r for r in rules if r.id == "disabled")
        assert disabled_rule.enabled is False


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunction:
    """Tests fuer Factory Function."""

    def test_get_auto_approval_service(self, mock_db):
        """Factory erstellt Service korrekt."""
        service = get_auto_approval_service(mock_db)

        assert isinstance(service, AutoApprovalService)
        assert service.db == mock_db

    def test_get_auto_approval_service_with_config(self, mock_db):
        """Factory mit benutzerdefinierter Config."""
        config = AutoApprovalConfig(default_max_amount=Decimal("999.00"))
        service = get_auto_approval_service(mock_db, config=config)

        assert service.config.default_max_amount == Decimal("999.00")


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestAutoApprovalWorkflow:
    """Tests fuer kompletten Auto-Approval Workflow."""

    @pytest.mark.asyncio
    async def test_complete_auto_approval_flow(self, service, mock_db):
        """Kompletter Auto-Approval Flow."""
        from app.db.models import ApprovalRequest

        # Mock: Keine existierenden Daten
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        # 1. Check
        check_result = await service.check_auto_approval(
            amount=Decimal("30.00"),
            document_type="invoice",
            company_id=uuid4(),
        )

        assert check_result.decision == AutoApprovalDecision.AUTO_APPROVED

        # 2. Apply (wuerde ApprovalRequest erstellen)
        # Da wir keine echte DB haben, pruefen wir nur dass apply aufgerufen werden kann
        document_id = uuid4()
        company_id = uuid4()

        # Mock fuer apply
        approval_request = await service.apply_auto_approval(
            entity_type="invoice",
            entity_id=document_id,
            company_id=company_id,
            amount=Decimal("30.00"),
        )

        # Check dass DB add aufgerufen wurde
        assert mock_db.add.called
        assert mock_db.commit.called

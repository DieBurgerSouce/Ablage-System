"""Tests fuer den ApprovalRuleService.

Testet:
- Regel-Erstellung (CRUD)
- Conditions-Evaluierung
- Rule Matching gegen Entity-Daten
- Default-Regeln
- Prioritaets-Sortierung
"""

import pytest
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalRule, ApprovalRuleType
from app.services.approval.approval_rule_service import (
    ApprovalRuleService,
    MatchedRule,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock-Datenbank-Session."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> ApprovalRuleService:
    """ApprovalRuleService mit Mock-DB."""
    return ApprovalRuleService(db=mock_db)


@pytest.fixture
def sample_rule() -> MagicMock:
    """Beispiel-Regel fuer Tests."""
    rule = MagicMock(spec=ApprovalRule)
    rule.id = uuid4()
    rule.company_id = uuid4()
    rule.name = "Rechnungen ueber 5000 EUR"
    rule.rule_type = ApprovalRuleType.AMOUNT_THRESHOLD
    rule.entity_types = ["invoice"]
    rule.conditions = {"amount_greater_than": 5000}
    rule.approval_chain = [
        {"step": 1, "type": "role", "value": "manager", "required": True}
    ]
    rule.priority = 100
    rule.is_active = True
    rule.sla_hours = 48
    return rule


@pytest.fixture
def sample_conditions() -> dict:
    """Beispiel-Bedingungen."""
    return {
        "amount_greater_than": 5000,
        "category_in": ["travel", "equipment"],
    }


# =============================================================================
# RULE CREATION TESTS
# =============================================================================

class TestRuleCreation:
    """Tests fuer Regel-Erstellung."""

    @pytest.mark.asyncio
    async def test_create_rule_basic(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Einfache Regel wird erstellt."""
        # Arrange
        company_id = uuid4()
        name = "Test-Regel"
        rule_type = ApprovalRuleType.AMOUNT_THRESHOLD
        entity_types = ["invoice"]
        conditions = {"amount_greater_than": 1000}
        approval_chain = [
            {"step": 1, "type": "role", "value": "manager", "required": True}
        ]
        created_by_id = uuid4()

        # Act
        rule = await service.create_rule(
            company_id=company_id,
            name=name,
            rule_type=rule_type,
            entity_types=entity_types,
            conditions=conditions,
            approval_chain=approval_chain,
            created_by_id=created_by_id,
        )

        # Assert
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_rule_with_escalation(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Regel mit Eskalations-Einstellungen wird erstellt."""
        company_id = uuid4()

        rule = await service.create_rule(
            company_id=company_id,
            name="Regel mit Eskalation",
            rule_type=ApprovalRuleType.CATEGORY,
            entity_types=["expense"],
            conditions={"category_in": ["travel"]},
            approval_chain=[
                {"step": 1, "type": "role", "value": "manager", "required": True}
            ],
            escalation_after_hours=24,
            escalation_to_role="director",
            sla_hours=48,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_rule_multi_step_chain(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Regel mit mehrstufiger Genehmiger-Kette wird erstellt."""
        company_id = uuid4()

        approval_chain = [
            {"step": 1, "type": "role", "value": "team_lead", "required": True},
            {"step": 2, "type": "role", "value": "manager", "required": True},
            {"step": 3, "type": "role", "value": "cfo", "required": True},
        ]

        rule = await service.create_rule(
            company_id=company_id,
            name="Grosse Betraege",
            rule_type=ApprovalRuleType.AMOUNT_THRESHOLD,
            entity_types=["invoice"],
            conditions={"amount_greater_than": 50000},
            approval_chain=approval_chain,
        )

        mock_db.add.assert_called_once()


# =============================================================================
# RULE RETRIEVAL TESTS
# =============================================================================

class TestRuleRetrieval:
    """Tests fuer Regel-Abfragen."""

    @pytest.mark.asyncio
    async def test_get_rule_found(
        self, service: ApprovalRuleService, mock_db: AsyncMock, sample_rule: MagicMock
    ) -> None:
        """Regel wird gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_rule
        mock_db.execute.return_value = mock_result

        result = await service.get_rule(sample_rule.id)

        assert result == sample_rule
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_rule_not_found(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Nicht existierende Regel gibt None zurueck."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_rule(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_rules_for_company(
        self, service: ApprovalRuleService, mock_db: AsyncMock, sample_rule: MagicMock
    ) -> None:
        """Alle Regeln einer Firma werden abgefragt."""
        company_id = sample_rule.company_id

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_rule]
        mock_db.execute.return_value = mock_result

        result = await service.get_rules_for_company(company_id)

        assert len(result) == 1
        assert result[0] == sample_rule

    @pytest.mark.asyncio
    async def test_get_rules_for_company_active_only(
        self, service: ApprovalRuleService, mock_db: AsyncMock, sample_rule: MagicMock
    ) -> None:
        """Nur aktive Regeln werden zurueckgegeben."""
        company_id = sample_rule.company_id

        inactive_rule = MagicMock(spec=ApprovalRule)
        inactive_rule.is_active = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_rule]  # Nur aktive
        mock_db.execute.return_value = mock_result

        result = await service.get_rules_for_company(company_id, active_only=True)

        assert len(result) == 1


# =============================================================================
# RULE UPDATE TESTS
# =============================================================================

class TestRuleUpdate:
    """Tests fuer Regel-Updates."""

    @pytest.mark.asyncio
    async def test_update_rule_name(
        self, service: ApprovalRuleService, mock_db: AsyncMock, sample_rule: MagicMock
    ) -> None:
        """Regelname wird aktualisiert."""
        with patch.object(service, "get_rule", return_value=sample_rule):
            result = await service.update_rule(
                sample_rule.id,
                name="Neuer Name"
            )

            assert sample_rule.name == "Neuer Name"
            mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_rule_conditions(
        self, service: ApprovalRuleService, mock_db: AsyncMock, sample_rule: MagicMock
    ) -> None:
        """Regelbedingungen werden aktualisiert."""
        new_conditions = {"amount_greater_than": 10000}

        with patch.object(service, "get_rule", return_value=sample_rule):
            result = await service.update_rule(
                sample_rule.id,
                conditions=new_conditions
            )

            assert sample_rule.conditions == new_conditions

    @pytest.mark.asyncio
    async def test_update_rule_not_found(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Update bei nicht existierender Regel gibt None zurueck."""
        with patch.object(service, "get_rule", return_value=None):
            result = await service.update_rule(uuid4(), name="Test")

            assert result is None

    @pytest.mark.asyncio
    async def test_update_rule_ignores_invalid_fields(
        self, service: ApprovalRuleService, mock_db: AsyncMock, sample_rule: MagicMock
    ) -> None:
        """Ungueltige Felder werden beim Update ignoriert."""
        with patch.object(service, "get_rule", return_value=sample_rule):
            result = await service.update_rule(
                sample_rule.id,
                name="Valid Name",
                invalid_field="Should be ignored"
            )

            # Sollte trotzdem funktionieren, nur valid field wird gesetzt
            assert sample_rule.name == "Valid Name"


# =============================================================================
# RULE DELETION TESTS
# =============================================================================

class TestRuleDeletion:
    """Tests fuer Regel-Loeschung."""

    @pytest.mark.asyncio
    async def test_delete_rule_success(
        self, service: ApprovalRuleService, mock_db: AsyncMock, sample_rule: MagicMock
    ) -> None:
        """Regel wird erfolgreich geloescht."""
        with patch.object(service, "get_rule", return_value=sample_rule):
            result = await service.delete_rule(sample_rule.id)

            assert result is True
            mock_db.delete.assert_awaited_once()
            mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_rule_not_found(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Loeschen nicht existierender Regel gibt False zurueck."""
        with patch.object(service, "get_rule", return_value=None):
            result = await service.delete_rule(uuid4())

            assert result is False
            mock_db.delete.assert_not_awaited()


# =============================================================================
# CONDITIONS EVALUATION TESTS
# =============================================================================

class TestConditionsEvaluation:
    """Tests fuer Bedingungspruefung."""

    def test_evaluate_empty_conditions_matches(
        self, service: ApprovalRuleService
    ) -> None:
        """Leere Bedingungen gelten als Match."""
        result = service._evaluate_conditions({}, {"amount": 1000})

        assert result["matches"] is True
        assert result["score"] == 1.0

    def test_evaluate_amount_greater_than_matches(
        self, service: ApprovalRuleService
    ) -> None:
        """amount_greater_than Bedingung trifft zu."""
        conditions = {"amount_greater_than": 5000}
        entity_data = {"amount": 6000}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is True
        assert "amount_greater_than" in result["matched"]

    def test_evaluate_amount_greater_than_not_matches(
        self, service: ApprovalRuleService
    ) -> None:
        """amount_greater_than Bedingung trifft nicht zu."""
        conditions = {"amount_greater_than": 5000}
        entity_data = {"amount": 3000}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is False

    def test_evaluate_amount_less_than_matches(
        self, service: ApprovalRuleService
    ) -> None:
        """amount_less_than Bedingung trifft zu."""
        conditions = {"amount_less_than": 1000}
        entity_data = {"amount": 500}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is True

    def test_evaluate_category_in_matches(
        self, service: ApprovalRuleService
    ) -> None:
        """category_in Bedingung trifft zu."""
        conditions = {"category_in": ["travel", "equipment", "supplies"]}
        entity_data = {"category": "travel"}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is True
        assert "category_in" in result["matched"]

    def test_evaluate_category_in_not_matches(
        self, service: ApprovalRuleService
    ) -> None:
        """category_in Bedingung trifft nicht zu."""
        conditions = {"category_in": ["travel", "equipment"]}
        entity_data = {"category": "office"}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is False

    def test_evaluate_category_not_in_matches(
        self, service: ApprovalRuleService
    ) -> None:
        """category_not_in Bedingung trifft zu."""
        conditions = {"category_not_in": ["restricted", "confidential"]}
        entity_data = {"category": "general"}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is True

    def test_evaluate_exact_match(
        self, service: ApprovalRuleService
    ) -> None:
        """Exakte Uebereinstimmung funktioniert."""
        conditions = {"supplier_id": "SUP123"}
        entity_data = {"supplier_id": "SUP123"}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is True

    def test_evaluate_multiple_conditions_all_match(
        self, service: ApprovalRuleService
    ) -> None:
        """Mehrere Bedingungen - alle muessen zutreffen."""
        conditions = {
            "amount_greater_than": 1000,
            "category_in": ["travel", "equipment"],
        }
        entity_data = {"amount": 2000, "category": "travel"}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is True
        assert result["score"] == 1.0
        assert len(result["matched"]) == 2

    def test_evaluate_multiple_conditions_partial_match(
        self, service: ApprovalRuleService
    ) -> None:
        """Mehrere Bedingungen - nur teilweise Match."""
        conditions = {
            "amount_greater_than": 1000,
            "category_in": ["travel"],
        }
        entity_data = {"amount": 2000, "category": "office"}  # Category passt nicht

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is False
        assert result["score"] == 0.5  # 1 von 2 Bedingungen
        assert len(result["matched"]) == 1

    def test_evaluate_missing_field_in_entity(
        self, service: ApprovalRuleService
    ) -> None:
        """Fehlende Felder in Entity-Daten werden uebersprungen."""
        conditions = {"amount_greater_than": 1000}
        entity_data = {}  # Kein amount

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is False

    def test_evaluate_equals_condition(
        self, service: ApprovalRuleService
    ) -> None:
        """_equals Bedingung funktioniert."""
        conditions = {"status_equals": "approved"}
        entity_data = {"status": "approved"}

        result = service._evaluate_conditions(conditions, entity_data)

        assert result["matches"] is True


# =============================================================================
# VALUE COMPARISON TESTS
# =============================================================================

class TestValueComparison:
    """Tests fuer Wertvergleiche."""

    def test_compare_decimal_greater_than(
        self, service: ApprovalRuleService
    ) -> None:
        """Decimal-Vergleich > funktioniert."""
        assert service._compare_values(Decimal("6000"), Decimal("5000"), ">") is True
        assert service._compare_values(Decimal("4000"), Decimal("5000"), ">") is False

    def test_compare_decimal_less_than(
        self, service: ApprovalRuleService
    ) -> None:
        """Decimal-Vergleich < funktioniert."""
        assert service._compare_values(Decimal("3000"), Decimal("5000"), "<") is True
        assert service._compare_values(Decimal("7000"), Decimal("5000"), "<") is False

    def test_compare_integer_values(
        self, service: ApprovalRuleService
    ) -> None:
        """Integer-Vergleich funktioniert."""
        assert service._compare_values(100, 50, ">") is True
        assert service._compare_values(25, 50, "<") is True

    def test_compare_string_numbers(
        self, service: ApprovalRuleService
    ) -> None:
        """String-zu-Decimal Konvertierung funktioniert."""
        assert service._compare_values("6000", "5000", ">") is True
        assert service._compare_values("3000.50", "5000", "<") is True

    def test_compare_invalid_values(
        self, service: ApprovalRuleService
    ) -> None:
        """Ungueltige Werte geben False zurueck."""
        assert service._compare_values("not-a-number", 5000, ">") is False
        assert service._compare_values(None, 5000, ">") is False


# =============================================================================
# RULE MATCHING TESTS
# =============================================================================

class TestRuleMatching:
    """Tests fuer Rule-Matching."""

    @pytest.mark.asyncio
    async def test_find_matching_rules_entity_type_filter(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Nur Regeln mit passendem Entity-Typ werden gefunden."""
        invoice_rule = MagicMock(spec=ApprovalRule)
        invoice_rule.entity_types = ["invoice"]
        invoice_rule.conditions = {"amount_greater_than": 1000}
        invoice_rule.priority = 100

        expense_rule = MagicMock(spec=ApprovalRule)
        expense_rule.entity_types = ["expense"]
        expense_rule.conditions = {}
        expense_rule.priority = 100

        with patch.object(
            service, "get_rules_for_company",
            return_value=[invoice_rule, expense_rule]
        ):
            result = await service.find_matching_rules(
                company_id=uuid4(),
                entity_type="invoice",
                entity_data={"amount": 5000}
            )

            # Nur invoice_rule sollte gefunden werden
            assert len(result) == 1
            assert result[0].rule == invoice_rule

    @pytest.mark.asyncio
    async def test_find_matching_rules_conditions_evaluated(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Regeln werden nur bei passenden Bedingungen zurueckgegeben."""
        rule_5k = MagicMock(spec=ApprovalRule)
        rule_5k.entity_types = ["invoice"]
        rule_5k.conditions = {"amount_greater_than": 5000}
        rule_5k.priority = 100

        rule_10k = MagicMock(spec=ApprovalRule)
        rule_10k.entity_types = ["invoice"]
        rule_10k.conditions = {"amount_greater_than": 10000}
        rule_10k.priority = 50

        with patch.object(
            service, "get_rules_for_company",
            return_value=[rule_5k, rule_10k]
        ):
            # Betrag 7000 - sollte nur rule_5k matchen
            result = await service.find_matching_rules(
                company_id=uuid4(),
                entity_type="invoice",
                entity_data={"amount": 7000}
            )

            assert len(result) == 1
            assert result[0].rule == rule_5k

    @pytest.mark.asyncio
    async def test_find_matching_rules_sorted_by_priority(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Ergebnisse sind nach Prioritaet sortiert (niedrig = hoch)."""
        high_priority = MagicMock(spec=ApprovalRule)
        high_priority.entity_types = ["invoice"]
        high_priority.conditions = {}
        high_priority.priority = 10  # Hohe Prioritaet

        low_priority = MagicMock(spec=ApprovalRule)
        low_priority.entity_types = ["invoice"]
        low_priority.conditions = {}
        low_priority.priority = 100  # Niedrige Prioritaet

        with patch.object(
            service, "get_rules_for_company",
            return_value=[low_priority, high_priority]
        ):
            result = await service.find_matching_rules(
                company_id=uuid4(),
                entity_type="invoice",
                entity_data={}
            )

            assert len(result) == 2
            assert result[0].rule == high_priority  # Zuerst
            assert result[1].rule == low_priority

    @pytest.mark.asyncio
    async def test_find_matching_rules_no_match(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Leere Liste bei keinem Match."""
        rule = MagicMock(spec=ApprovalRule)
        rule.entity_types = ["expense"]  # Anderer Typ
        rule.conditions = {}
        rule.priority = 100

        with patch.object(
            service, "get_rules_for_company",
            return_value=[rule]
        ):
            result = await service.find_matching_rules(
                company_id=uuid4(),
                entity_type="invoice",  # Passt nicht
                entity_data={}
            )

            assert len(result) == 0


# =============================================================================
# EVALUATE RULE CONDITIONS (PUBLIC API) TESTS
# =============================================================================

class TestEvaluateRuleConditions:
    """Tests fuer die public evaluate_rule_conditions Methode."""

    @pytest.mark.asyncio
    async def test_evaluate_rule_conditions_matches(
        self, service: ApprovalRuleService, sample_rule: MagicMock
    ) -> None:
        """Regel trifft auf Entity-Daten zu."""
        entity_data = {"amount": 7500}  # > 5000

        result = await service.evaluate_rule_conditions(sample_rule, entity_data)

        assert result is True

    @pytest.mark.asyncio
    async def test_evaluate_rule_conditions_not_matches(
        self, service: ApprovalRuleService, sample_rule: MagicMock
    ) -> None:
        """Regel trifft nicht auf Entity-Daten zu."""
        entity_data = {"amount": 3000}  # < 5000

        result = await service.evaluate_rule_conditions(sample_rule, entity_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_rule_conditions_empty_conditions(
        self, service: ApprovalRuleService, sample_rule: MagicMock
    ) -> None:
        """Leere Bedingungen geben True zurueck."""
        sample_rule.conditions = None

        result = await service.evaluate_rule_conditions(sample_rule, {"any": "data"})

        assert result is True


# =============================================================================
# DEFAULT RULES TESTS
# =============================================================================

class TestDefaultRules:
    """Tests fuer Standard-Regeln."""

    @pytest.mark.asyncio
    async def test_create_default_rules(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Standard-Regeln werden erstellt."""
        company_id = uuid4()
        created_by_id = uuid4()

        result = await service.create_default_rules(company_id, created_by_id)

        # Sollte 4 Standard-Regeln erstellen
        assert mock_db.add.call_count == 4
        assert mock_db.commit.await_count == 4

    @pytest.mark.asyncio
    async def test_default_rules_content(
        self, service: ApprovalRuleService, mock_db: AsyncMock
    ) -> None:
        """Standard-Regeln haben korrekten Inhalt."""
        company_id = uuid4()
        created_by_id = uuid4()

        # Capture all added rules
        added_rules = []
        def capture_rule(rule):
            added_rules.append(rule)
        mock_db.add.side_effect = capture_rule

        await service.create_default_rules(company_id, created_by_id)

        # Prüfe dass verschiedene Regeltypen erstellt wurden
        rule_types = [r.rule_type for r in added_rules]
        assert ApprovalRuleType.AMOUNT_THRESHOLD in rule_types
        assert ApprovalRuleType.CATEGORY in rule_types
        assert ApprovalRuleType.DOCUMENT_TYPE in rule_types


# =============================================================================
# MATCHED RULE DATACLASS TESTS
# =============================================================================

class TestMatchedRuleDataclass:
    """Tests fuer MatchedRule Dataclass."""

    def test_matched_rule_creation(self, sample_rule: MagicMock) -> None:
        """MatchedRule wird korrekt erstellt."""
        matched = MatchedRule(
            rule=sample_rule,
            match_score=0.75,
            matched_conditions=["amount_greater_than"]
        )

        assert matched.rule == sample_rule
        assert matched.match_score == 0.75
        assert "amount_greater_than" in matched.matched_conditions

    def test_matched_rule_full_match(self, sample_rule: MagicMock) -> None:
        """Voller Match hat Score 1.0."""
        matched = MatchedRule(
            rule=sample_rule,
            match_score=1.0,
            matched_conditions=["amount_greater_than", "category_in"]
        )

        assert matched.match_score == 1.0
        assert len(matched.matched_conditions) == 2

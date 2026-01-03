"""
Unit Tests fuer ImportRuleService.

Tests fuer Rule Evaluation Engine mit AND/OR Logik,
Operator-Validierung und Action-Anwendung.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.import.import_rule_service import ImportRuleService


class TestRuleEvaluation:
    """Tests fuer die Rule Evaluation Engine."""

    @pytest.fixture
    def service(self) -> ImportRuleService:
        """Create service instance."""
        return ImportRuleService()

    # =========================================================================
    # String Operators
    # =========================================================================

    def test_evaluate_equals_match(self, service: ImportRuleService) -> None:
        """Test equals operator - match."""
        condition = {"field": "sender", "operator": "equals", "value": "test@example.com"}
        metadata = {"sender": "test@example.com"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_equals_no_match(self, service: ImportRuleService) -> None:
        """Test equals operator - no match."""
        condition = {"field": "sender", "operator": "equals", "value": "test@example.com"}
        metadata = {"sender": "other@example.com"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    def test_evaluate_equals_case_insensitive(self, service: ImportRuleService) -> None:
        """Test equals operator - case insensitive."""
        condition = {
            "field": "sender",
            "operator": "equals",
            "value": "Test@Example.COM",
            "case_sensitive": False,
        }
        metadata = {"sender": "test@example.com"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_equals_case_sensitive(self, service: ImportRuleService) -> None:
        """Test equals operator - case sensitive."""
        condition = {
            "field": "sender",
            "operator": "equals",
            "value": "Test@Example.COM",
            "case_sensitive": True,
        }
        metadata = {"sender": "test@example.com"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    def test_evaluate_not_equals(self, service: ImportRuleService) -> None:
        """Test not_equals operator."""
        condition = {"field": "sender", "operator": "not_equals", "value": "spam@example.com"}
        metadata = {"sender": "test@example.com"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_contains_match(self, service: ImportRuleService) -> None:
        """Test contains operator - match."""
        condition = {"field": "subject", "operator": "contains", "value": "Invoice"}
        metadata = {"subject": "Your Invoice #12345"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_contains_no_match(self, service: ImportRuleService) -> None:
        """Test contains operator - no match."""
        condition = {"field": "subject", "operator": "contains", "value": "Receipt"}
        metadata = {"subject": "Your Invoice #12345"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    def test_evaluate_not_contains(self, service: ImportRuleService) -> None:
        """Test not_contains operator."""
        condition = {"field": "subject", "operator": "not_contains", "value": "SPAM"}
        metadata = {"subject": "Important Document"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_starts_with(self, service: ImportRuleService) -> None:
        """Test starts_with operator."""
        condition = {"field": "filename", "operator": "starts_with", "value": "invoice_"}
        metadata = {"filename": "invoice_2024_001.pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_ends_with(self, service: ImportRuleService) -> None:
        """Test ends_with operator."""
        condition = {"field": "filename", "operator": "ends_with", "value": ".pdf"}
        metadata = {"filename": "document.pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_regex_match(self, service: ImportRuleService) -> None:
        """Test regex operator - match."""
        condition = {
            "field": "filename",
            "operator": "regex",
            "value": r"invoice_\d{4}_\d{3}\.pdf",
        }
        metadata = {"filename": "invoice_2024_001.pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_regex_no_match(self, service: ImportRuleService) -> None:
        """Test regex operator - no match."""
        condition = {
            "field": "filename",
            "operator": "regex",
            "value": r"invoice_\d{4}_\d{3}\.pdf",
        }
        metadata = {"filename": "receipt_2024.pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    def test_evaluate_regex_invalid_pattern(self, service: ImportRuleService) -> None:
        """Test regex operator - invalid pattern returns False."""
        condition = {"field": "filename", "operator": "regex", "value": r"[invalid("}
        metadata = {"filename": "test.pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    # =========================================================================
    # Numeric Operators
    # =========================================================================

    def test_evaluate_gt(self, service: ImportRuleService) -> None:
        """Test gt (greater than) operator."""
        condition = {"field": "file_size", "operator": "gt", "value": 1000}
        metadata = {"file_size": 2000}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_gt_equal_fails(self, service: ImportRuleService) -> None:
        """Test gt operator - equal value fails."""
        condition = {"field": "file_size", "operator": "gt", "value": 1000}
        metadata = {"file_size": 1000}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    def test_evaluate_lt(self, service: ImportRuleService) -> None:
        """Test lt (less than) operator."""
        condition = {"field": "file_size", "operator": "lt", "value": 5000}
        metadata = {"file_size": 1000}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_gte(self, service: ImportRuleService) -> None:
        """Test gte (greater than or equal) operator."""
        condition = {"field": "file_size", "operator": "gte", "value": 1000}
        metadata = {"file_size": 1000}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_lte(self, service: ImportRuleService) -> None:
        """Test lte (less than or equal) operator."""
        condition = {"field": "file_size", "operator": "lte", "value": 1000}
        metadata = {"file_size": 1000}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    # =========================================================================
    # List Operators
    # =========================================================================

    def test_evaluate_in_list_match(self, service: ImportRuleService) -> None:
        """Test in_list operator - match."""
        condition = {
            "field": "extension",
            "operator": "in_list",
            "value": [".pdf", ".png", ".jpg"],
        }
        metadata = {"extension": ".pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_in_list_no_match(self, service: ImportRuleService) -> None:
        """Test in_list operator - no match."""
        condition = {
            "field": "extension",
            "operator": "in_list",
            "value": [".pdf", ".png", ".jpg"],
        }
        metadata = {"extension": ".exe"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    def test_evaluate_not_in_list(self, service: ImportRuleService) -> None:
        """Test not_in_list operator."""
        condition = {
            "field": "extension",
            "operator": "not_in_list",
            "value": [".exe", ".bat", ".cmd"],
        }
        metadata = {"extension": ".pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    # =========================================================================
    # Empty/Null Operators
    # =========================================================================

    def test_evaluate_is_empty_none(self, service: ImportRuleService) -> None:
        """Test is_empty operator - None value."""
        condition = {"field": "attachment", "operator": "is_empty", "value": True}
        metadata = {"attachment": None}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_is_empty_empty_string(self, service: ImportRuleService) -> None:
        """Test is_empty operator - empty string."""
        condition = {"field": "attachment", "operator": "is_empty", "value": True}
        metadata = {"attachment": ""}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_is_empty_with_value(self, service: ImportRuleService) -> None:
        """Test is_empty operator - with value fails."""
        condition = {"field": "attachment", "operator": "is_empty", "value": True}
        metadata = {"attachment": "file.pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    def test_evaluate_is_not_empty(self, service: ImportRuleService) -> None:
        """Test is_not_empty operator."""
        condition = {"field": "attachment", "operator": "is_not_empty", "value": True}
        metadata = {"attachment": "file.pdf"}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_evaluate_missing_field(self, service: ImportRuleService) -> None:
        """Test evaluation with missing field returns False."""
        condition = {"field": "nonexistent", "operator": "equals", "value": "test"}
        metadata = {"other_field": "value"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False

    def test_evaluate_nested_field(self, service: ImportRuleService) -> None:
        """Test evaluation with nested field using dot notation."""
        condition = {"field": "email.sender", "operator": "equals", "value": "test@example.com"}
        metadata = {"email": {"sender": "test@example.com"}}

        result = service._evaluate_condition(condition, metadata)

        assert result is True

    def test_evaluate_unknown_operator(self, service: ImportRuleService) -> None:
        """Test evaluation with unknown operator returns False."""
        condition = {"field": "test", "operator": "unknown_op", "value": "test"}
        metadata = {"test": "test"}

        result = service._evaluate_condition(condition, metadata)

        assert result is False


class TestLogicEvaluation:
    """Tests fuer AND/OR Logik."""

    @pytest.fixture
    def service(self) -> ImportRuleService:
        """Create service instance."""
        return ImportRuleService()

    def test_and_logic_all_match(self, service: ImportRuleService) -> None:
        """Test AND logic - all conditions match."""
        conditions = [
            {"field": "sender", "operator": "contains", "value": "@example.com"},
            {"field": "subject", "operator": "contains", "value": "Invoice"},
        ]
        metadata = {"sender": "test@example.com", "subject": "Invoice #123"}

        result = service._evaluate_conditions(conditions, metadata, logic="AND")

        assert result is True

    def test_and_logic_one_fails(self, service: ImportRuleService) -> None:
        """Test AND logic - one condition fails."""
        conditions = [
            {"field": "sender", "operator": "contains", "value": "@example.com"},
            {"field": "subject", "operator": "contains", "value": "Receipt"},
        ]
        metadata = {"sender": "test@example.com", "subject": "Invoice #123"}

        result = service._evaluate_conditions(conditions, metadata, logic="AND")

        assert result is False

    def test_or_logic_one_match(self, service: ImportRuleService) -> None:
        """Test OR logic - one condition matches."""
        conditions = [
            {"field": "subject", "operator": "contains", "value": "Invoice"},
            {"field": "subject", "operator": "contains", "value": "Receipt"},
        ]
        metadata = {"subject": "Your Invoice #123"}

        result = service._evaluate_conditions(conditions, metadata, logic="OR")

        assert result is True

    def test_or_logic_none_match(self, service: ImportRuleService) -> None:
        """Test OR logic - no condition matches."""
        conditions = [
            {"field": "subject", "operator": "contains", "value": "Invoice"},
            {"field": "subject", "operator": "contains", "value": "Receipt"},
        ]
        metadata = {"subject": "General Information"}

        result = service._evaluate_conditions(conditions, metadata, logic="OR")

        assert result is False

    def test_empty_conditions(self, service: ImportRuleService) -> None:
        """Test evaluation with empty conditions returns True."""
        conditions: list = []
        metadata = {"test": "value"}

        result = service._evaluate_conditions(conditions, metadata, logic="AND")

        assert result is True


class TestRuleMatching:
    """Tests fuer vollstaendiges Rule Matching."""

    @pytest.fixture
    def service(self) -> ImportRuleService:
        """Create service instance."""
        return ImportRuleService()

    def test_match_single_rule(self, service: ImportRuleService) -> None:
        """Test matching a single rule."""
        rule = MagicMock()
        rule.id = str(uuid4())
        rule.name = "Invoice Rule"
        rule.is_active = True
        rule.priority = 1
        rule.logic = "AND"
        rule.conditions = [
            {"field": "subject", "operator": "contains", "value": "Invoice"},
        ]
        rule.actions = [
            {"action": "assign_folder", "value": "invoices"},
        ]
        rule.stop_processing_on_match = False

        metadata = {"subject": "Your Invoice #123"}

        matched, actions = service._match_rule(rule, metadata)

        assert matched is True
        assert actions == rule.actions

    def test_no_match_inactive_rule(self, service: ImportRuleService) -> None:
        """Test inactive rule does not match."""
        rule = MagicMock()
        rule.id = str(uuid4())
        rule.name = "Inactive Rule"
        rule.is_active = False
        rule.logic = "AND"
        rule.conditions = [
            {"field": "subject", "operator": "contains", "value": "Invoice"},
        ]
        rule.actions = []

        metadata = {"subject": "Your Invoice #123"}

        matched, actions = service._match_rule(rule, metadata)

        assert matched is False
        assert actions == []


class TestActionMerging:
    """Tests fuer Action Merging."""

    @pytest.fixture
    def service(self) -> ImportRuleService:
        """Create service instance."""
        return ImportRuleService()

    def test_merge_folder_actions(self, service: ImportRuleService) -> None:
        """Test merging folder actions - last wins."""
        actions_list = [
            [{"action": "assign_folder", "value": "folder1"}],
            [{"action": "assign_folder", "value": "folder2"}],
        ]

        merged = service._merge_actions(actions_list)

        # Last assign_folder should win
        folder_actions = [a for a in merged if a["action"] == "assign_folder"]
        assert len(folder_actions) == 1
        assert folder_actions[0]["value"] == "folder2"

    def test_merge_tag_actions(self, service: ImportRuleService) -> None:
        """Test merging tag actions - combined."""
        actions_list = [
            [{"action": "assign_tags", "value": ["tag1", "tag2"]}],
            [{"action": "assign_tags", "value": ["tag3"]}],
        ]

        merged = service._merge_actions(actions_list)

        tag_actions = [a for a in merged if a["action"] == "assign_tags"]
        assert len(tag_actions) == 1
        # Tags should be combined
        assert set(tag_actions[0]["value"]) == {"tag1", "tag2", "tag3"}

    def test_merge_different_actions(self, service: ImportRuleService) -> None:
        """Test merging different action types."""
        actions_list = [
            [{"action": "assign_folder", "value": "invoices"}],
            [{"action": "enable_ocr", "value": True}],
            [{"action": "set_priority", "value": "high"}],
        ]

        merged = service._merge_actions(actions_list)

        assert len(merged) == 3
        action_types = {a["action"] for a in merged}
        assert action_types == {"assign_folder", "enable_ocr", "set_priority"}


class TestRuleTestMode:
    """Tests fuer Rule Test Mode."""

    @pytest.fixture
    def service(self) -> ImportRuleService:
        """Create service instance."""
        return ImportRuleService()

    def test_test_rule_match(self, service: ImportRuleService) -> None:
        """Test rule testing with match."""
        rule = MagicMock()
        rule.id = str(uuid4())
        rule.name = "Test Rule"
        rule.is_active = True
        rule.logic = "AND"
        rule.conditions = [
            {"field": "extension", "operator": "equals", "value": ".pdf"},
        ]
        rule.actions = [
            {"action": "enable_ocr", "value": True},
        ]

        metadata = {"extension": ".pdf"}

        result = service.test_rule(rule, metadata)

        assert result["matched"] is True
        assert result["rule_id"] == rule.id
        assert result["rule_name"] == "Test Rule"
        assert len(result["applied_actions"]) == 1

    def test_test_rule_no_match(self, service: ImportRuleService) -> None:
        """Test rule testing without match."""
        rule = MagicMock()
        rule.id = str(uuid4())
        rule.name = "Test Rule"
        rule.is_active = True
        rule.logic = "AND"
        rule.conditions = [
            {"field": "extension", "operator": "equals", "value": ".pdf"},
        ]
        rule.actions = []

        metadata = {"extension": ".jpg"}

        result = service.test_rule(rule, metadata)

        assert result["matched"] is False
        assert result["rule_id"] == rule.id


# =============================================================================
# Async Tests
# =============================================================================

@pytest.mark.asyncio
class TestAsyncRuleOperations:
    """Async tests fuer Rule CRUD operations."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest_asyncio.fixture
    async def service(self) -> ImportRuleService:
        """Create service instance."""
        return ImportRuleService()

    async def test_evaluate_rules_empty_list(
        self, service: ImportRuleService, mock_db: AsyncMock
    ) -> None:
        """Test evaluate_rules with no rules."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        metadata = {"test": "value"}

        with patch.object(service, "_get_active_rules", return_value=[]):
            matched, actions = await service.evaluate_rules(
                mock_db, metadata, source_type="email"
            )

        assert matched == []
        assert actions == []

    async def test_evaluate_rules_with_matches(
        self, service: ImportRuleService, mock_db: AsyncMock
    ) -> None:
        """Test evaluate_rules with matching rules."""
        rule1 = MagicMock()
        rule1.id = str(uuid4())
        rule1.name = "Rule 1"
        rule1.is_active = True
        rule1.priority = 1
        rule1.logic = "AND"
        rule1.conditions = [{"field": "type", "operator": "equals", "value": "invoice"}]
        rule1.actions = [{"action": "assign_folder", "value": "invoices"}]
        rule1.stop_processing_on_match = False
        rule1.times_matched = 0

        with patch.object(service, "_get_active_rules", return_value=[rule1]):
            metadata = {"type": "invoice"}

            matched, actions = await service.evaluate_rules(
                mock_db, metadata, source_type="email"
            )

        assert len(matched) == 1
        assert matched[0].name == "Rule 1"
        assert len(actions) == 1

    async def test_evaluate_rules_stop_on_match(
        self, service: ImportRuleService, mock_db: AsyncMock
    ) -> None:
        """Test evaluate_rules stops processing on match."""
        rule1 = MagicMock()
        rule1.id = str(uuid4())
        rule1.name = "Rule 1"
        rule1.is_active = True
        rule1.priority = 1
        rule1.logic = "AND"
        rule1.conditions = [{"field": "type", "operator": "equals", "value": "invoice"}]
        rule1.actions = [{"action": "assign_folder", "value": "folder1"}]
        rule1.stop_processing_on_match = True
        rule1.times_matched = 0

        rule2 = MagicMock()
        rule2.id = str(uuid4())
        rule2.name = "Rule 2"
        rule2.is_active = True
        rule2.priority = 2
        rule2.logic = "AND"
        rule2.conditions = [{"field": "type", "operator": "equals", "value": "invoice"}]
        rule2.actions = [{"action": "assign_folder", "value": "folder2"}]
        rule2.stop_processing_on_match = False
        rule2.times_matched = 0

        with patch.object(service, "_get_active_rules", return_value=[rule1, rule2]):
            metadata = {"type": "invoice"}

            matched, actions = await service.evaluate_rules(
                mock_db, metadata, source_type="email"
            )

        # Only rule1 should match due to stop_processing_on_match
        assert len(matched) == 1
        assert matched[0].name == "Rule 1"

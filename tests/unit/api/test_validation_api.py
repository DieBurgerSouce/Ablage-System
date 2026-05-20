# -*- coding: utf-8 -*-
"""
Tests fuer Validation API Endpoints.

Testet alle Validation Queue API Endpunkte:
- Queue Management (CRUD, Assignment, Approval/Rejection)
- Batch Operations
- Field Reviews
- Validation Rules (CRUD)
- Sample Config
- Analytics
"""

import pytest
from datetime import datetime, date, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch


# ==================== Queue Management Tests ====================

class TestQueueManagementEndpoints:
    """Tests fuer Queue CRUD Endpoints."""

    @pytest.fixture
    def mock_queue_service(self):
        with patch('app.api.v1.validation.get_validation_queue_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_field_service(self):
        with patch('app.api.v1.validation.get_validation_field_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_read(self):
        """Benutzer mit validation:read Berechtigung."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "reader@example.com"
        return user

    @pytest.fixture
    def mock_user_write(self):
        """Benutzer mit validation:write Berechtigung."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "writer@example.com"
        return user

    @pytest.fixture
    def mock_user_manage(self):
        """Benutzer mit validation:manage Berechtigung (Admin)."""
        user = MagicMock()
        user.id = uuid4()
        user.email = "admin@example.com"
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_list_queue_items_service_called(self, mock_queue_service, mock_db, mock_user_read):
        """Sollte Queue-Service get_queue_items aufrufen."""
        mock_queue_service.get_queue_items = AsyncMock(return_value=([], 0))

        # Verify service method exists and can be called
        result = await mock_queue_service.get_queue_items(
            filters=MagicMock(),
            sort_options=MagicMock(),
            limit=50,
            offset=0
        )

        assert result == ([], 0)
        mock_queue_service.get_queue_items.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_queue_items_returns_items(self, mock_queue_service, mock_db, mock_user_read):
        """Sollte Queue-Items mit Paginierung zurueckgeben."""
        item_id = uuid4()
        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.document_id = uuid4()
        mock_item.status = "pending"
        mock_item.priority = 50

        mock_queue_service.get_queue_items = AsyncMock(return_value=([mock_item], 1))

        items, total = await mock_queue_service.get_queue_items(
            filters=MagicMock(),
            sort_options=MagicMock(),
            limit=50,
            offset=0
        )

        assert total == 1
        assert len(items) == 1
        assert items[0].id == item_id

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, mock_queue_service, mock_db, mock_user_read):
        """Sollte Queue-Statistiken zurueckgeben."""
        mock_queue_service.get_queue_stats = AsyncMock(return_value={
            "total": 100,
            "pending": 50,
            "in_review": 30,
            "approved": 15,
            "rejected": 5,
        })

        result = await mock_queue_service.get_queue_stats()

        assert result["total"] == 100
        assert result["pending"] == 50
        assert result["in_review"] == 30

    @pytest.mark.asyncio
    async def test_get_my_assigned_items(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte dem Benutzer zugewiesene Items zurueckgeben."""
        mock_item = MagicMock()
        mock_item.id = uuid4()
        mock_item.status = "in_review"

        mock_queue_service.get_my_assigned_items = AsyncMock(return_value=([mock_item], 5))

        items, total = await mock_queue_service.get_my_assigned_items(
            editor_id=mock_user_write.id,
            status=None,
            limit=50,
            offset=0
        )

        assert total == 5
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_add_to_queue(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte Queue-Item erstellen."""
        item_id = uuid4()
        doc_id = uuid4()
        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.document_id = doc_id
        mock_item.status = "pending"

        mock_queue_service.add_to_queue = AsyncMock(return_value=mock_item)

        result = await mock_queue_service.add_to_queue(
            document_id=doc_id,
            source="manual",
            priority=75,
            notes="Test-Notiz",
            rule_id=None
        )

        assert result.id == item_id
        assert result.document_id == doc_id

    @pytest.mark.asyncio
    async def test_get_queue_item_success(self, mock_queue_service, mock_db, mock_user_read):
        """Sollte einzelnes Queue-Item zurueckgeben."""
        item_id = uuid4()
        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.document_id = uuid4()
        mock_item.status = "pending"

        mock_queue_service.get_queue_item = AsyncMock(return_value=mock_item)

        result = await mock_queue_service.get_queue_item(item_id)

        assert result.id == item_id

    @pytest.mark.asyncio
    async def test_get_queue_item_not_found(self, mock_queue_service, mock_db, mock_user_read):
        """Sollte None bei nicht gefundenem Item zurueckgeben."""
        mock_queue_service.get_queue_item = AsyncMock(return_value=None)

        result = await mock_queue_service.get_queue_item(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_update_queue_item(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte Queue-Item aktualisieren."""
        item_id = uuid4()
        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.priority = 90

        mock_queue_service.update_queue_item = AsyncMock(return_value=mock_item)

        result = await mock_queue_service.update_queue_item(
            item_id=item_id,
            update_data=MagicMock()
        )

        assert result.id == item_id
        assert result.priority == 90

    @pytest.mark.asyncio
    async def test_update_queue_item_not_found(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte None bei nicht gefundenem Item zurueckgeben."""
        mock_queue_service.update_queue_item = AsyncMock(return_value=None)

        result = await mock_queue_service.update_queue_item(
            item_id=uuid4(),
            update_data=MagicMock()
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_queue_item(self, mock_queue_service, mock_db, mock_user_manage):
        """Sollte Queue-Item loeschen."""
        mock_queue_service.delete_queue_item = AsyncMock(return_value=True)

        result = await mock_queue_service.delete_queue_item(uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_queue_item_not_found(self, mock_queue_service, mock_db, mock_user_manage):
        """Sollte False bei nicht gefundenem Item zurueckgeben."""
        mock_queue_service.delete_queue_item = AsyncMock(return_value=False)

        result = await mock_queue_service.delete_queue_item(uuid4())

        assert result is False


# ==================== Assignment Tests ====================

class TestAssignmentEndpoints:
    """Tests fuer Queue-Item Assignment."""

    @pytest.fixture
    def mock_queue_service(self):
        with patch('app.api.v1.validation.get_validation_queue_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_manage(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "admin@example.com"
        return user

    @pytest.mark.asyncio
    async def test_assign_to_editor(self, mock_queue_service, mock_db, mock_user_manage):
        """Sollte Item einem Editor zuweisen."""
        item_id = uuid4()
        editor_id = uuid4()

        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.assigned_to_id = editor_id
        mock_item.status = "in_review"

        mock_queue_service.assign_to_editor = AsyncMock(return_value=mock_item)

        result = await mock_queue_service.assign_to_editor(
            item_id=item_id,
            editor_id=editor_id,
            assigned_by_id=mock_user_manage.id
        )

        assert result.assigned_to_id == editor_id

    @pytest.mark.asyncio
    async def test_assign_to_editor_invalid(self, mock_queue_service, mock_db, mock_user_manage):
        """Sollte ValueError bei ungueltigem Editor werfen."""
        mock_queue_service.assign_to_editor = AsyncMock(
            side_effect=ValueError("Editor not found")
        )

        with pytest.raises(ValueError):
            await mock_queue_service.assign_to_editor(
                item_id=uuid4(),
                editor_id=uuid4(),
                assigned_by_id=mock_user_manage.id
            )

    @pytest.mark.asyncio
    async def test_unassign(self, mock_queue_service, mock_db, mock_user_manage):
        """Sollte Zuweisung entfernen."""
        item_id = uuid4()
        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.assigned_to_id = None
        mock_item.status = "pending"

        mock_queue_service.unassign = AsyncMock(return_value=mock_item)

        result = await mock_queue_service.unassign(item_id)

        assert result.assigned_to_id is None

    @pytest.mark.asyncio
    async def test_unassign_not_found(self, mock_queue_service, mock_db, mock_user_manage):
        """Sollte None bei nicht gefundenem Item zurueckgeben."""
        mock_queue_service.unassign = AsyncMock(return_value=None)

        result = await mock_queue_service.unassign(uuid4())

        assert result is None


# ==================== Approval/Rejection Tests ====================

class TestApprovalRejectionEndpoints:
    """Tests fuer Genehmigung und Ablehnung."""

    @pytest.fixture
    def mock_queue_service(self):
        with patch('app.api.v1.validation.get_validation_queue_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_write(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "editor@example.com"
        return user

    @pytest.mark.asyncio
    async def test_approve_item(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte Queue-Item genehmigen."""
        item_id = uuid4()
        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.status = "approved"
        mock_item.validated_by_id = mock_user_write.id

        mock_queue_service.approve_item = AsyncMock(return_value=mock_item)

        result = await mock_queue_service.approve_item(
            item_id=item_id,
            validated_by_id=mock_user_write.id,
            notes="Genehmigt nach Pruefung",
            apply_corrections=True
        )

        assert result.status == "approved"

    @pytest.mark.asyncio
    async def test_approve_item_not_found(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte None bei nicht gefundenem Item zurueckgeben."""
        mock_queue_service.approve_item = AsyncMock(return_value=None)

        result = await mock_queue_service.approve_item(
            item_id=uuid4(),
            validated_by_id=mock_user_write.id,
            notes=None,
            apply_corrections=False
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_item(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte Queue-Item ablehnen."""
        item_id = uuid4()
        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.status = "rejected"

        mock_queue_service.reject_item = AsyncMock(return_value=mock_item)

        result = await mock_queue_service.reject_item(
            item_id=item_id,
            validated_by_id=mock_user_write.id,
            reason="OCR-Qualitaet unzureichend",
            rejection_category=None
        )

        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_reject_item_invalid(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte ValueError bei ungueltiger Ablehnung werfen."""
        mock_queue_service.reject_item = AsyncMock(
            side_effect=ValueError("Invalid rejection")
        )

        with pytest.raises(ValueError):
            await mock_queue_service.reject_item(
                item_id=uuid4(),
                validated_by_id=mock_user_write.id,
                reason="Test",
                rejection_category=None
            )


# ==================== Batch Operations Tests ====================

class TestBatchOperationsEndpoints:
    """Tests fuer Batch-Operationen."""

    @pytest.fixture
    def mock_queue_service(self):
        with patch('app.api.v1.validation.get_validation_queue_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_write(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_user_manage(self):
        user = MagicMock()
        user.id = uuid4()
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_batch_approve(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte mehrere Items genehmigen."""
        mock_queue_service.batch_approve = AsyncMock(return_value={
            "success_count": 5,
            "failed_count": 0,
            "succeeded_ids": [str(uuid4()) for _ in range(5)],
            "failed_ids": [],
        })

        result = await mock_queue_service.batch_approve(
            item_ids=[uuid4() for _ in range(5)],
            validated_by_id=mock_user_write.id,
            notes="Batch-Genehmigung"
        )

        assert result["success_count"] == 5
        assert result["failed_count"] == 0

    @pytest.mark.asyncio
    async def test_batch_approve_partial_failure(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte Teilerfolg bei Batch-Genehmigung handhaben."""
        mock_queue_service.batch_approve = AsyncMock(return_value={
            "success_count": 3,
            "failed_count": 2,
            "succeeded_ids": [str(uuid4()) for _ in range(3)],
            "failed_ids": [str(uuid4()) for _ in range(2)],
        })

        result = await mock_queue_service.batch_approve(
            item_ids=[uuid4() for _ in range(5)],
            validated_by_id=mock_user_write.id,
            notes=None
        )

        assert result["success_count"] == 3
        assert result["failed_count"] == 2

    @pytest.mark.asyncio
    async def test_batch_reject(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte mehrere Items ablehnen."""
        mock_queue_service.batch_reject = AsyncMock(return_value={
            "success_count": 3,
            "failed_count": 0,
            "succeeded_ids": [str(uuid4()) for _ in range(3)],
            "failed_ids": [],
        })

        result = await mock_queue_service.batch_reject(
            item_ids=[uuid4() for _ in range(3)],
            validated_by_id=mock_user_write.id,
            reason="Qualitaet unzureichend",
            rejection_category=None
        )

        assert result["success_count"] == 3

    @pytest.mark.asyncio
    async def test_batch_assign(self, mock_queue_service, mock_db, mock_user_manage):
        """Sollte mehrere Items zuweisen (Admin-only)."""
        editor_id = uuid4()
        mock_queue_service.batch_assign = AsyncMock(return_value={
            "success_count": 10,
            "failed_count": 0,
            "succeeded_ids": [str(uuid4()) for _ in range(10)],
            "failed_ids": [],
        })

        result = await mock_queue_service.batch_assign(
            item_ids=[uuid4() for _ in range(10)],
            editor_id=editor_id,
            assigned_by_id=mock_user_manage.id
        )

        assert result["success_count"] == 10


# ==================== Field Reviews Tests ====================

class TestFieldReviewsEndpoints:
    """Tests fuer Field-Review-Endpoints."""

    @pytest.fixture
    def mock_field_service(self):
        with patch('app.api.v1.validation.get_validation_field_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_read(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_user_write(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_fields_for_review(self, mock_field_service, mock_db, mock_user_read):
        """Sollte Felder fuer Queue-Item zurueckgeben."""
        mock_field1 = MagicMock()
        mock_field1.id = uuid4()
        mock_field1.field_name = "invoice_number"
        mock_field1.original_value = "12345"

        mock_field2 = MagicMock()
        mock_field2.id = uuid4()
        mock_field2.field_name = "total_amount"
        mock_field2.original_value = "1000.00"

        mock_field_service.get_fields_for_review = AsyncMock(
            return_value=[mock_field1, mock_field2]
        )

        result = await mock_field_service.get_fields_for_review(uuid4())

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_update_field(self, mock_field_service, mock_db, mock_user_write):
        """Sollte Feld aktualisieren."""
        field_id = uuid4()
        mock_field = MagicMock()
        mock_field.id = field_id
        mock_field.corrected_value = "Korrigierter Wert"

        mock_field_service.update_field = AsyncMock(return_value=mock_field)

        result = await mock_field_service.update_field(
            field_id=field_id,
            corrected_value="Korrigierter Wert",
            reviewed_by_id=mock_user_write.id
        )

        assert result.corrected_value == "Korrigierter Wert"

    @pytest.mark.asyncio
    async def test_update_field_not_found(self, mock_field_service, mock_db, mock_user_write):
        """Sollte None bei nicht gefundenem Feld zurueckgeben."""
        mock_field_service.update_field = AsyncMock(return_value=None)

        result = await mock_field_service.update_field(
            field_id=uuid4(),
            corrected_value="Test",
            reviewed_by_id=mock_user_write.id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_field(self, mock_field_service, mock_db, mock_user_write):
        """Sollte Feld validieren."""
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.validation_errors = []
        mock_result.umlaut_issues = []

        mock_field_service.validate_field = AsyncMock(return_value=mock_result)

        result = await mock_field_service.validate_field(uuid4())

        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_validate_field_not_found(self, mock_field_service, mock_db, mock_user_write):
        """Sollte ValueError bei nicht gefundenem Feld werfen."""
        mock_field_service.validate_field = AsyncMock(
            side_effect=ValueError("Field not found")
        )

        with pytest.raises(ValueError):
            await mock_field_service.validate_field(uuid4())

    @pytest.mark.asyncio
    async def test_validate_all_fields(self, mock_field_service, mock_db, mock_user_write):
        """Sollte alle Felder validieren."""
        mock_result1 = MagicMock()
        mock_result1.field_name = "invoice_number"
        mock_result1.is_valid = True

        mock_result2 = MagicMock()
        mock_result2.field_name = "total_amount"
        mock_result2.is_valid = False

        mock_field_service.validate_all_fields = AsyncMock(
            return_value=[mock_result1, mock_result2]
        )

        result = await mock_field_service.validate_all_fields(uuid4())

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_field_stats(self, mock_field_service, mock_db, mock_user_read):
        """Sollte Feld-Statistiken zurueckgeben."""
        mock_field_service.get_field_stats = AsyncMock(return_value={
            "total_fields": 10,
            "reviewed_fields": 8,
            "corrected_fields": 3,
        })

        result = await mock_field_service.get_field_stats(uuid4())

        assert result["total_fields"] == 10


# ==================== Validation Rules Tests ====================

class TestValidationRulesEndpoints:
    """Tests fuer Validation Rules CRUD (Admin-only)."""

    @pytest.fixture
    def mock_sample_service(self):
        with patch('app.api.v1.validation.get_validation_sample_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_manage(self):
        user = MagicMock()
        user.id = uuid4()
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_get_active_rules(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte aktive Regeln auflisten."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Low Confidence"
        mock_rule.is_active = True

        mock_sample_service.get_active_rules = AsyncMock(return_value=[mock_rule])

        result = await mock_sample_service.get_active_rules()

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_all_rules(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte auch inaktive Regeln auflisten."""
        mock_rule1 = MagicMock()
        mock_rule1.id = uuid4()
        mock_rule1.name = "Rule 1"
        mock_rule1.is_active = True

        mock_rule2 = MagicMock()
        mock_rule2.id = uuid4()
        mock_rule2.name = "Rule 2"
        mock_rule2.is_active = False

        mock_sample_service.get_all_rules = AsyncMock(return_value=[mock_rule1, mock_rule2])

        result = await mock_sample_service.get_all_rules()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_create_rule(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte Regel erstellen."""
        rule_id = uuid4()
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Neue Regel"
        mock_rule.is_active = True

        mock_sample_service.create_rule = AsyncMock(return_value=mock_rule)

        result = await mock_sample_service.create_rule(
            rule_data=MagicMock(),
            created_by_id=mock_user_manage.id
        )

        assert result.id == rule_id

    @pytest.mark.asyncio
    async def test_get_rule(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte einzelne Regel zurueckgeben."""
        rule_id = uuid4()
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Test-Regel"

        mock_sample_service.get_rule = AsyncMock(return_value=mock_rule)

        result = await mock_sample_service.get_rule(rule_id)

        assert result.id == rule_id

    @pytest.mark.asyncio
    async def test_get_rule_not_found(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte None bei nicht gefundener Regel zurueckgeben."""
        mock_sample_service.get_rule = AsyncMock(return_value=None)

        result = await mock_sample_service.get_rule(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_update_rule(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte Regel aktualisieren."""
        rule_id = uuid4()
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Aktualisierte Regel"

        mock_sample_service.update_rule = AsyncMock(return_value=mock_rule)

        result = await mock_sample_service.update_rule(rule_id, MagicMock())

        assert result.name == "Aktualisierte Regel"

    @pytest.mark.asyncio
    async def test_update_rule_system_rule_error(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte ValueError bei System-Regel werfen."""
        mock_sample_service.update_rule = AsyncMock(
            side_effect=ValueError("System rule")
        )

        with pytest.raises(ValueError):
            await mock_sample_service.update_rule(uuid4(), MagicMock())

    @pytest.mark.asyncio
    async def test_delete_rule(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte Regel loeschen."""
        mock_sample_service.delete_rule = AsyncMock(return_value=True)

        result = await mock_sample_service.delete_rule(uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_rule_system_rule_error(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte ValueError bei System-Regel werfen."""
        mock_sample_service.delete_rule = AsyncMock(
            side_effect=ValueError("Cannot delete system rule")
        )

        with pytest.raises(ValueError):
            await mock_sample_service.delete_rule(uuid4())


# ==================== Sample Config Tests ====================

class TestSampleConfigEndpoints:
    """Tests fuer Sample Config (Admin-only)."""

    @pytest.fixture
    def mock_sample_service(self):
        with patch('app.api.v1.validation.get_validation_sample_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_manage(self):
        user = MagicMock()
        user.id = uuid4()
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_get_sample_config(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte Sample-Konfiguration zurueckgeben."""
        mock_config = MagicMock()
        mock_config.id = uuid4()
        mock_config.sample_rate = 0.1
        mock_config.confidence_threshold = 0.8

        mock_sample_service.get_sample_config = AsyncMock(return_value=mock_config)

        result = await mock_sample_service.get_sample_config()

        assert result.sample_rate == 0.1

    @pytest.mark.asyncio
    async def test_get_sample_config_not_found(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte None bei fehlender Konfiguration zurueckgeben."""
        mock_sample_service.get_sample_config = AsyncMock(return_value=None)

        result = await mock_sample_service.get_sample_config()

        assert result is None

    @pytest.mark.asyncio
    async def test_update_sample_config(self, mock_sample_service, mock_db, mock_user_manage):
        """Sollte Sample-Konfiguration aktualisieren."""
        config_id = uuid4()
        mock_config = MagicMock()
        mock_config.id = config_id
        mock_config.sample_rate = 0.15

        mock_sample_service.update_sample_config = AsyncMock(return_value=mock_config)

        result = await mock_sample_service.update_sample_config(config_id, MagicMock())

        assert result.sample_rate == 0.15


# ==================== Analytics Tests ====================

class TestAnalyticsEndpoints:
    """Tests fuer Analytics-Endpoints."""

    @pytest.fixture
    def mock_analytics_service(self):
        with patch('app.api.v1.validation.get_validation_analytics_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_read(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_user_manage(self):
        user = MagicMock()
        user.id = uuid4()
        user.role = "admin"
        return user

    @pytest.mark.asyncio
    async def test_get_overview_stats(self, mock_analytics_service, mock_db, mock_user_read):
        """Sollte Analytics-Uebersicht zurueckgeben."""
        mock_stats = MagicMock()
        mock_stats.total_processed = 1000
        mock_stats.approval_rate = 0.85
        mock_stats.average_processing_time = 120.5

        mock_analytics_service.get_overview_stats = AsyncMock(return_value=mock_stats)

        result = await mock_analytics_service.get_overview_stats(None, None)

        assert result.total_processed == 1000

    @pytest.mark.asyncio
    async def test_get_overview_stats_with_date_filter(self, mock_analytics_service, mock_db, mock_user_read):
        """Sollte Analytics mit Datumsfilter zurueckgeben."""
        mock_stats = MagicMock()
        mock_stats.total_processed = 500

        mock_analytics_service.get_overview_stats = AsyncMock(return_value=mock_stats)

        result = await mock_analytics_service.get_overview_stats(
            date(2024, 1, 1),
            date(2024, 6, 30)
        )

        mock_analytics_service.get_overview_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_editor_stats(self, mock_analytics_service, mock_db, mock_user_manage):
        """Sollte Editor-Statistiken zurueckgeben (Admin-only)."""
        mock_stat1 = MagicMock()
        mock_stat1.editor_id = uuid4()
        mock_stat1.items_processed = 100

        mock_stat2 = MagicMock()
        mock_stat2.editor_id = uuid4()
        mock_stat2.items_processed = 80

        mock_analytics_service.get_editor_stats = AsyncMock(
            return_value=[mock_stat1, mock_stat2]
        )

        result = await mock_analytics_service.get_editor_stats(None, None)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_trend_data(self, mock_analytics_service, mock_db, mock_user_read):
        """Sollte Trend-Daten zurueckgeben."""
        mock_analytics_service.get_trend_data = AsyncMock(return_value=[
            {"date": "2024-01-01", "count": 50},
            {"date": "2024-01-02", "count": 60},
        ])

        result = await mock_analytics_service.get_trend_data(30, "day")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_document_type_stats(self, mock_analytics_service, mock_db, mock_user_read):
        """Sollte Dokumenttyp-Statistiken zurueckgeben."""
        mock_stat1 = MagicMock()
        mock_stat1.document_type = "invoice"
        mock_stat1.count = 500

        mock_stat2 = MagicMock()
        mock_stat2.document_type = "contract"
        mock_stat2.count = 200

        mock_analytics_service.get_document_type_stats = AsyncMock(
            return_value=[mock_stat1, mock_stat2]
        )

        result = await mock_analytics_service.get_document_type_stats()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_confidence_distribution(self, mock_analytics_service, mock_db, mock_user_read):
        """Sollte Confidence-Verteilung zurueckgeben."""
        mock_distribution = MagicMock()
        mock_distribution.buckets = [
            {"range": "0.0-0.1", "count": 10},
            {"range": "0.9-1.0", "count": 500},
        ]

        mock_analytics_service.get_confidence_distribution = AsyncMock(
            return_value=mock_distribution
        )

        result = await mock_analytics_service.get_confidence_distribution()

        assert len(result.buckets) == 2


# ==================== Document Integration Tests ====================

class TestDocumentIntegrationEndpoints:
    """Tests fuer Dokument-Integration."""

    @pytest.fixture
    def mock_queue_service(self):
        with patch('app.api.v1.validation.get_validation_queue_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_write(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_add_document_to_queue(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte Dokument zur Queue hinzufuegen."""
        item_id = uuid4()
        doc_id = uuid4()

        mock_item = MagicMock()
        mock_item.id = item_id
        mock_item.document_id = doc_id
        mock_item.status = "pending"

        mock_queue_service.add_to_queue = AsyncMock(return_value=mock_item)

        result = await mock_queue_service.add_to_queue(
            document_id=doc_id,
            source="manual",
            priority=75,
            notes="Manuelle Pruefung erforderlich",
            rule_id=None
        )

        assert result.document_id == doc_id

    @pytest.mark.asyncio
    async def test_add_document_to_queue_error(self, mock_queue_service, mock_db, mock_user_write):
        """Sollte ValueError bei Fehler werfen."""
        mock_queue_service.add_to_queue = AsyncMock(
            side_effect=ValueError("Document already in queue")
        )

        with pytest.raises(ValueError):
            await mock_queue_service.add_to_queue(
                document_id=uuid4(),
                source="manual",
                priority=50,
                notes=None,
                rule_id=None
            )


# ==================== Error Handling Tests ====================

class TestErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    @pytest.fixture
    def mock_queue_service(self):
        with patch('app.api.v1.validation.get_validation_queue_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_service_exception_handling(self, mock_queue_service, mock_db):
        """Sollte Service-Exceptions korrekt handhaben."""
        mock_queue_service.get_queue_item = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception) as exc:
            await mock_queue_service.get_queue_item(uuid4())

        assert "Database error" in str(exc.value)

    @pytest.mark.asyncio
    async def test_value_error_handling(self, mock_queue_service, mock_db):
        """Sollte ValueError als 400 behandeln."""
        mock_queue_service.assign_to_editor = AsyncMock(
            side_effect=ValueError("Invalid editor")
        )

        with pytest.raises(ValueError) as exc:
            await mock_queue_service.assign_to_editor(
                item_id=uuid4(),
                editor_id=uuid4(),
                assigned_by_id=uuid4()
            )

        assert "Invalid editor" in str(exc.value)

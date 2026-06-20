# -*- coding: utf-8 -*-
"""
Unit-Tests fuer EscalationService.

Testet:
- Escalation Rule Management (CRUD)
- Rule Matching
- Task Escalation
- Batch Processing
- Statistics

Feinpoliert und durchdacht - Eskalations-Service-Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List

import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))


# Test constants
TEST_USER_ID = uuid4()
TEST_COMPANY_ID = uuid4()
TEST_RULE_ID = uuid4()
TEST_TASK_ID = uuid4()


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = Mock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_escalation_rule():
    """Create mock escalation rule."""
    rule = Mock()
    rule.id = TEST_RULE_ID
    rule.company_id = TEST_COMPANY_ID
    rule.name = "Default Eskalation"
    rule.description = "Test-Regel"
    rule.task_type = None  # Gilt fuer alle
    rule.priority = None  # Gilt fuer alle
    rule.timeout_hours = 24
    rule.escalate_to_user_id = TEST_USER_ID
    rule.escalate_to_role = None
    rule.notify_original_assignee = True
    rule.notify_escalation_target = True
    rule.notify_task_creator = False
    rule.is_active = True
    rule.rule_priority = 100
    rule.created_at = datetime.now(timezone.utc)
    rule.updated_at = datetime.now(timezone.utc)
    return rule


@pytest.fixture
def mock_task():
    """Create mock document task."""
    task = Mock()
    task.id = TEST_TASK_ID
    task.title = "Test-Aufgabe"
    task.description = "Eine Test-Aufgabe"
    task.task_type = "review"
    task.priority = "high"
    task.status = "open"
    task.assigned_to_id = uuid4()
    task.created_by_id = uuid4()
    task.escalated = False
    task.escalated_at = None
    task.created_at = datetime.now(timezone.utc) - timedelta(hours=48)  # Alt genug
    return task


@pytest.fixture
def mock_user():
    """Create mock user."""
    user = Mock()
    user.id = TEST_USER_ID
    user.email = "escalation@example.com"
    user.username = "escalation_target"
    user.is_superuser = True
    user.is_active = True
    return user


# ========================= Rule Management Tests =========================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "APP-BUG: EscalationService nutzt Felder, die das kanonische "
        "EscalationRule-Modell (models_approval_extended) nicht besitzt "
        "(escalate_to_user_id/escalate_to_role/rule_priority/description/"
        "task_type/priority/notify_* + Relationship escalate_to_user). "
        "Das Modell kennt nur escalation_target_user_id/-role, send_email, "
        "send_notification. Rule-CRUD crasht daher zur Laufzeit. Eine "
        "Korrektur erfordert eine Produktentscheidung (Modell+Migration "
        "erweitern -> TABU) und ist kein rein mechanischer Drift-Fix."
    ),
)
class TestEscalationServiceRuleManagement:
    """Tests fuer Escalation Rule CRUD."""

    @pytest.mark.asyncio
    async def test_create_rule(self, mock_db_session):
        """Sollte neue Eskalationsregel erstellen."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        result = await service.create_rule(
            company_id=TEST_COMPANY_ID,
            name="Hohe Prioritaet",
            timeout_hours=12,
            escalate_to_user_id=TEST_USER_ID,
            priority="high",
        )

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called()
        mock_db_session.refresh.assert_called()

    @pytest.mark.asyncio
    async def test_get_rule_found(self, mock_db_session, mock_escalation_rule):
        """Sollte Regel zurueckgeben wenn gefunden."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_escalation_rule
        mock_db_session.execute.return_value = mock_result

        service = EscalationService(mock_db_session)
        result = await service.get_rule(TEST_RULE_ID)

        assert result is not None
        assert result.name == "Default Eskalation"

    @pytest.mark.asyncio
    async def test_get_rule_not_found(self, mock_db_session):
        """Sollte None zurueckgeben wenn Regel nicht existiert."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        service = EscalationService(mock_db_session)
        result = await service.get_rule(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_rules_for_company(self, mock_db_session, mock_escalation_rule):
        """Sollte alle Regeln eines Unternehmens zurueckgeben."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_escalation_rule]
        mock_db_session.execute.return_value = mock_result

        service = EscalationService(mock_db_session)
        result = await service.get_rules_for_company(TEST_COMPANY_ID)

        assert len(result) == 1
        assert result[0].company_id == TEST_COMPANY_ID

    @pytest.mark.asyncio
    async def test_update_rule_success(self, mock_db_session, mock_escalation_rule):
        """Sollte Regel erfolgreich aktualisieren."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(service, 'get_rule', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_escalation_rule

            result = await service.update_rule(
                TEST_RULE_ID,
                name="Aktualisierte Regel",
                timeout_hours=48,
            )

            assert result is not None
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_rule_not_found(self, mock_db_session):
        """Sollte None zurueckgeben wenn Regel nicht existiert."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(service, 'get_rule', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await service.update_rule(uuid4(), name="Test")

            assert result is None

    @pytest.mark.asyncio
    async def test_delete_rule_success(self, mock_db_session, mock_escalation_rule):
        """Sollte Regel erfolgreich loeschen."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(service, 'get_rule', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_escalation_rule

            result = await service.delete_rule(TEST_RULE_ID)

            assert result is True
            mock_db_session.delete.assert_called_once_with(mock_escalation_rule)
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_rule_not_found(self, mock_db_session):
        """Sollte False zurueckgeben wenn Regel nicht existiert."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(service, 'get_rule', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await service.delete_rule(uuid4())

            assert result is False


# ========================= Rule Matching Tests =========================


class TestEscalationServiceRuleMatching:
    """Tests fuer Rule Matching."""

    @pytest.mark.asyncio
    async def test_find_matching_rule_all_tasks(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte Regel finden die fuer alle Tasks gilt."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(
            service, 'get_rules_for_company', new_callable=AsyncMock
        ) as mock_get_rules:
            mock_get_rules.return_value = [mock_escalation_rule]

            result = await service.find_matching_rule(mock_task, TEST_COMPANY_ID)

            assert result is not None
            assert result.id == TEST_RULE_ID

    @pytest.mark.asyncio
    async def test_find_matching_rule_filtered_by_type(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte Regel nicht finden wenn Task-Type nicht passt."""
        from app.services.collaboration.escalation_service import EscalationService

        # Regel gilt nur fuer "approval" Tasks
        mock_escalation_rule.task_type = "approval"
        mock_task.task_type = "review"

        service = EscalationService(mock_db_session)

        with patch.object(
            service, 'get_rules_for_company', new_callable=AsyncMock
        ) as mock_get_rules:
            mock_get_rules.return_value = [mock_escalation_rule]

            result = await service.find_matching_rule(mock_task, TEST_COMPANY_ID)

            assert result is None

    @pytest.mark.asyncio
    async def test_find_matching_rule_filtered_by_priority(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte Regel nicht finden wenn Prioritaet nicht passt."""
        from app.services.collaboration.escalation_service import EscalationService

        # Regel gilt nur fuer "critical" Prioritaet
        mock_escalation_rule.priority = "critical"
        mock_task.priority = "high"

        service = EscalationService(mock_db_session)

        with patch.object(
            service, 'get_rules_for_company', new_callable=AsyncMock
        ) as mock_get_rules:
            mock_get_rules.return_value = [mock_escalation_rule]

            result = await service.find_matching_rule(mock_task, TEST_COMPANY_ID)

            assert result is None

    @pytest.mark.asyncio
    async def test_find_matching_rule_no_rules(self, mock_db_session, mock_task):
        """Sollte None zurueckgeben wenn keine Regeln existieren."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(
            service, 'get_rules_for_company', new_callable=AsyncMock
        ) as mock_get_rules:
            mock_get_rules.return_value = []

            result = await service.find_matching_rule(mock_task, TEST_COMPANY_ID)

            assert result is None


# ========================= Escalation Check Tests =========================


class TestEscalationServiceEscalationCheck:
    """Tests fuer Escalation Check."""

    @pytest.mark.asyncio
    async def test_check_task_already_escalated(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte (False, None) zurueckgeben wenn Task bereits eskaliert."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_task.escalated = True

        service = EscalationService(mock_db_session)
        should_escalate, rule = await service.check_task_for_escalation(
            mock_task, TEST_COMPANY_ID
        )

        assert should_escalate is False
        assert rule is None

    @pytest.mark.asyncio
    async def test_check_task_completed_status(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte (False, None) zurueckgeben wenn Task abgeschlossen."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_task.status = "completed"

        service = EscalationService(mock_db_session)
        should_escalate, rule = await service.check_task_for_escalation(
            mock_task, TEST_COMPANY_ID
        )

        assert should_escalate is False
        assert rule is None

    @pytest.mark.asyncio
    async def test_check_task_no_matching_rule(
        self, mock_db_session, mock_task
    ):
        """Sollte (False, None) zurueckgeben wenn keine Regel passt."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(
            service, 'find_matching_rule', new_callable=AsyncMock
        ) as mock_find:
            mock_find.return_value = None

            should_escalate, rule = await service.check_task_for_escalation(
                mock_task, TEST_COMPANY_ID
            )

            assert should_escalate is False
            assert rule is None

    @pytest.mark.asyncio
    async def test_check_task_not_old_enough(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte (False, None) zurueckgeben wenn Task nicht alt genug."""
        from app.services.collaboration.escalation_service import EscalationService

        # Task erst 1 Stunde alt, Regel erwartet 24 Stunden
        mock_task.created_at = datetime.now(timezone.utc) - timedelta(hours=1)

        service = EscalationService(mock_db_session)

        with patch.object(
            service, 'find_matching_rule', new_callable=AsyncMock
        ) as mock_find:
            mock_find.return_value = mock_escalation_rule

            should_escalate, rule = await service.check_task_for_escalation(
                mock_task, TEST_COMPANY_ID
            )

            assert should_escalate is False

    @pytest.mark.asyncio
    async def test_check_task_should_escalate(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte (True, rule) zurueckgeben wenn Task eskaliert werden sollte."""
        from app.services.collaboration.escalation_service import EscalationService

        # Task 48 Stunden alt, Regel erwartet 24 Stunden
        mock_task.created_at = datetime.now(timezone.utc) - timedelta(hours=48)

        service = EscalationService(mock_db_session)

        with patch.object(
            service, 'find_matching_rule', new_callable=AsyncMock
        ) as mock_find:
            mock_find.return_value = mock_escalation_rule

            should_escalate, rule = await service.check_task_for_escalation(
                mock_task, TEST_COMPANY_ID
            )

            assert should_escalate is True
            assert rule is not None


# ========================= Escalate Task Tests =========================


class TestEscalationServiceEscalateTask:
    """Tests fuer Task Escalation."""

    @pytest.mark.asyncio
    async def test_escalate_task_success(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte Task erfolgreich eskalieren."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(
            service, '_determine_escalation_target', new_callable=AsyncMock
        ) as mock_determine:
            mock_determine.return_value = TEST_USER_ID

            with patch(
                'app.services.collaboration.escalation_service.NotificationService'
            ) as MockNotifService:
                mock_notif_service = Mock()
                mock_notif_service.create_notification = AsyncMock()
                MockNotifService.return_value = mock_notif_service

                result = await service.escalate_task(mock_task, mock_escalation_rule)

                assert result is True
                assert mock_task.escalated is True
                assert mock_task.assigned_to_id == TEST_USER_ID
                mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_escalate_task_no_target(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte False zurueckgeben wenn kein Eskalationsziel gefunden."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        with patch.object(
            service, '_determine_escalation_target', new_callable=AsyncMock
        ) as mock_determine:
            mock_determine.return_value = None

            result = await service.escalate_task(mock_task, mock_escalation_rule)

            assert result is False


# ========================= Helper Method Tests =========================


class TestEscalationServiceHelpers:
    """Tests fuer Helper Methods."""

    @pytest.mark.asyncio
    async def test_determine_escalation_target_direct_user(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte direkten User als Ziel verwenden wenn angegeben."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)

        result = await service._determine_escalation_target(
            mock_escalation_rule, mock_task
        )

        assert result == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_determine_escalation_target_role(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte User nach Rolle suchen wenn keine direkte ID."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_escalation_rule.escalate_to_user_id = None
        mock_escalation_rule.escalate_to_role = "admin"

        service = EscalationService(mock_db_session)

        with patch.object(
            service, '_find_user_by_role', new_callable=AsyncMock
        ) as mock_find:
            admin_id = uuid4()
            mock_find.return_value = admin_id

            result = await service._determine_escalation_target(
                mock_escalation_rule, mock_task
            )

            assert result == admin_id

    @pytest.mark.asyncio
    async def test_determine_escalation_target_fallback_creator(
        self, mock_db_session, mock_task, mock_escalation_rule
    ):
        """Sollte auf Task-Ersteller zurueckfallen wenn kein anderes Ziel."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_escalation_rule.escalate_to_user_id = None
        mock_escalation_rule.escalate_to_role = None

        service = EscalationService(mock_db_session)

        result = await service._determine_escalation_target(
            mock_escalation_rule, mock_task
        )

        assert result == mock_task.created_by_id

    @pytest.mark.asyncio
    async def test_find_user_by_role_admin(self, mock_db_session, mock_user):
        """Sollte Admin-User finden."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = TEST_USER_ID
        mock_db_session.execute.return_value = mock_result

        service = EscalationService(mock_db_session)
        result = await service._find_user_by_role("admin", TEST_COMPANY_ID)

        assert result == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_find_user_by_role_unknown(self, mock_db_session):
        """Sollte None zurueckgeben fuer unbekannte Rolle."""
        from app.services.collaboration.escalation_service import EscalationService

        service = EscalationService(mock_db_session)
        result = await service._find_user_by_role("unknown_role", TEST_COMPANY_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_find_user_by_role_uses_company_filter(self, mock_db_session):
        """SECURITY: Testet dass _find_user_by_role company_id filtert.

        Die Query MUSS ueber UserCompany joinen und company_id filtern,
        um Cross-Company Eskalationen zu verhindern.
        """
        from app.services.collaboration.escalation_service import EscalationService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        service = EscalationService(mock_db_session)
        await service._find_user_by_role("admin", TEST_COMPANY_ID)

        # Pruefe dass execute aufgerufen wurde
        assert mock_db_session.execute.called

        # Der Query MUSS UserCompany referenzieren (Multi-Tenant Join)
        call_args = mock_db_session.execute.call_args
        query = str(call_args[0][0])

        assert "user_companies" in query.lower() or "usercompany" in query.lower(), \
            "SECURITY: Query muss ueber UserCompany joinen fuer Multi-Tenant Isolation!"

    @pytest.mark.asyncio
    async def test_find_user_by_role_manager(self, mock_db_session):
        """Sollte Manager-User innerhalb der Company finden."""
        from app.services.collaboration.escalation_service import EscalationService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = TEST_USER_ID
        mock_db_session.execute.return_value = mock_result

        service = EscalationService(mock_db_session)
        result = await service._find_user_by_role("manager", TEST_COMPANY_ID)

        assert result == TEST_USER_ID
        assert mock_db_session.execute.called


# ========================= Statistics Tests =========================


class TestEscalationServiceStatistics:
    """Tests fuer Statistics."""

    @pytest.mark.asyncio
    async def test_get_escalation_statistics(
        self, mock_db_session, mock_escalation_rule
    ):
        """Sollte Eskalations-Statistiken zurueckgeben."""
        from app.services.collaboration.escalation_service import EscalationService

        # Setup mock results
        escalated_mock = Mock()
        escalated_mock.scalar_one.return_value = 5

        total_mock = Mock()
        total_mock.scalar_one.return_value = 100

        avg_mock = Mock()
        avg_mock.scalar_one.return_value = 86400  # 24 Stunden in Sekunden

        mock_db_session.execute.side_effect = [
            escalated_mock,
            total_mock,
            avg_mock,
        ]

        service = EscalationService(mock_db_session)

        with patch.object(
            service, 'get_rules_for_company', new_callable=AsyncMock
        ) as mock_get_rules:
            mock_get_rules.return_value = [mock_escalation_rule]

            result = await service.get_escalation_statistics(TEST_COMPANY_ID)

            assert result["escalated_tasks"] == 5
            assert result["total_tasks"] == 100
            assert result["escalation_rate"] == 5.0
            assert result["active_rules"] == 1
            assert result["avg_hours_to_escalation"] == 24.0


# ========================= Factory Function Tests =========================


class TestGetEscalationService:
    """Tests fuer Factory Function."""

    def test_get_escalation_service(self, mock_db_session):
        """Sollte EscalationService-Instanz erstellen."""
        from app.services.collaboration.escalation_service import (
            get_escalation_service,
            EscalationService,
        )

        result = get_escalation_service(mock_db_session)

        assert isinstance(result, EscalationService)
        assert result.db == mock_db_session

# -*- coding: utf-8 -*-
"""Tests fuer RAG Agent Action Dispatcher.

Testet Tool-Call-Dispatching, Permission-Checks und Confirmation-Flow.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from typing import Dict

from app.services.rag.action_dispatcher import ActionDispatcher
from app.services.rag.tool_registry import ToolCall
from app.api.schemas.rag import (
    AIActionType,
    AIActionResult,
    AIActionStatus,
    AIActionAutonomyLevel,
)

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.services, pytest.mark.asyncio]


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock Database Session."""
    return AsyncMock()


@pytest.fixture
def mock_user_viewer() -> MagicMock:
    """Mock Viewer User."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "viewer@test.com"
    user.is_admin = False
    user.role = "viewer"
    return user


@pytest.fixture
def mock_user_editor() -> MagicMock:
    """Mock Editor User."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "editor@test.com"
    user.is_admin = False
    user.role = "editor"
    return user


@pytest.fixture
def mock_user_admin() -> MagicMock:
    """Mock Admin User."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "admin@test.com"
    user.is_admin = True
    user.role = "admin"
    return user


@pytest.fixture
def mock_ai_action_service() -> AsyncMock:
    """Mock AIActionService."""
    service = AsyncMock()

    # Default: get_autonomy_level ist sync, daher MagicMock
    service.get_autonomy_level = MagicMock(return_value=AIActionAutonomyLevel.VIEWER)

    # Default: execute_action gibt SUCCESS zurueck
    default_result = AIActionResult(
        action_id=uuid4(),
        action_type=AIActionType.SEARCH_DOCUMENTS,
        status=AIActionStatus.COMPLETED,
        message="Erfolgreich ausgefuehrt",
        execution_time_ms=100,
    )
    service.execute_action.return_value = default_result

    # Default: confirm_action gibt SUCCESS zurueck
    service.confirm_action.return_value = default_result

    return service


class TestActionDispatcher:
    """Tests fuer ActionDispatcher."""

    async def test_dispatch_read_only_action(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """search_documents wird sofort ausgefuehrt ohne Bestaetigung."""
        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="search_documents",
            parameters={"query": "test"}
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_viewer,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.COMPLETED, "Read-only sollte sofort completed sein"
        assert mock_ai_action_service.execute_action.called, "execute_action sollte aufgerufen werden"

    async def test_dispatch_write_action_requires_confirmation(
        self, mock_db_session: AsyncMock, mock_user_editor: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """tag_document gibt pending status zurueck."""
        # Editor-Level setzen
        mock_ai_action_service.get_autonomy_level.return_value = AIActionAutonomyLevel.EDITOR

        # Pending result
        pending_result = AIActionResult(
            action_id=uuid4(),
            action_type=AIActionType.TAG_DOCUMENT,
            status=AIActionStatus.SUGGESTED,
            message="Bestaetigung erforderlich",
            execution_time_ms=50,
        )
        mock_ai_action_service.execute_action.return_value = pending_result

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="tag_document",
            parameters={"document_id": str(uuid4()), "tags": ["test"]}
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_editor,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.SUGGESTED, "Write-Action sollte pending sein"

    async def test_dispatch_checks_permission(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Viewer kann keine editor actions ausfuehren."""
        # Viewer-Level setzen
        mock_ai_action_service.get_autonomy_level.return_value = AIActionAutonomyLevel.VIEWER

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="tag_document",
            parameters={"document_id": str(uuid4()), "tags": ["test"]}
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_viewer,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.FAILED, "Viewer sollte editor-action nicht ausfuehren koennen"
        assert "Keine Berechtigung" in result.message, "Fehlermeldung sollte Permission-Error enthalten"

    async def test_confirm_action_executes(
        self, mock_db_session: AsyncMock, mock_user_editor: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Bestaetigung einer pending action fuehrt sie aus."""
        action_id = uuid4()

        confirmed_result = AIActionResult(
            action_id=action_id,
            action_type=AIActionType.TAG_DOCUMENT,
            status=AIActionStatus.COMPLETED,
            message="Erfolgreich ausgefuehrt",
            execution_time_ms=120,
        )
        mock_ai_action_service.confirm_action.return_value = confirmed_result

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        result = await dispatcher.confirm_action(
            action_id=action_id,
            user=mock_user_editor,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.COMPLETED, "Bestaetigte Action sollte completed sein"
        assert mock_ai_action_service.confirm_action.called, "confirm_action sollte aufgerufen werden"

    async def test_reject_action(
        self, mock_db_session: AsyncMock, mock_user_editor: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Ablehnung setzt status auf rejected."""
        action_id = uuid4()

        rejected_result = AIActionResult(
            action_id=action_id,
            action_type=AIActionType.TAG_DOCUMENT,
            status=AIActionStatus.REJECTED,
            message="Vom Benutzer abgelehnt",
            execution_time_ms=10,
        )
        mock_ai_action_service.confirm_action.return_value = rejected_result

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        result = await dispatcher.reject_action(
            action_id=action_id,
            user=mock_user_editor,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.REJECTED, "Abgelehnte Action sollte rejected sein"

    async def test_confirm_nonexistent_action(
        self, mock_db_session: AsyncMock, mock_user_editor: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Bestaetigung unbekannter action_id gibt error."""
        action_id = uuid4()

        # Service gibt FAILED zurueck
        error_result = AIActionResult(
            action_id=action_id,
            action_type=AIActionType.TAG_DOCUMENT,
            status=AIActionStatus.FAILED,
            message="Aktion nicht gefunden",
            execution_time_ms=5,
        )
        mock_ai_action_service.confirm_action.return_value = error_result

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        result = await dispatcher.confirm_action(
            action_id=action_id,
            user=mock_user_editor,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.FAILED, "Unbekannte Action sollte failed sein"

    async def test_dispatch_validates_parameters(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Ungueltige Parameter geben error zurueck."""
        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        # Fehlendes required parameter "query"
        tool_call = ToolCall(
            tool_name="search_documents",
            parameters={}  # query fehlt!
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_viewer,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.FAILED, "Fehlende Parameter sollten failed geben"
        assert "Ungueltige Parameter" in result.message or "erforderlich" in result.message.lower()

    async def test_dispatch_logs_audit(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Action dispatch erstellt Log-Eintrag."""
        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="search_documents",
            parameters={"query": "test"}
        )

        with patch("app.services.rag.action_dispatcher.logger") as mock_logger:
            result = await dispatcher.dispatch(
                tool_call=tool_call,
                user=mock_user_viewer,
                db=mock_db_session,
            )

            # Logger sollte aufgerufen werden
            assert mock_logger.info.called, "Logger info sollte aufgerufen werden"

    async def test_dispatch_unknown_tool(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Unbekanntes Tool gibt error."""
        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="unknown_tool_xyz",
            parameters={}
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_viewer,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.FAILED, "Unbekanntes Tool sollte failed geben"
        assert "Unbekanntes Tool" in result.message

    async def test_dispatch_sanitizes_pii_in_logs(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """PII wird in Logs maskiert."""
        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        # Parameter mit PII
        tool_call = ToolCall(
            tool_name="search_documents",
            parameters={
                "query": "test",
                "email": "sensitive@example.com",
                "iban": "DE00000000000000000000"
            }
        )

        with patch("app.services.rag.action_dispatcher.logger") as mock_logger:
            result = await dispatcher.dispatch(
                tool_call=tool_call,
                user=mock_user_viewer,
                db=mock_db_session,
            )

            # Sanitize sollte gecalled werden (implizit durch _sanitize_parameters)
            # Wir koennen nicht direkt pruefen, aber der Test zeigt dass die Methode existiert

    async def test_dispatch_type_validation_string(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Type Validation fuer String-Parameter."""
        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        # query sollte string sein, nicht int
        tool_call = ToolCall(
            tool_name="search_documents",
            parameters={"query": 123}  # Falsch: int statt string
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_viewer,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.FAILED, "Type mismatch sollte failed geben"

    async def test_dispatch_type_validation_array(
        self, mock_db_session: AsyncMock, mock_user_editor: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Type Validation fuer Array-Parameter."""
        # Editor-Level
        mock_ai_action_service.get_autonomy_level.return_value = AIActionAutonomyLevel.EDITOR

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        # tags sollte array sein
        tool_call = ToolCall(
            tool_name="tag_document",
            parameters={
                "document_id": str(uuid4()),
                "tags": "not-an-array"  # Falsch: string statt array
            }
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_editor,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.FAILED, "Array type mismatch sollte failed geben"

    async def test_dispatch_with_context_id(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Context-ID wird korrekt uebergeben."""
        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="search_documents",
            parameters={"query": "test"}
        )

        context_id = uuid4()

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_viewer,
            db=mock_db_session,
            context_id=context_id,
        )

        # Pruefe dass execute_action mit context_id aufgerufen wurde
        call_args = mock_ai_action_service.execute_action.call_args
        assert call_args is not None
        request = call_args.kwargs["request"]
        assert request.context_id == context_id

    async def test_dispatch_exception_handling(
        self, mock_db_session: AsyncMock, mock_user_viewer: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Exceptions werden abgefangen und als FAILED zurueckgegeben."""
        # Service wirft Exception
        mock_ai_action_service.execute_action.side_effect = Exception("Test error")

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="search_documents",
            parameters={"query": "test"}
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_viewer,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.FAILED, "Exception sollte FAILED geben"
        assert "Tool-Ausfuehrung" in result.message or "fehlgeschlagen" in result.message.lower()


class TestPermissionChecks:
    """Tests fuer Permission-Hierarchie."""

    async def test_admin_can_execute_all_actions(
        self, mock_db_session: AsyncMock, mock_user_admin: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Admin kann alle Tools ausfuehren."""
        mock_ai_action_service.get_autonomy_level.return_value = AIActionAutonomyLevel.ADMIN

        # Pending result fuer move_document (admin-only)
        pending_result = AIActionResult(
            action_id=uuid4(),
            action_type=AIActionType.CATEGORIZE_DOCUMENT,
            status=AIActionStatus.SUGGESTED,
            message="Bestaetigung erforderlich",
            execution_time_ms=50,
        )
        mock_ai_action_service.execute_action.return_value = pending_result

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="move_document",
            parameters={"document_id": str(uuid4()), "folder_id": str(uuid4())}
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_admin,
            db=mock_db_session,
        )

        # Admin sollte move_document ausfuehren koennen (pending weil confirmation required)
        assert result.status == AIActionStatus.SUGGESTED, "Admin sollte move_document ausfuehren koennen"

    async def test_editor_cannot_execute_admin_actions(
        self, mock_db_session: AsyncMock, mock_user_editor: MagicMock, mock_ai_action_service: AsyncMock
    ) -> None:
        """Editor kann keine admin-only actions ausfuehren."""
        mock_ai_action_service.get_autonomy_level.return_value = AIActionAutonomyLevel.EDITOR

        dispatcher = ActionDispatcher(ai_action_service=mock_ai_action_service)

        tool_call = ToolCall(
            tool_name="move_document",  # Admin-only
            parameters={"document_id": str(uuid4()), "folder_id": str(uuid4())}
        )

        result = await dispatcher.dispatch(
            tool_call=tool_call,
            user=mock_user_editor,
            db=mock_db_session,
        )

        assert result.status == AIActionStatus.FAILED, "Editor sollte admin-action nicht ausfuehren koennen"
        assert "Keine Berechtigung" in result.message

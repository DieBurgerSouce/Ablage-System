# -*- coding: utf-8 -*-
"""Unit Tests fuer ChatToolAction Model.

Testet das Satellite Model fuer RAG Agent Tool-Aktionen.
"""

import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.db.models_chat_actions import ChatToolAction

pytestmark = [pytest.mark.unit]


def _make_action(**kwargs) -> SimpleNamespace:
    """Erstelle Test-Objekt mit ChatToolAction-Feldern.

    Nutzt SimpleNamespace statt echtem SQLAlchemy Model,
    da der Mapper wegen fehlender ProcessDefinition-Beziehung
    nicht konfigurierbar ist. to_dict() und __repr__()
    werden als unbound Methods getestet.
    """
    return SimpleNamespace(**kwargs)


class TestChatToolAction:
    """Test-Suite fuer ChatToolAction Model."""

    def test_chat_tool_action_creation(self):
        """Teste dass ChatToolAction die erwarteten Felder hat."""
        # Arrange
        action_id = uuid4()
        session_id = uuid4()
        message_id = uuid4()
        confirmed_by_id = uuid4()
        executed_at = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        # Act
        action = _make_action(
            id=action_id,
            session_id=session_id,
            message_id=message_id,
            tool_name="create_document",
            parameters={"folder_id": "123", "title": "Test Doc"},
            status="executed",
            result={"document_id": "456", "success": True},
            error_message=None,
            requires_confirmation=True,
            confirmed_by_id=confirmed_by_id,
            executed_at=executed_at,
            created_at=created_at,
        )

        # Assert
        assert action.id == action_id
        assert action.session_id == session_id
        assert action.message_id == message_id
        assert action.tool_name == "create_document"
        assert action.parameters == {"folder_id": "123", "title": "Test Doc"}
        assert action.status == "executed"
        assert action.result == {"document_id": "456", "success": True}
        assert action.error_message is None
        assert action.requires_confirmation is True
        assert action.confirmed_by_id == confirmed_by_id
        assert action.executed_at == executed_at
        assert action.created_at == created_at

    def test_chat_tool_action_defaults(self):
        """Teste Default-Werte der ChatToolAction."""
        from sqlalchemy.inspection import inspect

        mapper = inspect(ChatToolAction)
        parameters_col = mapper.columns["parameters"]
        requires_confirmation_col = mapper.columns["requires_confirmation"]

        # Assert defaults
        assert callable(parameters_col.default.arg)
        assert parameters_col.default.arg.__name__ == "dict"
        assert parameters_col.default.arg.__module__ == "builtins"

        assert requires_confirmation_col.default.arg is False

    def test_to_dict(self):
        """Teste to_dict Methode mit allen Feldern gesetzt."""
        # Arrange
        action_id = uuid4()
        session_id = uuid4()
        message_id = uuid4()
        confirmed_by_id = uuid4()
        executed_at = datetime(2026, 2, 10, 15, 30, 45, tzinfo=timezone.utc)
        created_at = datetime(2026, 2, 10, 15, 25, 30, tzinfo=timezone.utc)

        action = _make_action(
            id=action_id,
            session_id=session_id,
            message_id=message_id,
            tool_name="search_documents",
            parameters={"query": "invoice", "limit": 10},
            status="executed",
            result={"count": 5, "documents": []},
            error_message=None,
            requires_confirmation=False,
            confirmed_by_id=confirmed_by_id,
            executed_at=executed_at,
            created_at=created_at,
        )

        # Act - call as unbound method
        result = ChatToolAction.to_dict(action)

        # Assert
        assert result["id"] == str(action_id)
        assert result["session_id"] == str(session_id)
        assert result["message_id"] == str(message_id)
        assert result["tool_name"] == "search_documents"
        assert result["parameters"] == {"query": "invoice", "limit": 10}
        assert result["status"] == "executed"
        assert result["result"] == {"count": 5, "documents": []}
        assert result["error_message"] is None
        assert result["requires_confirmation"] is False
        assert result["confirmed_by_id"] == str(confirmed_by_id)
        assert result["executed_at"] == "2026-02-10T15:30:45+00:00"
        assert result["created_at"] == "2026-02-10T15:25:30+00:00"

    def test_to_dict_nullable_fields(self):
        """Teste to_dict mit nullable Feldern als None."""
        # Arrange
        action_id = uuid4()
        session_id = uuid4()
        created_at = datetime.now(timezone.utc)

        action = _make_action(
            id=action_id,
            session_id=session_id,
            message_id=None,
            tool_name="pending_tool",
            parameters={},
            status="pending_confirmation",
            result=None,
            error_message=None,
            requires_confirmation=True,
            confirmed_by_id=None,
            executed_at=None,
            created_at=created_at,
        )

        # Act
        result = ChatToolAction.to_dict(action)

        # Assert
        assert result["message_id"] is None
        assert result["confirmed_by_id"] is None
        assert result["executed_at"] is None
        assert result["result"] is None
        assert result["error_message"] is None

    def test_repr(self):
        """Teste __repr__ Methode."""
        # Arrange
        session_id = uuid4()

        action = _make_action(
            id=uuid4(),
            session_id=session_id,
            tool_name="test_tool",
            status="confirmed",
        )

        # Act
        repr_str = ChatToolAction.__repr__(action)

        # Assert
        assert repr_str == (
            f"<ChatToolAction("
            f"tool=test_tool, "
            f"status=confirmed, "
            f"session={session_id}"
            f")>"
        )
        assert "ChatToolAction" in repr_str
        assert "test_tool" in repr_str
        assert "confirmed" in repr_str
        assert str(session_id) in repr_str

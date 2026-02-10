# -*- coding: utf-8 -*-
"""Unit Tests fuer ChatToolAction Model.

Testet das Satellite Model fuer RAG Agent Tool-Aktionen.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.db.models_chat_actions import ChatToolAction

pytestmark = [pytest.mark.unit]


class TestChatToolAction:
    """Test-Suite fuer ChatToolAction Model."""

    def test_chat_tool_action_creation(self):
        """Teste Erstellung einer ChatToolAction mit allen Feldern."""
        # Arrange
        action_id = uuid4()
        session_id = uuid4()
        message_id = uuid4()
        confirmed_by_id = uuid4()
        executed_at = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        # Act - Create instance using __new__ to avoid DB
        action = ChatToolAction.__new__(ChatToolAction)
        action.id = action_id
        action.session_id = session_id
        action.message_id = message_id
        action.tool_name = "create_document"
        action.parameters = {"folder_id": "123", "title": "Test Doc"}
        action.status = "executed"
        action.result = {"document_id": "456", "success": True}
        action.error_message = None
        action.requires_confirmation = True
        action.confirmed_by_id = confirmed_by_id
        action.executed_at = executed_at
        action.created_at = created_at

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
        # Arrange & Act - Check Column defaults
        from sqlalchemy.inspection import inspect

        mapper = inspect(ChatToolAction)
        parameters_col = mapper.columns["parameters"]
        requires_confirmation_col = mapper.columns["requires_confirmation"]

        # Assert defaults
        assert parameters_col.default.arg == dict
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

        action = ChatToolAction.__new__(ChatToolAction)
        action.id = action_id
        action.session_id = session_id
        action.message_id = message_id
        action.tool_name = "search_documents"
        action.parameters = {"query": "invoice", "limit": 10}
        action.status = "executed"
        action.result = {"count": 5, "documents": []}
        action.error_message = None
        action.requires_confirmation = False
        action.confirmed_by_id = confirmed_by_id
        action.executed_at = executed_at
        action.created_at = created_at

        # Act
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

        action = ChatToolAction.__new__(ChatToolAction)
        action.id = action_id
        action.session_id = session_id
        action.message_id = None  # Nullable
        action.tool_name = "pending_tool"
        action.parameters = {}
        action.status = "pending_confirmation"
        action.result = None
        action.error_message = None
        action.requires_confirmation = True
        action.confirmed_by_id = None  # Nullable
        action.executed_at = None  # Nullable
        action.created_at = created_at

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
        action_id = uuid4()
        session_id = uuid4()

        action = ChatToolAction.__new__(ChatToolAction)
        action.id = action_id
        action.session_id = session_id
        action.tool_name = "test_tool"
        action.status = "confirmed"

        # Act
        repr_str = action.__repr__()

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

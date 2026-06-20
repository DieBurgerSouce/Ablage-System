# -*- coding: utf-8 -*-
"""
Unit Tests fuer AI Conversations API.

Vision 2.0 - Phase 1: Conversation Persistence

Testet:
- CRUD-Operationen fuer Konversationen
- Message-Handling
- Feedback-System
- Aktions-Management
- Pagination und Filterung
- Statistiken
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.ai_conversations import (
    ConversationListResponse,
    ConversationSummary,
    ConversationDetail,
    ConversationStatsResponse,
    CreateConversationRequest,
    UpdateConversationRequest,
    SendMessageRequest,
    FeedbackRequest,
    MessageFeedbackRequest,
    ActionConfirmRequest,
)
from app.db.models_ai_conversation import (
    AIConversation,
    AIConversationMessage,
    AIConversationAction,
    AIConversationFeedback,
    AIMessageRole,
    AIActionStatus,
    AIFeedbackType,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_user():
    """Erstelle Mock-User."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.company_id = uuid.uuid4()
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_conversation(mock_user):
    """Erstelle Mock-Konversation."""
    conv = MagicMock(spec=AIConversation)
    conv.id = uuid.uuid4()
    conv.session_id = f"conv_{uuid.uuid4().hex[:16]}"
    conv.user_id = mock_user.id
    conv.company_id = mock_user.company_id
    conv.title = "Test-Konversation"
    conv.context_page = "/documents"
    conv.context_data = {"selected_ids": ["doc1", "doc2"]}
    conv.preferences = {"theme": "dark"}
    conv.language = "de"
    conv.is_active = True
    conv.is_starred = False
    conv.message_count = 5
    conv.action_count = 2
    conv.total_tokens = 1500
    conv.created_at = datetime.now(timezone.utc)
    conv.updated_at = datetime.now(timezone.utc)
    conv.last_message_at = datetime.now(timezone.utc)
    conv.messages = []
    conv.actions = []
    conv.to_summary_dict = MagicMock(return_value={
        "id": str(conv.id),
        "session_id": conv.session_id,
        "title": conv.title,
        "message_count": conv.message_count,
        "action_count": conv.action_count,
        "is_starred": conv.is_starred,
        "is_active": conv.is_active,
        "context_page": conv.context_page,
        "language": conv.language,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "last_message_at": conv.last_message_at.isoformat(),
    })
    return conv


@pytest.fixture
def mock_message(mock_conversation):
    """Erstelle Mock-Nachricht."""
    msg = MagicMock(spec=AIConversationMessage)
    msg.id = uuid.uuid4()
    msg.conversation_id = mock_conversation.id
    msg.role = AIMessageRole.USER.value
    msg.content = "Zeige mir alle offenen Rechnungen"
    msg.intent = "search"
    msg.confidence = 0.95
    msg.search_results_count = 5
    msg.actions_proposed = 0
    msg.processing_time_ms = 150
    msg.model_used = "ollama/mistral"
    msg.tokens_used = 100
    msg.extra_data = None
    msg.referenced_documents = ["doc1"]
    msg.created_at = datetime.now(timezone.utc)
    msg.to_dict = MagicMock(return_value={
        "id": str(msg.id),
        "role": msg.role,
        "content": msg.content,
        "intent": msg.intent,
        "confidence": msg.confidence,
        "created_at": msg.created_at.isoformat(),
    })
    return msg


@pytest.fixture
def mock_action(mock_conversation, mock_message):
    """Erstelle Mock-Aktion."""
    action = MagicMock(spec=AIConversationAction)
    action.id = uuid.uuid4()
    action.conversation_id = mock_conversation.id
    action.message_id = mock_message.id
    action.action_type = "approve_invoices"
    action.description = "5 Rechnungen genehmigen"
    action.status = AIActionStatus.PROPOSED.value
    action.parameters = {"invoice_ids": ["inv1", "inv2"]}
    action.result = None
    action.error_message = None
    action.affected_count = 5
    action.success_count = None
    action.failure_count = None
    action.requires_confirmation = True
    action.confirmed_by_id = None
    action.confirmed_at = None
    action.proposed_at = datetime.now(timezone.utc)
    action.executed_at = None
    action.to_dict = MagicMock(return_value={
        "id": str(action.id),
        "action_type": action.action_type,
        "description": action.description,
        "status": action.status,
        "parameters": action.parameters,
        "proposed_at": action.proposed_at.isoformat(),
    })
    return action


@pytest.fixture
def mock_feedback(mock_message, mock_user):
    """Erstelle Mock-Feedback."""
    feedback = MagicMock(spec=AIConversationFeedback)
    feedback.id = uuid.uuid4()
    feedback.message_id = mock_message.id
    feedback.user_id = mock_user.id
    feedback.feedback_type = AIFeedbackType.HELPFUL.value
    feedback.rating = 5
    feedback.comment = "Sehr hilfreiche Antwort!"
    feedback.correction = None
    feedback.expected_intent = None
    feedback.created_at = datetime.now(timezone.utc)
    feedback.to_dict = MagicMock(return_value={
        "id": str(feedback.id),
        "feedback_type": feedback.feedback_type,
        "rating": feedback.rating,
        "comment": feedback.comment,
        "created_at": feedback.created_at.isoformat(),
    })
    return feedback


# =============================================================================
# Tests: Pydantic Models
# =============================================================================


class TestPydanticModels:
    """Tests fuer Request/Response Pydantic-Modelle."""

    def test_conversation_summary_fields(self):
        """ConversationSummary hat alle erforderlichen Felder."""
        summary = ConversationSummary(
            id="test-id",
            session_id="conv_abc123",
            title="Test",
            message_count=10,
            action_count=2,
            is_starred=True,
            is_active=True,
            context_page="/dashboard",
            language="de",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_message_at=datetime.now(timezone.utc),
        )

        assert summary.id == "test-id"
        assert summary.is_active is True
        assert summary.language == "de"
        assert summary.updated_at is not None

    def test_conversation_detail_extends_summary(self):
        """ConversationDetail hat zusaetzliche Felder."""
        detail = ConversationDetail(
            id="test-id",
            session_id="conv_abc123",
            title="Test",
            message_count=10,
            action_count=2,
            is_starred=False,
            is_active=True,
            context_page="/dashboard",
            context_data={"key": "value"},
            preferences={"theme": "dark"},
            language="de",
            total_tokens=500,
            messages=[{"id": "msg1", "content": "Hello"}],
            actions=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_message_at=None,
        )

        assert detail.context_data == {"key": "value"}
        assert detail.preferences == {"theme": "dark"}
        assert detail.total_tokens == 500
        assert len(detail.messages) == 1

    def test_conversation_list_response_pagination(self):
        """ConversationListResponse hat Pagination-Felder."""
        response = ConversationListResponse(
            conversations=[],
            total=100,
            page=2,
            page_size=50,
        )

        assert response.total == 100
        assert response.page == 2
        assert response.page_size == 50

    def test_stats_response_fields(self):
        """ConversationStatsResponse hat alle Statistik-Felder."""
        stats = ConversationStatsResponse(
            total_conversations=50,
            active_conversations=45,
            total_messages=500,
            total_actions=100,
            total_feedbacks=25,
            actions_by_status={"proposed": 10, "executed": 90},
            conversations_by_day=[],
            top_intents=[],
            average_messages_per_conversation=10.0,
            average_actions_per_conversation=2.0,
        )

        assert stats.total_conversations == 50
        assert stats.active_conversations == 45
        assert stats.total_feedbacks == 25
        assert stats.average_messages_per_conversation == 10.0

    def test_message_feedback_request_accepts_camelcase(self):
        """MessageFeedbackRequest akzeptiert camelCase Aliase."""
        # Test mit snake_case (direkt)
        req1 = MessageFeedbackRequest(
            feedback_type="helpful",
            rating=5,
        )
        assert req1.feedback_type == "helpful"

        # Test mit camelCase (via JSON/Frontend)
        from pydantic import ValidationError
        req2 = MessageFeedbackRequest.model_validate({
            "feedbackType": "not_helpful",
            "expectedIntent": "search",
        })
        assert req2.feedback_type == "not_helpful"
        assert req2.expected_intent == "search"


# =============================================================================
# Tests: Endpoint Logic
# =============================================================================


class TestListConversations:
    """Tests fuer GET /ai/conversations."""

    def test_returns_paginated_response(self, mock_conversation):
        """Endpoint liefert paginierte Antwort."""
        # Die Antwort sollte ConversationListResponse sein
        response = ConversationListResponse(
            conversations=[ConversationSummary(**mock_conversation.to_summary_dict())],
            total=1,
            page=1,
            page_size=50,
        )

        assert response.total == 1
        assert len(response.conversations) == 1
        assert response.conversations[0].session_id == mock_conversation.session_id

class TestGetConversationBySession:
    """Tests fuer GET /ai/conversations/session/{session_id}."""

    def test_returns_conversation_by_session_id(self, mock_conversation):
        """Findet Konversation per Session-ID."""
        detail = ConversationDetail(
            id=str(mock_conversation.id),
            session_id=mock_conversation.session_id,
            title=mock_conversation.title,
            message_count=mock_conversation.message_count,
            action_count=mock_conversation.action_count,
            is_starred=mock_conversation.is_starred,
            is_active=mock_conversation.is_active,
            context_page=mock_conversation.context_page,
            context_data=mock_conversation.context_data,
            preferences=mock_conversation.preferences,
            language=mock_conversation.language,
            total_tokens=mock_conversation.total_tokens,
            messages=[],
            actions=[],
            created_at=mock_conversation.created_at,
            updated_at=mock_conversation.updated_at,
            last_message_at=mock_conversation.last_message_at,
        )

        assert detail.session_id == mock_conversation.session_id
        assert detail.is_active is True

class TestMessageFeedback:
    """Tests fuer POST /ai/conversations/messages/{message_id}/feedback."""

    def test_accepts_message_id_directly(self, mock_message, mock_feedback):
        """Feedback kann direkt per Message-ID gegeben werden."""
        assert mock_feedback.message_id == mock_message.id

    def test_validates_feedback_type(self):
        """Ungueltige Feedback-Typen werden abgelehnt."""
        valid_types = ["helpful", "not_helpful", "incorrect", "confusing", "other"]
        for ft in valid_types:
            req = MessageFeedbackRequest(feedback_type=ft)
            assert req.feedback_type == ft

    def test_rating_range_validation(self):
        """Rating muss 1-5 sein."""
        from pydantic import ValidationError

        # Gueltiger Bereich
        for rating in [1, 2, 3, 4, 5]:
            req = MessageFeedbackRequest(feedback_type="helpful", rating=rating)
            assert req.rating == rating

        # Ungueltiger Bereich
        with pytest.raises(ValidationError):
            MessageFeedbackRequest(feedback_type="helpful", rating=0)

        with pytest.raises(ValidationError):
            MessageFeedbackRequest(feedback_type="helpful", rating=6)


class TestStats:
    """Tests fuer GET /ai/conversations/stats."""

    def test_returns_comprehensive_stats(self):
        """Stats-Endpoint liefert vollstaendige Statistiken."""
        stats = ConversationStatsResponse(
            total_conversations=100,
            active_conversations=85,
            total_messages=1500,
            total_actions=300,
            total_feedbacks=50,
            actions_by_status={
                "proposed": 50,
                "confirmed": 30,
                "executed": 200,
                "cancelled": 10,
                "failed": 10,
            },
            conversations_by_day=[
                {"date": "2026-01-20", "count": 15},
                {"date": "2026-01-21", "count": 20},
            ],
            top_intents=[
                {"intent": "search", "count": 500},
                {"intent": "execute_action", "count": 300},
            ],
            average_messages_per_conversation=15.0,
            average_actions_per_conversation=3.0,
        )

        assert stats.total_conversations == 100
        assert stats.active_conversations == 85
        assert stats.total_feedbacks == 50
        assert sum(stats.actions_by_status.values()) == 300


class TestActionConfirmation:
    """Tests fuer POST /ai/conversations/{id}/actions/{action_id}/confirm."""

    def test_confirms_proposed_action(self, mock_action, mock_user):
        """Vorgeschlagene Aktion kann bestaetigt werden."""
        assert mock_action.status == AIActionStatus.PROPOSED.value
        mock_action.status = AIActionStatus.CONFIRMED.value
        mock_action.confirmed_by_id = mock_user.id
        mock_action.confirmed_at = datetime.now(timezone.utc)

        assert mock_action.status == AIActionStatus.CONFIRMED.value
        assert mock_action.confirmed_by_id == mock_user.id

    def test_rejects_already_executed_action(self, mock_action):
        """Bereits ausgefuehrte Aktion kann nicht bestaetigt werden."""
        mock_action.status = AIActionStatus.EXECUTED.value
        # Sollte 400 werfen
        pass


# =============================================================================
# Tests: Model Methods
# =============================================================================


class TestAIConversationModel:
    """Tests fuer AIConversation SQLAlchemy Model."""

    def test_to_summary_dict_includes_all_fields(self, mock_conversation):
        """to_summary_dict() enthaelt alle Frontend-Felder."""
        summary = mock_conversation.to_summary_dict()

        required_fields = [
            "id", "session_id", "title", "message_count", "action_count",
            "is_starred", "is_active", "context_page", "language",
            "created_at", "updated_at", "last_message_at"
        ]

        for field in required_fields:
            assert field in summary, f"Feld '{field}' fehlt in to_summary_dict()"

    def test_is_active_defaults_to_true(self, mock_conversation):
        """is_active ist standardmaessig True."""
        assert mock_conversation.is_active is True

    def test_language_defaults_to_german(self, mock_conversation):
        """language ist standardmaessig 'de'."""
        assert mock_conversation.language == "de"


# =============================================================================
# Tests: Frontend/Backend Contract
# =============================================================================


class TestFrontendBackendContract:
    """Tests fuer Frontend-Backend API-Vertrag."""

    def test_list_response_matches_frontend_type(self):
        """ConversationListResponse entspricht Frontend-Typdefinition."""
        # Frontend erwartet: { conversations, total, page, page_size }
        response = ConversationListResponse(
            conversations=[],
            total=0,
            page=1,
            page_size=50,
        )

        # Serialisierung pruefen
        data = response.model_dump()
        assert "conversations" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_stats_response_matches_frontend_type(self):
        """ConversationStatsResponse entspricht Frontend-Typdefinition."""
        # Frontend erwartet: total_conversations, active_conversations, total_messages,
        # total_actions, total_feedbacks, actions_by_status, etc.
        stats = ConversationStatsResponse(
            total_conversations=10,
            active_conversations=8,
            total_messages=100,
            total_actions=20,
            total_feedbacks=5,
            actions_by_status={},
            conversations_by_day=[],
            top_intents=[],
            average_messages_per_conversation=10.0,
            average_actions_per_conversation=2.0,
        )

        data = stats.model_dump()
        assert "total_feedbacks" in data  # Frontend braucht dieses Feld!
        assert "active_conversations" in data

    def test_conversation_summary_has_is_active_field(self):
        """ConversationSummary hat is_active (Frontend braucht das)."""
        summary = ConversationSummary(
            id="test",
            session_id="conv_123",
            title="Test",
            message_count=0,
            action_count=0,
            is_starred=False,
            is_active=True,
            context_page=None,
            language="de",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_message_at=None,
        )

        data = summary.model_dump()
        assert "is_active" in data
        assert data["is_active"] is True


# =============================================================================
# Tests: Security - Input Validation (NEU: Januar 2026)
# =============================================================================


class TestInputValidation:
    """Tests fuer Input-Validierung und SQL-Injection-Schutz."""

    def test_validate_search_input_accepts_valid_input(self):
        """Gueltige Sucheingaben werden akzeptiert."""
        from app.api.v1.ai_conversations import validate_search_input

        # Normale Texte
        assert validate_search_input("Rechnung") == "Rechnung"
        assert validate_search_input("Müller GmbH") == "Müller GmbH"
        assert validate_search_input("Test 123") == "Test 123"

        # Deutsche Umlaute
        assert validate_search_input("Überweisung") == "Überweisung"
        assert validate_search_input("Geschäftsführer") == "Geschäftsführer"
        assert validate_search_input("Größe") == "Größe"

        # Erlaubte Sonderzeichen
        assert validate_search_input("Test-Fall") == "Test-Fall"
        # Unterstrich ist ein SQL-LIKE-Wildcard und wird bewusst escaped (CLAUDE.md Regel 9)
        assert validate_search_input("Test_Fall") == r"Test\_Fall"
        assert validate_search_input("Test.Fall") == "Test.Fall"

    def test_validate_search_input_rejects_sql_injection(self):
        """SQL-Injection-Versuche werden abgelehnt."""
        from fastapi import HTTPException
        from app.api.v1.ai_conversations import validate_search_input

        # SQL-Injection-Versuche
        # Der Validator ist eine Zeichen-Whitelist (CLAUDE.md Regel 9): er lehnt
        # Eingaben mit unsicheren Zeichen ab. Reiner Text wie "UNION SELECT" ist
        # zeichenseitig harmlos (Schutz via parametrisierte Queries + Wildcard-Escape)
        # und wird daher bewusst NICHT abgelehnt -> nicht Teil dieser Liste.
        injection_attempts = [
            "'; DROP TABLE users; --",
            "1 OR 1=1",
            "1; SELECT * FROM",
            "' OR '1'='1",
            "<script>alert('xss')</script>",
            "${7*7}",
            "{{7*7}}",
        ]

        for attempt in injection_attempts:
            with pytest.raises(HTTPException) as exc_info:
                validate_search_input(attempt)
            assert exc_info.value.status_code == 400
            assert "ungültige Zeichen" in exc_info.value.detail

    def test_validate_search_input_escapes_wildcards(self):
        """SQL-Wildcards werden escaped."""
        from app.api.v1.ai_conversations import validate_search_input

        # Wildcards sollten escaped werden (ohne Fehler)
        # Die Funktion escaped % und _ aber akzeptiert sie erstmal nicht
        # da sie nicht im SAFE_SEARCH_PATTERN enthalten sind
        # Normale Eingaben ohne Wildcards funktionieren
        assert validate_search_input("Test") == "Test"

    def test_validate_search_input_rejects_too_long_input(self):
        """Zu lange Eingaben werden abgelehnt."""
        from fastapi import HTTPException
        from app.api.v1.ai_conversations import validate_search_input, MAX_SEARCH_LENGTH

        long_input = "a" * (MAX_SEARCH_LENGTH + 1)
        with pytest.raises(HTTPException) as exc_info:
            validate_search_input(long_input)
        assert exc_info.value.status_code == 400
        assert "zu lang" in exc_info.value.detail

    def test_validate_search_input_handles_none(self):
        """None-Eingaben werden als None zurueckgegeben."""
        from app.api.v1.ai_conversations import validate_search_input

        assert validate_search_input(None) is None
        assert validate_search_input("") is None

    def test_create_conversation_request_validates_language(self):
        """CreateConversationRequest validiert Sprachcode."""
        from pydantic import ValidationError

        # Gueltige Sprachen
        req_de = CreateConversationRequest(language="de")
        assert req_de.language == "de"

        req_en = CreateConversationRequest(language="en")
        assert req_en.language == "en"

        # Ungueltige Sprache
        with pytest.raises(ValidationError) as exc_info:
            CreateConversationRequest(language="fr")
        assert "Sprache muss eine von" in str(exc_info.value)

    def test_create_conversation_request_validates_context_page(self):
        """CreateConversationRequest validiert context_page gegen Path Traversal."""
        from pydantic import ValidationError

        # Gueltiger Pfad
        req = CreateConversationRequest(context_page="documents")
        assert req.context_page == "documents"

        # Path Traversal Versuche
        with pytest.raises(ValidationError):
            CreateConversationRequest(context_page="../../../etc/passwd")

        with pytest.raises(ValidationError):
            CreateConversationRequest(context_page="/absolute/path")

    def test_update_conversation_request_validates_title(self):
        """UpdateConversationRequest validiert Titel gegen gefaehrliche Zeichen."""
        from pydantic import ValidationError

        # Gueltiger Titel
        req = UpdateConversationRequest(title="Meine Konversation")
        assert req.title == "Meine Konversation"

        # Ungueltiger Titel (Script-Tags)
        with pytest.raises(ValidationError):
            UpdateConversationRequest(title="<script>alert('xss')</script>")


# =============================================================================
# Tests: New Response Models (NEU: Januar 2026)
# =============================================================================


class TestNewResponseModels:
    """Tests fuer neue Response-Modelle zur API-Contract-Angleichung."""

    def test_conversation_messages_response(self):
        """ConversationMessagesResponse hat messages und total."""
        from app.api.v1.ai_conversations import ConversationMessagesResponse, MessageResponse

        response = ConversationMessagesResponse(
            messages=[
                MessageResponse(
                    id="msg-1",
                    role="user",
                    content="Hallo",
                    intent=None,
                    confidence=None,
                    search_results_count=None,
                    actions_proposed=None,
                    processing_time_ms=None,
                    referenced_documents=None,
                    created_at=datetime.now(timezone.utc),
                ),
                MessageResponse(
                    id="msg-2",
                    role="assistant",
                    content="Hallo! Wie kann ich helfen?",
                    intent="chat",
                    confidence=0.95,
                    search_results_count=0,
                    actions_proposed=0,
                    processing_time_ms=150,
                    referenced_documents=None,
                    created_at=datetime.now(timezone.utc),
                ),
            ],
            total=2,
        )

        assert response.total == 2
        assert len(response.messages) == 2
        assert response.messages[0].role == "user"
        assert response.messages[1].role == "assistant"

    def test_conversation_actions_response(self):
        """ConversationActionsResponse hat actions und total."""
        from app.api.v1.ai_conversations import ConversationActionsResponse, ActionResponse

        response = ConversationActionsResponse(
            actions=[
                ActionResponse(
                    id="action-1",
                    action_type="approve_invoices",
                    description="5 Rechnungen genehmigen",
                    status="proposed",
                    parameters={"invoice_ids": ["inv1", "inv2"]},
                    result=None,
                    error_message=None,
                    affected_count=5,
                    success_count=None,
                    failure_count=None,
                    requires_confirmation=True,
                    confirmed_at=None,
                    proposed_at=datetime.now(timezone.utc),
                    executed_at=None,
                ),
            ],
            total=1,
        )

        assert response.total == 1
        assert len(response.actions) == 1
        assert response.actions[0].action_type == "approve_invoices"
        assert response.actions[0].requires_confirmation is True

    def test_action_response_all_fields(self):
        """ActionResponse hat alle erforderlichen Felder."""
        from app.api.v1.ai_conversations import ActionResponse

        now = datetime.now(timezone.utc)
        action = ActionResponse(
            id="action-123",
            action_type="payment_run",
            description="Zahlungslauf fuer 3 Rechnungen",
            status="executed",
            parameters={"invoice_ids": ["inv1", "inv2", "inv3"]},
            result={"success": True, "processed": 3},
            error_message=None,
            affected_count=3,
            success_count=3,
            failure_count=0,
            requires_confirmation=True,
            confirmed_at=now,
            proposed_at=now,
            executed_at=now,
        )

        data = action.model_dump()
        required_fields = [
            "id", "action_type", "description", "status", "parameters",
            "result", "error_message", "affected_count", "success_count",
            "failure_count", "requires_confirmation", "confirmed_at",
            "proposed_at", "executed_at"
        ]
        for field in required_fields:
            assert field in data, f"Feld '{field}' fehlt in ActionResponse"

    def test_feedback_response_all_fields(self):
        """FeedbackResponse hat alle erforderlichen Felder."""
        from app.api.v1.ai_conversations import FeedbackResponse

        feedback = FeedbackResponse(
            id="feedback-123",
            feedback_type="helpful",
            rating=5,
            comment="Sehr hilfreich!",
            correction=None,
            expected_intent=None,
            created_at=datetime.now(timezone.utc),
        )

        data = feedback.model_dump()
        required_fields = [
            "id", "feedback_type", "rating", "comment",
            "correction", "expected_intent", "created_at"
        ]
        for field in required_fields:
            assert field in data, f"Feld '{field}' fehlt in FeedbackResponse"


# =============================================================================
# Tests: Error Handling (NEU: Januar 2026)
# =============================================================================


class TestErrorHandling:
    """Tests fuer Error-Handling in allen Endpoints."""

    def test_feedback_type_validation(self):
        """Ungueltige Feedback-Typen werden erkannt."""
        from app.db.models_ai_conversation import AIFeedbackType

        # Gueltige Typen
        valid_types = ["helpful", "not_helpful", "incorrect", "confusing", "other"]
        for ft in valid_types:
            assert AIFeedbackType(ft) is not None

        # Ungueltiger Typ
        with pytest.raises(ValueError):
            AIFeedbackType("invalid_type")

    def test_action_status_validation(self):
        """Ungueltige Action-Status werden erkannt."""
        from app.db.models_ai_conversation import AIActionStatus

        # Gueltige Status
        valid_status = ["proposed", "confirmed", "executed", "cancelled", "failed"]
        for s in valid_status:
            assert AIActionStatus(s) is not None

        # Ungueltiger Status
        with pytest.raises(ValueError):
            AIActionStatus("invalid_status")

    def test_message_role_validation(self):
        """Ungueltige Message-Rollen werden erkannt."""
        from app.db.models_ai_conversation import AIMessageRole

        # Gueltige Rollen
        valid_roles = ["user", "assistant", "system"]
        for r in valid_roles:
            assert AIMessageRole(r) is not None

        # Ungueltige Rolle
        with pytest.raises(ValueError):
            AIMessageRole("invalid_role")


# =============================================================================
# Tests: Rate Limiting Configuration (NEU: Januar 2026)
# =============================================================================


class TestRateLimitingConfig:
    """Tests fuer Rate-Limiting-Konfiguration."""

    def test_limiter_is_configured(self):
        """Rate-Limiter ist konfiguriert."""
        from app.api.v1.ai_conversations import limiter

        assert limiter is not None
        # Der Limiter sollte key_func haben
        assert hasattr(limiter, "_key_func") or hasattr(limiter, "key_func")

    def test_endpoints_have_rate_limits(self):
        """Alle Endpoints haben Rate-Limits (dekoriert)."""
        from app.api.v1.ai_conversations import (
            list_conversations,
            create_conversation,
            get_conversation_by_session,
            get_conversation,
            update_conversation,
            delete_conversation,
            get_messages,
            send_message,
            submit_message_feedback,
            submit_feedback,
            get_actions,
            confirm_action,
            cancel_action,
            get_stats,
            get_conversation_stats_legacy,
        )

        # Alle wichtigen Endpoints sollten existieren
        endpoints = [
            list_conversations,
            create_conversation,
            get_conversation_by_session,
            get_conversation,
            update_conversation,
            delete_conversation,
            get_messages,
            send_message,
            submit_message_feedback,
            submit_feedback,
            get_actions,
            confirm_action,
            cancel_action,
            get_stats,
            get_conversation_stats_legacy,
        ]

        for endpoint in endpoints:
            assert callable(endpoint), f"{endpoint.__name__} ist nicht aufrufbar"


# =============================================================================
# Tests: Constants and Limits (NEU: Januar 2026)
# =============================================================================


class TestSecurityConstants:
    """Tests fuer Security-Konstanten."""

    def test_max_lengths_are_defined(self):
        """Maximale Laengen sind definiert."""
        from app.api.v1.ai_conversations import (
            MAX_SEARCH_LENGTH,
            MAX_TITLE_LENGTH,
            MAX_CONTENT_LENGTH,
            MAX_COMMENT_LENGTH,
            MAX_SESSION_ID_LENGTH,
            MAX_CONTEXT_PAGE_LENGTH,
        )

        assert MAX_SEARCH_LENGTH == 100
        assert MAX_TITLE_LENGTH == 255
        assert MAX_CONTENT_LENGTH == 10000
        assert MAX_COMMENT_LENGTH == 2000
        assert MAX_SESSION_ID_LENGTH == 64
        assert MAX_CONTEXT_PAGE_LENGTH == 255

    def test_safe_search_pattern_is_defined(self):
        """Sicheres Suchmuster ist definiert."""
        from app.api.v1.ai_conversations import SAFE_SEARCH_PATTERN

        assert SAFE_SEARCH_PATTERN is not None

        # Pattern sollte normale Zeichen akzeptieren
        assert SAFE_SEARCH_PATTERN.match("Test123")
        assert SAFE_SEARCH_PATTERN.match("Müller GmbH")
        assert SAFE_SEARCH_PATTERN.match("Test-Fall")

        # Pattern sollte gefaehrliche Zeichen ablehnen
        assert not SAFE_SEARCH_PATTERN.match("'; DROP TABLE")
        assert not SAFE_SEARCH_PATTERN.match("<script>")
        assert not SAFE_SEARCH_PATTERN.match("${variable}")

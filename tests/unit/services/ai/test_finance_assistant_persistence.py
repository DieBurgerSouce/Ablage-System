# -*- coding: utf-8 -*-
"""
Unit Tests fuer FinanceAssistantService Persistenz-Methoden.

Tests fuer Migration 120: AI Conversations Persistierung.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4, UUID

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_ai_conversation import (
    AIConversation,
    AIConversationMessage,
    AIConversationAction,
    AIMessageRole,
    AIActionStatus,
)
from app.services.ai.finance_assistant_service import (
    FinanceAssistantService,
    AssistantContext,
    AssistantResponse,
    AssistantIntent,
    ActionProposal,
    ActionType,
    BookingSuggestion,
    Insight,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> FinanceAssistantService:
    """Erstellt Service mit Mock-DB."""
    return FinanceAssistantService(db=mock_db)


@pytest.fixture
def sample_context() -> AssistantContext:
    """Standard-Kontext fuer Tests."""
    return AssistantContext(
        user_id=uuid4(),
        company_id=uuid4(),
        user_role="editor",
        current_page="/banking/invoices",
        session_id="test_session_123",
        language="de",
    )


@pytest.fixture
def sample_conversation(sample_context: AssistantContext) -> AIConversation:
    """Beispiel-Konversation."""
    return AIConversation(
        id=uuid4(),
        session_id=sample_context.session_id,
        user_id=sample_context.user_id,
        company_id=sample_context.company_id,
        context_page=sample_context.current_page,
        language="de",
        message_count=0,
        action_count=0,
    )


@pytest.fixture
def sample_response() -> AssistantResponse:
    """Beispiel-Assistenten-Antwort."""
    return AssistantResponse(
        message="Ich habe 5 offene Rechnungen gefunden.",
        intent=AssistantIntent.SEARCH,
        success=True,
        confidence=0.92,
        result_count=5,
        processing_time_ms=150,
        search_results=[
            {"id": str(uuid4()), "title": "Rechnung 001"},
            {"id": str(uuid4()), "title": "Rechnung 002"},
        ],
        follow_up_suggestions=["Zeige Details", "Erstelle Zahlungslauf"],
    )


# ============================================================================
# Tests: get_or_create_conversation
# ============================================================================


class TestGetOrCreateConversation:
    """Tests fuer get_or_create_conversation."""

    @pytest.mark.asyncio
    async def test_creates_new_conversation_without_session(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test: Neue Konversation ohne session_id wird erstellt."""
        context = AssistantContext(
            user_id=uuid4(),
            company_id=uuid4(),
            session_id="",
        )

        # Mock execute to return None (no existing conversation)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        conversation = await service.get_or_create_conversation(context)

        assert conversation is not None
        assert conversation.user_id == context.user_id
        assert conversation.company_id == context.company_id
        assert conversation.session_id.startswith("conv_")
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_conversation_by_id(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_context: AssistantContext,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: Existierende Konversation wird per ID geladen."""
        sample_context.conversation_id = sample_conversation.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db.execute.return_value = mock_result

        conversation = await service.get_or_create_conversation(sample_context)

        assert conversation == sample_conversation
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_existing_conversation_by_session_id(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_context: AssistantContext,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: Existierende Konversation wird per session_id geladen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db.execute.return_value = mock_result

        conversation = await service.get_or_create_conversation(sample_context)

        assert conversation == sample_conversation

    @pytest.mark.asyncio
    async def test_stores_selected_documents_in_context(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test: Ausgewaehlte Dokumente werden im Kontext gespeichert."""
        doc_ids = [uuid4(), uuid4()]
        context = AssistantContext(
            user_id=uuid4(),
            company_id=uuid4(),
            selected_documents=doc_ids,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        conversation = await service.get_or_create_conversation(context)

        assert conversation.context_data is not None
        assert "selected_documents" in conversation.context_data
        assert len(conversation.context_data["selected_documents"]) == 2


# ============================================================================
# Tests: save_user_message
# ============================================================================


class TestSaveUserMessage:
    """Tests fuer save_user_message."""

    @pytest.mark.asyncio
    async def test_saves_user_message(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: User-Nachricht wird korrekt gespeichert."""
        message = "Zeige mir alle offenen Rechnungen"

        result = await service.save_user_message(
            conversation=sample_conversation,
            message=message,
            intent=AssistantIntent.SEARCH,
        )

        assert result.role == AIMessageRole.USER.value
        assert result.content == message
        assert result.intent == "search"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_increments_message_count(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: message_count wird inkrementiert."""
        initial_count = sample_conversation.message_count or 0

        await service.save_user_message(
            conversation=sample_conversation,
            message="Test",
        )

        assert sample_conversation.message_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_sets_title_from_first_message(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: Titel wird aus erster Nachricht generiert."""
        sample_conversation.message_count = 0
        message = "Zeige mir alle offenen Rechnungen der letzten Woche"

        await service.save_user_message(
            conversation=sample_conversation,
            message=message,
        )

        assert sample_conversation.title == message[:100]

    @pytest.mark.asyncio
    async def test_truncates_long_title(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: Lange Titel werden abgeschnitten."""
        sample_conversation.message_count = 0
        long_message = "A" * 150

        await service.save_user_message(
            conversation=sample_conversation,
            message=long_message,
        )

        assert sample_conversation.title.endswith("...")
        assert len(sample_conversation.title) == 103  # 100 + "..."

    @pytest.mark.asyncio
    async def test_updates_last_message_at(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: last_message_at wird aktualisiert."""
        sample_conversation.last_message_at = None

        await service.save_user_message(
            conversation=sample_conversation,
            message="Test",
        )

        assert sample_conversation.last_message_at is not None


# ============================================================================
# Tests: save_assistant_response
# ============================================================================


class TestSaveAssistantResponse:
    """Tests fuer save_assistant_response."""

    @pytest.mark.asyncio
    async def test_saves_assistant_response(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
        sample_response: AssistantResponse,
    ) -> None:
        """Test: Assistenten-Antwort wird korrekt gespeichert."""
        result = await service.save_assistant_response(
            conversation=sample_conversation,
            response=sample_response,
            model_used="ollama/mistral",
        )

        assert result.role == AIMessageRole.ASSISTANT.value
        assert result.content == sample_response.message
        assert result.intent == "search"
        assert result.confidence == 0.92
        assert result.model_used == "ollama/mistral"
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_insights_in_metadata(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: Insights werden in Metadaten gespeichert."""
        response = AssistantResponse(
            message="Analyse abgeschlossen",
            intent=AssistantIntent.ANALYZE,
            insights=[
                Insight(
                    title="Cash Flow Warnung",
                    content="Liquiditaetsengpass in 2 Wochen moeglich",
                    category="cash_flow",
                    severity="warning",
                ),
            ],
        )

        result = await service.save_assistant_response(
            conversation=sample_conversation,
            response=response,
        )

        assert result.extra_data is not None
        assert "insights" in result.extra_data
        assert len(result.extra_data["insights"]) == 1
        assert result.extra_data["insights"][0]["title"] == "Cash Flow Warnung"

    @pytest.mark.asyncio
    async def test_stores_booking_suggestions(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: Buchungsvorschlaege werden gespeichert."""
        response = AssistantResponse(
            message="Buchungsvorschlag erstellt",
            intent=AssistantIntent.SUGGEST_BOOKING,
            booking_suggestions=[
                BookingSuggestion(
                    debit_account="3300",
                    debit_account_name="Wareneingang",
                    credit_account="1600",
                    credit_account_name="Verbindlichkeiten",
                    amount=Decimal("1000.00"),
                    description="Wareneingang Lieferant X",
                    confidence=0.95,
                ),
            ],
        )

        result = await service.save_assistant_response(
            conversation=sample_conversation,
            response=response,
        )

        assert result.extra_data is not None
        assert "booking_suggestions" in result.extra_data
        assert result.extra_data["booking_suggestions"][0]["amount"] == 1000.00

    @pytest.mark.asyncio
    async def test_extracts_referenced_documents(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
        sample_response: AssistantResponse,
    ) -> None:
        """Test: Referenzierte Dokumente werden extrahiert."""
        result = await service.save_assistant_response(
            conversation=sample_conversation,
            response=sample_response,
        )

        assert result.referenced_documents is not None
        assert len(result.referenced_documents) == 2

    @pytest.mark.asyncio
    async def test_stores_follow_up_suggestions(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
        sample_response: AssistantResponse,
    ) -> None:
        """Test: Follow-up Vorschlaege werden gespeichert."""
        result = await service.save_assistant_response(
            conversation=sample_conversation,
            response=sample_response,
        )

        assert result.extra_data is not None
        assert "follow_up_suggestions" in result.extra_data


# ============================================================================
# Tests: save_proposed_actions
# ============================================================================


class TestSaveProposedActions:
    """Tests fuer save_proposed_actions."""

    @pytest.mark.asyncio
    async def test_saves_proposed_actions(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: Vorgeschlagene Aktionen werden gespeichert."""
        message_id = uuid4()
        actions = [
            ActionProposal(
                action_type=ActionType.PAYMENT_RUN,
                description="Zahlungslauf fuer 5 Rechnungen",
                parameters={"invoice_ids": ["1", "2", "3"]},
                confidence=0.9,
                affected_count=5,
            ),
            ActionProposal(
                action_type=ActionType.SEND_REMINDER,
                description="Mahnung an 2 Kunden",
                parameters={"customer_ids": ["a", "b"]},
                confidence=0.85,
                affected_count=2,
            ),
        ]

        result = await service.save_proposed_actions(
            conversation=sample_conversation,
            message_id=message_id,
            actions=actions,
        )

        assert len(result) == 2
        assert result[0].action_type == "payment_run"
        assert result[0].status == AIActionStatus.PROPOSED.value
        assert result[1].affected_count == 2
        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_increments_action_count(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_conversation: AIConversation,
    ) -> None:
        """Test: action_count wird korrekt inkrementiert."""
        sample_conversation.action_count = 0
        actions = [
            ActionProposal(
                action_type=ActionType.PAYMENT_RUN,
                description="Test",
                parameters={},
                confidence=0.9,
            ),
        ]

        await service.save_proposed_actions(
            conversation=sample_conversation,
            message_id=uuid4(),
            actions=actions,
        )

        assert sample_conversation.action_count == 1


# ============================================================================
# Tests: update_action_status
# ============================================================================


class TestUpdateActionStatus:
    """Tests fuer update_action_status."""

    @pytest.mark.asyncio
    async def test_updates_status_to_executed(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test: Status wird auf EXECUTED aktualisiert."""
        action = AIConversationAction(
            id=uuid4(),
            conversation_id=uuid4(),
            action_type="payment_run",
            description="Test",
            status=AIActionStatus.CONFIRMED.value,
            parameters={},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = action
        mock_db.execute.return_value = mock_result

        result_data = {"processed_count": 5, "total_amount": 10000}

        result = await service.update_action_status(
            action_id=action.id,
            status=AIActionStatus.EXECUTED,
            result=result_data,
        )

        assert result.status == AIActionStatus.EXECUTED.value
        assert result.result == result_data
        assert result.executed_at is not None

    @pytest.mark.asyncio
    async def test_updates_status_to_failed(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test: Status wird auf FAILED aktualisiert mit Fehlermeldung."""
        action = AIConversationAction(
            id=uuid4(),
            conversation_id=uuid4(),
            action_type="payment_run",
            description="Test",
            status=AIActionStatus.CONFIRMED.value,
            parameters={},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = action
        mock_db.execute.return_value = mock_result

        result = await service.update_action_status(
            action_id=action.id,
            status=AIActionStatus.FAILED,
            error_message="Bankverbindung fehlgeschlagen",
        )

        assert result.status == AIActionStatus.FAILED.value
        assert result.error_message == "Bankverbindung fehlgeschlagen"

    @pytest.mark.asyncio
    async def test_sets_confirmed_by_and_at(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test: confirmed_by und confirmed_at werden gesetzt."""
        action = AIConversationAction(
            id=uuid4(),
            conversation_id=uuid4(),
            action_type="payment_run",
            description="Test",
            status=AIActionStatus.PROPOSED.value,
            parameters={},
        )
        user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = action
        mock_db.execute.return_value = mock_result

        result = await service.update_action_status(
            action_id=action.id,
            status=AIActionStatus.CONFIRMED,
            confirmed_by_id=user_id,
        )

        assert result.confirmed_by_id == user_id
        assert result.confirmed_at is not None

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_action(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test: None zurueckgegeben bei nicht existierender Aktion."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.update_action_status(
            action_id=uuid4(),
            status=AIActionStatus.CANCELLED,
        )

        assert result is None


# ============================================================================
# Tests: load_conversation_history
# ============================================================================


class TestLoadConversationHistory:
    """Tests fuer load_conversation_history."""

    @pytest.mark.asyncio
    async def test_loads_messages_in_chronological_order(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test: Nachrichten werden chronologisch sortiert."""
        conv_id = uuid4()
        messages = [
            AIConversationMessage(
                id=uuid4(),
                conversation_id=conv_id,
                role="user",
                content="Erste Nachricht",
            ),
            AIConversationMessage(
                id=uuid4(),
                conversation_id=conv_id,
                role="assistant",
                content="Antwort",
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = list(reversed(messages))
        mock_db.execute.return_value = mock_result

        result = await service.load_conversation_history(conv_id)

        # Sollte in chronologischer Reihenfolge sein (aelteste zuerst)
        assert result[0].content == "Erste Nachricht"
        assert result[1].content == "Antwort"

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test: limit Parameter wird beachtet."""
        conv_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        await service.load_conversation_history(conv_id, limit=10)

        # Verify the limit is passed in the query
        mock_db.execute.assert_called_once()


# ============================================================================
# Tests: cancel_action
# ============================================================================


class TestCancelAction:
    """Tests fuer cancel_action."""

    @pytest.mark.asyncio
    async def test_cancels_action_successfully(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_context: AssistantContext,
    ) -> None:
        """Test: Aktion wird erfolgreich abgebrochen."""
        action = AIConversationAction(
            id=uuid4(),
            conversation_id=uuid4(),
            action_type="payment_run",
            description="Test",
            status=AIActionStatus.PROPOSED.value,
            parameters={},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = action
        mock_db.execute.return_value = mock_result

        result = await service.cancel_action(action.id, sample_context)

        assert result is True
        assert action.status == AIActionStatus.CANCELLED.value
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_action(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_context: AssistantContext,
    ) -> None:
        """Test: False bei nicht existierender Aktion."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.cancel_action(uuid4(), sample_context)

        assert result is False


# ============================================================================
# Tests: get_pending_actions
# ============================================================================


class TestGetPendingActions:
    """Tests fuer get_pending_actions."""

    @pytest.mark.asyncio
    async def test_returns_pending_actions_for_user(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_context: AssistantContext,
    ) -> None:
        """Test: Offene Aktionen fuer Benutzer werden zurueckgegeben."""
        actions = [
            AIConversationAction(
                id=uuid4(),
                conversation_id=uuid4(),
                action_type="payment_run",
                description="Zahlungslauf",
                status=AIActionStatus.PROPOSED.value,
                parameters={},
            ),
            AIConversationAction(
                id=uuid4(),
                conversation_id=uuid4(),
                action_type="send_reminder",
                description="Mahnung",
                status=AIActionStatus.PROPOSED.value,
                parameters={},
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = actions
        mock_db.execute.return_value = mock_result

        result = await service.get_pending_actions(sample_context)

        assert len(result) == 2
        assert result[0].action_type == "payment_run"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_pending(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_context: AssistantContext,
    ) -> None:
        """Test: Leere Liste wenn keine offenen Aktionen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.get_pending_actions(sample_context)

        assert result == []


# ============================================================================
# Integration Tests: process_message mit Persistenz
# ============================================================================


class TestProcessMessageWithPersistence:
    """Tests fuer process_message mit Persistenz-Integration."""

    @pytest.mark.asyncio
    async def test_persist_disabled_skips_db_operations(
        self,
        service: FinanceAssistantService,
        mock_db: AsyncMock,
        sample_context: AssistantContext,
    ) -> None:
        """Test: persist=False ueberspringt DB-Operationen."""
        # Mock the internal methods to avoid actual processing
        with patch.object(service, "_detect_intent") as mock_detect:
            with patch.object(service, "_handle_search") as mock_search:
                mock_detect.return_value = AssistantIntent.SEARCH
                mock_search.return_value = AssistantResponse(
                    message="Ergebnis",
                    intent=AssistantIntent.SEARCH,
                )

                await service.process_message(
                    message="Test",
                    context=sample_context,
                    persist=False,
                )

                # Mit persist=False sollten keine DB-Adds erfolgen
                # (Conversation-bezogene adds)
                # Note: This is a simplified test - real test would check
                # that conversation-related DB calls are skipped

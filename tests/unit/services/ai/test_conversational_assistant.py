# -*- coding: utf-8 -*-
"""
Unit Tests fuer ConversationalAssistantService.

Testet:
- Intent-Klassifikation
- NLQ-Verarbeitung (ohne echte Datenbank)
- Document Search (Mocking)
- Action Request Handling
- Session-Management
- Feedback-Verarbeitung

Feinpoliert und durchdacht - Deutsche Praezision.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.services.ai.conversational_assistant import (
    ConversationalAssistantService,
    OllamaClient,
    AssistantIntent,
    ChatContext,
    ChatResponse,
    DocumentReference,
    SuggestedAction,
    INTENT_KEYWORDS,
    get_conversational_assistant_service,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def service():
    """Erstellt eine Service-Instanz mit gemocktem Ollama.

    Wichtig: ``generate`` wird als nicht erreichbar gemockt, damit die
    Intent-Klassifikation deterministisch auf den Keyword-Klassifikator
    zurueckfaellt (die LLM-Verfeinerung ist ein Laufzeit-Verhalten und
    darf einen Offline-Unit-Test nicht von einem live laufenden Ollama
    abhaengig machen). Tests, die das LLM-Verhalten pruefen wollen,
    ueberschreiben ``svc._ollama.generate`` selbst.
    """
    with patch.object(OllamaClient, 'is_available', new_callable=AsyncMock) as mock_available:
        mock_available.return_value = True
        svc = ConversationalAssistantService()
        svc._enabled = True
        svc._ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama im Unit-Test nicht verfuegbar"))
        yield svc


@pytest.fixture
def mock_user():
    """Erstellt einen Mock-User."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_superuser = False
    return user


@pytest.fixture
def mock_db():
    """Erstellt eine Mock-DB-Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def company_id():
    """Generiert eine Company-ID."""
    return uuid4()


# =============================================================================
# INTENT-KLASSIFIKATION TESTS
# =============================================================================


class TestIntentClassification:
    """Tests fuer Intent-Klassifikation."""

    @pytest.mark.asyncio
    async def test_classify_nlq_intent(self, service):
        """Testet NLQ-Intent-Erkennung."""
        nlq_messages = [
            "Wie viele Rechnungen sind offen?",
            "Zeige mir alle Lieferanten",
            "Berechne die Summe der Ausgaben",
            "Liste alle Dokumente vom Januar",
            "Durchschnittlicher Rechnungsbetrag?",
        ]

        for message in nlq_messages:
            intent, confidence = await service.classify_intent(message)
            assert intent == AssistantIntent.NLQ, f"Erwartet NLQ fuer: {message}"
            assert confidence >= 0.5, f"Konfidenz zu niedrig fuer: {message}"

    @pytest.mark.asyncio
    async def test_classify_document_search_intent(self, service):
        """Testet Document-Search-Intent-Erkennung."""
        search_messages = [
            "Finde die Rechnung von Amazon",
            "Suche nach Vertrag 2024",
            "Wo ist der Lieferschein?",
            "Aehnliche Dokumente wie dieses",
        ]

        for message in search_messages:
            intent, confidence = await service.classify_intent(message)
            assert intent == AssistantIntent.DOCUMENT_SEARCH, f"Erwartet DOCUMENT_SEARCH fuer: {message}"
            assert confidence >= 0.5, f"Konfidenz zu niedrig fuer: {message}"

    @pytest.mark.asyncio
    async def test_classify_action_request_intent(self, service):
        """Testet Action-Request-Intent-Erkennung."""
        action_messages = [
            "Genehmige diese Rechnung",
            "Exportiere alle Dokumente",
            "Erstelle einen Bericht",
            "Verknuepfe mit Lieferant XY",
        ]

        for message in action_messages:
            intent, confidence = await service.classify_intent(message)
            assert intent == AssistantIntent.ACTION_REQUEST, f"Erwartet ACTION_REQUEST fuer: {message}"
            assert confidence >= 0.5, f"Konfidenz zu niedrig fuer: {message}"

    @pytest.mark.asyncio
    async def test_classify_general_intent(self, service):
        """Testet General-Intent-Erkennung (Fallback)."""
        general_messages = [
            "Hallo",
            "Was kannst du?",
            "Erklaere mir das Skonto",
            "Wie funktioniert das System?",
        ]

        for message in general_messages:
            intent, confidence = await service.classify_intent(message)
            assert intent == AssistantIntent.GENERAL, f"Erwartet GENERAL fuer: {message}"

    @pytest.mark.asyncio
    async def test_classify_with_context(self, service):
        """Testet Intent-Klassifikation mit Kontext."""
        context = ChatContext(
            document_id=uuid4(),
            current_view="invoice_detail",
        )

        intent, confidence = await service.classify_intent(
            "Was steht hier?",
            context=context,
        )

        # Mit Dokument-Kontext sollte es DOCUMENT_SEARCH oder GENERAL sein
        assert intent in [AssistantIntent.DOCUMENT_SEARCH, AssistantIntent.GENERAL]


# =============================================================================
# OLLAMA CLIENT TESTS
# =============================================================================


class TestOllamaClient:
    """Tests fuer OllamaClient."""

    @pytest.mark.asyncio
    async def test_is_available_returns_false_on_error(self):
        """Testet dass is_available bei Fehler False zurueckgibt."""
        client = OllamaClient(base_url="http://nonexistent:11434")
        result = await client.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_list_models_returns_empty_on_error(self):
        """Testet dass list_models bei Fehler leere Liste zurueckgibt."""
        client = OllamaClient(base_url="http://nonexistent:11434")
        models = await client.list_models()
        assert models == []

    @pytest.mark.asyncio
    async def test_generate_with_mock(self):
        """Testet Textgenerierung mit Mock."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"content": "Test response"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            client = OllamaClient()
            client._client = MagicMock()
            client._client.post = AsyncMock(return_value=mock_response)

            result = await client.generate("Test prompt")
            assert result == "Test response"


# =============================================================================
# CHAT RESPONSE TESTS
# =============================================================================


class TestChatResponse:
    """Tests fuer ChatResponse Dataclass."""

    def test_chat_response_to_dict(self):
        """Testet ChatResponse.to_dict()."""
        response = ChatResponse(
            response="Test Antwort",
            intent=AssistantIntent.GENERAL,
            sources=[
                DocumentReference(
                    id=uuid4(),
                    filename="test.pdf",
                    document_type="invoice",
                    similarity=0.85,
                    snippet="Test snippet",
                )
            ],
            actions=[
                SuggestedAction(
                    action_type="approve_document",
                    description="Dokument genehmigen",
                    parameters={"doc_id": "123"},
                    requires_confirmation=True,
                    confidence=0.9,
                )
            ],
            session_id="test-session-123",
            confidence=0.8,
            processing_time_ms=150,
            model_used="llama3.1",
            follow_up_suggestions=["Was noch?", "Zeige Details"],
        )

        result = response.to_dict()

        assert result["response"] == "Test Antwort"
        assert result["intent"] == "general"
        assert len(result["sources"]) == 1
        assert result["sources"][0]["filename"] == "test.pdf"
        assert len(result["actions"]) == 1
        assert result["actions"][0]["action_type"] == "approve_document"
        assert result["session_id"] == "test-session-123"
        assert result["confidence"] == 0.8
        assert result["processing_time_ms"] == 150


# =============================================================================
# SERVICE TESTS MIT MOCKING
# =============================================================================


class TestConversationalAssistantService:
    """Tests fuer ConversationalAssistantService."""

    @pytest.mark.asyncio
    async def test_is_available(self, service):
        """Testet Service-Verfuegbarkeitspruefung."""
        service._enabled = True
        service._ollama.is_available = AsyncMock(return_value=True)

        result = await service.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_not_available_when_disabled(self, service):
        """Testet dass Service bei Deaktivierung nicht verfuegbar ist."""
        service._enabled = False

        result = await service.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_generate_follow_ups_for_nlq(self, service):
        """Testet Follow-up-Generierung fuer NLQ."""
        response = ChatResponse(
            response="Ergebnis: 42",
            intent=AssistantIntent.NLQ,
            session_id="test",
        )

        follow_ups = await service._generate_follow_ups(
            AssistantIntent.NLQ,
            "Wie viele Rechnungen?",
            response,
        )

        assert len(follow_ups) == 3
        assert isinstance(follow_ups, list)

    @pytest.mark.asyncio
    async def test_generate_follow_ups_for_search(self, service):
        """Testet Follow-up-Generierung fuer Document Search."""
        response = ChatResponse(
            response="Gefundene Dokumente",
            intent=AssistantIntent.DOCUMENT_SEARCH,
            sources=[
                DocumentReference(
                    id=uuid4(),
                    filename="test.pdf",
                    document_type="invoice",
                    similarity=0.9,
                )
            ],
            session_id="test",
        )

        follow_ups = await service._generate_follow_ups(
            AssistantIntent.DOCUMENT_SEARCH,
            "Finde Rechnungen",
            response,
        )

        assert len(follow_ups) == 3
        # Echter Follow-up nutzt UTF-8-Umlaut: "Zeige ähnliche Dokumente"
        assert any("ähnlich" in f.lower() for f in follow_ups)


# =============================================================================
# DOCUMENT REFERENCE TESTS
# =============================================================================


class TestDocumentReference:
    """Tests fuer DocumentReference Dataclass."""

    def test_document_reference_to_dict(self):
        """Testet DocumentReference.to_dict()."""
        doc_id = uuid4()
        ref = DocumentReference(
            id=doc_id,
            filename="invoice_001.pdf",
            document_type="invoice",
            similarity=0.92,
            snippet="Rechnungsnummer: 12345",
        )

        result = ref.to_dict()

        assert result["id"] == str(doc_id)
        assert result["filename"] == "invoice_001.pdf"
        assert result["document_type"] == "invoice"
        assert result["similarity"] == 0.92
        assert result["snippet"] == "Rechnungsnummer: 12345"


# =============================================================================
# SUGGESTED ACTION TESTS
# =============================================================================


class TestSuggestedAction:
    """Tests fuer SuggestedAction Dataclass."""

    def test_suggested_action_to_dict(self):
        """Testet SuggestedAction.to_dict()."""
        action = SuggestedAction(
            action_type="approve_document",
            description="Rechnung genehmigen",
            parameters={"document_id": "abc-123", "amount": 1500.0},
            requires_confirmation=True,
            confidence=0.95,
        )

        result = action.to_dict()

        assert result["action_type"] == "approve_document"
        assert result["description"] == "Rechnung genehmigen"
        assert result["parameters"]["document_id"] == "abc-123"
        assert result["requires_confirmation"] is True
        assert result["confidence"] == 0.95


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================


class TestFactoryFunction:
    """Tests fuer Factory Function."""

    def test_get_conversational_assistant_service_returns_singleton(self):
        """Testet dass Factory Function Singleton zurueckgibt."""
        service1 = get_conversational_assistant_service()
        service2 = get_conversational_assistant_service()

        assert service1 is service2

    def test_service_instance_type(self):
        """Testet den Typ der Service-Instanz."""
        service = get_conversational_assistant_service()
        assert isinstance(service, ConversationalAssistantService)


# =============================================================================
# INTENT KEYWORDS TESTS
# =============================================================================


class TestIntentKeywords:
    """Tests fuer Intent-Keywords Konfiguration."""

    def test_intent_keywords_not_empty(self):
        """Testet dass alle Intent-Kategorien Keywords haben."""
        for intent in [AssistantIntent.NLQ, AssistantIntent.DOCUMENT_SEARCH, AssistantIntent.ACTION_REQUEST]:
            assert intent in INTENT_KEYWORDS
            assert len(INTENT_KEYWORDS[intent]) > 0

    def test_keywords_are_lowercase(self):
        """Testet dass Keywords lowercase sind."""
        for intent, keywords in INTENT_KEYWORDS.items():
            for keyword in keywords:
                assert keyword == keyword.lower(), f"Keyword '{keyword}' sollte lowercase sein"


# =============================================================================
# CONTEXT TESTS
# =============================================================================


class TestChatContext:
    """Tests fuer ChatContext Dataclass."""

    def test_chat_context_defaults(self):
        """Testet ChatContext mit Defaults."""
        context = ChatContext()

        assert context.document_id is None
        assert context.page_number is None
        assert context.selected_text is None
        assert context.current_view is None
        assert context.additional_data == {}

    def test_chat_context_with_values(self):
        """Testet ChatContext mit Werten."""
        doc_id = uuid4()
        context = ChatContext(
            document_id=doc_id,
            page_number=3,
            selected_text="Test text",
            current_view="document_detail",
            additional_data={"key": "value"},
        )

        assert context.document_id == doc_id
        assert context.page_number == 3
        assert context.selected_text == "Test text"
        assert context.current_view == "document_detail"
        assert context.additional_data == {"key": "value"}

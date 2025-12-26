# -*- coding: utf-8 -*-
"""
Tests fuer RAG API Endpoints.

Testet alle RAG API Endpunkte:
- Search (Semantic, Hybrid, Keyword)
- Chat (Messages, Sessions, Streaming)
- Session Sharing
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException


# ==================== Search Tests ====================

class TestRAGSearchEndpoints:
    """Tests fuer RAG Search API."""

    @pytest.fixture
    def mock_search_service(self):
        with patch('app.api.v1.rag.search.get_rag_search_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_semantic_search_post(self, mock_search_service, mock_db, mock_user):
        """Sollte semantische Suche via POST durchfuehren."""
        from app.api.v1.rag.search import search_chunks
        from app.api.schemas.rag import RAGSearchRequest, RAGSearchType

        chunk_id = uuid4()
        doc_id = uuid4()

        mock_search_service.semantic_search = AsyncMock(return_value=MagicMock(
            query="Test query",
            search_type="semantic",
            results=[MagicMock(
                chunk_id=chunk_id,
                document_id=doc_id,
                chunk_text="Test chunk text",
                chunk_index=0,
                page_number=1,
                section_type="body",
                similarity=0.95,
                rerank_score=0.92,
            )],
            total_results=1,
            search_time_ms=50,
            embedding_time_ms=20,
            rerank_time_ms=30,
        ))

        request = MagicMock(spec=RAGSearchRequest)
        request.query = "Test query"
        request.search_type = RAGSearchType.SEMANTIC
        request.limit = 20
        request.threshold = 0.7
        request.document_ids = None
        request.section_types = None
        request.rerank = True

        result = await search_chunks(
            request=request,
            current_user=mock_user,
            db=mock_db,
            search_service=mock_search_service,
        )

        assert result.total_results == 1
        assert len(result.results) == 1
        assert result.results[0].similarity == 0.95

    @pytest.mark.asyncio
    async def test_hybrid_search_post(self, mock_search_service, mock_db, mock_user):
        """Sollte Hybrid-Suche via POST durchfuehren."""
        from app.api.v1.rag.search import search_chunks
        from app.api.schemas.rag import RAGSearchRequest, RAGSearchType

        mock_search_service.hybrid_search = AsyncMock(return_value=MagicMock(
            query="Test hybrid",
            search_type="hybrid",
            results=[],
            total_results=0,
            search_time_ms=60,
            embedding_time_ms=20,
            rerank_time_ms=40,
        ))

        request = MagicMock(spec=RAGSearchRequest)
        request.query = "Test hybrid"
        request.search_type = RAGSearchType.HYBRID
        request.limit = 10
        request.threshold = 0.5
        request.document_ids = None
        request.rerank = True

        result = await search_chunks(
            request=request,
            current_user=mock_user,
            db=mock_db,
            search_service=mock_search_service,
        )

        assert result.search_type == RAGSearchType.HYBRID

    @pytest.mark.asyncio
    async def test_keyword_search_post(self, mock_search_service, mock_db, mock_user):
        """Sollte Keyword-Suche via POST durchfuehren."""
        from app.api.v1.rag.search import search_chunks
        from app.api.schemas.rag import RAGSearchRequest, RAGSearchType

        mock_search_service.keyword_search = AsyncMock(return_value=MagicMock(
            query="keyword test",
            search_type="keyword",
            results=[],
            total_results=0,
            search_time_ms=30,
            embedding_time_ms=0,
            rerank_time_ms=0,
        ))

        request = MagicMock(spec=RAGSearchRequest)
        request.query = "keyword test"
        request.search_type = RAGSearchType.KEYWORD
        request.limit = 20
        request.document_ids = None

        result = await search_chunks(
            request=request,
            current_user=mock_user,
            db=mock_db,
            search_service=mock_search_service,
        )

        mock_search_service.keyword_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_semantic_search_get(self, mock_search_service, mock_db, mock_user):
        """Sollte semantische Suche via GET durchfuehren."""
        from app.api.v1.rag.search import semantic_search_get

        mock_search_service.semantic_search = AsyncMock(return_value=MagicMock(
            query="simple query",
            search_type="semantic",
            results=[],
            total_results=0,
            search_time_ms=40,
            embedding_time_ms=15,
            rerank_time_ms=0,
        ))

        result = await semantic_search_get(
            q="simple query",
            limit=20,
            threshold=0.7,
            rerank=False,
            current_user=mock_user,
            db=mock_db,
            search_service=mock_search_service,
        )

        assert result.query == "simple query"

    @pytest.mark.asyncio
    async def test_hybrid_search_get(self, mock_search_service, mock_db, mock_user):
        """Sollte Hybrid-Suche via GET durchfuehren."""
        from app.api.v1.rag.search import hybrid_search_get

        mock_search_service.hybrid_search = AsyncMock(return_value=MagicMock(
            query="hybrid query",
            search_type="hybrid",
            results=[],
            total_results=0,
            search_time_ms=55,
            embedding_time_ms=20,
            rerank_time_ms=35,
        ))

        result = await hybrid_search_get(
            q="hybrid query",
            limit=20,
            semantic_weight=0.7,
            keyword_weight=0.3,
            rerank=True,
            current_user=mock_user,
            db=mock_db,
            search_service=mock_search_service,
        )

        mock_search_service.hybrid_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_error_handling(self, mock_search_service, mock_db, mock_user):
        """Sollte Fehler bei der Suche abfangen."""
        from app.api.v1.rag.search import search_chunks
        from app.api.schemas.rag import RAGSearchRequest, RAGSearchType

        mock_search_service.semantic_search = AsyncMock(
            side_effect=Exception("Search failed")
        )

        request = MagicMock(spec=RAGSearchRequest)
        request.query = "error query"
        request.search_type = RAGSearchType.SEMANTIC
        request.limit = 20
        request.threshold = 0.7
        request.document_ids = None
        request.section_types = None
        request.rerank = False

        with pytest.raises(HTTPException) as exc:
            await search_chunks(
                request=request,
                current_user=mock_user,
                db=mock_db,
                search_service=mock_search_service,
            )

        assert exc.value.status_code == 500


# ==================== Chat Tests ====================

class TestRAGChatEndpoints:
    """Tests fuer RAG Chat API."""

    @pytest.fixture
    def mock_llm_service(self):
        with patch('app.api.v1.rag.chat.get_llm_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_search_service(self):
        with patch('app.api.v1.rag.chat.get_rag_search_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_create_chat_session(self, mock_db, mock_user):
        """Sollte Chat-Session erstellen."""
        from app.api.v1.rag.chat import create_chat_session
        from app.api.schemas.rag import RAGChatSessionCreate, RAGContextType

        request = MagicMock(spec=RAGChatSessionCreate)
        request.title = "Test Session"
        request.context_type = RAGContextType.GENERAL
        request.context_id = None

        # Mock session creation
        session_id = uuid4()

        def mock_add(session):
            session.id = session_id
            session.user_id = mock_user.id
            session.session_token = "test-token"
            session.title = request.title
            session.context_type = request.context_type.value
            session.context_id = None
            session.status = "active"
            session.message_count = 0
            session.created_at = datetime.now(timezone.utc)
            session.updated_at = datetime.now(timezone.utc)
            session.last_message_at = None

        mock_db.add.side_effect = mock_add

        with patch('app.api.v1.rag.chat.RAGChatSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.id = session_id
            mock_session.user_id = mock_user.id
            mock_session.session_token = "test-token"
            mock_session.title = "Test Session"
            mock_session.context_type = "general"
            mock_session.context_id = None
            mock_session.status = "active"
            mock_session.message_count = 0
            mock_session.created_at = datetime.now(timezone.utc)
            mock_session.updated_at = datetime.now(timezone.utc)
            mock_session.last_message_at = None

            mock_session_class.return_value = mock_session

            result = await create_chat_session(
                request=request,
                current_user=mock_user,
                db=mock_db,
            )

            assert result.title == "Test Session"

    @pytest.mark.asyncio
    async def test_list_chat_sessions(self, mock_db, mock_user):
        """Sollte Chat-Sessions auflisten."""
        from app.api.v1.rag.chat import list_chat_sessions

        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = mock_user.id
        mock_session.session_token = "token-1"
        mock_session.title = "Session 1"
        mock_session.context_type = "general"
        mock_session.context_id = None
        mock_session.status = "active"
        mock_session.message_count = 5
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        mock_session.last_message_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_session]
        mock_db.execute.return_value = mock_result

        result = await list_chat_sessions(
            limit=20,
            offset=0,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].title == "Session 1"

    @pytest.mark.asyncio
    async def test_get_chat_session(self, mock_db, mock_user):
        """Sollte Chat-Session mit Nachrichten abrufen."""
        from app.api.v1.rag.chat import get_chat_session

        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = mock_user.id
        mock_session.session_token = "token"
        mock_session.title = "Test Session"
        mock_session.context_type = "general"
        mock_session.context_id = None
        mock_session.status = "active"
        mock_session.message_count = 2
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        mock_session.last_message_at = datetime.now(timezone.utc)

        mock_db.get.return_value = mock_session

        # Mock messages
        mock_message = MagicMock()
        mock_message.id = uuid4()
        mock_message.session_id = session_id
        mock_message.role = MagicMock(value="user")
        mock_message.content = "Hello"
        mock_message.thinking_content = None
        mock_message.confidence_score = None
        mock_message.model_used = None
        mock_message.tokens_input = None
        mock_message.tokens_output = None
        mock_message.generation_time_ms = None
        mock_message.created_at = datetime.now(timezone.utc)
        mock_message.attached_document = None

        mock_messages_result = MagicMock()
        mock_messages_result.scalars.return_value.all.return_value = [mock_message]
        mock_db.execute.return_value = mock_messages_result

        result = await get_chat_session(
            session_id=session_id,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.id == session_id
        assert len(result.messages) == 1

    @pytest.mark.asyncio
    async def test_get_chat_session_not_found(self, mock_db, mock_user):
        """Sollte 404 bei nicht gefundener Session werfen."""
        from app.api.v1.rag.chat import get_chat_session

        mock_db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_chat_session(
                session_id=uuid4(),
                current_user=mock_user,
                db=mock_db,
            )

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_chat_session(self, mock_db, mock_user):
        """Sollte Chat-Session aktualisieren."""
        from app.api.v1.rag.chat import update_chat_session

        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = mock_user.id
        mock_session.session_token = "token"
        mock_session.title = "Old Title"
        mock_session.context_type = "general"
        mock_session.context_id = None
        mock_session.status = "active"
        mock_session.message_count = 0
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        mock_session.last_message_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await update_chat_session(
            session_id=session_id,
            title="New Title",
            current_user=mock_user,
            db=mock_db,
        )

        assert mock_session.title == "New Title"

    @pytest.mark.asyncio
    async def test_delete_chat_session(self, mock_db, mock_user):
        """Sollte Chat-Session loeschen."""
        from app.api.v1.rag.chat import delete_chat_session

        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = mock_user.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await delete_chat_session(
            session_id=session_id,
            current_user=mock_user,
            db=mock_db,
        )

        assert result["success"] is True
        mock_db.delete.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_delete_chat_session_not_found(self, mock_db, mock_user):
        """Sollte 404 bei nicht gefundener Session werfen."""
        from app.api.v1.rag.chat import delete_chat_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc:
            await delete_chat_session(
                session_id=uuid4(),
                current_user=mock_user,
                db=mock_db,
            )

        assert exc.value.status_code == 404


# ==================== Chat Sharing Tests ====================

class TestChatSharingEndpoints:
    """Tests fuer Chat Sharing API."""

    @pytest.fixture
    def mock_sharing_service(self):
        with patch('app.api.v1.rag.chat.get_chat_sharing_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.get = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.username = "testuser"
        user.email = "test@example.com"
        return user

    @pytest.mark.asyncio
    async def test_share_chat_session(self, mock_sharing_service, mock_db, mock_user):
        """Sollte Chat-Session teilen."""
        from app.api.v1.rag.chat import share_chat_session
        from app.api.schemas.rag import ChatSessionShareRequest, ChatSessionAccessLevel

        session_id = uuid4()
        target_user_id = uuid4()

        mock_access = MagicMock()
        mock_access.user_id = target_user_id
        mock_access.access_level = "edit"
        mock_access.granted_at = datetime.now(timezone.utc)

        mock_sharing_service.share_session = AsyncMock(return_value=mock_access)

        mock_target_user = MagicMock()
        mock_target_user.username = "targetuser"
        mock_target_user.email = "target@example.com"
        mock_db.get.return_value = mock_target_user

        request = MagicMock(spec=ChatSessionShareRequest)
        request.user_id = target_user_id
        request.access_level = ChatSessionAccessLevel.EDIT

        result = await share_chat_session(
            session_id=session_id,
            request=request,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.user_id == str(target_user_id)
        assert result.username == "targetuser"

    @pytest.mark.asyncio
    async def test_revoke_chat_session_access(self, mock_sharing_service, mock_db, mock_user):
        """Sollte Chat-Session-Zugriff entziehen."""
        from app.api.v1.rag.chat import revoke_chat_session_access

        session_id = uuid4()
        target_user_id = uuid4()

        mock_sharing_service.revoke_access = AsyncMock(return_value=True)

        result = await revoke_chat_session_access(
            session_id=session_id,
            user_id=target_user_id,
            current_user=mock_user,
            db=mock_db,
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_revoke_chat_session_access_not_found(self, mock_sharing_service, mock_db, mock_user):
        """Sollte 404 bei nicht gefundenem Zugriff werfen."""
        from app.api.v1.rag.chat import revoke_chat_session_access

        mock_sharing_service.revoke_access = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc:
            await revoke_chat_session_access(
                session_id=uuid4(),
                user_id=uuid4(),
                current_user=mock_user,
                db=mock_db,
            )

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_chat_session_collaborators(self, mock_sharing_service, mock_db, mock_user):
        """Sollte Collaborators einer Session zurueckgeben."""
        from app.api.v1.rag.chat import get_chat_session_collaborators

        session_id = uuid4()

        mock_sharing_service.get_collaborators = AsyncMock(return_value=[
            {
                "user_id": str(uuid4()),
                "username": "user1",
                "email": "user1@example.com",
                "access_level": "view",
                "is_owner": False,
                "granted_at": "2024-01-01T00:00:00",
            },
            {
                "user_id": str(uuid4()),
                "username": "user2",
                "email": "user2@example.com",
                "access_level": "edit",
                "is_owner": False,
                "granted_at": "2024-01-02T00:00:00",
            },
        ])

        result = await get_chat_session_collaborators(
            session_id=session_id,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_shared_sessions(self, mock_sharing_service, mock_db, mock_user):
        """Sollte mit mir geteilte Sessions zurueckgeben."""
        from app.api.v1.rag.chat import get_shared_sessions

        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = uuid4()  # Different user (owner)
        mock_session.session_token = "shared-token"
        mock_session.title = "Shared Session"
        mock_session.context_type = "general"
        mock_session.context_id = None
        mock_session.status = "active"
        mock_session.message_count = 10
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        mock_session.last_message_at = datetime.now(timezone.utc)

        mock_sharing_service.get_shared_sessions = AsyncMock(return_value=[mock_session])
        mock_sharing_service.get_access_level = AsyncMock(return_value="view")
        mock_sharing_service.get_collaborators = AsyncMock(return_value=[])

        result = await get_shared_sessions(
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].is_shared is True


# ==================== Chat Message Tests ====================

class TestChatMessageEndpoints:
    """Tests fuer Chat Message Sending."""

    @pytest.fixture
    def mock_llm_service(self):
        mock = MagicMock()
        return mock

    @pytest.fixture
    def mock_search_service(self):
        mock = MagicMock()
        return mock

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_send_chat_message(self, mock_llm_service, mock_search_service, mock_db, mock_user):
        """Sollte Chat-Nachricht senden und Antwort erhalten."""
        from app.api.v1.rag.chat import send_chat_message
        from app.api.schemas.rag import RAGChatRequest, RAGContextType

        session_id = uuid4()

        # Mock session
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = mock_user.id
        mock_session.message_count = 0
        mock_session.last_message_at = None

        # Mock search response
        mock_search_service.search_for_context = AsyncMock(return_value=[
            {
                "chunk_id": str(uuid4()),
                "document_id": str(uuid4()),
                "text": "Relevant context",
                "page_number": 1,
                "section_type": "body",
                "similarity": 0.9,
                "rerank_score": 0.88,
            }
        ])

        # Mock LLM response
        mock_llm_service.generate = AsyncMock(return_value=MagicMock(
            content="Das ist die Antwort",
            thinking_content=None,
            model="deepseek-v3",
            tokens_input=100,
            tokens_output=50,
            generation_time_ms=500,
        ))

        request = MagicMock(spec=RAGChatRequest)
        request.session_id = session_id
        request.message = "Was steht im Dokument?"
        request.context_type = RAGContextType.GENERAL
        request.context_id = None
        request.realtime = False

        with patch('app.api.v1.rag.chat._get_or_create_session') as mock_get_session:
            mock_get_session.return_value = mock_session

            with patch('app.api.v1.rag.chat._get_chat_history') as mock_history:
                mock_history.return_value = []

                with patch('app.api.v1.rag.chat.build_rag_context') as mock_context:
                    mock_context.return_value = "Relevant context"

                    with patch('app.api.v1.rag.chat.build_chat_prompt') as mock_prompt:
                        mock_prompt.return_value = [
                            {"role": "system", "content": "System prompt"},
                            {"role": "user", "content": "Was steht im Dokument?"},
                        ]

                        result = await send_chat_message(
                            request=request,
                            current_user=mock_user,
                            db=mock_db,
                            llm_service=mock_llm_service,
                            search_service=mock_search_service,
                        )

                        assert result.message == "Das ist die Antwort"
                        assert result.session_id == session_id


# ==================== Helper Function Tests ====================

class TestChatHelperFunctions:
    """Tests fuer Helper-Funktionen."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_llm_service(self):
        mock = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_generate_chat_title(self, mock_llm_service):
        """Sollte Chat-Titel generieren."""
        from app.api.v1.rag.chat import _generate_chat_title

        # Mock streaming response
        async def mock_stream(*args, **kwargs):
            for chunk in ["Dokument", "analyse", " Q1"]:
                yield chunk

        mock_llm_service.generate_stream = mock_stream

        title = await _generate_chat_title(
            llm_service=mock_llm_service,
            user_message="Analysiere bitte diese Rechnung von Q1 2024"
        )

        assert len(title) <= 50

    @pytest.mark.asyncio
    async def test_generate_chat_title_fallback(self, mock_llm_service):
        """Sollte bei Fehler auf ersten 50 Zeichen fallbacken."""
        from app.api.v1.rag.chat import _generate_chat_title

        mock_llm_service.generate_stream = AsyncMock(
            side_effect=Exception("LLM Error")
        )

        long_message = "Dies ist eine sehr lange Nachricht die mehr als 50 Zeichen hat und gekuerzt werden sollte"

        title = await _generate_chat_title(
            llm_service=mock_llm_service,
            user_message=long_message
        )

        assert len(title) <= 53  # 50 + "..."

    @pytest.mark.asyncio
    async def test_get_or_create_session_existing(self, mock_db):
        """Sollte existierende Session zurueckgeben."""
        from app.api.v1.rag.chat import _get_or_create_session
        from app.api.schemas.rag import RAGContextType

        user_id = uuid4()
        session_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await _get_or_create_session(
            db=mock_db,
            user_id=user_id,
            session_id=session_id,
            context_type=RAGContextType.GENERAL,
            context_id=None,
        )

        assert result.id == session_id

    @pytest.mark.asyncio
    async def test_get_or_create_session_new(self, mock_db):
        """Sollte neue Session erstellen."""
        from app.api.v1.rag.chat import _get_or_create_session
        from app.api.schemas.rag import RAGContextType

        user_id = uuid4()

        with patch('app.api.v1.rag.chat.RAGChatSession') as mock_class:
            mock_session = MagicMock()
            mock_class.return_value = mock_session

            result = await _get_or_create_session(
                db=mock_db,
                user_id=user_id,
                session_id=None,
                context_type=RAGContextType.DOCUMENT,
                context_id="doc-123",
            )

            mock_db.add.assert_called_once()
            mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_chat_history(self, mock_db):
        """Sollte Chat-Historie laden."""
        from app.api.v1.rag.chat import _get_chat_history

        session_id = uuid4()

        mock_message1 = MagicMock()
        mock_message1.role = MagicMock(value="user")
        mock_message1.content = "Frage 1"

        mock_message2 = MagicMock()
        mock_message2.role = MagicMock(value="assistant")
        mock_message2.content = "Antwort 1"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_message2, mock_message1]
        mock_db.execute.return_value = mock_result

        with patch('app.api.v1.rag.chat.settings') as mock_settings:
            mock_settings.RAG_CHAT_MAX_HISTORY = 10

            result = await _get_chat_history(
                db=mock_db,
                session_id=session_id,
            )

            assert len(result) == 2
            # Should be reversed (chronological)
            assert result[0]["content"] == "Frage 1"
            assert result[1]["content"] == "Antwort 1"

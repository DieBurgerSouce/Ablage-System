"""RAG Chat Service.

Document-aware chat service mit:
- Semantischer Suche für Kontext-Retrieval
- LLM-Integration für Antwortgenerierung
- Multi-Tool Calling (Aktionen aus dem Chat)
- Chat-History Management
- Streaming-Unterstützung

Feinpoliert und durchdacht - Intelligente Dokumentenanalyse.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, AsyncGenerator, Callable
from uuid import UUID
import uuid as uuid_module
import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.search_service import SearchService
from app.services.embedding_service import get_embedding_service
from app.db.schemas import SearchType, SearchFilters
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.services.rag.tool_registry import ToolCall, get_tool_registry
from app.services.rag.action_dispatcher import get_action_dispatcher

logger = structlog.get_logger(__name__)


class ChatMessage:
    """Einzelne Chat-Nachricht."""

    def __init__(
        self,
        role: str,  # "user", "assistant", "system"
        content: str,
        message_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tool_actions: Optional[List[Dict[str, Any]]] = None,
    ):
        self.id = message_id or str(uuid_module.uuid4())
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.sources = sources or []  # Referenced documents
        self.metadata = metadata or {}
        self.tool_actions = tool_actions or []  # Tool-Call Ergebnisse

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert Nachricht zu Dictionary."""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "sources": self.sources,
            "metadata": self.metadata,
            "tool_actions": self.tool_actions,
        }


class ChatSession:
    """Chat-Session mit History."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[UUID] = None,
        max_history: int = 20,
    ):
        self.id = session_id or str(uuid_module.uuid4())
        self.user_id = user_id
        self.messages: List[ChatMessage] = []
        self.max_history = max_history
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.context_documents: List[Dict[str, Any]] = []

    def add_message(self, message: ChatMessage) -> None:
        """Fuegt Nachricht zur History hinzu."""
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)

        # Begrenze History-Länge
        if len(self.messages) > self.max_history:
            # Behalte System-Nachrichten und letzte N Nachrichten
            system_msgs = [m for m in self.messages if m.role == "system"]
            other_msgs = [m for m in self.messages if m.role != "system"]
            keep_count = self.max_history - len(system_msgs)
            self.messages = system_msgs + other_msgs[-keep_count:]

    def get_context_for_llm(self, include_system: bool = True) -> List[Dict[str, str]]:
        """Bereitet Chat-History für LLM auf."""
        result = []
        for msg in self.messages:
            if msg.role == "system" and not include_system:
                continue
            result.append({"role": msg.role, "content": msg.content})
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert Session zu Dictionary."""
        return {
            "id": self.id,
            "user_id": str(self.user_id) if self.user_id else None,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "context_documents": self.context_documents,
        }


class RAGChatService:
    """RAG Chat Service für dokumentenbasierte Konversationen.

    Kombiniert semantische Suche mit LLM für kontextbewusste Antworten.
    """

    _instance: Optional["RAGChatService"] = None

    def __new__(cls) -> "RAGChatService":
        """Singleton-Instanz."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialisierung."""
        if getattr(self, "_initialized", False):
            return

        self.search_service = SearchService()
        self.embedding_service = get_embedding_service()
        self.sessions: Dict[str, ChatSession] = {}
        self.tool_registry = get_tool_registry()
        self.action_dispatcher = get_action_dispatcher()

        # LLM-Konfiguration (kann erweitert werden für Ollama, OpenAI, etc.)
        self.llm_enabled = getattr(settings, "LLM_ENABLED", False)
        self.llm_model = getattr(settings, "LLM_MODEL", "llama3.1:8b")
        self.ollama_url = getattr(settings, "OLLAMA_URL", "http://localhost:11434")

        self._initialized = True
        logger.info(
            "rag_chat_service_initialized",
            llm_enabled=self.llm_enabled,
            llm_model=self.llm_model,
        )

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[UUID] = None,
        user_level: str = "viewer",
    ) -> ChatSession:
        """Holt oder erstellt eine Chat-Session."""
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
            if user_id and session.user_id != user_id:
                raise PermissionError("Session gehoert einem anderen Benutzer")
            return session

        session = ChatSession(session_id=session_id, user_id=user_id)
        self.sessions[session.id] = session

        # Tool-Definitionen für System-Prompt
        tools_text = self.tool_registry.format_tools_for_llm(user_level)

        # System-Prompt mit Tool-Calling Instruktionen
        system_prompt = ChatMessage(
            role="system",
            content=(
                "Du bist ein hilfreicher Assistent für das Ablage-System. "
                "Du kannst auf Dokumente zugreifen und Fragen dazu beantworten. "
                "Antworte immer auf Deutsch und nutze die bereitgestellten Dokumente als Kontext. "
                "Wenn du dir nicht sicher bist, sage es ehrlich.\n\n"
                "Du hast Zugriff auf Tools die du aufrufen kannst um Aktionen auszuführen. "
                "Du kannst MEHRERE Tools in einer Antwort aufrufen. "
                "Verwende Tools nur wenn der Benutzer eine Aktion anfragt oder Daten benötigt.\n\n"
                f"{tools_text}"
            ),
        )
        session.add_message(system_prompt)

        logger.info(
            "chat_session_created",
            session_id=session.id,
            user_id=str(user_id) if user_id else None,
            user_level=user_level,
        )
        return session

    def delete_session(self, session_id: str) -> bool:
        """Löscht eine Chat-Session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info("chat_session_deleted", session_id=session_id)
            return True
        return False

    async def retrieve_context(
        self,
        query: str,
        user_id: UUID,
        db: AsyncSession,
        max_documents: int = 5,
        similarity_threshold: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """Holt relevante Dokumente für die Anfrage.

        Verwendet semantische Suche für Kontext-Retrieval.
        """
        try:
            # Semantische Suche
            results = await self.search_service.search(
                db=db,
                query=query,
                user_id=user_id,
                search_type=SearchType.SEMANTIC,
                filters=None,
                page=1,
                per_page=max_documents,
            )

            # Filtern nach Similarity
            context_docs = []
            for result in results.results:
                if result.similarity_score and result.similarity_score >= similarity_threshold:
                    context_docs.append({
                        "document_id": str(result.id),
                        "filename": result.filename,
                        "document_type": result.document_type.value if result.document_type else None,
                        "similarity": result.similarity_score,
                        "snippet": result.snippet,
                        "text": result.extracted_text[:2000] if result.extracted_text else None,
                    })

            logger.info(
                "context_retrieved",
                query_length=len(query),
                documents_found=len(context_docs),
            )
            return context_docs

        except Exception as e:
            logger.error("context_retrieval_error", **safe_error_log(e))
            return []

    def build_prompt_with_context(
        self,
        query: str,
        context_documents: List[Dict[str, Any]],
        chat_history: List[Dict[str, str]],
    ) -> str:
        """Baut den Prompt mit Kontext auf."""
        # Kontext-Dokumente formatieren
        context_text = ""
        if context_documents:
            context_text = "\n\n=== RELEVANTE DOKUMENTE ===\n"
            for i, doc in enumerate(context_documents, 1):
                context_text += f"\n[Dokument {i}: {doc['filename']}]\n"
                if doc.get("text"):
                    context_text += doc["text"][:1500] + "\n"
                elif doc.get("snippet"):
                    context_text += doc["snippet"] + "\n"

        # Chat-History formatieren (letzte 3 Nachrichten)
        history_text = ""
        recent_history = [h for h in chat_history if h["role"] != "system"][-6:]
        if recent_history:
            history_text = "\n\n=== BISHERIGER VERLAUF ===\n"
            for msg in recent_history:
                role_name = "Benutzer" if msg["role"] == "user" else "Assistent"
                history_text += f"{role_name}: {msg['content'][:500]}\n"

        # Finaler Prompt
        prompt = f"""Beantworte die folgende Frage basierend auf den bereitgestellten Dokumenten.
Wenn die Dokumente keine relevanten Informationen enthalten, sage das ehrlich.
{context_text}{history_text}

=== AKTUELLE FRAGE ===
{query}

=== ANTWORT ==="""

        return prompt

    async def generate_response(
        self,
        query: str,
        session: ChatSession,
        context_documents: List[Dict[str, Any]],
        stream: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Generiert Antwort mit LLM.

        Unterstützt Streaming für Echtzeit-Ausgabe.
        """
        # Prompt mit Kontext aufbauen
        chat_history = session.get_context_for_llm(include_system=False)
        prompt = self.build_prompt_with_context(query, context_documents, chat_history)

        if not self.llm_enabled:
            # Fallback ohne LLM - generiere informative Antwort aus Kontext
            if context_documents:
                response = "Basierend auf den gefundenen Dokumenten:\n\n"
                for doc in context_documents[:3]:
                    response += f"**{doc['filename']}** (Relevanz: {doc['similarity']:.0%})\n"
                    if doc.get("snippet"):
                        response += f"> {doc['snippet']}\n\n"
                response += "\n*Hinweis: LLM-Integration ist nicht aktiviert. Dies ist eine Kontextvorschau.*"
            else:
                response = "Keine relevanten Dokumente gefunden. Versuche eine andere Formulierung."

            # Simuliere Streaming
            words = response.split()
            for i, word in enumerate(words):
                yield word + (" " if i < len(words) - 1 else "")
                await asyncio.sleep(0.02)  # Kleine Verzögerung für Streaming-Effekt
            return

        # LLM-Generierung mit Ollama
        try:
            import httpx

            async with httpx.AsyncClient(timeout=120.0) as client:
                if stream:
                    async with client.stream(
                        "POST",
                        f"{self.ollama_url}/api/generate",
                        json={
                            "model": self.llm_model,
                            "prompt": prompt,
                            "stream": True,
                            "options": {
                                "temperature": 0.7,
                                "top_p": 0.9,
                                "num_predict": 1000,
                            },
                        },
                    ) as response:
                        async for line in response.aiter_lines():
                            if line:
                                try:
                                    data = json.loads(line)
                                    if "response" in data:
                                        yield data["response"]
                                except json.JSONDecodeError:
                                    continue
                else:
                    response = await client.post(
                        f"{self.ollama_url}/api/generate",
                        json={
                            "model": self.llm_model,
                            "prompt": prompt,
                            "stream": False,
                            "options": {
                                "temperature": 0.7,
                                "top_p": 0.9,
                                "num_predict": 1000,
                            },
                        },
                    )
                    data = response.json()
                    yield data.get("response", "Fehler bei der Antwortgenerierung.")

        except Exception as e:
            logger.error("llm_generation_error", **safe_error_log(e))
            yield f"Fehler bei der LLM-Verbindung: {str(e)}"

    async def dispatch_tool_calls(
        self,
        tool_calls: List[ToolCall],
        user: Any,
        db: AsyncSession,
        context_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Dispatcht alle Tool-Calls und sammelt Ergebnisse.

        Args:
            tool_calls: Geparste Tool-Calls aus LLM-Antwort
            user: Aktueller User
            db: Database Session
            context_id: Optionale Kontext-Dokument-ID

        Returns:
            Liste von Tool-Action Ergebnissen als Dicts
        """
        results: List[Dict[str, Any]] = []

        for tc in tool_calls:
            try:
                result = await self.action_dispatcher.dispatch(
                    tool_call=tc,
                    user=user,
                    db=db,
                    context_id=context_id,
                )
                results.append({
                    "action_id": str(result.action_id),
                    "tool_name": tc.tool_name,
                    "parameters": tc.parameters,
                    "action_type": result.action_type.value,
                    "status": result.status.value,
                    "message": result.message or "",
                    "data": result.data if hasattr(result, "data") else None,
                    "requires_confirmation": result.status.value == "pending_confirmation",
                    "execution_time_ms": result.execution_time_ms,
                })
            except Exception as e:
                logger.error(
                    "tool_call_dispatch_error",
                    tool_name=tc.tool_name,
                    **safe_error_log(e),
                )
                results.append({
                    "action_id": str(uuid_module.uuid4()),
                    "tool_name": tc.tool_name,
                    "parameters": tc.parameters,
                    "action_type": "unknown",
                    "status": "failed",
                    "message": safe_error_detail(e, "Tool-Ausführung"),
                    "data": None,
                    "requires_confirmation": False,
                    "execution_time_ms": 0,
                })

        logger.info(
            "tool_calls_dispatched",
            count=len(results),
            tool_names=[r["tool_name"] for r in results],
            statuses=[r["status"] for r in results],
        )
        return results

    async def chat(
        self,
        query: str,
        user_id: UUID,
        db: AsyncSession,
        session_id: Optional[str] = None,
        stream: bool = True,
        on_token: Optional[Callable[[str], None]] = None,
        user: Optional[Any] = None,
        user_level: str = "viewer",
    ) -> ChatMessage:
        """Hauptmethode für Chat-Interaktion.

        Args:
            query: Benutzeranfrage
            user_id: Benutzer-ID
            db: Datenbank-Session
            session_id: Optionale Session-ID
            stream: Streaming aktivieren
            on_token: Callback für Streaming-Tokens
            user: User-Objekt für Tool-Calling Permissions
            user_level: User-Level für Tool-Zugriff

        Returns:
            ChatMessage mit vollständiger Antwort und Tool-Actions
        """
        session = self.get_or_create_session(session_id, user_id, user_level=user_level)

        # Benutzer-Nachricht speichern
        user_message = ChatMessage(role="user", content=query)
        session.add_message(user_message)

        # Kontext-Dokumente holen
        context_docs = await self.retrieve_context(query, user_id, db)
        session.context_documents = context_docs

        # Antwort generieren
        full_response = ""
        async for token in self.generate_response(query, session, context_docs, stream):
            full_response += token
            if on_token:
                on_token(token)

        # Tool-Calls parsen und dispatchen
        tool_actions: List[Dict[str, Any]] = []
        parsed_calls = self.tool_registry.parse_tool_calls(full_response)

        if parsed_calls and user is not None:
            tool_actions = await self.dispatch_tool_calls(
                tool_calls=parsed_calls,
                user=user,
                db=db,
            )

            logger.info(
                "chat_tool_calls_processed",
                session_id=session.id,
                tool_count=len(parsed_calls),
                action_count=len(tool_actions),
            )

        # Assistent-Nachricht speichern
        sources = [
            {"document_id": doc["document_id"], "filename": doc["filename"], "similarity": doc["similarity"]}
            for doc in context_docs
        ]
        assistant_message = ChatMessage(
            role="assistant",
            content=full_response,
            sources=sources,
            tool_actions=tool_actions,
        )
        session.add_message(assistant_message)

        logger.info(
            "chat_completed",
            session_id=session.id,
            query_length=len(query),
            response_length=len(full_response),
            sources_count=len(sources),
            tool_actions_count=len(tool_actions),
        )

        return assistant_message

    def get_session_history(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Holt Session-History."""
        session = self.sessions.get(session_id)
        if session:
            return session.to_dict()
        return None

    def clear_session_history(self, session_id: str) -> bool:
        """Löscht Chat-History einer Session (behält System-Prompt)."""
        session = self.sessions.get(session_id)
        if session:
            system_msgs = [m for m in session.messages if m.role == "system"]
            session.messages = system_msgs
            session.context_documents = []
            logger.info("session_history_cleared", session_id=session_id)
            return True
        return False


# Singleton-Getter
_chat_service: Optional[RAGChatService] = None


def get_chat_service() -> RAGChatService:
    """Gibt Singleton-Instanz des Chat-Service zurück."""
    global _chat_service
    if _chat_service is None:
        _chat_service = RAGChatService()
    return _chat_service

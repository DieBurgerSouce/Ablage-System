# -*- coding: utf-8 -*-
"""
Conversational Assistant Service mit Ollama Integration.

Enterprise Feature: Intelligenter Chat-Assistent für Dokument-Interaktion.

Funktionen:
- Intent-Klassifikation (NLQ, DOCUMENT_SEARCH, ACTION_REQUEST, GENERAL)
- RAG-basierte Dokumentensuche
- Natural Language Queries auf Datenbank
- Workflow-Aktionen mit Bestätigung
- Streaming-Antworten

Feinpoliert und durchdacht - Deutsche Praezision.
"""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.db.models import Document, User, BusinessEntity
from app.db.models_ai_conversation import (
    AIConversation,
    AIConversationMessage,
    AIConversationAction,
    AIConversationFeedback,
    AIMessageRole,
    AIAssistantIntent,
    AIActionStatus,
    AIFeedbackType,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS UND KONSTANTEN
# =============================================================================


class AssistantIntent(str, Enum):
    """Erkannte Benutzerabsicht."""

    NLQ = "nlq"  # Natural Language Query (SQL-Generierung)
    DOCUMENT_SEARCH = "document_search"  # Dokumentensuche via RAG
    ACTION_REQUEST = "action_request"  # Workflow-Aktion
    GENERAL = "general"  # Allgemeine Frage/Chat


class ActionType(str, Enum):
    """Verfügbare Aktionstypen."""

    APPROVE_DOCUMENT = "approve_document"
    REJECT_DOCUMENT = "reject_document"
    CATEGORIZE_DOCUMENT = "categorize_document"
    LINK_ENTITY = "link_entity"
    CREATE_TASK = "create_task"
    EXPORT_DOCUMENTS = "export_documents"
    SCHEDULE_PAYMENT = "schedule_payment"
    GENERATE_REPORT = "generate_report"


# Intent-Keywords für Klassifikation
INTENT_KEYWORDS: Dict[AssistantIntent, List[str]] = {
    AssistantIntent.NLQ: [
        "wie viele", "zeige mir", "liste", "welche", "berechne", "summe",
        "durchschnitt", "anzahl", "gesamt", "statistik", "übersicht",
        "show me", "how many", "list all", "calculate", "total",
    ],
    AssistantIntent.DOCUMENT_SEARCH: [
        "finde", "suche", "dokument", "rechnung", "vertrag", "ähnlich",
        "find", "search", "document", "invoice", "contract", "similar",
        "beleg", "lieferschein", "angebot", "bestellung",
    ],
    AssistantIntent.ACTION_REQUEST: [
        "genehmige", "freigeben", "ablehnen", "kategorisiere", "verknüpfe",
        # ASCII-Umlaut-Schreibweisen (Nutzer tippen oft ue/ae/oe statt ü/ä/ö)
        "verknuepfe", "loesche", "kuerze",
        "erstelle", "exportiere", "plane", "approve", "reject", "categorize",
        "link", "create", "export", "schedule",
    ],
}

# NLQ Schema-Mapping für SQL-Generierung
NLQ_SCHEMA_CONTEXT = """
Verfügbare Tabellen und Spalten:

documents:
- id (UUID): Dokument-ID
- filename (String): Dateiname
- original_filename (String): Original-Dateiname
- document_type (String): Typ (invoice, contract, delivery_note, etc.)
- extracted_text (Text): OCR-Text
- confidence (Float): OCR-Konfidenz (0.0-1.0)
- total_amount (Float): Betrag in EUR
- created_at (DateTime): Erstellungsdatum
- processing_status (String): Status (pending, processing, completed, error)

business_entities:
- id (UUID): Entity-ID
- name (String): Firmenname
- entity_type (String): Typ (customer, supplier)
- customer_number (String): Kundennummer
- tax_id (String): USt-IdNr

invoice_tracking:
- document_id (UUID): Verknüpftes Dokument
- invoice_number (String): Rechnungsnummer
- due_date (Date): Fälligkeitsdatum
- paid_at (DateTime): Bezahlt am
- status (String): Status (open, overdue, paid)
- dunning_level (Integer): Mahnstufe (0-3)

Wichtig: Alle Abfragen müssen company_id filtern!
"""


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class DocumentReference:
    """Referenz auf ein Dokument im Suchergebnis."""

    id: UUID
    filename: str
    document_type: Optional[str]
    similarity: float
    snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "id": str(self.id),
            "filename": self.filename,
            "document_type": self.document_type,
            "similarity": self.similarity,
            "snippet": self.snippet,
        }


@dataclass
class SuggestedAction:
    """Vorgeschlagene Aktion."""

    action_type: str
    description: str
    parameters: Dict[str, Any]
    requires_confirmation: bool = True
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "action_type": self.action_type,
            "description": self.description,
            "parameters": self.parameters,
            "requires_confirmation": self.requires_confirmation,
            "confidence": self.confidence,
        }


@dataclass
class ChatContext:
    """Kontext für Chat-Nachricht."""

    document_id: Optional[UUID] = None
    page_number: Optional[int] = None
    selected_text: Optional[str] = None
    current_view: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """Antwort des Assistenten."""

    response: str
    intent: AssistantIntent
    sources: List[DocumentReference] = field(default_factory=list)
    actions: List[SuggestedAction] = field(default_factory=list)
    session_id: str = ""
    confidence: float = 0.0
    processing_time_ms: int = 0
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    follow_up_suggestions: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API."""
        return {
            "response": self.response,
            "intent": self.intent.value,
            "sources": [s.to_dict() for s in self.sources],
            "actions": [a.to_dict() for a in self.actions],
            "session_id": self.session_id,
            "confidence": self.confidence,
            "processing_time_ms": self.processing_time_ms,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "follow_up_suggestions": self.follow_up_suggestions,
            "error_message": self.error_message,
        }


# =============================================================================
# OLLAMA CLIENT
# =============================================================================


class OllamaClient:
    """HTTP-Client für Ollama API mit Streaming-Support."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
    ) -> None:
        """Initialisiert den Client.

        Args:
            base_url: Ollama API URL (Default aus Settings)
            timeout: Timeout in Sekunden
            max_retries: Maximale Wiederholungsversuche
        """
        self.base_url = base_url or settings.OLLAMA_URL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Holt oder erstellt HTTP-Client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Schließt den HTTP-Client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def is_available(self) -> bool:
        """Prüft ob Ollama verfügbar ist."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning("ollama_not_available", error=str(e))
            return False

    async def list_models(self) -> List[str]:
        """Listet verfügbare Modelle."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            logger.error("ollama_list_models_error", **safe_error_log(e))
            return []

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        format_json: bool = False,
    ) -> str:
        """Generiert Text mit Ollama.

        Args:
            prompt: User-Prompt
            model: Modellname (Default aus Settings)
            system_prompt: System-Prompt
            temperature: Sampling-Temperatur
            format_json: JSON-Ausgabe erzwingen

        Returns:
            Generierter Text
        """
        model = model or settings.DEFAULT_LLM_REALTIME

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "options": {"temperature": temperature},
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        }

        if format_json:
            payload["format"] = "json"

        client = await self._get_client()

        for attempt in range(self.max_retries):
            try:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "ollama_http_error",
                    attempt=attempt + 1,
                    status=e.response.status_code,
                )
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
            except httpx.RequestError as e:
                logger.warning("ollama_connection_error", attempt=attempt + 1)
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

        return ""

    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> AsyncIterator[str]:
        """Generiert Text mit Streaming.

        Args:
            prompt: User-Prompt
            model: Modellname
            system_prompt: System-Prompt
            temperature: Sampling-Temperatur

        Yields:
            Text-Chunks
        """
        model = model or settings.DEFAULT_LLM_REALTIME

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "options": {"temperature": temperature},
            "stream": True,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        }

        client = await self._get_client()

        async with client.stream("POST", "/api/chat", json=payload) as response:
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue


# =============================================================================
# CONVERSATIONAL ASSISTANT SERVICE
# =============================================================================


class ConversationalAssistantService:
    """Service für intelligenten Chat-Assistenten.

    Verarbeitet Benutzeranfragen mit:
    - Intent-Klassifikation
    - RAG-basierter Dokumentensuche
    - Natural Language Queries
    - Workflow-Aktionen
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._ollama = OllamaClient()
        self._enabled = settings.ASSISTANT_ENABLED if hasattr(settings, 'ASSISTANT_ENABLED') else True
        self._max_context_docs = getattr(settings, 'ASSISTANT_MAX_CONTEXT_DOCS', 5)

    async def is_available(self) -> bool:
        """Prüft ob der Service verfügbar ist."""
        if not self._enabled:
            return False
        return await self._ollama.is_available()

    async def classify_intent(
        self,
        message: str,
        context: Optional[ChatContext] = None,
    ) -> Tuple[AssistantIntent, float]:
        """Klassifiziert die Benutzerabsicht.

        Args:
            message: Benutzer-Nachricht
            context: Optionaler Kontext

        Returns:
            Tuple aus (Intent, Konfidenz)
        """
        message_lower = message.lower()

        # Keyword-basierte Vorab-Klassifikation
        intent_scores: Dict[AssistantIntent, int] = {
            AssistantIntent.NLQ: 0,
            AssistantIntent.DOCUMENT_SEARCH: 0,
            AssistantIntent.ACTION_REQUEST: 0,
            AssistantIntent.GENERAL: 0,
        }

        for intent, keywords in INTENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in message_lower:
                    intent_scores[intent] += 1

        # Hoechster Score als Vor-Klassifikation. Bei Gleichstand hat eine
        # explizite Aktion (imperativer Verb) Vorrang vor reiner Dokument-Suche
        # bzw. NLQ — "Genehmige diese Rechnung" ist eine Aktion, keine Suche.
        max_score = max(intent_scores.values())
        if max_score > 0:
            tie_break_priority = {
                AssistantIntent.ACTION_REQUEST: 3,
                AssistantIntent.NLQ: 2,
                AssistantIntent.DOCUMENT_SEARCH: 1,
                AssistantIntent.GENERAL: 0,
            }
            preliminary_intent = max(
                intent_scores,
                key=lambda i: (intent_scores[i], tie_break_priority.get(i, 0)),
            )
            preliminary_confidence = min(0.5 + (max_score * 0.1), 0.85)
        else:
            preliminary_intent = AssistantIntent.GENERAL
            preliminary_confidence = 0.6

        # LLM-basierte Verfeinerung bei niedriger Konfidenz
        if preliminary_confidence < 0.75:
            try:
                llm_intent, llm_confidence = await self._classify_with_llm(message)
                if llm_confidence > preliminary_confidence:
                    return llm_intent, llm_confidence
            except Exception as e:
                logger.warning("intent_classification_llm_error", **safe_error_log(e))

        return preliminary_intent, preliminary_confidence

    async def _classify_with_llm(
        self,
        message: str,
    ) -> Tuple[AssistantIntent, float]:
        """LLM-basierte Intent-Klassifikation.

        Args:
            message: Benutzer-Nachricht

        Returns:
            Tuple aus (Intent, Konfidenz)
        """
        system_prompt = """Du bist ein Intent-Klassifikator für ein Dokumentenmanagementsystem.
Klassifiziere die Benutzeranfrage in eine der folgenden Kategorien:

1. NLQ - Natural Language Query: Benutzer moechte Daten abfragen/berechnen
   Beispiele: "Wie viele Rechnungen sind offen?", "Zeige mir alle Lieferanten"

2. DOCUMENT_SEARCH - Dokumentensuche: Benutzer sucht nach bestimmten Dokumenten
   Beispiele: "Finde die Rechnung von Amazon", "Suche nach Vertrag 2024"

3. ACTION_REQUEST - Aktion ausführen: Benutzer moechte eine Aktion durchführen
   Beispiele: "Genehmige diese Rechnung", "Erstelle einen Export"

4. GENERAL - Allgemeine Frage: Allgemeine Fragen oder Chat
   Beispiele: "Was kannst du?", "Erkläre mir das Skonto"

Antworte NUR mit JSON:
{
    "intent": "NLQ" | "DOCUMENT_SEARCH" | "ACTION_REQUEST" | "GENERAL",
    "confidence": 0.0-1.0,
    "reasoning": "Kurze Begruendung"
}"""

        prompt = f"Klassifiziere diese Anfrage:\n\n{message}"

        response = await self._ollama.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            format_json=True,
        )

        try:
            data = json.loads(response)
            intent_str = data.get("intent", "GENERAL").upper()
            intent_map = {
                "NLQ": AssistantIntent.NLQ,
                "DOCUMENT_SEARCH": AssistantIntent.DOCUMENT_SEARCH,
                "ACTION_REQUEST": AssistantIntent.ACTION_REQUEST,
                "GENERAL": AssistantIntent.GENERAL,
            }
            intent = intent_map.get(intent_str, AssistantIntent.GENERAL)
            confidence = float(data.get("confidence", 0.5))
            return intent, min(max(confidence, 0.0), 1.0)
        except (json.JSONDecodeError, KeyError, ValueError):
            return AssistantIntent.GENERAL, 0.5

    async def process_message(
        self,
        db: AsyncSession,
        message: str,
        user: User,
        company_id: UUID,
        session_id: Optional[str] = None,
        context: Optional[ChatContext] = None,
    ) -> ChatResponse:
        """Verarbeitet eine Chat-Nachricht.

        Args:
            db: Datenbank-Session
            message: Benutzer-Nachricht
            user: Aktueller Benutzer
            company_id: Company-ID
            session_id: Optionale Session-ID
            context: Optionaler Kontext

        Returns:
            ChatResponse mit Antwort und Metadaten
        """
        start_time = time.time()

        # Session-ID generieren wenn nicht vorhanden
        if not session_id:
            session_id = f"chat_{secrets.token_urlsafe(16)}"

        logger.info(
            "assistant_process_message",
            session_id=session_id,
            message_preview=message[:100] if len(message) > 100 else message,
            user_id=str(user.id),
        )

        try:
            # 1. Intent-Klassifikation
            intent, intent_confidence = await self.classify_intent(message, context)

            logger.info(
                "assistant_intent_classified",
                intent=intent.value,
                confidence=intent_confidence,
            )

            # 2. Intent-spezifische Verarbeitung
            if intent == AssistantIntent.NLQ:
                response = await self._process_nlq(
                    db, message, user, company_id, context
                )
            elif intent == AssistantIntent.DOCUMENT_SEARCH:
                response = await self._process_document_search(
                    db, message, user, company_id, context
                )
            elif intent == AssistantIntent.ACTION_REQUEST:
                response = await self._process_action_request(
                    db, message, user, company_id, context
                )
            else:
                response = await self._process_general(
                    db, message, user, company_id, context
                )

            # 3. Metadaten ergaenzen
            response.session_id = session_id
            response.intent = intent
            response.confidence = intent_confidence
            response.processing_time_ms = int((time.time() - start_time) * 1000)

            # 4. Follow-up Vorschläge generieren
            response.follow_up_suggestions = await self._generate_follow_ups(
                intent, message, response
            )

            # 5. Konversation speichern
            await self._save_conversation(
                db, session_id, user.id, company_id, message, response
            )

            return response

        except Exception as e:
            logger.error(
                "assistant_process_error",
                session_id=session_id,
                **safe_error_log(e),
            )
            return ChatResponse(
                response="Entschuldigung, bei der Verarbeitung ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.",
                intent=AssistantIntent.GENERAL,
                session_id=session_id,
                error_message=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def _process_nlq(
        self,
        db: AsyncSession,
        message: str,
        user: User,
        company_id: UUID,
        context: Optional[ChatContext],
    ) -> ChatResponse:
        """Verarbeitet Natural Language Query.

        Generiert SQL aus natürlicher Sprache und führt Abfrage aus.
        """
        system_prompt = f"""Du bist ein SQL-Generator für ein Dokumentenmanagementsystem.
Generiere sichere, parameterisierte SQL-Abfragen basierend auf Benutzeranfragen.

{NLQ_SCHEMA_CONTEXT}

WICHTIG:
- Generiere NUR SELECT-Statements
- Verwende IMMER company_id = :company_id Filter
- Limitiere Ergebnisse auf maximal 100 Zeilen
- Keine DELETE, UPDATE, INSERT, DROP oder andere modifizierende Befehle
- Antworte mit JSON:

{{
    "sql": "SELECT ... FROM ... WHERE company_id = :company_id ...",
    "explanation": "Erklärung was die Abfrage macht",
    "parameters": {{"company_id": "wird automatisch gesetzt"}}
}}

Bei unklaren Anfragen antworte mit:
{{
    "sql": null,
    "explanation": "Erklärung warum keine Abfrage möglich ist",
    "suggestion": "Vorschlag für klarere Formulierung"
}}"""

        prompt = f"Generiere eine SQL-Abfrage für: {message}"

        try:
            response = await self._ollama.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                format_json=True,
                model=settings.DEFAULT_LLM_ANALYSIS,
            )

            data = json.loads(response)
            sql = data.get("sql")
            explanation = data.get("explanation", "")

            if not sql:
                suggestion = data.get("suggestion", "")
                return ChatResponse(
                    response=f"{explanation}\n\nVorschlag: {suggestion}" if suggestion else explanation,
                    intent=AssistantIntent.NLQ,
                    confidence=0.5,
                )

            # Sicherheitsprüfung
            sql_upper = sql.upper()
            forbidden = ["DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
            if any(f in sql_upper for f in forbidden):
                logger.warning(
                    "nlq_forbidden_sql",
                    user_id=str(user.id),
                    sql_preview=sql[:200],
                )
                return ChatResponse(
                    response="Diese Art von Abfrage ist aus Sicherheitsgruenden nicht erlaubt.",
                    intent=AssistantIntent.NLQ,
                    confidence=0.0,
                    error_message="Forbidden SQL operation",
                )

            # Abfrage ausführen
            result = await db.execute(
                text(sql),
                {"company_id": company_id}
            )
            rows = result.fetchall()

            # Ergebnis formatieren
            if not rows:
                response_text = f"{explanation}\n\nErgebnis: Keine Daten gefunden."
            elif len(rows) == 1 and len(rows[0]) == 1:
                # Einzelner Wert
                response_text = f"{explanation}\n\nErgebnis: {rows[0][0]}"
            else:
                # Tabelle formatieren
                columns = result.keys()
                table_rows = [f"| {' | '.join(str(col) for col in row)} |" for row in rows[:20]]
                header = f"| {' | '.join(columns)} |"
                separator = f"| {' | '.join('---' for _ in columns)} |"
                table = f"{header}\n{separator}\n" + "\n".join(table_rows)

                response_text = f"{explanation}\n\n{table}"
                if len(rows) > 20:
                    response_text += f"\n\n...und {len(rows) - 20} weitere Zeilen"

            return ChatResponse(
                response=response_text,
                intent=AssistantIntent.NLQ,
                confidence=0.9,
                model_used=settings.DEFAULT_LLM_ANALYSIS,
            )

        except json.JSONDecodeError:
            return ChatResponse(
                response="Die Anfrage konnte nicht verarbeitet werden. Bitte formulieren Sie sie anders.",
                intent=AssistantIntent.NLQ,
                confidence=0.3,
            )
        except Exception as e:
            logger.error("nlq_execution_error", **safe_error_log(e))
            return ChatResponse(
                response="Bei der Ausführung der Abfrage ist ein Fehler aufgetreten.",
                intent=AssistantIntent.NLQ,
                error_message=str(e),
            )

    async def _process_document_search(
        self,
        db: AsyncSession,
        message: str,
        user: User,
        company_id: UUID,
        context: Optional[ChatContext],
    ) -> ChatResponse:
        """Verarbeitet Dokumentensuche via RAG.

        Nutzt semantische Suche und generiert zusammenfassende Antwort.
        """
        try:
            # RAG Search Service importieren
            from app.services.rag.search_service import RAGSearchService

            rag_service = RAGSearchService()

            # Semantische Suche
            search_results = await rag_service.semantic_search(
                db=db,
                query=message,
                limit=self._max_context_docs,
                threshold=0.6,
                user_id=user.id,
                rerank=True,
            )

            if not search_results.results:
                # Fallback: Keyword-Suche auf documents
                return await self._fallback_document_search(
                    db, message, user, company_id
                )

            # Dokument-Referenzen erstellen
            sources: List[DocumentReference] = []
            context_chunks: List[str] = []

            for result in search_results.results[:self._max_context_docs]:
                # Dokument laden für Metadaten
                doc_stmt = select(Document).where(Document.id == result.document_id)
                doc_result = await db.execute(doc_stmt)
                doc = doc_result.scalar_one_or_none()

                if doc:
                    sources.append(DocumentReference(
                        id=doc.id,
                        filename=doc.filename,
                        document_type=doc.document_type,
                        similarity=result.similarity,
                        snippet=result.chunk_text[:200] if result.chunk_text else None,
                    ))
                    context_chunks.append(result.chunk_text)

            # Antwort mit Kontext generieren
            context_text = "\n\n---\n\n".join(context_chunks)

            system_prompt = """Du bist ein hilfreicher Assistent für ein Dokumentenmanagementsystem.
Beantworte die Frage basierend auf dem gegebenen Kontext aus den Dokumenten.
Antworte auf Deutsch, praezise und hilfreich.
Wenn die Antwort nicht im Kontext zu finden ist, sage das ehrlich."""

            prompt = f"""Kontext aus den gefundenen Dokumenten:

{context_text}

---

Frage des Benutzers: {message}

Bitte beantworte die Frage basierend auf dem Kontext."""

            response_text = await self._ollama.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
            )

            return ChatResponse(
                response=response_text,
                intent=AssistantIntent.DOCUMENT_SEARCH,
                sources=sources,
                confidence=0.85 if sources else 0.5,
                model_used=settings.DEFAULT_LLM_REALTIME,
            )

        except ImportError:
            return await self._fallback_document_search(db, message, user, company_id)
        except Exception as e:
            logger.error("document_search_error", **safe_error_log(e))
            return await self._fallback_document_search(db, message, user, company_id)

    async def _fallback_document_search(
        self,
        db: AsyncSession,
        message: str,
        user: User,
        company_id: UUID,
    ) -> ChatResponse:
        """Fallback-Dokumentensuche mit Keyword-Match."""
        # Einfache Keyword-Suche
        keywords = message.lower().split()

        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    or_(
                        *[Document.extracted_text.ilike(f"%{kw}%") for kw in keywords if len(kw) > 2],
                        *[Document.filename.ilike(f"%{kw}%") for kw in keywords if len(kw) > 2],
                    )
                )
            )
            .order_by(Document.created_at.desc())
            .limit(self._max_context_docs)
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        if not documents:
            return ChatResponse(
                response="Keine passenden Dokumente gefunden. Versuchen Sie andere Suchbegriffe.",
                intent=AssistantIntent.DOCUMENT_SEARCH,
                confidence=0.3,
            )

        sources = [
            DocumentReference(
                id=doc.id,
                filename=doc.filename,
                document_type=doc.document_type,
                similarity=0.5,  # Keyword-Match hat niedrigere Konfidenz
                snippet=doc.extracted_text[:200] if doc.extracted_text else None,
            )
            for doc in documents
        ]

        doc_list = "\n".join([
            f"- **{doc.filename}** ({doc.document_type or 'Unbekannt'})"
            for doc in documents
        ])

        return ChatResponse(
            response=f"Ich habe {len(documents)} Dokumente gefunden:\n\n{doc_list}\n\nKlicken Sie auf ein Dokument für Details.",
            intent=AssistantIntent.DOCUMENT_SEARCH,
            sources=sources,
            confidence=0.6,
        )

    async def _process_action_request(
        self,
        db: AsyncSession,
        message: str,
        user: User,
        company_id: UUID,
        context: Optional[ChatContext],
    ) -> ChatResponse:
        """Verarbeitet Aktionsanfragen.

        Erkennt gewünschte Aktion und schlaegt sie zur Bestätigung vor.
        """
        system_prompt = """Du bist ein Aktions-Interpreter für ein Dokumentenmanagementsystem.
Analysiere die Benutzeranfrage und identifiziere die gewünschte Aktion.

Verfügbare Aktionen:
- approve_document: Dokument genehmigen/freigeben
- reject_document: Dokument ablehnen
- categorize_document: Dokument kategorisieren
- link_entity: Dokument mit Geschäftspartner verknüpfen
- create_task: Aufgabe erstellen
- export_documents: Dokumente exportieren
- schedule_payment: Zahlung planen
- generate_report: Bericht generieren

Antworte mit JSON:
{
    "action_type": "action_name oder null",
    "description": "Beschreibung der Aktion auf Deutsch",
    "parameters": {"key": "value"},
    "confidence": 0.0-1.0,
    "requires_document": true/false
}

Wenn keine klare Aktion erkannt wird, setze action_type auf null."""

        prompt = f"Analysiere diese Aktionsanfrage: {message}"

        if context and context.document_id:
            prompt += f"\n\nKontext: Aktuelles Dokument-ID = {context.document_id}"

        try:
            response = await self._ollama.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                format_json=True,
            )

            data = json.loads(response)
            action_type = data.get("action_type")

            if not action_type:
                return ChatResponse(
                    response="Ich konnte keine eindeutige Aktion erkennen. Könnten Sie bitte genauer beschreiben, was Sie tun moechten?",
                    intent=AssistantIntent.ACTION_REQUEST,
                    confidence=0.3,
                )

            # Aktion erstellen
            action = SuggestedAction(
                action_type=action_type,
                description=data.get("description", ""),
                parameters=data.get("parameters", {}),
                requires_confirmation=True,
                confidence=data.get("confidence", 0.7),
            )

            # Prüfen ob Dokument benötigt wird
            if data.get("requires_document", False) and (not context or not context.document_id):
                return ChatResponse(
                    response=f"Für die Aktion '{action.description}' benötigen Sie ein ausgewaehltes Dokument. Bitte öffnen Sie zuerst das gewünschte Dokument.",
                    intent=AssistantIntent.ACTION_REQUEST,
                    actions=[action],
                    confidence=0.5,
                )

            # Aktion mit Kontext ergaenzen
            if context and context.document_id:
                action.parameters["document_id"] = str(context.document_id)

            return ChatResponse(
                response=f"Ich habe folgende Aktion erkannt:\n\n**{action.description}**\n\nMoechten Sie diese Aktion ausführen? Klicken Sie auf 'Bestätigen' oder sagen Sie 'Ja'.",
                intent=AssistantIntent.ACTION_REQUEST,
                actions=[action],
                confidence=action.confidence,
                model_used=settings.DEFAULT_LLM_REALTIME,
            )

        except json.JSONDecodeError:
            return ChatResponse(
                response="Die Anfrage konnte nicht verarbeitet werden. Bitte beschreiben Sie die gewünschte Aktion genauer.",
                intent=AssistantIntent.ACTION_REQUEST,
                confidence=0.3,
            )

    async def _process_general(
        self,
        db: AsyncSession,
        message: str,
        user: User,
        company_id: UUID,
        context: Optional[ChatContext],
    ) -> ChatResponse:
        """Verarbeitet allgemeine Fragen und Chat."""
        system_prompt = """Du bist ein hilfreicher Assistent für das Ablage-System, ein Dokumentenmanagementsystem.
Beantworte Fragen freundlich und kompetent auf Deutsch.

Du kannst helfen mit:
- Fragen zur Bedienung des Systems
- Erklärungen zu Funktionen (OCR, Rechnungsverarbeitung, Buchhaltung)
- Allgemeinen Fragen zu Dokumentenmanagement
- Informationen über Skonto, Mahnwesen, DATEV-Export

Halte Antworten praegnant und hilfreich."""

        prompt = f"Benutzeranfrage: {message}"

        if context:
            if context.current_view:
                prompt += f"\nAktueller Bereich: {context.current_view}"
            if context.document_id:
                prompt += f"\nAktuelles Dokument: {context.document_id}"

        response_text = await self._ollama.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.5,
        )

        return ChatResponse(
            response=response_text,
            intent=AssistantIntent.GENERAL,
            confidence=0.8,
            model_used=settings.DEFAULT_LLM_REALTIME,
        )

    async def _generate_follow_ups(
        self,
        intent: AssistantIntent,
        message: str,
        response: ChatResponse,
    ) -> List[str]:
        """Generiert Follow-up Vorschläge."""
        follow_ups = []

        if intent == AssistantIntent.NLQ:
            follow_ups = [
                "Zeige mir die Details",
                "Exportiere als CSV",
                "Vergleiche mit Vormonat",
            ]
        elif intent == AssistantIntent.DOCUMENT_SEARCH:
            if response.sources:
                follow_ups = [
                    "Zeige ähnliche Dokumente",
                    "Öffne das erste Dokument",
                    "Suche verfeinern",
                ]
            else:
                follow_ups = [
                    "Andere Suchbegriffe versuchen",
                    "Alle Dokumente anzeigen",
                ]
        elif intent == AssistantIntent.ACTION_REQUEST:
            if response.actions:
                follow_ups = [
                    "Ja, ausführen",
                    "Nein, abbrechen",
                    "Mehr Details",
                ]
            else:
                follow_ups = [
                    "Was kann ich tun?",
                    "Hilfe zu Aktionen",
                ]
        else:
            follow_ups = [
                "Was kannst du noch?",
                "Zeige meine Dokumente",
                "Offene Aufgaben anzeigen",
            ]

        return follow_ups[:3]

    async def _save_conversation(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: UUID,
        company_id: UUID,
        message: str,
        response: ChatResponse,
    ) -> None:
        """Speichert die Konversation in der Datenbank."""
        try:
            # Bestehende Konversation suchen oder erstellen
            stmt = select(AIConversation).where(AIConversation.session_id == session_id)
            result = await db.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                conversation = AIConversation(
                    session_id=session_id,
                    user_id=user_id,
                    company_id=company_id,
                    title=message[:100] if len(message) > 100 else message,
                    language="de",
                )
                db.add(conversation)
                await db.flush()

            # Benutzer-Nachricht speichern
            user_message = AIConversationMessage(
                conversation_id=conversation.id,
                role=AIMessageRole.USER.value,
                content=message,
                intent=response.intent.value,
                confidence=response.confidence,
            )
            db.add(user_message)

            # Assistenten-Antwort speichern
            assistant_message = AIConversationMessage(
                conversation_id=conversation.id,
                role=AIMessageRole.ASSISTANT.value,
                content=response.response,
                search_results_count=len(response.sources),
                actions_proposed=len(response.actions),
                processing_time_ms=response.processing_time_ms,
                model_used=response.model_used,
                tokens_used=response.tokens_used,
                extra_data={
                    "follow_ups": response.follow_up_suggestions,
                },
                referenced_documents=[str(s.id) for s in response.sources],
            )
            db.add(assistant_message)

            # Konversation aktualisieren
            conversation.message_count += 2
            conversation.action_count += len(response.actions)
            conversation.last_message_at = datetime.now(timezone.utc)

            # Aktionen speichern
            for action in response.actions:
                action_record = AIConversationAction(
                    conversation_id=conversation.id,
                    message_id=assistant_message.id,
                    action_type=action.action_type,
                    description=action.description,
                    parameters=action.parameters,
                    status=AIActionStatus.PROPOSED.value,
                    requires_confirmation=action.requires_confirmation,
                )
                db.add(action_record)

            await db.commit()

        except Exception as e:
            logger.error("conversation_save_error", **safe_error_log(e))
            # Nicht critical - Konversation wird trotzdem zurückgegeben

    async def get_chat_history(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: UUID,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Ruft Chat-Historie für eine Session ab.

        Args:
            db: Datenbank-Session
            session_id: Session-ID
            user_id: Benutzer-ID (Sicherheitsprüfung)
            limit: Maximale Anzahl Nachrichten

        Returns:
            Liste von Nachrichten als Dictionaries
        """
        stmt = (
            select(AIConversationMessage)
            .join(AIConversation)
            .where(
                and_(
                    AIConversation.session_id == session_id,
                    AIConversation.user_id == user_id,
                )
            )
            .order_by(AIConversationMessage.created_at.asc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        messages = result.scalars().all()

        return [msg.to_dict() for msg in messages]

    async def submit_feedback(
        self,
        db: AsyncSession,
        message_id: UUID,
        user_id: UUID,
        feedback_type: str,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
        correction: Optional[str] = None,
    ) -> bool:
        """Speichert Benutzer-Feedback zu einer Antwort.

        Args:
            db: Datenbank-Session
            message_id: Nachrichten-ID
            user_id: Benutzer-ID
            feedback_type: Feedback-Typ (helpful, not_helpful, incorrect, etc.)
            rating: Optionale Sternebewertung (1-5)
            comment: Optionaler Kommentar
            correction: Optionale Korrektur

        Returns:
            True bei Erfolg
        """
        try:
            # Validiere Feedback-Typ
            valid_types = [f.value for f in AIFeedbackType]
            if feedback_type not in valid_types:
                feedback_type = AIFeedbackType.OTHER.value

            # Feedback erstellen
            feedback = AIConversationFeedback(
                message_id=message_id,
                user_id=user_id,
                feedback_type=feedback_type,
                rating=rating if rating and 1 <= rating <= 5 else None,
                comment=comment,
                correction=correction,
            )
            db.add(feedback)
            await db.commit()

            logger.info(
                "assistant_feedback_saved",
                message_id=str(message_id),
                feedback_type=feedback_type,
            )

            return True

        except Exception as e:
            logger.error("feedback_save_error", **safe_error_log(e))
            return False

    async def close(self) -> None:
        """Schließt alle Verbindungen."""
        await self._ollama.close()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


_assistant_service: Optional[ConversationalAssistantService] = None


def get_conversational_assistant_service() -> ConversationalAssistantService:
    """Holt oder erstellt den Singleton-Service.

    Returns:
        ConversationalAssistantService Instanz
    """
    global _assistant_service
    if _assistant_service is None:
        _assistant_service = ConversationalAssistantService()
    return _assistant_service


async def get_assistant_service() -> ConversationalAssistantService:
    """Async Dependency für FastAPI.

    Returns:
        ConversationalAssistantService Instanz
    """
    return get_conversational_assistant_service()

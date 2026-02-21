# -*- coding: utf-8 -*-
"""AI Chat Service - Eingebetteter KI-Assistent für das Briefing Cockpit.

Stellt einen kontextsensitiven deutschen KI-Chat-Assistenten bereit:
- Beantwortet Fragen zu Dokumenten, Entitäten und Rechnungen
- Nutzt den LLMService (Ollama / Qwen3) für lokale, datenschutzkonforme Verarbeitung
- Verwaltet Chat-Sessions mit Gesprächshistorie
- Erstellt strukturierte Antworten mit optionalen Daten-Anhängen

Feinpoliert und durchdacht - Enterprise AI Chat für das Büro der Zukunft.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
)
from app.services.rag.llm_service import (
    LLMContextType,
    LLMMessage,
    LLMResponse,
    LLMService,
    get_llm_service,
)

logger = structlog.get_logger(__name__)

# Konfiguration
MAX_CONTEXT_DOCUMENTS: int = 5      # Maximale Dokumente im LLM-Kontext
MAX_HISTORY_MESSAGES: int = 10      # Maximale Gesprächshistorie pro Anfrage
MAX_RESPONSE_TOKENS: int = 1024     # Maximale Token-Anzahl für Antworten
MAX_MESSAGE_LENGTH: int = 10_000    # Maximale Eingabelänge
SESSION_MAX_MESSAGES: int = 100     # Maximale Nachrichten pro Session

# System-Prompt auf Deutsch
_SYSTEM_PROMPT = """Du bist ein intelligenter Assistent für das Ablage-System, ein Enterprise-Dokumentenverwaltungssystem.

Deine Aufgaben:
- Beantworte Fragen zu Dokumenten, Rechnungen, Lieferanten und Kunden auf Deutsch
- Unterstütze bei der Analyse von Geschäftsprozessen und Finanzdaten
- Hilf beim Verstehen von GoBD-Compliance-Anforderungen
- Gib konkrete, handlungsorientierte Empfehlungen

Regeln:
- Antworte IMMER auf Deutsch
- Halte Antworten präzise und praxisorientiert
- Nenne bei Datenabfragen konkrete Zahlen aus dem bereitgestellten Kontext
- Schütze sensible Daten: Nenne keine vollständigen IBANs oder Kundennummern
- Bei unklaren Fragen: Bitte um Präzisierung
- Formatiere wichtige Informationen mit Markdown (Listen, Fettdruck)

Du hast Zugriff auf die folgenden Unternehmensdaten:
- Dokumente (Rechnungen, Verträge, Lieferscheine, etc.)
- Geschäftspartner (Kunden, Lieferanten)
- Rechnungsverfolgung und Zahlungsstatus
- Compliance-Status (GoBD)"""

# Mustererkennung für Kontexttypen
_INVOICE_PATTERN = re.compile(
    r"rechnung|invoice|faktura|zahlung|payment|fällig|überfällig|skonto",
    re.IGNORECASE,
)
_DOCUMENT_PATTERN = re.compile(
    r"dokument|document|datei|file|ocr|archiv|scan",
    re.IGNORECASE,
)
_ENTITY_PATTERN = re.compile(
    r"lieferant|supplier|kunde|customer|partner|firma|company",
    re.IGNORECASE,
)
_COMPLIANCE_PATTERN = re.compile(
    r"gobd|compliance|archivierung|aufbewahrung|steuer|finanzamt",
    re.IGNORECASE,
)


# =============================================================================
# Datenklassen
# =============================================================================


@dataclass
class ChatMessage:
    """Einzelne Chat-Nachricht."""
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert die Nachricht als Dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "ChatMessage":
        """Deserialisiert eine Nachricht aus einem Dictionary.

        Args:
            data: Serialisiertes Dictionary

        Returns:
            ChatMessage-Instanz
        """
        ts_raw = data.get("timestamp")
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw)
        else:
            ts = datetime.now(timezone.utc)
        return cls(
            role=str(data.get("role", "user")),
            content=str(data.get("content", "")),
            timestamp=ts,
        )


@dataclass
class DataAttachment:
    """Daten-Anhang zu einer KI-Antwort (z.B. Liste von Rechnungen)."""
    attachment_type: str  # "invoices", "documents", "entities", "stats"
    title: str
    data: List[Dict[str, object]]

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert den Anhang als Dictionary."""
        return {
            "attachment_type": self.attachment_type,
            "title": self.title,
            "data": self.data,
        }


@dataclass
class AIChatResponse:
    """Strukturierte Antwort des KI-Assistenten."""
    session_id: str
    message: str
    thinking: Optional[str] = None
    attachments: List[DataAttachment] = field(default_factory=list)
    model_used: str = ""
    generation_time_ms: int = 0
    tokens_used: int = 0

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert die Antwort als Dictionary."""
        return {
            "session_id": self.session_id,
            "message": self.message,
            "thinking": self.thinking,
            "attachments": [a.to_dict() for a in self.attachments],
            "model_used": self.model_used,
            "generation_time_ms": self.generation_time_ms,
            "tokens_used": self.tokens_used,
        }


@dataclass
class ChatSession:
    """Chat-Session mit Gesprächshistorie."""
    session_id: str
    company_id: UUID
    user_id: UUID
    title: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def message_count(self) -> int:
        """Anzahl Nachrichten in der Session (exkl. System)."""
        return sum(1 for m in self.messages if m.role != "system")

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert die Session als Dictionary."""
        return {
            "session_id": self.session_id,
            "company_id": str(self.company_id),
            "user_id": str(self.user_id),
            "title": self.title,
            "message_count": self.message_count,
            "messages": [m.to_dict() for m in self.messages if m.role != "system"],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# =============================================================================
# In-Memory Session Store (wird durch DB-Persistenz in models_morning_briefing ersetzt)
# =============================================================================


class SessionStore:
    """Einfacher In-Memory Session Store.

    In der Produktion werden Sessions via ai_chat_sessions-Tabelle
    persistent gespeichert. Dieser Store dient als schneller Lese-Cache.
    """

    def __init__(self) -> None:
        """Initialisiert den Session Store."""
        self._sessions: Dict[str, ChatSession] = {}

    def get(self, session_id: str) -> Optional[ChatSession]:
        """Gibt eine Session zurück oder None.

        Args:
            session_id: Session-ID

        Returns:
            ChatSession oder None
        """
        return self._sessions.get(session_id)

    def store(self, session: ChatSession) -> None:
        """Speichert oder aktualisiert eine Session.

        Args:
            session: Chat-Session
        """
        session.updated_at = datetime.now(timezone.utc)
        self._sessions[session.session_id] = session

    def list_for_company_user(
        self,
        company_id: UUID,
        user_id: UUID,
        limit: int = 20,
    ) -> List[ChatSession]:
        """Listet Sessions für ein Unternehmen und Benutzer auf.

        Args:
            company_id: Firmen-ID
            user_id: Benutzer-ID
            limit: Maximale Anzahl

        Returns:
            Liste von ChatSessions, neueste zuerst
        """
        matching = [
            s for s in self._sessions.values()
            if s.company_id == company_id and s.user_id == user_id
        ]
        matching.sort(key=lambda s: s.updated_at, reverse=True)
        return matching[:limit]

    def delete(self, session_id: str) -> bool:
        """Löscht eine Session.

        Args:
            session_id: Session-ID

        Returns:
            True wenn gelöscht, False wenn nicht gefunden
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False


# =============================================================================
# AI Chat Service
# =============================================================================


class AIChatService:
    """KI-Assistent Service für das Morning Briefing Cockpit.

    Bietet kontextsensitiven Chat mit Zugriff auf Unternehmensdaten.
    Nutzt Ollama (Qwen3) für lokale, datenschutzkonforme LLM-Inference.

    Features:
    - Automatische Kontexterkennung (Rechnungen, Dokumente, Entitäten)
    - Strukturierte Daten-Anhänge in Antworten
    - Gesprächshistorie über Sessions
    - Vollständig auf Deutsch
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        """Initialisiert den AIChatService.

        Args:
            llm_service: Optional externer LLMService (für Tests)
        """
        self._llm: LLMService = llm_service or get_llm_service()
        self._session_store = SessionStore()

    async def process_message(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        message: str,
        session_id: Optional[str] = None,
    ) -> AIChatResponse:
        """Verarbeitet eine Chat-Nachricht und generiert eine KI-Antwort.

        Der Service:
        1. Lädt oder erstellt die Chat-Session
        2. Erkennt den Kontext (Rechnungen, Dokumente, etc.)
        3. Lädt relevante Daten aus der DB
        4. Generiert eine kontextuelle LLM-Antwort
        5. Speichert die Nachricht in der Session

        Args:
            db: Async-Datenbank-Session
            company_id: Firmen-ID für Mandantenisolierung
            user_id: Benutzer-ID
            message: Eingabe-Nachricht des Benutzers
            session_id: Optionale Session-ID (neue Session wenn None)

        Returns:
            AIChatResponse mit Antwort und optionalen Daten-Anhängen
        """
        # Session laden oder erstellen
        session = self._get_or_create_session(
            session_id=session_id,
            company_id=company_id,
            user_id=user_id,
            first_message=message,
        )

        logger.info(
            "ai_chat_nachricht_eingang",
            session_id=session.session_id,
            company_id=str(company_id),
            message_length=len(message),
        )

        # Benutzer-Nachricht zur Session hinzufügen
        user_msg = ChatMessage(role="user", content=message)
        session.messages.append(user_msg)

        # Kontext und Daten ermitteln
        context_data, attachments = await self._gather_context(
            db=db,
            company_id=company_id,
            message=message,
        )

        # LLM-Nachrichten aufbauen
        llm_messages = self._build_llm_messages(
            session=session,
            context_data=context_data,
        )

        # LLM-Antwort generieren
        llm_response = await self._generate_llm_response(
            messages=llm_messages,
            message=message,
        )

        # Assistent-Antwort zur Session hinzufügen
        assistant_msg = ChatMessage(
            role="assistant",
            content=llm_response.content,
        )
        session.messages.append(assistant_msg)

        # Session kürzen wenn zu lang
        if len(session.messages) > SESSION_MAX_MESSAGES:
            # System-Nachricht erhalten, älteste User/Assistant-Nachrichten löschen
            system_msgs = [m for m in session.messages if m.role == "system"]
            other_msgs = [m for m in session.messages if m.role != "system"]
            trim_count = len(other_msgs) - (SESSION_MAX_MESSAGES - len(system_msgs))
            if trim_count > 0:
                other_msgs = other_msgs[trim_count:]
            session.messages = system_msgs + other_msgs

        # Session speichern
        self._session_store.store(session)

        logger.info(
            "ai_chat_antwort_generiert",
            session_id=session.session_id,
            response_length=len(llm_response.content),
            model=llm_response.model,
            tokens_output=llm_response.tokens_output,
        )

        return AIChatResponse(
            session_id=session.session_id,
            message=llm_response.content,
            thinking=llm_response.thinking_content,
            attachments=attachments,
            model_used=llm_response.model,
            generation_time_ms=llm_response.generation_time_ms,
            tokens_used=llm_response.tokens_output,
        )

    def get_sessions(
        self,
        company_id: UUID,
        user_id: UUID,
        limit: int = 20,
    ) -> List[ChatSession]:
        """Gibt Chat-Sessions für einen Benutzer zurück.

        Args:
            company_id: Firmen-ID
            user_id: Benutzer-ID
            limit: Maximale Anzahl Sessions

        Returns:
            Liste von ChatSessions, neueste zuerst
        """
        return self._session_store.list_for_company_user(
            company_id=company_id,
            user_id=user_id,
            limit=limit,
        )

    def get_session(
        self,
        session_id: str,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[ChatSession]:
        """Gibt eine einzelne Session zurück.

        Args:
            session_id: Session-ID
            company_id: Firmen-ID (für Isolierung)
            user_id: Benutzer-ID (für Isolierung)

        Returns:
            ChatSession oder None wenn nicht gefunden / kein Zugriff
        """
        session = self._session_store.get(session_id)
        if session is None:
            return None
        # Mandantenisolierung und Benutzerisolierung
        if session.company_id != company_id or session.user_id != user_id:
            logger.warning(
                "ai_chat_session_zugriff_verweigert",
                session_id=session_id,
                company_id=str(company_id),
            )
            return None
        return session

    def delete_session(
        self,
        session_id: str,
        company_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Löscht eine Chat-Session.

        Args:
            session_id: Session-ID
            company_id: Firmen-ID (Sicherheitsprüfung)
            user_id: Benutzer-ID (Sicherheitsprüfung)

        Returns:
            True wenn gelöscht, False wenn nicht gefunden oder kein Zugriff
        """
        session = self.get_session(session_id, company_id, user_id)
        if session is None:
            return False
        return self._session_store.delete(session_id)

    # =========================================================================
    # Interne Hilfsmethoden
    # =========================================================================

    def _get_or_create_session(
        self,
        session_id: Optional[str],
        company_id: UUID,
        user_id: UUID,
        first_message: str,
    ) -> ChatSession:
        """Lädt eine bestehende Session oder erstellt eine neue.

        Args:
            session_id: Optionale Session-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            first_message: Erste Nachricht (für Titel-Generierung)

        Returns:
            ChatSession (neu oder bestehend)
        """
        if session_id:
            existing = self._session_store.get(session_id)
            if (
                existing is not None
                and existing.company_id == company_id
                and existing.user_id == user_id
            ):
                return existing

        # Neue Session erstellen
        new_id = f"session_{uuid.uuid4().hex}"
        title = self._generate_session_title(first_message)

        session = ChatSession(
            session_id=new_id,
            company_id=company_id,
            user_id=user_id,
            title=title,
            messages=[
                ChatMessage(role="system", content=_SYSTEM_PROMPT)
            ],
        )
        return session

    def _generate_session_title(self, first_message: str) -> str:
        """Generiert einen Session-Titel aus der ersten Nachricht.

        Args:
            first_message: Erste Benutzer-Nachricht

        Returns:
            Kurzer Titel für die Session (max. 60 Zeichen)
        """
        # Ersten Satz oder erste 60 Zeichen als Titel
        clean = first_message.strip()
        if len(clean) <= 60:
            return clean
        # Am letzten Leerzeichen vor Zeichen 60 abschneiden
        cut = clean[:57]
        last_space = cut.rfind(" ")
        if last_space > 30:
            cut = cut[:last_space]
        return cut + "..."

    async def _gather_context(
        self,
        db: AsyncSession,
        company_id: UUID,
        message: str,
    ) -> tuple[str, List[DataAttachment]]:
        """Sammelt relevante Daten basierend auf dem Nachrichten-Inhalt.

        Erkennt den Kontext automatisch via Regex-Muster und lädt
        die passenden Daten aus der Datenbank.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            message: Benutzer-Nachricht

        Returns:
            Tupel aus (Kontext-String für LLM, Daten-Anhänge)
        """
        context_parts: List[str] = []
        attachments: List[DataAttachment] = []

        try:
            # Rechnungskontext
            if _INVOICE_PATTERN.search(message):
                invoice_context, invoice_attachment = await self._load_invoice_context(
                    db=db,
                    company_id=company_id,
                )
                if invoice_context:
                    context_parts.append(invoice_context)
                if invoice_attachment:
                    attachments.append(invoice_attachment)

            # Dokumentenkontext
            if _DOCUMENT_PATTERN.search(message):
                doc_context, doc_attachment = await self._load_document_context(
                    db=db,
                    company_id=company_id,
                )
                if doc_context:
                    context_parts.append(doc_context)
                if doc_attachment:
                    attachments.append(doc_attachment)

            # Entitätskontext (Kunden/Lieferanten)
            if _ENTITY_PATTERN.search(message):
                entity_context = await self._load_entity_context(
                    db=db,
                    company_id=company_id,
                )
                if entity_context:
                    context_parts.append(entity_context)

        except Exception as exc:
            logger.warning(
                "ai_chat_kontext_fehler",
                **safe_error_log(exc),
                company_id=str(company_id),
            )
            context_parts.append(
                "Hinweis: Einige Unternehmensdaten konnten nicht geladen werden."
            )

        combined_context = "\n\n".join(context_parts) if context_parts else ""
        return combined_context, attachments

    async def _load_invoice_context(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> tuple[str, Optional[DataAttachment]]:
        """Lädt Rechnungskontext für das LLM.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Tupel aus (Kontext-String, Optionaler Daten-Anhang)
        """
        try:
            # Offene Rechnungen (neueste 5)
            stmt = (
                select(InvoiceTracking)
                .where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["open", "partial", "overdue"]),
                        InvoiceTracking.deleted_at.is_(None),
                    )
                )
                .order_by(desc(InvoiceTracking.invoice_date))
                .limit(MAX_CONTEXT_DOCUMENTS)
            )
            result = await db.execute(stmt)
            invoices = result.scalars().all()

            if not invoices:
                return "Rechnungskontext: Keine offenen Rechnungen gefunden.", None

            # Statistiken berechnen
            total_open = len(invoices)
            invoice_data: List[Dict[str, object]] = []

            for inv in invoices:
                inv_dict: Dict[str, object] = {
                    "id": str(inv.id),
                    "status": inv.status,
                    "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                    "due_date": inv.due_date.isoformat() if inv.due_date else None,
                    "amount": float(inv.total_amount) if inv.total_amount else None,
                    "currency": getattr(inv, "currency", "EUR"),
                }
                invoice_data.append(inv_dict)

            # Kontext-String für LLM
            context = (
                f"Rechnungsübersicht: {total_open} offene Rechnung(en). "
                "Aktuell offene Rechnungen: " +
                ", ".join(
                    f"#{str(inv.id)[:8]} (Status: {inv.status})"
                    for inv in invoices[:3]
                )
            )

            attachment = DataAttachment(
                attachment_type="invoices",
                title=f"Offene Rechnungen ({total_open})",
                data=invoice_data,
            )

            return context, attachment

        except Exception as exc:
            logger.warning(
                "ai_chat_rechnung_kontext_fehler",
                **safe_error_log(exc),
            )
            return "", None

    async def _load_document_context(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> tuple[str, Optional[DataAttachment]]:
        """Lädt Dokumentenkontext für das LLM.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Tupel aus (Kontext-String, Optionaler Daten-Anhang)
        """
        try:
            # Aktuellste Dokumente
            stmt = (
                select(Document)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                    )
                )
                .order_by(desc(Document.created_at))
                .limit(MAX_CONTEXT_DOCUMENTS)
            )
            result = await db.execute(stmt)
            documents = result.scalars().all()

            # Queue-Statistik
            stmt_queue = (
                select(func.count(Document.id))
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.status.in_(["pending", "queued", "processing"]),
                    )
                )
            )
            result_queue = await db.execute(stmt_queue)
            queue_count = result_queue.scalar_one_or_none() or 0

            # Gesamtanzahl
            stmt_total = (
                select(func.count(Document.id))
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                    )
                )
            )
            result_total = await db.execute(stmt_total)
            total_count = result_total.scalar_one_or_none() or 0

            doc_data: List[Dict[str, object]] = [
                {
                    "id": str(doc.id),
                    "filename": doc.original_filename,
                    "type": doc.document_type,
                    "status": doc.status,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                }
                for doc in documents
            ]

            context = (
                f"Dokumentenübersicht: {total_count} Dokument(e) gesamt, "
                f"{queue_count} in der OCR-Queue. "
                "Neueste Dokumente: " +
                ", ".join(d.original_filename for d in documents[:3] if hasattr(d, "original_filename"))
            )

            attachment = DataAttachment(
                attachment_type="documents",
                title=f"Aktuelle Dokumente ({total_count} gesamt)",
                data=doc_data,
            )

            return context, attachment

        except Exception as exc:
            logger.warning(
                "ai_chat_dokument_kontext_fehler",
                **safe_error_log(exc),
            )
            return "", None

    async def _load_entity_context(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> str:
        """Lädt Entitätskontext (Kunden/Lieferanten) für das LLM.

        DATENSCHUTZ: Gibt keine vollständigen Kundennummern oder IBANs zurück.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Kontext-String für das LLM
        """
        try:
            # Top-Geschäftspartner (anonymisiert)
            stmt = (
                select(
                    BusinessEntity.entity_type,
                    func.count(BusinessEntity.id).label("count"),
                )
                .where(BusinessEntity.company_id == company_id)
                .group_by(BusinessEntity.entity_type)
            )
            result = await db.execute(stmt)
            entity_stats = result.all()

            if not entity_stats:
                return "Keine Geschäftspartner-Daten verfügbar."

            stats_parts: List[str] = []
            for entity_type, count in entity_stats:
                label = "Kunden" if entity_type == "customer" else "Lieferanten"
                stats_parts.append(f"{count} {label}")

            return "Geschäftspartner: " + ", ".join(stats_parts) + "."

        except Exception as exc:
            logger.warning(
                "ai_chat_entitaet_kontext_fehler",
                **safe_error_log(exc),
            )
            return ""

    def _build_llm_messages(
        self,
        session: ChatSession,
        context_data: str,
    ) -> List[LLMMessage]:
        """Baut die Nachrichten-Liste für die LLM-Anfrage auf.

        Fügt den Datenkontext als zusätzliche System-Nachricht ein.

        Args:
            session: Chat-Session mit Gesprächshistorie
            context_data: Gesammelter Datenkontext

        Returns:
            Liste von LLMMessage für den LLM-Service
        """
        llm_messages: List[LLMMessage] = []

        # System-Prompt
        system_content = _SYSTEM_PROMPT
        if context_data:
            system_content = (
                _SYSTEM_PROMPT
                + "\n\n## Aktuelle Unternehmensdaten\n"
                + context_data
            )

        llm_messages.append(LLMMessage(role="system", content=system_content))

        # Gesprächshistorie (letzte MAX_HISTORY_MESSAGES Nachrichten ohne System)
        history = [m for m in session.messages if m.role != "system"]
        # Letzte Nachricht ist die aktuelle Benutzer-Nachricht, daher bis -1
        recent_history = history[-(MAX_HISTORY_MESSAGES + 1):]

        for msg in recent_history:
            llm_messages.append(LLMMessage(role=msg.role, content=msg.content))

        return llm_messages

    async def _generate_llm_response(
        self,
        messages: List[LLMMessage],
        message: str,
    ) -> LLMResponse:
        """Generiert eine LLM-Antwort mit Fehlerbehandlung.

        Args:
            messages: Vollständige Nachrichtenliste inkl. Kontext
            message: Original-Benutzer-Nachricht

        Returns:
            LLMResponse mit Antwort und Metadaten
        """
        try:
            # Kontext-Typ bestimmen für optimales Model-Routing
            context_type = LLMContextType.REALTIME

            if _COMPLIANCE_PATTERN.search(message):
                # Compliance-Fragen brauchen mehr Reasoning-Kapazität
                context_type = LLMContextType.GENERAL

            response = await self._llm.generate(
                messages=messages,
                context_type=context_type,
                enable_thinking=False,  # Schnelle Antworten für Chat
                max_tokens=MAX_RESPONSE_TOKENS,
            )
            return response

        except Exception as exc:
            logger.error(
                "ai_chat_llm_fehler",
                **safe_error_log(exc),
            )
            # Fallback-Antwort bei LLM-Fehler
            from app.services.rag.llm_service import LLMResponse
            return LLMResponse(
                content=(
                    "Entschuldigung, ich konnte Ihre Anfrage gerade nicht bearbeiten. "
                    "Bitte versuchen Sie es erneut oder wenden Sie sich an den Support."
                ),
                model="fallback",
                generation_time_ms=0,
            )


# =============================================================================
# Factory
# =============================================================================

_ai_chat_service: Optional[AIChatService] = None


def get_ai_chat_service() -> AIChatService:
    """Gibt eine Singleton-Instanz des AIChatService zurück.

    Returns:
        AIChatService-Instanz
    """
    global _ai_chat_service
    if _ai_chat_service is None:
        _ai_chat_service = AIChatService()
    return _ai_chat_service

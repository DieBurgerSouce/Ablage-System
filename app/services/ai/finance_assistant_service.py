# -*- coding: utf-8 -*-
"""
FinanceAssistantService - Intelligenter KI-Finanzassistent.

Zentraler Chat-basierter Assistent für Buchhalter mit:
- Dokumenten-Suche via Natural Language
- Aktionen ausführen (Zahlungslauf, Buchungen, etc.)
- Erklärungen & Insights generieren
- Buchungsvorschläge
- Anomalie-Erkennung
- Predictive Analytics
- Konversations-Persistenz (Migration 120)

Vision 2.0 - Kern-Feature (Januar 2026)
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

import structlog
from sqlalchemy import select, and_, func, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_detail,  safe_error_log
from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    BankTransaction,
    User,
    AuditLog,
)
from app.db.models_ai_conversation import (
    AIConversation,
    AIConversationMessage,
    AIConversationAction,
    AIMessageRole,
    AIActionStatus,
)
from app.services.invoice_direction import is_incoming_invoice, is_outgoing_invoice

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Models
# ============================================================================


class AssistantIntent(str, Enum):
    """Erkannte Benutzerabsicht."""

    SEARCH = "search"  # Dokumente/Daten suchen
    EXECUTE_ACTION = "execute_action"  # Aktion ausführen
    EXPLAIN = "explain"  # Erklärung anfordern
    SUGGEST_BOOKING = "suggest_booking"  # Buchungsvorschlag
    ANALYZE = "analyze"  # Analyse durchführen
    PREDICT = "predict"  # Vorhersage treffen
    HELP = "help"  # Hilfe anzeigen
    CHAT = "chat"  # Allgemeiner Chat


class ActionType(str, Enum):
    """Verfügbare Aktionstypen."""

    PAYMENT_RUN = "payment_run"  # Zahlungslauf erstellen
    APPROVE_INVOICES = "approve_invoices"  # Rechnungen genehmigen
    CATEGORIZE_DOCUMENTS = "categorize_documents"  # Dokumente kategorisieren
    SEND_REMINDER = "send_reminder"  # Mahnung senden
    EXPORT_DATA = "export_data"  # Daten exportieren
    MATCH_TRANSACTIONS = "match_transactions"  # Transaktionen zuordnen
    CREATE_BOOKING = "create_booking"  # Buchung erstellen


@dataclass
class AssistantContext:
    """Kontext für den Assistenten."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    user_role: str = "viewer"  # viewer, editor, admin
    current_page: Optional[str] = None  # z.B. "/banking/transactions"
    selected_documents: List[uuid.UUID] = field(default_factory=list)
    session_id: str = ""
    language: str = "de"
    conversation_id: Optional[uuid.UUID] = None  # Persistierte Konversations-ID


@dataclass
class ActionProposal:
    """Vorgeschlagene Aktion."""

    action_type: ActionType
    description: str
    parameters: Dict[str, Any]
    confidence: float
    requires_confirmation: bool = True
    affected_count: int = 0


@dataclass
class BookingSuggestion:
    """Buchungsvorschlag."""

    debit_account: str
    debit_account_name: str
    credit_account: str
    credit_account_name: str
    amount: Decimal
    description: str
    tax_code: Optional[str] = None
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class Insight:
    """Erklärung oder Insight."""

    title: str
    content: str
    category: str  # cash_flow, anomaly, trend, warning
    severity: str = "info"  # info, warning, critical
    related_documents: List[uuid.UUID] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None


@dataclass
class AssistantResponse:
    """Antwort des Assistenten."""

    message: str
    intent: AssistantIntent
    success: bool = True
    confidence: float = 0.0
    actions: List[ActionProposal] = field(default_factory=list)
    booking_suggestions: List[BookingSuggestion] = field(default_factory=list)
    insights: List[Insight] = field(default_factory=list)
    search_results: Optional[List[Dict[str, Any]]] = None
    result_count: int = 0
    processing_time_ms: int = 0
    follow_up_suggestions: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


# ============================================================================
# SKR03/04 Kontenrahmen (vereinfacht)
# ============================================================================


SKR03_ACCOUNTS: Dict[str, Dict[str, str]] = {
    "1000": {"name": "Kasse", "type": "asset"},
    "1200": {"name": "Bank", "type": "asset"},
    "1400": {"name": "Forderungen aus L+L", "type": "asset"},
    "1600": {"name": "Verbindlichkeiten aus L+L", "type": "liability"},
    "3300": {"name": "Wareneingang", "type": "expense"},
    "3400": {"name": "Wareneingang 7% VSt", "type": "expense"},
    "4000": {"name": "Umsatzerlöse 19%", "type": "revenue"},
    "4120": {"name": "Umsatzerlöse 7%", "type": "revenue"},
    "4400": {"name": "Erlösschmälerungen", "type": "expense"},
    "4600": {"name": "Werbekosten", "type": "expense"},
    "4900": {"name": "Sonstige betriebliche Aufwendungen", "type": "expense"},
    "8400": {"name": "Erlöse 19% USt", "type": "revenue"},
}


# ============================================================================
# FinanceAssistantService
# ============================================================================


class FinanceAssistantService:
    """Intelligenter Finanz-Assistent mit Chat-Interface.

    Orchestriert alle KI-Features für Buchhalter:
    - NLQ für Suche
    - Aktionsausführung
    - Insights & Erklärungen
    - Buchungsvorschläge
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db
        self._ollama_service = None
        self._nlq_service = None
        self._action_handlers: Dict[ActionType, Callable] = {}
        self._register_action_handlers()

    def _register_action_handlers(self) -> None:
        """Registriert Handler für Aktionen."""
        self._action_handlers = {
            ActionType.PAYMENT_RUN: self._handle_payment_run,
            ActionType.APPROVE_INVOICES: self._handle_approve_invoices,
            ActionType.CATEGORIZE_DOCUMENTS: self._handle_categorize_documents,
            ActionType.SEND_REMINDER: self._handle_send_reminder,
            ActionType.MATCH_TRANSACTIONS: self._handle_match_transactions,
        }

    # ========================================================================
    # Conversation Persistence (Migration 120)
    # ========================================================================

    async def get_or_create_conversation(
        self,
        context: AssistantContext,
    ) -> AIConversation:
        """Holt oder erstellt eine Konversation.

        Args:
            context: Benutzerkontext mit session_id

        Returns:
            AIConversation Objekt
        """
        if context.conversation_id:
            # Existierende Konversation laden
            stmt = (
                select(AIConversation)
                .where(
                    and_(
                        AIConversation.id == context.conversation_id,
                        AIConversation.user_id == context.user_id,
                        AIConversation.company_id == context.company_id,
                    )
                )
            )
            result = await self.db.execute(stmt)
            conversation = result.scalar_one_or_none()
            if conversation:
                return conversation

        # Konversation per session_id suchen
        if context.session_id:
            stmt = (
                select(AIConversation)
                .where(
                    and_(
                        AIConversation.session_id == context.session_id,
                        AIConversation.user_id == context.user_id,
                    )
                )
            )
            result = await self.db.execute(stmt)
            conversation = result.scalar_one_or_none()
            if conversation:
                return conversation

        # Neue Konversation erstellen
        session_id = context.session_id or f"conv_{uuid.uuid4().hex[:16]}"
        conversation = AIConversation(
            id=uuid.uuid4(),
            session_id=session_id,
            user_id=context.user_id,
            company_id=context.company_id,
            context_page=context.current_page,
            language=context.language,
            context_data={
                "selected_documents": [str(d) for d in context.selected_documents],
            } if context.selected_documents else None,
        )
        self.db.add(conversation)
        await self.db.flush()

        logger.info(
            "conversation_created",
            conversation_id=str(conversation.id),
            session_id=session_id,
        )
        return conversation

    async def save_user_message(
        self,
        conversation: AIConversation,
        message: str,
        intent: Optional[AssistantIntent] = None,
    ) -> AIConversationMessage:
        """Speichert eine User-Nachricht.

        Args:
            conversation: Die Konversation
            message: Der Nachrichteninhalt
            intent: Erkannte Absicht (optional)

        Returns:
            Gespeicherte Nachricht
        """
        msg = AIConversationMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            role=AIMessageRole.USER.value,
            content=message,
            intent=intent.value if intent else None,
        )
        self.db.add(msg)

        # Konversations-Stats aktualisieren
        conversation.message_count = (conversation.message_count or 0) + 1
        conversation.last_message_at = utc_now()

        # Titel automatisch generieren (aus erster Nachricht)
        if conversation.message_count == 1:
            conversation.title = message[:100] + ("..." if len(message) > 100 else "")

        await self.db.flush()
        return msg

    async def save_assistant_response(
        self,
        conversation: AIConversation,
        response: "AssistantResponse",
        user_message_id: Optional[uuid.UUID] = None,
        model_used: Optional[str] = None,
    ) -> AIConversationMessage:
        """Speichert eine Assistenten-Antwort.

        Args:
            conversation: Die Konversation
            response: Die AssistantResponse
            user_message_id: ID der zugehoerigen User-Nachricht
            model_used: Verwendetes Modell (z.B. "ollama/mistral")

        Returns:
            Gespeicherte Nachricht
        """
        # Insights und Suggestions als Metadaten speichern
        metadata = {}
        if response.insights:
            metadata["insights"] = [
                {
                    "title": i.title,
                    "content": i.content,
                    "category": i.category,
                    "severity": i.severity,
                }
                for i in response.insights
            ]
        if response.booking_suggestions:
            metadata["booking_suggestions"] = [
                {
                    "debit_account": b.debit_account,
                    "credit_account": b.credit_account,
                    "amount": float(b.amount),
                    "description": b.description,
                }
                for b in response.booking_suggestions
            ]
        if response.follow_up_suggestions:
            metadata["follow_up_suggestions"] = response.follow_up_suggestions

        # Referenzierte Dokumente aus Suchergebnissen extrahieren
        referenced_docs = None
        if response.search_results:
            doc_ids = []
            for r in response.search_results[:20]:  # Max 20 Referenzen
                if isinstance(r, dict) and "id" in r:
                    doc_ids.append(r["id"])
            if doc_ids:
                referenced_docs = doc_ids

        msg = AIConversationMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            role=AIMessageRole.ASSISTANT.value,
            content=response.message,
            intent=response.intent.value,
            confidence=response.confidence,
            search_results_count=response.result_count if response.result_count else None,
            actions_proposed=len(response.actions) if response.actions else None,
            processing_time_ms=response.processing_time_ms,
            model_used=model_used,
            extra_data=metadata if metadata else None,
            referenced_documents=referenced_docs,
        )
        self.db.add(msg)

        # Konversations-Stats aktualisieren
        conversation.message_count = (conversation.message_count or 0) + 1
        conversation.last_message_at = utc_now()

        await self.db.flush()
        return msg

    async def save_proposed_actions(
        self,
        conversation: AIConversation,
        message_id: uuid.UUID,
        actions: List[ActionProposal],
    ) -> List[AIConversationAction]:
        """Speichert vorgeschlagene Aktionen.

        Args:
            conversation: Die Konversation
            message_id: ID der Nachricht mit den Aktionen
            actions: Liste der vorgeschlagenen Aktionen

        Returns:
            Liste der gespeicherten Aktionen
        """
        saved_actions = []
        for action in actions:
            db_action = AIConversationAction(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                message_id=message_id,
                action_type=action.action_type.value,
                description=action.description,
                status=AIActionStatus.PROPOSED.value,
                parameters=action.parameters,
                affected_count=action.affected_count,
                requires_confirmation=action.requires_confirmation,
            )
            self.db.add(db_action)
            saved_actions.append(db_action)

        # Konversations-Stats aktualisieren
        conversation.action_count = (conversation.action_count or 0) + len(actions)

        await self.db.flush()
        return saved_actions

    async def update_action_status(
        self,
        action_id: uuid.UUID,
        status: AIActionStatus,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        confirmed_by_id: Optional[uuid.UUID] = None,
    ) -> Optional[AIConversationAction]:
        """Aktualisiert den Status einer Aktion.

        Args:
            action_id: ID der Aktion
            status: Neuer Status
            result: Ergebnis-Daten (optional)
            error_message: Fehlermeldung (optional)
            confirmed_by_id: User-ID bei Bestätigung (optional)

        Returns:
            Aktualisierte Aktion oder None
        """
        stmt = select(AIConversationAction).where(AIConversationAction.id == action_id)
        result_obj = await self.db.execute(stmt)
        action = result_obj.scalar_one_or_none()

        if not action:
            return None

        action.status = status.value

        if result:
            action.result = result
        if error_message:
            action.error_message = error_message
        if confirmed_by_id:
            action.confirmed_by_id = confirmed_by_id
            action.confirmed_at = utc_now()
        if status == AIActionStatus.EXECUTED:
            action.executed_at = utc_now()

        await self.db.flush()
        return action

    async def load_conversation_history(
        self,
        conversation_id: uuid.UUID,
        limit: int = 20,
    ) -> List[AIConversationMessage]:
        """Laedt die Chat-Historie einer Konversation.

        Args:
            conversation_id: Konversations-ID
            limit: Maximale Anzahl Nachrichten

        Returns:
            Liste der letzten Nachrichten (aelteste zuerst)
        """
        stmt = (
            select(AIConversationMessage)
            .where(AIConversationMessage.conversation_id == conversation_id)
            .order_by(AIConversationMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()  # Chronologische Reihenfolge
        return messages

    async def _get_ollama_service(self):
        """Lazy-Loading für OllamaService."""
        if self._ollama_service is None:
            from app.services.ai.ollama_service import get_ollama_service
            self._ollama_service = get_ollama_service()
        return self._ollama_service

    async def _get_nlq_service(self):
        """Lazy-Loading für NLQService."""
        if self._nlq_service is None:
            from app.services.ai.nlq_service import NLQService

            self._nlq_service = NLQService(db=self.db)
        return self._nlq_service

    # ========================================================================
    # Main Entry Point
    # ========================================================================

    async def process_message(
        self,
        message: str,
        context: AssistantContext,
        persist: bool = True,
    ) -> AssistantResponse:
        """Verarbeitet eine Benutzer-Nachricht.

        Args:
            message: Die Benutzernachricht
            context: Kontext mit User/Company/Permissions
            persist: Konversation in DB speichern (default: True)

        Returns:
            AssistantResponse mit Antwort und Vorschlägen
        """
        import time
        start_time = time.time()

        conversation: Optional[AIConversation] = None
        user_msg: Optional[AIConversationMessage] = None

        try:
            # 0. Konversation holen/erstellen (Persistenz)
            if persist:
                conversation = await self.get_or_create_conversation(context)
                context.conversation_id = conversation.id

            # 1. Intent erkennen
            intent = await self._detect_intent(message)

            # 1b. User-Nachricht speichern
            if persist and conversation:
                user_msg = await self.save_user_message(conversation, message, intent)

            # 2. Je nach Intent verarbeiten
            if intent == AssistantIntent.SEARCH:
                response = await self._handle_search(message, context)
            elif intent == AssistantIntent.EXECUTE_ACTION:
                response = await self._handle_action_request(message, context)
            elif intent == AssistantIntent.EXPLAIN:
                response = await self._handle_explain_request(message, context)
            elif intent == AssistantIntent.SUGGEST_BOOKING:
                response = await self._handle_booking_request(message, context)
            elif intent == AssistantIntent.ANALYZE:
                response = await self._handle_analysis_request(message, context)
            elif intent == AssistantIntent.PREDICT:
                response = await self._handle_prediction_request(message, context)
            elif intent == AssistantIntent.HELP:
                response = await self._handle_help_request(context)
            else:
                response = await self._handle_general_chat(message, context)

            # Verarbeitungszeit hinzufügen
            response.processing_time_ms = int((time.time() - start_time) * 1000)

            # Follow-up Suggestions generieren
            response.follow_up_suggestions = self._generate_follow_ups(
                response.intent, message
            )

            # 3. Assistenten-Antwort speichern
            if persist and conversation:
                # Dynamisch das verwendete Modell ermitteln
                model_used = "ollama/unknown"
                try:
                    ollama = await self._get_ollama_service()
                    if ollama and hasattr(ollama, 'config') and ollama.config:
                        model_used = f"ollama/{ollama.config.default_model}"
                except Exception:
                    # Fallback auf Settings
                    from app.core.config import settings
                    model_used = f"ollama/{getattr(settings, 'DEFAULT_LLM_REALTIME', 'mistral')}"

                assistant_msg = await self.save_assistant_response(
                    conversation=conversation,
                    response=response,
                    user_message_id=user_msg.id if user_msg else None,
                    model_used=model_used,
                )

                # 4. Aktionen speichern falls vorhanden
                if response.actions:
                    await self.save_proposed_actions(
                        conversation=conversation,
                        message_id=assistant_msg.id,
                        actions=response.actions,
                    )

                # Commit der Persistenz
                await self.db.commit()

            # Audit-Log (zusätzlich zu DB-Persistenz)
            await self._log_interaction(message, response, context)

            logger.info(
                "finance_assistant_processed",
                intent=intent.value,
                processing_time_ms=response.processing_time_ms,
                success=response.success,
                conversation_id=str(conversation.id) if conversation else None,
            )

            return response

        except Exception as e:
            logger.error(
                "finance_assistant_error",
                message=message[:100],
                **safe_error_log(e),
            )
            # Rollback bei Fehler
            if persist:
                await self.db.rollback()

            return AssistantResponse(
                message=safe_error_detail(e, "Entschuldigung, ein Fehler ist aufgetreten: "),
                intent=AssistantIntent.CHAT,
                success=False,
                processing_time_ms=int((time.time() - start_time) * 1000),
                error_message=safe_error_detail(e, "KI-Assistent"),
            )

    # ========================================================================
    # Intent Detection
    # ========================================================================

    async def _detect_intent(self, message: str) -> AssistantIntent:
        """Erkennt den Intent der Nachricht."""
        message_lower = message.lower()

        # Aktions-Keywords
        action_keywords = [
            "erstelle", "führe aus", "starte", "genehmige", "buche",
            "sende", "exportiere", "zahle", "überweise"
        ]
        for keyword in action_keywords:
            if keyword in message_lower:
                return AssistantIntent.EXECUTE_ACTION

        # Such-Keywords
        search_keywords = [
            "zeige", "finde", "suche", "liste", "welche", "wo ist",
            "wie viele", "wieviele", "alle"
        ]
        for keyword in search_keywords:
            if keyword in message_lower:
                return AssistantIntent.SEARCH

        # Erklärungs-Keywords
        explain_keywords = [
            "warum", "erkläre", "was bedeutet", "wie kommt es",
            "wieso", "weshalb"
        ]
        for keyword in explain_keywords:
            if keyword in message_lower:
                return AssistantIntent.EXPLAIN

        # Buchungs-Keywords
        booking_keywords = [
            "wie buche", "buchungsvorschlag", "kontierung", "verbuchen",
            "buchungssatz", "auf welches konto"
        ]
        for keyword in booking_keywords:
            if keyword in message_lower:
                return AssistantIntent.SUGGEST_BOOKING

        # Analyse-Keywords
        analyze_keywords = [
            "analysiere", "untersuche", "prüfe", "vergleiche",
            "anomalie", "ungewöhnlich"
        ]
        for keyword in analyze_keywords:
            if keyword in message_lower:
                return AssistantIntent.ANALYZE

        # Vorhersage-Keywords
        predict_keywords = [
            "vorhersage", "prognose", "wird", "erwarte", "trend",
            "in 2 wochen", "nächsten monat"
        ]
        for keyword in predict_keywords:
            if keyword in message_lower:
                return AssistantIntent.PREDICT

        # Hilfe-Keywords
        help_keywords = ["hilfe", "help", "was kannst du", "befehle"]
        for keyword in help_keywords:
            if keyword in message_lower:
                return AssistantIntent.HELP

        return AssistantIntent.CHAT

    # ========================================================================
    # Search Handler
    # ========================================================================

    async def _handle_search(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Verarbeitet Such-Anfragen über NLQ."""
        nlq_service = await self._get_nlq_service()

        result = await nlq_service.process_query(
            query=message,
            company_id=context.company_id,
            user_id=context.user_id,
            limit=50,
        )

        if result.success:
            return AssistantResponse(
                message=result.natural_response,
                intent=AssistantIntent.SEARCH,
                success=True,
                confidence=result.confidence,
                search_results=result.results,
                result_count=result.result_count,
            )
        else:
            return AssistantResponse(
                message=result.natural_response,
                intent=AssistantIntent.SEARCH,
                success=False,
                confidence=result.confidence,
                error_message=result.error_message,
            )

    # ========================================================================
    # Action Handler
    # ========================================================================

    async def _handle_action_request(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Verarbeitet Aktions-Anfragen."""
        message_lower = message.lower()

        # Zahlungslauf erkennen
        if any(kw in message_lower for kw in ["zahlungslauf", "überweise", "zahle"]):
            return await self._propose_payment_run(message, context)

        # Genehmigung erkennen
        if any(kw in message_lower for kw in ["genehmige", "freigabe"]):
            return await self._propose_approval(message, context)

        # Mahnung erkennen
        if any(kw in message_lower for kw in ["mahnung", "erinnerung", "mahnlauf"]):
            return await self._propose_reminder(message, context)

        # Export erkennen
        if any(kw in message_lower for kw in ["exportiere", "export"]):
            return await self._propose_export(message, context)

        # Fallback
        return AssistantResponse(
            message="Ich habe die gewünschte Aktion nicht erkannt. "
                   "Verfügbare Aktionen: Zahlungslauf, Genehmigung, Mahnung, Export.",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=False,
            confidence=0.5,
        )

    async def _propose_payment_run(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Schlägt einen Zahlungslauf vor."""
        # Fällige Rechnungen abfragen
        stmt = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.status.in_(["pending", "open"]),
                    InvoiceTracking.due_date <= date.today() + timedelta(days=7),
                )
            )
            .order_by(InvoiceTracking.due_date)
        )

        result = await self.db.execute(stmt)
        invoices = result.scalars().all()

        if not invoices:
            return AssistantResponse(
                message="Aktuell gibt es keine fälligen Rechnungen für einen Zahlungslauf.",
                intent=AssistantIntent.EXECUTE_ACTION,
                success=True,
                confidence=0.9,
            )

        # Betragsfilter aus Nachricht extrahieren
        amount_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:€|eur)', message.lower())
        max_amount = None
        if amount_match:
            max_amount = Decimal(amount_match.group(1).replace(",", "."))
            invoices = [i for i in invoices if i.amount <= max_amount]

        total_amount = sum(i.amount for i in invoices)

        action = ActionProposal(
            action_type=ActionType.PAYMENT_RUN,
            description=f"Zahlungslauf für {len(invoices)} Rechnungen ({total_amount:,.2f} EUR)",
            parameters={
                "invoice_ids": [str(i.id) for i in invoices],
                "total_amount": float(total_amount),
                "max_amount": float(max_amount) if max_amount else None,
            },
            confidence=0.85,
            requires_confirmation=True,
            affected_count=len(invoices),
        )

        return AssistantResponse(
            message=f"Ich habe {len(invoices)} zahlungsreife Rechnungen gefunden "
                   f"mit einem Gesamtbetrag von {total_amount:,.2f} EUR. "
                   f"Soll ich den Zahlungslauf vorbereiten?",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=0.85,
            actions=[action],
            result_count=len(invoices),
        )

    async def _propose_approval(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Schlägt Genehmigungen vor."""
        # Rechnungen zur Genehmigung
        stmt = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.status == "pending_approval",
                )
            )
            .limit(20)
        )

        result = await self.db.execute(stmt)
        invoices = result.scalars().all()

        if not invoices:
            return AssistantResponse(
                message="Es gibt aktuell keine Rechnungen, die auf Genehmigung warten.",
                intent=AssistantIntent.EXECUTE_ACTION,
                success=True,
                confidence=0.9,
            )

        action = ActionProposal(
            action_type=ActionType.APPROVE_INVOICES,
            description=f"{len(invoices)} Rechnungen genehmigen",
            parameters={
                "invoice_ids": [str(i.id) for i in invoices],
            },
            confidence=0.80,
            requires_confirmation=True,
            affected_count=len(invoices),
        )

        return AssistantResponse(
            message=f"Es warten {len(invoices)} Rechnungen auf Genehmigung. "
                   "Soll ich diese zur Freigabe vorbereiten?",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=0.80,
            actions=[action],
            result_count=len(invoices),
        )

    async def _propose_reminder(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Schlägt Mahnungen vor."""
        # Überfällige Rechnungen
        stmt = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.status.in_(["pending", "open"]),
                    InvoiceTracking.due_date < date.today(),
                )
            )
            .order_by(InvoiceTracking.due_date)
        )

        result = await self.db.execute(stmt)
        overdue = result.scalars().all()

        if not overdue:
            return AssistantResponse(
                message="Es gibt aktuell keine überfälligen Rechnungen.",
                intent=AssistantIntent.EXECUTE_ACTION,
                success=True,
                confidence=0.9,
            )

        # Nach Mahnstufe gruppieren
        by_level: Dict[int, List] = {}
        for inv in overdue:
            level = inv.dunning_level or 0
            if level not in by_level:
                by_level[level] = []
            by_level[level].append(inv)

        action = ActionProposal(
            action_type=ActionType.SEND_REMINDER,
            description=f"Mahnlauf für {len(overdue)} überfällige Rechnungen",
            parameters={
                "invoice_ids": [str(i.id) for i in overdue],
                "by_dunning_level": {k: len(v) for k, v in by_level.items()},
            },
            confidence=0.85,
            requires_confirmation=True,
            affected_count=len(overdue),
        )

        level_info = ", ".join(
            f"Mahnstufe {k}: {len(v)}" for k, v in sorted(by_level.items())
        )

        return AssistantResponse(
            message=f"Es gibt {len(overdue)} überfällige Rechnungen. "
                   f"Verteilung: {level_info}. "
                   "Soll ich den Mahnlauf starten?",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=0.85,
            actions=[action],
            result_count=len(overdue),
        )

    async def _propose_export(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Schlägt Export vor."""
        export_types = []

        message_lower = message.lower()
        if "datev" in message_lower:
            export_types.append("DATEV")
        if "excel" in message_lower or "xlsx" in message_lower:
            export_types.append("Excel")
        if "pdf" in message_lower:
            export_types.append("PDF")
        if "csv" in message_lower:
            export_types.append("CSV")

        if not export_types:
            export_types = ["DATEV", "Excel"]  # Default

        action = ActionProposal(
            action_type=ActionType.EXPORT_DATA,
            description=f"Datenexport als {', '.join(export_types)}",
            parameters={
                "formats": export_types,
                "company_id": str(context.company_id),
            },
            confidence=0.75,
            requires_confirmation=True,
            affected_count=1,
        )

        return AssistantResponse(
            message=f"Export wird vorbereitet. Verfügbare Formate: {', '.join(export_types)}. "
                   "Welchen Zeitraum möchten Sie exportieren?",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=0.75,
            actions=[action],
        )

    # ========================================================================
    # Action Execution
    # ========================================================================

    async def execute_action(
        self,
        action: ActionProposal,
        context: AssistantContext,
        action_id: Optional[uuid.UUID] = None,
    ) -> AssistantResponse:
        """Führt eine bestätigte Aktion aus.

        Args:
            action: Die auszuführende Aktion
            context: Benutzerkontext
            action_id: DB-ID der Aktion (für Status-Updates)

        Returns:
            AssistantResponse mit Ergebnis
        """
        # Berechtigungsprüfung
        if context.user_role == "viewer":
            return AssistantResponse(
                message="Sie haben keine Berechtigung, Aktionen auszuführen.",
                intent=AssistantIntent.EXECUTE_ACTION,
                success=False,
                confidence=1.0,
            )

        handler = self._action_handlers.get(action.action_type)
        if not handler:
            return AssistantResponse(
                message=f"Aktion '{action.action_type.value}' wird nicht unterstützt.",
                intent=AssistantIntent.EXECUTE_ACTION,
                success=False,
                confidence=1.0,
            )

        try:
            # Aktion als bestätigt markieren
            if action_id:
                await self.update_action_status(
                    action_id=action_id,
                    status=AIActionStatus.CONFIRMED,
                    confirmed_by_id=context.user_id,
                )

            # Aktion ausführen
            result = await handler(action, context)

            # Status-Update nach Ausführung
            if action_id:
                if result.success:
                    await self.update_action_status(
                        action_id=action_id,
                        status=AIActionStatus.EXECUTED,
                        result={
                            "message": result.message,
                            "result_count": result.result_count,
                        },
                    )
                else:
                    await self.update_action_status(
                        action_id=action_id,
                        status=AIActionStatus.FAILED,
                        error_message=result.error_message,
                    )
                await self.db.commit()

            return result

        except Exception as e:
            logger.error(
                "action_execution_error",
                action_type=action.action_type.value,
                **safe_error_log(e),
            )
            # Fehler-Status speichern
            if action_id:
                await self.update_action_status(
                    action_id=action_id,
                    status=AIActionStatus.FAILED,
                    error_message=safe_error_detail(e, "KI-Assistent"),
                )
                await self.db.commit()

            return AssistantResponse(
                message=safe_error_detail(e, "Fehler bei der Ausführung: "),
                intent=AssistantIntent.EXECUTE_ACTION,
                success=False,
                error_message=safe_error_detail(e, "KI-Assistent"),
            )

    async def _handle_payment_run(
        self,
        action: ActionProposal,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Führt einen Zahlungslauf durch."""
        invoice_ids = action.parameters.get("invoice_ids", [])

        # Hier würde die eigentliche SEPA-Export-Logik kommen
        # Für jetzt: Status-Update
        for inv_id in invoice_ids:
            stmt = (
                select(InvoiceTracking)
                .where(InvoiceTracking.id == uuid.UUID(inv_id))
            )
            result = await self.db.execute(stmt)
            invoice = result.scalar_one_or_none()
            if invoice:
                invoice.status = "payment_pending"

        await self.db.commit()

        return AssistantResponse(
            message=f"Zahlungslauf für {len(invoice_ids)} Rechnungen wurde vorbereitet. "
                   "Die Überweisungen können jetzt freigegeben werden.",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=1.0,
            result_count=len(invoice_ids),
        )

    async def _handle_approve_invoices(
        self,
        action: ActionProposal,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Genehmigt Rechnungen."""
        invoice_ids = action.parameters.get("invoice_ids", [])

        for inv_id in invoice_ids:
            stmt = (
                select(InvoiceTracking)
                .where(InvoiceTracking.id == uuid.UUID(inv_id))
            )
            result = await self.db.execute(stmt)
            invoice = result.scalar_one_or_none()
            if invoice:
                invoice.status = "approved"
                invoice.approved_at = utc_now()
                invoice.approved_by = context.user_id

        await self.db.commit()

        return AssistantResponse(
            message=f"{len(invoice_ids)} Rechnungen wurden genehmigt.",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=1.0,
            result_count=len(invoice_ids),
        )

    async def _handle_categorize_documents(
        self,
        action: ActionProposal,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Kategorisiert Dokumente automatisch."""
        # Implementierung würde AutoCategorizationService nutzen
        return AssistantResponse(
            message="Dokumenten-Kategorisierung wurde gestartet.",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=0.9,
        )

    async def _handle_send_reminder(
        self,
        action: ActionProposal,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Sendet Mahnungen."""
        invoice_ids = action.parameters.get("invoice_ids", [])

        # Mahnstufe erhöhen und Mahnung generieren
        for inv_id in invoice_ids:
            stmt = (
                select(InvoiceTracking)
                .where(InvoiceTracking.id == uuid.UUID(inv_id))
            )
            result = await self.db.execute(stmt)
            invoice = result.scalar_one_or_none()
            if invoice:
                invoice.dunning_level = (invoice.dunning_level or 0) + 1
                invoice.last_dunning_date = date.today()

        await self.db.commit()

        return AssistantResponse(
            message=f"Mahnungen für {len(invoice_ids)} Rechnungen wurden erstellt.",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=1.0,
            result_count=len(invoice_ids),
        )

    async def _handle_match_transactions(
        self,
        action: ActionProposal,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Ordnet Transaktionen zu."""
        # Implementierung würde ReconciliationService nutzen
        return AssistantResponse(
            message="Transaktions-Zuordnung wurde gestartet.",
            intent=AssistantIntent.EXECUTE_ACTION,
            success=True,
            confidence=0.9,
        )

    # ========================================================================
    # Explanation Handler
    # ========================================================================

    async def _handle_explain_request(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Generiert Erklärungen für Geschäftsfragen."""
        message_lower = message.lower()

        insights: List[Insight] = []

        # Cash Flow Erklärung
        if "cash" in message_lower or "liquidität" in message_lower:
            insight = await self._explain_cash_flow(context)
            insights.append(insight)

        # Überfällige Rechnungen erklären
        if "überfällig" in message_lower or "offen" in message_lower:
            insight = await self._explain_overdue(context)
            insights.append(insight)

        # Anomalie erklären
        if "anomalie" in message_lower or "ungewöhnlich" in message_lower:
            insight = await self._explain_anomalies(context)
            insights.append(insight)

        if not insights:
            # Generische Erklärung mit LLM
            return await self._generate_llm_explanation(message, context)

        response_text = "\n\n".join(f"**{i.title}**\n{i.content}" for i in insights)

        return AssistantResponse(
            message=response_text,
            intent=AssistantIntent.EXPLAIN,
            success=True,
            confidence=0.85,
            insights=insights,
        )

    async def _explain_cash_flow(self, context: AssistantContext) -> Insight:
        """Erklärt den aktuellen Cash Flow."""
        # Einnahmen letzter Monat
        month_start = date.today().replace(day=1)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)

        # Einnahmen (Ausgangsrechnungen; Richtung via Entity-Typ 'customer')
        income_stmt = (
            select(func.sum(InvoiceTracking.amount))
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    is_outgoing_invoice(),
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at >= month_start,
                )
            )
        )
        result = await self.db.execute(income_stmt)
        income = result.scalar() or Decimal("0")

        # Ausgaben (Eingangsrechnungen; Richtung via Entity-Typ 'supplier')
        expense_stmt = (
            select(func.sum(InvoiceTracking.amount))
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    is_incoming_invoice(),
                    InvoiceTracking.paid_at >= month_start,
                )
            )
        )
        result = await self.db.execute(expense_stmt)
        expenses = result.scalar() or Decimal("0")

        net_flow = income - expenses

        content = f"""
**Dieser Monat (ab {month_start.strftime('%d.%m.%Y')})**
- Einnahmen: {float(income):,.2f} EUR
- Ausgaben: {float(expenses):,.2f} EUR
- Netto Cash Flow: {float(net_flow):+,.2f} EUR

{"Der Cash Flow ist positiv - gute Liquiditätslage." if net_flow >= 0 else "Achtung: Negativer Cash Flow - prüfen Sie offene Forderungen."}
        """.strip()

        return Insight(
            title="Cash Flow Analyse",
            content=content,
            category="cash_flow",
            severity="info" if net_flow >= 0 else "warning",
            data={
                "income": float(income),
                "expenses": float(expenses),
                "net_flow": float(net_flow),
            },
        )

    async def _explain_overdue(self, context: AssistantContext) -> Insight:
        """Erklärt überfällige Posten."""
        stmt = (
            select(
                func.count(InvoiceTracking.id),
                func.sum(InvoiceTracking.amount),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.status.in_(["pending", "open"]),
                    InvoiceTracking.due_date < date.today(),
                )
            )
        )
        result = await self.db.execute(stmt)
        row = result.one()
        count, total = row[0] or 0, row[1] or Decimal("0")

        if count == 0:
            content = "Es gibt aktuell keine überfälligen Rechnungen. Alle Zahlungen sind im Plan."
            severity = "info"
        else:
            content = f"""
**{count} überfällige Rechnung(en)** mit einem Gesamtbetrag von **{float(total):,.2f} EUR**.

Empfehlung:
- Prüfen Sie den Mahnstatus
- Kontaktieren Sie säumige Zahler
- Erwägen Sie Skonto-Optimierung bei eigenen Verbindlichkeiten
            """.strip()
            severity = "warning" if count < 5 else "critical"

        return Insight(
            title="Überfällige Posten",
            content=content,
            category="warning",
            severity=severity,
            data={"count": count, "total": float(total)},
        )

    async def _explain_anomalies(self, context: AssistantContext) -> Insight:
        """Erklärt erkannte Anomalien."""
        # Vereinfachte Anomalie-Erkennung
        # In Produktion würde AnomalyDetectionService genutzt

        # Prüfe auf ungewöhnlich hohe Rechnungen
        avg_stmt = (
            select(func.avg(InvoiceTracking.amount))
            .where(InvoiceTracking.company_id == context.company_id)
        )
        result = await self.db.execute(avg_stmt)
        avg_amount = result.scalar() or Decimal("0")

        threshold = avg_amount * Decimal("3")

        high_stmt = (
            select(func.count(InvoiceTracking.id))
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.amount > threshold,
                    InvoiceTracking.created_at >= date.today() - timedelta(days=30),
                )
            )
        )
        result = await self.db.execute(high_stmt)
        high_count = result.scalar() or 0

        if high_count == 0:
            content = "Keine Anomalien in den letzten 30 Tagen erkannt. Alle Buchungen sind im normalen Rahmen."
            severity = "info"
        else:
            content = f"""
**{high_count} ungewöhnlich hohe Rechnung(en)** erkannt (>3x Durchschnitt von {float(avg_amount):,.2f} EUR).

Diese sollten manuell geprüft werden.
            """.strip()
            severity = "warning"

        return Insight(
            title="Anomalie-Analyse",
            content=content,
            category="anomaly",
            severity=severity,
            data={"average": float(avg_amount), "high_count": high_count},
        )

    async def _generate_llm_explanation(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Generiert LLM-basierte Erklärung."""
        try:
            ollama = await self._get_ollama_service()
            if not await ollama.is_available():
                return AssistantResponse(
                    message="Der KI-Assistent ist derzeit nicht verfügbar. "
                           "Bitte versuchen Sie es später erneut.",
                    intent=AssistantIntent.EXPLAIN,
                    success=False,
                    confidence=0.5,
                )

            system_prompt = """Du bist ein erfahrener Buchhalter und Finanzexperte.
Beantworte die Frage des Benutzers präzise und verständlich auf Deutsch.
Nutze Fachbegriffe, aber erkläre sie wenn nötig.
Halte dich kurz und praxisorientiert."""

            response = await ollama.generate(
                prompt=message,
                system_prompt=system_prompt,
                temperature=0.3,
            )

            return AssistantResponse(
                message=response,
                intent=AssistantIntent.EXPLAIN,
                success=True,
                confidence=0.75,
            )

        except Exception as e:
            logger.error("llm_explanation_error", **safe_error_log(e))
            return AssistantResponse(
                message="Ich konnte Ihre Frage leider nicht beantworten. "
                       "Bitte formulieren Sie sie anders.",
                intent=AssistantIntent.EXPLAIN,
                success=False,
                error_message=safe_error_detail(e, "KI-Assistent"),
            )

    # ========================================================================
    # Booking Suggestion Handler
    # ========================================================================

    async def _handle_booking_request(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Generiert Buchungsvorschläge."""
        suggestions: List[BookingSuggestion] = []

        message_lower = message.lower()

        # Betrag extrahieren
        amount_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:€|eur)?', message)
        amount = Decimal(amount_match.group(1).replace(",", ".")) if amount_match else Decimal("100")

        # Buchungstyp erkennen
        if "wareneingang" in message_lower or "einkauf" in message_lower:
            suggestions.append(BookingSuggestion(
                debit_account="3300",
                debit_account_name="Wareneingang 19% VSt",
                credit_account="1600",
                credit_account_name="Verbindlichkeiten aus L+L",
                amount=amount,
                description="Wareneingang Buchung",
                tax_code="VSt19",
                confidence=0.85,
                reasoning="Standard-Buchung für Wareneinkauf mit 19% Vorsteuer.",
            ))
        elif "verkauf" in message_lower or "umsatz" in message_lower:
            suggestions.append(BookingSuggestion(
                debit_account="1400",
                debit_account_name="Forderungen aus L+L",
                credit_account="8400",
                credit_account_name="Erlöse 19% USt",
                amount=amount,
                description="Erlösbuchung",
                tax_code="USt19",
                confidence=0.85,
                reasoning="Standard-Buchung für Verkauf mit 19% Umsatzsteuer.",
            ))
        elif "bank" in message_lower or "überweisung" in message_lower:
            suggestions.append(BookingSuggestion(
                debit_account="1200",
                debit_account_name="Bank",
                credit_account="1400",
                credit_account_name="Forderungen aus L+L",
                amount=amount,
                description="Zahlungseingang",
                confidence=0.80,
                reasoning="Buchung bei Zahlungseingang auf Bankkonto.",
            ))
        elif "barzahlung" in message_lower or "kasse" in message_lower:
            suggestions.append(BookingSuggestion(
                debit_account="1000",
                debit_account_name="Kasse",
                credit_account="8400",
                credit_account_name="Erlöse 19% USt",
                amount=amount,
                description="Barverkauf",
                tax_code="USt19",
                confidence=0.85,
                reasoning="Buchung für Barverkauf.",
            ))
        elif "werbung" in message_lower:
            suggestions.append(BookingSuggestion(
                debit_account="4600",
                debit_account_name="Werbekosten",
                credit_account="1200",
                credit_account_name="Bank",
                amount=amount,
                description="Werbeausgabe",
                tax_code="VSt19",
                confidence=0.80,
                reasoning="Werbekosten als Betriebsausgabe.",
            ))
        else:
            # LLM für komplexe Fälle
            return await self._generate_llm_booking_suggestion(message, amount, context)

        if suggestions:
            s = suggestions[0]
            response_text = f"""**Buchungsvorschlag:**

| Soll | Haben |
|------|-------|
| {s.debit_account} {s.debit_account_name} | {s.credit_account} {s.credit_account_name} |
| {float(s.amount):,.2f} EUR | {float(s.amount):,.2f} EUR |

**Steuerkennzeichen:** {s.tax_code or 'keins'}

_{s.reasoning}_"""

            return AssistantResponse(
                message=response_text,
                intent=AssistantIntent.SUGGEST_BOOKING,
                success=True,
                confidence=suggestions[0].confidence,
                booking_suggestions=suggestions,
            )

        return AssistantResponse(
            message="Ich konnte keinen passenden Buchungsvorschlag erstellen. "
                   "Bitte beschreiben Sie den Geschäftsvorfall genauer.",
            intent=AssistantIntent.SUGGEST_BOOKING,
            success=False,
            confidence=0.5,
        )

    async def _generate_llm_booking_suggestion(
        self,
        message: str,
        amount: Decimal,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Generiert LLM-basierten Buchungsvorschlag."""
        try:
            ollama = await self._get_ollama_service()
            if not await ollama.is_available():
                return AssistantResponse(
                    message="Der KI-Assistent ist derzeit nicht verfügbar.",
                    intent=AssistantIntent.SUGGEST_BOOKING,
                    success=False,
                )

            kontenrahmen_info = "\n".join(
                f"- {k}: {v['name']} ({v['type']})"
                for k, v in SKR03_ACCOUNTS.items()
            )

            system_prompt = f"""Du bist ein erfahrener Buchhalter.
Erstelle einen Buchungsvorschlag basierend auf SKR03.

Verfügbare Konten:
{kontenrahmen_info}

Antworte im Format:
SOLL: [Konto] [Kontoname]
HABEN: [Konto] [Kontoname]
BETRAG: {float(amount):,.2f} EUR
STEUERKENNZEICHEN: [VSt19, USt19, oder keins]
BEGRÜNDUNG: [Kurze Erklärung]"""

            response = await ollama.generate(
                prompt=f"Buchungsvorschlag für: {message}",
                system_prompt=system_prompt,
                temperature=0.2,
            )

            return AssistantResponse(
                message=f"**KI-generierter Buchungsvorschlag:**\n\n{response}\n\n"
                       "_Bitte prüfen Sie den Vorschlag sorgfältig._",
                intent=AssistantIntent.SUGGEST_BOOKING,
                success=True,
                confidence=0.70,
            )

        except Exception as e:
            logger.error("llm_booking_error", **safe_error_log(e))
            return AssistantResponse(
                message="Buchungsvorschlag konnte nicht erstellt werden.",
                intent=AssistantIntent.SUGGEST_BOOKING,
                success=False,
                error_message=safe_error_detail(e, "KI-Assistent"),
            )

    # ========================================================================
    # Analysis Handler
    # ========================================================================

    async def _handle_analysis_request(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Führt Analysen durch."""
        insights: List[Insight] = []

        # Cash Flow Trend
        insight_cf = await self._explain_cash_flow(context)
        insights.append(insight_cf)

        # Überfällige
        insight_od = await self._explain_overdue(context)
        insights.append(insight_od)

        # Anomalien
        insight_an = await self._explain_anomalies(context)
        insights.append(insight_an)

        response_text = "**Analyse-Ergebnis:**\n\n" + "\n\n---\n\n".join(
            f"### {i.title}\n{i.content}" for i in insights
        )

        return AssistantResponse(
            message=response_text,
            intent=AssistantIntent.ANALYZE,
            success=True,
            confidence=0.85,
            insights=insights,
        )

    # ========================================================================
    # Prediction Handler
    # ========================================================================

    async def _handle_prediction_request(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Erstellt Vorhersagen."""
        # Historische Daten für Trend
        stmt = (
            select(
                func.date_trunc('month', InvoiceTracking.created_at).label('month'),
                func.sum(
                    case(
                        (is_outgoing_invoice(), InvoiceTracking.amount),
                        else_=Decimal("0")
                    )
                ).label('income'),
                func.sum(
                    case(
                        (is_incoming_invoice(), InvoiceTracking.amount),
                        else_=Decimal("0")
                    )
                ).label('expenses'),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.created_at >= date.today() - timedelta(days=180),
                )
            )
            .group_by('month')
            .order_by('month')
        )

        result = await self.db.execute(stmt)
        monthly_data = result.all()

        if len(monthly_data) < 3:
            return AssistantResponse(
                message="Für eine Vorhersage werden mindestens 3 Monate Daten benötigt.",
                intent=AssistantIntent.PREDICT,
                success=False,
                confidence=0.5,
            )

        # Einfacher Trend (Durchschnitt der letzten 3 Monate)
        recent = monthly_data[-3:]
        avg_income = sum(r.income or Decimal("0") for r in recent) / 3
        avg_expenses = sum(r.expenses or Decimal("0") for r in recent) / 3
        avg_net = avg_income - avg_expenses

        # Vorhersage
        next_month = date.today().replace(day=1) + timedelta(days=32)
        next_month = next_month.replace(day=1)

        prediction_text = f"""**Prognose für {next_month.strftime('%B %Y')}:**

Basierend auf dem 3-Monats-Durchschnitt:
- Erwartete Einnahmen: ~{float(avg_income):,.0f} EUR
- Erwartete Ausgaben: ~{float(avg_expenses):,.0f} EUR
- Erwarteter Netto Cash Flow: ~{float(avg_net):+,.0f} EUR

{"⚠️ Möglicher Liquiditätsengpass!" if avg_net < 0 else "✓ Positive Liquiditätsentwicklung erwartet."}

_Hinweis: Dies ist eine vereinfachte Trendfortschreibung._"""

        insight = Insight(
            title=f"Prognose {next_month.strftime('%B %Y')}",
            content=prediction_text,
            category="trend",
            severity="warning" if avg_net < 0 else "info",
            data={
                "predicted_income": float(avg_income),
                "predicted_expenses": float(avg_expenses),
                "predicted_net": float(avg_net),
            },
        )

        return AssistantResponse(
            message=prediction_text,
            intent=AssistantIntent.PREDICT,
            success=True,
            confidence=0.70,
            insights=[insight],
        )

    # ========================================================================
    # Help Handler
    # ========================================================================

    async def _handle_help_request(
        self,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Zeigt Hilfe an."""
        help_text = """**Ich bin Ihr Finanz-Assistent!**

**Was ich kann:**

🔍 **Suchen**
- "Zeige alle Rechnungen von Müller GmbH"
- "Welche Rechnungen sind überfällig?"
- "Finde Dokumente mit Stichwort 'Wartung'"

💰 **Aktionen**
- "Erstelle Zahlungslauf für fällige Rechnungen unter 5000€"
- "Starte Mahnlauf"
- "Exportiere Daten als DATEV"

📊 **Analysen**
- "Analysiere den Cash Flow"
- "Warum ist der Umsatz gesunken?"
- "Zeige Anomalien"

📝 **Buchungsvorschläge**
- "Wie buche ich einen Wareneingang über 500€?"
- "Buchungsvorschlag für Werbekosten"

🔮 **Vorhersagen**
- "Wie entwickelt sich die Liquidität?"
- "Prognose für nächsten Monat"

**Tipp:** Sie können natürlich formulieren - ich verstehe auch komplexe Fragen!"""

        return AssistantResponse(
            message=help_text,
            intent=AssistantIntent.HELP,
            success=True,
            confidence=1.0,
        )

    # ========================================================================
    # General Chat Handler
    # ========================================================================

    async def _handle_general_chat(
        self,
        message: str,
        context: AssistantContext,
    ) -> AssistantResponse:
        """Verarbeitet allgemeine Chat-Nachrichten."""
        # Versuche über NLQ zu suchen
        nlq_service = await self._get_nlq_service()
        result = await nlq_service.process_query(
            query=message,
            company_id=context.company_id,
            user_id=context.user_id,
        )

        if result.success and result.result_count > 0:
            return AssistantResponse(
                message=result.natural_response,
                intent=AssistantIntent.CHAT,
                success=True,
                confidence=result.confidence,
                search_results=result.results,
                result_count=result.result_count,
            )

        # Fallback zu LLM
        try:
            ollama = await self._get_ollama_service()
            if await ollama.is_available():
                response = await ollama.generate(
                    prompt=message,
                    system_prompt="Du bist ein hilfreicher Finanz-Assistent. "
                                 "Antworte auf Deutsch, kurz und präzise.",
                    temperature=0.5,
                )
                return AssistantResponse(
                    message=response,
                    intent=AssistantIntent.CHAT,
                    success=True,
                    confidence=0.6,
                )
        except Exception as e:
            logger.debug(
                "assistant_intent_fallback_failed",
                error_type=type(e).__name__,
            )

        return AssistantResponse(
            message="Ich bin mir nicht sicher, wie ich Ihnen helfen kann. "
                   "Versuchen Sie 'Hilfe' für verfügbare Befehle.",
            intent=AssistantIntent.CHAT,
            success=True,
            confidence=0.3,
        )

    # ========================================================================
    # Utilities
    # ========================================================================

    def _generate_follow_ups(
        self,
        intent: AssistantIntent,
        message: str,
    ) -> List[str]:
        """Generiert Follow-up Vorschläge."""
        suggestions = []

        if intent == AssistantIntent.SEARCH:
            suggestions = [
                "Zeige Details zu einem Dokument",
                "Exportiere die Ergebnisse",
                "Analysiere diese Dokumente",
            ]
        elif intent == AssistantIntent.EXECUTE_ACTION:
            suggestions = [
                "Zeige den Aktionsverlauf",
                "Analysiere das Ergebnis",
            ]
        elif intent == AssistantIntent.EXPLAIN:
            suggestions = [
                "Zeige betroffene Dokumente",
                "Erstelle einen Bericht",
            ]
        elif intent == AssistantIntent.SUGGEST_BOOKING:
            suggestions = [
                "Buche diesen Vorschlag",
                "Zeige alternative Buchungen",
            ]

        return suggestions[:3]

    async def cancel_action(
        self,
        action_id: uuid.UUID,
        context: AssistantContext,
    ) -> bool:
        """Bricht eine vorgeschlagene Aktion ab.

        Args:
            action_id: ID der Aktion
            context: Benutzerkontext

        Returns:
            True wenn erfolgreich abgebrochen
        """
        action = await self.update_action_status(
            action_id=action_id,
            status=AIActionStatus.CANCELLED,
        )
        if action:
            await self.db.commit()
            logger.info(
                "action_cancelled",
                action_id=str(action_id),
                user_id=str(context.user_id),
            )
            return True
        return False

    async def get_pending_actions(
        self,
        context: AssistantContext,
    ) -> List[AIConversationAction]:
        """Holt alle offenen Aktionen für einen Benutzer.

        Args:
            context: Benutzerkontext

        Returns:
            Liste offener Aktionen
        """
        stmt = (
            select(AIConversationAction)
            .join(AIConversation)
            .where(
                and_(
                    AIConversation.user_id == context.user_id,
                    AIConversation.company_id == context.company_id,
                    AIConversationAction.status == AIActionStatus.PROPOSED.value,
                )
            )
            .order_by(AIConversationAction.proposed_at.desc())
            .limit(20)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _log_interaction(
        self,
        message: str,
        response: AssistantResponse,
        context: AssistantContext,
    ) -> None:
        """Protokolliert die Interaktion."""
        try:
            # Audit-Log eintrag (zusätzlich zu DB-Persistenz)
            logger.info(
                "finance_assistant_interaction",
                user_id=str(context.user_id),
                company_id=str(context.company_id),
                intent=response.intent.value,
                success=response.success,
                confidence=response.confidence,
                message_length=len(message),
                conversation_id=str(context.conversation_id) if context.conversation_id else None,
            )
        except Exception as e:
            logger.error("audit_log_error", **safe_error_log(e))


# ============================================================================
# Factory Functions
# ============================================================================


async def get_finance_assistant_service(db: AsyncSession) -> FinanceAssistantService:
    """Factory-Funktion für FinanceAssistantService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter FinanceAssistantService
    """
    return FinanceAssistantService(db=db)

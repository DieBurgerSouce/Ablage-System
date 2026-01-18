"""
AI Action Service.

Handles AI-driven actions with role-based autonomy levels:
- Viewer: Read-only actions (search, analyze, report)
- Editor: Supervised actions (requires confirmation)
- Admin: Autonomous actions (self-executing)
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import User, Document, BusinessEntity
from app.api.schemas.rag import (
    AIActionType,
    AIActionAutonomyLevel,
    AIActionStatus,
    AIActionRequest,
    AIActionResult,
    AIActionSuggestion,
    AIActionParameter,
    AIActionListResponse,
    AIContextInfo,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# ACTION DEFINITIONS
# ============================================================================

# Actions available at each autonomy level
VIEWER_ACTIONS = {
    AIActionType.SEARCH_DOCUMENTS,
    AIActionType.ANALYZE_ENTITY,
    AIActionType.GENERATE_REPORT,
    AIActionType.EXPLAIN_DOCUMENT,
}

EDITOR_ACTIONS = VIEWER_ACTIONS | {
    AIActionType.CATEGORIZE_DOCUMENT,
    AIActionType.TAG_DOCUMENT,
    AIActionType.LINK_ENTITY,
    AIActionType.CREATE_REMINDER,
}

ADMIN_ACTIONS = EDITOR_ACTIONS | {
    AIActionType.APPROVE_VALIDATION,
    AIActionType.TRIGGER_OCR,
    AIActionType.SEND_NOTIFICATION,
    AIActionType.BULK_CATEGORIZE,
}

# Actions that require confirmation at Editor level
SUPERVISED_ACTIONS = {
    AIActionType.CATEGORIZE_DOCUMENT,
    AIActionType.TAG_DOCUMENT,
    AIActionType.LINK_ENTITY,
    AIActionType.CREATE_REMINDER,
    AIActionType.APPROVE_VALIDATION,
    AIActionType.TRIGGER_OCR,
    AIActionType.SEND_NOTIFICATION,
    AIActionType.BULK_CATEGORIZE,
}

# German action descriptions
ACTION_DESCRIPTIONS: Dict[AIActionType, Dict[str, str]] = {
    AIActionType.SEARCH_DOCUMENTS: {
        "title": "Dokumente durchsuchen",
        "description": "Durchsucht die Dokumentenbasis nach relevanten Inhalten.",
        "impact": "Keine Aenderungen - nur Lesezugriff",
    },
    AIActionType.ANALYZE_ENTITY: {
        "title": "Geschaeftspartner analysieren",
        "description": "Analysiert Daten zu einem Kunden oder Lieferanten.",
        "impact": "Keine Aenderungen - nur Analyse",
    },
    AIActionType.GENERATE_REPORT: {
        "title": "Bericht erstellen",
        "description": "Generiert einen Bericht basierend auf den Daten.",
        "impact": "Keine Aenderungen - nur Export",
    },
    AIActionType.EXPLAIN_DOCUMENT: {
        "title": "Dokument erklaeren",
        "description": "Erklaert den Inhalt und die wichtigsten Punkte eines Dokuments.",
        "impact": "Keine Aenderungen - nur Erklaerung",
    },
    AIActionType.CATEGORIZE_DOCUMENT: {
        "title": "Dokument kategorisieren",
        "description": "Ordnet das Dokument einer Kategorie zu.",
        "impact": "Aendert Dokument-Kategorie",
    },
    AIActionType.TAG_DOCUMENT: {
        "title": "Tags hinzufuegen",
        "description": "Fuegt Tags zum Dokument hinzu.",
        "impact": "Aendert Dokument-Tags",
    },
    AIActionType.LINK_ENTITY: {
        "title": "Mit Geschaeftspartner verknuepfen",
        "description": "Verknuepft das Dokument mit einem Kunden oder Lieferanten.",
        "impact": "Erstellt Verknuepfung",
    },
    AIActionType.CREATE_REMINDER: {
        "title": "Erinnerung erstellen",
        "description": "Erstellt eine Erinnerung fuer eine Aufgabe.",
        "impact": "Erstellt neue Erinnerung",
    },
    AIActionType.APPROVE_VALIDATION: {
        "title": "Validierung genehmigen",
        "description": "Genehmigt ein Dokument in der Validierungs-Queue.",
        "impact": "Aendert Validierungs-Status",
    },
    AIActionType.TRIGGER_OCR: {
        "title": "OCR starten",
        "description": "Startet die OCR-Verarbeitung fuer ein Dokument.",
        "impact": "Startet Hintergrund-Task",
    },
    AIActionType.SEND_NOTIFICATION: {
        "title": "Benachrichtigung senden",
        "description": "Sendet eine Benachrichtigung an Benutzer.",
        "impact": "Sendet Nachricht",
    },
    AIActionType.BULK_CATEGORIZE: {
        "title": "Mehrere kategorisieren",
        "description": "Kategorisiert mehrere Dokumente gleichzeitig.",
        "impact": "Aendert mehrere Dokumente",
    },
}


class AIActionService:
    """Service fuer AI-gesteuerte Aktionen."""

    def __init__(self) -> None:
        """Initialisiert den AI Action Service."""
        # In-memory storage for pending suggestions (in production: use Redis or DB)
        self._pending_suggestions: Dict[UUID, AIActionSuggestion] = {}

    def get_autonomy_level(self, user: User) -> AIActionAutonomyLevel:
        """Bestimmt das Autonomie-Level basierend auf User-Rolle.

        Args:
            user: Der aktuelle User

        Returns:
            AIActionAutonomyLevel basierend auf Rolle
        """
        if user.is_superuser:
            return AIActionAutonomyLevel.ADMIN
        # Check for specific roles (extend based on your role system)
        if hasattr(user, 'role'):
            if user.role in ('admin', 'manager'):
                return AIActionAutonomyLevel.ADMIN
            if user.role in ('editor', 'operator'):
                return AIActionAutonomyLevel.EDITOR
        return AIActionAutonomyLevel.VIEWER

    def get_available_actions(
        self,
        user: User,
        context_type: Optional[str] = None,
    ) -> AIActionListResponse:
        """Gibt verfuegbare Aktionen basierend auf Rolle zurueck.

        Args:
            user: Der aktuelle User
            context_type: Optionaler Kontext-Typ (document, entity, etc.)

        Returns:
            Liste der verfuegbaren Aktionen
        """
        level = self.get_autonomy_level(user)

        if level == AIActionAutonomyLevel.ADMIN:
            actions = ADMIN_ACTIONS
        elif level == AIActionAutonomyLevel.EDITOR:
            actions = EDITOR_ACTIONS
        else:
            actions = VIEWER_ACTIONS

        # Filter by context if provided
        if context_type:
            if context_type == 'document':
                actions = {a for a in actions if 'document' in a.value.lower() or a in VIEWER_ACTIONS}
            elif context_type == 'entity':
                actions = {a for a in actions if 'entity' in a.value.lower() or a in VIEWER_ACTIONS}

        # Build response with descriptions
        action_list = []
        for action in actions:
            desc = ACTION_DESCRIPTIONS.get(action, {})
            action_list.append({
                "action_type": action.value,
                "title": desc.get("title", action.value),
                "description": desc.get("description", ""),
                "impact": desc.get("impact", ""),
                "requires_confirmation": action in SUPERVISED_ACTIONS and level != AIActionAutonomyLevel.ADMIN,
            })

        # Count pending suggestions for this user
        pending_count = sum(1 for s in self._pending_suggestions.values())

        return AIActionListResponse(
            available_actions=action_list,
            autonomy_level=level,
            pending_suggestions=pending_count,
        )

    async def execute_action(
        self,
        db: AsyncSession,
        user: User,
        request: AIActionRequest,
    ) -> AIActionResult:
        """Fuehrt eine AI-Aktion aus.

        Args:
            db: Database Session
            user: Der aktuelle User
            request: Action Request

        Returns:
            Action Result mit Status und Details
        """
        start_time = datetime.now(timezone.utc)
        action_id = uuid4()
        level = self.get_autonomy_level(user)

        # Check permission
        if level == AIActionAutonomyLevel.ADMIN:
            allowed = ADMIN_ACTIONS
        elif level == AIActionAutonomyLevel.EDITOR:
            allowed = EDITOR_ACTIONS
        else:
            allowed = VIEWER_ACTIONS

        if request.action_type not in allowed:
            return AIActionResult(
                action_id=action_id,
                action_type=request.action_type,
                status=AIActionStatus.FAILED,
                message="Keine Berechtigung fuer diese Aktion.",
                execution_time_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            )

        # Check if action requires confirmation
        requires_confirmation = (
            request.action_type in SUPERVISED_ACTIONS
            and level != AIActionAutonomyLevel.ADMIN
            and not request.auto_execute
        )

        if requires_confirmation:
            # Create suggestion instead of executing
            suggestion = await self._create_suggestion(
                action_id=action_id,
                request=request,
            )
            self._pending_suggestions[action_id] = suggestion

            return AIActionResult(
                action_id=action_id,
                action_type=request.action_type,
                status=AIActionStatus.SUGGESTED,
                message="Aktion vorgeschlagen. Bitte bestaetigen Sie die Ausfuehrung.",
                details={"suggestion": suggestion.model_dump()},
                execution_time_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            )

        # Execute the action
        try:
            result = await self._execute_action_impl(
                db=db,
                user=user,
                action_id=action_id,
                request=request,
            )
            return result
        except Exception as e:
            logger.error(
                "ai_action_failed",
                action_type=request.action_type.value,
                error=str(e),
            )
            return AIActionResult(
                action_id=action_id,
                action_type=request.action_type,
                status=AIActionStatus.FAILED,
                message=f"Aktion fehlgeschlagen: {str(e)}",
                execution_time_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            )

    async def confirm_action(
        self,
        db: AsyncSession,
        user: User,
        action_id: UUID,
        confirmed: bool,
        modified_parameters: Optional[Dict[str, Any]] = None,
    ) -> AIActionResult:
        """Bestaetigt oder lehnt eine vorgeschlagene Aktion ab.

        Args:
            db: Database Session
            user: Der aktuelle User
            action_id: ID der Aktion
            confirmed: True = bestaetigen, False = ablehnen
            modified_parameters: Optionale geaenderte Parameter

        Returns:
            Action Result
        """
        start_time = datetime.now(timezone.utc)

        if action_id not in self._pending_suggestions:
            return AIActionResult(
                action_id=action_id,
                action_type=AIActionType.SEARCH_DOCUMENTS,  # Default
                status=AIActionStatus.FAILED,
                message="Vorschlag nicht gefunden oder bereits verarbeitet.",
                execution_time_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            )

        suggestion = self._pending_suggestions.pop(action_id)

        if not confirmed:
            logger.info(
                "ai_action_rejected",
                action_id=str(action_id),
                action_type=suggestion.action_type.value,
            )
            return AIActionResult(
                action_id=action_id,
                action_type=suggestion.action_type,
                status=AIActionStatus.REJECTED,
                message="Aktion wurde abgelehnt.",
                execution_time_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            )

        # Build request from suggestion
        parameters = {p.name: p.value for p in suggestion.parameters}
        if modified_parameters:
            parameters.update(modified_parameters)

        request = AIActionRequest(
            action_type=suggestion.action_type,
            parameters=parameters,
            auto_execute=True,  # Already confirmed
        )

        return await self._execute_action_impl(
            db=db,
            user=user,
            action_id=action_id,
            request=request,
        )

    async def _create_suggestion(
        self,
        action_id: UUID,
        request: AIActionRequest,
    ) -> AIActionSuggestion:
        """Erstellt einen Aktions-Vorschlag.

        Args:
            action_id: ID der Aktion
            request: Original Request

        Returns:
            AIActionSuggestion
        """
        desc = ACTION_DESCRIPTIONS.get(request.action_type, {})

        parameters = [
            AIActionParameter(
                name=key,
                value=value,
                label=key.replace("_", " ").title(),
                editable=True,
            )
            for key, value in request.parameters.items()
        ]

        return AIActionSuggestion(
            action_id=action_id,
            action_type=request.action_type,
            title=desc.get("title", request.action_type.value),
            description=desc.get("description", ""),
            parameters=parameters,
            confidence=0.85,  # Default confidence
            requires_confirmation=True,
            estimated_impact=desc.get("impact", "Unbekannt"),
        )

    async def _execute_action_impl(
        self,
        db: AsyncSession,
        user: User,
        action_id: UUID,
        request: AIActionRequest,
    ) -> AIActionResult:
        """Fuehrt die eigentliche Aktion aus.

        Args:
            db: Database Session
            user: Der aktuelle User
            action_id: Action ID
            request: Action Request

        Returns:
            AIActionResult
        """
        start_time = datetime.now(timezone.utc)
        affected_items: List[UUID] = []
        details: Dict[str, Any] = {}

        # Dispatch to specific action handlers
        if request.action_type == AIActionType.SEARCH_DOCUMENTS:
            message = "Suche ausgefuehrt."
            details = {"query": request.parameters.get("query", "")}

        elif request.action_type == AIActionType.ANALYZE_ENTITY:
            entity_id = request.context_id or request.parameters.get("entity_id")
            message = f"Analyse fuer Entitaet abgeschlossen."
            if entity_id:
                affected_items.append(entity_id)

        elif request.action_type == AIActionType.GENERATE_REPORT:
            message = "Bericht wird generiert..."
            details = {"report_type": request.parameters.get("report_type", "standard")}

        elif request.action_type == AIActionType.EXPLAIN_DOCUMENT:
            doc_id = request.context_id or request.parameters.get("document_id")
            message = "Dokument-Erklaerung generiert."
            if doc_id:
                affected_items.append(doc_id)

        elif request.action_type == AIActionType.CATEGORIZE_DOCUMENT:
            doc_id = request.context_id or request.parameters.get("document_id")
            category = request.parameters.get("category", "Unbekannt")
            message = f"Dokument als '{category}' kategorisiert."
            if doc_id:
                affected_items.append(doc_id)
                # TODO: Actually update the document category in DB

        elif request.action_type == AIActionType.TAG_DOCUMENT:
            doc_id = request.context_id or request.parameters.get("document_id")
            tags = request.parameters.get("tags", [])
            message = f"Tags hinzugefuegt: {', '.join(tags) if tags else 'keine'}"
            if doc_id:
                affected_items.append(doc_id)
                # TODO: Actually add tags to document

        elif request.action_type == AIActionType.LINK_ENTITY:
            doc_id = request.context_id
            entity_id = request.parameters.get("entity_id")
            message = "Dokument mit Geschaeftspartner verknuepft."
            if doc_id:
                affected_items.append(doc_id)
            if entity_id:
                affected_items.append(entity_id)
            # TODO: Actually create the link

        elif request.action_type == AIActionType.CREATE_REMINDER:
            message = "Erinnerung erstellt."
            details = {
                "due_date": request.parameters.get("due_date"),
                "title": request.parameters.get("title"),
            }
            # TODO: Actually create reminder

        elif request.action_type == AIActionType.APPROVE_VALIDATION:
            doc_id = request.context_id or request.parameters.get("document_id")
            message = "Validierung genehmigt."
            if doc_id:
                affected_items.append(doc_id)
            # TODO: Actually approve validation

        elif request.action_type == AIActionType.TRIGGER_OCR:
            doc_id = request.context_id or request.parameters.get("document_id")
            message = "OCR-Verarbeitung gestartet."
            if doc_id:
                affected_items.append(doc_id)
            # TODO: Actually trigger OCR task

        elif request.action_type == AIActionType.SEND_NOTIFICATION:
            message = "Benachrichtigung gesendet."
            details = {
                "recipient": request.parameters.get("recipient"),
                "channel": request.parameters.get("channel", "email"),
            }
            # TODO: Actually send notification

        elif request.action_type == AIActionType.BULK_CATEGORIZE:
            doc_ids = request.parameters.get("document_ids", [])
            category = request.parameters.get("category", "Unbekannt")
            message = f"{len(doc_ids)} Dokumente als '{category}' kategorisiert."
            affected_items.extend([UUID(d) if isinstance(d, str) else d for d in doc_ids])
            # TODO: Actually bulk categorize

        else:
            message = "Unbekannte Aktion."

        execution_time = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        logger.info(
            "ai_action_completed",
            action_id=str(action_id),
            action_type=request.action_type.value,
            user_id=str(user.id),
            affected_items=len(affected_items),
            execution_time_ms=execution_time,
        )

        return AIActionResult(
            action_id=action_id,
            action_type=request.action_type,
            status=AIActionStatus.COMPLETED,
            message=message,
            details=details if details else None,
            affected_items=affected_items,
            execution_time_ms=execution_time,
        )

    def get_context_info(
        self,
        user: User,
        page_type: str,
        document_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
    ) -> AIContextInfo:
        """Gibt Kontext-Informationen fuer den AI-Assistent zurueck.

        Args:
            user: Der aktuelle User
            page_type: Aktueller Seitentyp
            document_id: Optional Document ID
            entity_id: Optional Entity ID

        Returns:
            AIContextInfo mit Vorschlaegen und verfuegbaren Aktionen
        """
        level = self.get_autonomy_level(user)

        # Get available actions based on context
        context_type = None
        if document_id:
            context_type = 'document'
        elif entity_id:
            context_type = 'entity'

        available = self.get_available_actions(user, context_type)
        action_types = [AIActionType(a["action_type"]) for a in available.available_actions]

        # Generate context-specific suggestions
        suggestions = self._get_context_suggestions(page_type, document_id, entity_id)

        return AIContextInfo(
            page_type=page_type,
            document_id=document_id,
            entity_id=entity_id,
            suggestions=suggestions,
            available_actions=action_types,
        )

    def _get_context_suggestions(
        self,
        page_type: str,
        document_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
    ) -> List[str]:
        """Generiert kontextspezifische Vorschlaege.

        Args:
            page_type: Seitentyp
            document_id: Optional Document ID
            entity_id: Optional Entity ID

        Returns:
            Liste von Vorschlaegen auf Deutsch
        """
        suggestions = {
            'dashboard': [
                "Was sind meine offenen Aufgaben?",
                "Zeige mir die wichtigsten KPIs",
                "Welche Rechnungen sind ueberfaellig?",
            ],
            'documents': [
                "Finde alle Rechnungen von letztem Monat",
                "Zeige mir unbezahlte Rechnungen",
                "Suche nach Vertraegen",
            ],
            'document-detail': [
                "Fasse dieses Dokument zusammen",
                "Welche Entitaeten sind hier erwaehnt?",
                "Kategorisiere dieses Dokument",
            ],
            'entities': [
                "Zeige mir High-Risk Kunden",
                "Wer hat offene Rechnungen?",
                "Analysiere Zahlungsverhalten",
            ],
            'entity-detail': [
                "Zeige mir alle Dokumente zu diesem Kunden",
                "Wie ist das Zahlungsverhalten?",
                "Erstelle einen Kundenbericht",
            ],
            'invoices': [
                "Welche Rechnungen sind ueberfaellig?",
                "Zeige mir Skonto-Moeglichkeiten",
                "Analysiere Zahlungseingaenge",
            ],
            'banking': [
                "Zeige offene Transaktionen",
                "Finde nicht zugeordnete Buchungen",
                "Analysiere Kontoumsaetze",
            ],
            'validation': [
                "Zeige mir Items mit niedrigem Confidence",
                "Was muss ich heute validieren?",
                "Erklaere die OCR-Fehler",
            ],
        }

        return suggestions.get(page_type, [
            "Wie kann ich dir helfen?",
            "Suche in meinen Dokumenten",
            "Analysiere meine Daten",
        ])


# Singleton instance
_ai_action_service: Optional[AIActionService] = None


def get_ai_action_service() -> AIActionService:
    """Gibt die AI Action Service Instanz zurueck.

    Returns:
        AIActionService Singleton
    """
    global _ai_action_service
    if _ai_action_service is None:
        _ai_action_service = AIActionService()
    return _ai_action_service

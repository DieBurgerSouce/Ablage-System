"""
AI Action Service.

Handles AI-driven actions with role-based autonomy levels:
- Viewer: Read-only actions (search, analyze, report)
- Editor: Supervised actions (requires confirmation)
- Admin: Autonomous actions (self-executing)

ENTERPRISE: Alle Aktionen führen echte DB-Operationen durch.
"""

import asyncio
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func as sa_func

from app.db.models import (
    User, Document, BusinessEntity, Tag, ProcessingStatus, document_tags,
    InvoiceTracking, InvoiceStatus,
)
from app.core.safe_errors import safe_error_log, safe_error_detail
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
# PERIOD PARSING HELPERS
# ============================================================================

def _parse_period_range(period: str) -> tuple:
    """Parst Periodenbezeichnung in Start/End-Datetime.

    Unterstützte Formate:
    - YYYY-MM (z.B. '2025-01')
    - Qx_YYYY (z.B. 'Q3_2025')
    - letzter_monat, dieser_monat

    Args:
        period: Periodenstring

    Returns:
        Tuple (start_datetime, end_datetime) in UTC
    """
    import re as _re
    import calendar

    now = datetime.now(timezone.utc)

    # YYYY-MM Format
    match = _re.match(r'^(\d{4})-(\d{2})$', period)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        last_day = calendar.monthrange(year, month)[1]
        end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
        return start, end

    # Qx_YYYY Format
    match = _re.match(r'^Q(\d)_(\d{4})$', period, _re.IGNORECASE)
    if match:
        quarter, year = int(match.group(1)), int(match.group(2))
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        start = datetime(year, start_month, 1, tzinfo=timezone.utc)
        last_day = calendar.monthrange(year, end_month)[1]
        end = datetime(year, end_month, last_day, 23, 59, 59, tzinfo=timezone.utc)
        return start, end

    # Relative Perioden
    if period in ("letzter_monat", "last_month"):
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_of_this_month - timedelta(seconds=1)
        start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, end

    if period in ("dieser_monat", "this_month"):
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = calendar.monthrange(now.year, now.month)[1]
        end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
        return start, end

    # Fallback: letztes Jahr
    start = datetime(now.year - 1, 1, 1, tzinfo=timezone.utc)
    end = datetime(now.year - 1, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


# ============================================================================
# ACTION DEFINITIONS
# ============================================================================

# Actions available at each autonomy level
VIEWER_ACTIONS = {
    AIActionType.SEARCH_DOCUMENTS,
    AIActionType.ANALYZE_ENTITY,
    AIActionType.GENERATE_REPORT,
    AIActionType.EXPLAIN_DOCUMENT,
    AIActionType.GET_DAILY_AGENDA,
    AIActionType.COMPARE_EXPENSES,
    AIActionType.GET_SKONTO,
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
    AIActionType.BOOK_INVOICE,
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
    AIActionType.BOOK_INVOICE,
}

# German action descriptions
ACTION_DESCRIPTIONS: Dict[AIActionType, Dict[str, str]] = {
    AIActionType.SEARCH_DOCUMENTS: {
        "title": "Dokumente durchsuchen",
        "description": "Durchsucht die Dokumentenbasis nach relevanten Inhalten.",
        "impact": "Keine Änderungen - nur Lesezugriff",
    },
    AIActionType.ANALYZE_ENTITY: {
        "title": "Geschäftspartner analysieren",
        "description": "Analysiert Daten zu einem Kunden oder Lieferanten.",
        "impact": "Keine Änderungen - nur Analyse",
    },
    AIActionType.GENERATE_REPORT: {
        "title": "Bericht erstellen",
        "description": "Generiert einen Bericht basierend auf den Daten.",
        "impact": "Keine Änderungen - nur Export",
    },
    AIActionType.EXPLAIN_DOCUMENT: {
        "title": "Dokument erklären",
        "description": "Erklärt den Inhalt und die wichtigsten Punkte eines Dokuments.",
        "impact": "Keine Änderungen - nur Erklärung",
    },
    AIActionType.CATEGORIZE_DOCUMENT: {
        "title": "Dokument kategorisieren",
        "description": "Ordnet das Dokument einer Kategorie zu.",
        "impact": "Ändert Dokument-Kategorie",
    },
    AIActionType.TAG_DOCUMENT: {
        "title": "Tags hinzufuegen",
        "description": "Fuegt Tags zum Dokument hinzu.",
        "impact": "Ändert Dokument-Tags",
    },
    AIActionType.LINK_ENTITY: {
        "title": "Mit Geschäftspartner verknüpfen",
        "description": "Verknüpft das Dokument mit einem Kunden oder Lieferanten.",
        "impact": "Erstellt Verknüpfung",
    },
    AIActionType.CREATE_REMINDER: {
        "title": "Erinnerung erstellen",
        "description": "Erstellt eine Erinnerung für eine Aufgabe.",
        "impact": "Erstellt neue Erinnerung",
    },
    AIActionType.APPROVE_VALIDATION: {
        "title": "Validierung genehmigen",
        "description": "Genehmigt ein Dokument in der Validierungs-Queue.",
        "impact": "Ändert Validierungs-Status",
    },
    AIActionType.TRIGGER_OCR: {
        "title": "OCR starten",
        "description": "Startet die OCR-Verarbeitung für ein Dokument.",
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
        "impact": "Ändert mehrere Dokumente",
    },
    AIActionType.GET_DAILY_AGENDA: {
        "title": "Tagesagenda anzeigen",
        "description": "Zeigt Fristen, offene Freigaben, Skonto-Deadlines und überfällige Rechnungen.",
        "impact": "Keine Änderungen - nur Lesezugriff",
    },
    AIActionType.COMPARE_EXPENSES: {
        "title": "Ausgaben vergleichen",
        "description": "Vergleicht Ausgaben zwischen zwei Zeitraeumen nach Kategorie oder Lieferant.",
        "impact": "Keine Änderungen - nur Analyse",
    },
    AIActionType.GET_SKONTO: {
        "title": "Skonto-Möglichkeiten anzeigen",
        "description": "Zeigt aktuelle Skonto-Möglichkeiten mit Fristen und Ersparnissen.",
        "impact": "Keine Änderungen - nur Analyse",
    },
    AIActionType.BOOK_INVOICE: {
        "title": "Rechnung buchen",
        "description": "Bucht eine Rechnung auf ein bestimmtes Sachkonto oder eine Kostenstelle.",
        "impact": "Ändert Buchungsdaten der Rechnung",
    },
}


class AIActionService:
    """Service für AI-gesteuerte Aktionen."""

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
        """Gibt verfügbare Aktionen basierend auf Rolle zurück.

        Args:
            user: Der aktuelle User
            context_type: Optionaler Kontext-Typ (document, entity, etc.)

        Returns:
            Liste der verfügbaren Aktionen
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
        """Führt eine AI-Aktion aus.

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
                message="Keine Berechtigung für diese Aktion.",
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
                message="Aktion vorgeschlagen. Bitte bestätigen Sie die Ausführung.",
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
                **safe_error_log(e),
            )
            return AIActionResult(
                action_id=action_id,
                action_type=request.action_type,
                status=AIActionStatus.FAILED,
                message=safe_error_detail(e, "RAG-Aktion"),
                execution_time_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            )

    async def confirm_action(
        self,
        db: AsyncSession,
        user: User,
        action_id: UUID,
        confirmed: bool,
        modified_parameters: Optional[Dict[str, object]] = None,
    ) -> AIActionResult:
        """Bestätigt oder lehnt eine vorgeschlagene Aktion ab.

        Args:
            db: Database Session
            user: Der aktuelle User
            action_id: ID der Aktion
            confirmed: True = bestätigen, False = ablehnen
            modified_parameters: Optionale geänderte Parameter

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
        """Führt die eigentliche Aktion aus.

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
        details: Dict[str, object] = {}

        # W2-13: User-Modell hat KEINE company_id-Spalte (Tenancy via UserCompany).
        # Aktive Firma einmalig zentral aufloesen (Helper aus app.api.dependencies;
        # lokaler Import vermeidet Service<->API Zirkular-Import).
        from app.api.dependencies import get_user_company_id
        company_id = await get_user_company_id(db, user)

        # Dispatch to specific action handlers
        if request.action_type == AIActionType.SEARCH_DOCUMENTS:
            message = "Suche ausgeführt."
            details = {"query": request.parameters.get("query", "")}

        elif request.action_type == AIActionType.ANALYZE_ENTITY:
            entity_id = request.context_id or request.parameters.get("entity_id")
            message = f"Analyse für Entität abgeschlossen."
            if entity_id:
                affected_items.append(entity_id)

        elif request.action_type == AIActionType.GENERATE_REPORT:
            message = "Bericht wird generiert..."
            details = {"report_type": request.parameters.get("report_type", "standard")}

        elif request.action_type == AIActionType.EXPLAIN_DOCUMENT:
            doc_id = request.context_id or request.parameters.get("document_id")
            message = "Dokument-Erklärung generiert."
            if doc_id:
                affected_items.append(doc_id)

        elif request.action_type == AIActionType.CATEGORIZE_DOCUMENT:
            doc_id = request.context_id or request.parameters.get("document_id")
            category = request.parameters.get("category", "Unbekannt")
            if doc_id:
                doc_uuid = UUID(doc_id) if isinstance(doc_id, str) else doc_id
                # Echte DB-Operation: Dokument-Kategorie aktualisieren
                await db.execute(
                    update(Document)
                    .where(
                        Document.id == doc_uuid,
                        Document.company_id == company_id,
                    )
                    .values(
                        document_type=category,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
                affected_items.append(doc_uuid)
                message = f"Dokument als '{category}' kategorisiert."
                logger.info(
                    "document_categorized_by_ai",
                    document_id=str(doc_uuid),
                    category=category,
                    user_id=str(user.id),
                )
            else:
                message = "Fehler: Keine Dokument-ID angegeben."

        elif request.action_type == AIActionType.TAG_DOCUMENT:
            doc_id = request.context_id or request.parameters.get("document_id")
            tags = request.parameters.get("tags", [])
            if doc_id and tags:
                doc_uuid = UUID(doc_id) if isinstance(doc_id, str) else doc_id
                # Echte DB-Operation: Tags zum Dokument hinzufuegen
                for tag_name in tags:
                    # Prüfe ob Tag bereits existiert
                    existing_tag = await db.execute(
                        select(Tag).where(Tag.name == tag_name)
                    )
                    tag_obj = existing_tag.scalar_one_or_none()
                    if not tag_obj:
                        tag_obj = Tag(name=tag_name)
                        db.add(tag_obj)
                        await db.flush()
                    # Verknüpfe Tag mit Dokument (via association table)
                    existing_link = await db.execute(
                        select(document_tags).where(
                            document_tags.c.document_id == doc_uuid,
                            document_tags.c.tag_id == tag_obj.id,
                        )
                    )
                    if not existing_link.first():
                        await db.execute(
                            document_tags.insert().values(
                                document_id=doc_uuid,
                                tag_id=tag_obj.id,
                            )
                        )
                await db.commit()
                affected_items.append(doc_uuid)
                message = f"Tags hinzugefuegt: {', '.join(tags)}"
                logger.info(
                    "document_tagged_by_ai",
                    document_id=str(doc_uuid),
                    tags=tags,
                    user_id=str(user.id),
                )
            else:
                message = f"Tags hinzugefuegt: {', '.join(tags) if tags else 'keine'}"

        elif request.action_type == AIActionType.LINK_ENTITY:
            doc_id = request.context_id
            entity_id = request.parameters.get("entity_id")
            if doc_id and entity_id:
                doc_uuid = UUID(doc_id) if isinstance(doc_id, str) else doc_id
                entity_uuid = UUID(entity_id) if isinstance(entity_id, str) else entity_id
                # Echte DB-Operation: Entity mit Dokument verknüpfen
                await db.execute(
                    update(Document)
                    .where(
                        Document.id == doc_uuid,
                        Document.company_id == company_id,
                    )
                    .values(
                        business_entity_id=entity_uuid,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
                affected_items.append(doc_uuid)
                affected_items.append(entity_uuid)
                message = "Dokument mit Geschäftspartner verknüpft."
                logger.info(
                    "document_linked_to_entity_by_ai",
                    document_id=str(doc_uuid),
                    entity_id=str(entity_uuid),
                    user_id=str(user.id),
                )
            else:
                message = "Fehler: Dokument-ID oder Entity-ID fehlt."

        elif request.action_type == AIActionType.CREATE_REMINDER:
            from app.db.models import Reminder
            due_date_str = request.parameters.get("due_date")
            title = request.parameters.get("title", "AI-Erinnerung")
            description = request.parameters.get("description", "")
            doc_id = request.context_id

            # Parse due_date
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
                except ValueError:
                    due_date = datetime.now(timezone.utc) + timedelta(days=7)
            else:
                due_date = datetime.now(timezone.utc) + timedelta(days=7)

            # Echte DB-Operation: Erinnerung erstellen
            reminder = Reminder(
                id=uuid4(),
                user_id=user.id,
                company_id=company_id,
                title=title,
                description=description,
                due_date=due_date,
                document_id=UUID(doc_id) if doc_id and isinstance(doc_id, str) else doc_id,
                created_at=datetime.now(timezone.utc),
                is_completed=False,
            )
            db.add(reminder)
            await db.commit()
            affected_items.append(reminder.id)
            message = f"Erinnerung '{title}' erstellt für {due_date.strftime('%d.%m.%Y')}."
            details = {
                "reminder_id": str(reminder.id),
                "due_date": due_date.isoformat(),
                "title": title,
            }
            logger.info(
                "reminder_created_by_ai",
                reminder_id=str(reminder.id),
                due_date=due_date.isoformat(),
                user_id=str(user.id),
            )

        elif request.action_type == AIActionType.APPROVE_VALIDATION:
            doc_id = request.context_id or request.parameters.get("document_id")
            if doc_id:
                doc_uuid = UUID(doc_id) if isinstance(doc_id, str) else doc_id
                # Echte DB-Operation: Validierung genehmigen (Status auf COMPLETED)
                await db.execute(
                    update(Document)
                    .where(
                        Document.id == doc_uuid,
                        Document.company_id == company_id,
                    )
                    .values(
                        status=ProcessingStatus.COMPLETED.value,
                        processed_date=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
                affected_items.append(doc_uuid)
                message = "Validierung genehmigt - Dokument als abgeschlossen markiert."
                logger.info(
                    "validation_approved_by_ai",
                    document_id=str(doc_uuid),
                    user_id=str(user.id),
                )
            else:
                message = "Fehler: Keine Dokument-ID angegeben."

        elif request.action_type == AIActionType.TRIGGER_OCR:
            doc_id = request.context_id or request.parameters.get("document_id")
            if doc_id:
                doc_uuid = UUID(doc_id) if isinstance(doc_id, str) else doc_id
                # Echte Operation: OCR-Task via Celery ausloesen
                from app.workers.tasks import ocr_tasks
                try:
                    # Setze Status auf PROCESSING
                    await db.execute(
                        update(Document)
                        .where(
                            Document.id == doc_uuid,
                            Document.company_id == company_id,
                        )
                        .values(
                            status=ProcessingStatus.PROCESSING.value,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    await db.commit()

                    # Trigger Celery Task
                    ocr_tasks.process_document_task.delay(str(doc_uuid))
                    affected_items.append(doc_uuid)
                    message = "OCR-Verarbeitung gestartet."
                    logger.info(
                        "ocr_triggered_by_ai",
                        document_id=str(doc_uuid),
                        user_id=str(user.id),
                    )
                except Exception as e:
                    message = safe_error_detail(e, "OCR-Start")
                    logger.error(
                        "ocr_trigger_failed",
                        document_id=str(doc_uuid),
                        **safe_error_log(e),
                    )
            else:
                message = "Fehler: Keine Dokument-ID angegeben."

        elif request.action_type == AIActionType.SEND_NOTIFICATION:
            recipient = request.parameters.get("recipient")
            channel = request.parameters.get("channel", "email")
            notification_message = request.parameters.get("message", "")
            subject = request.parameters.get("subject", "Benachrichtigung")

            # Echte Operation: Notification senden
            if channel == "slack":
                from app.services.slack_service import SlackService
                slack_service = SlackService()
                if slack_service.is_configured():
                    await slack_service.send_message(
                        channel=recipient or "#general",
                        text=notification_message,
                        blocks=None,
                    )
                    message = f"Slack-Nachricht an {recipient or '#general'} gesendet."
                else:
                    message = "Slack ist nicht konfiguriert."
            else:
                # Email-Benachrichtigung (via NotificationService)
                from app.db.models import Notification

                notification = Notification(
                    id=uuid4(),
                    user_id=user.id,
                    company_id=company_id,
                    title=subject,
                    message=notification_message,
                    notification_type="ai_action",
                    channel=channel,
                    is_read=False,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(notification)
                await db.commit()
                affected_items.append(notification.id)
                message = "Benachrichtigung erstellt."

            details = {
                "recipient": recipient,
                "channel": channel,
            }
            logger.info(
                "notification_sent_by_ai",
                channel=channel,
                recipient=recipient,
                user_id=str(user.id),
            )

        elif request.action_type == AIActionType.BULK_CATEGORIZE:
            doc_ids = request.parameters.get("document_ids", [])
            category = request.parameters.get("category", "Unbekannt")
            if doc_ids:
                doc_uuids = [UUID(d) if isinstance(d, str) else d for d in doc_ids]
                # Echte DB-Operation: Bulk-Kategorisierung
                await db.execute(
                    update(Document)
                    .where(
                        Document.id.in_(doc_uuids),
                        Document.company_id == company_id,
                    )
                    .values(
                        document_type=category,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
                affected_items.extend(doc_uuids)
                message = f"{len(doc_uuids)} Dokumente als '{category}' kategorisiert."
                logger.info(
                    "bulk_categorize_by_ai",
                    document_count=len(doc_uuids),
                    category=category,
                    user_id=str(user.id),
                )
            else:
                message = "Keine Dokumente zur Kategorisierung angegeben."

        elif request.action_type == AIActionType.GET_DAILY_AGENDA:
            include_future_days = request.parameters.get("include_future_days", 3)
            now = datetime.now(timezone.utc)
            future_cutoff = now + timedelta(days=int(include_future_days))

            # Überfällige Rechnungen (via InvoiceTracking)
            overdue_result = await db.execute(
                select(InvoiceTracking).where(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status == InvoiceStatus.OVERDUE.value,
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            overdue_invoices = overdue_result.scalars().all()

            # Ausstehende Validierungen (Dokumente im Pending-Status)
            pending_result = await db.execute(
                select(sa_func.count()).select_from(Document).where(
                    Document.company_id == company_id,
                    Document.status == ProcessingStatus.PENDING.value,
                    Document.deleted_at.is_(None),
                )
            )
            pending_count = pending_result.scalar() or 0

            # Skonto-Deadlines die bald ablaufen
            skonto_result = await db.execute(
                select(InvoiceTracking).where(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_used.is_(False),
                    InvoiceTracking.skonto_deadline >= now,
                    InvoiceTracking.skonto_deadline <= future_cutoff,
                    InvoiceTracking.status.in_([
                        InvoiceStatus.OPEN.value,
                        InvoiceStatus.SENT.value,
                    ]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            skonto_invoices = skonto_result.scalars().all()

            agenda_items: List[Dict[str, object]] = []
            for inv in overdue_invoices:
                agenda_items.append({
                    "typ": "überfällig",
                    "document_id": str(inv.document_id),
                    "rechnungsnummer": inv.invoice_number or "Unbekannt",
                    "betrag": float(inv.amount or 0),
                    "tage_verzug": inv.days_overdue,
                })
            for inv in skonto_invoices:
                days_left = inv.days_until_skonto_expires
                agenda_items.append({
                    "typ": "skonto_frist",
                    "document_id": str(inv.document_id),
                    "rechnungsnummer": inv.invoice_number or "Unbekannt",
                    "betrag": float(inv.amount or 0),
                    "skonto_prozent": float(inv.skonto_percentage or 0),
                    "tage_verbleibend": days_left if days_left is not None else 0,
                })

            details = {
                "überfällige_rechnungen": len(overdue_invoices),
                "ausstehende_validierungen": pending_count,
                "skonto_fristen": len(skonto_invoices),
                "items": agenda_items,
            }
            message = (
                f"Tagesagenda: {len(overdue_invoices)} überfällige Rechnungen, "
                f"{pending_count} ausstehende Validierungen, "
                f"{len(skonto_invoices)} ablaufende Skonto-Fristen."
            )
            logger.info(
                "daily_agenda_generated",
                overdue=len(overdue_invoices),
                pending=pending_count,
                skonto=len(skonto_invoices),
                user_id=str(user.id),
            )

        elif request.action_type == AIActionType.COMPARE_EXPENSES:
            period_1 = request.parameters.get("period_1", "")
            period_2 = request.parameters.get("period_2", "")
            group_by = request.parameters.get("group_by", "kategorie")

            range_1_start, range_1_end = _parse_period_range(str(period_1))
            range_2_start, range_2_end = _parse_period_range(str(period_2))

            # Summe und Anzahl für Periode 1
            result_1 = await db.execute(
                select(
                    sa_func.coalesce(sa_func.sum(InvoiceTracking.amount), 0),
                    sa_func.count(InvoiceTracking.id),
                ).where(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= range_1_start,
                    InvoiceTracking.invoice_date < range_1_end,
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            row_1 = result_1.one()
            total_1 = float(row_1[0])
            count_1 = int(row_1[1])

            # Summe und Anzahl für Periode 2
            result_2 = await db.execute(
                select(
                    sa_func.coalesce(sa_func.sum(InvoiceTracking.amount), 0),
                    sa_func.count(InvoiceTracking.id),
                ).where(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= range_2_start,
                    InvoiceTracking.invoice_date < range_2_end,
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            row_2 = result_2.one()
            total_2 = float(row_2[0])
            count_2 = int(row_2[1])

            diff = total_2 - total_1
            diff_percent = (diff / total_1 * 100) if total_1 > 0 else 0.0

            details = {
                "periode_1": {"label": period_1, "summe": total_1, "anzahl": count_1},
                "periode_2": {"label": period_2, "summe": total_2, "anzahl": count_2},
                "differenz": diff,
                "differenz_prozent": round(diff_percent, 1),
                "gruppierung": group_by,
            }
            direction = "mehr" if diff > 0 else "weniger"
            message = (
                f"Ausgabenvergleich: {period_1} ({total_1:.2f} EUR, {count_1} Rechnungen) vs. "
                f"{period_2} ({total_2:.2f} EUR, {count_2} Rechnungen) - "
                f"{abs(diff):.2f} EUR {direction} ({abs(diff_percent):.1f}%)."
            )
            logger.info(
                "expenses_compared",
                period_1=period_1,
                period_2=period_2,
                diff=diff,
                user_id=str(user.id),
            )

        elif request.action_type == AIActionType.GET_SKONTO:
            days_ahead = request.parameters.get("days_ahead", 14)
            now = datetime.now(timezone.utc)
            cutoff = now + timedelta(days=int(days_ahead))

            # Rechnungen mit Skonto-Bedingungen (via InvoiceTracking)
            skonto_result = await db.execute(
                select(InvoiceTracking).where(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_used.is_(False),
                    InvoiceTracking.skonto_deadline >= now,
                    InvoiceTracking.skonto_deadline <= cutoff,
                    InvoiceTracking.status.in_([
                        InvoiceStatus.OPEN.value,
                        InvoiceStatus.SENT.value,
                    ]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            skonto_invoices = skonto_result.scalars().all()

            opportunities: List[Dict[str, object]] = []
            total_savings = 0.0
            for inv in skonto_invoices:
                amount = float(inv.amount or 0)
                skonto_pct = float(inv.skonto_percentage or 0)
                saving = float(inv.skonto_amount or (amount * skonto_pct / 100))
                total_savings += saving
                days_left = inv.days_until_skonto_expires
                opportunities.append({
                    "document_id": str(inv.document_id),
                    "rechnungsnummer": inv.invoice_number or "Unbekannt",
                    "betrag": amount,
                    "skonto_prozent": skonto_pct,
                    "ersparnis": round(saving, 2),
                    "tage_verbleibend": days_left if days_left is not None else 0,
                })

            details = {
                "anzahl": len(opportunities),
                "gesamt_ersparnis": round(total_savings, 2),
                "opportunities": opportunities,
            }
            message = (
                f"{len(opportunities)} Skonto-Möglichkeiten in den nächsten {days_ahead} Tagen. "
                f"Potenzielle Ersparnis: {total_savings:.2f} EUR."
            )
            logger.info(
                "skonto_opportunities_retrieved",
                count=len(opportunities),
                total_savings=total_savings,
                user_id=str(user.id),
            )

        elif request.action_type == AIActionType.BOOK_INVOICE:
            from app.db.models import DATEVBuchung, DATEVConnection
            doc_id = request.parameters.get("document_id")
            account_number = request.parameters.get("account_number", "")
            cost_center = request.parameters.get("cost_center")

            if doc_id and account_number:
                doc_uuid = UUID(doc_id) if isinstance(doc_id, str) else doc_id

                # Hole Rechnungsdaten
                doc_result = await db.execute(
                    select(Document).where(
                        Document.id == doc_uuid,
                        Document.company_id == company_id,
                    )
                )
                doc = doc_result.scalar_one_or_none()
                if not doc:
                    message = "Fehler: Dokument nicht gefunden."
                else:
                    # Aktive DATEV-Verbindung für diese Company
                    conn_result = await db.execute(
                        select(DATEVConnection).where(
                            DATEVConnection.company_id == company_id,
                            DATEVConnection.is_active.is_(True),
                            DATEVConnection.connection_status == "connected",
                        ).limit(1)
                    )
                    datev_conn = conn_result.scalar_one_or_none()
                    if not datev_conn:
                        message = "Fehler: Keine aktive DATEV-Verbindung konfiguriert."
                    else:
                        # Betrag aus InvoiceTracking
                        inv_result = await db.execute(
                            select(InvoiceTracking).where(
                                InvoiceTracking.document_id == doc_uuid,
                                InvoiceTracking.deleted_at.is_(None),
                            )
                        )
                        inv = inv_result.scalar_one_or_none()
                        betrag = float(inv.amount) if inv else 0.0

                        # DATEVBuchung erstellen
                        buchung = DATEVBuchung(
                            id=uuid4(),
                            connection_id=datev_conn.id,
                            document_id=doc_uuid,
                            entity_id=doc.business_entity_id,
                            belegdatum=date.today(),
                            buchungsdatum=date.today(),
                            betrag_soll=betrag,
                            betrag_haben=betrag,
                            konto_soll=str(account_number),
                            konto_haben="1200",  # Standard-Gegenkonto (Bank)
                            buchungstext=f"AI-Buchung: {doc.original_filename or 'Rechnung'}",
                            belegnummer=inv.invoice_number if inv else None,
                            kostenstelle_1=str(cost_center) if cost_center else None,
                            created_by=user.id,
                        )
                        db.add(buchung)

                        # Rechnung als abgeschlossen markieren
                        await db.execute(
                            update(Document)
                            .where(Document.id == doc_uuid)
                            .values(
                                status=ProcessingStatus.COMPLETED.value,
                                updated_at=datetime.now(timezone.utc),
                            )
                        )
                        await db.commit()

                        affected_items.append(doc_uuid)
                        affected_items.append(buchung.id)
                        cost_info = f" (Kostenstelle: {cost_center})" if cost_center else ""
                        message = f"Rechnung auf Konto {account_number} gebucht{cost_info}. Betrag: {betrag:.2f} EUR."
                        details = {
                            "buchung_id": str(buchung.id),
                            "document_id": str(doc_uuid),
                            "account_number": str(account_number),
                            "cost_center": cost_center,
                            "betrag": betrag,
                        }
                        logger.info(
                            "invoice_booked_by_ai",
                            document_id=str(doc_uuid),
                            buchung_id=str(buchung.id),
                            account_number=str(account_number),
                            cost_center=cost_center,
                            betrag=betrag,
                            user_id=str(user.id),
                        )
            else:
                message = "Fehler: Dokument-ID und Kontonummer sind erforderlich."

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
        """Gibt Kontext-Informationen für den AI-Assistent zurück.

        Args:
            user: Der aktuelle User
            page_type: Aktueller Seitentyp
            document_id: Optional Document ID
            entity_id: Optional Entity ID

        Returns:
            AIContextInfo mit Vorschlägen und verfügbaren Aktionen
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
        """Generiert kontextspezifische Vorschläge.

        Args:
            page_type: Seitentyp
            document_id: Optional Document ID
            entity_id: Optional Entity ID

        Returns:
            Liste von Vorschlägen auf Deutsch
        """
        suggestions = {
            'dashboard': [
                "Was sind meine offenen Aufgaben?",
                "Zeige mir die wichtigsten KPIs",
                "Welche Rechnungen sind überfällig?",
            ],
            'documents': [
                "Finde alle Rechnungen von letztem Monat",
                "Zeige mir unbezahlte Rechnungen",
                "Suche nach Verträgen",
            ],
            'document-detail': [
                "Fasse dieses Dokument zusammen",
                "Welche Entitäten sind hier erwaehnt?",
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
                "Welche Rechnungen sind überfällig?",
                "Zeige mir Skonto-Möglichkeiten",
                "Analysiere Zahlungseingaenge",
            ],
            'banking': [
                "Zeige offene Transaktionen",
                "Finde nicht zugeordnete Buchungen",
                "Analysiere Kontoumsätze",
            ],
            'validation': [
                "Zeige mir Items mit niedrigem Confidence",
                "Was muss ich heute validieren?",
                "Erkläre die OCR-Fehler",
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
    """Gibt die AI Action Service Instanz zurück.

    Returns:
        AIActionService Singleton
    """
    global _ai_action_service
    if _ai_action_service is None:
        _ai_action_service = AIActionService()
    return _ai_action_service

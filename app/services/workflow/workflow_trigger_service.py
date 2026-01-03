# -*- coding: utf-8 -*-
"""Workflow Trigger Service.

Verwaltet Workflow-Trigger (Events, Schedule, Webhook, Manual).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

import structlog
from croniter import croniter
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Workflow

if TYPE_CHECKING:
    from app.services.workflow.workflow_execution_service import WorkflowExecutionService

logger = structlog.get_logger(__name__)


class WorkflowTriggerService:
    """Service fuer Workflow-Trigger.

    Verwaltet:
    - Document Event Triggers (created, processed, failed, deleted)
    - Schedule Triggers (Cron-basiert)
    - Condition Triggers (Feldaenderungen)
    - Manual Triggers (API/UI-Ausloesung)
    - Webhook Triggers (Externe Systeme)
    """

    def __init__(
        self,
        db: AsyncSession,
        execution_service: Optional["WorkflowExecutionService"] = None,
    ) -> None:
        """Initialisiert den TriggerService.

        Args:
            db: AsyncSession fuer Datenbankoperationen
            execution_service: WorkflowExecutionService fuer Ausfuehrung
        """
        self.db = db
        self.execution_service = execution_service

    def set_execution_service(
        self,
        service: "WorkflowExecutionService",
    ) -> None:
        """Setzt den ExecutionService (fuer zirkulaere Abhaengigkeiten).

        Args:
            service: WorkflowExecutionService
        """
        self.execution_service = service

    # =========================================================================
    # Document Event Triggers
    # =========================================================================

    async def on_document_event(
        self,
        event_type: str,
        document_id: UUID,
        user_id: UUID,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> List[UUID]:
        """Wird bei Document-Events aufgerufen.

        Args:
            event_type: Event-Typ (created, processed, failed, deleted, status_changed)
            document_id: Dokument-ID
            user_id: User-ID
            event_data: Zusaetzliche Event-Daten

        Returns:
            Liste gestarteter Execution-IDs
        """
        logger.debug(
            "document_event_received",
            event_type=event_type,
            document_id=str(document_id),
        )

        # Matching Workflows finden
        workflows = await self._find_matching_workflows(
            trigger_type="document_event",
            user_id=user_id,
            event_type=event_type,
        )

        if not workflows:
            return []

        # Dokument-Daten laden
        document = await self._load_document(document_id)

        execution_ids = []

        for workflow in workflows:
            # Trigger-Bedingungen pruefen
            if not self._check_trigger_conditions(workflow, document, event_data):
                continue

            # Workflow ausfuehren
            try:
                if self.execution_service:
                    execution = await self.execution_service.start_execution(
                        workflow_id=workflow.id,
                        user_id=user_id,
                        document_id=document_id,
                        trigger_data={
                            "type": "document_event",
                            "event": event_type,
                            "document_id": str(document_id),
                            **(event_data or {}),
                        },
                    )
                    execution_ids.append(execution.id)

                    logger.info(
                        "workflow_triggered_by_document_event",
                        workflow_id=str(workflow.id),
                        workflow_name=workflow.name,
                        event_type=event_type,
                        document_id=str(document_id),
                        execution_id=str(execution.id),
                    )

            except Exception as e:
                logger.error(
                    "workflow_trigger_error",
                    workflow_id=str(workflow.id),
                    error=str(e),
                )

        return execution_ids

    async def on_document_created(
        self,
        document_id: UUID,
        user_id: UUID,
    ) -> List[UUID]:
        """Shortcut fuer document_created Event.

        Args:
            document_id: Dokument-ID
            user_id: User-ID

        Returns:
            Liste gestarteter Execution-IDs
        """
        return await self.on_document_event(
            event_type="created",
            document_id=document_id,
            user_id=user_id,
        )

    async def on_document_processed(
        self,
        document_id: UUID,
        user_id: UUID,
        ocr_result: Optional[Dict[str, Any]] = None,
    ) -> List[UUID]:
        """Shortcut fuer document_processed Event.

        Args:
            document_id: Dokument-ID
            user_id: User-ID
            ocr_result: OCR-Ergebnis

        Returns:
            Liste gestarteter Execution-IDs
        """
        return await self.on_document_event(
            event_type="processed",
            document_id=document_id,
            user_id=user_id,
            event_data={"ocr_result": ocr_result},
        )

    async def on_document_failed(
        self,
        document_id: UUID,
        user_id: UUID,
        error: str,
    ) -> List[UUID]:
        """Shortcut fuer document_failed Event.

        Args:
            document_id: Dokument-ID
            user_id: User-ID
            error: Fehlermeldung

        Returns:
            Liste gestarteter Execution-IDs
        """
        return await self.on_document_event(
            event_type="failed",
            document_id=document_id,
            user_id=user_id,
            event_data={"error": error},
        )

    async def on_document_status_changed(
        self,
        document_id: UUID,
        user_id: UUID,
        old_status: str,
        new_status: str,
    ) -> List[UUID]:
        """Shortcut fuer status_changed Event.

        Args:
            document_id: Dokument-ID
            user_id: User-ID
            old_status: Alter Status
            new_status: Neuer Status

        Returns:
            Liste gestarteter Execution-IDs
        """
        return await self.on_document_event(
            event_type="status_changed",
            document_id=document_id,
            user_id=user_id,
            event_data={
                "old_status": old_status,
                "new_status": new_status,
            },
        )

    # =========================================================================
    # Schedule Triggers
    # =========================================================================

    async def check_scheduled_workflows(self) -> List[UUID]:
        """Prueft und startet faellige Schedule-Workflows.

        Wird regelmaessig von Celery Beat aufgerufen.

        Returns:
            Liste gestarteter Execution-IDs
        """
        now = datetime.now(timezone.utc)

        # Aktive Schedule-Workflows finden
        query = select(Workflow).where(
            and_(
                Workflow.trigger_type == "schedule",
                Workflow.is_active == True,  # noqa: E712
            )
        )

        result = await self.db.execute(query)
        workflows = list(result.scalars().all())

        execution_ids = []

        for workflow in workflows:
            try:
                if self._should_run_scheduled_workflow(workflow, now):
                    if self.execution_service:
                        execution = await self.execution_service.start_execution(
                            workflow_id=workflow.id,
                            user_id=workflow.user_id,
                            trigger_data={
                                "type": "schedule",
                                "scheduled_at": now.isoformat(),
                            },
                        )
                        execution_ids.append(execution.id)

                        logger.info(
                            "scheduled_workflow_triggered",
                            workflow_id=str(workflow.id),
                            workflow_name=workflow.name,
                            execution_id=str(execution.id),
                        )

            except Exception as e:
                logger.error(
                    "scheduled_workflow_trigger_error",
                    workflow_id=str(workflow.id),
                    error=str(e),
                )

        return execution_ids

    def _should_run_scheduled_workflow(
        self,
        workflow: Workflow,
        now: datetime,
    ) -> bool:
        """Prueft ob ein Schedule-Workflow ausgefuehrt werden soll.

        Args:
            workflow: Workflow
            now: Aktuelle Zeit

        Returns:
            True wenn faellig
        """
        cron_expression = workflow.trigger_config.get("cron")
        if not cron_expression:
            return False

        try:
            # Timezone beruecksichtigen
            tz_name = workflow.trigger_config.get("timezone", "UTC")

            # Letzte Ausfuehrung pruefen
            last_run = workflow.last_executed_at
            if last_run:
                # Naechste geplante Ausfuehrung berechnen
                cron = croniter(cron_expression, last_run)
                next_run = cron.get_next(datetime)

                return now >= next_run
            else:
                # Noch nie ausgefuehrt - jetzt starten
                return True

        except Exception as e:
            logger.warning(
                "cron_parse_error",
                workflow_id=str(workflow.id),
                cron=cron_expression,
                error=str(e),
            )
            return False

    def get_next_run_time(
        self,
        cron_expression: str,
        from_time: Optional[datetime] = None,
    ) -> Optional[datetime]:
        """Berechnet die naechste Ausfuehrungszeit.

        Args:
            cron_expression: Cron-Ausdruck
            from_time: Startzeit (default: jetzt)

        Returns:
            Naechste Ausfuehrungszeit oder None
        """
        try:
            from_time = from_time or datetime.now(timezone.utc)
            cron = croniter(cron_expression, from_time)
            return cron.get_next(datetime)
        except Exception:
            return None

    def validate_cron_expression(
        self,
        cron_expression: str,
    ) -> tuple[bool, Optional[str]]:
        """Validiert einen Cron-Ausdruck.

        Args:
            cron_expression: Cron-Ausdruck

        Returns:
            Tuple aus (valid, error_message)
        """
        try:
            croniter(cron_expression)
            return True, None
        except Exception as e:
            return False, str(e)

    # =========================================================================
    # Manual Triggers
    # =========================================================================

    async def trigger_workflow_manually(
        self,
        workflow_id: UUID,
        user_id: UUID,
        document_id: Optional[UUID] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Optional[UUID]:
        """Loest einen Workflow manuell aus.

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID
            document_id: Optionale Dokument-ID
            variables: Optionale Variablen

        Returns:
            Execution-ID oder None
        """
        workflow = await self._get_workflow(workflow_id, user_id)
        if not workflow:
            return None

        # Manuelle Trigger muessen nicht aktiv sein
        # aber der Trigger-Typ muss manual sein oder es muss erlaubt sein
        allow_manual = workflow.trigger_config.get("allow_manual_trigger", True)
        if workflow.trigger_type != "manual" and not allow_manual:
            logger.warning(
                "manual_trigger_not_allowed",
                workflow_id=str(workflow_id),
            )
            return None

        if not self.execution_service:
            return None

        execution = await self.execution_service.start_execution(
            workflow_id=workflow_id,
            user_id=user_id,
            document_id=document_id,
            trigger_data={
                "type": "manual",
                "triggered_by": str(user_id),
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            },
            initial_variables=variables,
        )

        logger.info(
            "workflow_manually_triggered",
            workflow_id=str(workflow_id),
            user_id=str(user_id),
            execution_id=str(execution.id),
        )

        return execution.id

    # =========================================================================
    # Webhook Triggers
    # =========================================================================

    async def handle_webhook(
        self,
        webhook_path: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Optional[UUID]:
        """Verarbeitet einen eingehenden Webhook.

        Args:
            webhook_path: Webhook-Pfad
            payload: Webhook-Payload
            headers: HTTP-Headers

        Returns:
            Execution-ID oder None
        """
        # Workflow anhand des Pfads finden
        workflow = await self._find_workflow_by_webhook_path(webhook_path)
        if not workflow:
            logger.warning(
                "webhook_workflow_not_found",
                path=webhook_path,
            )
            return None

        # Signatur validieren falls konfiguriert
        secret = workflow.trigger_config.get("webhook_secret")
        if secret:
            signature = headers.get("X-Webhook-Signature") or headers.get("X-Hub-Signature-256")
            if not self._validate_webhook_signature(payload, secret, signature):
                logger.warning(
                    "webhook_signature_invalid",
                    workflow_id=str(workflow.id),
                )
                return None

        if not self.execution_service:
            return None

        execution = await self.execution_service.start_execution(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            trigger_data={
                "type": "webhook",
                "path": webhook_path,
                "payload": payload,
                "headers": {k: v for k, v in headers.items() if not k.lower().startswith("x-")},
            },
        )

        logger.info(
            "workflow_triggered_by_webhook",
            workflow_id=str(workflow.id),
            webhook_path=webhook_path,
            execution_id=str(execution.id),
        )

        return execution.id

    async def get_webhook_config(
        self,
        workflow_id: UUID,
        user_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Holt Webhook-Konfiguration fuer einen Workflow.

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID

        Returns:
            Webhook-Config oder None
        """
        workflow = await self._get_workflow(workflow_id, user_id)
        if not workflow or workflow.trigger_type != "webhook":
            return None

        webhook_path = workflow.trigger_config.get("webhook_path")
        if not webhook_path:
            # Generiere Pfad falls nicht vorhanden
            webhook_path = f"wf-{workflow_id.hex[:12]}"
            workflow.trigger_config["webhook_path"] = webhook_path
            await self.db.commit()

        return {
            "webhook_path": webhook_path,
            "webhook_url": f"/api/v1/workflows/trigger/{webhook_path}",
            "has_secret": bool(workflow.trigger_config.get("webhook_secret")),
        }

    async def regenerate_webhook_secret(
        self,
        workflow_id: UUID,
        user_id: UUID,
    ) -> Optional[str]:
        """Generiert ein neues Webhook-Secret.

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID

        Returns:
            Neues Secret oder None
        """
        workflow = await self._get_workflow(workflow_id, user_id)
        if not workflow or workflow.user_id != user_id:
            return None

        new_secret = secrets.token_hex(32)

        if workflow.trigger_config is None:
            workflow.trigger_config = {}

        workflow.trigger_config["webhook_secret"] = new_secret
        workflow.updated_at = datetime.now(timezone.utc)

        await self.db.commit()

        logger.info(
            "webhook_secret_regenerated",
            workflow_id=str(workflow_id),
        )

        return new_secret

    def _validate_webhook_signature(
        self,
        payload: Dict[str, Any],
        secret: str,
        signature: Optional[str],
    ) -> bool:
        """Validiert eine Webhook-Signatur.

        Args:
            payload: Webhook-Payload
            secret: Webhook-Secret
            signature: Empfangene Signatur

        Returns:
            True wenn gueltig
        """
        if not signature:
            return False

        import json

        payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
        expected = hmac.new(
            secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        # sha256=... Format (GitHub Style)
        if signature.startswith("sha256="):
            signature = signature[7:]

        return hmac.compare_digest(expected, signature)

    # =========================================================================
    # Condition Triggers
    # =========================================================================

    async def check_condition_triggers(
        self,
        document_id: UUID,
        user_id: UUID,
        changed_fields: Dict[str, tuple[Any, Any]],
    ) -> List[UUID]:
        """Prueft Condition-Triggers bei Feldaenderungen.

        Args:
            document_id: Dokument-ID
            user_id: User-ID
            changed_fields: Geaenderte Felder {field: (old_value, new_value)}

        Returns:
            Liste gestarteter Execution-IDs
        """
        if not changed_fields:
            return []

        # Matching Workflows finden
        workflows = await self._find_matching_workflows(
            trigger_type="condition",
            user_id=user_id,
        )

        if not workflows:
            return []

        execution_ids = []

        for workflow in workflows:
            # Trigger-Bedingungen pruefen
            watch_fields = workflow.trigger_config.get("watch_fields", [])

            # Pruefen ob eines der beobachteten Felder geaendert wurde
            triggered = False
            for field in watch_fields:
                if field in changed_fields:
                    triggered = True
                    break

            if not triggered:
                continue

            try:
                if self.execution_service:
                    execution = await self.execution_service.start_execution(
                        workflow_id=workflow.id,
                        user_id=user_id,
                        document_id=document_id,
                        trigger_data={
                            "type": "condition",
                            "changed_fields": {
                                k: {"old": v[0], "new": v[1]}
                                for k, v in changed_fields.items()
                            },
                        },
                    )
                    execution_ids.append(execution.id)

            except Exception as e:
                logger.error(
                    "condition_trigger_error",
                    workflow_id=str(workflow.id),
                    error=str(e),
                )

        return execution_ids

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _find_matching_workflows(
        self,
        trigger_type: str,
        user_id: UUID,
        event_type: Optional[str] = None,
    ) -> List[Workflow]:
        """Findet passende Workflows.

        Args:
            trigger_type: Trigger-Typ
            user_id: User-ID
            event_type: Optional Event-Typ fuer document_event

        Returns:
            Liste passender Workflows
        """
        conditions = [
            Workflow.trigger_type == trigger_type,
            Workflow.is_active == True,  # noqa: E712
            or_(
                Workflow.user_id == user_id,
                Workflow.trigger_config["scope"].astext == "global",
            ),
        ]

        query = select(Workflow).where(and_(*conditions))
        result = await self.db.execute(query)
        workflows = list(result.scalars().all())

        # Event-Type Filter (fuer document_event)
        if event_type and trigger_type == "document_event":
            workflows = [
                w for w in workflows
                if event_type in (w.trigger_config.get("events") or [])
            ]

        return workflows

    def _check_trigger_conditions(
        self,
        workflow: Workflow,
        document: Optional[Document],
        event_data: Optional[Dict[str, Any]],
    ) -> bool:
        """Prueft zusaetzliche Trigger-Bedingungen.

        Args:
            workflow: Workflow
            document: Dokument
            event_data: Event-Daten

        Returns:
            True wenn Bedingungen erfuellt
        """
        conditions = workflow.trigger_config.get("conditions")
        if not conditions:
            return True

        # TODO: Condition Evaluator integrieren
        # Fuer jetzt: einfache Filter

        # Document-Type Filter
        doc_types = conditions.get("document_types", [])
        if doc_types and document:
            if document.document_type not in doc_types:
                return False

        # File-Extension Filter
        extensions = conditions.get("file_extensions", [])
        if extensions and document:
            if document.file_extension not in extensions:
                return False

        # Folder Filter
        folder_ids = conditions.get("folder_ids", [])
        if folder_ids and document:
            if str(document.folder_id) not in folder_ids:
                return False

        return True

    async def _get_workflow(
        self,
        workflow_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Optional[Workflow]:
        """Laedt einen Workflow.

        Args:
            workflow_id: Workflow-ID
            user_id: Optionale User-ID

        Returns:
            Workflow oder None
        """
        query = select(Workflow).where(Workflow.id == workflow_id)

        if user_id:
            query = query.where(
                or_(
                    Workflow.user_id == user_id,
                    Workflow.is_template == True,  # noqa: E712
                )
            )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _find_workflow_by_webhook_path(
        self,
        webhook_path: str,
    ) -> Optional[Workflow]:
        """Findet Workflow anhand Webhook-Pfad.

        Args:
            webhook_path: Webhook-Pfad

        Returns:
            Workflow oder None
        """
        query = select(Workflow).where(
            and_(
                Workflow.trigger_type == "webhook",
                Workflow.is_active == True,  # noqa: E712
            )
        )

        result = await self.db.execute(query)
        workflows = list(result.scalars().all())

        # Pfad in trigger_config suchen
        for workflow in workflows:
            if workflow.trigger_config.get("webhook_path") == webhook_path:
                return workflow

        return None

    async def _load_document(
        self,
        document_id: UUID,
    ) -> Optional[Document]:
        """Laedt ein Dokument.

        Args:
            document_id: Dokument-ID

        Returns:
            Document oder None
        """
        query = select(Document).where(Document.id == document_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

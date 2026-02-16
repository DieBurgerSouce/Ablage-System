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
from app.core.safe_errors import safe_error_log, safe_error_detail

if TYPE_CHECKING:
    from app.services.workflow.workflow_execution_service import WorkflowExecutionService

logger = structlog.get_logger(__name__)


class WorkflowTriggerService:
    """Service für Workflow-Trigger.

    Verwaltet:
    - Document Event Triggers (created, processed, failed, deleted)
    - Schedule Triggers (Cron-basiert)
    - Condition Triggers (Feldänderungen)
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
            db: AsyncSession für Datenbankoperationen
            execution_service: WorkflowExecutionService für Ausführung
        """
        self.db = db
        self.execution_service = execution_service

    def set_execution_service(
        self,
        service: "WorkflowExecutionService",
    ) -> None:
        """Setzt den ExecutionService (für zirkuläre Abhängigkeiten).

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
            event_data: Zusätzliche Event-Daten

        Returns:
            Liste gestarteter Execution-IDs
        """
        logger.debug(
            "document_event_received",
            event_type=event_type,
            document_id=str(document_id),
        )

        # Dokument-Daten ZUERST laden für company_id (Multi-Tenant Isolation)
        document = await self._load_document(document_id)
        if not document:
            logger.warning(
                "document_not_found_for_event",
                document_id=str(document_id),
                event_type=event_type,
            )
            return []

        # SECURITY: company_id aus Document für Multi-Tenant Isolation
        if not document.company_id:
            logger.error(
                "document_missing_company_id",
                document_id=str(document_id),
            )
            return []

        # Matching Workflows finden MIT company_id Filter
        workflows = await self._find_matching_workflows(
            trigger_type="document_event",
            user_id=user_id,
            company_id=document.company_id,
            event_type=event_type,
        )

        if not workflows:
            return []

        execution_ids = []

        for workflow in workflows:
            # Trigger-Bedingungen prüfen
            if not self._check_trigger_conditions(workflow, document, event_data):
                continue

            # Workflow ausführen
            try:
                if self.execution_service:
                    # SECURITY: company_id MUSS an ExecutionService weitergegeben werden
                    execution = await self.execution_service.start_execution(
                        workflow_id=workflow.id,
                        user_id=user_id,
                        company_id=document.company_id,  # SECURITY: Multi-Tenant Isolation
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
                    **safe_error_log(e),
                )

        return execution_ids

    async def on_document_created(
        self,
        document_id: UUID,
        user_id: UUID,
    ) -> List[UUID]:
        """Shortcut für document_created Event.

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
        """Shortcut für document_processed Event.

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
        """Shortcut für document_failed Event.

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
        """Shortcut für status_changed Event.

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
        """Prüft und startet fällige Schedule-Workflows.

        Wird regelmäßig von Celery Beat aufgerufen.

        SECURITY: Jeder Workflow wird mit seiner eigenen company_id ausgeführt,
        um Multi-Tenant Isolation sicherzustellen. Workflows OHNE company_id
        werden übersprungen (Sicherheitsmassnahme).

        Returns:
            Liste gestarteter Execution-IDs
        """
        now = datetime.now(timezone.utc)

        # SECURITY: Nur aktive Schedule-Workflows MIT company_id laden
        # Workflows ohne company_id werden übersprungen (potentielles Sicherheitsrisiko)
        query = select(Workflow).where(
            and_(
                Workflow.trigger_type == "schedule",
                Workflow.is_active == True,  # noqa: E712
                Workflow.company_id.isnot(None),  # SECURITY: company_id PFLICHT
            )
        )

        result = await self.db.execute(query)
        workflows = list(result.scalars().all())

        execution_ids = []

        for workflow in workflows:
            try:
                # SECURITY: Nochmal validieren dass company_id vorhanden ist
                if not workflow.company_id:
                    logger.warning(
                        "scheduled_workflow_missing_company_id",
                        workflow_id=str(workflow.id),
                        workflow_name=workflow.name,
                    )
                    continue

                if self._should_run_scheduled_workflow(workflow, now):
                    if self.execution_service:
                        # SECURITY: company_id an ExecutionService weitergeben
                        execution = await self.execution_service.start_execution(
                            workflow_id=workflow.id,
                            user_id=workflow.user_id,
                            company_id=workflow.company_id,  # Multi-Tenant Isolation
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
                    **safe_error_log(e),
                )

        return execution_ids

    def _should_run_scheduled_workflow(
        self,
        workflow: Workflow,
        now: datetime,
    ) -> bool:
        """Prüft ob ein Schedule-Workflow ausgeführt werden soll.

        Args:
            workflow: Workflow
            now: Aktuelle Zeit

        Returns:
            True wenn fällig
        """
        cron_expression = workflow.trigger_config.get("cron")
        if not cron_expression:
            return False

        try:
            # Timezone berücksichtigen
            tz_name = workflow.trigger_config.get("timezone", "UTC")

            # Letzte Ausführung prüfen
            last_run = workflow.last_executed_at
            if last_run:
                # Nächste geplante Ausführung berechnen
                cron = croniter(cron_expression, last_run)
                next_run = cron.get_next(datetime)

                return now >= next_run
            else:
                # Noch nie ausgeführt - jetzt starten
                return True

        except Exception as e:
            logger.warning(
                "cron_parse_error",
                workflow_id=str(workflow.id),
                cron=cron_expression,
                **safe_error_log(e),
            )
            return False

    def get_next_run_time(
        self,
        cron_expression: str,
        from_time: Optional[datetime] = None,
    ) -> Optional[datetime]:
        """Berechnet die nächste Ausführungszeit.

        Args:
            cron_expression: Cron-Ausdruck
            from_time: Startzeit (default: jetzt)

        Returns:
            Nächste Ausführungszeit oder None
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
            return False, safe_error_detail(e, "Workflow-Trigger")

    # =========================================================================
    # Manual Triggers
    # =========================================================================

    async def trigger_workflow_manually(
        self,
        workflow_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Optional[UUID]:
        """Loest einen Workflow manuell aus.

        SECURITY: Wenn company_id angegeben wird, MUSS der Workflow zu dieser
        Company gehoeren (Multi-Tenant Isolation).

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID
            company_id: Company-ID für Multi-Tenant Validierung (empfohlen)
            document_id: Optionale Dokument-ID
            variables: Optionale Variablen

        Returns:
            Execution-ID oder None
        """
        workflow = await self._get_workflow(workflow_id, user_id, company_id)
        if not workflow:
            return None

        # Manuelle Trigger müssen nicht aktiv sein
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

        # SECURITY: company_id an ExecutionService weitergeben
        execution = await self.execution_service.start_execution(
            workflow_id=workflow_id,
            user_id=user_id,
            company_id=company_id,
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
        company_id: Optional[UUID] = None,
    ) -> Optional[UUID]:
        """Verarbeitet einen eingehenden Webhook.

        SECURITY: Webhook-Paths sind global unique. Wenn company_id angegeben wird,
        muss der gefundene Workflow zu dieser Company gehoeren.

        Args:
            webhook_path: Webhook-Pfad
            payload: Webhook-Payload
            headers: HTTP-Headers
            company_id: Optional Company-ID für Multi-Tenant Validierung

        Returns:
            Execution-ID oder None
        """
        # Workflow anhand des Pfads finden
        workflow = await self._find_workflow_by_webhook_path(webhook_path, company_id)
        if not workflow:
            logger.warning(
                "webhook_workflow_not_found",
                path=webhook_path,
            )
            return None

        # SECURITY: Workflow MUSS company_id haben für Ausführung
        if not workflow.company_id:
            logger.error(
                "webhook_workflow_missing_company_id",
                workflow_id=str(workflow.id),
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

        # SECURITY: company_id MUSS an ExecutionService weitergegeben werden
        execution = await self.execution_service.start_execution(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            company_id=workflow.company_id,  # SECURITY: Multi-Tenant Isolation
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
        company_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """Holt Webhook-Konfiguration für einen Workflow.

        SECURITY: Wenn company_id angegeben wird, MUSS der Workflow zu dieser
        Company gehoeren (Multi-Tenant Isolation).

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID
            company_id: Company-ID für Multi-Tenant Validierung (empfohlen)

        Returns:
            Webhook-Config oder None
        """
        workflow = await self._get_workflow(workflow_id, user_id, company_id)
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
        company_id: Optional[UUID] = None,
    ) -> Optional[str]:
        """Generiert ein neues Webhook-Secret.

        SECURITY: Wenn company_id angegeben wird, MUSS der Workflow zu dieser
        Company gehoeren (Multi-Tenant Isolation).

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID
            company_id: Company-ID für Multi-Tenant Isolation

        Returns:
            Neues Secret oder None
        """
        workflow = await self._get_workflow(workflow_id, user_id, company_id)
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
            True wenn gültig
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
        """Prüft Condition-Triggers bei Feldänderungen.

        Args:
            document_id: Dokument-ID
            user_id: User-ID
            changed_fields: Geänderte Felder {field: (old_value, new_value)}

        Returns:
            Liste gestarteter Execution-IDs
        """
        if not changed_fields:
            return []

        # SECURITY: Dokument laden für company_id (Multi-Tenant Isolation)
        document = await self._load_document(document_id)
        if not document or not document.company_id:
            logger.warning(
                "document_not_found_or_missing_company",
                document_id=str(document_id),
            )
            return []

        # Matching Workflows finden MIT company_id Filter
        workflows = await self._find_matching_workflows(
            trigger_type="condition",
            user_id=user_id,
            company_id=document.company_id,
        )

        if not workflows:
            return []

        execution_ids = []

        for workflow in workflows:
            # Trigger-Bedingungen prüfen
            watch_fields = workflow.trigger_config.get("watch_fields", [])

            # Prüfen ob eines der beobachteten Felder geändert wurde
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
                    **safe_error_log(e),
                )

        return execution_ids

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _find_matching_workflows(
        self,
        trigger_type: str,
        user_id: UUID,
        company_id: UUID,
        event_type: Optional[str] = None,
    ) -> List[Workflow]:
        """Findet passende Workflows mit Multi-Tenant Isolation.

        SECURITY: Filtert IMMER nach company_id für Multi-Tenant Isolation.
        Workflows ohne company_id (Templates) werden nur bei scope="global" berücksichtigt.

        Args:
            trigger_type: Trigger-Typ
            user_id: User-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant Isolation)
            event_type: Optional Event-Typ für document_event

        Returns:
            Liste passender Workflows
        """
        # SECURITY: company_id ist Pflicht für Multi-Tenant Isolation
        conditions = [
            Workflow.trigger_type == trigger_type,
            Workflow.is_active == True,  # noqa: E712
            or_(
                # Benutzer-spezifische Workflows der eigenen Company
                and_(
                    Workflow.user_id == user_id,
                    Workflow.company_id == company_id,
                ),
                # Globale Workflows der eigenen Company
                and_(
                    Workflow.trigger_config["scope"].astext == "global",
                    Workflow.company_id == company_id,
                ),
                # Company-weite Workflows (Templates, aber company_id muss matchen)
                and_(
                    Workflow.is_template == True,  # noqa: E712
                    Workflow.company_id == company_id,
                ),
            ),
        ]

        query = select(Workflow).where(and_(*conditions))
        result = await self.db.execute(query)
        workflows = list(result.scalars().all())

        # Event-Type Filter (für document_event)
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
        """Prüft zusätzliche Trigger-Bedingungen.

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

        # Einfache Filter (Legacy-Kompatibilität)
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

        # Erweiterte Bedingungen mit ConditionEvaluator
        advanced_conditions = conditions.get("rules")
        if advanced_conditions and document:
            from app.services.workflow.condition_evaluator import ConditionEvaluator

            from dataclasses import dataclass, field as dataclass_field
            from typing import Optional as Opt
            from uuid import UUID as UUIDType

            # Minimaler Trigger-Kontext für ConditionEvaluator
            @dataclass
            class TriggerContext:
                """Minimaler Kontext für Trigger-Bedingungsevaluierung."""
                document: Document
                event_data: Dict[str, Any] = dataclass_field(default_factory=dict)
                variables: Dict[str, Any] = dataclass_field(default_factory=dict)
                step_outputs: Dict[str, Any] = dataclass_field(default_factory=dict)
                document_id: Opt[UUIDType] = None
                execution_id: Opt[UUIDType] = None
                is_paused: bool = False

            trigger_context = TriggerContext(
                document=document,
                event_data=event_data or {},
                document_id=document.id,
            )

            evaluator = ConditionEvaluator()
            if not evaluator.evaluate(conditions, trigger_context):
                logger.debug(
                    "trigger_conditions_not_met",
                    workflow_id=str(workflow.id),
                    document_id=str(document.id) if document else None,
                )
                return False

        return True

    async def _get_workflow(
        self,
        workflow_id: UUID,
        user_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
    ) -> Optional[Workflow]:
        """Laedt einen Workflow mit Multi-Tenant Isolation.

        SECURITY: Wenn company_id angegeben wird, MUSS der Workflow zu dieser
        Company gehoeren. Templates werden nur zurückgegeben wenn sie zur
        gleichen Company gehoeren.

        Args:
            workflow_id: Workflow-ID
            user_id: Optionale User-ID
            company_id: Company-ID für Multi-Tenant Validierung (empfohlen)

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

        # SECURITY: company_id Filter für Multi-Tenant Isolation
        if company_id:
            query = query.where(Workflow.company_id == company_id)

        result = await self.db.execute(query)
        workflow = result.scalar_one_or_none()

        # SECURITY: Cross-Tenant Zugriff loggen
        if workflow is None and company_id:
            # Prüfen ob Workflow existiert aber andere Company hat
            check_query = select(Workflow.id, Workflow.company_id).where(
                Workflow.id == workflow_id
            )
            check_result = await self.db.execute(check_query)
            row = check_result.first()
            if row and row.company_id != company_id:
                logger.warning(
                    "cross_tenant_workflow_access_blocked",
                    workflow_id=str(workflow_id),
                    requested_company_id=str(company_id),
                    user_id=str(user_id) if user_id else None,
                )

        return workflow

    async def _find_workflow_by_webhook_path(
        self,
        webhook_path: str,
        company_id: Optional[UUID] = None,
    ) -> Optional[Workflow]:
        """Findet Workflow anhand Webhook-Pfad mit optionaler Multi-Tenant Isolation.

        SECURITY: Wenn company_id angegeben wird, MUSS der Workflow zu dieser Company gehoeren.
        Webhook-Paths sind global unique, aber die company_id Validierung schuetzt vor
        Cross-Tenant Zugriff wenn die API den company_id Parameter übergibt.

        Args:
            webhook_path: Webhook-Pfad
            company_id: Optional Company-ID für Multi-Tenant Validierung

        Returns:
            Workflow oder None
        """
        conditions = [
            Workflow.trigger_type == "webhook",
            Workflow.is_active == True,  # noqa: E712
        ]

        # SECURITY: company_id Filter wenn angegeben
        if company_id:
            conditions.append(Workflow.company_id == company_id)

        query = select(Workflow).where(and_(*conditions))
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

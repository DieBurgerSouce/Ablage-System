# -*- coding: utf-8 -*-
"""Workflow Step Executor.

Führt einzelne Workflow-Steps aus (20+ Action-Typen).
"""

from __future__ import annotations

import asyncio
import httpx
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

import structlog

from app.db.models import WorkflowStep
from app.services.workflow.condition_evaluator import ConditionEvaluator
from app.core.safe_errors import safe_error_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.services.workflow.workflow_execution_service import ExecutionContext

logger = structlog.get_logger(__name__)


@dataclass
class StepResult:
    """Ergebnis einer Step-Ausführung."""

    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retry_count: int = 0
    branch_result: Optional[str] = None


class WorkflowStepExecutor:
    """Executor für Workflow-Steps.

    Unterstützt 20+ Action-Typen:
    - Dokument-Aktionen: move_folder, assign_tags, assign_document_type, update_status
    - Benachrichtigungen: send_notification, send_email
    - Integration: call_webhook, http_request
    - Verarbeitung: start_ocr, ai_categorization, export_document
    - Workflow-Steuerung: delay, set_variable, condition, branch, parallel, loop
    - User-Aktionen: assign_user, create_task, request_approval
    """

    def __init__(
        self,
        db: "AsyncSession",
    ) -> None:
        """Initialisiert den StepExecutor.

        Args:
            db: AsyncSession für Datenbankoperationen
        """
        self.db = db
        self.condition_evaluator = ConditionEvaluator()

        # Action-Handler registrieren
        self._action_handlers: Dict[str, Any] = {
            # Dokument-Aktionen
            "move_folder": self._action_move_folder,
            "assign_tags": self._action_assign_tags,
            "assign_document_type": self._action_assign_document_type,
            "update_status": self._action_update_status,
            "delete_document": self._action_delete_document,

            # Benachrichtigungen
            "send_notification": self._action_send_notification,
            "send_email": self._action_send_email,

            # Integration
            "call_webhook": self._action_call_webhook,
            "http_request": self._action_http_request,

            # Verarbeitung
            "start_ocr": self._action_start_ocr,
            "ai_categorization": self._action_ai_categorization,
            "export_document": self._action_export_document,
            "duplicate_check": self._action_duplicate_check,

            # Workflow-Steuerung
            "delay": self._action_delay,
            "set_variable": self._action_set_variable,
            "log_message": self._action_log_message,

            # User-Aktionen
            "assign_user": self._action_assign_user,
            "create_task": self._action_create_task,
            "request_approval": self._action_request_approval,
        }

    async def execute_step(
        self,
        step: WorkflowStep,
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt einen Step aus.

        Args:
            step: WorkflowStep
            context: ExecutionContext

        Returns:
            StepResult
        """
        logger.debug(
            "executing_workflow_step",
            step_id=str(step.id),
            step_type=step.step_type,
            step_name=step.step_name,
        )

        try:
            if step.step_type == "condition":
                return await self._execute_condition(step, context)
            elif step.step_type == "branch":
                return await self._execute_branch(step, context)
            elif step.step_type == "delay":
                return await self._execute_delay(step, context)
            elif step.step_type == "parallel":
                return await self._execute_parallel(step, context)
            elif step.step_type == "loop":
                return await self._execute_loop(step, context)
            elif step.step_type == "action":
                return await self._execute_action(step, context)
            else:
                return StepResult(
                    success=False,
                    error=f"Unbekannter Step-Typ: {step.step_type}",
                )

        except Exception as e:
            logger.exception(
                "step_execution_error",
                step_id=str(step.id),
                **safe_error_log(e),
            )
            return StepResult(success=False, **safe_error_log(e))

    # =========================================================================
    # Step-Type Executors
    # =========================================================================

    async def _execute_condition(
        self,
        step: WorkflowStep,
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt eine Bedingung aus.

        Args:
            step: WorkflowStep
            context: ExecutionContext

        Returns:
            StepResult
        """
        conditions = step.config.get("conditions", {})
        result = self.condition_evaluator.evaluate(conditions, context)

        return StepResult(
            success=True,
            output={"result": result},
            branch_result="true" if result else "false",
        )

    async def _execute_branch(
        self,
        step: WorkflowStep,
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt eine Verzweigung aus.

        Args:
            step: WorkflowStep
            context: ExecutionContext

        Returns:
            StepResult
        """
        branches = step.config.get("branches", [])

        for branch in branches:
            conditions = branch.get("conditions", {})
            if self.condition_evaluator.evaluate(conditions, context):
                return StepResult(
                    success=True,
                    output={"branch": branch.get("name", "default")},
                    branch_result=branch.get("name", "default"),
                )

        # Default-Branch
        default = step.config.get("default_branch")
        return StepResult(
            success=True,
            output={"branch": default or "else"},
            branch_result=default or "else",
        )

    async def _execute_delay(
        self,
        step: WorkflowStep,
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt eine Verzögerung aus.

        Args:
            step: WorkflowStep
            context: ExecutionContext

        Returns:
            StepResult
        """
        delay_seconds = step.config.get("delay_seconds", 0)
        delay_until = step.config.get("delay_until")  # ISO datetime

        if delay_until:
            target_time = datetime.fromisoformat(delay_until)
            now = datetime.now(timezone.utc)
            delay_seconds = max(0, (target_time - now).total_seconds())

        if delay_seconds > 0:
            logger.info(
                "workflow_step_delay",
                step_id=str(step.id),
                delay_seconds=delay_seconds,
            )
            await asyncio.sleep(delay_seconds)

        return StepResult(
            success=True,
            output={"delayed_seconds": delay_seconds},
        )

    async def _execute_parallel(
        self,
        step: WorkflowStep,
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt parallele Steps aus.

        Args:
            step: WorkflowStep
            context: ExecutionContext

        Returns:
            StepResult
        """
        parallel_steps = step.config.get("steps", [])

        if not parallel_steps:
            return StepResult(success=True, output={"results": []})

        # Parallele Ausführung mit asyncio.gather()
        async def execute_parallel_action(action_config: Dict[str, Any]) -> Dict[str, Any]:
            """Führt eine einzelne Action aus und gibt das Ergebnis zurück."""
            action_type = action_config.get("action_type")
            action_name = action_config.get("name", action_type)

            if not action_type:
                return {
                    "name": action_name,
                    "success": False,
                    "error": "Kein Action-Typ definiert",
                }

            handler = self._action_handlers.get(action_type)
            if not handler:
                return {
                    "name": action_name,
                    "success": False,
                    "error": f"Unbekannter Action-Typ: {action_type}",
                }

            try:
                result = await handler(action_config, context)
                return {
                    "name": action_name,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                }
            except Exception as e:
                logger.exception(
                    "parallel_step_failed",
                    action_type=action_type,
                    **safe_error_log(e),
                )
                return {
                    "name": action_name,
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                }

        # Alle Actions parallel ausführen
        logger.info(
            "executing_parallel_steps",
            step_id=str(step.id),
            parallel_count=len(parallel_steps),
        )

        results = await asyncio.gather(
            *[execute_parallel_action(action_config) for action_config in parallel_steps],
            return_exceptions=True,
        )

        # Ergebnisse verarbeiten
        processed_results: List[Dict[str, Any]] = []
        all_success = True

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "name": parallel_steps[i].get("name", f"step_{i}"),
                    "success": False,
                    "error": str(result),
                })
                all_success = False
            else:
                processed_results.append(result)
                if not result.get("success", False):
                    all_success = False

        return StepResult(
            success=all_success,
            output={"results": processed_results},
            error=None if all_success else "Ein oder mehrere parallele Schritte fehlgeschlagen",
        )

    async def _execute_loop(
        self,
        step: WorkflowStep,
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt eine Schleife aus.

        Args:
            step: WorkflowStep
            context: ExecutionContext

        Returns:
            StepResult
        """
        loop_type = step.config.get("loop_type", "count")
        max_iterations = step.config.get("max_iterations", 10)

        iterations = 0

        if loop_type == "count":
            count = step.config.get("count", 1)
            iterations = min(count, max_iterations)

        elif loop_type == "while":
            conditions = step.config.get("conditions", {})
            while iterations < max_iterations:
                if not self.condition_evaluator.evaluate(conditions, context):
                    break
                iterations += 1

        elif loop_type == "for_each":
            items_field = step.config.get("items_field")
            items = self.condition_evaluator.get_field_value(items_field, context)
            if isinstance(items, list):
                iterations = min(len(items), max_iterations)

        return StepResult(
            success=True,
            output={"iterations": iterations},
        )

    async def _execute_action(
        self,
        step: WorkflowStep,
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt eine Action aus.

        Args:
            step: WorkflowStep
            context: ExecutionContext

        Returns:
            StepResult
        """
        action_type = step.config.get("action_type")

        if not action_type:
            return StepResult(
                success=False,
                error="Kein Action-Typ definiert",
            )

        handler = self._action_handlers.get(action_type)

        if not handler:
            return StepResult(
                success=False,
                error=f"Unbekannter Action-Typ: {action_type}",
            )

        return await handler(step.config, context)

    # =========================================================================
    # Document Actions
    # =========================================================================

    async def _action_move_folder(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Verschiebt Dokument in anderen Ordner.

        SECURITY: Validiert company_id vor Änderung (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        from app.db.models import Document
        from sqlalchemy import update

        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "move_folder")
        if not is_valid:
            return error_result  # type: ignore

        target_folder_id = config.get("folder_id")
        if not target_folder_id:
            return StepResult(success=False, error="Kein Zielordner angegeben")

        stmt = (
            update(Document)
            .where(Document.id == context.document_id)
            .values(folder_id=UUID(target_folder_id))
        )

        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(
            "workflow_action_move_folder",
            document_id=str(context.document_id),
            folder_id=target_folder_id,
        )

        return StepResult(
            success=True,
            output={"folder_id": target_folder_id},
        )

    async def _action_assign_tags(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Weist Dokument Tags zu.

        SECURITY: Validiert company_id vor Änderung (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        from app.db.models import Tag, document_tags
        from sqlalchemy import select, insert

        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "assign_tags")
        if not is_valid:
            return error_result  # type: ignore

        tag_ids = config.get("tag_ids", [])
        tag_names = config.get("tag_names", [])
        append_mode = config.get("append", True)

        assigned_tags = []

        # Tags nach Namen finden/erstellen
        for tag_name in tag_names:
            query = select(Tag).where(Tag.name == tag_name)
            result = await self.db.execute(query)
            tag = result.scalar_one_or_none()

            if tag:
                tag_ids.append(str(tag.id))
            else:
                # Tag erstellen falls nicht vorhanden
                auto_create = config.get("auto_create_tags", True)
                if auto_create:
                    new_tag = Tag(
                        name=tag_name[:50],  # Max 50 Zeichen
                        description=f"Automatisch erstellt durch Workflow",
                        color=config.get("default_tag_color", "bg-gray-500"),
                        is_system=False,
                        is_active=True,
                    )
                    self.db.add(new_tag)
                    await self.db.flush()  # ID generieren
                    tag_ids.append(str(new_tag.id))
                    logger.info(
                        "workflow_tag_created",
                        tag_name=tag_name,
                        tag_id=str(new_tag.id),
                    )

        # Bestehende Tags entfernen falls append=False
        if not append_mode:
            from sqlalchemy import delete
            stmt = delete(document_tags).where(
                document_tags.c.document_id == context.document_id
            )
            await self.db.execute(stmt)

        # Tags zuweisen
        for tag_id in tag_ids:
            try:
                stmt = insert(document_tags).values(
                    document_id=context.document_id,
                    tag_id=UUID(tag_id),
                )
                await self.db.execute(stmt)
                assigned_tags.append(tag_id)
            except Exception:
                # Tag bereits zugewiesen
                pass

        await self.db.commit()

        return StepResult(
            success=True,
            output={"assigned_tags": assigned_tags},
        )

    async def _action_assign_document_type(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Weist Dokumenttyp zu.

        SECURITY: Validiert company_id vor Änderung (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        from app.db.models import Document
        from sqlalchemy import update

        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "assign_document_type")
        if not is_valid:
            return error_result  # type: ignore

        document_type = config.get("document_type")
        if not document_type:
            return StepResult(success=False, error="Kein Dokumenttyp angegeben")

        stmt = (
            update(Document)
            .where(Document.id == context.document_id)
            .values(document_type=document_type)
        )

        await self.db.execute(stmt)
        await self.db.commit()

        return StepResult(
            success=True,
            output={"document_type": document_type},
        )

    async def _action_update_status(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Aktualisiert Dokument-Status.

        SECURITY: Validiert company_id vor Änderung (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        from app.db.models import Document
        from sqlalchemy import update

        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "update_status")
        if not is_valid:
            return error_result  # type: ignore

        status = config.get("status")
        if not status:
            return StepResult(success=False, error="Kein Status angegeben")

        stmt = (
            update(Document)
            .where(Document.id == context.document_id)
            .values(status=status)
        )

        await self.db.execute(stmt)
        await self.db.commit()

        return StepResult(
            success=True,
            output={"status": status},
        )

    async def _action_delete_document(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Löscht ein Dokument (Soft-Delete).

        SECURITY: Validiert company_id vor Änderung (Multi-Tenant Isolation).
        KRITISCH: Ohne Validierung könnte Cross-Tenant Deletion möglich sein!

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        from app.db.models import Document
        from sqlalchemy import update

        # SECURITY: Multi-Tenant Validierung - KRITISCH bei Delete!
        is_valid, error_result = await self._validate_document_company(context, "delete_document")
        if not is_valid:
            return error_result  # type: ignore

        soft_delete = config.get("soft_delete", True)

        if soft_delete:
            stmt = (
                update(Document)
                .where(Document.id == context.document_id)
                .values(
                    is_deleted=True,
                    deleted_at=datetime.now(timezone.utc),
                )
            )
            await self.db.execute(stmt)
        else:
            # Hard delete - nur mit expliziter Berechtigung
            from sqlalchemy import delete
            stmt = delete(Document).where(Document.id == context.document_id)
            await self.db.execute(stmt)

        await self.db.commit()

        return StepResult(
            success=True,
            output={"deleted": True, "soft_delete": soft_delete},
        )

    # =========================================================================
    # Notification Actions
    # =========================================================================

    async def _action_send_notification(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Sendet eine In-App Benachrichtigung.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        try:
            from app.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)

            title = self._interpolate_variables(config.get("title", ""), context)
            message = self._interpolate_variables(config.get("message", ""), context)
            user_ids = config.get("user_ids", [context.user_id])
            notification_type = config.get("type", "workflow")

            sent_count = 0
            for user_id in user_ids:
                await notification_service.create_notification(
                    user_id=UUID(str(user_id)),
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    data={
                        "workflow_id": str(context.workflow_id),
                        "execution_id": str(context.execution_id),
                        "document_id": str(context.document_id) if context.document_id else None,
                    },
                )
                sent_count += 1

            return StepResult(
                success=True,
                output={"sent_count": sent_count},
            )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    async def _action_send_email(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Sendet eine E-Mail.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        try:
            from app.services.email_service import EmailService

            email_service = EmailService()

            to_addresses = config.get("to", [])
            subject = self._interpolate_variables(config.get("subject", ""), context)
            body = self._interpolate_variables(config.get("body", ""), context)
            html_body = self._interpolate_variables(config.get("html_body", ""), context)
            template = config.get("template")

            await email_service.send_email(
                to=to_addresses,
                subject=subject,
                body=body,
                html_body=html_body if html_body else None,
                template=template,
            )

            return StepResult(
                success=True,
                output={"sent_to": to_addresses},
            )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    # =========================================================================
    # Integration Actions
    # =========================================================================

    async def _action_call_webhook(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Ruft einen Webhook auf.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        try:
            from app.services.webhook_dispatcher import WebhookDispatcher

            dispatcher = WebhookDispatcher()

            url = config.get("url")
            event_type = config.get("event_type", "workflow.step")
            payload = config.get("payload", {})

            # Context-Daten hinzufuegen
            payload["workflow_id"] = str(context.workflow_id)
            payload["execution_id"] = str(context.execution_id)
            if context.document_id:
                payload["document_id"] = str(context.document_id)

            success = await dispatcher.dispatch_to_url(
                url=url,
                event_type=event_type,
                payload=payload,
            )

            return StepResult(
                success=success,
                output={"url": url, "dispatched": success},
            )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    async def _action_http_request(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt einen HTTP-Request aus.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        url = config.get("url")
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        body = config.get("body")
        timeout = config.get("timeout", 30)

        # Variable interpolation
        url = self._interpolate_variables(url, context)
        if body and isinstance(body, str):
            body = self._interpolate_variables(body, context)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body if isinstance(body, dict) else None,
                    content=body if isinstance(body, str) else None,
                )

                return StepResult(
                    success=response.is_success,
                    output={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text[:1000],  # Truncate
                    },
                    error=None if response.is_success else f"HTTP {response.status_code}",
                )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    # =========================================================================
    # Processing Actions
    # =========================================================================

    async def _action_start_ocr(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Startet OCR-Verarbeitung.

        SECURITY: Validiert company_id vor Verarbeitung (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "start_ocr")
        if not is_valid:
            return error_result  # type: ignore

        backend = config.get("backend", "auto")
        priority = config.get("priority", "normal")

        try:
            # Celery Task starten
            from app.workers.tasks.ocr_tasks import process_document_task

            task = process_document_task.delay(
                document_id=str(context.document_id),
                backend=backend,
                priority=priority,
            )

            return StepResult(
                success=True,
                output={
                    "task_id": task.id,
                    "backend": backend,
                },
            )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    async def _action_ai_categorization(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Führt KI-Kategorisierung durch.

        SECURITY: Validiert company_id vor Verarbeitung (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "ai_categorization")
        if not is_valid:
            return error_result  # type: ignore

        try:
            from app.services.ai.auto_categorization_service import AutoCategorizationService

            categorization_service = AutoCategorizationService(self.db)

            result = await categorization_service.categorize_document(
                document_id=context.document_id,
            )

            return StepResult(
                success=True,
                output={
                    "category": result.get("category"),
                    "confidence": result.get("confidence"),
                    "suggestions": result.get("suggestions", []),
                },
            )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    async def _action_export_document(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Exportiert ein Dokument.

        SECURITY: Validiert company_id vor Export (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "export_document")
        if not is_valid:
            return error_result  # type: ignore

        export_format = config.get("format", "pdf")
        destination = config.get("destination")

        try:
            from app.services.document_services.export_service import DocumentExportService

            export_service = DocumentExportService(self.db)

            result = await export_service.export_document(
                document_id=context.document_id,
                format=export_format,
                destination=destination,
            )

            return StepResult(
                success=True,
                output={
                    "export_path": result.get("path"),
                    "format": export_format,
                },
            )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    async def _action_duplicate_check(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Prüft auf Duplikate.

        SECURITY: Validiert company_id vor Check (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "duplicate_check")
        if not is_valid:
            return error_result  # type: ignore

        try:
            from app.services.ai.duplicate_detection_service import DuplicateDetectionService

            duplicate_service = DuplicateDetectionService(self.db)

            result = await duplicate_service.check_for_duplicates(
                document_id=context.document_id,
            )

            return StepResult(
                success=True,
                output={
                    "is_duplicate": result.get("is_duplicate", False),
                    "duplicate_of": result.get("duplicate_of"),
                    "similarity_score": result.get("similarity_score"),
                },
            )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    # =========================================================================
    # Workflow Control Actions
    # =========================================================================

    async def _action_delay(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Verzögerungs-Action.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        delay_seconds = config.get("delay_seconds", 0)
        await asyncio.sleep(delay_seconds)

        return StepResult(
            success=True,
            output={"delayed_seconds": delay_seconds},
        )

    async def _action_set_variable(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Setzt eine Workflow-Variable.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        variable_name = config.get("name")
        variable_value = config.get("value")

        if not variable_name:
            return StepResult(success=False, error="Kein Variablenname angegeben")

        # Variable interpolation
        if isinstance(variable_value, str):
            variable_value = self._interpolate_variables(variable_value, context)

        context.variables[variable_name] = variable_value

        return StepResult(
            success=True,
            output={variable_name: variable_value},
        )

    async def _action_log_message(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Loggt eine Nachricht.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        message = self._interpolate_variables(config.get("message", ""), context)
        level = config.get("level", "info")

        log_func = getattr(logger, level, logger.info)
        log_func(
            "workflow_log_message",
            message=message,
            workflow_id=str(context.workflow_id),
            execution_id=str(context.execution_id),
        )

        return StepResult(
            success=True,
            output={"message": message, "level": level},
        )

    # =========================================================================
    # User Actions
    # =========================================================================

    async def _action_assign_user(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Weist Dokument einem User zu.

        SECURITY: Validiert company_id vor Änderung (Multi-Tenant Isolation).

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        from app.db.models import Document
        from sqlalchemy import update

        # SECURITY: Multi-Tenant Validierung
        is_valid, error_result = await self._validate_document_company(context, "assign_user")
        if not is_valid:
            return error_result  # type: ignore

        user_id = config.get("user_id")
        if not user_id:
            return StepResult(success=False, error="Kein User angegeben")

        stmt = (
            update(Document)
            .where(Document.id == context.document_id)
            .values(assigned_user_id=UUID(user_id))
        )

        await self.db.execute(stmt)
        await self.db.commit()

        return StepResult(
            success=True,
            output={"assigned_user_id": user_id},
        )

    async def _action_create_task(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Erstellt einen Task.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        title = self._interpolate_variables(config.get("title", ""), context)
        description = self._interpolate_variables(config.get("description", ""), context)
        assignee_id = config.get("assignee_id")
        due_date = config.get("due_date")
        priority = config.get("priority", "normal")

        try:
            from app.services.task_service import TaskService

            task_service = TaskService(self.db)

            task = await task_service.create_task(
                title=title,
                description=description,
                assignee_id=UUID(assignee_id) if assignee_id else None,
                created_by_id=context.user_id,
                document_id=context.document_id,
                due_date=due_date,
                priority=priority,
            )

            return StepResult(
                success=True,
                output={"task_id": str(task.id)},
            )

        except Exception as e:
            return StepResult(success=False, **safe_error_log(e))

    async def _action_request_approval(
        self,
        config: Dict[str, Any],
        context: "ExecutionContext",
    ) -> StepResult:
        """Fordert eine Genehmigung an.

        Args:
            config: Action-Konfiguration
            context: ExecutionContext

        Returns:
            StepResult
        """
        approver_ids = config.get("approver_ids", [])
        title = self._interpolate_variables(config.get("title", "Genehmigung erforderlich"), context)
        message = self._interpolate_variables(config.get("message", ""), context)

        # Benachrichtigungen an Genehmiger senden
        from app.services.notification_service import NotificationService

        notification_service = NotificationService(self.db)

        for approver_id in approver_ids:
            await notification_service.create_notification(
                user_id=UUID(approver_id),
                title=title,
                message=message,
                notification_type="approval_request",
                data={
                    "workflow_id": str(context.workflow_id),
                    "execution_id": str(context.execution_id),
                    "document_id": str(context.document_id) if context.document_id else None,
                    "requires_response": True,
                },
            )

        return StepResult(
            success=True,
            output={
                "approval_requested": True,
                "approvers": approver_ids,
            },
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _validate_document_company(
        self,
        context: "ExecutionContext",
        action_name: str,
    ) -> tuple[bool, Optional[StepResult]]:
        """Validiert dass Dokument zur gleichen Company gehoert wie der Workflow.

        SECURITY: Multi-Tenant Isolation - verhindert Cross-Tenant Zugriffe.

        Args:
            context: ExecutionContext mit document_id und company_id
            action_name: Name der Action für Logging

        Returns:
            Tuple (is_valid, error_result):
                - (True, None) wenn valid
                - (False, StepResult) wenn invalid (StepResult enthält Fehler)
        """
        if not context.document_id:
            return False, StepResult(success=False, error="Kein Dokument im Kontext")

        if not context.company_id:
            # Keine company_id im Context = kein Multi-Tenant Check möglich
            # Dies ist ein Legacy-Fall oder System-Workflow
            return True, None

        from app.db.models import Document

        from sqlalchemy import select

        doc_query = select(Document.company_id).where(Document.id == context.document_id)
        doc_result = await self.db.execute(doc_query)
        doc_company_id = doc_result.scalar_one_or_none()

        if doc_company_id is None:
            # Dokument nicht gefunden
            logger.warning(
                "workflow_document_not_found",
                action=action_name,
                document_id=str(context.document_id),
            )
            return False, StepResult(success=False, error="Dokument nicht gefunden")

        if doc_company_id != context.company_id:
            logger.warning(
                "cross_tenant_document_action_blocked",
                action=action_name,
                document_id=str(context.document_id),
                workflow_company_id=str(context.company_id),
                document_company_id=str(doc_company_id),
            )
            return False, StepResult(success=False, error="Dokument nicht gefunden")

        return True, None

    def _interpolate_variables(
        self,
        text: str,
        context: "ExecutionContext",
    ) -> str:
        """Ersetzt Variablen-Platzhalter im Text.

        Args:
            text: Text mit Platzhaltern
            context: ExecutionContext

        Returns:
            Text mit ersetzten Variablen
        """
        if not text:
            return text

        import re

        def replace_var(match: re.Match) -> str:
            var_path = match.group(1)
            value = self.condition_evaluator.get_field_value(var_path, context)
            return str(value) if value is not None else ""

        # Format: {{variable.path}} oder ${variable.path}
        result = re.sub(r"\{\{([^}]+)\}\}", replace_var, text)
        result = re.sub(r"\$\{([^}]+)\}", replace_var, result)

        return result

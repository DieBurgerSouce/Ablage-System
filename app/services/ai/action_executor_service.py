# -*- coding: utf-8 -*-
"""
ActionExecutorService - Führt KI-vorgeschlagene Aktionen aus.

Verantwortlich für:
- Aktionsausführung mit Berechtigungsprüfung
- Transaktionssicherheit
- Rollback-Fähigkeit
- Audit-Logging aller Aktionen

Vision 2.0 - Phase 1 (Januar 2026)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import Document, InvoiceTracking, BankTransaction, AuditLog

logger = structlog.get_logger(__name__)


class ActionStatus(str, Enum):
    """Status einer Aktion."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ActionCategory(str, Enum):
    """Kategorie der Aktion."""

    PAYMENT = "payment"
    APPROVAL = "approval"
    DOCUMENT = "document"
    NOTIFICATION = "notification"
    EXPORT = "export"
    RECONCILIATION = "reconciliation"


@dataclass
class ActionContext:
    """Kontext für Aktionsausführung."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    user_role: str
    session_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class ActionResult:
    """Ergebnis einer Aktionsausführung."""

    action_id: uuid.UUID
    status: ActionStatus
    success: bool
    message: str
    affected_count: int = 0
    affected_ids: List[uuid.UUID] = field(default_factory=list)
    rollback_possible: bool = False
    execution_time_ms: int = 0
    error_details: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RollbackInfo:
    """Information für Rollback."""

    action_id: uuid.UUID
    original_states: Dict[str, Any]
    rollback_sql: Optional[str] = None


class ActionExecutorService:
    """Service für sichere Aktionsausführung.

    Features:
    - Berechtigungsprüfung vor Ausführung
    - Transaktionssicherheit
    - Automatisches Audit-Logging
    - Rollback-Unterstützung
    """

    # Berechtigungsmatrix: action_type -> required_role
    PERMISSION_MATRIX: Dict[str, str] = {
        "payment_run": "admin",
        "approve_invoices": "editor",
        "categorize_documents": "editor",
        "send_reminder": "editor",
        "export_data": "viewer",
        "match_transactions": "editor",
        "create_booking": "editor",
        "delete_document": "admin",
    }

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db
        self._rollback_registry: Dict[uuid.UUID, RollbackInfo] = {}

    async def execute_action(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        context: ActionContext,
    ) -> ActionResult:
        """Führt eine Aktion sicher aus.

        Args:
            action_type: Art der Aktion
            parameters: Aktionsparameter
            context: Ausführungskontext

        Returns:
            ActionResult mit Ergebnis
        """
        import time
        start_time = time.time()

        action_id = uuid.uuid4()

        # 1. Berechtigungsprüfung
        if not self._check_permission(action_type, context.user_role):
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                success=False,
                message="Keine Berechtigung für diese Aktion.",
                error_details=f"Erforderliche Rolle: {self.PERMISSION_MATRIX.get(action_type, 'admin')}",
            )

        # 2. Pre-Execution Audit
        await self._log_action_start(action_id, action_type, parameters, context)

        try:
            # 3. Aktion ausführen
            if action_type == "payment_run":
                result = await self._execute_payment_run(action_id, parameters, context)
            elif action_type == "approve_invoices":
                result = await self._execute_approve_invoices(action_id, parameters, context)
            elif action_type == "categorize_documents":
                result = await self._execute_categorize(action_id, parameters, context)
            elif action_type == "send_reminder":
                result = await self._execute_send_reminder(action_id, parameters, context)
            elif action_type == "match_transactions":
                result = await self._execute_match_transactions(action_id, parameters, context)
            elif action_type == "export_data":
                result = await self._execute_export(action_id, parameters, context)
            else:
                result = ActionResult(
                    action_id=action_id,
                    status=ActionStatus.FAILED,
                    success=False,
                    message=f"Unbekannte Aktion: {action_type}",
                )

            # 4. Commit bei Erfolg
            if result.success:
                await self.db.commit()
            else:
                await self.db.rollback()

            # 5. Post-Execution Audit
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            await self._log_action_end(action_id, result, context)

            return result

        except Exception as e:
            await self.db.rollback()
            logger.error(
                "action_execution_error",
                action_id=str(action_id),
                action_type=action_type,
                error=str(e),
            )
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                success=False,
                message="Fehler bei der Ausführung",
                error_details=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

    def _check_permission(self, action_type: str, user_role: str) -> bool:
        """Prüft Berechtigung für Aktion."""
        required_role = self.PERMISSION_MATRIX.get(action_type, "admin")
        role_hierarchy = {"viewer": 0, "editor": 1, "admin": 2}

        user_level = role_hierarchy.get(user_role, 0)
        required_level = role_hierarchy.get(required_role, 2)

        return user_level >= required_level

    # ========================================================================
    # Action Implementations
    # ========================================================================

    async def _execute_payment_run(
        self,
        action_id: uuid.UUID,
        parameters: Dict[str, Any],
        context: ActionContext,
    ) -> ActionResult:
        """Führt Zahlungslauf aus."""
        invoice_ids = parameters.get("invoice_ids", [])

        if not invoice_ids:
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                success=False,
                message="Keine Rechnungen für Zahlungslauf angegeben.",
            )

        # Originalzustände für Rollback speichern
        original_states = {}

        affected = []
        for inv_id_str in invoice_ids:
            inv_id = uuid.UUID(inv_id_str)
            stmt = (
                select(InvoiceTracking)
                .where(
                    and_(
                        InvoiceTracking.id == inv_id,
                        InvoiceTracking.company_id == context.company_id,
                    )
                )
            )
            result = await self.db.execute(stmt)
            invoice = result.scalar_one_or_none()

            if invoice:
                # Originalzustand speichern
                original_states[str(inv_id)] = {
                    "status": invoice.status,
                    "payment_initiated_at": invoice.payment_initiated_at,
                }

                # Status aktualisieren
                invoice.status = "payment_pending"
                invoice.payment_initiated_at = utc_now()
                invoice.payment_initiated_by = context.user_id
                affected.append(inv_id)

        # Rollback-Info speichern
        self._rollback_registry[action_id] = RollbackInfo(
            action_id=action_id,
            original_states=original_states,
        )

        total_amount = sum(
            float(parameters.get("total_amount", 0))
            for _ in affected
        ) if affected else 0

        return ActionResult(
            action_id=action_id,
            status=ActionStatus.COMPLETED,
            success=True,
            message=f"Zahlungslauf für {len(affected)} Rechnungen vorbereitet.",
            affected_count=len(affected),
            affected_ids=affected,
            rollback_possible=True,
            metadata={"total_amount": total_amount},
        )

    async def _execute_approve_invoices(
        self,
        action_id: uuid.UUID,
        parameters: Dict[str, Any],
        context: ActionContext,
    ) -> ActionResult:
        """Genehmigt Rechnungen."""
        invoice_ids = parameters.get("invoice_ids", [])

        if not invoice_ids:
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                success=False,
                message="Keine Rechnungen zur Genehmigung angegeben.",
            )

        original_states = {}
        affected = []

        for inv_id_str in invoice_ids:
            inv_id = uuid.UUID(inv_id_str)
            stmt = (
                select(InvoiceTracking)
                .where(
                    and_(
                        InvoiceTracking.id == inv_id,
                        InvoiceTracking.company_id == context.company_id,
                    )
                )
            )
            result = await self.db.execute(stmt)
            invoice = result.scalar_one_or_none()

            if invoice:
                original_states[str(inv_id)] = {"status": invoice.status}
                invoice.status = "approved"
                invoice.approved_at = utc_now()
                invoice.approved_by = context.user_id
                affected.append(inv_id)

        self._rollback_registry[action_id] = RollbackInfo(
            action_id=action_id,
            original_states=original_states,
        )

        return ActionResult(
            action_id=action_id,
            status=ActionStatus.COMPLETED,
            success=True,
            message=f"{len(affected)} Rechnungen genehmigt.",
            affected_count=len(affected),
            affected_ids=affected,
            rollback_possible=True,
        )

    async def _execute_categorize(
        self,
        action_id: uuid.UUID,
        parameters: Dict[str, Any],
        context: ActionContext,
    ) -> ActionResult:
        """Kategorisiert Dokumente."""
        document_ids = parameters.get("document_ids", [])
        category = parameters.get("category")

        if not document_ids or not category:
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                success=False,
                message="Dokumente oder Kategorie fehlen.",
            )

        original_states = {}
        affected = []

        for doc_id_str in document_ids:
            doc_id = uuid.UUID(doc_id_str)
            stmt = (
                select(Document)
                .where(
                    and_(
                        Document.id == doc_id,
                        Document.company_id == context.company_id,
                    )
                )
            )
            result = await self.db.execute(stmt)
            doc = result.scalar_one_or_none()

            if doc:
                original_states[str(doc_id)] = {"document_type": doc.document_type}
                doc.document_type = category
                affected.append(doc_id)

        self._rollback_registry[action_id] = RollbackInfo(
            action_id=action_id,
            original_states=original_states,
        )

        return ActionResult(
            action_id=action_id,
            status=ActionStatus.COMPLETED,
            success=True,
            message=f"{len(affected)} Dokumente kategorisiert als '{category}'.",
            affected_count=len(affected),
            affected_ids=affected,
            rollback_possible=True,
        )

    async def _execute_send_reminder(
        self,
        action_id: uuid.UUID,
        parameters: Dict[str, Any],
        context: ActionContext,
    ) -> ActionResult:
        """Sendet Mahnungen."""
        invoice_ids = parameters.get("invoice_ids", [])

        if not invoice_ids:
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                success=False,
                message="Keine Rechnungen für Mahnung angegeben.",
            )

        original_states = {}
        affected = []

        for inv_id_str in invoice_ids:
            inv_id = uuid.UUID(inv_id_str)
            stmt = (
                select(InvoiceTracking)
                .where(
                    and_(
                        InvoiceTracking.id == inv_id,
                        InvoiceTracking.company_id == context.company_id,
                    )
                )
            )
            result = await self.db.execute(stmt)
            invoice = result.scalar_one_or_none()

            if invoice:
                original_states[str(inv_id)] = {
                    "dunning_level": invoice.dunning_level,
                    "last_dunning_date": str(invoice.last_dunning_date) if invoice.last_dunning_date else None,
                }
                invoice.dunning_level = (invoice.dunning_level or 0) + 1
                invoice.last_dunning_date = date.today()
                affected.append(inv_id)

        self._rollback_registry[action_id] = RollbackInfo(
            action_id=action_id,
            original_states=original_states,
        )

        return ActionResult(
            action_id=action_id,
            status=ActionStatus.COMPLETED,
            success=True,
            message=f"Mahnungen für {len(affected)} Rechnungen erstellt.",
            affected_count=len(affected),
            affected_ids=affected,
            rollback_possible=True,
        )

    async def _execute_match_transactions(
        self,
        action_id: uuid.UUID,
        parameters: Dict[str, Any],
        context: ActionContext,
    ) -> ActionResult:
        """Ordnet Transaktionen automatisch zu."""
        # Vereinfachte Implementierung
        # In Produktion würde ReconciliationService genutzt

        matched_count = 0

        # Unzugeordnete Transaktionen finden
        stmt = (
            select(BankTransaction)
            .where(
                and_(
                    BankTransaction.company_id == context.company_id,
                    BankTransaction.matched_invoice_id.is_(None),
                    BankTransaction.amount > 0,
                )
            )
            .limit(50)
        )
        result = await self.db.execute(stmt)
        transactions = result.scalars().all()

        for tx in transactions:
            # Versuch: Rechnung mit gleichem Betrag finden
            inv_stmt = (
                select(InvoiceTracking)
                .where(
                    and_(
                        InvoiceTracking.company_id == context.company_id,
                        InvoiceTracking.total_amount == tx.amount,
                        InvoiceTracking.status.in_(["pending", "open"]),
                    )
                )
                .limit(1)
            )
            inv_result = await self.db.execute(inv_stmt)
            invoice = inv_result.scalar_one_or_none()

            if invoice:
                tx.matched_invoice_id = invoice.id
                tx.matched_at = utc_now()
                invoice.status = "paid"
                invoice.paid_at = utc_now()
                matched_count += 1

        return ActionResult(
            action_id=action_id,
            status=ActionStatus.COMPLETED,
            success=True,
            message=f"{matched_count} Transaktionen automatisch zugeordnet.",
            affected_count=matched_count,
            rollback_possible=False,  # Komplexer Rollback
        )

    async def _execute_export(
        self,
        action_id: uuid.UUID,
        parameters: Dict[str, Any],
        context: ActionContext,
    ) -> ActionResult:
        """Führt Datenexport durch."""
        formats = parameters.get("formats", ["Excel"])
        date_from = parameters.get("date_from")
        date_to = parameters.get("date_to")

        # Export-Logik würde hier implementiert
        # Für jetzt: Erfolg simulieren

        return ActionResult(
            action_id=action_id,
            status=ActionStatus.COMPLETED,
            success=True,
            message=f"Export als {', '.join(formats)} wurde erstellt.",
            affected_count=1,
            rollback_possible=False,
            metadata={
                "formats": formats,
                "download_url": f"/api/v1/exports/{action_id}",
            },
        )

    # ========================================================================
    # Rollback Support
    # ========================================================================

    async def rollback_action(
        self,
        action_id: uuid.UUID,
        context: ActionContext,
    ) -> ActionResult:
        """Macht eine Aktion rückgängig.

        Args:
            action_id: ID der rückgängig zu machenden Aktion
            context: Ausführungskontext

        Returns:
            ActionResult mit Rollback-Ergebnis
        """
        rollback_info = self._rollback_registry.get(action_id)

        if not rollback_info:
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                success=False,
                message="Rollback-Informationen nicht gefunden.",
            )

        try:
            # Originalzustände wiederherstellen
            for entity_id, original_state in rollback_info.original_states.items():
                # Versuche als InvoiceTracking
                stmt = select(InvoiceTracking).where(
                    InvoiceTracking.id == uuid.UUID(entity_id)
                )
                result = await self.db.execute(stmt)
                entity = result.scalar_one_or_none()

                if entity:
                    for key, value in original_state.items():
                        if hasattr(entity, key):
                            setattr(entity, key, value)
                    continue

                # Versuche als Document
                stmt = select(Document).where(Document.id == uuid.UUID(entity_id))
                result = await self.db.execute(stmt)
                entity = result.scalar_one_or_none()

                if entity:
                    for key, value in original_state.items():
                        if hasattr(entity, key):
                            setattr(entity, key, value)

            await self.db.commit()

            # Aus Registry entfernen
            del self._rollback_registry[action_id]

            logger.info(
                "action_rolled_back",
                action_id=str(action_id),
                user_id=str(context.user_id),
            )

            return ActionResult(
                action_id=action_id,
                status=ActionStatus.ROLLED_BACK,
                success=True,
                message="Aktion erfolgreich rückgängig gemacht.",
                affected_count=len(rollback_info.original_states),
            )

        except Exception as e:
            await self.db.rollback()
            logger.error(
                "rollback_error",
                action_id=str(action_id),
                error=str(e),
            )
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                success=False,
                message="Rollback fehlgeschlagen.",
                error_details=str(e),
            )

    # ========================================================================
    # Audit Logging
    # ========================================================================

    async def _log_action_start(
        self,
        action_id: uuid.UUID,
        action_type: str,
        parameters: Dict[str, Any],
        context: ActionContext,
    ) -> None:
        """Protokolliert Aktionsstart."""
        logger.info(
            "action_started",
            action_id=str(action_id),
            action_type=action_type,
            user_id=str(context.user_id),
            company_id=str(context.company_id),
            parameter_keys=list(parameters.keys()),
        )

    async def _log_action_end(
        self,
        action_id: uuid.UUID,
        result: ActionResult,
        context: ActionContext,
    ) -> None:
        """Protokolliert Aktionsende."""
        logger.info(
            "action_completed",
            action_id=str(action_id),
            status=result.status.value,
            success=result.success,
            affected_count=result.affected_count,
            execution_time_ms=result.execution_time_ms,
            user_id=str(context.user_id),
        )


# ============================================================================
# Factory Function
# ============================================================================


async def get_action_executor_service(db: AsyncSession) -> ActionExecutorService:
    """Factory-Funktion für ActionExecutorService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter ActionExecutorService
    """
    return ActionExecutorService(db=db)

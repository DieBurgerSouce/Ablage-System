"""Approval Audit Service - Unveraenderliches Audit-Protokoll.

Enterprise Feature: Append-only Audit Log fuer Genehmigungen.
Dokumentiert jeden Statuswechsel mit unveraenderlichem Protokoll.
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, List, Dict
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_approval_matrix import ApprovalAuditLog

logger = structlog.get_logger(__name__)


@dataclass
class AuditEntry:
    """Audit-Log Eintrag fuer Response."""
    id: UUID
    request_id: UUID
    step_id: Optional[UUID]
    actor_id: Optional[UUID]
    action_type: str
    old_status: Optional[str]
    new_status: str
    notes: Optional[str]
    ip_address: Optional[str]
    created_at: datetime


class ApprovalAuditService:
    """Service fuer Approval Audit Logging.

    Verwaltet append-only Audit-Protokoll:
    - Unveraenderliche Log-Eintraege
    - Vollstaendiger Audit Trail
    - IP-Adress-Tracking fuer Compliance
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den ApprovalAuditService.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def log_action(
        self,
        company_id: UUID,
        request_id: UUID,
        action_type: str,
        new_status: str,
        actor_id: Optional[UUID] = None,
        step_id: Optional[UUID] = None,
        old_status: Optional[str] = None,
        notes: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalAuditLog:
        """Loggt eine Aktion im Audit-Protokoll (append-only).

        Erlaubte action_types:
        - created: Genehmigung erstellt
        - approved: Genehmigt
        - rejected: Abgelehnt
        - escalated: Eskaliert
        - delegated: Delegiert
        - recalled: Zurueckgerufen
        - four_eyes_check: Vier-Augen-Pruefung

        Args:
            company_id: Firmen-ID
            request_id: Approval Request ID
            action_type: Art der Aktion
            new_status: Neuer Status
            actor_id: User ID des Akteurs
            step_id: Approval Step ID (optional)
            old_status: Alter Status (optional)
            notes: Notizen (optional)
            ip_address: IP-Adresse (optional)
            metadata: Zusaetzliche Kontextdaten (optional)

        Returns:
            Erstellter ApprovalAuditLog Eintrag
        """
        log_entry = ApprovalAuditLog(
            company_id=company_id,
            request_id=request_id,
            step_id=step_id,
            actor_id=actor_id,
            action_type=action_type,
            old_status=old_status,
            new_status=new_status,
            notes=notes,
            ip_address=ip_address,
            metadata_json=metadata,
        )
        self.db.add(log_entry)
        await self.db.commit()
        await self.db.refresh(log_entry)

        logger.info(
            "audit_log_created",
            log_id=str(log_entry.id),
            request_id=str(request_id),
            action_type=action_type,
            actor_id=str(actor_id) if actor_id else None,
        )
        return log_entry

    async def get_audit_trail(
        self,
        request_id: UUID,
    ) -> List[AuditEntry]:
        """Ruft vollstaendigen Audit Trail fuer eine Genehmigungsanfrage ab.

        Args:
            request_id: Approval Request ID

        Returns:
            Liste von AuditEntry, chronologisch sortiert
        """
        query = (
            select(ApprovalAuditLog)
            .where(ApprovalAuditLog.request_id == request_id)
            .order_by(ApprovalAuditLog.created_at.asc())
        )
        result = await self.db.execute(query)
        logs = result.scalars().all()

        return [
            AuditEntry(
                id=log.id,
                request_id=log.request_id,
                step_id=log.step_id,
                actor_id=log.actor_id,
                action_type=log.action_type,
                old_status=log.old_status,
                new_status=log.new_status,
                notes=log.notes,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in logs
        ]

    async def get_company_audit_log(
        self,
        company_id: UUID,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        action_types: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[AuditEntry]:
        """Ruft Firmen-weites Audit-Protokoll ab.

        Args:
            company_id: Firmen-ID
            from_date: Start-Datum (optional)
            to_date: End-Datum (optional)
            action_types: Filter nach Action Types (optional)
            limit: Maximale Anzahl Eintraege (default: 1000)

        Returns:
            Liste von AuditEntry
        """
        conditions = [ApprovalAuditLog.company_id == company_id]

        if from_date:
            conditions.append(ApprovalAuditLog.created_at >= from_date)

        if to_date:
            conditions.append(ApprovalAuditLog.created_at <= to_date)

        if action_types:
            conditions.append(ApprovalAuditLog.action_type.in_(action_types))

        query = (
            select(ApprovalAuditLog)
            .where(and_(*conditions))
            .order_by(ApprovalAuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        logs = result.scalars().all()

        return [
            AuditEntry(
                id=log.id,
                request_id=log.request_id,
                step_id=log.step_id,
                actor_id=log.actor_id,
                action_type=log.action_type,
                old_status=log.old_status,
                new_status=log.new_status,
                notes=log.notes,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in logs
        ]

    async def get_user_audit_log(
        self,
        actor_id: UUID,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Ruft Audit-Protokoll fuer einen bestimmten User ab.

        Args:
            actor_id: User ID
            from_date: Start-Datum (optional)
            to_date: End-Datum (optional)
            limit: Maximale Anzahl Eintraege (default: 100)

        Returns:
            Liste von AuditEntry
        """
        conditions = [ApprovalAuditLog.actor_id == actor_id]

        if from_date:
            conditions.append(ApprovalAuditLog.created_at >= from_date)

        if to_date:
            conditions.append(ApprovalAuditLog.created_at <= to_date)

        query = (
            select(ApprovalAuditLog)
            .where(and_(*conditions))
            .order_by(ApprovalAuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        logs = result.scalars().all()

        return [
            AuditEntry(
                id=log.id,
                request_id=log.request_id,
                step_id=log.step_id,
                actor_id=log.actor_id,
                action_type=log.action_type,
                old_status=log.old_status,
                new_status=log.new_status,
                notes=log.notes,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in logs
        ]

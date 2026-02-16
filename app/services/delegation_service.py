# -*- coding: utf-8 -*-
"""
Delegation Service für Ablage-System.

Ermöglicht temporaere Rechte-Übertragung:
- Urlaubsvertretung
- Krankheitsvertretung
- Projektbasierte Delegation
- Vollständiger Audit-Trail

Phase 3.2 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
import logging

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models_delegation import (
    Delegation,
    DelegationAuditLog,
    DelegationTemplate,
    DelegationType,
    DelegationStatus,
    DelegationReason,
)
from app.db.models import User

logger = logging.getLogger(__name__)


class DelegationService:
    """Service für Delegations-Management.

    Bietet:
    - Erstellen/Verwalten von Delegationen
    - Permission-Checks mit Delegation-Support
    - Audit-Logging für Compliance
    - Template-basierte Schnellerstellung
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Delegation CRUD
    # =========================================================================

    async def create_delegation(
        self,
        delegator_id: UUID,
        delegate_id: UUID,
        company_id: UUID,
        valid_from: datetime,
        valid_until: datetime,
        delegation_type: DelegationType = DelegationType.PARTIAL,
        permissions: Optional[List[str]] = None,
        scope: Optional[Dict[str, Any]] = None,
        reason: DelegationReason = DelegationReason.OTHER,
        reason_text: Optional[str] = None,
        notes: Optional[str] = None,
        requires_acceptance: bool = True,
        notify_on_activation: bool = True,
        notify_on_expiry: bool = True,
        notify_on_usage: bool = False,
        max_approvals: Optional[int] = None,
        max_amount: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Delegation:
        """Erstellt eine neue Delegation.

        Args:
            delegator_id: User der seine Rechte delegiert
            delegate_id: User der die Rechte erhält
            company_id: Company-ID (Multi-Tenant)
            valid_from: Startzeitpunkt
            valid_until: Endzeitpunkt
            delegation_type: Art der Delegation (FULL, PARTIAL, APPROVAL, READ_ONLY, EMERGENCY)
            permissions: Liste der delegierten Berechtigungen (bei PARTIAL)
            scope: Einschränkung auf bestimmte Ressourcen
            reason: Grund für die Delegation
            reason_text: Freitext-Begruendung
            notes: Interne Notizen
            requires_acceptance: Muss Delegate bestätigen?
            notify_on_activation: Bei Aktivierung benachrichtigen
            notify_on_expiry: Bei Ablauf benachrichtigen
            notify_on_usage: Bei jeder Nutzung benachrichtigen
            max_approvals: Max. Anzahl Genehmigungen
            max_amount: Max. Betrag pro Genehmigung
            metadata: Zusätzliche Metadaten

        Returns:
            Die erstellte Delegation

        Raises:
            ValueError: Bei ungültigen Parametern
        """
        # Validierung
        if delegator_id == delegate_id:
            raise ValueError("Delegator und Delegate müssen unterschiedlich sein")

        if valid_until <= valid_from:
            raise ValueError("Endzeitpunkt muss nach Startzeitpunkt liegen")

        if valid_until <= datetime.utcnow():
            raise ValueError("Delegation kann nicht in der Vergangenheit enden")

        # Prüfen ob bereits aktive Delegation existiert
        existing = await self._get_overlapping_delegation(
            delegator_id, delegate_id, company_id, valid_from, valid_until
        )
        if existing:
            raise ValueError(
                f"Es existiert bereits eine überlappende Delegation "
                f"(ID: {existing.id}, {existing.valid_from} - {existing.valid_until})"
            )

        # Status bestimmen
        status = DelegationStatus.PENDING if requires_acceptance else DelegationStatus.ACTIVE

        delegation = Delegation(
            delegator_id=delegator_id,
            delegate_id=delegate_id,
            company_id=company_id,
            delegation_type=delegation_type,
            permissions=permissions or [],
            scope=scope or {},
            valid_from=valid_from,
            valid_until=valid_until,
            status=status,
            reason=reason,
            reason_text=reason_text,
            notes=notes,
            requires_acceptance=requires_acceptance,
            notify_on_activation=notify_on_activation,
            notify_on_expiry=notify_on_expiry,
            notify_on_usage=notify_on_usage,
            max_approvals=max_approvals,
            max_amount=max_amount,
            metadata_json=metadata or {},
        )

        self.db.add(delegation)
        await self.db.flush()

        logger.info(
            "Delegation erstellt: %s delegiert an %s (%s - %s)",
            delegator_id, delegate_id, valid_from, valid_until
        )

        return delegation

    async def get_delegation(
        self,
        delegation_id: UUID,
        company_id: UUID,
    ) -> Optional[Delegation]:
        """Holt eine Delegation nach ID.

        Args:
            delegation_id: Delegation-ID
            company_id: Company-ID für Multi-Tenant-Isolation

        Returns:
            Delegation oder None
        """
        result = await self.db.execute(
            select(Delegation)
            .options(
                selectinload(Delegation.delegator),
                selectinload(Delegation.delegate),
                selectinload(Delegation.revoked_by),
            )
            .where(
                Delegation.id == delegation_id,
                Delegation.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_delegations(
        self,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        as_delegator: bool = True,
        as_delegate: bool = True,
        status: Optional[DelegationStatus] = None,
        include_expired: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Delegation]:
        """Listet Delegationen auf.

        Args:
            company_id: Company-ID
            user_id: Optional User-Filter
            as_delegator: Delegationen als Delegator einbeziehen
            as_delegate: Delegationen als Delegate einbeziehen
            status: Status-Filter
            include_expired: Abgelaufene einbeziehen
            limit: Max. Anzahl
            offset: Offset für Pagination

        Returns:
            Liste von Delegationen
        """
        query = (
            select(Delegation)
            .options(
                selectinload(Delegation.delegator),
                selectinload(Delegation.delegate),
            )
            .where(Delegation.company_id == company_id)
        )

        # User-Filter
        if user_id:
            user_conditions = []
            if as_delegator:
                user_conditions.append(Delegation.delegator_id == user_id)
            if as_delegate:
                user_conditions.append(Delegation.delegate_id == user_id)
            if user_conditions:
                query = query.where(or_(*user_conditions))

        # Status-Filter
        if status:
            query = query.where(Delegation.status == status)
        elif not include_expired:
            query = query.where(
                Delegation.status.in_([
                    DelegationStatus.PENDING,
                    DelegationStatus.ACTIVE,
                ])
            )

        query = (
            query
            .order_by(Delegation.valid_from.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_delegations(
        self,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        status: Optional[DelegationStatus] = None,
    ) -> int:
        """Zaehlt Delegationen.

        Args:
            company_id: Company-ID
            user_id: Optional User-Filter
            status: Status-Filter

        Returns:
            Anzahl der Delegationen
        """
        query = (
            select(func.count(Delegation.id))
            .where(Delegation.company_id == company_id)
        )

        if user_id:
            query = query.where(
                or_(
                    Delegation.delegator_id == user_id,
                    Delegation.delegate_id == user_id,
                )
            )

        if status:
            query = query.where(Delegation.status == status)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def update_delegation(
        self,
        delegation_id: UUID,
        company_id: UUID,
        **updates,
    ) -> Optional[Delegation]:
        """Aktualisiert eine Delegation.

        Args:
            delegation_id: Delegation-ID
            company_id: Company-ID
            **updates: Zu aktualisierende Felder

        Returns:
            Aktualisierte Delegation oder None
        """
        delegation = await self.get_delegation(delegation_id, company_id)
        if not delegation:
            return None

        # Nur bestimmte Felder erlauben
        allowed_fields = {
            "permissions", "scope", "notes", "notify_on_activation",
            "notify_on_expiry", "notify_on_usage", "max_approvals",
            "max_amount", "metadata_json",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(delegation, field, value)

        await self.db.flush()
        return delegation

    # =========================================================================
    # Delegation Lifecycle
    # =========================================================================

    async def accept_delegation(
        self,
        delegation_id: UUID,
        delegate_id: UUID,
        company_id: UUID,
    ) -> Delegation:
        """Delegate akzeptiert eine Delegation.

        Args:
            delegation_id: Delegation-ID
            delegate_id: ID des Delegates (zur Verifizierung)
            company_id: Company-ID

        Returns:
            Aktualisierte Delegation

        Raises:
            ValueError: Bei ungültigem Zustand
        """
        delegation = await self.get_delegation(delegation_id, company_id)
        if not delegation:
            raise ValueError("Delegation nicht gefunden")

        if delegation.delegate_id != delegate_id:
            raise ValueError("Nur der Delegate kann die Delegation akzeptieren")

        if delegation.status != DelegationStatus.PENDING:
            raise ValueError(
                f"Delegation kann im Status {delegation.status.value} "
                "nicht akzeptiert werden"
            )

        delegation.status = DelegationStatus.ACTIVE
        delegation.accepted_at = datetime.utcnow()

        await self.db.flush()

        logger.info("Delegation %s akzeptiert von %s", delegation_id, delegate_id)

        return delegation

    async def decline_delegation(
        self,
        delegation_id: UUID,
        delegate_id: UUID,
        company_id: UUID,
        reason: Optional[str] = None,
    ) -> Delegation:
        """Delegate lehnt eine Delegation ab.

        Args:
            delegation_id: Delegation-ID
            delegate_id: ID des Delegates
            company_id: Company-ID
            reason: Ablehnungsgrund

        Returns:
            Aktualisierte Delegation
        """
        delegation = await self.get_delegation(delegation_id, company_id)
        if not delegation:
            raise ValueError("Delegation nicht gefunden")

        if delegation.delegate_id != delegate_id:
            raise ValueError("Nur der Delegate kann die Delegation ablehnen")

        if delegation.status != DelegationStatus.PENDING:
            raise ValueError(
                f"Delegation kann im Status {delegation.status.value} "
                "nicht abgelehnt werden"
            )

        delegation.status = DelegationStatus.DECLINED
        delegation.declined_at = datetime.utcnow()
        delegation.decline_reason = reason

        await self.db.flush()

        logger.info("Delegation %s abgelehnt von %s", delegation_id, delegate_id)

        return delegation

    async def revoke_delegation(
        self,
        delegation_id: UUID,
        revoked_by_id: UUID,
        company_id: UUID,
        reason: Optional[str] = None,
    ) -> Delegation:
        """Widerruft eine Delegation.

        Kann vom Delegator oder Admin widerrufen werden.

        Args:
            delegation_id: Delegation-ID
            revoked_by_id: Wer widerruft
            company_id: Company-ID
            reason: Widerrufsgrund

        Returns:
            Aktualisierte Delegation
        """
        delegation = await self.get_delegation(delegation_id, company_id)
        if not delegation:
            raise ValueError("Delegation nicht gefunden")

        if delegation.status not in [DelegationStatus.PENDING, DelegationStatus.ACTIVE]:
            raise ValueError(
                f"Delegation kann im Status {delegation.status.value} "
                "nicht widerrufen werden"
            )

        delegation.status = DelegationStatus.REVOKED
        delegation.revoked_at = datetime.utcnow()
        delegation.revoked_by_id = revoked_by_id
        delegation.revoke_reason = reason

        await self.db.flush()

        logger.info(
            "Delegation %s widerrufen von %s: %s",
            delegation_id, revoked_by_id, reason
        )

        return delegation

    async def expire_delegations(self, company_id: Optional[UUID] = None) -> int:
        """Markiert abgelaufene Delegationen als expired.

        Sollte regelmäßig per Celery-Task aufgerufen werden.

        Args:
            company_id: Optional Company-Filter

        Returns:
            Anzahl der aktualisierten Delegationen
        """
        now = datetime.utcnow()

        query = (
            select(Delegation)
            .where(
                Delegation.status == DelegationStatus.ACTIVE,
                Delegation.valid_until < now,
            )
        )

        if company_id:
            query = query.where(Delegation.company_id == company_id)

        result = await self.db.execute(query)
        delegations = result.scalars().all()

        count = 0
        for delegation in delegations:
            delegation.status = DelegationStatus.EXPIRED
            count += 1

        if count > 0:
            await self.db.flush()
            logger.info("%d Delegationen als abgelaufen markiert", count)

        return count

    # =========================================================================
    # Permission Checking mit Delegation
    # =========================================================================

    async def check_permission_with_delegation(
        self,
        user_id: UUID,
        company_id: UUID,
        permission: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        amount: Optional[float] = None,
        request_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Prüft Berechtigung unter Berücksichtigung von Delegationen.

        Args:
            user_id: User der die Aktion ausführt
            company_id: Company-ID
            permission: Benötigte Berechtigung (z.B. "approvals:execute")
            resource_type: Optional Ressourcen-Typ
            resource_id: Optional Ressourcen-ID
            amount: Optional Betrag (für Betragsgrenzen)
            request_info: Request-Informationen für Audit

        Returns:
            Dict mit:
            - allowed: bool
            - via_delegation: bool
            - delegation_id: Optional[UUID]
            - reason: str
        """
        # Aktive Delegationen für diesen User finden
        now = datetime.utcnow()

        result = await self.db.execute(
            select(Delegation)
            .where(
                Delegation.delegate_id == user_id,
                Delegation.company_id == company_id,
                Delegation.status == DelegationStatus.ACTIVE,
                Delegation.valid_from <= now,
                Delegation.valid_until >= now,
            )
            .order_by(Delegation.created_at.desc())
        )
        delegations = result.scalars().all()

        if not delegations:
            return {
                "allowed": False,
                "via_delegation": False,
                "delegation_id": None,
                "reason": "Keine aktive Delegation gefunden",
            }

        # Passende Delegation suchen
        for delegation in delegations:
            # Permission prüfen
            if not self._check_permission_match(delegation, permission):
                continue

            # Scope prüfen
            if not self._check_scope_match(delegation, resource_type, resource_id):
                continue

            # Betragslimit prüfen
            if amount and delegation.max_amount and amount > delegation.max_amount:
                continue

            # Genehmigungslimit prüfen
            if delegation.max_approvals:
                if delegation.usage_count >= delegation.max_approvals:
                    continue

            # Delegation gefunden - Audit-Log erstellen
            await self._log_delegation_usage(
                delegation=delegation,
                action=permission,
                resource_type=resource_type,
                resource_id=resource_id,
                success=True,
                request_info=request_info,
            )

            # Usage Counter erhöhen
            delegation.usage_count += 1
            delegation.last_used_at = now
            await self.db.flush()

            return {
                "allowed": True,
                "via_delegation": True,
                "delegation_id": delegation.id,
                "delegator_id": delegation.delegator_id,
                "reason": f"Berechtigt via Delegation von User {delegation.delegator_id}",
            }

        return {
            "allowed": False,
            "via_delegation": False,
            "delegation_id": None,
            "reason": "Keine passende Delegation für diese Aktion gefunden",
        }

    def _check_permission_match(
        self,
        delegation: Delegation,
        permission: str,
    ) -> bool:
        """Prüft ob Delegation die Berechtigung abdeckt."""
        # FULL Delegation deckt alles ab
        if delegation.delegation_type == DelegationType.FULL:
            return True

        # EMERGENCY auch
        if delegation.delegation_type == DelegationType.EMERGENCY:
            return True

        # READ_ONLY nur Leserechte
        if delegation.delegation_type == DelegationType.READ_ONLY:
            return permission.endswith(":read") or permission.endswith(":view")

        # APPROVAL nur Genehmigungen
        if delegation.delegation_type == DelegationType.APPROVAL:
            return permission.startswith("approval")

        # PARTIAL - explizite Permissions prüfen
        if delegation.delegation_type == DelegationType.PARTIAL:
            permissions = delegation.permissions or []

            # Wildcard-Match
            for perm in permissions:
                if perm == "*":
                    return True
                if perm.endswith(":*"):
                    prefix = perm[:-2]
                    if permission.startswith(prefix):
                        return True
                if perm == permission:
                    return True

            return False

        return False

    def _check_scope_match(
        self,
        delegation: Delegation,
        resource_type: Optional[str],
        resource_id: Optional[UUID],
    ) -> bool:
        """Prüft ob Ressource im Scope der Delegation liegt."""
        scope = delegation.scope or {}

        # Kein Scope definiert = alles erlaubt
        if not scope:
            return True

        # Ordner-Einschränkung
        if resource_type == "folder" and resource_id:
            allowed_folders = scope.get("folders", [])
            if allowed_folders and str(resource_id) not in allowed_folders:
                return False

        # Tag-Einschränkung (müsste separat geprüft werden)
        # allowed_tags = scope.get("tags", [])

        return True

    # =========================================================================
    # Audit Logging
    # =========================================================================

    async def _log_delegation_usage(
        self,
        delegation: Delegation,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        resource_name: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_info: Optional[Dict[str, Any]] = None,
    ) -> DelegationAuditLog:
        """Erstellt Audit-Log-Eintrag für Delegations-Nutzung."""
        log = DelegationAuditLog(
            delegation_id=delegation.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            success=success,
            error_message=error_message,
            details=details or {},
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
        )

        self.db.add(log)
        await self.db.flush()

        return log

    async def get_audit_logs(
        self,
        delegation_id: UUID,
        company_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[DelegationAuditLog]:
        """Holt Audit-Logs für eine Delegation.

        Args:
            delegation_id: Delegation-ID
            company_id: Company-ID
            limit: Max. Anzahl
            offset: Offset

        Returns:
            Liste von Audit-Logs
        """
        # Erst verifizieren dass Delegation zur Company gehoert
        delegation = await self.get_delegation(delegation_id, company_id)
        if not delegation:
            return []

        result = await self.db.execute(
            select(DelegationAuditLog)
            .where(DelegationAuditLog.delegation_id == delegation_id)
            .order_by(DelegationAuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return list(result.scalars().all())

    # =========================================================================
    # Templates
    # =========================================================================

    async def create_template(
        self,
        company_id: UUID,
        name: str,
        delegation_type: DelegationType,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        scope: Optional[Dict[str, Any]] = None,
        default_duration_days: int = 14,
        requires_acceptance: bool = True,
        notify_on_activation: bool = True,
        notify_on_usage: bool = False,
        is_system: bool = False,
    ) -> DelegationTemplate:
        """Erstellt ein Delegations-Template.

        Args:
            company_id: Company-ID
            name: Template-Name
            delegation_type: Delegations-Typ
            description: Beschreibung
            permissions: Berechtigungen
            scope: Scope-Einschränkungen
            default_duration_days: Standard-Dauer
            requires_acceptance: Bestätigung erforderlich
            notify_on_activation: Benachrichtigung bei Aktivierung
            notify_on_usage: Benachrichtigung bei Nutzung
            is_system: System-Template (nicht löschbar)

        Returns:
            Das erstellte Template
        """
        template = DelegationTemplate(
            company_id=company_id,
            name=name,
            description=description,
            delegation_type=delegation_type,
            permissions=permissions or [],
            scope=scope or {},
            default_duration_days=default_duration_days,
            requires_acceptance=requires_acceptance,
            notify_on_activation=notify_on_activation,
            notify_on_usage=notify_on_usage,
            is_system=is_system,
        )

        self.db.add(template)
        await self.db.flush()

        return template

    async def list_templates(
        self,
        company_id: UUID,
        include_inactive: bool = False,
    ) -> List[DelegationTemplate]:
        """Listet alle Templates einer Company auf."""
        query = (
            select(DelegationTemplate)
            .where(DelegationTemplate.company_id == company_id)
        )

        if not include_inactive:
            query = query.where(DelegationTemplate.is_active == True)

        query = query.order_by(DelegationTemplate.name)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_from_template(
        self,
        template_id: UUID,
        delegator_id: UUID,
        delegate_id: UUID,
        company_id: UUID,
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
        reason: DelegationReason = DelegationReason.OTHER,
        reason_text: Optional[str] = None,
    ) -> Delegation:
        """Erstellt Delegation aus Template.

        Args:
            template_id: Template-ID
            delegator_id: Delegator-ID
            delegate_id: Delegate-ID
            company_id: Company-ID
            valid_from: Start (default: jetzt)
            valid_until: Ende (default: jetzt + default_duration_days)
            reason: Delegations-Grund
            reason_text: Freitext-Begruendung

        Returns:
            Die erstellte Delegation
        """
        result = await self.db.execute(
            select(DelegationTemplate)
            .where(
                DelegationTemplate.id == template_id,
                DelegationTemplate.company_id == company_id,
                DelegationTemplate.is_active == True,
            )
        )
        template = result.scalar_one_or_none()

        if not template:
            raise ValueError("Template nicht gefunden oder inaktiv")

        # Zeitraum bestimmen
        if not valid_from:
            valid_from = datetime.utcnow()
        if not valid_until:
            valid_until = valid_from + timedelta(days=template.default_duration_days)

        return await self.create_delegation(
            delegator_id=delegator_id,
            delegate_id=delegate_id,
            company_id=company_id,
            valid_from=valid_from,
            valid_until=valid_until,
            delegation_type=template.delegation_type,
            permissions=template.permissions,
            scope=template.scope,
            reason=reason,
            reason_text=reason_text,
            requires_acceptance=template.requires_acceptance,
            notify_on_activation=template.notify_on_activation,
            notify_on_usage=template.notify_on_usage,
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _get_overlapping_delegation(
        self,
        delegator_id: UUID,
        delegate_id: UUID,
        company_id: UUID,
        valid_from: datetime,
        valid_until: datetime,
    ) -> Optional[Delegation]:
        """Prüft auf überlappende Delegationen."""
        result = await self.db.execute(
            select(Delegation)
            .where(
                Delegation.delegator_id == delegator_id,
                Delegation.delegate_id == delegate_id,
                Delegation.company_id == company_id,
                Delegation.status.in_([
                    DelegationStatus.PENDING,
                    DelegationStatus.ACTIVE,
                ]),
                # Überlappungsprüfung
                or_(
                    and_(
                        Delegation.valid_from <= valid_from,
                        Delegation.valid_until >= valid_from,
                    ),
                    and_(
                        Delegation.valid_from <= valid_until,
                        Delegation.valid_until >= valid_until,
                    ),
                    and_(
                        Delegation.valid_from >= valid_from,
                        Delegation.valid_until <= valid_until,
                    ),
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_delegations_for_user(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> List[Delegation]:
        """Holt alle aktiven Delegationen für einen User (als Delegate)."""
        now = datetime.utcnow()

        result = await self.db.execute(
            select(Delegation)
            .options(selectinload(Delegation.delegator))
            .where(
                Delegation.delegate_id == user_id,
                Delegation.company_id == company_id,
                Delegation.status == DelegationStatus.ACTIVE,
                Delegation.valid_from <= now,
                Delegation.valid_until >= now,
            )
        )

        return list(result.scalars().all())

    async def get_pending_delegations_for_user(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> List[Delegation]:
        """Holt ausstehende Delegationen die auf Bestätigung warten."""
        result = await self.db.execute(
            select(Delegation)
            .options(selectinload(Delegation.delegator))
            .where(
                Delegation.delegate_id == user_id,
                Delegation.company_id == company_id,
                Delegation.status == DelegationStatus.PENDING,
            )
            .order_by(Delegation.created_at.desc())
        )

        return list(result.scalars().all())

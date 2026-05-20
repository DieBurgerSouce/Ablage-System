# -*- coding: utf-8 -*-
"""Permission Audit Service für Ablage-System.

Phase 1.2: Berechtigungsprotokoll für Compliance und Security Audits.

Features:
- Jede Permission-Änderung wird protokolliert
- Wer hat wann welche Berechtigung erhalten/verloren
- Exportierbar für Compliance-Reports (CSV, JSON)
- DSGVO Art. 30 konforme Verarbeitungsdokumentation

SECURITY: Tenant-isolierte Abfragen durch company_id Filter.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from uuid import UUID
import csv
import io
import json

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

logger = structlog.get_logger(__name__)


class PermissionChangeType(str, Enum):
    """Typen von Permission-Änderungen."""

    # Rollen-Änderungen
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    ROLE_CHANGED = "role_changed"

    # Einzelne Permissions
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"

    # Gruppen-Mitgliedschaft
    GROUP_ADDED = "group_added"
    GROUP_REMOVED = "group_removed"

    # Team-Mitgliedschaft (Phase 3)
    TEAM_JOINED = "team_joined"
    TEAM_LEFT = "team_left"
    TEAM_ROLE_CHANGED = "team_role_changed"

    # Delegation (Phase 3)
    DELEGATION_CREATED = "delegation_created"
    DELEGATION_REVOKED = "delegation_revoked"
    DELEGATION_EXPIRED = "delegation_expired"


class PermissionChangeRecord(BaseModel):
    """Schema für einen Permission-Änderungs-Eintrag."""

    id: str
    timestamp: datetime
    change_type: PermissionChangeType

    # Wer wurde geändert
    target_user_id: str
    target_user_email: Optional[str] = None

    # Wer hat geändert
    changed_by_user_id: Optional[str] = None
    changed_by_email: Optional[str] = None

    # Was wurde geändert
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    permission_name: Optional[str] = None
    role_name: Optional[str] = None
    group_name: Optional[str] = None
    team_name: Optional[str] = None

    # Kontext
    company_id: str
    ip_address: Optional[str] = None
    reason: Optional[str] = None

    # Metadaten
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PermissionAuditExport(BaseModel):
    """Schema für Export-Ergebnis."""

    generated_at: datetime
    company_id: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    total_records: int
    records: List[PermissionChangeRecord]


class PermissionAuditService:
    """
    Service für Permission-Audit und Compliance-Reporting.

    Phase 1.2: Berechtigungsprotokoll
    - Protokolliert alle Permission-Änderungen
    - Unterstützt Compliance-Exports
    - Tenant-isolierte Abfragen

    Verwendung:
        service = PermissionAuditService(db)
        await service.log_role_change(...)
        report = await service.get_audit_report(company_id, ...)
        csv_data = await service.export_csv(company_id, ...)
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den Permission Audit Service.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db
        self.audit_logger = SecurityAuditLogger(db)

    # =========================================================================
    # Logging Methods
    # =========================================================================

    async def log_role_assigned(
        self,
        target_user_id: str,
        role_name: str,
        company_id: str,
        changed_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """
        Protokolliert die Zuweisung einer Rolle.

        Args:
            target_user_id: User der die Rolle erhält
            role_name: Name der zugewiesenen Rolle
            company_id: Company-ID für Tenant-Isolation
            changed_by_user_id: Admin der die Änderung durchführt
            ip_address: IP-Adresse des Admins
            reason: Optionaler Grund für die Änderung

        Returns:
            Audit-Log-ID oder None bei Fehler
        """
        return await self._log_permission_change(
            change_type=PermissionChangeType.ROLE_ASSIGNED,
            target_user_id=target_user_id,
            company_id=company_id,
            changed_by_user_id=changed_by_user_id,
            ip_address=ip_address,
            new_value=role_name,
            role_name=role_name,
            reason=reason,
        )

    async def log_role_removed(
        self,
        target_user_id: str,
        role_name: str,
        company_id: str,
        changed_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert das Entfernen einer Rolle."""
        return await self._log_permission_change(
            change_type=PermissionChangeType.ROLE_REMOVED,
            target_user_id=target_user_id,
            company_id=company_id,
            changed_by_user_id=changed_by_user_id,
            ip_address=ip_address,
            old_value=role_name,
            role_name=role_name,
            reason=reason,
        )

    async def log_role_changed(
        self,
        target_user_id: str,
        old_role: str,
        new_role: str,
        company_id: str,
        changed_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert eine Rollenänderung."""
        return await self._log_permission_change(
            change_type=PermissionChangeType.ROLE_CHANGED,
            target_user_id=target_user_id,
            company_id=company_id,
            changed_by_user_id=changed_by_user_id,
            ip_address=ip_address,
            old_value=old_role,
            new_value=new_role,
            role_name=new_role,
            reason=reason,
        )

    async def log_permission_granted(
        self,
        target_user_id: str,
        permission_name: str,
        company_id: str,
        changed_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert das Erteilen einer einzelnen Permission."""
        return await self._log_permission_change(
            change_type=PermissionChangeType.PERMISSION_GRANTED,
            target_user_id=target_user_id,
            company_id=company_id,
            changed_by_user_id=changed_by_user_id,
            ip_address=ip_address,
            new_value=permission_name,
            permission_name=permission_name,
            reason=reason,
        )

    async def log_permission_revoked(
        self,
        target_user_id: str,
        permission_name: str,
        company_id: str,
        changed_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert das Entziehen einer Permission."""
        return await self._log_permission_change(
            change_type=PermissionChangeType.PERMISSION_REVOKED,
            target_user_id=target_user_id,
            company_id=company_id,
            changed_by_user_id=changed_by_user_id,
            ip_address=ip_address,
            old_value=permission_name,
            permission_name=permission_name,
            reason=reason,
        )

    async def log_group_membership_change(
        self,
        target_user_id: str,
        group_name: str,
        added: bool,
        company_id: str,
        changed_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert Änderungen an Gruppenmitgliedschaften."""
        change_type = PermissionChangeType.GROUP_ADDED if added else PermissionChangeType.GROUP_REMOVED
        return await self._log_permission_change(
            change_type=change_type,
            target_user_id=target_user_id,
            company_id=company_id,
            changed_by_user_id=changed_by_user_id,
            ip_address=ip_address,
            new_value=group_name if added else None,
            old_value=group_name if not added else None,
            group_name=group_name,
            reason=reason,
        )

    async def log_delegation_created(
        self,
        delegator_id: str,
        delegate_id: str,
        permissions: List[str],
        valid_until: datetime,
        company_id: str,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert das Erstellen einer Delegation (Phase 3)."""
        return await self._log_permission_change(
            change_type=PermissionChangeType.DELEGATION_CREATED,
            target_user_id=delegate_id,
            company_id=company_id,
            changed_by_user_id=delegator_id,
            ip_address=ip_address,
            new_value=",".join(permissions),
            reason=reason,
            metadata={
                "delegator_id": delegator_id,
                "valid_until": valid_until.isoformat(),
                "permissions_count": len(permissions),
            },
        )

    async def log_delegation_revoked(
        self,
        delegator_id: str,
        delegate_id: str,
        company_id: str,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Protokolliert das Widerrufen einer Delegation."""
        return await self._log_permission_change(
            change_type=PermissionChangeType.DELEGATION_REVOKED,
            target_user_id=delegate_id,
            company_id=company_id,
            changed_by_user_id=delegator_id,
            ip_address=ip_address,
            reason=reason,
        )

    async def _log_permission_change(
        self,
        change_type: PermissionChangeType,
        target_user_id: str,
        company_id: str,
        changed_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        permission_name: Optional[str] = None,
        role_name: Optional[str] = None,
        group_name: Optional[str] = None,
        team_name: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Interne Methode zum Protokollieren von Permission-Änderungen.

        Nutzt die bestehende SecurityAuditLogger-Infrastruktur.
        """
        # Map change_type to SecurityEventType
        event_type_map = {
            PermissionChangeType.ROLE_ASSIGNED: SecurityEventType.ROLE_CHANGED,
            PermissionChangeType.ROLE_REMOVED: SecurityEventType.ROLE_CHANGED,
            PermissionChangeType.ROLE_CHANGED: SecurityEventType.ROLE_CHANGED,
            PermissionChangeType.PERMISSION_GRANTED: SecurityEventType.PERMISSION_GRANTED,
            PermissionChangeType.PERMISSION_REVOKED: SecurityEventType.PERMISSION_REVOKED,
            PermissionChangeType.GROUP_ADDED: SecurityEventType.PERMISSION_GRANTED,
            PermissionChangeType.GROUP_REMOVED: SecurityEventType.PERMISSION_REVOKED,
            PermissionChangeType.TEAM_JOINED: SecurityEventType.PERMISSION_GRANTED,
            PermissionChangeType.TEAM_LEFT: SecurityEventType.PERMISSION_REVOKED,
            PermissionChangeType.TEAM_ROLE_CHANGED: SecurityEventType.ROLE_CHANGED,
            PermissionChangeType.DELEGATION_CREATED: SecurityEventType.PERMISSION_GRANTED,
            PermissionChangeType.DELEGATION_REVOKED: SecurityEventType.PERMISSION_REVOKED,
            PermissionChangeType.DELEGATION_EXPIRED: SecurityEventType.PERMISSION_REVOKED,
        }

        event_type = event_type_map.get(change_type, SecurityEventType.PERMISSION_GRANTED)

        # Build details
        details = {
            "change_type": change_type.value,
            "company_id": company_id,
            "target_user_id": target_user_id,
        }

        if changed_by_user_id:
            details["changed_by"] = changed_by_user_id
        if old_value:
            details["old_value"] = old_value
        if new_value:
            details["new_value"] = new_value
        if permission_name:
            details["permission"] = permission_name
        if role_name:
            details["role"] = role_name
        if group_name:
            details["group"] = group_name
        if team_name:
            details["team"] = team_name
        if reason:
            details["reason"] = reason
        if metadata:
            details["metadata"] = metadata

        # Log via SecurityAuditLogger
        audit_id = await self.audit_logger.log_event(
            event_type=event_type,
            user_id=target_user_id,
            ip_address=ip_address,
            resource_type="permission",
            resource_id=None,
            details=details,
            severity="warning" if "revoked" in change_type.value.lower() else "info",
        )

        logger.info(
            "permission_change_logged",
            change_type=change_type.value,
            target_user=target_user_id[:8] + "..." if target_user_id else None,
            company_id=company_id[:8] + "..." if company_id else None,
        )

        return audit_id

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_user_permission_history(
        self,
        user_id: str,
        company_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[PermissionChangeRecord]:
        """
        Holt die Permission-Historie für einen User.

        Args:
            user_id: User-ID
            company_id: Company-ID für Tenant-Isolation
            start_date: Optionaler Startpunkt
            end_date: Optionaler Endpunkt
            limit: Maximale Anzahl Einträge
            offset: Offset für Pagination

        Returns:
            Liste von PermissionChangeRecord
        """
        from app.db.models import AuditLog

        # Base query mit Tenant-Filter
        conditions = [
            AuditLog.user_id == UUID(user_id),
            AuditLog.resource_type == "permission",
        ]

        # Zeitfilter
        if start_date:
            conditions.append(AuditLog.created_at >= start_date)
        if end_date:
            conditions.append(AuditLog.created_at <= end_date)

        query = (
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        entries = result.scalars().all()

        # Convert to PermissionChangeRecord
        records = []
        for entry in entries:
            metadata = entry.audit_metadata or {}

            # Tenant-Isolation Check
            if metadata.get("company_id") != company_id:
                continue

            record = PermissionChangeRecord(
                id=str(entry.id),
                timestamp=entry.created_at,
                change_type=PermissionChangeType(
                    metadata.get("change_type", "permission_granted")
                ),
                target_user_id=str(entry.user_id) if entry.user_id else "",
                changed_by_user_id=metadata.get("changed_by"),
                old_value=metadata.get("old_value"),
                new_value=metadata.get("new_value"),
                permission_name=metadata.get("permission"),
                role_name=metadata.get("role"),
                group_name=metadata.get("group"),
                team_name=metadata.get("team"),
                company_id=company_id,
                ip_address=entry.ip_address,
                reason=metadata.get("reason"),
                metadata=metadata.get("metadata", {}),
            )
            records.append(record)

        return records

    async def get_company_permission_audit(
        self,
        company_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        change_types: Optional[List[PermissionChangeType]] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> PermissionAuditExport:
        """
        Holt alle Permission-Änderungen für eine Company.

        Args:
            company_id: Company-ID
            start_date: Optionaler Startpunkt
            end_date: Optionaler Endpunkt
            change_types: Optionale Filter für Change-Types
            limit: Maximale Anzahl Einträge
            offset: Offset für Pagination

        Returns:
            PermissionAuditExport mit allen Records
        """
        from app.db.models import AuditLog
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import cast, String

        # Permission-relevante Event-Types
        permission_events = [
            SecurityEventType.ROLE_CHANGED.value,
            SecurityEventType.PERMISSION_GRANTED.value,
            SecurityEventType.PERMISSION_REVOKED.value,
        ]

        # Base query
        conditions = [
            AuditLog.resource_type == "permission",
            AuditLog.action.in_(permission_events),
        ]

        # Zeitfilter
        if start_date:
            conditions.append(AuditLog.created_at >= start_date)
        if end_date:
            conditions.append(AuditLog.created_at <= end_date)

        query = (
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        entries = result.scalars().all()

        # Filter by company_id in metadata und convert
        records = []
        for entry in entries:
            metadata = entry.audit_metadata or {}

            # Tenant-Isolation
            if metadata.get("company_id") != company_id:
                continue

            # Change-Type Filter
            change_type_str = metadata.get("change_type", "permission_granted")
            try:
                change_type = PermissionChangeType(change_type_str)
            except ValueError:
                change_type = PermissionChangeType.PERMISSION_GRANTED

            if change_types and change_type not in change_types:
                continue

            record = PermissionChangeRecord(
                id=str(entry.id),
                timestamp=entry.created_at,
                change_type=change_type,
                target_user_id=str(entry.user_id) if entry.user_id else "",
                changed_by_user_id=metadata.get("changed_by"),
                old_value=metadata.get("old_value"),
                new_value=metadata.get("new_value"),
                permission_name=metadata.get("permission"),
                role_name=metadata.get("role"),
                group_name=metadata.get("group"),
                team_name=metadata.get("team"),
                company_id=company_id,
                ip_address=entry.ip_address,
                reason=metadata.get("reason"),
                metadata=metadata.get("metadata", {}),
            )
            records.append(record)

        return PermissionAuditExport(
            generated_at=datetime.now(timezone.utc),
            company_id=company_id,
            period_start=start_date,
            period_end=end_date,
            total_records=len(records),
            records=records,
        )

    # =========================================================================
    # Export Methods
    # =========================================================================

    async def export_csv(
        self,
        company_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """
        Exportiert Permission-Audit als CSV.

        DSGVO Art. 30 konforme Dokumentation.

        Args:
            company_id: Company-ID
            start_date: Optionaler Startpunkt
            end_date: Optionaler Endpunkt

        Returns:
            CSV-String
        """
        audit = await self.get_company_permission_audit(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            limit=10000,  # Max für Export
        )

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")  # Semikolon für deutsche Excel

        # Header (Deutsch für Compliance)
        writer.writerow([
            "ID",
            "Zeitstempel",
            "Änderungstyp",
            "Betroffener Benutzer",
            "Durchgeführt von",
            "Alter Wert",
            "Neuer Wert",
            "Berechtigung",
            "Rolle",
            "Gruppe",
            "IP-Adresse",
            "Grund",
        ])

        # Daten
        for record in audit.records:
            writer.writerow([
                record.id,
                record.timestamp.isoformat(),
                record.change_type.value,
                record.target_user_id,
                record.changed_by_user_id or "",
                record.old_value or "",
                record.new_value or "",
                record.permission_name or "",
                record.role_name or "",
                record.group_name or "",
                record.ip_address or "",
                record.reason or "",
            ])

        return output.getvalue()

    async def export_json(
        self,
        company_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """
        Exportiert Permission-Audit als JSON.

        Args:
            company_id: Company-ID
            start_date: Optionaler Startpunkt
            end_date: Optionaler Endpunkt

        Returns:
            JSON-String
        """
        audit = await self.get_company_permission_audit(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )

        return audit.model_dump_json(indent=2)

    # =========================================================================
    # Compliance Reports
    # =========================================================================

    async def get_compliance_summary(
        self,
        company_id: str,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Erstellt eine Compliance-Zusammenfassung für Permission-Änderungen.

        Args:
            company_id: Company-ID
            period_days: Betrachtungszeitraum in Tagen

        Returns:
            Zusammenfassung als Dict
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=period_days)

        audit = await self.get_company_permission_audit(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )

        # Statistiken berechnen
        by_type: Dict[str, int] = {}
        by_user: Dict[str, int] = {}
        by_admin: Dict[str, int] = {}

        for record in audit.records:
            # Nach Typ
            type_key = record.change_type.value
            by_type[type_key] = by_type.get(type_key, 0) + 1

            # Nach betroffenem User
            if record.target_user_id:
                by_user[record.target_user_id] = by_user.get(record.target_user_id, 0) + 1

            # Nach Admin
            if record.changed_by_user_id:
                by_admin[record.changed_by_user_id] = by_admin.get(record.changed_by_user_id, 0) + 1

        return {
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "total_changes": audit.total_records,
            "changes_by_type": by_type,
            "users_affected": len(by_user),
            "admins_involved": len(by_admin),
            "top_affected_users": sorted(
                by_user.items(), key=lambda x: x[1], reverse=True
            )[:10],
            "top_admins": sorted(
                by_admin.items(), key=lambda x: x[1], reverse=True
            )[:10],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

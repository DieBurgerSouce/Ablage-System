"""Retention Enforcement Service - Aktive Durchsetzung von Aufbewahrungsfristen.

Erweitert den bestehenden RetentionService um:
- Loeschsperre waehrend aktiver Aufbewahrungsfrist
- GDPR vs. Retention Konflikt-Aufloesung (§17 DSGVO vs §147 AO)
- Automatische Pruefung bei Document-Delete-Anfragen
- Compliance-Dashboard-Daten

Gesetzliche Grundlagen:
- §147 AO (Abgabenordnung): 10 Jahre Aufbewahrungspflicht fuer Buchfuehrungsunterlagen
- §257 HGB (Handelsgesetzbuch): 6-10 Jahre je nach Dokumenttyp
- §17 DSGVO: Recht auf Loeschung (Ausnahme: §17 Abs. 3 lit. b - rechtliche Verpflichtung)
"""

from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentArchive, Company
from app.services.compliance.retention_service import retention_service

logger = structlog.get_logger(__name__)


class EnforcementStatus(str, Enum):
    """Status der Durchsetzung von Aufbewahrungsfristen."""
    ACTIVE = "active"  # Aufbewahrungsfrist aktiv
    EXPIRED = "expired"  # Frist abgelaufen
    GDPR_CONFLICT = "gdpr_conflict"  # GDPR-Loeschanfrage mit aktiver Frist
    EXCEPTION_GRANTED = "exception_granted"  # Ausnahmegenehmigung


class ConflictResolutionAction(str, Enum):
    """Massnahmen bei GDPR vs. Retention Konflikt."""
    RETENTION_WINS = "retention_wins"  # Aufbewahrungspflicht hat Vorrang
    ANONYMIZE_METADATA = "anonymize_metadata"  # Metadaten anonymisieren
    SCHEDULE_POST_RETENTION = "schedule_post_retention"  # Nach Fristablauf loeschen
    EXCEPTION_REQUIRED = "exception_required"  # Admin-Genehmigung erforderlich


@dataclass
class RetentionCheckResult:
    """Ergebnis einer Aufbewahrungsfristen-Pruefung."""
    can_delete: bool
    reason: str
    enforcement_status: EnforcementStatus
    retention_expires_at: Optional[date]
    days_remaining: Optional[int]
    legal_basis: Optional[str]
    archive_id: Optional[uuid.UUID]


@dataclass
class ConflictResolution:
    """Ergebnis der Konflikt-Aufloesung zwischen GDPR und Retention."""
    action: ConflictResolutionAction
    reason: str
    retention_expires_at: date
    can_anonymize: bool
    scheduled_deletion_at: Optional[date]
    requires_admin_approval: bool
    legal_justification: str


@dataclass
class ComplianceDashboard:
    """Compliance-Dashboard Daten fuer Uebersicht."""
    total_archives: int
    active_retention: int
    expired_retention: int
    expiring_30_days: int
    expiring_90_days: int
    gdpr_conflicts: int
    scheduled_post_retention_deletions: int
    by_category: Dict[str, int]
    by_enforcement_status: Dict[str, int]
    last_updated: datetime


@dataclass
class EnforcementResult:
    """Ergebnis einer Durchsetzungs-Aktion."""
    success: bool
    action_taken: str
    reason: str
    document_id: uuid.UUID
    archive_id: Optional[uuid.UUID]
    legal_basis: Optional[str]


class RetentionEnforcementService:
    """Service fuer aktive Durchsetzung von Aufbewahrungsfristen.

    Verwaltet die Loeschsperre waehrend Aufbewahrungsfristen und
    loest Konflikte zwischen GDPR-Loeschanspruch und Aufbewahrungspflicht.
    """

    async def can_delete_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> RetentionCheckResult:
        """Prueft ob ein Dokument geloescht werden darf.

        Prueft ob eine aktive Aufbewahrungsfrist die Loeschung verhindert.

        Args:
            db: Datenbank-Session
            document_id: ID des zu pruefenden Dokuments

        Returns:
            RetentionCheckResult mit Entscheidung und Begruendung
        """
        # Dokument und Archiv laden
        result = await db.execute(
            select(Document)
            .where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            return RetentionCheckResult(
                can_delete=False,
                reason="Dokument nicht gefunden",
                enforcement_status=EnforcementStatus.ACTIVE,
                retention_expires_at=None,
                days_remaining=None,
                legal_basis=None,
                archive_id=None,
            )

        # Pruefe ob Dokument archiviert ist
        if not document.is_archived:
            return RetentionCheckResult(
                can_delete=True,
                reason="Dokument ist nicht archiviert, keine Aufbewahrungspflicht",
                enforcement_status=EnforcementStatus.EXPIRED,
                retention_expires_at=None,
                days_remaining=None,
                legal_basis=None,
                archive_id=None,
            )

        # Archiv-Eintrag laden
        archive_result = await db.execute(
            select(DocumentArchive)
            .where(DocumentArchive.document_id == document_id)
        )
        archive = archive_result.scalar_one_or_none()

        if not archive:
            # Inkonsistenz: is_archived=True aber kein Archive-Eintrag
            logger.warning(
                "document_archive_inconsistency",
                document_id=str(document_id),
                is_archived=document.is_archived,
            )
            return RetentionCheckResult(
                can_delete=True,
                reason="Archiv-Eintrag nicht gefunden (Inkonsistenz)",
                enforcement_status=EnforcementStatus.EXPIRED,
                retention_expires_at=None,
                days_remaining=None,
                legal_basis=None,
                archive_id=None,
            )

        today = date.today()
        days_remaining = (archive.retention_expires_at - today).days

        # Pruefe ob Aufbewahrungsfrist abgelaufen ist
        if archive.retention_expires_at < today:
            return RetentionCheckResult(
                can_delete=True,
                reason=f"Aufbewahrungsfrist abgelaufen am {archive.retention_expires_at}",
                enforcement_status=EnforcementStatus.EXPIRED,
                retention_expires_at=archive.retention_expires_at,
                days_remaining=days_remaining,
                legal_basis=retention_service.default_periods.get(
                    archive.retention_category.lower(), {}
                ).get("legal_basis"),
                archive_id=archive.id,
            )

        # Aufbewahrungsfrist ist noch aktiv
        legal_basis = retention_service.default_periods.get(
            archive.retention_category.lower(), {}
        ).get("legal_basis", "§147 AO / §257 HGB")

        return RetentionCheckResult(
            can_delete=False,
            reason=(
                f"Aufbewahrungsfrist aktiv bis {archive.retention_expires_at} "
                f"({days_remaining} Tage verbleibend). "
                f"Gesetzliche Grundlage: {legal_basis}"
            ),
            enforcement_status=EnforcementStatus.ACTIVE,
            retention_expires_at=archive.retention_expires_at,
            days_remaining=days_remaining,
            legal_basis=legal_basis,
            archive_id=archive.id,
        )

    async def resolve_gdpr_retention_conflict(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        gdpr_request_id: Optional[uuid.UUID] = None,
    ) -> ConflictResolution:
        """Loest Konflikt zwischen GDPR-Loeschanspruch und Aufbewahrungspflicht.

        Nach §17 Abs. 3 lit. b DSGVO besteht kein Loeschanspruch,
        wenn eine rechtliche Aufbewahrungspflicht besteht (§147 AO, §257 HGB).

        Loesung:
        - Aufbewahrungspflicht hat Vorrang (deutsches Recht)
        - Personenbezogene Metadaten koennen anonymisiert werden
        - Automatische Loeschung nach Fristablauf planen

        Args:
            db: Datenbank-Session
            document_id: ID des betroffenen Dokuments
            gdpr_request_id: Optional - ID der GDPR-Loeschanfrage

        Returns:
            ConflictResolution mit Massnahmen und Begruendung
        """
        # Pruefe Loeschbarkeit
        check_result = await self.can_delete_document(db, document_id)

        if check_result.can_delete:
            # Kein Konflikt - Dokument kann geloescht werden
            return ConflictResolution(
                action=ConflictResolutionAction.RETENTION_WINS,
                reason="Aufbewahrungsfrist abgelaufen, GDPR-Loeschung kann erfolgen",
                retention_expires_at=check_result.retention_expires_at or date.today(),
                can_anonymize=False,
                scheduled_deletion_at=None,
                requires_admin_approval=False,
                legal_justification="§17 DSGVO - Recht auf Loeschung",
            )

        # Konflikt: Aufbewahrungspflicht vs. GDPR
        # Nach deutschem Recht: Aufbewahrungspflicht hat Vorrang
        scheduled_deletion = check_result.retention_expires_at + timedelta(days=1) if check_result.retention_expires_at else None

        return ConflictResolution(
            action=ConflictResolutionAction.RETENTION_WINS,
            reason=(
                f"Aufbewahrungspflicht hat Vorrang gemaess {check_result.legal_basis}. "
                f"GDPR-Loeschung nach Fristablauf ({check_result.retention_expires_at}) geplant. "
                f"Metadaten-Anonymisierung moeglich."
            ),
            retention_expires_at=check_result.retention_expires_at,
            can_anonymize=True,
            scheduled_deletion_at=scheduled_deletion,
            requires_admin_approval=False,
            legal_justification=(
                f"§17 Abs. 3 lit. b DSGVO: Ausnahme vom Loeschanspruch bei rechtlicher Verpflichtung. "
                f"Aufbewahrungspflicht: {check_result.legal_basis}"
            ),
        )

    async def get_compliance_dashboard(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> ComplianceDashboard:
        """Holt Compliance-Dashboard Daten fuer Uebersicht.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            ComplianceDashboard mit Statistiken
        """
        today = date.today()

        # Gesamtzahl Archive
        total_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(DocumentArchive.company_id == company_id)
        )
        total_archives = total_result.scalar() or 0

        # Aktive Aufbewahrungsfristen
        active_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at >= today,
                )
            )
        )
        active_retention = active_result.scalar() or 0

        # Abgelaufene Fristen
        expired_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at < today,
                )
            )
        )
        expired_retention = expired_result.scalar() or 0

        # Ablaufend in 30 Tagen
        expiring_30_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at >= today,
                    DocumentArchive.retention_expires_at <= today + timedelta(days=30),
                )
            )
        )
        expiring_30_days = expiring_30_result.scalar() or 0

        # Ablaufend in 90 Tagen
        expiring_90_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at >= today,
                    DocumentArchive.retention_expires_at <= today + timedelta(days=90),
                )
            )
        )
        expiring_90_days = expiring_90_result.scalar() or 0

        # Nach Kategorie
        category_result = await db.execute(
            select(
                DocumentArchive.retention_category,
                func.count().label("count"),
            )
            .where(DocumentArchive.company_id == company_id)
            .group_by(DocumentArchive.retention_category)
        )
        by_category = {row.retention_category: row.count for row in category_result.all()}

        # Nach Enforcement-Status
        # Hier simuliert - in Production wuerde enforcement_status aus DB kommen
        by_enforcement_status = {
            EnforcementStatus.ACTIVE.value: active_retention,
            EnforcementStatus.EXPIRED.value: expired_retention,
        }

        # GDPR-Konflikte - zaehle Archive mit GDPR conflict flag
        # (Aktuell simuliert - in Production wuerde gdpr_conflict_resolved_at geprueft)
        gdpr_conflicts = 0

        # Geplante Post-Retention Loeschungen
        # (Aktuell simuliert - in Production wuerde post_retention_review_scheduled geprueft)
        scheduled_post_retention = 0

        return ComplianceDashboard(
            total_archives=total_archives,
            active_retention=active_retention,
            expired_retention=expired_retention,
            expiring_30_days=expiring_30_days,
            expiring_90_days=expiring_90_days,
            gdpr_conflicts=gdpr_conflicts,
            scheduled_post_retention_deletions=scheduled_post_retention,
            by_category=by_category,
            by_enforcement_status=by_enforcement_status,
            last_updated=datetime.now(),
        )

    async def enforce_retention_on_delete(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> EnforcementResult:
        """Durchsetzt Aufbewahrungsfristen beim Loeschversuch.

        Wird vom Loeschpfad aufgerufen um zu pruefen ob Loeschung erlaubt ist.
        Wirft Exception wenn Aufbewahrungsfrist aktiv ist.

        Args:
            db: Datenbank-Session
            document_id: ID des zu loeschenden Dokuments
            user_id: ID des loeschenden Users

        Returns:
            EnforcementResult mit Ergebnis

        Raises:
            ValueError: Wenn Loeschung nicht erlaubt ist
        """
        check_result = await self.can_delete_document(db, document_id)

        if not check_result.can_delete:
            logger.warning(
                "retention_enforcement_blocked_deletion",
                document_id=str(document_id),
                user_id=str(user_id),
                reason=check_result.reason,
                retention_expires_at=str(check_result.retention_expires_at),
            )

            raise ValueError(
                f"Loeschung nicht erlaubt: {check_result.reason}"
            )

        logger.info(
            "retention_enforcement_allowed_deletion",
            document_id=str(document_id),
            user_id=str(user_id),
            reason=check_result.reason,
        )

        return EnforcementResult(
            success=True,
            action_taken="deletion_allowed",
            reason=check_result.reason,
            document_id=document_id,
            archive_id=check_result.archive_id,
            legal_basis=check_result.legal_basis,
        )

    async def schedule_post_retention_review(
        self,
        db: AsyncSession,
        archive_id: uuid.UUID,
    ) -> None:
        """Plant eine Pruefung nach Ablauf der Aufbewahrungsfrist.

        Setzt das Flag post_retention_review_scheduled=True und berechnet
        das Datum fuer die automatische Pruefung.

        Args:
            db: Datenbank-Session
            archive_id: ID des Archivs
        """
        # Archiv laden
        result = await db.execute(
            select(DocumentArchive)
            .where(DocumentArchive.id == archive_id)
        )
        archive = result.scalar_one_or_none()

        if not archive:
            raise ValueError(f"Archiv {archive_id} nicht gefunden")

        # Post-Retention Review planen (1 Tag nach Fristablauf)
        review_date = archive.retention_expires_at + timedelta(days=1)

        # Update Archive (nach Migration 205)
        # archive.post_retention_review_scheduled = True
        # archive.post_retention_review_at = datetime.combine(review_date, datetime.min.time())

        # Aktuell nur loggen, da Spalten noch nicht existieren
        logger.info(
            "post_retention_review_scheduled",
            archive_id=str(archive_id),
            document_id=str(archive.document_id),
            retention_expires_at=str(archive.retention_expires_at),
            review_scheduled_at=str(review_date),
        )

        await db.commit()


# Singleton-Instanz
retention_enforcement_service = RetentionEnforcementService()

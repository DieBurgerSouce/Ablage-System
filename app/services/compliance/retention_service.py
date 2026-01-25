"""GoBD Retention Service - Aufbewahrungsfristen-Management.

Verwaltet die gesetzlichen Aufbewahrungsfristen nach GoBD:
- Automatische Fristberechnung bei Archivierung
- Warnungen vor ablaufenden Fristen
- Loeschfreigabe-Workflow
- Compliance-Reporting

Gesetzliche Grundlagen:
- §147 AO (Abgabenordnung): 10 Jahre fuer Buchfuehrungsunterlagen
- §257 HGB (Handelsgesetzbuch): 6-10 Jahre je nach Dokumenttyp
- §14b UStG (Umsatzsteuergesetz): 10 Jahre fuer Rechnungen
"""

import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

import structlog
from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentArchive, RetentionCategory
from app.db.bpmn_models.gobd import (
    RetentionPolicy,
    RetentionDeletionRequest,
    AuditChainEventType,
)
from app.services.compliance.audit_chain_service import log_document_event

logger = structlog.get_logger(__name__)


class RetentionAlertLevel(str, Enum):
    """Alert-Level fuer ablaufende Aufbewahrungsfristen."""
    INFO = "info"  # >180 Tage
    WARNING = "warning"  # 90-180 Tage
    CRITICAL = "critical"  # <90 Tage
    EXPIRED = "expired"  # Abgelaufen


@dataclass
class RetentionAlert:
    """Alert fuer eine ablaufende Aufbewahrungsfrist."""
    archive_id: uuid.UUID
    document_id: uuid.UUID
    category: str
    expires_at: date
    days_remaining: int
    level: RetentionAlertLevel


@dataclass
class RetentionStats:
    """Statistiken zu Aufbewahrungsfristen."""
    total_archived: int
    by_category: Dict[str, int]
    expiring_30_days: int
    expiring_90_days: int
    expiring_180_days: int
    expired: int


# Standard-Aufbewahrungsfristen nach deutschem Recht
DEFAULT_RETENTION_PERIODS: Dict[str, Dict[str, Any]] = {
    "invoice": {
        "years": 10,
        "legal_basis": "§147 AO, §14b UStG",
        "display_name": "Rechnungen",
    },
    "invoice_incoming": {
        "years": 10,
        "legal_basis": "§147 AO, §14b UStG",
        "display_name": "Eingangsrechnungen",
    },
    "invoice_outgoing": {
        "years": 10,
        "legal_basis": "§147 AO, §14b UStG",
        "display_name": "Ausgangsrechnungen",
    },
    "contract": {
        "years": 10,
        "legal_basis": "§257 HGB",
        "display_name": "Vertraege",
    },
    "correspondence": {
        "years": 6,
        "legal_basis": "§257 HGB",
        "display_name": "Geschaeftsbriefe",
    },
    "accounting": {
        "years": 10,
        "legal_basis": "§147 AO, §257 HGB",
        "display_name": "Buchfuehrungsunterlagen",
    },
    "annual_report": {
        "years": 10,
        "legal_basis": "§257 HGB",
        "display_name": "Jahresabschluesse",
    },
    "tax_document": {
        "years": 10,
        "legal_basis": "§147 AO",
        "display_name": "Steuerunterlagen",
    },
    "payroll": {
        "years": 10,
        "legal_basis": "§147 AO",
        "display_name": "Lohnabrechnungen",
    },
    "delivery_note": {
        "years": 6,
        "legal_basis": "§257 HGB",
        "display_name": "Lieferscheine",
    },
    "order": {
        "years": 6,
        "legal_basis": "§257 HGB",
        "display_name": "Bestellungen",
    },
    "quotation": {
        "years": 6,
        "legal_basis": "§257 HGB",
        "display_name": "Angebote",
    },
    "bank_statement": {
        "years": 10,
        "legal_basis": "§147 AO",
        "display_name": "Kontoauszuege",
    },
    "receipt": {
        "years": 10,
        "legal_basis": "§147 AO",
        "display_name": "Belege",
    },
    "other": {
        "years": 6,
        "legal_basis": "§257 HGB",
        "display_name": "Sonstige Dokumente",
    },
}


class RetentionService:
    """Service fuer GoBD-konforme Aufbewahrungsfristen-Verwaltung."""

    def __init__(self):
        self.default_periods = DEFAULT_RETENTION_PERIODS

    def get_retention_years(self, category: str) -> int:
        """Ermittelt die Aufbewahrungsfrist in Jahren fuer eine Kategorie.

        Args:
            category: Dokumentkategorie

        Returns:
            Aufbewahrungsfrist in Jahren (default: 10)
        """
        period = self.default_periods.get(category.lower())
        if period:
            return period["years"]
        return 10  # Default: 10 Jahre nach §147 AO

    def calculate_expiry_date(
        self,
        category: str,
        document_date: date,
        custom_years: Optional[int] = None,
    ) -> date:
        """Berechnet das Ablaufdatum der Aufbewahrungsfrist.

        Die Frist beginnt am Ende des Kalenderjahres, in dem
        das Dokument erstellt wurde.

        Beispiel: Rechnung vom 15.03.2024 → Frist endet 31.12.2034

        Args:
            category: Dokumentkategorie
            document_date: Datum des Dokuments
            custom_years: Optionale abweichende Frist

        Returns:
            Ablaufdatum der Aufbewahrungsfrist
        """
        years = custom_years if custom_years is not None else self.get_retention_years(category)

        # Frist beginnt am Ende des Kalenderjahres
        year_end = date(document_date.year, 12, 31)
        expiry = date(year_end.year + years, 12, 31)

        return expiry

    async def get_retention_policy(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        category: str,
    ) -> Optional[RetentionPolicy]:
        """Holt die Aufbewahrungsrichtlinie fuer eine Kategorie.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            category: Dokumentkategorie

        Returns:
            RetentionPolicy oder None (dann Default verwenden)
        """
        result = await db.execute(
            select(RetentionPolicy)
            .where(
                and_(
                    RetentionPolicy.company_id == company_id,
                    RetentionPolicy.document_category == category.lower(),
                    RetentionPolicy.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create_retention_policy(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        category: str,
        retention_years: int,
        legal_basis: Optional[str] = None,
        warning_days_before: int = 180,
        critical_days_before: int = 30,
        require_approval_for_delete: bool = True,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> RetentionPolicy:
        """Erstellt eine neue Aufbewahrungsrichtlinie.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            category: Dokumentkategorie
            retention_years: Aufbewahrungsdauer
            legal_basis: Gesetzliche Grundlage
            warning_days_before: Tage vor Ablauf fuer Warnung
            critical_days_before: Tage vor Ablauf fuer kritische Warnung
            require_approval_for_delete: Freigabe vor Loeschung
            created_by_id: ID des erstellenden Users

        Returns:
            Die erstellte RetentionPolicy
        """
        # Hole Default-Werte falls vorhanden
        defaults = self.default_periods.get(category.lower(), {})

        policy = RetentionPolicy(
            company_id=company_id,
            name=defaults.get("display_name", category),
            document_category=category.lower(),
            retention_years=retention_years,
            legal_basis=legal_basis or defaults.get("legal_basis"),
            warning_days_before=warning_days_before,
            critical_days_before=critical_days_before,
            require_approval_for_delete=require_approval_for_delete,
            created_by_id=created_by_id,
        )

        db.add(policy)
        await db.flush()

        logger.info(
            "retention_policy_created",
            company_id=str(company_id),
            category=category,
            retention_years=retention_years,
        )

        return policy

    async def get_expiring_archives(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        days_ahead: int = 180,
    ) -> List[RetentionAlert]:
        """Findet Archive deren Aufbewahrungsfrist bald ablaeuft.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            days_ahead: Wie viele Tage voraus pruefen

        Returns:
            Liste von RetentionAlert
        """
        today = date.today()
        cutoff_date = today + timedelta(days=days_ahead)

        result = await db.execute(
            select(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at <= cutoff_date,
                )
            )
            .order_by(DocumentArchive.retention_expires_at)
        )
        archives = result.scalars().all()

        alerts = []
        for archive in archives:
            days_remaining = (archive.retention_expires_at - today).days

            # Bestimme Alert-Level
            if days_remaining < 0:
                level = RetentionAlertLevel.EXPIRED
            elif days_remaining <= 30:
                level = RetentionAlertLevel.CRITICAL
            elif days_remaining <= 90:
                level = RetentionAlertLevel.WARNING
            else:
                level = RetentionAlertLevel.INFO

            alerts.append(
                RetentionAlert(
                    archive_id=archive.id,
                    document_id=archive.document_id,
                    category=archive.retention_category,
                    expires_at=archive.retention_expires_at,
                    days_remaining=days_remaining,
                    level=level,
                )
            )

        return alerts

    async def get_expired_archives(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[DocumentArchive]:
        """Findet Archive deren Aufbewahrungsfrist abgelaufen ist.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Liste von abgelaufenen DocumentArchive
        """
        today = date.today()

        result = await db.execute(
            select(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at < today,
                )
            )
            .order_by(DocumentArchive.retention_expires_at)
        )
        return list(result.scalars().all())

    async def request_deletion(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        archive_id: uuid.UUID,
        reason: str,
        requested_by_id: uuid.UUID,
    ) -> RetentionDeletionRequest:
        """Erstellt eine Loeschanfrage fuer ein abgelaufenes Archiv.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            archive_id: Archiv-ID
            reason: Begruendung
            requested_by_id: User der die Anfrage stellt

        Returns:
            RetentionDeletionRequest

        Raises:
            ValueError: Wenn Archiv nicht gefunden oder nicht abgelaufen
        """
        # Pruefe ob Archiv existiert und abgelaufen ist
        archive = await db.get(DocumentArchive, archive_id)
        if not archive or archive.company_id != company_id:
            raise ValueError("Archiv nicht gefunden")

        if archive.retention_expires_at >= date.today():
            raise ValueError("Aufbewahrungsfrist ist noch nicht abgelaufen")

        # Erstelle Anfrage
        request = RetentionDeletionRequest(
            archive_id=archive_id,
            company_id=company_id,
            reason=reason,
            retention_expired_at=datetime.combine(
                archive.retention_expires_at, datetime.min.time()
            ),
            requested_by_id=requested_by_id,
        )

        db.add(request)
        await db.flush()

        # Log in Audit-Chain
        await log_document_event(
            db=db,
            company_id=company_id,
            event_type=AuditChainEventType.RETENTION_DELETION_APPROVED,
            document_id=archive.document_id,
            event_data={
                "request_id": str(request.id),
                "archive_id": str(archive_id),
                "expired_at": archive.retention_expires_at.isoformat(),
            },
            user_id=requested_by_id,
        )

        logger.info(
            "deletion_request_created",
            company_id=str(company_id),
            archive_id=str(archive_id),
            request_id=str(request.id),
        )

        return request

    async def approve_deletion(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        request_id: uuid.UUID,
        approved_by_id: uuid.UUID,
        comment: Optional[str] = None,
    ) -> RetentionDeletionRequest:
        """Genehmigt eine Loeschanfrage.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            request_id: Anfrage-ID
            approved_by_id: User der genehmigt
            comment: Optionaler Kommentar

        Returns:
            Aktualisierte RetentionDeletionRequest

        Raises:
            ValueError: Wenn Anfrage nicht gefunden oder bereits bearbeitet
        """
        result = await db.execute(
            select(RetentionDeletionRequest)
            .where(
                and_(
                    RetentionDeletionRequest.id == request_id,
                    RetentionDeletionRequest.company_id == company_id,
                    RetentionDeletionRequest.status == "pending",
                )
            )
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ValueError("Anfrage nicht gefunden oder bereits bearbeitet")

        request.status = "approved"
        request.approved_at = datetime.utcnow()
        request.approved_by_id = approved_by_id
        request.approval_comment = comment

        await db.flush()

        logger.info(
            "deletion_request_approved",
            request_id=str(request_id),
            approved_by=str(approved_by_id),
        )

        return request

    async def reject_deletion(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        request_id: uuid.UUID,
        rejected_by_id: uuid.UUID,
        reason: str,
    ) -> RetentionDeletionRequest:
        """Lehnt eine Loeschanfrage ab.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            request_id: Anfrage-ID
            rejected_by_id: User der ablehnt
            reason: Ablehnungsgrund

        Returns:
            Aktualisierte RetentionDeletionRequest

        Raises:
            ValueError: Wenn Anfrage nicht gefunden oder bereits bearbeitet
        """
        result = await db.execute(
            select(RetentionDeletionRequest)
            .where(
                and_(
                    RetentionDeletionRequest.id == request_id,
                    RetentionDeletionRequest.company_id == company_id,
                    RetentionDeletionRequest.status == "pending",
                )
            )
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ValueError("Anfrage nicht gefunden oder bereits bearbeitet")

        request.status = "rejected"
        request.rejected_at = datetime.utcnow()
        request.rejected_by_id = rejected_by_id
        request.rejection_reason = reason

        await db.flush()

        logger.info(
            "deletion_request_rejected",
            request_id=str(request_id),
            rejected_by=str(rejected_by_id),
        )

        return request

    async def get_retention_statistics(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> RetentionStats:
        """Holt Statistiken zu Aufbewahrungsfristen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            RetentionStats mit Uebersicht
        """
        today = date.today()

        # Gesamtanzahl
        total_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(DocumentArchive.company_id == company_id)
        )
        total = total_result.scalar() or 0

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

        # Ablaufend in 30 Tagen
        exp_30_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at >= today,
                    DocumentArchive.retention_expires_at <= today + timedelta(days=30),
                )
            )
        )
        expiring_30 = exp_30_result.scalar() or 0

        # Ablaufend in 90 Tagen
        exp_90_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at >= today,
                    DocumentArchive.retention_expires_at <= today + timedelta(days=90),
                )
            )
        )
        expiring_90 = exp_90_result.scalar() or 0

        # Ablaufend in 180 Tagen
        exp_180_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at >= today,
                    DocumentArchive.retention_expires_at <= today + timedelta(days=180),
                )
            )
        )
        expiring_180 = exp_180_result.scalar() or 0

        # Abgelaufen
        expired_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at < today,
                )
            )
        )
        expired = expired_result.scalar() or 0

        return RetentionStats(
            total_archived=total,
            by_category=by_category,
            expiring_30_days=expiring_30,
            expiring_90_days=expiring_90,
            expiring_180_days=expiring_180,
            expired=expired,
        )

    async def send_retention_reminders(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> int:
        """Sendet Erinnerungen fuer bald ablaufende Aufbewahrungsfristen.

        Aktualisiert den reminder_sent Status in DocumentArchive.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Anzahl gesendeter Erinnerungen
        """
        today = date.today()
        reminder_date = today + timedelta(days=180)  # 6 Monate vorher

        # Finde Archive die bald ablaufen und noch keine Erinnerung bekommen haben
        result = await db.execute(
            select(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at <= reminder_date,
                    DocumentArchive.retention_reminder_sent == False,
                )
            )
        )
        archives = result.scalars().all()

        sent_count = 0
        for archive in archives:
            # TODO: Tatsaechliche Benachrichtigung senden (Slack, Email, etc.)

            # Markiere als gesendet
            archive.retention_reminder_sent = True
            archive.retention_reminder_at = datetime.utcnow()
            sent_count += 1

        await db.flush()

        if sent_count > 0:
            logger.info(
                "retention_reminders_sent",
                company_id=str(company_id),
                count=sent_count,
            )

        return sent_count

    async def initialize_company_policies(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> List[RetentionPolicy]:
        """Initialisiert Standard-Aufbewahrungsrichtlinien fuer eine Company.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            created_by_id: Optional - Ersteller

        Returns:
            Liste der erstellten Policies
        """
        created_policies = []

        for category, defaults in self.default_periods.items():
            # Pruefe ob bereits existiert
            existing = await self.get_retention_policy(db, company_id, category)
            if existing:
                continue

            policy = await self.create_retention_policy(
                db=db,
                company_id=company_id,
                category=category,
                retention_years=defaults["years"],
                legal_basis=defaults.get("legal_basis"),
                created_by_id=created_by_id,
            )
            created_policies.append(policy)

        logger.info(
            "company_retention_policies_initialized",
            company_id=str(company_id),
            policies_created=len(created_policies),
        )

        return created_policies


# Singleton-Instanz
retention_service = RetentionService()

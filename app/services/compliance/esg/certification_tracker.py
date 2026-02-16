"""
Zertifizierungs-Tracker.

Verwaltung und Tracking von Nachhaltigkeits-Zertifizierungen.
"""

from datetime import date, datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
import structlog

from app.db.models_esg import ESGCertification, CertificationStatus, ESGCategory

logger = structlog.get_logger(__name__)


# Bekannte Zertifizierungstypen
CERTIFICATION_TYPES = {
    # Environmental
    "ISO_14001": {
        "name": "ISO 14001",
        "category": "environmental",
        "description": "Umweltmanagementsystem",
    },
    "ISO_50001": {
        "name": "ISO 50001",
        "category": "environmental",
        "description": "Energiemanagementsystem",
    },
    "EMAS": {
        "name": "EMAS",
        "category": "environmental",
        "description": "Eco-Management and Audit Scheme",
    },
    "BLUE_ANGEL": {
        "name": "Blauer Engel",
        "category": "environmental",
        "description": "Deutsches Umweltzeichen",
    },
    "FSC": {
        "name": "FSC",
        "category": "environmental",
        "description": "Forest Stewardship Council",
    },

    # Social
    "SA8000": {
        "name": "SA8000",
        "category": "social",
        "description": "Social Accountability Standard",
    },
    "ISO_45001": {
        "name": "ISO 45001",
        "category": "social",
        "description": "Arbeitsschutzmanagementsystem",
    },
    "FAIR_TRADE": {
        "name": "Fairtrade",
        "category": "social",
        "description": "Fair-Trade-Zertifizierung",
    },

    # Governance
    "ISO_37001": {
        "name": "ISO 37001",
        "category": "governance",
        "description": "Anti-Korruptions-Managementsystem",
    },
    "ISO_27001": {
        "name": "ISO 27001",
        "category": "governance",
        "description": "Informationssicherheitsmanagement",
    },
    "SOC2": {
        "name": "SOC 2",
        "category": "governance",
        "description": "Service Organization Control",
    },

    # Integriert
    "B_CORP": {
        "name": "B Corp",
        "category": "governance",
        "description": "Certified B Corporation",
    },
    "ECOVADIS": {
        "name": "EcoVadis",
        "category": "governance",
        "description": "EcoVadis Nachhaltigkeitsrating",
    },
}


class CertificationTracker:
    """
    Service für Zertifizierungs-Tracking.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def get_certification_types() -> Dict[str, Dict[str, Any]]:
        """Gebe bekannte Zertifizierungstypen zurück."""
        return CERTIFICATION_TYPES

    async def add_certification(
        self,
        company_id: UUID,
        certification_type: str,
        certification_name: str,
        issue_date: date,
        category: str,
        certification_body: Optional[str] = None,
        certificate_number: Optional[str] = None,
        expiry_date: Optional[date] = None,
        scope_description: Optional[str] = None,
        applicable_sites: Optional[List[str]] = None,
        document_id: Optional[UUID] = None,
        next_audit_date: Optional[date] = None,
        reminder_days_before: int = 90,
        notes: Optional[str] = None,
    ) -> ESGCertification:
        """
        Fuege eine neue Zertifizierung hinzu.
        """
        # Validiere Kategorie
        valid_categories = [c.value for c in ESGCategory]
        if category not in valid_categories:
            raise ValueError(f"Ungültige Kategorie. Erlaubt: {valid_categories}")

        # Bestimme Status
        status = CertificationStatus.ACTIVE
        if expiry_date and expiry_date < date.today():
            status = CertificationStatus.EXPIRED

        certification = ESGCertification(
            company_id=company_id,
            certification_type=certification_type,
            certification_name=certification_name,
            certification_body=certification_body,
            certificate_number=certificate_number,
            category=category,
            issue_date=issue_date,
            expiry_date=expiry_date,
            status=status,
            scope_description=scope_description,
            applicable_sites=applicable_sites or [],
            document_id=document_id,
            next_audit_date=next_audit_date,
            reminder_days_before=reminder_days_before,
            notes=notes,
        )

        self.db.add(certification)
        await self.db.commit()
        await self.db.refresh(certification)

        logger.info(
            "certification_added",
            certification_id=str(certification.id),
            company_id=str(company_id),
            type=certification_type,
        )

        return certification

    async def get_certifications(
        self,
        company_id: UUID,
        category: Optional[str] = None,
        status: Optional[str] = None,
        include_expired: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole Zertifizierungen.
        """
        query = select(ESGCertification).where(
            ESGCertification.company_id == company_id
        )

        if category:
            query = query.where(ESGCertification.category == category)
        if status:
            query = query.where(ESGCertification.status == status)
        elif not include_expired:
            query = query.where(ESGCertification.status != CertificationStatus.EXPIRED)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(ESGCertification.expiry_date.asc().nullsfirst())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        certifications = result.scalars().all()

        return [
            {
                "id": str(c.id),
                "certification_type": c.certification_type,
                "certification_name": c.certification_name,
                "certification_body": c.certification_body,
                "certificate_number": c.certificate_number,
                "category": c.category,
                "issue_date": c.issue_date.isoformat() if c.issue_date else None,
                "expiry_date": c.expiry_date.isoformat() if c.expiry_date else None,
                "status": c.status,
                "next_audit_date": c.next_audit_date.isoformat() if c.next_audit_date else None,
                "days_until_expiry": (c.expiry_date - date.today()).days if c.expiry_date else None,
            }
            for c in certifications
        ], total

    async def get_certification_detail(
        self,
        certification_id: UUID,
        company_id: UUID,
    ) -> Optional[dict]:
        """Hole Zertifizierungs-Details."""
        result = await self.db.execute(
            select(ESGCertification).where(
                and_(
                    ESGCertification.id == certification_id,
                    ESGCertification.company_id == company_id,
                )
            )
        )
        cert = result.scalar_one_or_none()

        if not cert:
            return None

        return {
            "id": str(cert.id),
            "certification_type": cert.certification_type,
            "certification_name": cert.certification_name,
            "certification_body": cert.certification_body,
            "certificate_number": cert.certificate_number,
            "category": cert.category,
            "issue_date": cert.issue_date.isoformat() if cert.issue_date else None,
            "expiry_date": cert.expiry_date.isoformat() if cert.expiry_date else None,
            "status": cert.status,
            "scope_description": cert.scope_description,
            "applicable_sites": cert.applicable_sites,
            "document_id": str(cert.document_id) if cert.document_id else None,
            "last_audit_date": cert.last_audit_date.isoformat() if cert.last_audit_date else None,
            "next_audit_date": cert.next_audit_date.isoformat() if cert.next_audit_date else None,
            "audit_findings": cert.audit_findings,
            "reminder_days_before": cert.reminder_days_before,
            "notes": cert.notes,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
        }

    async def get_expiring_soon(
        self,
        company_id: UUID,
        days: int = 90,
    ) -> List[dict]:
        """
        Hole bald ablaufende Zertifizierungen.
        """
        threshold = date.today() + timedelta(days=days)

        result = await self.db.execute(
            select(ESGCertification).where(
                and_(
                    ESGCertification.company_id == company_id,
                    ESGCertification.status == CertificationStatus.ACTIVE,
                    ESGCertification.expiry_date <= threshold,
                    ESGCertification.expiry_date >= date.today(),
                )
            ).order_by(ESGCertification.expiry_date.asc())
        )
        certifications = result.scalars().all()

        return [
            {
                "id": str(c.id),
                "certification_type": c.certification_type,
                "certification_name": c.certification_name,
                "expiry_date": c.expiry_date.isoformat() if c.expiry_date else None,
                "days_until_expiry": (c.expiry_date - date.today()).days if c.expiry_date else None,
                "category": c.category,
            }
            for c in certifications
        ]

    async def get_upcoming_audits(
        self,
        company_id: UUID,
        days: int = 60,
    ) -> List[dict]:
        """
        Hole anstehende Audits.
        """
        threshold = date.today() + timedelta(days=days)

        result = await self.db.execute(
            select(ESGCertification).where(
                and_(
                    ESGCertification.company_id == company_id,
                    ESGCertification.status == CertificationStatus.ACTIVE,
                    ESGCertification.next_audit_date <= threshold,
                    ESGCertification.next_audit_date >= date.today(),
                )
            ).order_by(ESGCertification.next_audit_date.asc())
        )
        certifications = result.scalars().all()

        return [
            {
                "id": str(c.id),
                "certification_type": c.certification_type,
                "certification_name": c.certification_name,
                "next_audit_date": c.next_audit_date.isoformat() if c.next_audit_date else None,
                "days_until_audit": (c.next_audit_date - date.today()).days if c.next_audit_date else None,
            }
            for c in certifications
        ]

    async def record_audit(
        self,
        certification_id: UUID,
        company_id: UUID,
        audit_date: date,
        findings: Optional[List[str]] = None,
        next_audit_date: Optional[date] = None,
    ) -> bool:
        """
        Erfasse ein durchgeführtes Audit.
        """
        result = await self.db.execute(
            select(ESGCertification).where(
                and_(
                    ESGCertification.id == certification_id,
                    ESGCertification.company_id == company_id,
                )
            )
        )
        cert = result.scalar_one_or_none()

        if not cert:
            return False

        cert.last_audit_date = audit_date
        if next_audit_date:
            cert.next_audit_date = next_audit_date
        if findings is not None:
            cert.audit_findings = findings

        await self.db.commit()

        logger.info(
            "certification_audit_recorded",
            certification_id=str(certification_id),
            audit_date=audit_date.isoformat(),
        )

        return True

    async def update_status(
        self,
        certification_id: UUID,
        company_id: UUID,
        new_status: str,
    ) -> bool:
        """
        Aktualisiere Zertifizierungsstatus.
        """
        result = await self.db.execute(
            select(ESGCertification).where(
                and_(
                    ESGCertification.id == certification_id,
                    ESGCertification.company_id == company_id,
                )
            )
        )
        cert = result.scalar_one_or_none()

        if not cert:
            return False

        # Validiere Status
        valid_statuses = [s.value for s in CertificationStatus]
        if new_status not in valid_statuses:
            raise ValueError(f"Ungültiger Status: {new_status}")

        cert.status = new_status
        await self.db.commit()

        return True

    async def check_expired_certifications(
        self,
        company_id: UUID,
    ) -> int:
        """
        Prüfe und aktualisiere abgelaufene Zertifizierungen.

        Returns:
            Anzahl der aktualisierten Zertifizierungen.
        """
        result = await self.db.execute(
            select(ESGCertification).where(
                and_(
                    ESGCertification.company_id == company_id,
                    ESGCertification.status == CertificationStatus.ACTIVE,
                    ESGCertification.expiry_date < date.today(),
                )
            )
        )
        expired = result.scalars().all()

        count = 0
        for cert in expired:
            cert.status = CertificationStatus.EXPIRED
            count += 1

        if count > 0:
            await self.db.commit()
            logger.info(
                "certifications_marked_expired",
                company_id=str(company_id),
                count=count,
            )

        return count

    async def get_certification_summary(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Hole Zertifizierungs-Zusammenfassung.
        """
        result = await self.db.execute(
            select(ESGCertification).where(
                ESGCertification.company_id == company_id
            )
        )
        all_certs = result.scalars().all()

        by_category = {"environmental": 0, "social": 0, "governance": 0}
        by_status = {"active": 0, "expired": 0, "pending": 0, "revoked": 0}
        expiring_soon = 0

        for cert in all_certs:
            # Nach Kategorie
            cat = cert.category or "governance"
            by_category[cat] = by_category.get(cat, 0) + 1

            # Nach Status
            stat = cert.status or "active"
            by_status[stat] = by_status.get(stat, 0) + 1

            # Bald ablaufend (90 Tage)
            if (
                cert.status == CertificationStatus.ACTIVE and
                cert.expiry_date and
                cert.expiry_date <= date.today() + timedelta(days=90) and
                cert.expiry_date >= date.today()
            ):
                expiring_soon += 1

        return {
            "total": len(all_certs),
            "active": by_status.get("active", 0),
            "expired": by_status.get("expired", 0),
            "expiring_soon": expiring_soon,
            "by_category": by_category,
            "by_status": by_status,
        }


def get_certification_tracker(db: AsyncSession) -> CertificationTracker:
    """Factory-Funktion für CertificationTracker."""
    return CertificationTracker(db)

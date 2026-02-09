"""
Portal-Reklamationsservice.

Kunden koennen Reklamationen einreichen und verfolgen.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID
import secrets

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.db.models_portal import (
    PortalComplaint, PortalUser, ComplaintStatus, ComplaintType
)

logger = structlog.get_logger(__name__)


def generate_reference_number() -> str:
    """Generiere eindeutige Referenznummer."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_part = secrets.token_hex(4).upper()
    return f"RK-{timestamp}-{random_part}"


class PortalComplaintService:
    """
    Service fuer Reklamationen im Kundenportal.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_complaint(
        self,
        portal_user: PortalUser,
        complaint_type: str,
        subject: str,
        description: str,
        document_id: Optional[UUID] = None,
        invoice_tracking_id: Optional[UUID] = None,
        priority: str = "normal",
        metadata: Optional[dict] = None,
    ) -> PortalComplaint:
        """
        Reiche eine neue Reklamation ein.
        """
        # Validiere complaint_type
        valid_types = [t.value for t in ComplaintType]
        if complaint_type not in valid_types:
            raise ValueError(f"Ungueltiger Reklamationstyp. Erlaubt: {valid_types}")

        # Validiere priority
        valid_priorities = ["low", "normal", "high", "urgent"]
        if priority not in valid_priorities:
            priority = "normal"

        complaint = PortalComplaint(
            company_id=portal_user.company_id,
            entity_id=portal_user.entity_id,
            submitted_by_id=portal_user.id,
            document_id=document_id,
            invoice_tracking_id=invoice_tracking_id,
            reference_number=generate_reference_number(),
            complaint_type=complaint_type,
            subject=subject,
            description=description,
            status=ComplaintStatus.NEW,
            priority=priority,
            metadata=metadata or {},
        )

        self.db.add(complaint)
        await self.db.commit()
        await self.db.refresh(complaint)

        logger.info(
            "portal_complaint_submitted",
            complaint_id=str(complaint.id),
            reference_number=complaint.reference_number,
            entity_id=str(portal_user.entity_id),
            complaint_type=complaint_type,
        )

        return complaint

    async def get_complaints(
        self,
        entity_id: UUID,
        company_id: UUID,
        status: Optional[str] = None,
        complaint_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole alle Reklamationen fuer einen Entity.
        """
        query = select(PortalComplaint).where(
            and_(
                PortalComplaint.entity_id == entity_id,
                PortalComplaint.company_id == company_id,
            )
        )

        if status:
            query = query.where(PortalComplaint.status == status)
        if complaint_type:
            query = query.where(PortalComplaint.complaint_type == complaint_type)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(PortalComplaint.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        complaints = result.scalars().all()

        complaint_list = []
        for comp in complaints:
            complaint_list.append({
                "id": str(comp.id),
                "reference_number": comp.reference_number,
                "complaint_type": comp.complaint_type,
                "subject": comp.subject,
                "status": comp.status,
                "priority": comp.priority,
                "created_at": comp.created_at.isoformat() if comp.created_at else None,
                "first_response_at": comp.first_response_at.isoformat() if comp.first_response_at else None,
                "resolved_at": comp.resolved_at.isoformat() if comp.resolved_at else None,
                "has_resolution": comp.resolution is not None,
            })

        return complaint_list, total

    async def get_complaint_detail(
        self,
        complaint_id: UUID,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[dict]:
        """
        Hole Details einer Reklamation.
        """
        result = await self.db.execute(
            select(PortalComplaint).where(
                and_(
                    PortalComplaint.id == complaint_id,
                    PortalComplaint.entity_id == entity_id,
                    PortalComplaint.company_id == company_id,
                )
            )
        )
        complaint = result.scalar_one_or_none()

        if not complaint:
            return None

        return {
            "id": str(complaint.id),
            "reference_number": complaint.reference_number,
            "complaint_type": complaint.complaint_type,
            "subject": complaint.subject,
            "description": complaint.description,
            "status": complaint.status,
            "priority": complaint.priority,
            "document_id": str(complaint.document_id) if complaint.document_id else None,
            "invoice_tracking_id": str(complaint.invoice_tracking_id) if complaint.invoice_tracking_id else None,
            "resolution": complaint.resolution,  # Antwort vom Unternehmen
            "created_at": complaint.created_at.isoformat() if complaint.created_at else None,
            "updated_at": complaint.updated_at.isoformat() if complaint.updated_at else None,
            "first_response_at": complaint.first_response_at.isoformat() if complaint.first_response_at else None,
            "resolved_at": complaint.resolved_at.isoformat() if complaint.resolved_at else None,
            "closed_at": complaint.closed_at.isoformat() if complaint.closed_at else None,
            "metadata": complaint.complaint_metadata,
        }

    async def add_information(
        self,
        complaint_id: UUID,
        portal_user: PortalUser,
        additional_info: str,
        attachment_ids: Optional[List[str]] = None,
    ) -> bool:
        """
        Fuege zusaetzliche Informationen zu einer Reklamation hinzu.

        Nur moeglich wenn nicht abgeschlossen.
        """
        result = await self.db.execute(
            select(PortalComplaint).where(
                and_(
                    PortalComplaint.id == complaint_id,
                    PortalComplaint.entity_id == portal_user.entity_id,
                    PortalComplaint.company_id == portal_user.company_id,
                    PortalComplaint.status.notin_([
                        ComplaintStatus.CLOSED,
                        ComplaintStatus.RESOLVED
                    ]),
                )
            )
        )
        complaint = result.scalar_one_or_none()

        if not complaint:
            return False

        # Fuege Info zum Metadata hinzu
        metadata = complaint.complaint_metadata or {}
        updates = metadata.get("customer_updates", [])
        updates.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": additional_info,
            "attachments": attachment_ids or [],
        })
        metadata["customer_updates"] = updates
        complaint.complaint_metadata = metadata
        complaint.updated_at = datetime.now(timezone.utc)

        await self.db.commit()

        logger.info(
            "portal_complaint_info_added",
            complaint_id=str(complaint_id),
        )

        return True

    async def get_complaint_summary(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> dict:
        """
        Hole Zusammenfassung aller Reklamationen.
        """
        result = await self.db.execute(
            select(PortalComplaint).where(
                and_(
                    PortalComplaint.entity_id == entity_id,
                    PortalComplaint.company_id == company_id,
                )
            )
        )
        complaints = result.scalars().all()

        total = len(complaints)
        by_status = {}
        by_type = {}

        for comp in complaints:
            # Nach Status
            status = comp.status or "unknown"
            by_status[status] = by_status.get(status, 0) + 1

            # Nach Typ
            c_type = comp.complaint_type or "unknown"
            by_type[c_type] = by_type.get(c_type, 0) + 1

        open_count = sum(
            count for status, count in by_status.items()
            if status in [
                ComplaintStatus.NEW.value if hasattr(ComplaintStatus.NEW, 'value') else ComplaintStatus.NEW,
                ComplaintStatus.IN_REVIEW.value if hasattr(ComplaintStatus.IN_REVIEW, 'value') else ComplaintStatus.IN_REVIEW,
                "new", "in_review"
            ]
        )

        return {
            "total_complaints": total,
            "open_complaints": open_count,
            "by_status": by_status,
            "by_type": by_type,
        }

    @staticmethod
    def get_complaint_types() -> List[dict]:
        """Gebe verfuegbare Reklamationstypen zurueck."""
        return [
            {
                "value": ComplaintType.INVOICE_ERROR.value,
                "label": "Rechnungsfehler",
                "description": "Fehler in der Rechnung (Betrag, Artikel, etc.)",
            },
            {
                "value": ComplaintType.DELIVERY_ISSUE.value,
                "label": "Lieferproblem",
                "description": "Problem mit der Lieferung (Verzoegerung, Beschaedigung, etc.)",
            },
            {
                "value": ComplaintType.QUALITY_ISSUE.value,
                "label": "Qualitaetsmangel",
                "description": "Mangel an Produkt- oder Servicequalitaet",
            },
            {
                "value": ComplaintType.PAYMENT_DISPUTE.value,
                "label": "Zahlungsstreit",
                "description": "Unstimmigkeit bei Zahlungen",
            },
            {
                "value": ComplaintType.OTHER.value,
                "label": "Sonstiges",
                "description": "Andere Anliegen",
            },
        ]


def get_portal_complaint_service(db: AsyncSession) -> PortalComplaintService:
    """Factory-Funktion fuer PortalComplaintService."""
    return PortalComplaintService(db)

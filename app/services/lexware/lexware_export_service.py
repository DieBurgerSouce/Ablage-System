"""Lexware Export Service.

Exportiert Daten zurück an Lexware:
- Kunden/Lieferanten-Stammdaten
- Rechnungsstatus-Updates
- Zahlungs-Bestätigungen
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict
from uuid import UUID, uuid4
from enum import Enum
from decimal import Decimal
import csv
import io

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger(__name__)

class LexwareExportType(str, Enum):
    CUSTOMERS = "customers"
    SUPPLIERS = "suppliers"
    INVOICES = "invoices"
    PAYMENTS = "payments"

class LexwareExportStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    DOWNLOADED = "downloaded"
    ERROR = "error"

@dataclass
class LexwareExportJob:
    """Export-Auftrag für Lexware."""
    id: str
    company_id: str
    export_type: LexwareExportType
    status: LexwareExportStatus = LexwareExportStatus.PENDING
    record_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    csv_content: Optional[str] = None
    error_message: Optional[str] = None

# In-memory store
_export_jobs: Dict[str, LexwareExportJob] = {}

class LexwareExportService:
    """Lexware Bidirektional-Export Service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_customers(self, company_id: UUID) -> LexwareExportJob:
        """Exportiert Kunden für Lexware-Import."""
        from app.db.models import BusinessEntity
        stmt = (
            select(BusinessEntity)
            .where(BusinessEntity.company_id == company_id)
            .where(BusinessEntity.entity_type == "customer")
            .order_by(BusinessEntity.name)
        )
        result = await self.db.execute(stmt)
        entities = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)

        # Lexware customer import header
        writer.writerow([
            "Kundennummer", "Firma", "Anrede", "Vorname", "Nachname",
            "Strasse", "PLZ", "Ort", "Land", "Telefon", "E-Mail",
            "Steuernummer", "USt-IdNr"
        ])

        for entity in entities:
            addr = entity.address or {}
            writer.writerow([
                entity.external_id or "",
                entity.name,
                addr.get("salutation", ""),
                addr.get("first_name", ""),
                addr.get("last_name", ""),
                addr.get("street", ""),
                addr.get("zip_code", ""),
                addr.get("city", ""),
                addr.get("country", "DE"),
                entity.phone or "",
                entity.email or "",
                entity.tax_number or "",
                entity.vat_id or "",
            ])

        job = LexwareExportJob(
            id=str(uuid4()),
            company_id=str(company_id),
            export_type=LexwareExportType.CUSTOMERS,
            status=LexwareExportStatus.READY,
            record_count=len(entities),
            completed_at=datetime.now(timezone.utc),
            csv_content=output.getvalue(),
        )
        _export_jobs[job.id] = job
        logger.info("lexware_export_customers", count=len(entities))
        return job

    async def export_suppliers(self, company_id: UUID) -> LexwareExportJob:
        """Exportiert Lieferanten für Lexware-Import."""
        from app.db.models import BusinessEntity
        stmt = (
            select(BusinessEntity)
            .where(BusinessEntity.company_id == company_id)
            .where(BusinessEntity.entity_type == "supplier")
            .order_by(BusinessEntity.name)
        )
        result = await self.db.execute(stmt)
        entities = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)

        writer.writerow([
            "Lieferantennummer", "Firma", "Anrede", "Vorname", "Nachname",
            "Strasse", "PLZ", "Ort", "Land", "Telefon", "E-Mail",
            "Steuernummer", "USt-IdNr", "IBAN", "BIC"
        ])

        for entity in entities:
            addr = entity.address or {}
            bank = entity.bank_details or {}
            writer.writerow([
                entity.external_id or "",
                entity.name,
                addr.get("salutation", ""),
                addr.get("first_name", ""),
                addr.get("last_name", ""),
                addr.get("street", ""),
                addr.get("zip_code", ""),
                addr.get("city", ""),
                addr.get("country", "DE"),
                entity.phone or "",
                entity.email or "",
                entity.tax_number or "",
                entity.vat_id or "",
                bank.get("iban", ""),
                bank.get("bic", ""),
            ])

        job = LexwareExportJob(
            id=str(uuid4()),
            company_id=str(company_id),
            export_type=LexwareExportType.SUPPLIERS,
            status=LexwareExportStatus.READY,
            record_count=len(entities),
            completed_at=datetime.now(timezone.utc),
            csv_content=output.getvalue(),
        )
        _export_jobs[job.id] = job
        logger.info("lexware_export_suppliers", count=len(entities))
        return job

    async def export_payment_status(self, company_id: UUID) -> LexwareExportJob:
        """Exportiert Zahlungsstatus-Updates für Lexware."""
        from app.db.models import InvoiceTracking
        stmt = (
            select(InvoiceTracking)
            .where(InvoiceTracking.company_id == company_id)
            .where(InvoiceTracking.status.in_(["paid", "partial"]))
            .order_by(InvoiceTracking.updated_at.desc())
            .limit(500)
        )
        result = await self.db.execute(stmt)
        trackings = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)

        writer.writerow([
            "Rechnungsnummer", "Status", "Bezahlter Betrag", "Zahlungsdatum",
            "Restbetrag", "Zahlungsart"
        ])

        for tracking in trackings:
            writer.writerow([
                tracking.invoice_number or "",
                tracking.status or "",
                f"{tracking.paid_amount:.2f}" if tracking.paid_amount else "0.00",
                tracking.payment_date.strftime("%d.%m.%Y") if tracking.payment_date else "",
                f"{(tracking.amount - (tracking.paid_amount or 0)):.2f}" if tracking.amount else "0.00",
                tracking.payment_method or "",
            ])

        job = LexwareExportJob(
            id=str(uuid4()),
            company_id=str(company_id),
            export_type=LexwareExportType.PAYMENTS,
            status=LexwareExportStatus.READY,
            record_count=len(trackings),
            completed_at=datetime.now(timezone.utc),
            csv_content=output.getvalue(),
        )
        _export_jobs[job.id] = job
        logger.info("lexware_export_payments", count=len(trackings))
        return job

    def get_job(self, job_id: str) -> Optional[LexwareExportJob]:
        return _export_jobs.get(job_id)

    def list_jobs(self, company_id: str, limit: int = 20) -> List[LexwareExportJob]:
        jobs = [j for j in _export_jobs.values() if j.company_id == company_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

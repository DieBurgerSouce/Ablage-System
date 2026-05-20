"""Cross-Tenant Reports API - Aggregierte Statistiken über alle Mandanten.

Dieser Router bietet Superusern/Admins einen Überblick über alle
Firmen-Mandanten in der Installation.

Security:
---------
- ALLE Endpoints erfordern Superuser-Berechtigung
- RLS-Bypass wird automatisch aktiviert für aggregierte Queries
- Keine direkten Dokumenten-Inhalte werden zurückgegeben

Use Cases:
----------
- System-Administrator Dashboard
- Multi-Tenant-Monitoring
- Kapazitaetsplanung
- Rechnungsstellung basierend auf Nutzung

"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
import structlog

from app.api.dependencies import get_current_superuser, get_db
from app.db.models import User, Company, Document, DocumentArchive, ProcessingStatus
from app.core.safe_errors import safe_error_log
from app.core.rate_limiting import limiter, get_user_identifier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/cross-tenant", tags=["cross-tenant-reports"])


# ==================== Response Models ====================


class CompanyOverviewStats(BaseModel):
    """Aggregierte Statistiken für eine Firma."""

    company_id: UUID = Field(..., description="Firmen-ID")
    company_name: str = Field(..., description="Firmenname")
    is_active: bool = Field(..., description="Firma aktiv?")

    # Dokumenten-Statistiken
    total_documents: int = Field(0, description="Gesamt-Anzahl Dokumente")
    documents_this_month: int = Field(0, description="Dokumente diesen Monat")
    archived_documents: int = Field(0, description="Archivierte Dokumente")

    # Letzter Upload
    last_upload_date: Optional[datetime] = Field(None, description="Letzter Upload")


class CompanyFinancialSummary(BaseModel):
    """Finanz-Übersicht für eine Firma."""

    company_id: UUID = Field(..., description="Firmen-ID")
    company_name: str = Field(..., description="Firmenname")
    is_active: bool = Field(..., description="Firma aktiv?")

    # Rechnungs-Statistiken
    total_invoices: int = Field(0, description="Anzahl Rechnungen (document_type=invoice)")

    # Processing-Status
    processing_queued: int = Field(0, description="Dokumente in Warteschlange")
    processing_completed: int = Field(0, description="Erfolgreich verarbeitete Dokumente")
    processing_failed: int = Field(0, description="Fehlgeschlagene Verarbeitungen")


class CrossTenantOverviewResponse(BaseModel):
    """Response für den Overview-Endpoint."""

    total_companies: int = Field(..., description="Anzahl Firmen in System")
    active_companies: int = Field(..., description="Anzahl aktiver Firmen")
    companies: List[CompanyOverviewStats] = Field(..., description="Statistiken pro Firma")


class CrossTenantFinancialResponse(BaseModel):
    """Response für den Financial-Summary-Endpoint."""

    total_companies: int = Field(..., description="Anzahl Firmen in System")
    active_companies: int = Field(..., description="Anzahl aktiver Firmen")
    companies: List[CompanyFinancialSummary] = Field(..., description="Finanz-Statistiken pro Firma")


# ==================== Endpoints ====================


@router.get(
    "/overview",
    response_model=CrossTenantOverviewResponse,
    summary="Cross-Tenant Übersicht",
    description="Aggregierte Statistiken für alle Firmen (nur Admins)"
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_cross_tenant_overview(
    request: Request,  # Required for rate limiter
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> CrossTenantOverviewResponse:
    """
    Gibt einen Überblick über alle Firmen im System.

    Für jede Firma wird zurückgegeben:
    - Firmen-ID und Name
    - Anzahl Dokumente (gesamt, diesen Monat, archiviert)
    - Datum des letzten Uploads

    **Berechtigung**: Nur Superuser/Admins

    **RLS-Hinweis**: Dieser Endpoint aktiviert RLS-Bypass um alle Firmen zu sehen.
    """
    try:
        # RLS-Bypass aktivieren für Cross-Tenant-Zugriff
        await db.execute(text("SET LOCAL app.rls_bypass = true"))

        # Alle Firmen abrufen (sortiert nach Name)
        result = await db.execute(
            select(Company).order_by(Company.name)
        )
        companies = result.scalars().all()

        # Start des aktuellen Monats
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        company_stats: List[CompanyOverviewStats] = []

        for company in companies:
            # Dokumenten-Statistiken für diese Firma
            total_docs_result = await db.execute(
                select(func.count(Document.id)).where(
                    and_(
                        Document.company_id == company.id,
                        Document.deleted_at.is_(None)  # Soft-deleted ausschließen
                    )
                )
            )
            total_documents = total_docs_result.scalar() or 0

            # Dokumente diesen Monat
            monthly_docs_result = await db.execute(
                select(func.count(Document.id)).where(
                    and_(
                        Document.company_id == company.id,
                        Document.deleted_at.is_(None),
                        Document.upload_date >= month_start
                    )
                )
            )
            documents_this_month = monthly_docs_result.scalar() or 0

            # Archivierte Dokumente
            archived_result = await db.execute(
                select(func.count(Document.id)).where(
                    and_(
                        Document.company_id == company.id,
                        Document.is_archived == True
                    )
                )
            )
            archived_documents = archived_result.scalar() or 0

            # Letzter Upload
            last_upload_result = await db.execute(
                select(func.max(Document.upload_date)).where(
                    and_(
                        Document.company_id == company.id,
                        Document.deleted_at.is_(None)
                    )
                )
            )
            last_upload_date = last_upload_result.scalar()

            company_stats.append(
                CompanyOverviewStats(
                    company_id=company.id,
                    company_name=company.name,
                    is_active=company.is_active,
                    total_documents=total_documents,
                    documents_this_month=documents_this_month,
                    archived_documents=archived_documents,
                    last_upload_date=last_upload_date
                )
            )

        # Response zusammenstellen
        active_count = sum(1 for c in companies if c.is_active)

        logger.info(
            "cross_tenant_overview_accessed",
            admin_id=str(admin.id),
            total_companies=len(companies),
            active_companies=active_count
        )

        return CrossTenantOverviewResponse(
            total_companies=len(companies),
            active_companies=active_count,
            companies=company_stats
        )

    except Exception as e:
        logger.error(
            "cross_tenant_overview_failed",
            admin_id=str(admin.id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Cross-Tenant-Übersicht"
        )


@router.get(
    "/financial-summary",
    response_model=CrossTenantFinancialResponse,
    summary="Cross-Tenant Finanz-Übersicht",
    description="Finanz-relevante Statistiken für alle Firmen (nur Admins)"
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_cross_tenant_financial_summary(
    request: Request,  # Required for rate limiter
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> CrossTenantFinancialResponse:
    """
    Gibt eine Finanz-Übersicht für alle Firmen im System.

    Für jede Firma wird zurückgegeben:
    - Firmen-ID und Name
    - Anzahl Rechnungen (document_type='invoice')
    - Processing-Status (queued, completed, failed)

    **Berechtigung**: Nur Superuser/Admins

    **RLS-Hinweis**: Dieser Endpoint aktiviert RLS-Bypass um alle Firmen zu sehen.
    """
    try:
        # RLS-Bypass aktivieren
        await db.execute(text("SET LOCAL app.rls_bypass = true"))

        # Alle Firmen abrufen
        result = await db.execute(
            select(Company).order_by(Company.name)
        )
        companies = result.scalars().all()

        company_summaries: List[CompanyFinancialSummary] = []

        for company in companies:
            # Anzahl Rechnungen (document_type = 'invoice')
            invoices_result = await db.execute(
                select(func.count(Document.id)).where(
                    and_(
                        Document.company_id == company.id,
                        Document.deleted_at.is_(None),
                        Document.document_type == "invoice"
                    )
                )
            )
            total_invoices = invoices_result.scalar() or 0

            # Processing Status: Queued
            queued_result = await db.execute(
                select(func.count(Document.id)).where(
                    and_(
                        Document.company_id == company.id,
                        Document.deleted_at.is_(None),
                        or_(
                            Document.status == ProcessingStatus.PENDING,
                            Document.status == ProcessingStatus.QUEUED
                        )
                    )
                )
            )
            processing_queued = queued_result.scalar() or 0

            # Processing Status: Completed
            completed_result = await db.execute(
                select(func.count(Document.id)).where(
                    and_(
                        Document.company_id == company.id,
                        Document.deleted_at.is_(None),
                        Document.status == ProcessingStatus.COMPLETED
                    )
                )
            )
            processing_completed = completed_result.scalar() or 0

            # Processing Status: Failed
            failed_result = await db.execute(
                select(func.count(Document.id)).where(
                    and_(
                        Document.company_id == company.id,
                        Document.deleted_at.is_(None),
                        Document.status == ProcessingStatus.FAILED
                    )
                )
            )
            processing_failed = failed_result.scalar() or 0

            company_summaries.append(
                CompanyFinancialSummary(
                    company_id=company.id,
                    company_name=company.name,
                    is_active=company.is_active,
                    total_invoices=total_invoices,
                    processing_queued=processing_queued,
                    processing_completed=processing_completed,
                    processing_failed=processing_failed
                )
            )

        # Response zusammenstellen
        active_count = sum(1 for c in companies if c.is_active)

        logger.info(
            "cross_tenant_financial_summary_accessed",
            admin_id=str(admin.id),
            total_companies=len(companies),
            active_companies=active_count
        )

        return CrossTenantFinancialResponse(
            total_companies=len(companies),
            active_companies=active_count,
            companies=company_summaries
        )

    except Exception as e:
        logger.error(
            "cross_tenant_financial_summary_failed",
            admin_id=str(admin.id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Cross-Tenant-Finanz-Übersicht"
        )

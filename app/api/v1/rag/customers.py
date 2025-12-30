"""RAG Customer Cards API Endpoints.

Customer Intelligence mit:
- Pre-computed Zusammenfassungen
- Schneller Abruf (< 100ms)
- Fuzzy Search
- Manuelle Aktualisierung
"""

import structlog
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.models import User, RAGCustomerCard
from app.api.dependencies import get_current_user, get_db, require_admin
from app.services.rag.customer_card_service import (
    get_customer_card_service,
    CustomerCardService,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/customers", tags=["rag-customers"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class QuickFactsResponse(BaseModel):
    """Quick Facts eines Kunden."""
    document_count: int = 0
    document_types: dict = Field(default_factory=dict)
    date_range: dict = Field(default_factory=dict)


class CustomerCardResponse(BaseModel):
    """Customer Card Response."""
    customer_id: str
    customer_name: str
    summary_text: Optional[str] = None
    quick_facts: Optional[dict] = None
    open_invoices: Optional[list] = None
    active_contracts: Optional[list] = None
    flags: Optional[list] = None
    payment_behavior: Optional[str] = None
    priority_level: int = 5  # 0-10 scale
    last_sync_at: Optional[datetime] = None
    sync_status: str = "pending"
    source_document_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerSearchResultResponse(BaseModel):
    """Ergebnis einer Kundensuche."""
    customer_id: str
    customer_name: str
    similarity: float
    document_count: int
    last_document_date: Optional[datetime] = None


class CustomerListResponse(BaseModel):
    """Liste von Customer Cards."""
    customers: List[CustomerCardResponse]
    total: int
    page: int
    page_size: int


class CustomerCardCreateRequest(BaseModel):
    """Request zum Erstellen einer Customer Card."""
    customer_id: str = Field(..., min_length=1, max_length=255)
    customer_name: str = Field(..., min_length=1, max_length=500)


# =============================================================================
# Dependencies
# =============================================================================

def get_card_service() -> CustomerCardService:
    """Dependency fuer CustomerCardService."""
    return get_customer_card_service()


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "/{customer_id}",
    response_model=CustomerCardResponse,
    summary="Customer Card abrufen",
    description="Ruft die Customer Card fuer einen Kunden ab."
)
async def get_customer_card(
    customer_id: str,
    force_refresh: bool = Query(False, description="Card neu generieren"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    card_service: CustomerCardService = Depends(get_card_service)
) -> CustomerCardResponse:
    """
    Ruft Customer Card ab.

    - Schneller Abruf aus Cache/DB (< 100ms Ziel)
    - Optional: Neu-Generierung mit force_refresh=true

    Die Card enthaelt:
    - **summary_text**: LLM-generierte Zusammenfassung
    - **quick_facts**: Dokumentanzahl, Typen, Zeitraum
    - **open_invoices**: Offene Rechnungen (falls verfuegbar)
    - **active_contracts**: Aktive Vertraege (falls verfuegbar)
    """
    logger.info(
        "get_customer_card_request",
        customer_id=customer_id,
        user_id=str(current_user.id),
        force_refresh=force_refresh
    )

    result = await card_service.get_card(
        db=db,
        customer_id=customer_id,
        force_refresh=force_refresh
    )

    if not result.card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer Card fuer '{customer_id}' nicht gefunden"
        )

    card = result.card

    return CustomerCardResponse(
        customer_id=card.customer_id,
        customer_name=card.customer_name,
        summary_text=card.summary_text,
        quick_facts=card.quick_facts,
        open_invoices=card.open_invoices,
        active_contracts=card.active_contracts,
        flags=card.flags,
        payment_behavior=card.payment_behavior,
        priority_level=card.priority_level or 5,
        last_sync_at=card.last_sync_at,
        sync_status=card.sync_status or "pending",
        source_document_count=len(card.source_document_ids) if card.source_document_ids else 0,
        created_at=card.created_at,
        updated_at=card.updated_at
    )


@router.get(
    "/search",
    response_model=List[CustomerSearchResultResponse],
    summary="Kunden suchen",
    description="Fuzzy-Suche nach Kunden."
)
async def search_customers(
    q: str = Query(..., min_length=1, max_length=255, description="Suchanfrage"),
    limit: int = Query(10, ge=1, le=50, description="Max Ergebnisse"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    card_service: CustomerCardService = Depends(get_card_service)
) -> List[CustomerSearchResultResponse]:
    """
    Fuzzy-Suche nach Kunden.

    Verwendet pg_trgm fuer aehnlichkeitsbasierte Suche.
    Gibt Kunden sortiert nach Aehnlichkeit zurueck.
    """
    results = await card_service.search_customers(
        db=db,
        query=q,
        limit=limit
    )

    return [
        CustomerSearchResultResponse(
            customer_id=r.customer_id,
            customer_name=r.customer_name,
            similarity=r.similarity,
            document_count=r.document_count,
            last_document_date=r.last_document_date
        )
        for r in results
    ]


@router.get(
    "",
    response_model=CustomerListResponse,
    summary="Alle Customer Cards auflisten",
    description="Listet alle Customer Cards mit Pagination auf."
)
async def list_customer_cards(
    page: int = Query(1, ge=1, description="Seite"),
    page_size: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    card_service: CustomerCardService = Depends(get_card_service)
) -> CustomerListResponse:
    """
    Listet alle Customer Cards auf.

    Sortiert alphabetisch nach Kundenname.
    """
    offset = (page - 1) * page_size

    cards = await card_service.get_all_customers(
        db=db,
        limit=page_size,
        offset=offset
    )

    # Total count
    from sqlalchemy import func, select
    total = await db.scalar(
        select(func.count(RAGCustomerCard.customer_id))
    ) or 0

    return CustomerListResponse(
        customers=[
            CustomerCardResponse(
                customer_id=c.customer_id,
                customer_name=c.customer_name,
                summary_text=c.summary_text,
                quick_facts=c.quick_facts,
                open_invoices=c.open_invoices,
                active_contracts=c.active_contracts,
                flags=c.flags,
                payment_behavior=c.payment_behavior,
                priority_level=c.priority_level.value if c.priority_level else "normal",
                last_sync_at=c.last_sync_at,
                sync_status=c.sync_status.value if c.sync_status else "pending",
                source_document_count=len(c.source_document_ids) if c.source_document_ids else 0,
                created_at=c.created_at,
                updated_at=c.updated_at
            )
            for c in cards
        ],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post(
    "/{customer_id}/refresh",
    response_model=CustomerCardResponse,
    summary="Customer Card aktualisieren",
    description="Generiert die Customer Card neu."
)
async def refresh_customer_card(
    customer_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    card_service: CustomerCardService = Depends(get_card_service)
) -> CustomerCardResponse:
    """
    Aktualisiert eine Customer Card manuell.

    - Sucht aktuelle Dokumente
    - Generiert neue LLM-Zusammenfassung
    - Aktualisiert Quick Facts
    """
    logger.info(
        "refresh_customer_card_request",
        customer_id=customer_id,
        user_id=str(current_user.id)
    )

    result = await card_service.get_card(
        db=db,
        customer_id=customer_id,
        force_refresh=True
    )

    if not result.card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer Card fuer '{customer_id}' konnte nicht generiert werden"
        )

    card = result.card

    return CustomerCardResponse(
        customer_id=card.customer_id,
        customer_name=card.customer_name,
        summary_text=card.summary_text,
        quick_facts=card.quick_facts,
        open_invoices=card.open_invoices,
        active_contracts=card.active_contracts,
        flags=card.flags,
        payment_behavior=card.payment_behavior,
        priority_level=card.priority_level or 5,
        last_sync_at=card.last_sync_at,
        sync_status=card.sync_status or "pending",
        source_document_count=len(card.source_document_ids) if card.source_document_ids else 0,
        created_at=card.created_at,
        updated_at=card.updated_at
    )


@router.post(
    "",
    response_model=CustomerCardResponse,
    summary="Customer Card erstellen",
    description="Erstellt eine neue Customer Card.",
    dependencies=[Depends(require_admin)]
)
async def create_customer_card(
    request: CustomerCardCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    card_service: CustomerCardService = Depends(get_card_service)
) -> CustomerCardResponse:
    """
    Erstellt eine neue Customer Card.

    Sucht relevante Dokumente und generiert LLM-Zusammenfassung.
    """
    logger.info(
        "create_customer_card_request",
        customer_id=request.customer_id,
        customer_name=request.customer_name,
        user_id=str(current_user.id)
    )

    # Pruefen ob Card bereits existiert
    from sqlalchemy import select
    existing = await db.execute(
        select(RAGCustomerCard).where(
            RAGCustomerCard.customer_id == request.customer_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Customer Card fuer '{request.customer_id}' existiert bereits"
        )

    try:
        card = await card_service.generate_card(
            db=db,
            customer_id=request.customer_id,
            customer_name=request.customer_name
        )

        return CustomerCardResponse(
            customer_id=card.customer_id,
            customer_name=card.customer_name,
            summary_text=card.summary_text,
            quick_facts=card.quick_facts,
            open_invoices=card.open_invoices,
            active_contracts=card.active_contracts,
            flags=card.flags,
            payment_behavior=card.payment_behavior,
            priority_level=card.priority_level.value if card.priority_level else "normal",
            last_sync_at=card.last_sync_at,
            sync_status=card.sync_status.value if card.sync_status else "pending",
            source_document_count=len(card.source_document_ids) if card.source_document_ids else 0,
            created_at=card.created_at,
            updated_at=card.updated_at
        )

    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.exception(
            "create_customer_card_failed",
            customer_id=request.customer_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erstellung fehlgeschlagen. Bitte erneut versuchen."
        )


@router.delete(
    "/{customer_id}",
    summary="Customer Card loeschen",
    description="Loescht eine Customer Card.",
    dependencies=[Depends(require_admin)]
)
async def delete_customer_card(
    customer_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    card_service: CustomerCardService = Depends(get_card_service)
) -> dict:
    """
    Loescht eine Customer Card.

    Die Card kann jederzeit neu generiert werden.
    """
    from sqlalchemy import select

    result = await db.execute(
        select(RAGCustomerCard).where(
            RAGCustomerCard.customer_id == customer_id
        )
    )
    card = result.scalar_one_or_none()

    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer Card fuer '{customer_id}' nicht gefunden"
        )

    await db.delete(card)
    await db.commit()

    # Cache leeren
    card_service.clear_cache(customer_id)

    logger.info(
        "customer_card_deleted",
        customer_id=customer_id,
        user_id=str(current_user.id)
    )

    return {
        "success": True,
        "customer_id": customer_id,
        "message": "Customer Card geloescht"
    }


@router.post(
    "/sync",
    summary="Alle Customer Cards synchronisieren",
    description="Startet Synchronisation aller Customer Cards.",
    dependencies=[Depends(require_admin)]
)
async def sync_all_customer_cards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Startet Batch-Synchronisation aller Customer Cards.

    Wird als Celery Task im Hintergrund ausgefuehrt.
    """
    from app.workers.tasks.rag_tasks import run_rag_batch_job
    from app.db.models import RAGBatchJob, RAGBatchJobType, RAGBatchJobStatus

    # Job erstellen
    job = RAGBatchJob(
        job_type=RAGBatchJobType.SYNC_CARDS,
        status=RAGBatchJobStatus.PENDING,
        progress_percent=0
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Celery Task starten
    run_rag_batch_job.delay(str(job.id))

    logger.info(
        "customer_card_sync_started",
        job_id=str(job.id),
        user_id=str(current_user.id)
    )

    return {
        "success": True,
        "job_id": str(job.id),
        "message": "Customer Card Sync gestartet"
    }

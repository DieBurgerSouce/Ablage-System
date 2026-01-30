"""Transactions API - Vorgangsverknuepfung von Dokumenten.

Basiert auf dem bestehenden DocumentGroup-Model mit group_type='transaction'.
Ermoeglicht die Verfolgung von Dokumentenketten:
  Anfrage → Angebot → Auftrag → Lieferschein → Rechnung → Zahlung

Phase: 11 (HIGH Priority TODOs)
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, or_, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import (
    User, Document, DocumentGroup, DocumentGroupType, DocumentRelationship,
    BusinessEntity, Company
)
from app.middleware.company_context import require_company, get_current_company

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])


# ==================== Schemas ====================

class TransactionStepResponse(BaseModel):
    """Ein Schritt in der Transaktionskette."""
    id: str
    type: str  # anfrage, angebot, auftrag, lieferschein, rechnung, zahlung
    status: str  # pending, active, completed, skipped
    document_id: Optional[str] = None
    document_number: Optional[str] = None
    completed_at: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "EUR"

    class Config:
        from_attributes = True


class TransactionResponse(BaseModel):
    """Vollstaendige Transaktionsantwort."""
    id: str
    transaction_number: str
    name: str
    status: str  # draft, pending, completed, cancelled
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    folder_id: Optional[str] = None
    steps: List[TransactionStepResponse]
    total_amount: Optional[float] = None
    currency: str = "EUR"
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    last_activity_at: str

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """Paginierte Liste von Transaktionen."""
    items: List[TransactionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CreateTransactionRequest(BaseModel):
    """Request zum Erstellen einer Transaktion."""
    name: str = Field(..., min_length=1, max_length=255)
    entity_id: Optional[UUID] = None
    folder_id: Optional[str] = None
    document_ids: List[UUID] = Field(default_factory=list)


class UpdateTransactionRequest(BaseModel):
    """Request zum Aktualisieren einer Transaktion."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = None


class UpdateStepRequest(BaseModel):
    """Request zum Aktualisieren eines Transaktionsschritts."""
    status: str = Field(..., pattern=r'^(pending|active|completed|skipped)$')
    document_id: Optional[UUID] = None
    amount: Optional[Decimal] = None


# ==================== Constants ====================

STEP_TYPES = ['anfrage', 'angebot', 'auftrag', 'lieferschein', 'rechnung', 'zahlung']

STATUS_ORDER = {
    'pending': 0,
    'active': 1,
    'completed': 2,
    'skipped': 3,
}


# ==================== Helper Functions ====================

def generate_transaction_number() -> str:
    """Generiert eine eindeutige Transaktionsnummer."""
    year = datetime.now().year
    random_part = uuid.uuid4().hex[:6].upper()
    return f"VG-{year}-{random_part}"


def determine_transaction_status(steps: List[Dict[str, Any]]) -> str:
    """Bestimmt den Status einer Transaktion basierend auf den Schritten."""
    if not steps:
        return "draft"

    completed_count = sum(1 for s in steps if s.get('status') == 'completed')
    skipped_count = sum(1 for s in steps if s.get('status') == 'skipped')
    active_count = sum(1 for s in steps if s.get('status') == 'active')

    # Alle relevanten Schritte abgeschlossen (completed oder skipped)
    if completed_count + skipped_count == len(steps):
        return "completed"

    # Mindestens ein Schritt aktiv oder abgeschlossen
    if active_count > 0 or completed_count > 0:
        return "pending"

    return "draft"


def build_steps_from_documents(
    documents: List[Document],
    relationships: List[DocumentRelationship]
) -> List[TransactionStepResponse]:
    """Baut die Schrittliste aus Dokumenten und Beziehungen."""
    steps: List[TransactionStepResponse] = []

    # Mapping von Dokumenttyp zu Schritttyp
    DOC_TYPE_TO_STEP = {
        'inquiry': 'anfrage',
        'anfrage': 'anfrage',
        'quote': 'angebot',
        'angebot': 'angebot',
        'order': 'auftrag',
        'auftrag': 'auftrag',
        'delivery_note': 'lieferschein',
        'lieferschein': 'lieferschein',
        'invoice': 'rechnung',
        'rechnung': 'rechnung',
        'payment': 'zahlung',
        'zahlung': 'zahlung',
    }

    # Schritte aus Dokumenten ableiten
    doc_by_type: Dict[str, Document] = {}
    for doc in documents:
        doc_type = doc.document_type or 'other'
        step_type = DOC_TYPE_TO_STEP.get(doc_type.lower())
        if step_type:
            doc_by_type[step_type] = doc

    # Alle Standard-Schritte erstellen
    for i, step_type in enumerate(STEP_TYPES):
        doc = doc_by_type.get(step_type)

        if doc:
            # Betrag aus extracted_data extrahieren
            amount = None
            if doc.extracted_data:
                invoice_data = doc.extracted_data.get('invoice', {})
                amount = invoice_data.get('total_gross')

            # Dokumentnummer ermitteln
            doc_number = None
            if doc.extracted_data:
                invoice_data = doc.extracted_data.get('invoice', {})
                doc_number = invoice_data.get('invoice_number') or invoice_data.get('order_number')
            if not doc_number:
                doc_number = doc.original_filename[:20] if doc.original_filename else None

            steps.append(TransactionStepResponse(
                id=f"step-{i+1}",
                type=step_type,
                status='completed',
                document_id=str(doc.id),
                document_number=doc_number,
                completed_at=doc.created_at.isoformat() if doc.created_at else None,
                amount=float(amount) if amount else None,
                currency='EUR',
            ))
        else:
            # Leerer Schritt
            steps.append(TransactionStepResponse(
                id=f"step-{i+1}",
                type=step_type,
                status='pending',
                document_id=None,
                document_number=None,
                completed_at=None,
                amount=None,
                currency='EUR',
            ))

    return steps


def group_to_transaction(
    group: DocumentGroup,
    documents: List[Document],
    relationships: List[DocumentRelationship],
    entity: Optional[BusinessEntity] = None
) -> TransactionResponse:
    """Konvertiert eine DocumentGroup zu einer TransactionResponse."""
    steps = build_steps_from_documents(documents, relationships)

    # Gesamtbetrag aus dem letzten Dokument mit Betrag
    total_amount = None
    for step in reversed(steps):
        if step.amount:
            total_amount = step.amount
            break

    # Status bestimmen
    status = determine_transaction_status([s.model_dump() for s in steps])

    # Letzte Aktivitaet
    last_activity = group.updated_at or group.created_at

    return TransactionResponse(
        id=str(group.id),
        transaction_number=group.reference_number or generate_transaction_number(),
        name=group.name,
        status=status,
        entity_id=str(entity.id) if entity else None,
        entity_name=entity.name if entity else None,
        folder_id=group.detection_details.get('folder_id') if group.detection_details else None,
        steps=steps,
        total_amount=total_amount,
        currency='EUR',
        created_at=group.created_at.isoformat() if group.created_at else datetime.now(timezone.utc).isoformat(),
        updated_at=group.updated_at.isoformat() if group.updated_at else datetime.now(timezone.utc).isoformat(),
        completed_at=group.detection_details.get('completed_at') if group.detection_details else None,
        last_activity_at=last_activity.isoformat() if last_activity else datetime.now(timezone.utc).isoformat(),
    )


# ==================== Endpoints ====================

@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    entity_id: Optional[UUID] = Query(None, description="Filter nach Entity-ID"),
    folder_id: Optional[str] = Query(None, description="Filter nach Ordner (folie/messer)"),
    status_filter: Optional[str] = Query(None, description="Filter nach Status (komma-separiert)"),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Suche nach Name oder Nummer"),
    page: int = Query(1, ge=1, description="Seitennummer (1-indexed)"),
    per_page: int = Query(20, ge=1, le=100, description="Items pro Seite"),
    sort_by: str = Query("updated_at", description="Sortierfeld"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sortierrichtung"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> TransactionListResponse:
    """
    Listet Transaktionen (Vorgaenge) mit Filterung und Pagination.

    Transaktionen basieren auf DocumentGroups mit group_type='transaction'.

    **Filter:**
    - entity_id: Kunden-/Lieferanten-UUID
    - folder_id: "folie" oder "messer"
    - status: "draft", "pending", "completed", "cancelled"
    - search: Freitext-Suche

    **Sortierung:**
    - sort_by: created_at, updated_at, name, reference_number
    - sort_order: asc, desc
    """
    # Base Query fuer DocumentGroups vom Typ "transaction"
    query = (
        select(DocumentGroup)
        .where(
            and_(
                DocumentGroup.group_type == DocumentGroupType.TRANSACTION.value,
                DocumentGroup.deleted_at.is_(None),
            )
        )
    )

    # Filter: Entity
    if entity_id:
        query = query.where(DocumentGroup.business_entity_id == entity_id)

    # Filter: Folder (in detection_details gespeichert)
    if folder_id:
        query = query.where(
            DocumentGroup.detection_details['folder_id'].astext == folder_id
        )

    # Filter: Search
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                DocumentGroup.name.ilike(search_pattern),
                DocumentGroup.reference_number.ilike(search_pattern),
            )
        )

    # SECURITY: Whitelist gegen Reflection-Angriffe (CWE-89)
    ALLOWED_SORT_FIELDS = {"created_at", "updated_at", "name", "reference_number"}
    if sort_by not in ALLOWED_SORT_FIELDS:
        sort_by = "updated_at"
    sort_column = getattr(DocumentGroup, sort_by)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    # Total Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    # Execute
    result = await db.execute(query)
    groups = result.scalars().all()

    # Transformieren
    items: List[TransactionResponse] = []
    for group in groups:
        # Dokumente der Gruppe laden
        doc_query = (
            select(Document)
            .join(DocumentRelationship, DocumentRelationship.source_document_id == Document.id)
            .where(
                and_(
                    DocumentRelationship.chain_id == str(group.id),
                    Document.deleted_at.is_(None),
                )
            )
        )
        doc_result = await db.execute(doc_query)
        documents = list(doc_result.scalars().all())

        # Entity laden
        entity = None
        if group.business_entity_id:
            entity_result = await db.execute(
                select(BusinessEntity).where(BusinessEntity.id == group.business_entity_id)
            )
            entity = entity_result.scalar_one_or_none()

        # Beziehungen laden
        rel_query = select(DocumentRelationship).where(
            DocumentRelationship.chain_id == str(group.id)
        )
        rel_result = await db.execute(rel_query)
        relationships = list(rel_result.scalars().all())

        items.append(group_to_transaction(group, documents, relationships, entity))

    # Status-Filter nachtraeglich anwenden (da Status berechnet wird)
    if status_filter:
        allowed_statuses = set(status_filter.split(','))
        items = [item for item in items if item.status in allowed_statuses]

    total_pages = (total + per_page - 1) // per_page

    logger.info(
        "transactions_listed",
        user_id=str(current_user.id),
        total=total,
        page=page,
        filters={
            "entity_id": str(entity_id) if entity_id else None,
            "folder_id": folder_id,
            "search": bool(search),
        }
    )

    return TransactionListResponse(
        items=items,
        total=len(items),  # Nach Status-Filter
        page=page,
        page_size=per_page,
        total_pages=total_pages,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """
    Ruft eine einzelne Transaktion ab.

    Beinhaltet alle Schritte mit verknuepften Dokumenten.
    """
    # Gruppe laden
    result = await db.execute(
        select(DocumentGroup).where(
            and_(
                DocumentGroup.id == transaction_id,
                DocumentGroup.group_type == DocumentGroupType.TRANSACTION.value,
                DocumentGroup.deleted_at.is_(None),
            )
        )
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden"
        )

    # Dokumente laden
    doc_query = (
        select(Document)
        .join(DocumentRelationship, DocumentRelationship.source_document_id == Document.id)
        .where(
            and_(
                DocumentRelationship.chain_id == str(group.id),
                Document.deleted_at.is_(None),
            )
        )
    )
    doc_result = await db.execute(doc_query)
    documents = list(doc_result.scalars().all())

    # Entity laden
    entity = None
    if group.business_entity_id:
        entity_result = await db.execute(
            select(BusinessEntity).where(BusinessEntity.id == group.business_entity_id)
        )
        entity = entity_result.scalar_one_or_none()

    # Beziehungen laden
    rel_query = select(DocumentRelationship).where(
        DocumentRelationship.chain_id == str(group.id)
    )
    rel_result = await db.execute(rel_query)
    relationships = list(rel_result.scalars().all())

    return group_to_transaction(group, documents, relationships, entity)


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    request: CreateTransactionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> TransactionResponse:
    """
    Erstellt eine neue Transaktion.

    Erstellt eine DocumentGroup vom Typ 'transaction' und verknuepft optional Dokumente.
    """
    # Neue DocumentGroup erstellen
    group = DocumentGroup(
        id=uuid.uuid4(),
        name=request.name,
        group_type=DocumentGroupType.TRANSACTION.value,
        reference_number=generate_transaction_number(),
        business_entity_id=request.entity_id,
        detection_details={
            "folder_id": request.folder_id,
            "created_by": str(current_user.id),
        },
        detection_method="manual",
        detection_confidence=1.0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(group)

    # Dokumente verknuepfen
    for doc_id in request.document_ids:
        relationship = DocumentRelationship(
            id=uuid.uuid4(),
            source_document_id=doc_id,
            target_document_id=doc_id,  # Self-reference fuer Gruppenmitgliedschaft
            relationship_type="transaction_member",
            chain_id=str(group.id),
            confidence=1.0,
            created_at=datetime.now(timezone.utc),
        )
        db.add(relationship)

    await db.commit()
    await db.refresh(group)

    logger.info(
        "transaction_created",
        transaction_id=str(group.id),
        user_id=str(current_user.id),
        document_count=len(request.document_ids),
    )

    # Dokumente laden
    documents: List[Document] = []
    if request.document_ids:
        doc_result = await db.execute(
            select(Document).where(Document.id.in_(request.document_ids))
        )
        documents = list(doc_result.scalars().all())

    # Entity laden
    entity = None
    if request.entity_id:
        entity_result = await db.execute(
            select(BusinessEntity).where(BusinessEntity.id == request.entity_id)
        )
        entity = entity_result.scalar_one_or_none()

    return group_to_transaction(group, documents, [], entity)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: UUID,
    request: UpdateTransactionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """
    Aktualisiert eine Transaktion (Name, Status).
    """
    result = await db.execute(
        select(DocumentGroup).where(
            and_(
                DocumentGroup.id == transaction_id,
                DocumentGroup.group_type == DocumentGroupType.TRANSACTION.value,
                DocumentGroup.deleted_at.is_(None),
            )
        )
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden"
        )

    # Updates anwenden
    if request.name:
        group.name = request.name

    if request.status:
        if not group.detection_details:
            group.detection_details = {}
        group.detection_details['status_override'] = request.status
        if request.status == 'completed':
            group.detection_details['completed_at'] = datetime.now(timezone.utc).isoformat()

    group.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(group)

    logger.info(
        "transaction_updated",
        transaction_id=str(transaction_id),
        user_id=str(current_user.id),
    )

    # Fuer Response transformieren
    return await get_transaction(transaction_id, current_user, db)


@router.post("/{transaction_id}/steps/{step_type}", response_model=TransactionResponse)
async def update_transaction_step(
    transaction_id: UUID,
    step_type: str,
    request: UpdateStepRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """
    Aktualisiert einen Schritt in der Transaktion.

    Kann ein Dokument mit einem Schritt verknuepfen und den Status setzen.
    """
    if step_type not in STEP_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Schritt-Typ: {step_type}. Erlaubt: {', '.join(STEP_TYPES)}"
        )

    # Transaktion laden
    result = await db.execute(
        select(DocumentGroup).where(
            and_(
                DocumentGroup.id == transaction_id,
                DocumentGroup.group_type == DocumentGroupType.TRANSACTION.value,
                DocumentGroup.deleted_at.is_(None),
            )
        )
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden"
        )

    # Dokument verknuepfen falls angegeben
    if request.document_id:
        # Pruefen ob Dokument existiert
        doc_result = await db.execute(
            select(Document).where(
                and_(
                    Document.id == request.document_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        doc = doc_result.scalar_one_or_none()

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument nicht gefunden"
            )

        # Relationship erstellen
        relationship = DocumentRelationship(
            id=uuid.uuid4(),
            source_document_id=request.document_id,
            target_document_id=request.document_id,
            relationship_type=f"transaction_{step_type}",
            chain_id=str(group.id),
            confidence=1.0,
            created_at=datetime.now(timezone.utc),
        )
        db.add(relationship)

    # Step-Status in detection_details speichern
    if not group.detection_details:
        group.detection_details = {}
    if 'steps' not in group.detection_details:
        group.detection_details['steps'] = {}

    group.detection_details['steps'][step_type] = {
        'status': request.status,
        'document_id': str(request.document_id) if request.document_id else None,
        'amount': float(request.amount) if request.amount else None,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }

    group.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(group)

    logger.info(
        "transaction_step_updated",
        transaction_id=str(transaction_id),
        step_type=step_type,
        user_id=str(current_user.id),
    )

    return await get_transaction(transaction_id, current_user, db)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Loescht eine Transaktion (Soft-Delete).

    Die verknuepften Dokumente werden NICHT geloescht.
    """
    result = await db.execute(
        select(DocumentGroup).where(
            and_(
                DocumentGroup.id == transaction_id,
                DocumentGroup.group_type == DocumentGroupType.TRANSACTION.value,
                DocumentGroup.deleted_at.is_(None),
            )
        )
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden"
        )

    # Soft-Delete
    group.deleted_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(
        "transaction_deleted",
        transaction_id=str(transaction_id),
        user_id=str(current_user.id),
    )

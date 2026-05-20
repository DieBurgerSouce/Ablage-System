"""
Business Contacts API Endpoints.

Geschäftskontakt-Verwaltung mit automatischer Erkennung:
- CRUD-Operationen für Kunden, Lieferanten, Partner
- Automatische Kontakterkennung aus Dokumenten
- Deduplizierung und Zusammenführung
- Dokumentenverknüpfung

Feinpoliert und durchdacht - Enterprise Contact Management.
"""

import structlog
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload

from app.db.models import User, Document, BusinessContact, DocumentContact, ContactType
from app.api.dependencies import get_current_user, get_db
from app.db.schemas import (
    BusinessContactCreate,
    BusinessContactUpdate,
    BusinessContactResponse,
    BusinessContactListFilters,
    BusinessContactListResponse,
    ContactDocumentsResponse,
    ContactDocumentInfo,
    MergeContactsRequest,
    MergeContactsResponse,
    DetectContactsRequest,
    DetectContactsResponse,
    ContactStatsResponse,
    ContactTypeEnum,
    ContactRoleEnum,
)
from app.services.customer_detection_service import (
    normalize_company_name,
    get_customer_detection_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/business-contacts", tags=["business-contacts"])


def build_contact_response(contact: BusinessContact) -> BusinessContactResponse:
    """Build contact response with computed fields."""
    return BusinessContactResponse(
        id=contact.id,
        name=contact.name,
        name_normalized=contact.name_normalized,
        contact_type=ContactTypeEnum(contact.contact_type) if contact.contact_type else ContactTypeEnum.CUSTOMER,
        company_form=contact.company_form,
        tax_id=contact.tax_id,
        vat_id=contact.vat_id,
        registration_number=contact.registration_number,
        customer_number=contact.customer_number,
        supplier_number=contact.supplier_number,
        street=contact.street,
        house_number=contact.house_number,
        address_addition=contact.address_addition,
        postal_code=contact.postal_code,
        city=contact.city,
        country=contact.country or "Deutschland",
        email=contact.email,
        phone=contact.phone,
        fax=contact.fax,
        website=contact.website,
        bank_name=contact.bank_name,
        iban=contact.iban,
        bic=contact.bic,
        contact_persons=contact.contact_persons or [],
        parent_company_id=contact.parent_company_id,
        notes=contact.notes,
        tags=contact.tags or [],
        custom_fields=contact.custom_fields or {},
        owner_id=contact.owner_id,
        source=contact.source or "manual",
        auto_detected=contact.auto_detected or False,
        auto_detection_confidence=contact.auto_detection_confidence,
        first_document_id=contact.first_document_id,
        is_active=contact.is_active if contact.is_active is not None else True,
        is_verified=contact.is_verified or False,
        merged_into_id=contact.merged_into_id,
        document_count=contact.document_count or 0,
        total_invoice_amount=contact.total_invoice_amount or 0.0,
        last_document_date=contact.last_document_date,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        formatted_address=contact.formatted_address,
        display_name=contact.display_name,
    )


# ==================== CRUD Endpoints ====================


@router.post("/", response_model=BusinessContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    data: BusinessContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessContactResponse:
    """Erstellt einen neuen Geschäftskontakt."""
    logger.info(
        "creating_business_contact",
        user_id=str(current_user.id),
        name=data.name,
        contact_type=data.contact_type,
    )

    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id

    # Check for existing with same VAT ID within company
    if data.vat_id:
        existing = await db.execute(
            select(BusinessContact).where(
                and_(
                    BusinessContact.vat_id == data.vat_id,
                    BusinessContact.company_id == company_id,
                    BusinessContact.is_active == True,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Kontakt mit USt-IdNr. {data.vat_id} existiert bereits",
            )

    # Create contact with company_id for Multi-Tenant isolation
    contact = BusinessContact(
        name=data.name,
        name_normalized=normalize_company_name(data.name),
        contact_type=data.contact_type.value if data.contact_type else ContactType.CUSTOMER.value,
        company_form=data.company_form,
        tax_id=data.tax_id,
        vat_id=data.vat_id,
        registration_number=data.registration_number,
        customer_number=data.customer_number,
        supplier_number=data.supplier_number,
        street=data.street,
        house_number=data.house_number,
        address_addition=data.address_addition,
        postal_code=data.postal_code,
        city=data.city,
        country=data.country,
        email=data.email,
        phone=data.phone,
        fax=data.fax,
        website=data.website,
        bank_name=data.bank_name,
        iban=data.iban,
        bic=data.bic,
        contact_persons=data.contact_persons if data.contact_persons else [],
        parent_company_id=data.parent_company_id,
        notes=data.notes,
        tags=data.tags or [],
        custom_fields=data.custom_fields or {},
        owner_id=current_user.id,
        company_id=company_id,  # Multi-Tenant Isolation
        source="manual",
        auto_detected=False,
        is_active=True,
        is_verified=data.is_verified,
    )

    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    logger.info("business_contact_created", contact_id=str(contact.id), name=contact.name)
    return build_contact_response(contact)


@router.get("/", response_model=BusinessContactListResponse)
async def list_contacts(
    search: Optional[str] = Query(None, description="Suche in Name, Email, etc."),
    contact_type: Optional[ContactTypeEnum] = Query(None),
    is_verified: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(True),
    has_documents: Optional[bool] = Query(None),
    city: Optional[str] = Query(None),
    postal_code_prefix: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    min_invoice_amount: Optional[float] = Query(None),
    auto_detected: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("name", pattern="^(name|created_at|updated_at|document_count|total_invoice_amount)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessContactListResponse:
    """Listet Geschäftskontakte mit Filtern und Paginierung."""
    # Multi-Tenant: company_id aus User-Context
    company_id = current_user.company_id

    # Build query with company_id filter for Multi-Tenant isolation
    query = select(BusinessContact).where(
        and_(
            BusinessContact.company_id == company_id,
            BusinessContact.merged_into_id.is_(None),  # Exclude merged contacts
        )
    )

    # Apply filters
    if is_active is not None:
        query = query.where(BusinessContact.is_active == is_active)

    if contact_type:
        query = query.where(BusinessContact.contact_type == contact_type.value)

    if is_verified is not None:
        query = query.where(BusinessContact.is_verified == is_verified)

    if auto_detected is not None:
        query = query.where(BusinessContact.auto_detected == auto_detected)

    if city:
        query = query.where(BusinessContact.city.ilike(f"%{city}%"))

    if postal_code_prefix:
        query = query.where(BusinessContact.postal_code.startswith(postal_code_prefix))

    if min_invoice_amount is not None:
        query = query.where(BusinessContact.total_invoice_amount >= min_invoice_amount)

    if has_documents is not None:
        if has_documents:
            query = query.where(BusinessContact.document_count > 0)
        else:
            query = query.where(BusinessContact.document_count == 0)

    if tags:
        # At least one tag must match
        for tag in tags:
            query = query.where(BusinessContact.tags.contains([tag]))

    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                BusinessContact.name.ilike(search_term),
                BusinessContact.email.ilike(search_term),
                BusinessContact.city.ilike(search_term),
                BusinessContact.vat_id.ilike(search_term),
                BusinessContact.customer_number.ilike(search_term),
                BusinessContact.supplier_number.ilike(search_term),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting
    sort_column = getattr(BusinessContact, sort_by)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    contacts = result.scalars().all()

    return BusinessContactListResponse(
        contacts=[build_contact_response(c) for c in contacts],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + len(contacts)) < total,
    )


@router.get("/stats", response_model=ContactStatsResponse)
async def get_contact_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactStatsResponse:
    """Statistiken über Geschäftskontakte."""
    # Multi-Tenant: company_id aus User-Context
    company_id = current_user.company_id

    # Total contacts
    total_result = await db.execute(
        select(func.count(BusinessContact.id)).where(
            and_(
                BusinessContact.company_id == company_id,
                BusinessContact.is_active == True,
                BusinessContact.merged_into_id.is_(None),
            )
        )
    )
    total_contacts = total_result.scalar() or 0

    # By type
    type_result = await db.execute(
        select(
            BusinessContact.contact_type,
            func.count(BusinessContact.id)
        ).where(
            and_(
                BusinessContact.company_id == company_id,
                BusinessContact.is_active == True,
                BusinessContact.merged_into_id.is_(None),
            )
        ).group_by(BusinessContact.contact_type)
    )
    by_type = {row[0]: row[1] for row in type_result.fetchall()}

    # Verified count
    verified_result = await db.execute(
        select(func.count(BusinessContact.id)).where(
            and_(
                BusinessContact.company_id == company_id,
                BusinessContact.is_active == True,
                BusinessContact.is_verified == True,
                BusinessContact.merged_into_id.is_(None),
            )
        )
    )
    verified_count = verified_result.scalar() or 0

    # Auto-detected count
    auto_result = await db.execute(
        select(func.count(BusinessContact.id)).where(
            and_(
                BusinessContact.company_id == company_id,
                BusinessContact.is_active == True,
                BusinessContact.auto_detected == True,
                BusinessContact.merged_into_id.is_(None),
            )
        )
    )
    auto_detected_count = auto_result.scalar() or 0

    # Top customers by invoice amount
    top_result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.company_id == company_id,
                BusinessContact.is_active == True,
                BusinessContact.contact_type == ContactType.CUSTOMER.value,
                BusinessContact.total_invoice_amount > 0,
                BusinessContact.merged_into_id.is_(None),
            )
        ).order_by(desc(BusinessContact.total_invoice_amount)).limit(10)
    )
    top_customers = [
        {
            "name": c.name,
            "total_amount": c.total_invoice_amount,
            "document_count": c.document_count,
        }
        for c in top_result.scalars().all()
    ]

    # Recent contacts
    recent_result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.company_id == company_id,
                BusinessContact.is_active == True,
                BusinessContact.merged_into_id.is_(None),
            )
        ).order_by(desc(BusinessContact.created_at)).limit(5)
    )
    recent_contacts = [build_contact_response(c) for c in recent_result.scalars().all()]

    # Average documents per contact
    avg_result = await db.execute(
        select(func.avg(BusinessContact.document_count)).where(
            and_(
                BusinessContact.company_id == company_id,
                BusinessContact.is_active == True,
                BusinessContact.merged_into_id.is_(None),
            )
        )
    )
    avg_docs = avg_result.scalar() or 0.0

    return ContactStatsResponse(
        total_contacts=total_contacts,
        by_type=by_type,
        verified_count=verified_count,
        auto_detected_count=auto_detected_count,
        top_customers_by_invoice=top_customers,
        recent_contacts=recent_contacts,
        avg_documents_per_contact=round(float(avg_docs), 2),
    )


@router.get("/{contact_id}", response_model=BusinessContactResponse)
async def get_contact(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessContactResponse:
    """Holt einen einzelnen Geschäftskontakt."""
    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id

    result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.id == contact_id,
                BusinessContact.company_id == company_id,
            )
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kontakt nicht gefunden",
        )

    # If merged, redirect to target
    if contact.merged_into_id:
        return await get_contact(contact.merged_into_id, current_user, db)

    return build_contact_response(contact)


@router.patch("/{contact_id}", response_model=BusinessContactResponse)
async def update_contact(
    contact_id: UUID,
    data: BusinessContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessContactResponse:
    """Aktualisiert einen Geschäftskontakt."""
    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id

    result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.id == contact_id,
                BusinessContact.company_id == company_id,
            )
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kontakt nicht gefunden",
        )

    if contact.merged_into_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zusammengeführter Kontakt kann nicht bearbeitet werden",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field == "contact_type" and value:
            value = value.value if hasattr(value, 'value') else value
        if field == "contact_persons" and value:
            value = [cp.model_dump() if hasattr(cp, 'model_dump') else cp for cp in value]
        setattr(contact, field, value)

    # Update normalized name if name changed
    if "name" in update_data:
        contact.name_normalized = normalize_company_name(contact.name)

    contact.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(contact)

    logger.info("business_contact_updated", contact_id=str(contact_id))
    return build_contact_response(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_contact(
    contact_id: UUID,
    hard_delete: bool = Query(False, description="Permanent löschen statt deaktivieren"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Löscht oder deaktiviert einen Geschäftskontakt."""
    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id

    result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.id == contact_id,
                BusinessContact.company_id == company_id,
            )
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kontakt nicht gefunden",
        )

    if hard_delete:
        # Remove document links first
        await db.execute(
            DocumentContact.__table__.delete().where(DocumentContact.contact_id == contact_id)
        )
        await db.delete(contact)
        logger.info("business_contact_hard_deleted", contact_id=str(contact_id))
    else:
        contact.is_active = False
        contact.updated_at = datetime.now(timezone.utc)
        logger.info("business_contact_deactivated", contact_id=str(contact_id))

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Document Linking ====================


@router.get("/{contact_id}/documents", response_model=ContactDocumentsResponse)
async def get_contact_documents(
    contact_id: UUID,
    role: Optional[ContactRoleEnum] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactDocumentsResponse:
    """Listet alle Dokumente eines Kontakts."""
    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id

    # Get contact with company_id validation
    contact_result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.id == contact_id,
                BusinessContact.company_id == company_id,
            )
        )
    )
    contact = contact_result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kontakt nicht gefunden",
        )

    # Build query for document links
    query = (
        select(DocumentContact, Document)
        .join(Document, DocumentContact.document_id == Document.id)
        .where(DocumentContact.contact_id == contact_id)
    )

    if role:
        query = query.where(DocumentContact.role == role.value)

    query = query.order_by(desc(Document.created_at))

    # Count
    count_query = (
        select(func.count(DocumentContact.id))
        .where(DocumentContact.contact_id == contact_id)
    )
    if role:
        count_query = count_query.where(DocumentContact.role == role.value)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    documents = [
        ContactDocumentInfo(
            id=doc.id,
            filename=doc.original_filename or doc.filename,
            document_type=doc.document_type,
            role=ContactRoleEnum(link.role),
            confidence=link.confidence,
            created_at=link.created_at,
        )
        for link, doc in rows
    ]

    return ContactDocumentsResponse(
        contact_id=contact_id,
        contact_name=contact.name,
        documents=documents,
        total=total,
    )


# ==================== Merge & Detect ====================


@router.post("/merge", response_model=MergeContactsResponse)
async def merge_contacts(
    request: MergeContactsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MergeContactsResponse:
    """Führt zwei Kontakte zusammen."""
    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id
    service = get_customer_detection_service()

    # Verify both contacts exist and belong to company
    source_result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.id == request.source_id,
                BusinessContact.company_id == company_id,
            )
        )
    )
    source = source_result.scalar_one_or_none()

    target_result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.id == request.target_id,
                BusinessContact.company_id == company_id,
            )
        )
    )
    target = target_result.scalar_one_or_none()

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quell-Kontakt nicht gefunden",
        )

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ziel-Kontakt nicht gefunden",
        )

    if source.merged_into_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quell-Kontakt wurde bereits zusammengeführt",
        )

    if target.merged_into_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ziel-Kontakt wurde bereits zusammengeführt",
        )

    # Merge using service - Multi-Tenant: company_id für Defense-in-Depth
    success = await service.merge_contacts(
        db=db,
        source_id=request.source_id,
        target_id=request.target_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Zusammenführung fehlgeschlagen",
        )

    # Refresh target
    await db.refresh(target)

    # Count transferred links
    link_count_result = await db.execute(
        select(func.count(DocumentContact.id)).where(
            DocumentContact.contact_id == request.target_id
        )
    )
    merged_links = link_count_result.scalar() or 0

    return MergeContactsResponse(
        success=True,
        target_contact=build_contact_response(target),
        merged_document_links=merged_links,
        message=f"Kontakt '{source.name}' wurde erfolgreich mit '{target.name}' zusammengeführt",
    )


@router.post("/detect", response_model=DetectContactsResponse)
async def detect_contacts(
    request: DetectContactsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DetectContactsResponse:
    """Erkennt Kontakte aus einem Dokument."""
    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id

    # Get document - Multi-Tenant Isolation via company_id
    doc_result = await db.execute(
        select(Document).where(
            and_(
                Document.id == request.document_id,
                Document.company_id == company_id,
            )
        )
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    service = get_customer_detection_service()

    # Multi-Tenant: company_id für sichere Isolation
    results = await service.process_document(
        db=db,
        document=document,
        owner_id=current_user.id,
        company_id=company_id,
        auto_create=request.auto_create,
    )

    await db.commit()

    new_count = sum(1 for r in results if r.get("created", False))
    existing_count = len(results) - new_count

    return DetectContactsResponse(
        document_id=request.document_id,
        detected_contacts=results,
        new_contacts_created=new_count,
        existing_contacts_matched=existing_count,
    )


@router.post("/{contact_id}/verify", response_model=BusinessContactResponse)
async def verify_contact(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessContactResponse:
    """Markiert einen Kontakt als manuell verifiziert."""
    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id

    result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.id == contact_id,
                BusinessContact.company_id == company_id,
            )
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kontakt nicht gefunden",
        )

    contact.is_verified = True
    contact.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(contact)

    logger.info("business_contact_verified", contact_id=str(contact_id))
    return build_contact_response(contact)


@router.get("/{contact_id}/similar", response_model=List[BusinessContactResponse])
async def find_similar_contacts(
    contact_id: UUID,
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Ähnlichkeitsschwelle"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[BusinessContactResponse]:
    """Findet ähnliche Kontakte (potenzielle Duplikate)."""
    # Multi-Tenant: company_id aus User-Context (IDOR Prevention)
    company_id = current_user.company_id

    # Get source contact
    result = await db.execute(
        select(BusinessContact).where(
            and_(
                BusinessContact.id == contact_id,
                BusinessContact.company_id == company_id,
            )
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kontakt nicht gefunden",
        )

    service = get_customer_detection_service()
    service.similarity_threshold = threshold

    # Multi-Tenant: company_id für sichere Isolation
    similar = await service.find_similar_contacts(
        db=db,
        name=contact.name,
        company_id=company_id,
    )

    # Filter out the source contact itself
    similar = [(c, score) for c, score in similar if c.id != contact_id][:limit]

    return [build_contact_response(c) for c, _ in similar]

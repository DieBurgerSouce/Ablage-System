# -*- coding: utf-8 -*-
"""
Knowledge Management API.

API-Endpoints fuer das Knowledge Management System:
- Notes: Wiki-artige Notizen mit Markdown
- Checklists: Aufgabenlisten mit Items
- Links: Knowledge Graph Verknuepfungen
- Tags: Kategorisierung

Alle Endpoints sind auf Deutsch lokalisiert.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db, get_current_user
from app.db.models import (
    KnowledgeNote,
    KnowledgeChecklist,
    KnowledgeChecklistItem,
    KnowledgeLink,
    KnowledgeTag,
    NoteType,
    ContentFormat,
    KnowledgeLinkType,
    LinkableType,
    User,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Management"])


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


# --- Notes ---

class NoteCreate(BaseModel):
    """Schema fuer das Erstellen einer Note."""

    title: str = Field(..., min_length=1, max_length=500)
    content: Optional[str] = None
    content_format: str = Field(default=ContentFormat.MARKDOWN.value)
    note_type: str = Field(default=NoteType.GENERAL.value)
    linked_document_id: Optional[UUID] = None
    linked_entity_id: Optional[UUID] = None
    linked_company_id: Optional[UUID] = None
    parent_note_id: Optional[UUID] = None
    is_pinned: bool = False
    is_template: bool = False
    tags: List[str] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    """Schema fuer das Aktualisieren einer Note."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = None
    content_format: Optional[str] = None
    note_type: Optional[str] = None
    linked_document_id: Optional[UUID] = None
    linked_entity_id: Optional[UUID] = None
    linked_company_id: Optional[UUID] = None
    parent_note_id: Optional[UUID] = None
    is_pinned: Optional[bool] = None
    is_template: Optional[bool] = None
    tags: Optional[List[str]] = None


class NoteResponse(BaseModel):
    """Schema fuer Note-Responses."""

    id: UUID
    title: str
    content: Optional[str]
    content_format: str
    note_type: str
    linked_document_id: Optional[UUID]
    linked_entity_id: Optional[UUID]
    linked_company_id: Optional[UUID]
    parent_note_id: Optional[UUID]
    is_pinned: bool
    is_template: bool
    view_count: int
    tags: List[str]
    created_by_id: Optional[UUID]
    updated_by_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NoteListResponse(BaseModel):
    """Schema fuer Note-Listen."""

    items: List[NoteResponse]
    total: int
    page: int
    page_size: int


# --- Checklists ---

class ChecklistItemCreate(BaseModel):
    """Schema fuer das Erstellen eines Checklist-Items."""

    text: str = Field(..., min_length=1, max_length=1000)
    description: Optional[str] = None
    sort_order: int = 0
    due_date: Optional[datetime] = None


class ChecklistItemUpdate(BaseModel):
    """Schema fuer das Aktualisieren eines Checklist-Items."""

    text: Optional[str] = Field(None, min_length=1, max_length=1000)
    description: Optional[str] = None
    is_completed: Optional[bool] = None
    sort_order: Optional[int] = None
    due_date: Optional[datetime] = None


class ChecklistItemResponse(BaseModel):
    """Schema fuer Checklist-Item-Responses."""

    id: UUID
    checklist_id: UUID
    text: str
    description: Optional[str]
    is_completed: bool
    completed_at: Optional[datetime]
    completed_by_id: Optional[UUID]
    sort_order: int
    due_date: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ChecklistCreate(BaseModel):
    """Schema fuer das Erstellen einer Checklist."""

    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    linked_document_id: Optional[UUID] = None
    linked_entity_id: Optional[UUID] = None
    linked_company_id: Optional[UUID] = None
    linked_note_id: Optional[UUID] = None
    is_template: bool = False
    items: List[ChecklistItemCreate] = Field(default_factory=list)


class ChecklistUpdate(BaseModel):
    """Schema fuer das Aktualisieren einer Checklist."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    linked_document_id: Optional[UUID] = None
    linked_entity_id: Optional[UUID] = None
    linked_company_id: Optional[UUID] = None
    linked_note_id: Optional[UUID] = None
    is_template: Optional[bool] = None


class ChecklistResponse(BaseModel):
    """Schema fuer Checklist-Responses."""

    id: UUID
    title: str
    description: Optional[str]
    linked_document_id: Optional[UUID]
    linked_entity_id: Optional[UUID]
    linked_company_id: Optional[UUID]
    linked_note_id: Optional[UUID]
    is_template: bool
    is_completed: bool
    completion_percentage: float
    completed_at: Optional[datetime]
    created_by_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    items: List[ChecklistItemResponse]

    model_config = ConfigDict(from_attributes=True)


class ChecklistListResponse(BaseModel):
    """Schema fuer Checklist-Listen."""

    items: List[ChecklistResponse]
    total: int
    page: int
    page_size: int


# --- Links ---

class LinkCreate(BaseModel):
    """Schema fuer das Erstellen eines Knowledge Links."""

    source_type: str
    source_id: UUID
    target_type: str
    target_id: UUID
    link_type: str = Field(default=KnowledgeLinkType.RELATED.value)
    description: Optional[str] = None
    is_bidirectional: bool = True


class LinkResponse(BaseModel):
    """Schema fuer Link-Responses."""

    id: UUID
    source_type: str
    source_id: UUID
    target_type: str
    target_id: UUID
    link_type: str
    description: Optional[str]
    confidence: Optional[float]
    is_bidirectional: bool
    created_by_id: Optional[UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Tags ---

class TagCreate(BaseModel):
    """Schema fuer das Erstellen eines Tags."""

    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    description: Optional[str] = None


class TagResponse(BaseModel):
    """Schema fuer Tag-Responses."""

    id: UUID
    name: str
    color: Optional[str]
    description: Optional[str]
    usage_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# NOTE ENDPOINTS
# =============================================================================


@router.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    data: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteResponse:
    """Erstellt eine neue Knowledge Note."""
    note = KnowledgeNote(
        title=data.title,
        content=data.content,
        content_format=data.content_format,
        note_type=data.note_type,
        linked_document_id=data.linked_document_id,
        linked_entity_id=data.linked_entity_id,
        linked_company_id=data.linked_company_id,
        parent_note_id=data.parent_note_id,
        is_pinned=data.is_pinned,
        is_template=data.is_template,
        tags=data.tags,
        created_by_id=current_user.id,
    )

    db.add(note)
    await db.commit()
    await db.refresh(note)

    logger.info("knowledge_note_created", note_id=str(note.id), title=note.title)
    return note


@router.get("/notes", response_model=NoteListResponse)
async def list_notes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    note_type: Optional[str] = None,
    linked_document_id: Optional[UUID] = None,
    linked_entity_id: Optional[UUID] = None,
    linked_company_id: Optional[UUID] = None,
    parent_note_id: Optional[UUID] = None,
    is_pinned: Optional[bool] = None,
    is_template: Optional[bool] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteListResponse:
    """Listet Knowledge Notes mit Filteroptionen."""
    query = select(KnowledgeNote).where(KnowledgeNote.deleted_at.is_(None))

    # Filter
    if note_type:
        query = query.where(KnowledgeNote.note_type == note_type)
    if linked_document_id:
        query = query.where(KnowledgeNote.linked_document_id == linked_document_id)
    if linked_entity_id:
        query = query.where(KnowledgeNote.linked_entity_id == linked_entity_id)
    if linked_company_id:
        query = query.where(KnowledgeNote.linked_company_id == linked_company_id)
    if parent_note_id is not None:
        query = query.where(KnowledgeNote.parent_note_id == parent_note_id)
    if is_pinned is not None:
        query = query.where(KnowledgeNote.is_pinned == is_pinned)
    if is_template is not None:
        query = query.where(KnowledgeNote.is_template == is_template)
    if tag:
        query = query.where(KnowledgeNote.tags.contains([tag]))
    if search:
        search_filter = or_(
            KnowledgeNote.title.ilike(f"%{search}%"),
            KnowledgeNote.content.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)

    # Count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(
        desc(KnowledgeNote.is_pinned),
        desc(KnowledgeNote.updated_at),
    ).offset(offset).limit(page_size)

    result = await db.execute(query)
    notes = list(result.scalars().all())

    return NoteListResponse(
        items=notes,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteResponse:
    """Ruft eine einzelne Knowledge Note ab."""
    result = await db.execute(
        select(KnowledgeNote)
        .where(KnowledgeNote.id == note_id)
        .where(KnowledgeNote.deleted_at.is_(None))
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notiz nicht gefunden",
        )

    # Increment view count
    note.view_count += 1
    await db.commit()

    return note


@router.patch("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    data: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteResponse:
    """Aktualisiert eine Knowledge Note."""
    result = await db.execute(
        select(KnowledgeNote)
        .where(KnowledgeNote.id == note_id)
        .where(KnowledgeNote.deleted_at.is_(None))
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notiz nicht gefunden",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    note.updated_by_id = current_user.id

    await db.commit()
    await db.refresh(note)

    logger.info("knowledge_note_updated", note_id=str(note_id))
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Loescht eine Knowledge Note (soft delete)."""
    result = await db.execute(
        select(KnowledgeNote)
        .where(KnowledgeNote.id == note_id)
        .where(KnowledgeNote.deleted_at.is_(None))
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notiz nicht gefunden",
        )

    note.deleted_at = datetime.utcnow()
    await db.commit()

    logger.info("knowledge_note_deleted", note_id=str(note_id))


# =============================================================================
# CHECKLIST ENDPOINTS
# =============================================================================


@router.post("/checklists", response_model=ChecklistResponse, status_code=status.HTTP_201_CREATED)
async def create_checklist(
    data: ChecklistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistResponse:
    """Erstellt eine neue Checklist mit Items."""
    checklist = KnowledgeChecklist(
        title=data.title,
        description=data.description,
        linked_document_id=data.linked_document_id,
        linked_entity_id=data.linked_entity_id,
        linked_company_id=data.linked_company_id,
        linked_note_id=data.linked_note_id,
        is_template=data.is_template,
        created_by_id=current_user.id,
    )

    # Add items
    for idx, item_data in enumerate(data.items):
        item = KnowledgeChecklistItem(
            text=item_data.text,
            description=item_data.description,
            sort_order=item_data.sort_order or idx,
            due_date=item_data.due_date,
        )
        checklist.items.append(item)

    db.add(checklist)
    await db.commit()
    await db.refresh(checklist)

    logger.info("knowledge_checklist_created", checklist_id=str(checklist.id))
    return checklist


@router.get("/checklists", response_model=ChecklistListResponse)
async def list_checklists(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    linked_document_id: Optional[UUID] = None,
    linked_entity_id: Optional[UUID] = None,
    linked_company_id: Optional[UUID] = None,
    linked_note_id: Optional[UUID] = None,
    is_template: Optional[bool] = None,
    is_completed: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistListResponse:
    """Listet Checklists mit Filteroptionen."""
    query = (
        select(KnowledgeChecklist)
        .options(selectinload(KnowledgeChecklist.items))
        .where(KnowledgeChecklist.deleted_at.is_(None))
    )

    # Filter
    if linked_document_id:
        query = query.where(KnowledgeChecklist.linked_document_id == linked_document_id)
    if linked_entity_id:
        query = query.where(KnowledgeChecklist.linked_entity_id == linked_entity_id)
    if linked_company_id:
        query = query.where(KnowledgeChecklist.linked_company_id == linked_company_id)
    if linked_note_id:
        query = query.where(KnowledgeChecklist.linked_note_id == linked_note_id)
    if is_template is not None:
        query = query.where(KnowledgeChecklist.is_template == is_template)
    if is_completed is not None:
        if is_completed:
            query = query.where(KnowledgeChecklist.completed_at.isnot(None))
        else:
            query = query.where(KnowledgeChecklist.completed_at.is_(None))
    if search:
        query = query.where(KnowledgeChecklist.title.ilike(f"%{search}%"))

    # Count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(desc(KnowledgeChecklist.updated_at)).offset(offset).limit(page_size)

    result = await db.execute(query)
    checklists = list(result.scalars().all())

    return ChecklistListResponse(
        items=checklists,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/checklists/{checklist_id}", response_model=ChecklistResponse)
async def get_checklist(
    checklist_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistResponse:
    """Ruft eine einzelne Checklist ab."""
    result = await db.execute(
        select(KnowledgeChecklist)
        .options(selectinload(KnowledgeChecklist.items))
        .where(KnowledgeChecklist.id == checklist_id)
        .where(KnowledgeChecklist.deleted_at.is_(None))
    )
    checklist = result.scalar_one_or_none()

    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkliste nicht gefunden",
        )

    return checklist


@router.patch("/checklists/{checklist_id}", response_model=ChecklistResponse)
async def update_checklist(
    checklist_id: UUID,
    data: ChecklistUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistResponse:
    """Aktualisiert eine Checklist."""
    result = await db.execute(
        select(KnowledgeChecklist)
        .options(selectinload(KnowledgeChecklist.items))
        .where(KnowledgeChecklist.id == checklist_id)
        .where(KnowledgeChecklist.deleted_at.is_(None))
    )
    checklist = result.scalar_one_or_none()

    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkliste nicht gefunden",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(checklist, field, value)

    await db.commit()
    await db.refresh(checklist)

    logger.info("knowledge_checklist_updated", checklist_id=str(checklist_id))
    return checklist


@router.delete("/checklists/{checklist_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_checklist(
    checklist_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Loescht eine Checklist (soft delete)."""
    result = await db.execute(
        select(KnowledgeChecklist)
        .where(KnowledgeChecklist.id == checklist_id)
        .where(KnowledgeChecklist.deleted_at.is_(None))
    )
    checklist = result.scalar_one_or_none()

    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkliste nicht gefunden",
        )

    checklist.deleted_at = datetime.utcnow()
    await db.commit()

    logger.info("knowledge_checklist_deleted", checklist_id=str(checklist_id))


# =============================================================================
# CHECKLIST ITEM ENDPOINTS
# =============================================================================


@router.post("/checklists/{checklist_id}/items", response_model=ChecklistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_checklist_item(
    checklist_id: UUID,
    data: ChecklistItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistItemResponse:
    """Fuegt ein Item zu einer Checklist hinzu."""
    result = await db.execute(
        select(KnowledgeChecklist)
        .where(KnowledgeChecklist.id == checklist_id)
        .where(KnowledgeChecklist.deleted_at.is_(None))
    )
    checklist = result.scalar_one_or_none()

    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkliste nicht gefunden",
        )

    item = KnowledgeChecklistItem(
        checklist_id=checklist_id,
        text=data.text,
        description=data.description,
        sort_order=data.sort_order,
        due_date=data.due_date,
    )

    db.add(item)
    await db.commit()
    await db.refresh(item)

    logger.info("checklist_item_added", checklist_id=str(checklist_id), item_id=str(item.id))
    return item


@router.patch("/checklists/{checklist_id}/items/{item_id}", response_model=ChecklistItemResponse)
async def update_checklist_item(
    checklist_id: UUID,
    item_id: UUID,
    data: ChecklistItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChecklistItemResponse:
    """Aktualisiert ein Checklist-Item."""
    result = await db.execute(
        select(KnowledgeChecklistItem)
        .where(KnowledgeChecklistItem.id == item_id)
        .where(KnowledgeChecklistItem.checklist_id == checklist_id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item nicht gefunden",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # Handle completion status
    if "is_completed" in update_data:
        if update_data["is_completed"] and not item.is_completed:
            item.completed_at = datetime.utcnow()
            item.completed_by_id = current_user.id
        elif not update_data["is_completed"] and item.is_completed:
            item.completed_at = None
            item.completed_by_id = None

    for field, value in update_data.items():
        setattr(item, field, value)

    # Check if checklist is now complete
    result = await db.execute(
        select(KnowledgeChecklist)
        .options(selectinload(KnowledgeChecklist.items))
        .where(KnowledgeChecklist.id == checklist_id)
    )
    checklist = result.scalar_one()
    if checklist.is_completed and not checklist.completed_at:
        checklist.completed_at = datetime.utcnow()
    elif not checklist.is_completed and checklist.completed_at:
        checklist.completed_at = None

    await db.commit()
    await db.refresh(item)

    logger.info("checklist_item_updated", item_id=str(item_id))
    return item


@router.delete("/checklists/{checklist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_checklist_item(
    checklist_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Loescht ein Checklist-Item."""
    result = await db.execute(
        select(KnowledgeChecklistItem)
        .where(KnowledgeChecklistItem.id == item_id)
        .where(KnowledgeChecklistItem.checklist_id == checklist_id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item nicht gefunden",
        )

    await db.delete(item)
    await db.commit()

    logger.info("checklist_item_deleted", item_id=str(item_id))


# =============================================================================
# LINK ENDPOINTS
# =============================================================================


@router.post("/links", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
async def create_link(
    data: LinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LinkResponse:
    """Erstellt eine Knowledge Graph Verknuepfung."""
    # Validate types
    valid_types = [lt.value for lt in LinkableType]
    if data.source_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger source_type. Erlaubt: {valid_types}",
        )
    if data.target_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger target_type. Erlaubt: {valid_types}",
        )

    # Check if link already exists
    existing = await db.execute(
        select(KnowledgeLink).where(
            and_(
                KnowledgeLink.source_type == data.source_type,
                KnowledgeLink.source_id == data.source_id,
                KnowledgeLink.target_type == data.target_type,
                KnowledgeLink.target_id == data.target_id,
                KnowledgeLink.link_type == data.link_type,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Verknuepfung existiert bereits",
        )

    link = KnowledgeLink(
        source_type=data.source_type,
        source_id=data.source_id,
        target_type=data.target_type,
        target_id=data.target_id,
        link_type=data.link_type,
        description=data.description,
        is_bidirectional=data.is_bidirectional,
        created_by_id=current_user.id,
    )

    db.add(link)
    await db.commit()
    await db.refresh(link)

    logger.info("knowledge_link_created", link_id=str(link.id))
    return link


@router.get("/links", response_model=List[LinkResponse])
async def list_links(
    source_type: Optional[str] = None,
    source_id: Optional[UUID] = None,
    target_type: Optional[str] = None,
    target_id: Optional[UUID] = None,
    link_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[LinkResponse]:
    """Listet Knowledge Links mit Filteroptionen."""
    query = select(KnowledgeLink)

    if source_type:
        query = query.where(KnowledgeLink.source_type == source_type)
    if source_id:
        query = query.where(KnowledgeLink.source_id == source_id)
    if target_type:
        query = query.where(KnowledgeLink.target_type == target_type)
    if target_id:
        query = query.where(KnowledgeLink.target_id == target_id)
    if link_type:
        query = query.where(KnowledgeLink.link_type == link_type)

    query = query.order_by(desc(KnowledgeLink.created_at)).limit(100)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/links/for/{object_type}/{object_id}", response_model=List[LinkResponse])
async def get_links_for_object(
    object_type: str,
    object_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[LinkResponse]:
    """Ruft alle Links fuer ein Objekt ab (als Source oder Target)."""
    result = await db.execute(
        select(KnowledgeLink).where(
            or_(
                and_(
                    KnowledgeLink.source_type == object_type,
                    KnowledgeLink.source_id == object_id,
                ),
                and_(
                    KnowledgeLink.target_type == object_type,
                    KnowledgeLink.target_id == object_id,
                    KnowledgeLink.is_bidirectional == True,
                ),
            )
        )
    )
    return list(result.scalars().all())


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_link(
    link_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Loescht eine Knowledge Graph Verknuepfung."""
    result = await db.execute(
        select(KnowledgeLink).where(KnowledgeLink.id == link_id)
    )
    link = result.scalar_one_or_none()

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verknuepfung nicht gefunden",
        )

    await db.delete(link)
    await db.commit()

    logger.info("knowledge_link_deleted", link_id=str(link_id))


# =============================================================================
# TAG ENDPOINTS
# =============================================================================


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    data: TagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TagResponse:
    """Erstellt einen neuen Tag."""
    # Check if tag exists
    existing = await db.execute(
        select(KnowledgeTag).where(KnowledgeTag.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag existiert bereits",
        )

    tag = KnowledgeTag(
        name=data.name,
        color=data.color,
        description=data.description,
    )

    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    logger.info("knowledge_tag_created", tag_name=tag.name)
    return tag


@router.get("/tags", response_model=List[TagResponse])
async def list_tags(
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TagResponse]:
    """Listet alle Tags sortiert nach Nutzungshaeufigkeit."""
    query = select(KnowledgeTag)

    if search:
        query = query.where(KnowledgeTag.name.ilike(f"%{search}%"))

    query = query.order_by(desc(KnowledgeTag.usage_count)).limit(100)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_tag(
    tag_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Loescht einen Tag."""
    result = await db.execute(
        select(KnowledgeTag).where(KnowledgeTag.id == tag_id)
    )
    tag = result.scalar_one_or_none()

    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag nicht gefunden",
        )

    await db.delete(tag)
    await db.commit()

    logger.info("knowledge_tag_deleted", tag_name=tag.name)

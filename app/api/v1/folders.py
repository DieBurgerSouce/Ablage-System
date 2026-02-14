# -*- coding: utf-8 -*-
"""
Folder Management API Endpoints.

REST API fuer die geschaeftliche Ordnerverwaltung:
- Hierarchische Ordnerstruktur (CRUD)
- Drag-Drop Reorganisation
- Dokument-Zuordnung
- Berechtigungsvererbung
- Ordnersuche

Feinpoliert und durchdacht - Enterprise Document Filing.
"""

from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.models_folder import FolderPermissionLevel, FolderType
from app.services.folder_service import get_folder_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/folders", tags=["Ordner"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class FolderCreate(BaseModel):
    """Schema fuer Ordner-Erstellung."""
    name: str = Field(..., min_length=1, max_length=255, description="Ordnername")
    parent_id: Optional[UUID] = Field(None, description="Eltern-Ordner (leer = Root)")
    description: Optional[str] = Field(None, max_length=2000)
    icon: str = Field("Folder", max_length=50)
    color: Optional[str] = Field(None, max_length=7, pattern=r"^#[0-9A-Fa-f]{6}$")
    folder_type: str = Field(FolderType.GESCHAEFTLICH.value, description="Ordnertyp")
    folder_metadata: Optional[Dict] = Field(None)


class FolderUpdate(BaseModel):
    """Schema fuer Ordner-Aktualisierung."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=7, pattern=r"^#[0-9A-Fa-f]{6}$")
    folder_type: Optional[str] = None
    folder_metadata: Optional[Dict] = None


class FolderResponse(BaseModel):
    """Schema fuer Ordner-Antwort."""
    id: UUID
    company_id: UUID
    parent_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    icon: str
    color: Optional[str] = None
    path: str
    level: int
    sort_order: int
    folder_type: str
    document_count: int
    subfolder_count: int
    is_locked: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class FolderMoveRequest(BaseModel):
    """Schema fuer Ordner-Verschiebung."""
    new_parent_id: Optional[UUID] = Field(None, description="Neuer Eltern-Ordner (leer = Root)")


class DocumentAddRequest(BaseModel):
    """Schema fuer Dokument-Zuordnung."""
    document_id: UUID = Field(..., description="Dokument-ID")
    is_primary: bool = Field(True, description="Primaerer Ordner")


class ReorderRequest(BaseModel):
    """Schema fuer Ordner-Neuordnung."""
    folder_order: List[UUID] = Field(..., description="Ordner-IDs in gewuenschter Reihenfolge")


class PermissionSetRequest(BaseModel):
    """Schema fuer Berechtigungs-Vergabe."""
    user_id: UUID = Field(..., description="User-ID")
    permission_level: str = Field(
        FolderPermissionLevel.READ.value,
        description="Berechtigungsstufe (read/write/admin)",
    )
    propagate: bool = Field(True, description="An Unterordner vererben")


class PermissionResponse(BaseModel):
    """Schema fuer Berechtigungs-Antwort."""
    id: UUID
    folder_id: UUID
    user_id: UUID
    permission_level: str
    inherited: bool
    inherited_from_id: Optional[UUID] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class FolderStatsResponse(BaseModel):
    """Schema fuer Ordner-Statistiken."""
    folder_id: str
    name: str
    direct_documents: int
    direct_subfolders: int
    total_documents_recursive: int
    total_subfolders_recursive: int
    level: int
    is_locked: bool


class BreadcrumbItem(BaseModel):
    """Einzelnes Breadcrumb-Element."""
    id: str
    name: str
    icon: Optional[str] = None


class DocumentMoveRequest(BaseModel):
    """Schema fuer Dokument-Verschiebung zwischen Ordnern."""
    target_folder_id: UUID = Field(..., description="Ziel-Ordner-ID")


# ============================================================================
# Helper
# ============================================================================


def _folder_to_response(folder) -> FolderResponse:
    """Konvertiert Folder-ORM-Objekt in Pydantic-Response."""
    return FolderResponse(
        id=folder.id,
        company_id=folder.company_id,
        parent_id=folder.parent_id,
        name=folder.name,
        description=folder.description,
        icon=folder.icon,
        color=folder.color,
        path=folder.path,
        level=folder.level,
        sort_order=folder.sort_order,
        folder_type=folder.folder_type,
        document_count=folder.document_count,
        subfolder_count=folder.subfolder_count,
        is_locked=folder.is_locked,
        created_at=folder.created_at.isoformat() if folder.created_at else None,
        updated_at=folder.updated_at.isoformat() if folder.updated_at else None,
    )


# ============================================================================
# CRUD Endpoints
# ============================================================================


@router.post(
    "",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ordner erstellen",
    description="Erstellt einen neuen Ordner in der Geschaeftsablage",
)
async def create_folder(
    body: FolderCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    """Neuen Ordner erstellen."""
    service = get_folder_service()
    try:
        folder = await service.create_folder(
            db,
            company_id=current_user.company_id,
            name=body.name,
            created_by_id=current_user.id,
            parent_id=body.parent_id,
            description=body.description,
            icon=body.icon,
            color=body.color,
            folder_type=body.folder_type,
            folder_metadata=body.folder_metadata,
        )
        await db.commit()
        return _folder_to_response(folder)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.error("folder_create_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ordner konnte nicht erstellt werden",
        )


@router.get(
    "",
    response_model=List[FolderResponse],
    summary="Ordner auflisten",
    description="Listet alle Ordner der aktuellen Firma",
)
async def list_folders(
    parent_id: Optional[UUID] = Query(None, description="Eltern-Ordner filtern"),
    folder_type: Optional[str] = Query(None, description="Nach Typ filtern"),
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[FolderResponse]:
    """Ordner auflisten mit optionaler Filterung."""
    service = get_folder_service()
    from sqlalchemy import select, and_
    from app.db.models_folder import Folder

    conditions = [
        Folder.company_id == current_user.company_id,
        Folder.deleted_at.is_(None),
    ]

    if parent_id is not None:
        conditions.append(Folder.parent_id == parent_id)

    if folder_type is not None:
        conditions.append(Folder.folder_type == folder_type)

    query = (
        select(Folder)
        .where(and_(*conditions))
        .order_by(Folder.sort_order, Folder.name)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    folders = result.scalars().all()

    return [_folder_to_response(f) for f in folders]


@router.get(
    "/{folder_id}",
    response_model=FolderResponse,
    summary="Ordner abrufen",
    description="Einzelnen Ordner mit Details abrufen",
)
async def get_folder(
    folder_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    """Einzelnen Ordner abrufen."""
    service = get_folder_service()
    folder = await service.get_folder(
        db, folder_id, current_user.company_id, current_user.id
    )
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordner nicht gefunden oder keine Berechtigung",
        )
    return _folder_to_response(folder)


@router.patch(
    "/{folder_id}",
    response_model=FolderResponse,
    summary="Ordner aktualisieren",
    description="Ordner-Eigenschaften aendern",
)
async def update_folder(
    folder_id: UUID,
    body: FolderUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    """Ordner aktualisieren."""
    service = get_folder_service()
    try:
        folder = await service.update_folder(
            db,
            folder_id,
            current_user.company_id,
            current_user.id,
            name=body.name,
            description=body.description,
            icon=body.icon,
            color=body.color,
            folder_type=body.folder_type,
            folder_metadata=body.folder_metadata,
        )
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ordner nicht gefunden",
            )
        await db.commit()
        return _folder_to_response(folder)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ordner loeschen",
    description="Ordner und Unterordner weich loeschen",
)
async def delete_folder(
    folder_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Ordner loeschen (Soft Delete)."""
    service = get_folder_service()
    try:
        deleted = await service.soft_delete_folder(
            db, folder_id, current_user.company_id, current_user.id
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ordner nicht gefunden",
            )
        await db.commit()
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# Hierarchie Endpoints
# ============================================================================


@router.get(
    "/tree",
    summary="Ordnerbaum abrufen",
    description="Vollstaendige Ordnerhierarchie als Baum",
)
async def get_folder_tree(
    parent_id: Optional[UUID] = Query(None, description="Start-Ordner"),
    max_depth: int = Query(10, ge=1, le=20, description="Max. Tiefe"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict]:
    """Ordnerbaum als verschachtelte Struktur."""
    service = get_folder_service()
    return await service.get_folder_tree(
        db, current_user.company_id, current_user.id, parent_id, max_depth
    )


@router.get(
    "/{folder_id}/breadcrumbs",
    response_model=List[BreadcrumbItem],
    summary="Breadcrumb-Pfad",
    description="Pfad vom Root-Ordner zum aktuellen Ordner",
)
async def get_breadcrumbs(
    folder_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[BreadcrumbItem]:
    """Breadcrumb-Pfad abrufen."""
    service = get_folder_service()
    crumbs = await service.get_breadcrumbs(db, folder_id, current_user.company_id)
    return [BreadcrumbItem(**c) for c in crumbs]


@router.post(
    "/{folder_id}/move",
    response_model=FolderResponse,
    summary="Ordner verschieben",
    description="Ordner in einen anderen Ordner verschieben",
)
async def move_folder(
    folder_id: UUID,
    body: FolderMoveRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    """Ordner verschieben."""
    service = get_folder_service()
    try:
        folder = await service.move_folder(
            db, folder_id, body.new_parent_id, current_user.company_id, current_user.id
        )
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ordner nicht gefunden",
            )
        await db.commit()
        return _folder_to_response(folder)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# Dokument-Zuordnung Endpoints
# ============================================================================


@router.post(
    "/{folder_id}/documents",
    status_code=status.HTTP_201_CREATED,
    summary="Dokument zum Ordner hinzufuegen",
    description="Ordnet ein Dokument einem Ordner zu",
)
async def add_document_to_folder(
    folder_id: UUID,
    body: DocumentAddRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Dokument zum Ordner hinzufuegen."""
    service = get_folder_service()
    try:
        fd = await service.add_document_to_folder(
            db, folder_id, body.document_id, current_user.id,
            current_user.company_id, body.is_primary,
        )
        await db.commit()
        return {
            "id": str(fd.id),
            "folder_id": str(fd.folder_id),
            "document_id": str(fd.document_id),
            "is_primary": fd.is_primary,
            "nachricht": "Dokument erfolgreich zugeordnet",
        }
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{folder_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dokument aus Ordner entfernen",
)
async def remove_document_from_folder(
    folder_id: UUID,
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Dokument aus Ordner entfernen."""
    service = get_folder_service()
    try:
        removed = await service.remove_document_from_folder(
            db, folder_id, document_id, current_user.id
        )
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument nicht in diesem Ordner",
            )
        await db.commit()
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/{folder_id}/documents",
    summary="Ordner-Dokumente auflisten",
    description="Alle Dokumente eines Ordners mit Pagination",
)
async def list_folder_documents(
    folder_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Dokumente eines Ordners auflisten."""
    service = get_folder_service()
    documents, total = await service.get_folder_documents(
        db, folder_id, current_user.id, current_user.company_id, page, per_page
    )
    return {
        "items": [
            {
                "id": str(d.id),
                "filename": d.filename,
                "original_filename": d.original_filename,
                "document_type": d.document_type,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in documents
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post(
    "/{folder_id}/documents/{document_id}/move",
    summary="Dokument verschieben",
    description="Dokument in einen anderen Ordner verschieben",
)
async def move_document(
    folder_id: UUID,
    document_id: UUID,
    body: DocumentMoveRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Dokument zwischen Ordnern verschieben."""
    service = get_folder_service()
    try:
        moved = await service.move_document_between_folders(
            db, document_id, folder_id, body.target_folder_id,
            current_user.id, current_user.company_id,
        )
        if not moved:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument nicht in diesem Ordner gefunden",
            )
        await db.commit()
        return {"nachricht": "Dokument erfolgreich verschoben"}
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ============================================================================
# Sortierung
# ============================================================================


@router.post(
    "/{folder_id}/reorder",
    summary="Unterordner sortieren",
    description="Sortierreihenfolge der Unterordner aendern (Drag-Drop)",
)
async def reorder_folders(
    folder_id: UUID,
    body: ReorderRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Unterordner neu sortieren."""
    service = get_folder_service()
    success = await service.reorder_folders(
        db, folder_id, current_user.company_id, current_user.id, body.folder_order
    )
    if success:
        await db.commit()
    return {"nachricht": "Sortierung aktualisiert", "erfolg": success}


# ============================================================================
# Berechtigungen
# ============================================================================


@router.get(
    "/{folder_id}/permissions",
    response_model=List[PermissionResponse],
    summary="Berechtigungen abrufen",
)
async def get_permissions(
    folder_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[PermissionResponse]:
    """Berechtigungen eines Ordners abrufen."""
    service = get_folder_service()

    if not await service.check_folder_access(db, folder_id, current_user.id, "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Admins koennen Berechtigungen einsehen",
        )

    perms = await service.get_folder_permissions(db, folder_id)
    return [
        PermissionResponse(
            id=p.id,
            folder_id=p.folder_id,
            user_id=p.user_id,
            permission_level=p.permission_level,
            inherited=p.inherited,
            inherited_from_id=p.inherited_from_id,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in perms
    ]


@router.post(
    "/{folder_id}/permissions",
    status_code=status.HTTP_201_CREATED,
    summary="Berechtigung vergeben",
)
async def set_permission(
    folder_id: UUID,
    body: PermissionSetRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Berechtigung fuer einen Ordner vergeben."""
    service = get_folder_service()
    try:
        perm = await service.set_folder_permission(
            db, folder_id, body.user_id, body.permission_level,
            current_user.id, current_user.company_id, body.propagate,
        )
        await db.commit()
        return {
            "id": str(perm.id),
            "nachricht": "Berechtigung erfolgreich gesetzt",
            "vererbung": body.propagate,
        }
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ============================================================================
# Statistiken
# ============================================================================


@router.get(
    "/{folder_id}/stats",
    response_model=FolderStatsResponse,
    summary="Ordner-Statistiken",
    description="Detaillierte Statistiken inklusive rekursiver Zaehlung",
)
async def get_folder_stats(
    folder_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FolderStatsResponse:
    """Ordner-Statistiken abrufen."""
    service = get_folder_service()
    stats = await service.get_folder_stats(db, folder_id, current_user.company_id)
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordner nicht gefunden",
        )
    return FolderStatsResponse(**stats)


# ============================================================================
# Suche
# ============================================================================


@router.get(
    "/search",
    summary="Ordner suchen",
    description="Ordner nach Name suchen",
)
async def search_folders(
    q: str = Query(..., min_length=1, description="Suchbegriff"),
    folder_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Ordner suchen."""
    service = get_folder_service()
    folders, total = await service.search_folders(
        db, current_user.company_id, current_user.id,
        q, folder_type, page, per_page,
    )
    return {
        "items": [_folder_to_response(f) for f in folders],
        "total": total,
        "page": page,
        "per_page": per_page,
    }

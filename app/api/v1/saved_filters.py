# -*- coding: utf-8 -*-
"""API Endpoints fuer Saved Filters.

Phase 4.5: Frontend UX Enhancement - Saved Filters + Sharing

Endpoints:
- GET /api/v1/saved-filters?feature=documents - Liste Filter fuer Feature
- GET /api/v1/saved-filters/{id} - Einzelner Filter
- POST /api/v1/saved-filters - Neuen Filter erstellen
- PATCH /api/v1/saved-filters/{id} - Filter aktualisieren
- DELETE /api/v1/saved-filters/{id} - Filter loeschen
- POST /api/v1/saved-filters/{id}/use - Nutzung aufzeichnen
- POST /api/v1/saved-filters/{id}/duplicate - Filter duplizieren
- POST /api/v1/saved-filters/{id}/set-default - Als Default setzen
- DELETE /api/v1/saved-filters/default/{feature} - Default entfernen
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User, SavedFilter
from app.services.saved_filter_service import SavedFilterService, ALLOWED_FEATURES
from app.core.exceptions import NotFoundError, ForbiddenError, ValidationError
from app.core.safe_errors import safe_error_detail


router = APIRouter(prefix="/saved-filters", tags=["Saved Filters"])


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class FilterConfigSchema(BaseModel):
    """Schema fuer Filter-Konfiguration (flexibel)."""

    class Config:
        extra = "allow"  # Erlaube beliebige zusaetzliche Felder


class SavedFilterCreate(BaseModel):
    """Schema zum Erstellen eines Filters."""
    name: str = Field(..., min_length=1, max_length=255, description="Anzeigename")
    feature: str = Field(..., description=f"Feature: {', '.join(sorted(ALLOWED_FEATURES))}")
    filter_config: dict = Field(default_factory=dict, description="Filter-Konfiguration")
    description: Optional[str] = Field(None, max_length=1000, description="Beschreibung")
    is_shared: bool = Field(False, description="Mit Team teilen")
    is_default: bool = Field(False, description="Als Standard verwenden")


class SavedFilterUpdate(BaseModel):
    """Schema zum Aktualisieren eines Filters."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    filter_config: Optional[dict] = None
    description: Optional[str] = Field(None, max_length=1000)
    is_shared: Optional[bool] = None
    is_default: Optional[bool] = None


class SavedFilterResponse(BaseModel):
    """Schema fuer Filter-Response."""
    id: UUID
    name: str
    description: Optional[str]
    feature: str
    filter_config: dict
    is_shared: bool
    is_default: bool
    use_count: int
    last_used_at: Optional[str]
    created_at: str
    updated_at: str
    is_own: bool = Field(description="True wenn eigener Filter, False wenn geteilt")

    class Config:
        from_attributes = True


class SavedFilterListResponse(BaseModel):
    """Schema fuer Filter-Listen-Response."""
    filters: List[SavedFilterResponse]
    total: int


class DuplicateFilterRequest(BaseModel):
    """Schema zum Duplizieren eines Filters."""
    new_name: Optional[str] = Field(None, max_length=255, description="Neuer Name (optional)")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _filter_to_response(
    saved_filter: SavedFilter,
    current_user_id: UUID,
) -> SavedFilterResponse:
    """Konvertiere SavedFilter Model zu Response Schema."""
    return SavedFilterResponse(
        id=saved_filter.id,
        name=saved_filter.name,
        description=saved_filter.description,
        feature=saved_filter.feature,
        filter_config=saved_filter.filter_config,
        is_shared=saved_filter.is_shared,
        is_default=saved_filter.is_default,
        use_count=saved_filter.use_count,
        last_used_at=saved_filter.last_used_at.isoformat() if saved_filter.last_used_at else None,
        created_at=saved_filter.created_at.isoformat() if saved_filter.created_at else "",
        updated_at=saved_filter.updated_at.isoformat() if saved_filter.updated_at else "",
        is_own=saved_filter.user_id == current_user_id,
    )


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get("", response_model=SavedFilterListResponse)
async def list_saved_filters(
    feature: str = Query(..., description=f"Feature: {', '.join(sorted(ALLOWED_FEATURES))}"),
    include_shared: bool = Query(True, description="Geteilte Filter einschliessen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedFilterListResponse:
    """Liste alle gespeicherten Filter fuer ein Feature.

    Gibt eigene Filter und (optional) geteilte Filter der Company zurueck.
    Sortiert nach: Default > Eigene > Geteilte, dann nach Nutzungshaeufigkeit.
    """
    service = SavedFilterService(db)

    try:
        filters = await service.get_filters_for_feature(
            user_id=current_user.id,
            company_id=current_user.company_id,
            feature=feature,
            include_shared=include_shared,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Filter"),
        )

    filter_responses = [
        _filter_to_response(f, current_user.id) for f in filters
    ]

    return SavedFilterListResponse(
        filters=filter_responses,
        total=len(filter_responses),
    )


@router.get("/{filter_id}", response_model=SavedFilterResponse)
async def get_saved_filter(
    filter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedFilterResponse:
    """Hole einen einzelnen gespeicherten Filter.

    Gibt den Filter zurueck wenn:
    - Der User der Eigentuemer ist, ODER
    - Der Filter geteilt ist und zur gleichen Company gehoert
    """
    service = SavedFilterService(db)

    try:
        saved_filter = await service.get_filter_by_id(
            filter_id=filter_id,
            user_id=current_user.id,
            company_id=current_user.company_id,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Filter"),
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Filter"),
        )

    return _filter_to_response(saved_filter, current_user.id)


@router.post("", response_model=SavedFilterResponse, status_code=status.HTTP_201_CREATED)
async def create_saved_filter(
    data: SavedFilterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedFilterResponse:
    """Erstelle einen neuen gespeicherten Filter.

    Filter werden initial dem aktuellen User zugeordnet.
    Optional kann is_shared=true gesetzt werden um den Filter zu teilen.
    """
    service = SavedFilterService(db)

    try:
        saved_filter = await service.create_filter(
            user_id=current_user.id,
            company_id=current_user.company_id,
            name=data.name,
            feature=data.feature,
            filter_config=data.filter_config,
            description=data.description,
            is_shared=data.is_shared,
            is_default=data.is_default,
        )
        await db.commit()
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Filter"),
        )

    return _filter_to_response(saved_filter, current_user.id)


@router.patch("/{filter_id}", response_model=SavedFilterResponse)
async def update_saved_filter(
    filter_id: UUID,
    data: SavedFilterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedFilterResponse:
    """Aktualisiere einen gespeicherten Filter.

    Nur der Eigentuemer kann den Filter bearbeiten.
    """
    service = SavedFilterService(db)

    try:
        saved_filter = await service.update_filter(
            filter_id=filter_id,
            user_id=current_user.id,
            company_id=current_user.company_id,
            name=data.name,
            filter_config=data.filter_config,
            description=data.description,
            is_shared=data.is_shared,
            is_default=data.is_default,
        )
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Filter"),
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Filter"),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Filter"),
        )

    return _filter_to_response(saved_filter, current_user.id)


@router.delete("/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_filter(
    filter_id: UUID,
    hard_delete: bool = Query(False, description="Permanent loeschen statt Soft-Delete"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loesche einen gespeicherten Filter.

    Standardmaessig Soft-Delete (wiederherstellbar).
    Mit hard_delete=true wird der Filter permanent geloescht.
    """
    service = SavedFilterService(db)

    try:
        await service.delete_filter(
            filter_id=filter_id,
            user_id=current_user.id,
            hard_delete=hard_delete,
        )
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Filter"),
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Filter"),
        )


@router.post("/{filter_id}/use", status_code=status.HTTP_204_NO_CONTENT)
async def record_filter_usage(
    filter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Zeichne Nutzung eines Filters auf.

    Erhoeht den use_count und aktualisiert last_used_at.
    Kann fuer eigene und geteilte Filter aufgerufen werden.
    """
    service = SavedFilterService(db)

    try:
        await service.record_filter_usage(
            filter_id=filter_id,
            user_id=current_user.id,
            company_id=current_user.company_id,
        )
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Filter"),
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Filter"),
        )


@router.post("/{filter_id}/duplicate", response_model=SavedFilterResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_saved_filter(
    filter_id: UUID,
    data: DuplicateFilterRequest = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedFilterResponse:
    """Dupliziere einen Filter.

    Erstellt eine Kopie des Filters fuer den aktuellen User.
    Funktioniert auch fuer geteilte Filter.
    Die Kopie ist initial privat (nicht geteilt).
    """
    service = SavedFilterService(db)

    try:
        new_filter = await service.duplicate_filter(
            filter_id=filter_id,
            user_id=current_user.id,
            company_id=current_user.company_id,
            new_name=data.new_name if data else None,
        )
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Filter"),
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Filter"),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Filter"),
        )

    return _filter_to_response(new_filter, current_user.id)


@router.post("/{filter_id}/set-default", response_model=SavedFilterResponse)
async def set_default_filter(
    filter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedFilterResponse:
    """Setze einen Filter als Standard fuer das Feature.

    Der bisherige Standard-Filter (falls vorhanden) wird zurueckgesetzt.
    Funktioniert fuer eigene und geteilte Filter.
    """
    service = SavedFilterService(db)

    try:
        saved_filter = await service.set_default_filter(
            filter_id=filter_id,
            user_id=current_user.id,
            company_id=current_user.company_id,
        )
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Filter"),
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Filter"),
        )

    return _filter_to_response(saved_filter, current_user.id)


@router.delete("/default/{feature}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_default_filter(
    feature: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Entferne den Standard-Filter fuer ein Feature.

    Nach dem Aufruf hat der User keinen Standard-Filter mehr fuer dieses Feature.
    """
    service = SavedFilterService(db)

    try:
        await service.clear_default_filter(
            user_id=current_user.id,
            feature=feature,
        )
        await db.commit()
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Filter"),
        )


@router.get("/features/list", response_model=List[str])
async def list_available_features() -> List[str]:
    """Liste aller verfuegbaren Features fuer Filter.

    Gibt die erlaubten Feature-Namen zurueck, die beim Erstellen
    von Filtern verwendet werden koennen.
    """
    return sorted(ALLOWED_FEATURES)


@router.post("/{filter_id}/share", response_model=SavedFilterResponse)
async def share_saved_filter(
    filter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedFilterResponse:
    """Teile einen Filter mit der Company.

    Nur der Eigentuemer kann einen Filter teilen.
    Geteilte Filter sind fuer alle User der gleichen Company sichtbar.
    """
    service = SavedFilterService(db)

    try:
        saved_filter = await service.share_filter(
            filter_id=filter_id,
            user_id=current_user.id,
            company_id=current_user.company_id,
        )
        await db.commit()
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Filter"),
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Filter"),
        )

    return _filter_to_response(saved_filter, current_user.id)


@router.get("/shared", response_model=SavedFilterListResponse)
async def list_shared_filters(
    feature: Optional[str] = Query(None, description=f"Feature: {', '.join(sorted(ALLOWED_FEATURES))}"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedFilterListResponse:
    """Liste alle mit mir geteilte Filter.

    Gibt Filter zurueck die von anderen Usern der gleichen Company
    geteilt wurden.
    """
    service = SavedFilterService(db)

    try:
        filters = await service.get_shared_filters(
            user_id=current_user.id,
            company_id=current_user.company_id,
            feature=feature,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Filter"),
        )

    filter_responses = [
        _filter_to_response(f, current_user.id) for f in filters
    ]

    return SavedFilterListResponse(
        filters=filter_responses,
        total=len(filter_responses),
    )

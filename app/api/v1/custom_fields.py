# -*- coding: utf-8 -*-
"""Custom Fields API Endpoints.

Stellt REST API Endpoints bereit fuer:
- Felddefinitionen verwalten (Admin)
- Feldwerte auf Dokumenten setzen/lesen
"""

from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Company
from app.middleware.company_context import require_company
from app.api.dependencies import get_current_active_user, get_db, require_admin
from app.api.schemas.custom_fields import (
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionUpdate,
    CustomFieldDefinitionResponse,
    CustomFieldDefinitionListResponse,
    CustomFieldValueSet,
    CustomFieldValueResponse,
)
from app.services.custom_field_service import (
    CustomFieldService,
    CustomFieldValidationError,
    get_custom_field_service,
)
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/custom-fields", tags=["custom-fields"])


# =============================================================================
# Helper
# =============================================================================

def _get_service() -> CustomFieldService:
    return get_custom_field_service()


# =============================================================================
# Definition Endpoints (Admin)
# =============================================================================

@router.get(
    "/definitions",
    response_model=CustomFieldDefinitionListResponse,
    summary="Felddefinitionen auflisten",
)
async def list_definitions(
    document_type: Optional[str] = Query(
        None, description="Nach Dokumenttyp filtern"
    ),
    include_inactive: bool = Query(
        False, description="Auch deaktivierte Felder anzeigen"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> CustomFieldDefinitionListResponse:
    """Listet alle benutzerdefinierten Felddefinitionen.

    Gibt Felder zurueck die fuer den angegebenen Dokumenttyp oder
    alle Dokumenttypen gelten.
    """
    service = _get_service()
    definitions = await service.list_definitions(
        db,
        company_id=company.id,
        document_type=document_type,
        include_inactive=include_inactive,
    )
    items = [
        CustomFieldDefinitionResponse.model_validate(d) for d in definitions
    ]
    return CustomFieldDefinitionListResponse(items=items, total=len(items))


@router.post(
    "/definitions",
    response_model=CustomFieldDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Felddefinition erstellen",
)
async def create_definition(
    data: CustomFieldDefinitionCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> CustomFieldDefinitionResponse:
    """Erstellt eine neue benutzerdefinierte Felddefinition.

    Nur fuer Administratoren. Der Feldname muss innerhalb des Mandanten
    und Dokumenttyps eindeutig sein.
    """
    service = _get_service()
    try:
        definition = await service.create_definition(
            db,
            name=data.name,
            label=data.label,
            description=data.description,
            field_type=data.field_type.value,
            document_type=data.document_type,
            required=data.required,
            default_value=data.default_value,
            validation_rules=(
                data.validation_rules.model_dump(exclude_none=True)
                if data.validation_rules
                else None
            ),
            dropdown_options=(
                [opt.model_dump() for opt in data.dropdown_options]
                if data.dropdown_options
                else None
            ),
            lookup_entity=data.lookup_entity,
            sort_order=data.sort_order,
            is_searchable=data.is_searchable,
            is_filterable=data.is_filterable,
            company_id=company.id,
            user_id=current_user.id,
        )
        await db.commit()
        return CustomFieldDefinitionResponse.model_validate(definition)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Feld"),
        )


@router.put(
    "/definitions/{field_id}",
    response_model=CustomFieldDefinitionResponse,
    summary="Felddefinition aktualisieren",
)
async def update_definition(
    field_id: UUID,
    data: CustomFieldDefinitionUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> CustomFieldDefinitionResponse:
    """Aktualisiert eine bestehende Felddefinition.

    Nur fuer Administratoren. Name und Typ koennen nicht
    geaendert werden.
    """
    service = _get_service()

    updates = data.model_dump(exclude_none=True)
    if "validation_rules" in updates and data.validation_rules is not None:
        updates["validation_rules"] = data.validation_rules.model_dump(
            exclude_none=True
        )
    if "dropdown_options" in updates and data.dropdown_options is not None:
        updates["dropdown_options"] = [
            opt.model_dump() for opt in data.dropdown_options
        ]

    definition = await service.update_definition(
        db, field_id=field_id, company_id=company.id, updates=updates
    )
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Felddefinition nicht gefunden.",
        )
    await db.commit()
    return CustomFieldDefinitionResponse.model_validate(definition)


@router.delete(
    "/definitions/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Felddefinition deaktivieren",
)
async def delete_definition(
    field_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> None:
    """Deaktiviert eine Felddefinition (Soft-Delete).

    Nur fuer Administratoren. Bestehende Werte auf Dokumenten
    bleiben erhalten.
    """
    service = _get_service()
    deleted = await service.delete_definition(
        db, field_id=field_id, company_id=company.id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Felddefinition nicht gefunden.",
        )
    await db.commit()


# =============================================================================
# Document Field Value Endpoints
# =============================================================================

@router.get(
    "/documents/{document_id}/values",
    response_model=CustomFieldValueResponse,
    summary="Feldwerte eines Dokuments lesen",
)
async def get_document_field_values(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> CustomFieldValueResponse:
    """Liest die benutzerdefinierten Feldwerte eines Dokuments."""
    service = _get_service()
    values = await service.get_field_values(
        db, document_id=document_id, company_id=company.id
    )
    return CustomFieldValueResponse(document_id=document_id, values=values)


@router.put(
    "/documents/{document_id}/values",
    response_model=CustomFieldValueResponse,
    summary="Feldwerte auf Dokument setzen",
)
async def set_document_field_values(
    document_id: UUID,
    data: CustomFieldValueSet,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> CustomFieldValueResponse:
    """Setzt benutzerdefinierte Feldwerte auf einem Dokument.

    Bestehende Werte die nicht im Request enthalten sind bleiben erhalten.
    Ein Wert von null entfernt das Feld.
    """
    service = _get_service()
    try:
        values = await service.set_field_values(
            db,
            document_id=document_id,
            company_id=company.id,
            values=data.values,
        )
        await db.commit()
        return CustomFieldValueResponse(document_id=document_id, values=values)
    except CustomFieldValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validierungsfehler: {e.message}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Feld"),
        )

"""
API Router für Template Engine.

Endpoints für PDF/DOCX/HTML-Generierung aus Templates.
"""

from typing import List, Optional
from uuid import UUID

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.core.security_auth import build_content_disposition
from app.db.models import User
from app.services.templates.template_engine import (
    TemplateEngineService,
    TemplateInfo,
    TemplateVariable,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class RenderTemplateRequest(BaseModel):
    """Request für Template-Rendering."""

    data: JSONDict = Field(..., description="Template-Variablen")
    format: str = Field(
        "pdf",
        description="Ausgabeformat (pdf, docx, html)",
        pattern="^(pdf|docx|html)$",
    )


class TemplateInfoResponse(BaseModel):
    """Template-Informationen Response."""

    id: str
    name: str
    category: str
    description: str
    variables: List[str]
    formats: List[str]

    model_config = ConfigDict(from_attributes=True)


class TemplateVariableResponse(BaseModel):
    """Template-Variable Response."""

    name: str
    label: str
    type: str
    required: bool
    default: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("", response_model=List[TemplateInfoResponse])
async def list_templates(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TemplateInfoResponse]:
    """
    Listet verfügbare Templates auf.

    Args:
        category: Optional filter nach Kategorie (rechnung, angebot, mahnung, etc.)
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        Liste von Template-Informationen
    """
    logger.info(
        "list_templates_requested",
        user_id=str(current_user.id),
        category=category,
    )

    try:
        service = TemplateEngineService()
        templates = await service.list_templates(category=category, db=db)

        return [
            TemplateInfoResponse(
                id=t.id,
                name=t.name,
                category=t.category,
                description=t.description,
                variables=t.variables,
                formats=t.formats,
            )
            for t in templates
        ]

    except Exception as e:
        logger.error("list_templates_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Template-Engine"),
        )


@router.get("/{template_id}", response_model=TemplateInfoResponse)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateInfoResponse:
    """
    Gibt Template-Details zurück.

    Args:
        template_id: Template-ID
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        Template-Informationen

    Raises:
        HTTPException 404: Template nicht gefunden
    """
    logger.info(
        "get_template_requested",
        user_id=str(current_user.id),
        template_id=template_id,
    )

    try:
        service = TemplateEngineService()
        templates = await service.list_templates(db=db)

        template = next((t for t in templates if t.id == template_id), None)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{template_id}' nicht gefunden",
            )

        return TemplateInfoResponse(
            id=template.id,
            name=template.name,
            category=template.category,
            description=template.description,
            variables=template.variables,
            formats=template.formats,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_template_failed", template_id=template_id, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Template-Engine"),
        )


@router.get("/{template_id}/variables", response_model=List[TemplateVariableResponse])
async def get_template_variables(
    template_id: str,
    current_user: User = Depends(get_current_user),
) -> List[TemplateVariableResponse]:
    """
    Gibt erforderliche Variablen für Template zurück.

    Args:
        template_id: Template-ID
        current_user: Aktueller Benutzer

    Returns:
        Liste von Template-Variablen mit Metadaten

    Raises:
        HTTPException 404: Template nicht gefunden
    """
    logger.info(
        "get_template_variables_requested",
        user_id=str(current_user.id),
        template_id=template_id,
    )

    try:
        service = TemplateEngineService()
        variables = await service.get_template_variables(template_id)

        return [
            TemplateVariableResponse(
                name=v.name,
                label=v.label,
                type=v.type,
                required=v.required,
                default=v.default,
            )
            for v in variables
        ]

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Template-Engine"),
        )
    except Exception as e:
        logger.error(
            "get_template_variables_failed",
            template_id=template_id,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Template-Engine"),
        )


@router.post("/{template_id}/render")
async def render_template(
    template_id: str,
    request: RenderTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Rendert Template und gibt Dokument zurück.

    Args:
        template_id: Template-ID
        request: Render-Request mit Daten und Format
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        StreamingResponse mit generiertem Dokument

    Raises:
        HTTPException 404: Template nicht gefunden
        HTTPException 400: Fehlende Variablen oder ungültiges Format
    """
    logger.info(
        "render_template_requested",
        user_id=str(current_user.id),
        template_id=template_id,
        format=request.format,
    )

    try:
        service = TemplateEngineService()
        rendered = await service.render_template(
            template_id=template_id,
            data=request.data,
            output_format=request.format,
            db=db,
        )

        # StreamingResponse zurückgeben
        import io

        return StreamingResponse(
            io.BytesIO(rendered.content),
            media_type=rendered.mime_type,
            headers={
                "Content-Disposition": build_content_disposition(rendered.filename, "attachment")
            },
        )

    except ValueError as e:
        # Template nicht gefunden oder Validierungsfehler
        error_msg = safe_error_detail(e, "Template-Engine")
        if "nicht gefunden" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )
    except Exception as e:
        logger.error(
            "render_template_failed",
            template_id=template_id,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Template-Engine"),
        )

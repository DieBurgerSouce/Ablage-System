# -*- coding: utf-8 -*-
"""Dokument-Versionsvergleich API Router.

Endpoints für Side-by-Side Dokumentvergleiche zwischen Versionen.
"""
from __future__ import annotations

from typing import List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_current_user
from app.db.session import get_async_session
from app.services.document_comparison_service import get_document_comparison_service
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/document-comparison", tags=["Dokumentvergleich"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class VersionInfo(BaseModel):
    """Schema für Version-Informationen."""
    id: str
    version_number: int
    change_type: str
    change_summary: Optional[str]
    created_at: str
    created_by_id: Optional[str]
    is_current: bool
    file_size: Optional[int]
    file_hash: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class CompareVersionsRequest(BaseModel):
    """Schema für Versionsvergleich-Anfrage."""
    version_a_id: UUID = Field(..., description="UUID der ersten Version")
    version_b_id: UUID = Field(..., description="UUID der zweiten Version")


class DiffBlockResponse(BaseModel):
    """Schema für einen Diff-Block."""
    type: str
    text_a: str
    text_b: str
    line_start_a: int
    line_end_a: int
    line_start_b: int
    line_end_b: int


class ComparisonResultResponse(BaseModel):
    """Schema für Vergleichsergebnis."""
    document_id: str
    version_a_id: str
    version_a_number: int
    version_a_created_at: str
    version_b_id: str
    version_b_number: int
    version_b_created_at: str
    similarity_ratio: float
    total_additions: int
    total_deletions: int
    total_changes: int
    text_differences: List[JSONDict]


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/{document_id}/versions", response_model=List[VersionInfo])
async def list_versions(
    document_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> List[VersionInfo]:
    """Listet alle verfügbaren Versionen eines Dokuments für Vergleich auf."""
    try:
        service = await get_document_comparison_service(db)
        versions = await service.list_document_versions(
            document_id=document_id,
            user_id=current_user["id"]
        )

        logger.info(
            "Versionen abgerufen",
            document_id=str(document_id),
            user_id=str(current_user["id"]),
            version_count=len(versions)
        )

        return [VersionInfo(**v) for v in versions]

    except ValueError as e:
        error_msg = str(e)
        if "nicht gefunden" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument nicht gefunden"
            )
        elif "Berechtigung" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für dieses Dokument"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    except Exception as e:
        logger.error("Fehler beim Abrufen der Versionen", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Versionsabfrage")
        )


@router.post("/{document_id}/compare")
async def compare_versions(
    document_id: UUID,
    request: CompareVersionsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> JSONDict:
    """Vergleicht zwei spezifische Versionen eines Dokuments."""
    try:
        service = await get_document_comparison_service(db)
        result = await service.compare_document_versions(
            document_id=document_id,
            version_a_id=request.version_a_id,
            version_b_id=request.version_b_id,
            user_id=current_user["id"]
        )

        logger.info(
            "Versionsvergleich abgeschlossen",
            document_id=str(document_id),
            user_id=str(current_user["id"]),
            similarity=result.overall_similarity
        )

        return {
            "document_id": str(document_id),
            "version_a_id": str(request.version_a_id),
            "version_b_id": str(request.version_b_id),
            "similarity_ratio": result.overall_similarity,
            "total_additions": result.additions,
            "total_deletions": result.removals,
            "total_changes": result.total_changes,
            "text_differences": [
                {
                    "type": d.diff_type.value,
                    "line_number": d.line_number,
                    "old_text": d.old_text,
                    "new_text": d.new_text
                }
                for d in result.text_differences
            ]
        }

    except ValueError as e:
        error_msg = str(e)
        if "nicht gefunden" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        elif "Berechtigung" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für dieses Dokument"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    except Exception as e:
        logger.error("Fehler beim Versionsvergleich", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Versionsvergleich")
        )


@router.get("/{document_id}/diff-original")
async def compare_with_original(
    document_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> JSONDict:
    """Vergleicht die aktuelle Version mit der Originalversion."""
    try:
        service = await get_document_comparison_service(db)
        result = await service.compare_with_original_version(
            document_id=document_id,
            user_id=current_user["id"]
        )

        logger.info(
            "Vergleich mit Original abgeschlossen",
            document_id=str(document_id),
            user_id=str(current_user["id"]),
            similarity=result.overall_similarity
        )

        return {
            "document_id": str(document_id),
            "version_a_id": str(result.document_1_id),
            "version_b_id": str(result.document_2_id),
            "similarity_ratio": result.overall_similarity,
            "total_additions": result.additions,
            "total_deletions": result.removals,
            "total_changes": result.total_changes,
            "text_differences": [
                {
                    "type": d.diff_type.value,
                    "line_number": d.line_number,
                    "old_text": d.old_text,
                    "new_text": d.new_text
                }
                for d in result.text_differences
            ]
        }

    except ValueError as e:
        error_msg = str(e)
        if "nicht gefunden" in error_msg or "keine Versionen" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        elif "Berechtigung" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für dieses Dokument"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    except Exception as e:
        logger.error("Fehler beim Vergleich mit Original", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Versionsvergleich")
        )

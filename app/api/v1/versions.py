"""OCR Version Management API Endpoints.

Provides REST API for:
- Version listing and details
- Version comparison with diff
- Version rollback
"""

import structlog
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_current_user, get_db, verify_document_ownership
from app.services.version_service import get_version_service, VersionService
from app.core.safe_errors import safe_error_log
from app.db.schemas import (

    OCRVersionResponse,
    OCRVersionListResponse,
    OCRVersionCompareRequest,
    OCRVersionCompareResponse,
    OCRVersionRollbackRequest,
    OCRVersionRollbackResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents/{document_id}/versions", tags=["versions"])


def get_version_service_dep() -> VersionService:
    """Dependency for version service."""
    return get_version_service()


@router.get(
    "/",
    response_model=OCRVersionListResponse,
    summary="Liste aller OCR-Versionen",
    description="Gibt alle OCR-Versionen eines Dokuments zuruck."
)
async def list_document_versions(
    document_id: UUID,
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    version_service: VersionService = Depends(get_version_service_dep)
) -> OCRVersionListResponse:
    """Liste aller OCR-Versionen eines Dokuments.

    Args:
        document_id: Dokument-ID
        page: Seitennummer (1-basiert)
        per_page: Eintraege pro Seite (1-100)
        current_user: Aktueller Benutzer
        db: Datenbank-Session
        version_service: Version-Service

    Returns:
        Liste der Versionen mit Metadaten
    """
    # Verify ownership
    await verify_document_ownership(document_id, current_user, db)

    try:
        result = await version_service.list_versions(
            db=db,
            document_id=document_id,
            limit=per_page,
            offset=(page - 1) * per_page
        )

        logger.info(
            "versions_listed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            count=result.total_versions
        )

        return result

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("versions_validation_error", **safe_error_log(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ressource nicht gefunden.")
    except Exception as e:
        logger.error("list_versions_error", **safe_error_log(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Versionen"
        )


@router.get(
    "/current",
    response_model=OCRVersionResponse,
    summary="Aktuelle Version",
    description="Gibt die aktuell aktive OCR-Version zuruck."
)
async def get_current_version(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    version_service: VersionService = Depends(get_version_service_dep)
) -> OCRVersionResponse:
    """Aktuelle (aktive) Version des Dokuments abrufen.

    Args:
        document_id: Dokument-ID
        current_user: Aktueller Benutzer
        db: Datenbank-Session
        version_service: Version-Service

    Returns:
        Aktuelle Versionsdaten
    """
    await verify_document_ownership(document_id, current_user, db)

    version = await version_service.get_current_version(db, document_id)

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine aktuelle Version gefunden"
        )

    return OCRVersionResponse.model_validate(version)


@router.get(
    "/{version_number}",
    response_model=OCRVersionResponse,
    summary="Version-Details",
    description="Gibt Details einer spezifischen Version zuruck."
)
async def get_version_details(
    document_id: UUID,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    version_service: VersionService = Depends(get_version_service_dep)
) -> OCRVersionResponse:
    """Details einer spezifischen Version abrufen.

    Args:
        document_id: Dokument-ID
        version_number: Versionsnummer
        current_user: Aktueller Benutzer
        db: Datenbank-Session
        version_service: Version-Service

    Returns:
        Vollstandige Versionsdaten
    """
    await verify_document_ownership(document_id, current_user, db)

    version = await version_service.get_version(db, document_id, version_number)

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_number} nicht gefunden"
        )

    return OCRVersionResponse.model_validate(version)


@router.post(
    "/compare",
    response_model=OCRVersionCompareResponse,
    summary="Versionen vergleichen",
    description="Vergleicht zwei Versionen eines Dokuments und zeigt Unterschiede."
)
async def compare_versions(
    document_id: UUID,
    request: OCRVersionCompareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    version_service: VersionService = Depends(get_version_service_dep)
) -> OCRVersionCompareResponse:
    """Vergleiche zwei Versionen eines Dokuments.

    Generiert sowohl Side-by-Side HTML-Diff als auch Unified Diff.

    Args:
        document_id: Dokument-ID
        request: Versionen zum Vergleichen (version_a, version_b)
        current_user: Aktueller Benutzer
        db: Datenbank-Session
        version_service: Version-Service

    Returns:
        Vergleichsergebnis mit Diff
    """
    await verify_document_ownership(document_id, current_user, db)

    try:
        result = await version_service.compare_versions(
            db=db,
            document_id=document_id,
            version_a=request.version_a,
            version_b=request.version_b
        )

        logger.info(
            "versions_compared",
            document_id=str(document_id),
            user_id=str(current_user.id),
            version_a=request.version_a,
            version_b=request.version_b
        )

        return result

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("versions_validation_error", **safe_error_log(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ressource nicht gefunden.")
    except Exception as e:
        logger.error("compare_versions_error", **safe_error_log(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Vergleichen der Versionen"
        )


@router.post(
    "/rollback",
    response_model=OCRVersionRollbackResponse,
    summary="Zu Version zuruckkehren",
    description="Erstellt eine neue Version mit dem Inhalt einer fruheren Version."
)
async def rollback_to_version(
    document_id: UUID,
    request: OCRVersionRollbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    version_service: VersionService = Depends(get_version_service_dep)
) -> OCRVersionRollbackResponse:
    """Rollback zu einer fruheren Version.

    Erstellt eine neue Version mit dem Inhalt der Zielversion.
    Die Original-Versionen bleiben erhalten (vollstandiger Audit-Trail).

    Args:
        document_id: Dokument-ID
        request: Zielversion und optionale Notiz
        current_user: Aktueller Benutzer
        db: Datenbank-Session
        version_service: Version-Service

    Returns:
        Rollback-Ergebnis mit neuer Versionsnummer
    """
    await verify_document_ownership(document_id, current_user, db)

    try:
        result = await version_service.rollback_to_version(
            db=db,
            document_id=document_id,
            target_version=request.target_version,
            user_id=current_user.id,
            rollback_note=request.rollback_note
        )

        logger.info(
            "version_rollback",
            document_id=str(document_id),
            user_id=str(current_user.id),
            target_version=request.target_version,
            new_version=result.new_version_number
        )

        return result

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("versions_validation_error", **safe_error_log(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ressource nicht gefunden.")
    except Exception as e:
        logger.error("rollback_error", **safe_error_log(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Rollback"
        )

"""
Admin-API fuer Mandanten-Verwaltung.

Nur fuer System-Administratoren zugaenglich.
"""

import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Optional
from uuid import UUID

from app.api.dependencies import get_current_superuser, get_db
from app.db.models import Document, User, UserCompany
from app.services.tenant import TenantConfigService, get_tenant_config_service
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# --- Quota Aggregation Helpers ---


async def _get_document_count(db: AsyncSession, company_id: UUID) -> int:
    """Zaehlt Dokumente des Mandanten im aktuellen Monat."""
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return await db.scalar(
        select(func.count(Document.id)).where(
            Document.company_id == company_id,
            Document.created_at >= month_start,
            Document.deleted_at.is_(None),
        )
    ) or 0


async def _get_storage_usage(db: AsyncSession, company_id: UUID) -> float:
    """Berechnet genutzten Speicherplatz in GB."""
    storage_bytes = await db.scalar(
        select(func.coalesce(func.sum(Document.file_size), 0)).where(
            Document.company_id == company_id,
            Document.deleted_at.is_(None),
        )
    ) or 0
    return round(storage_bytes / (1024 ** 3), 2)


async def _get_user_count(db: AsyncSession, company_id: UUID) -> int:
    """Zaehlt aktive Benutzer des Mandanten."""
    return await db.scalar(
        select(func.count(UserCompany.id)).where(
            UserCompany.company_id == company_id,
        )
    ) or 0


_QUOTA_AGGREGATORS = {
    "max_documents_per_month": _get_document_count,
    "max_storage_gb": _get_storage_usage,
    "max_users": _get_user_count,
}


router = APIRouter(prefix="/admin/tenants", tags=["tenant-admin"])


# --- Pydantic Models ---


class TenantConfigResponse(BaseModel):
    """Response-Schema fuer Mandanten-Konfiguration."""

    id: UUID
    company_id: UUID
    features: Optional[Dict[str, object]] = Field(default_factory=dict)
    quotas: Optional[Dict[str, object]] = Field(default_factory=dict)
    branding: Optional[Dict[str, object]] = Field(default_factory=dict)
    is_active: bool

    class Config:
        """Pydantic Config."""

        from_attributes = True


class TenantConfigUpdate(BaseModel):
    """Request-Schema fuer Konfiguration-Update."""

    features: Optional[Dict[str, object]] = None
    quotas: Optional[Dict[str, object]] = None
    branding: Optional[Dict[str, object]] = None


class TenantFeaturesResponse(BaseModel):
    """Response-Schema fuer Feature-Flags."""

    company_id: UUID
    features: Dict[str, bool]


class TenantUsageResponse(BaseModel):
    """Response-Schema fuer Quota-Nutzung."""

    company_id: UUID
    quotas: Dict[str, object]
    usage_summary: Dict[str, Dict[str, object]]


# --- API Endpoints ---


@router.get(
    "/{company_id}/config",
    response_model=TenantConfigResponse,
    summary="Mandanten-Konfiguration abrufen",
    description="Holt die Konfiguration eines Mandanten (nur fuer Superuser)",
)
async def get_tenant_config(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> TenantConfigResponse:
    """
    Holt die Konfiguration eines Mandanten.

    Args:
        company_id: UUID des Mandanten
        db: Database Session
        current_user: Aktueller Superuser

    Returns:
        Mandanten-Konfiguration

    Raises:
        HTTPException: 404 wenn nicht gefunden
    """
    try:
        service = get_tenant_config_service(db)
        config = await service.get_tenant_config(company_id)

        if config is None:
            logger.warning(
                "tenant_config_not_found",
                company_id=str(company_id),
                admin_user_id=str(current_user.id),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mandanten-Konfiguration nicht gefunden",
            )

        logger.info(
            "tenant_config_retrieved",
            company_id=str(company_id),
            admin_user_id=str(current_user.id),
        )

        return TenantConfigResponse.model_validate(config)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_tenant_config_failed",
            **safe_error_log(e),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Mandanten-Konfiguration",
        )


@router.patch(
    "/{company_id}/config",
    response_model=TenantConfigResponse,
    summary="Mandanten-Konfiguration aktualisieren",
    description="Aktualisiert Features, Quotas oder Branding eines Mandanten (nur fuer Superuser)",
)
async def update_tenant_config(
    company_id: UUID,
    update: TenantConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> TenantConfigResponse:
    """
    Aktualisiert die Konfiguration eines Mandanten.

    Args:
        company_id: UUID des Mandanten
        update: Konfiguration-Update
        db: Database Session
        current_user: Aktueller Superuser

    Returns:
        Aktualisierte Mandanten-Konfiguration

    Raises:
        HTTPException: Bei Fehlern
    """
    try:
        service = get_tenant_config_service(db)
        config = await service.create_or_update_config(
            company_id=company_id,
            features=update.features,
            quotas=update.quotas,
            branding=update.branding,
        )

        logger.info(
            "tenant_config_updated",
            company_id=str(company_id),
            admin_user_id=str(current_user.id),
            features_updated=update.features is not None,
            quotas_updated=update.quotas is not None,
            branding_updated=update.branding is not None,
        )

        return TenantConfigResponse.model_validate(config)

    except ValueError as e:
        logger.error(
            "invalid_tenant_config_update",
            **safe_error_log(e),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "update_tenant_config_failed",
            **safe_error_log(e),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der Mandanten-Konfiguration",
        )


@router.get(
    "/{company_id}/features",
    response_model=TenantFeaturesResponse,
    summary="Feature-Flags abrufen",
    description="Holt die Feature-Flags eines Mandanten (nur fuer Superuser)",
)
async def get_tenant_features(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> TenantFeaturesResponse:
    """
    Holt die Feature-Flags eines Mandanten.

    Args:
        company_id: UUID des Mandanten
        db: Database Session
        current_user: Aktueller Superuser

    Returns:
        Feature-Flags des Mandanten
    """
    try:
        service = get_tenant_config_service(db)
        features = await service.get_tenant_features(company_id)

        logger.info(
            "tenant_features_retrieved",
            company_id=str(company_id),
            admin_user_id=str(current_user.id),
            feature_count=len(features),
        )

        return TenantFeaturesResponse(
            company_id=company_id,
            features=features,
        )

    except Exception as e:
        logger.error(
            "get_tenant_features_failed",
            **safe_error_log(e),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Feature-Flags",
        )


@router.get(
    "/{company_id}/usage",
    response_model=TenantUsageResponse,
    summary="Quota-Nutzung abrufen",
    description="Holt eine Uebersicht der Quota-Nutzung eines Mandanten (nur fuer Superuser)",
)
async def get_tenant_usage(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> TenantUsageResponse:
    """
    Holt die Quota-Nutzung eines Mandanten.

    Args:
        company_id: UUID des Mandanten
        db: Database Session
        current_user: Aktueller Superuser

    Returns:
        Quota-Nutzung des Mandanten
    """
    try:
        service = get_tenant_config_service(db)
        config = await service.get_tenant_config(company_id)

        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mandanten-Konfiguration nicht gefunden",
            )

        quotas = config.quotas or {}

        usage_summary: Dict[str, Dict[str, object]] = {}

        for resource, limit in quotas.items():
            aggregator = _QUOTA_AGGREGATORS.get(resource)
            if aggregator:
                usage = await aggregator(db, company_id)
                int_limit = int(limit) if isinstance(limit, (int, float)) else 0
                usage_summary[resource] = {
                    "limit": int_limit,
                    "usage": usage,
                    "remaining": max(0, int_limit - usage) if int_limit > 0 else -1,
                    "within_quota": usage <= int_limit if int_limit > 0 else True,
                }
            else:
                usage_summary[resource] = {
                    "limit": limit,
                    "usage": 0,
                    "remaining": limit if isinstance(limit, int) else -1,
                    "within_quota": True,
                }

        logger.info(
            "tenant_usage_retrieved",
            company_id=str(company_id),
            admin_user_id=str(current_user.id),
        )

        return TenantUsageResponse(
            company_id=company_id,
            quotas=quotas,
            usage_summary=usage_summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_tenant_usage_failed",
            **safe_error_log(e),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Quota-Nutzung",
        )


@router.post(
    "/{company_id}/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mandant deaktivieren",
    description="Deaktiviert einen Mandanten (nur fuer Superuser)",
)
async def deactivate_tenant(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> None:
    """
    Deaktiviert einen Mandanten.

    Args:
        company_id: UUID des Mandanten
        db: Database Session
        current_user: Aktueller Superuser

    Raises:
        HTTPException: Bei Fehlern
    """
    try:
        service = get_tenant_config_service(db)
        success = await service.deactivate_tenant(company_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Fehler beim Deaktivieren des Mandanten",
            )

        logger.warning(
            "tenant_deactivated_via_api",
            company_id=str(company_id),
            admin_user_id=str(current_user.id),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "deactivate_tenant_failed",
            **safe_error_log(e),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Deaktivieren des Mandanten",
        )


@router.post(
    "/{company_id}/activate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mandant aktivieren",
    description="Aktiviert einen deaktivierten Mandanten (nur fuer Superuser)",
)
async def activate_tenant(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> None:
    """
    Aktiviert einen deaktivierten Mandanten.

    Args:
        company_id: UUID des Mandanten
        db: Database Session
        current_user: Aktueller Superuser

    Raises:
        HTTPException: Bei Fehlern
    """
    try:
        service = get_tenant_config_service(db)
        success = await service.activate_tenant(company_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Fehler beim Aktivieren des Mandanten",
            )

        logger.info(
            "tenant_activated_via_api",
            company_id=str(company_id),
            admin_user_id=str(current_user.id),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "activate_tenant_failed",
            **safe_error_log(e),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktivieren des Mandanten",
        )

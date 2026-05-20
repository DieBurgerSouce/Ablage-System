# -*- coding: utf-8 -*-
"""
Admin-API für Cache-Verwaltung.

Nur für System-Administratoren zugaenglich.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from starlette.requests import Request
from typing import Dict, Optional

from app.api.dependencies import get_current_superuser, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User
from app.core.cache import (
    get_cache_metrics,
    invalidate_cache,
    invalidate_all_caches,
    invalidate_search_cache,
    invalidate_document_cache,
    invalidate_user_cache,
    get_l1_cache,
)
from app.core.safe_errors import safe_error_log
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/cache", tags=["cache-admin"])


class CacheMetricsResponse(BaseModel):
    """Response für Cache-Metriken."""

    l1: Dict[str, object] = Field(default_factory=dict)
    l2: Dict[str, object] = Field(default_factory=dict)


class CacheInvalidateRequest(BaseModel):
    """Request für Cache-Invalidierung."""

    pattern: Optional[str] = Field(None, description="Redis-Key-Pattern (z.B. 'cache:doc:*')")
    scope: Optional[str] = Field(None, description="Vordefinierter Scope: 'all', 'search', 'documents', 'users'")
    document_id: Optional[str] = Field(None, description="Spezifische Dokument-ID")
    user_id: Optional[str] = Field(None, description="Spezifische User-ID")


class CacheInvalidateResponse(BaseModel):
    """Response für Cache-Invalidierung."""

    deleted_keys: int = 0
    scope: str = ""
    details: Dict[str, object] = Field(default_factory=dict)


class CacheWarmResponse(BaseModel):
    """Response für Cache-Warming."""

    warmed_entries: Dict[str, int] = Field(default_factory=dict)


@router.get(
    "/metrics",
    response_model=CacheMetricsResponse,
    summary="Cache-Metriken abrufen",
    description="Holt L1/L2 Cache-Statistiken (nur für Superuser)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_metrics(
    request: Request,
    current_user: User = Depends(get_current_superuser),
) -> CacheMetricsResponse:
    """
    Holt die Cache-Metriken für L1 und L2.

    Args:
        current_user: Aktueller Superuser

    Returns:
        Cache-Metriken für beide Tiers
    """
    try:
        metrics = await get_cache_metrics()
        logger.info("cache_metrics_retrieved", admin_user_id=str(current_user.id))
        return CacheMetricsResponse(**metrics)
    except Exception as e:
        logger.error("cache_metrics_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Cache-Metriken",
        )


@router.post(
    "/invalidate",
    response_model=CacheInvalidateResponse,
    summary="Cache invalidieren",
    description="Invalidiert Cache-Einträge nach Pattern oder Scope (nur für Superuser)",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def invalidate(
    request: Request,
    body: CacheInvalidateRequest,
    current_user: User = Depends(get_current_superuser),
) -> CacheInvalidateResponse:
    """
    Invalidiert Cache-Einträge nach Pattern, Scope oder ID.

    Args:
        request: HTTP Request (für Rate-Limiting)
        body: Invalidierungs-Parameter
        current_user: Aktueller Superuser

    Returns:
        Anzahl gelöschter Keys und Scope-Info
    """
    try:
        if body.document_id:
            result = await invalidate_document_cache(body.document_id, cascade=True)
            logger.info(
                "cache_invalidated_by_admin",
                admin_user_id=str(current_user.id),
                scope=f"document:{body.document_id}",
                deleted=result.get("total", 0),
            )
            return CacheInvalidateResponse(
                deleted_keys=result.get("total", 0),
                scope=f"document:{body.document_id}",
                details=result,
            )

        if body.user_id:
            result = await invalidate_user_cache(body.user_id, cascade=True)
            logger.info(
                "cache_invalidated_by_admin",
                admin_user_id=str(current_user.id),
                scope=f"user:{body.user_id}",
                deleted=result.get("total", 0),
            )
            return CacheInvalidateResponse(
                deleted_keys=result.get("total", 0),
                scope=f"user:{body.user_id}",
                details=result,
            )

        if body.scope == "all":
            result = await invalidate_all_caches()
            logger.warning(
                "cache_all_invalidated_by_admin",
                admin_user_id=str(current_user.id),
                deleted=result.get("total", 0),
            )
            return CacheInvalidateResponse(
                deleted_keys=result.get("total", 0),
                scope="all",
                details=result,
            )

        if body.scope == "search":
            deleted = await invalidate_search_cache()
            logger.info(
                "cache_invalidated_by_admin",
                admin_user_id=str(current_user.id),
                scope="search",
                deleted=deleted,
            )
            return CacheInvalidateResponse(deleted_keys=deleted, scope="search")

        if body.pattern:
            deleted = await invalidate_cache(body.pattern)
            logger.info(
                "cache_invalidated_by_admin",
                admin_user_id=str(current_user.id),
                scope=f"pattern:{body.pattern}",
                deleted=deleted,
            )
            return CacheInvalidateResponse(deleted_keys=deleted, scope=f"pattern:{body.pattern}")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bitte pattern, scope, document_id oder user_id angeben",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("cache_invalidation_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Cache-Invalidierung",
        )


@router.post(
    "/warm",
    response_model=CacheWarmResponse,
    summary="Cache aufwaermen",
    description="Laedt häufig genutzte Daten in den Cache (nur für Superuser)",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def warm_cache(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> CacheWarmResponse:
    """
    Startet Cache-Warming für häufig genutzte Daten.

    Args:
        db: Database Session
        current_user: Aktueller Superuser

    Returns:
        Anzahl der aufgewaermten Einträge pro Kategorie
    """
    try:
        from app.services.cache.cache_warming_service import CacheWarmingService

        warming_service = CacheWarmingService(db)
        results = await warming_service.warm_caches()
        logger.info("cache_warm_triggered", admin_user_id=str(current_user.id), **results)
        return CacheWarmResponse(warmed_entries=results)
    except Exception as e:
        logger.error("cache_warm_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Cache-Warming",
        )

"""
API-Endpunkte für Feature-Flag Verwaltung.

Admin-Endpunkte (nur Superuser):
- CRUD-Operationen für Feature-Flags
- Kill-Switch-Funktion

User-Endpunkte (authentifizierte Benutzer):
- Feature-Flag Evaluation
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from typing import Dict, List, Optional
from uuid import UUID
from datetime import datetime

from app.api.dependencies import get_current_superuser, get_current_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User
from app.services.feature_flag_service import get_feature_flag_service
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

# ==================== Admin Router ====================
admin_router = APIRouter(
    prefix="/admin/feature-flags",
    tags=["feature-flags-admin"],
)

# ==================== User Router ====================
user_router = APIRouter(
    prefix="/feature-flags",
    tags=["feature-flags"],
)


# --- Pydantic Models ---


class FeatureFlagResponse(BaseModel):
    """Response-Schema für Feature-Flag."""

    id: UUID
    key: str
    name: str
    description: Optional[str] = None
    enabled: bool
    rollout_percentage: int
    target_tiers: List[str] = Field(default_factory=list)
    target_users: List[str] = Field(default_factory=list)
    variants: Dict[str, int] = Field(default_factory=dict)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    config: Dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FeatureFlagCreate(BaseModel):
    """Request-Schema für Feature-Flag Erstellung."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Eindeutiger Schluessel (z.B. 'new_ocr_pipeline')",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Anzeigename des Feature-Flags",
    )
    description: Optional[str] = Field(
        None,
        description="Beschreibung des Feature-Flags",
    )
    enabled: bool = Field(
        False,
        description="Ob das Feature-Flag aktiviert ist",
    )
    rollout_percentage: int = Field(
        0,
        ge=0,
        le=100,
        description="Rollout-Prozentsatz (0-100)",
    )
    target_tiers: Optional[List[str]] = Field(
        None,
        description="Ziel-Tiers (z.B. ['premium', 'enterprise'])",
    )
    target_users: Optional[List[str]] = Field(
        None,
        description="Ziel-Benutzer-IDs",
    )
    variants: Optional[Dict[str, int]] = Field(
        None,
        description="A/B Test Varianten (z.B. {'control': 50, 'variant_a': 50})",
    )
    starts_at: Optional[datetime] = Field(
        None,
        description="Startdatum (optional)",
    )
    ends_at: Optional[datetime] = Field(
        None,
        description="Enddatum (optional)",
    )
    config: Optional[Dict[str, object]] = Field(
        None,
        description="Zusätzliche Konfiguration",
    )


class FeatureFlagUpdate(BaseModel):
    """Request-Schema für Feature-Flag Aktualisierung."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    enabled: Optional[bool] = None
    rollout_percentage: Optional[int] = Field(None, ge=0, le=100)
    target_tiers: Optional[List[str]] = None
    target_users: Optional[List[str]] = None
    variants: Optional[Dict[str, int]] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    config: Optional[Dict[str, object]] = None


class FeatureFlagEvalResponse(BaseModel):
    """Response-Schema für Feature-Flag Evaluation."""

    flag_key: str
    enabled: bool
    variant: Optional[str] = None
    reason: str


class FeatureFlagListResponse(BaseModel):
    """Response-Schema für Feature-Flag Liste."""

    flags: List[FeatureFlagResponse]
    total: int


# ==================== Admin Endpoints ====================


@admin_router.get(
    "/",
    response_model=FeatureFlagListResponse,
    summary="Alle Feature-Flags auflisten",
    description="Listet alle Feature-Flags auf (nur für Superuser)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def list_feature_flags(
    request: Request,
    enabled_only: bool = Query(False, description="Nur aktivierte Flags"),
    limit: int = Query(100, ge=1, le=500, description="Maximale Anzahl"),
    offset: int = Query(0, ge=0, description="Offset für Paginierung"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> FeatureFlagListResponse:
    """Alle Feature-Flags auflisten."""
    try:
        service = get_feature_flag_service(db)
        flags = await service.get_all(
            enabled_only=enabled_only,
            limit=limit,
            offset=offset,
        )
        total = await service.count(enabled_only=enabled_only)

        logger.info(
            "feature_flags_listed",
            admin_user_id=str(current_user.id),
            count=len(flags),
            total=total,
        )

        return FeatureFlagListResponse(
            flags=[FeatureFlagResponse.model_validate(f) for f in flags],
            total=total,
        )

    except Exception as e:
        logger.error(
            "list_feature_flags_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Auflisten der Feature-Flags",
        )


@admin_router.post(
    "/",
    response_model=FeatureFlagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Feature-Flag erstellen",
    description="Erstellt ein neues Feature-Flag (nur für Superuser)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def create_feature_flag(
    request: Request,
    data: FeatureFlagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> FeatureFlagResponse:
    """Neues Feature-Flag erstellen."""
    try:
        service = get_feature_flag_service(db)

        # Prüfen ob Key bereits existiert
        existing = await service.get_by_key(data.key)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Feature-Flag mit Key '{data.key}' existiert bereits",
            )

        flag = await service.create(
            key=data.key,
            name=data.name,
            description=data.description,
            enabled=data.enabled,
            rollout_percentage=data.rollout_percentage,
            target_tiers=data.target_tiers,
            target_users=data.target_users,
            variants=data.variants,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            config=data.config,
            created_by_id=current_user.id,
        )

        logger.info(
            "feature_flag_created_via_api",
            key=data.key,
            admin_user_id=str(current_user.id),
        )

        return FeatureFlagResponse.model_validate(flag)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(
            "create_feature_flag_validation_error",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Feature-Flag"),
        )
    except Exception as e:
        logger.error(
            "create_feature_flag_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen des Feature-Flags",
        )


@admin_router.get(
    "/{flag_id}",
    response_model=FeatureFlagResponse,
    summary="Feature-Flag abrufen",
    description="Holt ein Feature-Flag anhand der ID (nur für Superuser)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_feature_flag(
    request: Request,
    flag_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> FeatureFlagResponse:
    """Feature-Flag anhand der ID abrufen."""
    try:
        service = get_feature_flag_service(db)
        flag = await service.get_by_id(flag_id)

        if flag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feature-Flag nicht gefunden",
            )

        logger.info(
            "feature_flag_retrieved",
            flag_id=str(flag_id),
            admin_user_id=str(current_user.id),
        )

        return FeatureFlagResponse.model_validate(flag)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_feature_flag_failed",
            **safe_error_log(e),
            flag_id=str(flag_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen des Feature-Flags",
        )


@admin_router.patch(
    "/{flag_id}",
    response_model=FeatureFlagResponse,
    summary="Feature-Flag aktualisieren",
    description="Aktualisiert ein Feature-Flag (nur für Superuser)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def update_feature_flag(
    request: Request,
    flag_id: UUID,
    data: FeatureFlagUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> FeatureFlagResponse:
    """Feature-Flag aktualisieren."""
    try:
        service = get_feature_flag_service(db)

        # Nur gesetzte Felder als Updates übergeben
        updates: Dict[str, object] = {}
        for field_name, value in data.model_dump(exclude_unset=True).items():
            updates[field_name] = value

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Keine Aktualisierungen angegeben",
            )

        flag = await service.update_flag(
            flag_id=flag_id,
            updates=updates,
            updated_by_id=current_user.id,
        )

        if flag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feature-Flag nicht gefunden",
            )

        logger.info(
            "feature_flag_updated_via_api",
            flag_id=str(flag_id),
            admin_user_id=str(current_user.id),
            updated_fields=list(updates.keys()),
        )

        return FeatureFlagResponse.model_validate(flag)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(
            "update_feature_flag_validation_error",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Feature-Flag"),
        )
    except Exception as e:
        logger.error(
            "update_feature_flag_failed",
            **safe_error_log(e),
            flag_id=str(flag_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren des Feature-Flags",
        )


@admin_router.delete(
    "/{flag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Feature-Flag löschen",
    description="Löscht ein Feature-Flag (nur für Superuser)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def delete_feature_flag(
    request: Request,
    flag_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> None:
    """Feature-Flag löschen."""
    try:
        service = get_feature_flag_service(db)
        success = await service.delete_flag(flag_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feature-Flag nicht gefunden",
            )

        logger.warning(
            "feature_flag_deleted_via_api",
            flag_id=str(flag_id),
            admin_user_id=str(current_user.id),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "delete_feature_flag_failed",
            **safe_error_log(e),
            flag_id=str(flag_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Löschen des Feature-Flags",
        )


@admin_router.post(
    "/{key}/kill-switch",
    status_code=status.HTTP_200_OK,
    summary="Kill-Switch aktivieren",
    description="Deaktiviert ein Feature-Flag sofort (Kill-Switch, nur für Superuser)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def activate_kill_switch(
    request: Request,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> Dict[str, object]:
    """Kill-Switch für ein Feature-Flag aktivieren."""
    try:
        service = get_feature_flag_service(db)
        success = await service.kill_switch(key)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feature-Flag '{key}' nicht gefunden",
            )

        logger.warning(
            "kill_switch_activated_via_api",
            key=key,
            admin_user_id=str(current_user.id),
        )

        return {
            "key": key,
            "status": "deactivated",
            "message": f"Feature-Flag '{key}' wurde sofort deaktiviert",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "kill_switch_failed",
            **safe_error_log(e),
            key=key,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktivieren des Kill-Switch",
        )


# ==================== User Endpoints ====================


@user_router.get(
    "/evaluate/{key}",
    response_model=FeatureFlagEvalResponse,
    summary="Feature-Flag evaluieren",
    description="Evaluiert ein Feature-Flag für den aktuellen Benutzer",
)
@limiter.limit("100/minute", key_func=get_user_identifier)
async def evaluate_feature_flag(
    request: Request,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeatureFlagEvalResponse:
    """Feature-Flag für aktuellen Benutzer evaluieren."""
    try:
        service = get_feature_flag_service(db)
        user_tier = getattr(current_user, "tier", None)

        result = await service.evaluate(
            key=key,
            user_id=str(current_user.id),
            user_tier=user_tier,
        )

        return FeatureFlagEvalResponse(
            flag_key=str(result["flag_key"]),
            enabled=bool(result["enabled"]),
            variant=str(result["variant"]) if result.get("variant") else None,
            reason=str(result["reason"]),
        )

    except Exception as e:
        logger.error(
            "evaluate_feature_flag_failed",
            **safe_error_log(e),
            key=key,
        )
        # Fail-safe: Bei Fehlern immer disabled zurückgeben
        return FeatureFlagEvalResponse(
            flag_key=key,
            enabled=False,
            variant=None,
            reason="evaluation_error",
        )


@user_router.get(
    "/evaluate-all",
    summary="Alle Feature-Flags evaluieren",
    description="Evaluiert alle aktiven Feature-Flags für den aktuellen Benutzer",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def evaluate_all_feature_flags(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Dict[str, object]]:
    """Alle Feature-Flags für aktuellen Benutzer evaluieren."""
    try:
        service = get_feature_flag_service(db)
        user_tier = getattr(current_user, "tier", None)

        results = await service.evaluate_all(
            user_id=str(current_user.id),
            user_tier=user_tier,
        )

        return results

    except Exception as e:
        logger.error(
            "evaluate_all_feature_flags_failed",
            **safe_error_log(e),
        )
        # Fail-safe: Bei Fehlern leeres Dict zurückgeben
        return {}

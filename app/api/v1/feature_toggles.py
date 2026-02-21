# -*- coding: utf-8 -*-
"""
Admin API-Endpunkte für Feature-Toggle Verwaltung.

Alle Endpunkte sind ausschließlich für Superuser zugänglich.

Endpunkte:
    GET  /api/v1/admin/feature-toggles          - Alle Flags auflisten
    GET  /api/v1/admin/feature-toggles/{name}   - Detailansicht + Verlauf
    PATCH /api/v1/admin/feature-toggles/{name}  - Toggle / Rollout ändern
    POST /api/v1/admin/feature-toggles/{name}/user-override  - Per-User Override
    GET  /api/v1/admin/feature-toggles/{name}/history        - Änderungsverlauf
    GET  /api/v1/admin/feature-toggles/{name}/ab-results     - A/B Test Statistiken
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional
from uuid import UUID

from app.api.dependencies import get_current_superuser, get_db
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.feature_toggle_admin_service import (
    get_feature_toggle_admin_service,
    FeatureToggleAdminService,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/feature-toggles",
    tags=["Admin - Feature-Toggles"],
)


# =============================================================================
# Request / Response Schemas
# =============================================================================


class FeatureToggleHistoryEntry(BaseModel):
    """Einzelner Eintrag im Änderungsverlauf eines Feature-Flags."""

    id: str
    feature_flag_id: Optional[str] = None
    flag_name: str
    action: str
    old_value: Optional[Dict[str, object]] = None
    new_value: Optional[Dict[str, object]] = None
    changed_by_id: Optional[str] = None
    reason: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FeatureToggleSummary(BaseModel):
    """Zusammenfassung eines Feature-Flags."""

    id: str
    key: str
    name: str
    description: Optional[str] = None
    enabled: bool
    is_active: bool
    rollout_percentage: int
    target_tiers: List[str] = Field(default_factory=list)
    target_users: List[str] = Field(default_factory=list)
    has_ab_test: bool
    variants: Dict[str, int] = Field(default_factory=dict)
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    config: Dict[str, object] = Field(default_factory=dict)
    created_by_id: Optional[str] = None
    updated_by_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FeatureToggleDetail(FeatureToggleSummary):
    """Detailansicht eines Feature-Flags inkl. Änderungsverlauf."""

    history: List[FeatureToggleHistoryEntry] = Field(default_factory=list)


class FeatureToggleListResponse(BaseModel):
    """Paginierte Liste von Feature-Flags."""

    items: List[FeatureToggleSummary]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(from_attributes=True)


class FeatureTogglePatchRequest(BaseModel):
    """Request-Body für PATCH – entweder toggle oder rollout ändern."""

    enabled: Optional[bool] = Field(
        None,
        description="Neuer Aktivierungsstatus (true/false)",
    )
    rollout_percentage: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Neuer Rollout-Prozentsatz (0–100)",
    )
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Optionaler Begründungstext für den Audit-Trail",
    )

    model_config = ConfigDict(from_attributes=True)


class UserOverrideRequest(BaseModel):
    """Request-Body für Per-User Override."""

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="ID des Benutzers, für den der Override gesetzt wird",
    )
    enabled: bool = Field(
        ...,
        description="True = Benutzer explizit einschließen, False = entfernen",
    )

    model_config = ConfigDict(from_attributes=True)


class AbTestVariantStats(BaseModel):
    """Statistiken für eine einzelne A/B Test Variante."""

    count: int
    percentage_of_targets: float
    configured_weight: int

    model_config = ConfigDict(from_attributes=True)


class AbTestResultsResponse(BaseModel):
    """A/B Test Ergebnisse für ein Feature-Flag."""

    flag_name: str
    has_ab_test: bool
    message: Optional[str] = None
    rollout_percentage: Optional[int] = None
    total_users_in_target: int
    is_active: Optional[bool] = None
    variants: Dict[str, AbTestVariantStats] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Helper
# =============================================================================


def _require_flag_result(
    result: Optional[Dict[str, object]],
    flag_name: str,
) -> Dict[str, object]:
    """Wirft HTTP 404 wenn das Ergebnis None ist."""
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature-Flag nicht gefunden: {flag_name}",
        )
    return result


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=FeatureToggleListResponse,
    summary="Feature-Flags auflisten",
    description=(
        "Listet alle konfigurierten Feature-Flags auf. "
        "Nur für Administratoren zugänglich."
    ),
)
async def list_feature_toggles(
    limit: int = Query(100, ge=1, le=500, description="Maximale Anzahl Einträge"),
    offset: int = Query(0, ge=0, description="Überspringene Einträge (Paginierung)"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> FeatureToggleListResponse:
    """Listet alle Feature-Flags mit aktuellem Aktivierungsstatus auf."""
    service: FeatureToggleAdminService = get_feature_toggle_admin_service(db)

    try:
        items_raw = await service.list_flags(limit=limit, offset=offset)
        summaries = [FeatureToggleSummary(**item) for item in items_raw]

        return FeatureToggleListResponse(
            items=summaries,
            total=len(summaries),
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.error("api_list_feature_toggles_failed", **safe_error_log(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Feature-Flags",
        )


@router.get(
    "/{flag_name}",
    response_model=FeatureToggleDetail,
    summary="Feature-Flag Details",
    description=(
        "Ruft detaillierte Informationen zu einem Feature-Flag ab, "
        "einschließlich des letzten Änderungsverlaufs."
    ),
)
async def get_feature_toggle_detail(
    flag_name: str,
    history_limit: int = Query(10, ge=1, le=100, description="Anzahl Verlaufseinträge"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> FeatureToggleDetail:
    """Gibt Detailinformationen zu einem Feature-Flag zurück."""
    service: FeatureToggleAdminService = get_feature_toggle_admin_service(db)

    try:
        detail_raw = await service.get_flag_detail(
            flag_name=flag_name,
            history_limit=history_limit,
        )
        detail_raw = _require_flag_result(detail_raw, flag_name)

        history_entries = [
            FeatureToggleHistoryEntry(**entry)
            for entry in detail_raw.pop("history", [])  # type: ignore[arg-type]
        ]
        detail = FeatureToggleDetail(**detail_raw, history=history_entries)  # type: ignore[arg-type]
        return detail

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "api_get_feature_toggle_detail_failed",
            **safe_error_log(exc),
            flag=flag_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen des Feature-Flags: {flag_name}",
        )


@router.patch(
    "/{flag_name}",
    response_model=FeatureToggleSummary,
    summary="Feature-Flag aktualisieren",
    description=(
        "Aktiviert/deaktiviert ein Feature-Flag oder ändert den Rollout-Prozentsatz. "
        "Mindestens ein Feld (enabled oder rollout_percentage) muss angegeben werden."
    ),
)
async def patch_feature_toggle(
    flag_name: str,
    body: FeatureTogglePatchRequest,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> FeatureToggleSummary:
    """Aktualisiert den Status oder Rollout-Prozentsatz eines Feature-Flags."""
    if body.enabled is None and body.rollout_percentage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens 'enabled' oder 'rollout_percentage' muss angegeben werden",
        )

    service: FeatureToggleAdminService = get_feature_toggle_admin_service(db)

    try:
        result_raw: Optional[Dict[str, object]] = None

        # Toggle enabled/disabled first (if requested)
        if body.enabled is not None:
            result_raw = await service.toggle_flag(
                flag_name=flag_name,
                company_id=None,
                user_id=admin.id,
                enabled=body.enabled,
                reason=body.reason,
            )
            _require_flag_result(result_raw, flag_name)

        # Update rollout percentage (if requested)
        if body.rollout_percentage is not None:
            result_raw = await service.update_rollout(
                flag_name=flag_name,
                company_id=None,
                user_id=admin.id,
                rollout_percentage=body.rollout_percentage,
                reason=body.reason,
            )
            _require_flag_result(result_raw, flag_name)

        return FeatureToggleSummary(**result_raw)  # type: ignore[arg-type]

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "api_patch_feature_toggle_failed",
            **safe_error_log(exc),
            flag=flag_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Aktualisieren des Feature-Flags: {flag_name}",
        )


@router.post(
    "/{flag_name}/user-override",
    response_model=FeatureToggleSummary,
    summary="Benutzer-Override setzen",
    description=(
        "Fügt einen Benutzer zur Zielliste hinzu (enabled=true) oder entfernt ihn "
        "(enabled=false). Ermöglicht benutzerspezifische Feature-Aktivierung "
        "unabhängig vom globalen Rollout-Prozentsatz."
    ),
)
async def set_user_override(
    flag_name: str,
    body: UserOverrideRequest,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> FeatureToggleSummary:
    """Setzt oder entfernt einen benutzerspezifischen Override."""
    service: FeatureToggleAdminService = get_feature_toggle_admin_service(db)

    try:
        result_raw = await service.set_flag_for_user(
            flag_name=flag_name,
            target_user_id=body.user_id,
            company_id=None,
            enabled=body.enabled,
            changed_by_id=admin.id,
        )
        _require_flag_result(result_raw, flag_name)
        return FeatureToggleSummary(**result_raw)  # type: ignore[arg-type]

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "api_set_user_override_failed",
            **safe_error_log(exc),
            flag=flag_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Setzen des Benutzer-Overrides: {flag_name}",
        )


@router.get(
    "/{flag_name}/history",
    response_model=List[FeatureToggleHistoryEntry],
    summary="Änderungsverlauf",
    description=(
        "Gibt den vollständigen Änderungsverlauf eines Feature-Flags zurück. "
        "Einträge sind absteigend nach Datum sortiert (neueste zuerst)."
    ),
)
async def get_feature_toggle_history(
    flag_name: str,
    limit: int = Query(50, ge=1, le=500, description="Maximale Anzahl Verlaufseinträge"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[FeatureToggleHistoryEntry]:
    """Ruft den Änderungsverlauf eines Feature-Flags ab."""
    service: FeatureToggleAdminService = get_feature_toggle_admin_service(db)

    try:
        history_raw = await service.get_flag_history(
            flag_name=flag_name,
            limit=limit,
        )
        return [FeatureToggleHistoryEntry(**entry) for entry in history_raw]

    except Exception as exc:
        logger.error(
            "api_get_feature_toggle_history_failed",
            **safe_error_log(exc),
            flag=flag_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen des Verlaufs: {flag_name}",
        )


@router.get(
    "/{flag_name}/ab-results",
    response_model=AbTestResultsResponse,
    summary="A/B Test Ergebnisse",
    description=(
        "Gibt Statistiken zum A/B Test eines Feature-Flags zurück. "
        "Zeigt die Variantenverteilung über alle Benutzer in der Zielliste."
    ),
)
async def get_ab_test_results(
    flag_name: str,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> AbTestResultsResponse:
    """Ruft A/B Test Statistiken für ein Feature-Flag ab."""
    service: FeatureToggleAdminService = get_feature_toggle_admin_service(db)

    try:
        results_raw = await service.get_ab_test_results(flag_name=flag_name)

        if results_raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feature-Flag nicht gefunden: {flag_name}",
            )

        # Convert nested variant dicts to typed models
        variants_typed: Dict[str, AbTestVariantStats] = {}
        for variant_name, stats in (results_raw.get("variants") or {}).items():
            if isinstance(stats, dict):
                variants_typed[variant_name] = AbTestVariantStats(**stats)

        return AbTestResultsResponse(
            flag_name=str(results_raw.get("flag_name", flag_name)),
            has_ab_test=bool(results_raw.get("has_ab_test", False)),
            message=results_raw.get("message"),  # type: ignore[arg-type]
            rollout_percentage=results_raw.get("rollout_percentage"),  # type: ignore[arg-type]
            total_users_in_target=int(results_raw.get("total_users_in_target", 0)),
            is_active=results_raw.get("is_active"),  # type: ignore[arg-type]
            variants=variants_typed,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "api_get_ab_test_results_failed",
            **safe_error_log(exc),
            flag=flag_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der A/B Test Ergebnisse: {flag_name}",
        )

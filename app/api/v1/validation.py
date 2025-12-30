# -*- coding: utf-8 -*-
"""
Validation Queue API fuer Ablage-System OCR.

Endpoints fuer das Enterprise-Grade Validierungssystem:
- Queue-Management (CRUD, Assignment, Approval/Rejection)
- Batch-Operationen
- Field Reviews und Validierung
- Regeln fuer automatische Stichprobenauswahl
- Sample Config
- Analytics und Statistiken

Feinpoliert und durchdacht - Enterprise-grade Validation.
"""

from datetime import datetime, date
from typing import Optional, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.schemas import (
    # Queue Item Schemas
    ValidationQueueItemCreate,
    ValidationQueueItemUpdate,
    ValidationQueueItemAssign,
    ValidationQueueItemApprove,
    ValidationQueueItemReject,
    ValidationQueueItemResponse,
    ValidationQueueItemDetail,
    ValidationQueueListResponse,
    ValidationQueueFilters,
    ValidationQueueSortOptions,
    # Field Schemas
    ValidationFieldResponse,
    ValidationFieldUpdate,
    ValidationFieldValidateResult,
    # Rule Schemas
    ValidationRuleCreate,
    ValidationRuleUpdate,
    ValidationRuleResponse,
    ValidationRuleListResponse,
    # Config Schemas
    ValidationSampleConfigResponse,
    ValidationSampleConfigUpdate,
    # Batch Schemas
    BatchApproveRequest,
    BatchRejectRequest,
    BatchAssignRequest,
    BatchOperationResult,
    # Analytics Schemas
    ValidationAnalyticsOverview,
    EditorStatsListResponse,
    TrendDataResponse,
    DocumentTypeStatsResponse,
    ConfidenceDistribution,
    # Enums
    ValidationStatusEnum,
)
from app.api.dependencies import get_db
from app.core.rbac import require_permission, require_any_permission
from app.services.validation_queue_service import get_validation_queue_service
from app.services.validation_field_service import get_validation_field_service
from app.services.validation_sample_service import get_validation_sample_service
from app.services.validation_analytics_service import get_validation_analytics_service
from app.core.input_sanitization import sanitize_text_field
from app.core.rate_limiting import limiter, RateLimitTier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/validation", tags=["validation"])


# =============================================================================
# QUEUE MANAGEMENT
# =============================================================================

@router.get("/queue", response_model=ValidationQueueListResponse)
async def list_queue_items(
    # Filter parameters
    status: Optional[ValidationStatusEnum] = Query(None, description="Filter nach Status"),
    document_type: Optional[str] = Query(None, description="Filter nach Dokumenttyp"),
    priority_min: Optional[int] = Query(None, ge=0, le=100, description="Mindest-Prioritaet"),
    priority_max: Optional[int] = Query(None, ge=0, le=100, description="Maximale Prioritaet"),
    confidence_min: Optional[float] = Query(None, ge=0, le=1, description="Minimale Confidence"),
    confidence_max: Optional[float] = Query(None, ge=0, le=1, description="Maximale Confidence"),
    assigned_to_id: Optional[UUID] = Query(None, description="Filter nach zugewiesenem Editor"),
    sample_source: Optional[str] = Query(None, description="Filter nach Stichproben-Quelle"),
    created_from: Optional[datetime] = Query(None, description="Erstellt ab"),
    created_to: Optional[datetime] = Query(None, description="Erstellt bis"),
    # Sorting and pagination
    sort_by: Optional[str] = Query("created_at", description="Sortierfeld"),
    sort_order: Optional[str] = Query("desc", regex="^(asc|desc)$", description="Sortierrichtung"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl"),
    offset: int = Query(0, ge=0, description="Offset fuer Paginierung"),
    # Auth
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Listet Validierungs-Queue-Items mit optionalen Filtern auf.

    Erfordert `validation:read` Berechtigung.
    """
    service = get_validation_queue_service(db)

    filters = ValidationQueueFilters(
        status=status,
        document_type=document_type,
        priority_min=priority_min,
        priority_max=priority_max,
        confidence_min=confidence_min,
        confidence_max=confidence_max,
        assigned_to_id=assigned_to_id,
        sample_source=sample_source,
        created_from=created_from,
        created_to=created_to
    )

    sort_options = ValidationQueueSortOptions(
        sort_by=sort_by,
        sort_order=sort_order
    )

    items, total = await service.get_queue_items(
        filters=filters,
        sort_options=sort_options,
        limit=limit,
        offset=offset
    )

    return ValidationQueueListResponse(
        items=[ValidationQueueItemResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/queue/stats")
async def get_queue_stats(
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Uebersichtsstatistiken zur Warteschlange.

    Erfordert `validation:read` Berechtigung.
    """
    service = get_validation_queue_service(db)
    stats = await service.get_queue_stats()
    return stats


@router.get("/queue/my-items", response_model=ValidationQueueListResponse)
async def get_my_assigned_items(
    status: Optional[ValidationStatusEnum] = Query(None, description="Filter nach Status"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl"),
    offset: int = Query(0, ge=0, description="Offset fuer Paginierung"),
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt die dem aktuellen Benutzer zugewiesenen Queue-Items.

    Erfordert `validation:write` Berechtigung.
    """
    service = get_validation_queue_service(db)
    items, total = await service.get_my_assigned_items(
        editor_id=current_user.id,
        status=status.value if status else None,
        limit=limit,
        offset=offset
    )

    return ValidationQueueListResponse(
        items=[ValidationQueueItemResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/queue", response_model=ValidationQueueItemResponse, status_code=201)
@limiter.limit(RateLimitTier.API_GENERAL)
async def create_queue_item(
    request: Request,
    item_data: ValidationQueueItemCreate,
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Fuegt ein Dokument manuell zur Validierungswarteschlange hinzu.

    Erfordert `validation:write` Berechtigung.
    """
    service = get_validation_queue_service(db)
    item = await service.add_to_queue(
        document_id=item_data.document_id,
        source=item_data.sample_source.value if item_data.sample_source else "manual",
        priority=item_data.priority or 50,
        notes=item_data.notes,
        rule_id=item_data.triggered_by_rule_id
    )

    return ValidationQueueItemResponse.model_validate(item)


@router.get("/queue/{item_id}", response_model=ValidationQueueItemDetail)
async def get_queue_item(
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt ein einzelnes Queue-Item mit Details.

    Erfordert `validation:read` Berechtigung.
    """
    service = get_validation_queue_service(db)
    item = await service.get_queue_item(item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Validierungs-Item nicht gefunden"
        )

    # Lade Felder fuer Detailansicht
    field_service = get_validation_field_service(db)
    fields = await field_service.get_fields_for_review(item_id)

    return ValidationQueueItemDetail(
        **ValidationQueueItemResponse.model_validate(item).model_dump(),
        fields=[ValidationFieldResponse.model_validate(f) for f in fields]
    )


@router.patch("/queue/{item_id}", response_model=ValidationQueueItemResponse)
async def update_queue_item(
    update_data: ValidationQueueItemUpdate,
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert ein Queue-Item.

    Erfordert `validation:write` Berechtigung.
    """
    service = get_validation_queue_service(db)
    item = await service.update_queue_item(item_id, update_data)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Validierungs-Item nicht gefunden"
        )

    return ValidationQueueItemResponse.model_validate(item)


@router.delete("/queue/{item_id}", status_code=204)
async def delete_queue_item(
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Loescht ein Queue-Item.

    Erfordert `validation:manage` Berechtigung (nur Admins).
    """
    service = get_validation_queue_service(db)
    deleted = await service.delete_queue_item(item_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Validierungs-Item nicht gefunden"
        )

    return JSONResponse(status_code=204, content=None)


# =============================================================================
# ASSIGNMENT
# =============================================================================

@router.post("/queue/{item_id}/assign", response_model=ValidationQueueItemResponse)
@limiter.limit(RateLimitTier.API_GENERAL)
async def assign_queue_item(
    request: Request,
    assign_data: ValidationQueueItemAssign,
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Weist ein Queue-Item einem Editor zu.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_queue_service(db)

    try:
        item = await service.assign_to_editor(
            item_id=item_id,
            editor_id=assign_data.editor_id,
            assigned_by_id=current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Validierungs-Item nicht gefunden"
        )

    return ValidationQueueItemResponse.model_validate(item)


@router.post("/queue/{item_id}/unassign", response_model=ValidationQueueItemResponse)
async def unassign_queue_item(
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Entfernt die Zuweisung eines Queue-Items.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_queue_service(db)
    item = await service.unassign(item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Validierungs-Item nicht gefunden"
        )

    return ValidationQueueItemResponse.model_validate(item)


# =============================================================================
# APPROVAL / REJECTION
# =============================================================================

@router.post("/queue/{item_id}/approve", response_model=ValidationQueueItemResponse)
@limiter.limit(RateLimitTier.API_GENERAL)
async def approve_queue_item(
    request: Request,
    approve_data: ValidationQueueItemApprove,
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Genehmigt ein Queue-Item nach erfolgreicher Validierung.

    Erfordert `validation:write` Berechtigung.
    """
    service = get_validation_queue_service(db)

    # Input Sanitization: Notes gegen XSS schützen
    sanitized_notes = None
    if approve_data.notes:
        sanitized_notes = sanitize_text_field(
            approve_data.notes,
            max_length=2000,
            field_name="approval_notes"
        )

    try:
        item = await service.approve_item(
            item_id=item_id,
            validated_by_id=current_user.id,
            notes=sanitized_notes,
            apply_corrections=approve_data.apply_corrections
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Validierungs-Item nicht gefunden"
        )

    return ValidationQueueItemResponse.model_validate(item)


@router.post("/queue/{item_id}/reject", response_model=ValidationQueueItemResponse)
@limiter.limit(RateLimitTier.API_GENERAL)
async def reject_queue_item(
    request: Request,
    reject_data: ValidationQueueItemReject,
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Lehnt ein Queue-Item ab.

    Erfordert `validation:write` Berechtigung.
    """
    service = get_validation_queue_service(db)

    # Input Sanitization: Ablehnungsgrund gegen XSS schützen
    sanitized_reason = sanitize_text_field(
        reject_data.reason,
        max_length=2000,
        field_name="rejection_reason"
    )

    try:
        item = await service.reject_item(
            item_id=item_id,
            validated_by_id=current_user.id,
            reason=sanitized_reason,
            rejection_category=reject_data.rejection_category.value if reject_data.rejection_category else None
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Validierungs-Item nicht gefunden"
        )

    return ValidationQueueItemResponse.model_validate(item)


# =============================================================================
# BATCH OPERATIONS
# =============================================================================

@router.post("/batch/approve", response_model=BatchOperationResult)
@limiter.limit(RateLimitTier.API_HEAVY)
async def batch_approve(
    request: Request,
    batch_data: BatchApproveRequest,
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Genehmigt mehrere Queue-Items gleichzeitig.

    Erfordert `validation:write` Berechtigung.
    """
    service = get_validation_queue_service(db)

    # Input Sanitization: Batch-Notes gegen XSS schützen
    sanitized_notes = None
    if batch_data.notes:
        sanitized_notes = sanitize_text_field(
            batch_data.notes,
            max_length=500,
            field_name="batch_approval_notes"
        )

    result = await service.batch_approve(
        item_ids=batch_data.item_ids,
        validated_by_id=current_user.id,
        notes=sanitized_notes
    )

    return BatchOperationResult(**result)


@router.post("/batch/reject", response_model=BatchOperationResult)
@limiter.limit(RateLimitTier.API_HEAVY)
async def batch_reject(
    request: Request,
    batch_data: BatchRejectRequest,
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Lehnt mehrere Queue-Items gleichzeitig ab.

    Erfordert `validation:write` Berechtigung.
    """
    service = get_validation_queue_service(db)

    # Input Sanitization: Ablehnungsgrund gegen XSS schützen
    sanitized_reason = sanitize_text_field(
        batch_data.reason,
        max_length=2000,
        field_name="batch_rejection_reason"
    )

    result = await service.batch_reject(
        item_ids=batch_data.item_ids,
        validated_by_id=current_user.id,
        reason=sanitized_reason,
        rejection_category=batch_data.rejection_category.value if batch_data.rejection_category else None
    )

    return BatchOperationResult(**result)


@router.post("/batch/assign", response_model=BatchOperationResult)
@limiter.limit(RateLimitTier.API_HEAVY)
async def batch_assign(
    request: Request,
    batch_data: BatchAssignRequest,
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Weist mehrere Queue-Items einem Editor zu.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_queue_service(db)

    result = await service.batch_assign(
        item_ids=batch_data.item_ids,
        editor_id=batch_data.editor_id,
        assigned_by_id=current_user.id
    )

    return BatchOperationResult(**result)


# =============================================================================
# FIELD REVIEWS
# =============================================================================

@router.get("/queue/{item_id}/fields", response_model=List[ValidationFieldResponse])
async def get_queue_item_fields(
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt alle Feld-Reviews fuer ein Queue-Item.

    Erfordert `validation:read` Berechtigung.
    """
    field_service = get_validation_field_service(db)
    fields = await field_service.get_fields_for_review(item_id)
    return [ValidationFieldResponse.model_validate(f) for f in fields]


@router.patch("/queue/{item_id}/fields/{field_id}", response_model=ValidationFieldResponse)
async def update_field(
    update_data: ValidationFieldUpdate,
    item_id: UUID = Path(..., description="Queue Item ID"),
    field_id: UUID = Path(..., description="Field Review ID"),
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert einen Feldwert.

    Erfordert `validation:write` Berechtigung.
    """
    field_service = get_validation_field_service(db)

    field = await field_service.update_field(
        field_id=field_id,
        corrected_value=update_data.corrected_value,
        reviewed_by_id=current_user.id
    )

    if not field:
        raise HTTPException(
            status_code=404,
            detail="Feld nicht gefunden"
        )

    return ValidationFieldResponse.model_validate(field)


@router.post("/queue/{item_id}/fields/{field_id}/validate", response_model=ValidationFieldValidateResult)
async def validate_field(
    item_id: UUID = Path(..., description="Queue Item ID"),
    field_id: UUID = Path(..., description="Field Review ID"),
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Validiert ein einzelnes Feld (Umlaut-Pruefung, Format-Validierung).

    Erfordert `validation:write` Berechtigung.
    """
    field_service = get_validation_field_service(db)

    try:
        result = await field_service.validate_field(field_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return result


@router.post("/queue/{item_id}/validate-all", response_model=List[ValidationFieldValidateResult])
async def validate_all_fields(
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Validiert alle Felder eines Queue-Items.

    Erfordert `validation:write` Berechtigung.
    """
    field_service = get_validation_field_service(db)
    results = await field_service.validate_all_fields(item_id)
    return results


@router.get("/queue/{item_id}/field-stats")
async def get_field_stats(
    item_id: UUID = Path(..., description="Queue Item ID"),
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Statistiken zu Feldern eines Queue-Items.

    Erfordert `validation:read` Berechtigung.
    """
    field_service = get_validation_field_service(db)
    stats = await field_service.get_field_stats(item_id)
    return stats


# =============================================================================
# VALIDATION RULES (Admin-only)
# =============================================================================

@router.get("/rules", response_model=ValidationRuleListResponse)
async def list_rules(
    include_inactive: bool = Query(False, description="Auch inaktive Regeln anzeigen"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Listet alle Validierungsregeln auf.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_sample_service(db)

    if include_inactive:
        rules = await service.get_all_rules()
    else:
        rules = await service.get_active_rules()

    return ValidationRuleListResponse(
        rules=[ValidationRuleResponse.model_validate(r) for r in rules],
        total=len(rules)
    )


@router.post("/rules", response_model=ValidationRuleResponse, status_code=201)
async def create_rule(
    rule_data: ValidationRuleCreate,
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt eine neue Validierungsregel.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_sample_service(db)
    rule = await service.create_rule(
        rule_data=rule_data,
        created_by_id=current_user.id
    )

    return ValidationRuleResponse.model_validate(rule)


@router.get("/rules/{rule_id}", response_model=ValidationRuleResponse)
async def get_rule(
    rule_id: UUID = Path(..., description="Regel ID"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt eine einzelne Regel.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_sample_service(db)
    rule = await service.get_rule(rule_id)

    if not rule:
        raise HTTPException(
            status_code=404,
            detail="Regel nicht gefunden"
        )

    return ValidationRuleResponse.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=ValidationRuleResponse)
async def update_rule(
    update_data: ValidationRuleUpdate,
    rule_id: UUID = Path(..., description="Regel ID"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert eine Regel.

    Erfordert `validation:manage` Berechtigung.
    System-Regeln koennen nicht bearbeitet werden.
    """
    service = get_validation_sample_service(db)

    try:
        rule = await service.update_rule(rule_id, update_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not rule:
        raise HTTPException(
            status_code=404,
            detail="Regel nicht gefunden"
        )

    return ValidationRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: UUID = Path(..., description="Regel ID"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Loescht eine Regel.

    Erfordert `validation:manage` Berechtigung.
    System-Regeln koennen nicht geloescht werden.
    """
    service = get_validation_sample_service(db)

    try:
        deleted = await service.delete_rule(rule_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Regel nicht gefunden"
        )

    return JSONResponse(status_code=204, content=None)


# =============================================================================
# SAMPLE CONFIG (Admin-only)
# =============================================================================

@router.get("/sample-config", response_model=ValidationSampleConfigResponse)
async def get_sample_config(
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt die aktuelle Stichproben-Konfiguration.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_sample_service(db)
    config = await service.get_sample_config()

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Keine Stichproben-Konfiguration gefunden"
        )

    return ValidationSampleConfigResponse.model_validate(config)


@router.put("/sample-config/{config_id}", response_model=ValidationSampleConfigResponse)
async def update_sample_config(
    update_data: ValidationSampleConfigUpdate,
    config_id: UUID = Path(..., description="Config ID"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert die Stichproben-Konfiguration.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_sample_service(db)
    config = await service.update_sample_config(config_id, update_data)

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Stichproben-Konfiguration nicht gefunden"
        )

    return ValidationSampleConfigResponse.model_validate(config)


# =============================================================================
# ANALYTICS
# =============================================================================

@router.get("/analytics/overview", response_model=ValidationAnalyticsOverview)
@limiter.limit(RateLimitTier.API_HEAVY)
async def get_analytics_overview(
    request: Request,
    date_from: Optional[date] = Query(None, description="Startdatum"),
    date_to: Optional[date] = Query(None, description="Enddatum"),
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Uebersichtsstatistiken zur Validierung.

    Erfordert `validation:read` Berechtigung.
    """
    service = get_validation_analytics_service(db)
    stats = await service.get_overview_stats(date_from, date_to)
    return stats


@router.get("/analytics/editors", response_model=EditorStatsListResponse)
@limiter.limit(RateLimitTier.API_HEAVY)
async def get_editor_stats(
    request: Request,
    date_from: Optional[date] = Query(None, description="Startdatum"),
    date_to: Optional[date] = Query(None, description="Enddatum"),
    current_user: User = Depends(require_permission("validation:manage")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Statistiken pro Editor.

    Erfordert `validation:manage` Berechtigung.
    """
    service = get_validation_analytics_service(db)
    stats = await service.get_editor_stats(date_from, date_to)
    return EditorStatsListResponse(editors=stats)


@router.get("/analytics/trends", response_model=TrendDataResponse)
@limiter.limit(RateLimitTier.API_HEAVY)
async def get_trends(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Anzahl Tage"),
    group_by: str = Query("day", regex="^(day|week|month)$", description="Gruppierung"),
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Trend-Daten ueber Zeit.

    Erfordert `validation:read` Berechtigung.
    """
    service = get_validation_analytics_service(db)
    trends = await service.get_trend_data(days, group_by)
    return TrendDataResponse(data_points=trends, group_by=group_by)


@router.get("/analytics/document-types", response_model=DocumentTypeStatsResponse)
@limiter.limit(RateLimitTier.API_HEAVY)
async def get_document_type_stats(
    request: Request,
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Statistiken nach Dokumenttyp.

    Erfordert `validation:read` Berechtigung.
    """
    service = get_validation_analytics_service(db)
    stats = await service.get_document_type_stats()
    return DocumentTypeStatsResponse(document_types=stats)


@router.get("/analytics/confidence-distribution", response_model=ConfidenceDistribution)
@limiter.limit(RateLimitTier.API_HEAVY)
async def get_confidence_distribution(
    request: Request,
    current_user: User = Depends(require_permission("validation:read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt die Confidence-Verteilung.

    Erfordert `validation:read` Berechtigung.
    """
    service = get_validation_analytics_service(db)
    distribution = await service.get_confidence_distribution()
    return distribution


# =============================================================================
# DOCUMENT INTEGRATION
# =============================================================================

@router.post("/documents/{document_id}/queue-for-validation", response_model=ValidationQueueItemResponse, status_code=201)
@limiter.limit(RateLimitTier.API_GENERAL)
async def queue_document_for_validation(
    request: Request,
    document_id: UUID = Path(..., description="Dokument ID"),
    priority: int = Query(50, ge=0, le=100, description="Prioritaet"),
    notes: Optional[str] = Query(None, description="Notizen"),
    current_user: User = Depends(require_permission("validation:write")),
    db: AsyncSession = Depends(get_db)
):
    """
    Fuegt ein Dokument manuell zur Validierungswarteschlange hinzu.

    Erfordert `validation:write` Berechtigung.
    """
    service = get_validation_queue_service(db)

    try:
        item = await service.add_to_queue(
            document_id=document_id,
            source="manual",
            priority=priority,
            notes=notes
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ValidationQueueItemResponse.model_validate(item)

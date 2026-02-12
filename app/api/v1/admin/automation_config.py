# -*- coding: utf-8 -*-
"""Admin Automation Configuration API.

Provides endpoints for managing:
- Dunning/Mahnung configuration and statistics
- Autonomy levels and trust configuration
- Pending action approval queue
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from decimal import Decimal
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_active_user, get_current_superuser, get_db
from app.db.models import User

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/automation", tags=["Admin - Automation"])


# ============================================================================
# Dunning Config Models
# ============================================================================

class DunningConfigResponse(BaseModel):
    """Mahnung-Konfiguration."""
    reminder_after_days: int = 7
    first_dunning_after_days: int = 14
    second_dunning_after_days: int = 28
    final_dunning_after_days: int = 42
    first_dunning_fee: Decimal = Decimal("5.00")
    second_dunning_fee: Decimal = Decimal("10.00")
    final_dunning_fee: Decimal = Decimal("15.00")
    late_interest_rate: float = 5.0
    min_dunning_amount: Decimal = Decimal("5.00")
    auto_process_enabled: bool = False
    dry_run_mode: bool = True


class DunningConfigUpdate(BaseModel):
    """Mahnung-Konfiguration Update."""
    reminder_after_days: Optional[int] = None
    first_dunning_after_days: Optional[int] = None
    second_dunning_after_days: Optional[int] = None
    final_dunning_after_days: Optional[int] = None
    first_dunning_fee: Optional[Decimal] = None
    second_dunning_fee: Optional[Decimal] = None
    final_dunning_fee: Optional[Decimal] = None
    late_interest_rate: Optional[float] = None
    min_dunning_amount: Optional[Decimal] = None
    auto_process_enabled: Optional[bool] = None
    dry_run_mode: Optional[bool] = None


class DunningStatsResponse(BaseModel):
    """Mahnung-Statistiken."""
    active_dunnings_total: int = 0
    by_level: Dict[int, int] = Field(default_factory=dict)
    total_fees_collected: Decimal = Decimal("0.00")
    total_outstanding_fees: Decimal = Decimal("0.00")
    avg_resolution_days: float = 0.0


# ============================================================================
# Autonomy Config Models
# ============================================================================

class TrustLevelConfig(BaseModel):
    """Vertrauensstufe pro Aktionstyp."""
    action_type: str
    trust_level: str  # "immediate", "delayed", "confirm"
    confidence_threshold: float = 0.90


class AutonomyConfigResponse(BaseModel):
    """Autonomie-Konfiguration."""
    document_classification_threshold: float = 0.95
    entity_linking_threshold: float = 0.90
    invoice_approval_threshold: float = 0.95
    payment_matching_threshold: float = 0.95
    ocr_correction_threshold: float = 0.90
    payment_auto_approve_limit: Decimal = Decimal("5000.00")
    payment_suggest_limit: Decimal = Decimal("10000.00")
    dunning_auto_send_level: int = 1
    dunning_min_overdue_days: int = 14
    master_data_auto_update_confidence: float = 0.95
    filing_auto_confidence: float = 0.95
    filing_suggest_confidence: float = 0.80
    action_trust_levels: List[TrustLevelConfig] = Field(default_factory=list)


class AutonomyConfigUpdate(BaseModel):
    """Autonomie-Konfiguration Update (partial)."""
    document_classification_threshold: Optional[float] = None
    entity_linking_threshold: Optional[float] = None
    invoice_approval_threshold: Optional[float] = None
    payment_matching_threshold: Optional[float] = None
    ocr_correction_threshold: Optional[float] = None
    payment_auto_approve_limit: Optional[Decimal] = None
    payment_suggest_limit: Optional[Decimal] = None
    dunning_auto_send_level: Optional[int] = None
    dunning_min_overdue_days: Optional[int] = None
    master_data_auto_update_confidence: Optional[float] = None
    filing_auto_confidence: Optional[float] = None
    filing_suggest_confidence: Optional[float] = None
    action_trust_levels: Optional[List[TrustLevelConfig]] = None


# ============================================================================
# Action Queue Models
# ============================================================================

class QueuedActionResponse(BaseModel):
    """Warteschlangen-Aktion."""
    id: str
    action_type: str
    entity_name: Optional[str] = None
    entity_type: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""
    proposed_change: str = ""
    created_at: Optional[datetime] = None
    will_execute_at: Optional[datetime] = None
    status: str = "pending"


class ActionQueueListResponse(BaseModel):
    """Liste der wartenden Aktionen."""
    actions: List[QueuedActionResponse] = Field(default_factory=list)
    total: int = 0


# ============================================================================
# Dunning Config Endpoints
# ============================================================================

@router.get("/dunning/config", response_model=DunningConfigResponse)
async def get_dunning_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> DunningConfigResponse:
    """Aktuelle Mahnung-Konfiguration abrufen."""
    try:
        from app.services.banking.dunning_service import DunningService

        service = DunningService()
        cfg = service.config

        return DunningConfigResponse(
            reminder_after_days=cfg.reminder_after_days,
            first_dunning_after_days=cfg.first_dunning_after_days,
            second_dunning_after_days=cfg.second_dunning_after_days,
            final_dunning_after_days=cfg.final_dunning_after_days,
            first_dunning_fee=cfg.first_dunning_fee,
            second_dunning_fee=cfg.second_dunning_fee,
            final_dunning_fee=cfg.final_dunning_fee,
            late_interest_rate=float(cfg.late_interest_rate),
            min_dunning_amount=cfg.min_dunning_amount,
            auto_process_enabled=False,  # Not in current config
            dry_run_mode=True,  # Default
        )
    except Exception as e:
        logger.warning("dunning_config_load_failed", error=str(e))
        return DunningConfigResponse()


@router.put("/dunning/config", response_model=DunningConfigResponse)
async def update_dunning_config(
    config: DunningConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> DunningConfigResponse:
    """Mahnung-Konfiguration aktualisieren."""
    # Load current config
    current = await get_dunning_config(db=db, current_user=current_user)

    # Merge updates
    updates = config.model_dump(exclude_unset=True)
    merged_dict = current.model_dump()
    merged_dict.update(updates)

    logger.info(
        "dunning_config_updated",
        updates=list(updates.keys()),
        user_id=str(current_user.id),
    )

    # In production, this would persist to a settings table
    # For now, return the merged config
    return DunningConfigResponse(**merged_dict)


@router.get("/dunning/stats", response_model=DunningStatsResponse)
async def get_dunning_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> DunningStatsResponse:
    """Mahnung-Statistiken abrufen."""
    try:
        from app.services.banking.dunning_service import DunningService

        service = DunningService()
        stats = await service.get_dunning_stats(db, current_user.id)

        if stats:
            # Extract by_level from dict and convert to int keys
            by_level_dict: Dict[int, int] = {}
            if "by_level" in stats:
                for level_str, count in stats["by_level"].items():
                    try:
                        level_int = int(level_str)
                        by_level_dict[level_int] = count
                    except (ValueError, TypeError):
                        continue

            return DunningStatsResponse(
                active_dunnings_total=stats.get("total_active", 0),
                by_level=by_level_dict,
                total_fees_collected=Decimal(str(stats.get("total_fees", 0))),
                total_outstanding_fees=Decimal(str(stats.get("total_amount_overdue", 0))),
                avg_resolution_days=stats.get("avg_days_overdue", 0.0),
            )
    except Exception as e:
        logger.warning("dunning_stats_failed", error=str(e), exc_info=True)

    return DunningStatsResponse()


# ============================================================================
# Autonomy Config Endpoints
# ============================================================================

@router.get("/autonomy/config", response_model=AutonomyConfigResponse)
async def get_autonomy_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> AutonomyConfigResponse:
    """Aktuelle Autonomie-Konfiguration abrufen."""
    try:
        from app.services.ai.autonomous_actions_service import create_autonomy_config

        cfg = create_autonomy_config()

        return AutonomyConfigResponse(
            document_classification_threshold=cfg.document_classification_threshold,
            entity_linking_threshold=cfg.entity_linking_threshold,
            invoice_approval_threshold=cfg.invoice_approval_threshold,
            payment_matching_threshold=cfg.payment_matching_threshold,
            ocr_correction_threshold=cfg.ocr_correction_threshold,
            payment_auto_approve_limit=cfg.payment_auto_approve_limit,
            payment_suggest_limit=cfg.payment_suggest_limit,
            dunning_auto_send_level=cfg.dunning_auto_send_level,
            dunning_min_overdue_days=cfg.dunning_min_overdue_days,
            master_data_auto_update_confidence=cfg.master_data_auto_update_confidence,
            filing_auto_confidence=cfg.filing_auto_confidence,
            filing_suggest_confidence=cfg.filing_suggest_confidence,
            action_trust_levels=[],  # Not in current config
        )
    except Exception as e:
        logger.warning("autonomy_config_load_failed", error=str(e))
        return AutonomyConfigResponse()


@router.put("/autonomy/config", response_model=AutonomyConfigResponse)
async def update_autonomy_config(
    config: AutonomyConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> AutonomyConfigResponse:
    """Autonomie-Konfiguration aktualisieren."""
    # Load current config
    current = await get_autonomy_config(db=db, current_user=current_user)

    # Merge updates
    updates = config.model_dump(exclude_unset=True)
    merged_dict = current.model_dump()
    merged_dict.update(updates)

    logger.info(
        "autonomy_config_updated",
        updates=list(updates.keys()),
        user_id=str(current_user.id),
    )

    # In production, this would persist to a settings table
    return AutonomyConfigResponse(**merged_dict)


# ============================================================================
# Action Queue Endpoints
# ============================================================================

@router.get("/autonomy/queue", response_model=ActionQueueListResponse)
async def get_action_queue(
    status: str = "pending",
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> ActionQueueListResponse:
    """Warteschlange der ausstehenden autonomen Aktionen."""
    try:
        from app.services.ai.predictive_action_service import get_predictive_action_service

        service = get_predictive_action_service()

        # Get pending actions for the user's company
        if not current_user.company_id:
            logger.warning(
                "action_queue_no_company",
                user_id=str(current_user.id),
            )
            return ActionQueueListResponse()

        pending = await service.get_pending_actions(
            db=db,
            company_id=current_user.company_id,
            user_id=current_user.id,
            limit=limit,
        )

        actions = [
            QueuedActionResponse(
                id=str(action.id),
                action_type=action.action_type.value,
                entity_name=action.metadata.get("invoice_number") or action.metadata.get("entity_name"),
                entity_type=action.target_type,
                confidence=action.confidence,
                reason=action.description,
                proposed_change=action.title,
                created_at=action.created_at,
                will_execute_at=action.suggested_action_time,
                status=action.status.value,
            )
            for action in pending
        ]

        return ActionQueueListResponse(actions=actions, total=len(actions))

    except Exception as e:
        logger.warning("action_queue_failed", error=str(e), exc_info=True)
        return ActionQueueListResponse()


@router.post("/autonomy/queue/{action_id}/approve")
async def approve_action(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> Dict[str, str]:
    """Autonome Aktion genehmigen."""
    try:
        from app.services.ai.predictive_action_service import get_predictive_action_service

        service = get_predictive_action_service()

        # Get pending actions to find the one to approve
        if not current_user.company_id:
            raise HTTPException(status_code=400, detail="Benutzer hat keine zugewiesene Firma")

        pending = await service.get_pending_actions(
            db=db,
            company_id=current_user.company_id,
            user_id=current_user.id,
            limit=100,
        )

        # Find the action
        target_action = None
        for action in pending:
            if action.id == action_id:
                target_action = action
                break

        if not target_action:
            raise HTTPException(status_code=404, detail="Aktion nicht gefunden")

        # Accept the action
        success, message = await service.accept_action(
            db=db,
            action=target_action,
            user_id=current_user.id,
            execute_action=True,
        )

        if not success:
            raise HTTPException(status_code=500, detail=message)

        await db.commit()

        logger.info(
            "action_approved",
            action_id=str(action_id),
            user_id=str(current_user.id),
        )

        return {"status": "approved", "message": "Aktion genehmigt"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("action_approve_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Genehmigung fehlgeschlagen")


@router.post("/autonomy/queue/{action_id}/reject")
async def reject_action(
    action_id: UUID,
    reason: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> Dict[str, str]:
    """Autonome Aktion ablehnen."""
    try:
        from app.services.ai.predictive_action_service import get_predictive_action_service

        service = get_predictive_action_service()

        # Get pending actions to find the one to reject
        if not current_user.company_id:
            raise HTTPException(status_code=400, detail="Benutzer hat keine zugewiesene Firma")

        pending = await service.get_pending_actions(
            db=db,
            company_id=current_user.company_id,
            user_id=current_user.id,
            limit=100,
        )

        # Find the action
        target_action = None
        for action in pending:
            if action.id == action_id:
                target_action = action
                break

        if not target_action:
            raise HTTPException(status_code=404, detail="Aktion nicht gefunden")

        # Reject the action
        success = await service.reject_action(
            db=db,
            action=target_action,
            user_id=current_user.id,
            reason=reason,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Ablehnung fehlgeschlagen")

        await db.commit()

        logger.info(
            "action_rejected",
            action_id=str(action_id),
            user_id=str(current_user.id),
            reason=reason,
        )

        return {"status": "rejected", "message": "Aktion abgelehnt"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("action_reject_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Ablehnung fehlgeschlagen")

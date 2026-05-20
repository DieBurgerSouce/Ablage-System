# -*- coding: utf-8 -*-
"""
Digital Twin API Endpoints.

Provides 360° company overview with real-time snapshots.

Endpoints:
- GET /api/v1/digital-twin - Get full snapshot
- GET /api/v1/digital-twin/{section} - Get specific section
"""

from typing import Any, Dict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.digital_twin_service import (
    DigitalTwinService,
    get_digital_twin_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/digital-twin", tags=["Digital Twin"])


@router.get(
    "",
    response_model=Dict[str, Any],
    summary="Digital Twin Snapshot abrufen",
    description="Vollständiger 360° Schnappschuss des Unternehmens mit allen Metriken und Trends.",
)
async def get_digital_twin_snapshot(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ruft vollständigen Digital Twin Snapshot ab.

    Returns:
        Digital Twin Snapshot mit allen Sektionen
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen",
        )

    try:
        service = get_digital_twin_service(db)
        snapshot = await service.get_snapshot(current_user.company_id)

        logger.info(
            "digital_twin_snapshot_retrieved",
            user_id=str(current_user.id),
            company_id=str(current_user.company_id),
        )

        return snapshot.to_dict()

    except Exception as e:
        logger.error(
            "digital_twin_snapshot_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Abrufen des Digital Twin"),
        )


@router.get(
    "/{section}",
    response_model=Dict[str, Any],
    summary="Digital Twin Sektion abrufen",
    description="Einzelne Sektion des Digital Twin abrufen (financial_health, risk_overview, etc.).",
)
async def get_digital_twin_section(
    section: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ruft einzelne Digital Twin Sektion ab.

    Args:
        section: Section name (financial_health, risk_overview, document_pipeline, compliance_status, key_metrics, trends)

    Returns:
        Section data
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen",
        )

    valid_sections = [
        "financial_health",
        "risk_overview",
        "document_pipeline",
        "compliance_status",
        "key_metrics",
        "trends",
    ]

    if section not in valid_sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültige Sektion. Erlaubt: {', '.join(valid_sections)}",
        )

    try:
        service = get_digital_twin_service(db)
        section_data = await service.get_section(current_user.company_id, section)

        logger.info(
            "digital_twin_section_retrieved",
            user_id=str(current_user.id),
            company_id=str(current_user.company_id),
            section=section,
        )

        # Convert dataclass to dict
        if hasattr(section_data, "__dict__"):
            result = {}
            for key, value in section_data.__dict__.items():
                if isinstance(value, list):
                    result[key] = value
                elif hasattr(value, "__dict__"):
                    result[key] = value.__dict__
                else:
                    # Convert Decimal to float
                    try:
                        result[key] = float(value)
                    except (TypeError, ValueError):
                        result[key] = value
            return result
        else:
            return {"data": section_data}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Digitaler-Zwilling"),
        )
    except Exception as e:
        logger.error(
            "digital_twin_section_failed",
            user_id=str(current_user.id),
            section=section,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Abrufen der Sektion"),
        )

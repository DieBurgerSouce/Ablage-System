# -*- coding: utf-8 -*-
"""
Barcode/QR-Code API Endpoints fuer Ablage-System.

REST API fuer Barcode/QR-Erkennung:
- Erkannte Codes pro Dokument abrufen
- Erneute Erkennung ausloesen
- Einzelne Erkennung abrufen

Feinpoliert und durchdacht - Deutsche Barcode-Erkennung.
"""

from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.api.schemas.barcode import (
    BarcodeDetectionResponse,
    BarcodeListResponse,
    BarcodeRedetectRequest,
    BarcodeRedetectResponse,
)
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.models_barcode import BarcodeCategory
from app.services.barcode_pipeline_service import BarcodePipelineService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/barcodes", tags=["Barcode-Erkennung"])


@router.get(
    "/documents/{document_id}",
    response_model=BarcodeListResponse,
    summary="Erkannte Barcodes fuer Dokument abrufen",
    description="Gibt alle erkannten Barcodes und QR-Codes fuer ein Dokument zurueck.",
)
async def get_document_barcodes(
    document_id: UUID,
    kategorie: Optional[str] = Query(
        None,
        description="Kategorie-Filter (payment, product, logistics, document, url, other)",
    ),
    seite: Optional[int] = Query(
        None,
        ge=1,
        description="Seitennummer-Filter (1-basiert)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BarcodeListResponse:
    """Erkannte Barcodes/QR-Codes fuer ein Dokument abrufen."""
    try:
        service = BarcodePipelineService(db)
        detections = await service.get_document_barcodes(
            document_id=str(document_id),
            company_id=str(company_id),
            category=kategorie,
            page_number=seite,
        )

        erkennungen = [
            BarcodeDetectionResponse(
                id=d.id,
                document_id=d.document_id,
                code_type=d.code_type,
                category=d.category,
                raw_value=d.raw_value,
                parsed_data=d.parsed_data or {},
                position_x=d.position_x,
                position_y=d.position_y,
                position_width=d.position_width,
                position_height=d.position_height,
                page_number=d.page_number,
                confidence=d.confidence,
                created_at=d.created_at,
            )
            for d in detections
        ]

        hat_zahlungscodes = any(
            d.category == BarcodeCategory.PAYMENT.value for d in detections
        )
        hat_produktcodes = any(
            d.category == BarcodeCategory.PRODUCT.value for d in detections
        )

        return BarcodeListResponse(
            document_id=document_id,
            erkennungen=erkennungen,
            gesamt=len(erkennungen),
            hat_zahlungscodes=hat_zahlungscodes,
            hat_produktcodes=hat_produktcodes,
        )

    except Exception as e:
        logger.error(
            "barcode_api_get_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Barcode-Abfrage"),
        )


@router.post(
    "/documents/{document_id}/redetect",
    response_model=BarcodeRedetectResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Erneute Barcode-Erkennung ausloesen",
    description="Loest eine asynchrone erneute Barcode-/QR-Code-Erkennung fuer das Dokument aus.",
)
async def redetect_document_barcodes(
    document_id: UUID,
    request: Optional[BarcodeRedetectRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BarcodeRedetectResponse:
    """Erneute Barcode-Erkennung fuer ein Dokument ausloesen."""
    try:
        from app.workers.tasks.barcode_tasks import detect_barcodes_task

        task = detect_barcodes_task.delay(
            document_id=str(document_id),
            company_id=str(company_id),
            redetect=True,
        )

        grund = request.grund if request else None
        logger.info(
            "barcode_redetect_triggered",
            document_id=str(document_id),
            task_id=task.id,
            grund=grund,
        )

        return BarcodeRedetectResponse(
            document_id=document_id,
            nachricht="Erneute Barcode-Erkennung wurde gestartet.",
            task_id=task.id,
        )

    except Exception as e:
        logger.error(
            "barcode_api_redetect_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Barcode-Erkennung"),
        )


@router.get(
    "/{barcode_id}",
    response_model=BarcodeDetectionResponse,
    summary="Einzelne Barcode-Erkennung abrufen",
    description="Gibt eine einzelne Barcode-/QR-Code-Erkennung zurueck.",
)
async def get_barcode(
    barcode_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BarcodeDetectionResponse:
    """Einzelne Barcode-Erkennung abrufen."""
    try:
        service = BarcodePipelineService(db)
        detection = await service.get_barcode_by_id(
            barcode_id=str(barcode_id),
            company_id=str(company_id),
        )

        if detection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Barcode-Erkennung nicht gefunden.",
            )

        return BarcodeDetectionResponse(
            id=detection.id,
            document_id=detection.document_id,
            code_type=detection.code_type,
            category=detection.category,
            raw_value=detection.raw_value,
            parsed_data=detection.parsed_data or {},
            position_x=detection.position_x,
            position_y=detection.position_y,
            position_width=detection.position_width,
            position_height=detection.position_height,
            page_number=detection.page_number,
            confidence=detection.confidence,
            created_at=detection.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "barcode_api_get_single_error",
            barcode_id=str(barcode_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Barcode-Abfrage"),
        )

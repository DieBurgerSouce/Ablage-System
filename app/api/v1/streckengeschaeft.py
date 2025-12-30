"""
Streckengeschäft Detection - API Router

FastAPI router for Drop Shipment / Triangular Transaction Detection endpoints.
Follows established patterns from Mahnwesen and customer/supplier navigation.
"""

import structlog
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

from app.api.dependencies import (
    get_current_user,
    get_db,
    verify_document_ownership,
    check_rate_limit,
    check_batch_rate_limit,
    check_datev_export_rate_limit,
    RateLimitDependency,
)
from app.db.models import User, Document, DropShipmentClassification
from sqlalchemy import select


# =============================================================================
# RATE LIMIT CONFIGURATION
# =============================================================================

# Higher rate limit for read operations (100/hour)
check_read_rate_limit = RateLimitDependency(
    requests_per_hour=100,
    key_prefix="streckengeschaeft_read"
)


# =============================================================================
# SECURITY HELPERS
# =============================================================================

async def verify_classification_ownership(
    classification_id: UUID,
    current_user: User,
    session: AsyncSession,
) -> DropShipmentClassification:
    """
    Verify user owns the classification via document ownership.

    Raises:
        HTTPException 404: Classification not found
        HTTPException 403: Access denied (user doesn't own the document)

    Returns:
        The classification if ownership is verified
    """
    # Get classification
    classification = await session.get(DropShipmentClassification, classification_id)
    if not classification:
        raise HTTPException(status_code=404, detail="Klassifikation nicht gefunden")

    # Check if soft-deleted
    if classification.is_deleted:
        raise HTTPException(status_code=404, detail="Klassifikation nicht gefunden")

    # Get document and verify ownership
    document = await session.get(Document, classification.document_id)
    if not document or document.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    return classification


async def verify_classification_ids_ownership(
    classification_ids: list[UUID],
    current_user: User,
    session: AsyncSession,
) -> None:
    """
    Verify user owns ALL classification IDs via document ownership.

    Raises:
        HTTPException 403: Access denied if ANY ID doesn't belong to user
        HTTPException 404: If ANY classification not found
    """
    for classification_id in classification_ids:
        await verify_classification_ownership(classification_id, current_user, session)


from app.services.streckengeschaeft import (
    DropShipmentClassificationService,
    DropShipmentDetectionService,
    DatevExportService,
    VatIdValidationService,
)
from starlette.responses import JSONResponse
from app.services.streckengeschaeft.exceptions import (
    DropShipmentError,
    ClassificationNotFoundError,
    DocumentNotFoundError,
    AccessDeniedError,
    ValidationConflictError,
    DatevExportError,
    ViesServiceError,
    InvalidVatIdError,
    BulkOperationError,
    ProofDocumentError,
    ClassificationAlreadyExistsError,
)

router = APIRouter(
    prefix="/streckengeschaeft",
    tags=["Streckengeschäft Detection"],
)


# =============================================================================
# PYDANTIC MODELS - Request/Response
# =============================================================================

class ClassifyDocumentRequest(BaseModel):
    """Request to classify a single document."""
    document_id: UUID
    force_reclassify: bool = False
    skip_validation: bool = False


class BulkClassifyRequest(BaseModel):
    """Request to classify multiple documents."""
    document_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Document IDs to classify (1-100)"
    )
    force_reclassify: bool = False
    skip_low_confidence: bool = False

    @field_validator('document_ids')
    @classmethod
    def validate_no_duplicates(cls, v: list[UUID]) -> list[UUID]:
        if len(v) != len(set(v)):
            raise ValueError("Doppelte Dokument-IDs sind nicht erlaubt")
        return v


class ValidateClassificationRequest(BaseModel):
    """Request to manually validate/override a classification."""
    classification_id: UUID
    validated_transaction_type: str = Field(
        ...,
        pattern="^(standard|drop_shipment|triangular_eu|chain_transaction|unknown)$",
        description="Transaction type (standard, drop_shipment, triangular_eu, chain_transaction, unknown)"
    )
    validated_company_role: str = Field(
        ...,
        pattern="^(seller|intermediate|buyer|not_applicable)$",
        description="Company role in transaction"
    )
    validated_vat_category: str = Field(
        ...,
        pattern="^(standard_de|triangular_middle|intra_community|not_applicable)$",
        description="VAT category"
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Reason for validation override (max 500 characters)"
    )


class DatevExportRequest(BaseModel):
    """Request for DATEV export."""
    classification_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Classification IDs to export (1-500)"
    )
    kontenrahmen: str = Field(..., pattern="^SKR0[34]$")
    include_zm_data: bool = True
    export_format: str = Field(default="extf", pattern="^(csv|extf)$")

    @field_validator('classification_ids')
    @classmethod
    def validate_no_duplicates(cls, v: list[UUID]) -> list[UUID]:
        if len(v) != len(set(v)):
            raise ValueError("Doppelte Klassifikations-IDs sind nicht erlaubt")
        return v


class VatIdValidationRequest(BaseModel):
    """Request to validate a VAT ID via VIES."""
    vat_id: str = Field(..., min_length=8, max_length=20)
    requester_vat_id: Optional[str] = None


class ClassificationFilterParams(BaseModel):
    """Filter parameters for classification list."""
    transaction_types: Optional[list[str]] = None
    confidence_levels: Optional[list[str]] = None
    is_validated: Optional[bool] = None
    zm_relevant: Optional[bool] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    customer_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None


# =============================================================================
# CLASSIFICATION ENDPOINTS
# =============================================================================

@router.post("/classify")
async def classify_document(
    request: ClassifyDocumentRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_rate_limit),
):
    """
    Classify a single document for drop shipment / triangular transaction.

    Analyzes the document using the detection cascade:
    1. Check for definitive ERP indicators (TAS, §25b reference)
    2. Analyze party addresses and VAT IDs
    3. Check for three EU countries (triangular)
    4. Analyze positions for mixed invoices
    5. Validate document chain completeness

    Returns classification result with confidence score and suggested actions.
    """
    logger.info(
        "classification_requested",
        document_id=str(request.document_id),
        user_id=str(current_user.id),
        force_reclassify=request.force_reclassify,
    )

    # Security: Verify document ownership
    await verify_document_ownership(request.document_id, current_user, session)

    service = DropShipmentDetectionService(session)

    try:
        result = await service.classify_document(
            document_id=request.document_id,
            force_reclassify=request.force_reclassify,
            user_id=current_user.id,
        )

        logger.info(
            "classification_success",
            document_id=str(request.document_id),
            classification_id=str(result.classification.id) if result.classification else None,
            confidence_level=result.classification.confidence_level if result.classification else None,
            transaction_type=result.classification.transaction_type if result.classification else None,
            user_id=str(current_user.id),
        )

        return {
            "success": True,
            "classification": result.classification,
            "positions": result.positions,
            "parties": result.parties,
            "proof_documents": result.proof_documents,
            "suggested_actions": result.suggested_actions,
        }

    except DocumentNotFoundError as e:
        logger.warning("classification_document_not_found", document_id=str(request.document_id), error=str(e))
        raise HTTPException(status_code=404, detail=e.user_message)
    except ClassificationAlreadyExistsError as e:
        logger.warning("classification_already_exists", document_id=str(request.document_id), error_code=e.error_code)
        raise HTTPException(status_code=409, detail=e.user_message)
    except DropShipmentError as e:
        logger.warning("classification_error", document_id=str(request.document_id), error_code=e.error_code)
        raise HTTPException(status_code=400, detail=e.user_message)
    except Exception as e:
        logger.error(
            "classification_failed",
            document_id=str(request.document_id),
            user_id=str(current_user.id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Klassifikation fehlgeschlagen: {str(e)}")


@router.post("/classify/bulk")
async def bulk_classify_documents(
    request: BulkClassifyRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_batch_rate_limit),
):
    """
    Classify multiple documents in batch.

    Processes documents in parallel with rate limiting.
    Returns summary of successful and failed classifications.
    """
    logger.info(
        "bulk_classification_requested",
        document_count=len(request.document_ids),
        user_id=str(current_user.id),
        force_reclassify=request.force_reclassify,
    )

    # Security: Verify ownership of all documents
    for doc_id in request.document_ids:
        await verify_document_ownership(doc_id, current_user, session)

    service = DropShipmentDetectionService(session)

    try:
        results = await service.bulk_classify(
            document_ids=request.document_ids,
            force_reclassify=request.force_reclassify,
            skip_low_confidence=request.skip_low_confidence,
            user_id=current_user.id,
        )

        logger.info(
            "bulk_classification_complete",
            total=len(request.document_ids),
            successful=len(results.successful),
            failed=len(results.failed),
            manual_required=results.manual_required_count,
            user_id=str(current_user.id),
        )

        # Return 207 Multi-Status if there are partial failures
        if results.failed:
            return JSONResponse(
                status_code=207,
                content={
                    "successful": [
                        {"classification_id": str(r.classification.id)} for r in results.successful
                    ],
                    "failed": results.failed,
                    "summary": {
                        "total": len(request.document_ids),
                        "classified": len(results.successful),
                        "failed": len(results.failed),
                        "manual_required": results.manual_required_count,
                    }
                }
            )

        return {
            "successful": results.successful,
            "failed": results.failed,
            "summary": {
                "total": len(request.document_ids),
                "classified": len(results.successful),
                "failed": len(results.failed),
                "manual_required": results.manual_required_count,
            }
        }

    except BulkOperationError as e:
        logger.warning("bulk_classification_partial_failure", error_code=e.error_code, details=e.details)
        return JSONResponse(status_code=207, content=e.to_dict())
    except DropShipmentError as e:
        logger.error("bulk_classification_error", error_code=e.error_code, exc_info=True)
        raise HTTPException(status_code=400, detail=e.user_message)


@router.get("/classifications")
async def list_classifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    transaction_type: Optional[str] = None,
    confidence_level: Optional[str] = None,
    is_validated: Optional[bool] = None,
    zm_relevant: Optional[bool] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|confidence_score|transaction_type)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_read_rate_limit),  # Security: Rate limit
):
    """
    List classifications with filtering and pagination.

    Security: Only returns classifications owned by the current user.
    """
    service = DropShipmentClassificationService(session)

    filters = ClassificationFilterParams(
        transaction_types=[transaction_type] if transaction_type else None,
        confidence_levels=[confidence_level] if confidence_level else None,
        is_validated=is_validated,
        zm_relevant=zm_relevant,
        date_from=date_from,
        date_to=date_to,
    )

    # Security: Filter by user ownership
    result = await service.list_classifications(
        filters=filters,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        user_id=current_user.id,  # Security: Only user's own classifications
    )

    return {
        "items": result['items'],
        "total": result['total'],
        "page": page,
        "page_size": page_size,
        "has_more": (page * page_size) < result['total'],
    }


@router.get("/classifications/{classification_id}")
async def get_classification(
    classification_id: UUID,
    include_audit_log: bool = Query(False),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_read_rate_limit),  # Security: Rate limit
):
    """Get detailed classification by ID.

    Security: Verifies user owns the classification via document ownership.
    """
    # Security: Verify ownership before accessing
    await verify_classification_ownership(classification_id, current_user, session)

    service = DropShipmentClassificationService(session)

    classification = await service.get_classification_detail(
        classification_id=classification_id,
        include_audit_log=include_audit_log,
    )

    if not classification:
        raise HTTPException(status_code=404, detail="Klassifikation nicht gefunden")

    return classification


@router.patch("/classifications/{classification_id}/validate")
async def validate_classification(
    classification_id: UUID,
    request: ValidateClassificationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_rate_limit),
):
    """Manually validate or override a classification.

    Security: Verifies user owns the classification via document ownership.
    """
    logger.info(
        "validation_requested",
        classification_id=str(classification_id),
        user_id=str(current_user.id),
        new_transaction_type=request.validated_transaction_type,
    )

    # Security: Verify ownership before modifying
    await verify_classification_ownership(classification_id, current_user, session)

    service = DropShipmentClassificationService(session)

    try:
        result = await service.validate_classification(
            classification_id=classification_id,
            transaction_type=request.validated_transaction_type,
            company_role=request.validated_company_role,
            vat_category=request.validated_vat_category,
            reason=request.reason,
            validated_by=current_user.id,
        )

        logger.info(
            "validation_success",
            classification_id=str(classification_id),
            user_id=str(current_user.id),
            transaction_type=request.validated_transaction_type,
        )

        return {
            "success": True,
            "classification": result,
            "message": "Klassifikation erfolgreich validiert",
        }

    except ClassificationNotFoundError as e:
        logger.warning("validation_not_found", classification_id=str(classification_id), error=str(e))
        raise HTTPException(status_code=404, detail=e.user_message)
    except ValidationConflictError as e:
        logger.warning("validation_conflict", classification_id=str(classification_id), error=str(e))
        raise HTTPException(status_code=409, detail=e.user_message)
    except DropShipmentError as e:
        logger.warning("validation_error", classification_id=str(classification_id), error_code=e.error_code)
        raise HTTPException(status_code=400, detail=e.user_message)


# =============================================================================
# PROOF DOCUMENTS & VAT VALIDATION
# =============================================================================

@router.get("/classifications/{classification_id}/proofs")
async def get_proof_documents(
    classification_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_read_rate_limit),  # Security: Rate limit
):
    """Get proof document chain for a classification.

    Security: Verifies user owns the classification via document ownership.
    """
    # Security: Verify ownership before accessing
    await verify_classification_ownership(classification_id, current_user, session)

    service = DropShipmentClassificationService(session)
    proofs = await service.get_proof_documents(classification_id)

    required_proofs = [p for p in proofs if p.proof_type in
                      ('invoice', 'cmr', 'gelangensbestaetigung')]
    complete_count = sum(1 for p in required_proofs if p.is_present and p.is_complete)

    return {
        "classification_id": classification_id,
        "proof_documents": proofs,
        "completeness": {
            "required": len(required_proofs),
            "complete": complete_count,
            "percentage": (complete_count / len(required_proofs) * 100)
                         if required_proofs else 100,
        },
    }


class LinkProofRequest(BaseModel):
    """Request to link a proof document."""
    document_id: UUID
    proof_type: str = Field(..., pattern="^(invoice|cmr|gelangensbestaetigung|delivery_note|customs_declaration|vat_id_proof)$")


@router.post("/classifications/{classification_id}/proofs")
async def link_proof_document(
    classification_id: UUID,
    request: LinkProofRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_rate_limit),
):
    """Link a proof document to a classification.

    Security: Verifies user owns the classification via document ownership.
    """
    logger.info(
        "proof_link_requested",
        classification_id=str(classification_id),
        document_id=str(request.document_id),
        proof_type=request.proof_type,
        user_id=str(current_user.id),
    )

    # Security: Verify ownership before modifying
    await verify_classification_ownership(classification_id, current_user, session)

    service = DropShipmentClassificationService(session)

    try:
        result = await service.link_proof_document(
            classification_id=classification_id,
            document_id=request.document_id,
            proof_type=request.proof_type,
            user_id=current_user.id,
        )

        logger.info(
            "proof_link_success",
            classification_id=str(classification_id),
            document_id=str(request.document_id),
            proof_type=request.proof_type,
        )

        return {
            "success": True,
            "proof_document": result,
            "message": "Belegnachweis erfolgreich verknuepft",
        }
    except ProofDocumentError as e:
        logger.warning("proof_link_error", classification_id=str(classification_id), error=str(e))
        raise HTTPException(status_code=400, detail=e.user_message)
    except DropShipmentError as e:
        raise HTTPException(status_code=400, detail=e.user_message)


@router.delete("/classifications/{classification_id}/proofs/{proof_id}")
async def unlink_proof_document(
    classification_id: UUID,
    proof_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_rate_limit),
):
    """Unlink a proof document from a classification.

    Security: Verifies user owns the classification via document ownership.
    """
    # Security: Verify ownership before modifying
    await verify_classification_ownership(classification_id, current_user, session)

    service = DropShipmentClassificationService(session)

    try:
        await service.unlink_proof_document(
            classification_id=classification_id,
            proof_id=proof_id,
            user_id=current_user.id,
        )
        return {"success": True, "message": "Belegnachweis entfernt"}
    except ProofDocumentError as e:
        logger.warning("proof_unlink_error", classification_id=str(classification_id), proof_id=str(proof_id))
        raise HTTPException(status_code=404, detail=e.user_message)
    except DropShipmentError as e:
        raise HTTPException(status_code=400, detail=e.user_message)


@router.delete("/classifications/{classification_id}")
async def delete_classification(
    classification_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_rate_limit),
):
    """Soft-delete a classification.

    Security: Verifies user owns the classification via document ownership.
    """
    logger.info(
        "classification_delete_requested",
        classification_id=str(classification_id),
        user_id=str(current_user.id),
    )

    # Security: Verify ownership before deleting
    await verify_classification_ownership(classification_id, current_user, session)

    service = DropShipmentClassificationService(session)

    try:
        await service.delete_classification(
            classification_id=classification_id,
            user_id=current_user.id,
        )

        logger.info(
            "classification_delete_success",
            classification_id=str(classification_id),
            user_id=str(current_user.id),
        )

        return {"success": True, "message": "Klassifikation geloescht"}
    except ClassificationNotFoundError as e:
        logger.warning("classification_delete_not_found", classification_id=str(classification_id), error=str(e))
        raise HTTPException(status_code=404, detail=e.user_message)
    except DropShipmentError as e:
        logger.warning("classification_delete_error", classification_id=str(classification_id), error_code=e.error_code)
        raise HTTPException(status_code=400, detail=e.user_message)


@router.post("/vat-id/validate")
async def validate_vat_id(
    request: VatIdValidationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_rate_limit),
):
    """Validate a VAT ID via EU VIES service."""
    service = VatIdValidationService(session)
    
    result = await service.validate_vat_id(
        vat_id=request.vat_id,
        requester_vat_id=request.requester_vat_id,
    )
    
    return {
        "vat_id": request.vat_id,
        "is_valid": result.get('is_valid', False),
        "company_name": result.get('company_name'),
        "country_code": result.get('country_code'),
        "from_cache": result.get('from_cache', False),
    }


# =============================================================================
# DATEV EXPORT & ZM
# =============================================================================

@router.post("/datev/export")
async def export_to_datev(
    request: DatevExportRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_datev_export_rate_limit),
):
    """Export classifications to DATEV format.

    Security: Verifies user owns ALL classification IDs via document ownership.
    """
    logger.info(
        "datev_export_requested",
        classification_count=len(request.classification_ids),
        kontenrahmen=request.kontenrahmen,
        export_format=request.export_format,
        user_id=str(current_user.id),
    )

    # Security: Verify ownership of ALL classification IDs before export
    await verify_classification_ids_ownership(
        request.classification_ids, current_user, session
    )

    service = DatevExportService(session)

    try:
        result = await service.create_export(
            classification_ids=request.classification_ids,
            kontenrahmen=request.kontenrahmen,
            include_zm_data=request.include_zm_data,
            export_format=request.export_format,
            created_by=current_user.id,
        )

        logger.info(
            "datev_export_success",
            export_id=str(result.export_id),
            record_count=result.record_count,
            zm_record_count=result.zm_record_count,
            user_id=str(current_user.id),
        )

        return {
            "success": True,
            "export_id": result.export_id,
            "filename": result.filename,
            "download_url": result.download_url,
            "record_count": result.record_count,
            "zm_record_count": result.zm_record_count,
            "warnings": result.warnings,
        }
    except DatevExportError as e:
        logger.error("datev_export_failed", error_code=e.error_code, user_id=str(current_user.id), exc_info=True)
        raise HTTPException(status_code=500, detail=e.user_message)
    except Exception as e:
        logger.error("datev_export_error", error=str(e), user_id=str(current_user.id), exc_info=True)
        raise HTTPException(status_code=500, detail=f"DATEV-Export fehlgeschlagen: {str(e)}")


@router.get("/zm/summary")
async def get_zm_summary(
    period: str = Query(..., pattern="^\\d{4}-\\d{2}$"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_read_rate_limit),  # Security: Rate limit
):
    """Get ZM summary for a reporting period.

    Security: Only returns ZM data for classifications owned by the current user.
    """
    service = DropShipmentClassificationService(session)
    # Security: Filter by user ownership
    summary = await service.get_zm_summary(period, user_id=current_user.id)

    # Transform to Frontend-compatible format (camelCase, proper types)
    return {
        "period": summary.period,
        "totalAmount": float(summary.total_amount),
        "triangularAmount": float(sum(r.amount for r in summary.records if r.is_triangular)),
        "recordCount": summary.record_count,
        "triangularRecordCount": summary.triangular_count,
        "byCountry": [
            {
                "countryCode": c.country_code,
                "amount": float(c.amount),
                "recordCount": c.record_count,
            }
            for c in summary.by_country
        ],
        "deadline": summary.deadline.isoformat(),
        "isSubmitted": False,  # TODO: Track submission status in DB
        "records": [
            {
                "id": str(r.classification_id),
                "vatId": r.vat_id,
                "countryCode": r.country_code,
                "amount": float(r.amount),
                "isTriangular": r.is_triangular,
                "triangularMarker": "1" if r.is_triangular else None,
                "classificationId": str(r.classification_id),
            }
            for r in summary.records
        ],
    }


@router.get("/zm/records")
async def get_zm_records(
    period: str = Query(..., pattern="^\\d{4}-\\d{2}$"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_read_rate_limit),
):
    """Get ZM records for a reporting period.

    Returns the individual ZM-relevant records for the specified period.
    This endpoint is used by the frontend ZmSummaryCard component.

    Security: Only returns records for classifications owned by the current user.
    """
    service = DropShipmentClassificationService(session)
    # Security: Filter by user ownership (same as zm/summary)
    summary = await service.get_zm_summary(period, user_id=current_user.id)

    return {
        "records": [
            {
                "id": str(r.classification_id),
                "vatId": r.vat_id,
                "countryCode": r.country_code,
                "amount": float(r.amount),
                "isTriangular": r.is_triangular,
                "triangularMarker": "1" if r.is_triangular else None,
                "classificationId": str(r.classification_id),
            }
            for r in summary.records
        ],
        "period": period,
        "total": len(summary.records),
    }


# =============================================================================
# STATISTICS
# =============================================================================

@router.get("/statistics")
async def get_classification_statistics(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_read_rate_limit),  # Security: Rate limit
):
    """Get classification statistics for dashboard.

    Security: Only returns statistics for classifications owned by the current user.
    """
    service = DropShipmentClassificationService(session)
    # Security: Filter by user ownership
    stats = await service.get_statistics(
        date_from=date_from,
        date_to=date_to,
        user_id=current_user.id,
    )
    # Transform to camelCase for frontend compatibility
    return {
        "totalDocuments": stats["total"],
        "byTransactionType": stats["by_transaction_type"],
        "byConfidenceLevel": stats["by_confidence_level"],
        "pendingValidation": stats.get("manual_review_count", 0),
        "zmRelevantCount": stats.get("zm_relevant_count", 0),
        "classifiedToday": stats.get("classified_today", 0),
        "classifiedThisWeek": stats.get("classified_this_week", 0),
        "classifiedThisMonth": stats.get("classified_this_month", 0),
    }

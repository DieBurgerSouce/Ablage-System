# -*- coding: utf-8 -*-
"""
QES/eIDAS Signatur API-Endpoints.

Elektronische Signaturen nach eIDAS-Verordnung:
- Signaturanfragen erstellen und verwalten
- Dokumente signieren und ablehnen
- Signaturen verifizieren
- Audit-Trail abrufen
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.schemas_signature import (
    SignatureRequestCreate,
    SignatureRequestResponse,
    SignatureRequestListResponse,
    SignatureEntryResponse,
    SignEntryRequest,
    RejectSignatureRequest,
    SignatureVerificationResponse,
    SignatureAuditResponse,
)
from app.services.signature.signature_service import (
    SignatureService,
    SignerInfo,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/signatures",
    tags=["Elektronische Signaturen"],
)

# Service-Instanz
_signature_service = SignatureService()


# =============================================================================
# Signaturanfragen
# =============================================================================


@router.post(
    "/requests",
    response_model=SignatureRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Signaturanfrage erstellen",
    description="Erstellt eine neue Signaturanfrage für ein Dokument.",
)
async def create_signature_request(
    body: SignatureRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    company=Depends(require_company),
):
    """Erstellt eine Signaturanfrage mit einem oder mehreren Unterzeichnern."""
    try:
        signers = [
            SignerInfo(
                email=s.email,
                name=s.name,
                user_id=s.user_id,
                signing_order=s.signing_order,
            )
            for s in body.signers
        ]

        result = await _signature_service.create_signature_request(
            db=db,
            document_id=body.document_id,
            company_id=company.id,
            requested_by=current_user.id,
            title=body.title,
            signers=signers,
            signature_level=body.signature_level.value,
            provider=body.provider.value,
            signing_order_required=body.signing_order_required,
            expires_in_days=body.expires_in_days,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Fehler beim Erstellen der Signaturanfrage",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Signaturanfrage"),
        )


@router.get(
    "/requests",
    response_model=SignatureRequestListResponse,
    summary="Signaturanfragen auflisten",
    description="Listet Signaturanfragen mit optionalen Filtern.",
)
async def list_signature_requests(
    page: int = Query(1, ge=1, description="Seite"),
    per_page: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Statusfilter"
    ),
    document_id: Optional[UUID] = Query(
        None, description="Dokument-ID Filter"
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    company=Depends(require_company),
):
    """Listet Signaturanfragen für den aktuellen Mandanten."""
    try:
        items, total = await _signature_service.list_signature_requests(
            db=db,
            company_id=company.id,
            document_id=document_id,
            status=status_filter,
            page=page,
            per_page=per_page,
        )
        return SignatureRequestListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
        )
    except Exception as e:
        logger.error(
            "Fehler beim Auflisten der Signaturanfragen",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Signaturanfragen"),
        )


@router.get(
    "/requests/{request_id}",
    response_model=SignatureRequestResponse,
    summary="Signaturanfrage-Details abrufen",
    description="Ruft Details einer Signaturanfrage ab.",
)
async def get_signature_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    company=Depends(require_company),
):
    """Ruft eine einzelne Signaturanfrage mit Entries ab."""
    result = await _signature_service.get_signature_request(
        db=db,
        request_id=request_id,
        company_id=company.id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signaturanfrage nicht gefunden",
        )
    return result


# =============================================================================
# Signatureinträge
# =============================================================================


@router.post(
    "/entries/{entry_id}/sign",
    response_model=SignatureEntryResponse,
    summary="Dokument signieren",
    description="Signiert ein Dokument für den aktuellen Benutzer.",
)
async def sign_document(
    entry_id: UUID,
    body: SignEntryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    company=Depends(require_company),
):
    """Signiert einen Signatureintrag."""
    try:
        # IP-Adresse extrahieren
        ip_address: Optional[str] = None
        if request.client is not None:
            ip_address = request.client.host

        result = await _signature_service.sign_document(
            db=db,
            entry_id=entry_id,
            company_id=company.id,
            signer_id=current_user.id,
            certificate_issuer=body.certificate_issuer,
            certificate_serial=body.certificate_serial,
            ip_address=ip_address,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Fehler beim Signieren",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Signieren"),
        )


@router.post(
    "/entries/{entry_id}/reject",
    response_model=SignatureEntryResponse,
    summary="Signatur ablehnen",
    description="Lehnt eine Signaturanfrage ab.",
)
async def reject_signature(
    entry_id: UUID,
    body: RejectSignatureRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    company=Depends(require_company),
):
    """Lehnt einen Signatureintrag ab."""
    try:
        ip_address: Optional[str] = None
        if request.client is not None:
            ip_address = request.client.host

        result = await _signature_service.reject_signature(
            db=db,
            entry_id=entry_id,
            company_id=company.id,
            signer_id=current_user.id,
            reason=body.reason,
            ip_address=ip_address,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Fehler beim Ablehnen der Signatur",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Signatur-Ablehnung"),
        )


# =============================================================================
# Verifikation und Audit
# =============================================================================


@router.get(
    "/documents/{document_id}/verify",
    response_model=SignatureVerificationResponse,
    summary="Dokumentsignaturen verifizieren",
    description="Verifiziert alle Signaturen eines Dokuments.",
)
async def verify_document_signatures(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    company=Depends(require_company),
):
    """Verifiziert den Signaturstatus eines Dokuments."""
    try:
        result = await _signature_service.verify_signatures(
            db=db,
            document_id=document_id,
            company_id=company.id,
        )

        if result.is_fully_signed:
            message = (
                f"Dokument vollständig signiert "
                f"({result.completed_signatures}/{result.total_signatures} "
                f"Signaturen)"
            )
        elif result.rejected_signatures > 0:
            message = (
                f"Signatur abgelehnt - {result.rejected_signatures} "
                f"Ablehnungen"
            )
        else:
            message = (
                f"Signaturen ausstehend - "
                f"{result.completed_signatures}/{result.total_signatures} "
                f"abgeschlossen"
            )

        return SignatureVerificationResponse(
            document_id=result.document_id,
            is_fully_signed=result.is_fully_signed,
            total_signatures=result.total_signatures,
            completed_signatures=result.completed_signatures,
            pending_signatures=result.pending_signatures,
            rejected_signatures=result.rejected_signatures,
            message=message,
        )
    except Exception as e:
        logger.error(
            "Fehler bei der Signaturverifikation",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Signaturverifikation"),
        )


@router.get(
    "/requests/{request_id}/audit",
    response_model=List[SignatureAuditResponse],
    summary="Signatur-Audit-Trail abrufen",
    description="Ruft den Audit-Trail einer Signaturanfrage ab.",
)
async def get_signature_audit_trail(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    company=Depends(require_company),
):
    """Ruft den vollständigen Audit-Trail ab."""
    try:
        result = await _signature_service.get_audit_trail(
            db=db,
            request_id=request_id,
            company_id=company.id,
        )
        return result
    except Exception as e:
        logger.error(
            "Fehler beim Abrufen des Audit-Trails",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Audit-Trail"),
        )


@router.get(
    "/pending",
    response_model=List[SignatureEntryResponse],
    summary="Ausstehende Signaturen abrufen",
    description="Ruft alle ausstehenden Signaturen des aktuellen Benutzers ab.",
)
async def get_pending_signatures(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    company=Depends(require_company),
):
    """Listet ausstehende Signaturen des eingeloggten Users."""
    try:
        result = await _signature_service.get_pending_signatures(
            db=db,
            signer_id=current_user.id,
            company_id=company.id,
        )
        return result
    except Exception as e:
        logger.error(
            "Fehler beim Abrufen ausstehender Signaturen",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Ausstehende Signaturen"),
        )

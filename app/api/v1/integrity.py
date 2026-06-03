# -*- coding: utf-8 -*-
"""
Dokument-Integritaet (Hash-Chain) API Endpoints.

REST API für kryptographische Dokumenten-Verifizierung:
- SHA-256 Hash-Status pro Dokument
- Dokumenten-Verifizierung gegen gespeicherte Hashes
- Tägliche Merkle-Baeume mit kryptographischen Beweisen
- Integritaetsberichte für Compliance und Audits

Feinpoliert und durchdacht - Enterprise Document Integrity.
"""

from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.models_integrity import DocumentHash, IntegrityReport
from app.db.schemas_integrity import (
    IntegrityReportRequest,
    IntegrityReportResponse,
    IntegrityStatusResponse,
    IntegrityVerifyResponse,
    MerkleBuildRequest,
    MerkleBuildResponse,
    MerkleProofResponse,
)
from app.services.integrity.document_integrity_service import DocumentIntegrityService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/integrity", tags=["Dokument-Integrität"])

# Service-Instanz
_integrity_service = DocumentIntegrityService()


# =============================================================================
# HASH-STATUS
# =============================================================================


@router.get(
    "/documents/{document_id}/hash",
    response_model=IntegrityStatusResponse,
    summary="Integritaetsstatus eines Dokuments abrufen",
    description="Gibt den SHA-256 Hash und Verifizierungsstatus eines Dokuments zurück.",
)
async def get_document_hash_status(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> IntegrityStatusResponse:
    """Integritaetsstatus eines Dokuments abrufen."""
    try:
        doc_hash = await _integrity_service.get_document_integrity_status(
            db, document_id
        )

        if doc_hash is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kein Integritaets-Hash für dieses Dokument vorhanden",
            )

        # Multi-Tenant-Prüfung
        if doc_hash.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kein Zugriff auf dieses Dokument",
            )

        return IntegrityStatusResponse(
            document_id=doc_hash.document_id,
            file_hash=doc_hash.file_hash,
            hash_algorithm=doc_hash.hash_algorithm,
            file_size_bytes=doc_hash.file_size_bytes,
            computed_at=doc_hash.computed_at,
            verified_at=doc_hash.verified_at,
            verification_status=doc_hash.verification_status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Fehler beim Abrufen des Integritaetsstatus",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Integritaetsstatus"),
        )


# =============================================================================
# VERIFIZIERUNG
# =============================================================================


@router.post(
    "/documents/{document_id}/verify",
    response_model=IntegrityVerifyResponse,
    summary="Dokument-Integritaet verifizieren",
    description="Vergleicht den aktuellen Dateiinhalt mit dem gespeicherten Hash.",
)
async def verify_document(
    document_id: UUID,
    file: UploadFile,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> IntegrityVerifyResponse:
    """Dokument gegen gespeicherten Hash verifizieren."""
    try:
        file_content = await file.read()

        # Gespeicherten Hash laden für Response
        doc_hash = await _integrity_service.get_document_integrity_status(
            db, document_id
        )
        if doc_hash is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kein Integritaets-Hash für dieses Dokument vorhanden",
            )

        # Multi-Tenant-Prüfung
        if doc_hash.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kein Zugriff auf dieses Dokument",
            )

        is_valid, message = await _integrity_service.verify_document(
            db, document_id, file_content
        )

        computed_hash = _integrity_service._compute_sha256(file_content)

        await db.commit()

        return IntegrityVerifyResponse(
            document_id=document_id,
            is_valid=is_valid,
            message=message,
            stored_hash=doc_hash.file_hash,
            computed_hash=computed_hash,
            verified_at=datetime.now(timezone.utc),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Fehler bei Dokument-Verifizierung",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Verifizierung"),
        )


# =============================================================================
# MERKLE-BAUM
# =============================================================================


@router.post(
    "/merkle/build",
    response_model=MerkleBuildResponse,
    summary="Täglichen Merkle-Baum erstellen",
    description="Erstellt den Merkle-Baum für alle Dokument-Hashes eines Tages.",
)
async def build_merkle_tree(
    request: MerkleBuildRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MerkleBuildResponse:
    """Täglichen Merkle-Baum erstellen."""
    try:
        merkle_root = await _integrity_service.build_daily_merkle_tree(
            db, company_id, request.tree_date
        )

        # Anzahl der Dokumente zaehlen
        from sqlalchemy import func as sa_func

        count_stmt = select(sa_func.count(DocumentHash.id)).where(
            and_(
                DocumentHash.company_id == company_id,
                sa_func.date(DocumentHash.computed_at) == request.tree_date,
                DocumentHash.deleted_at.is_(None),
            )
        )
        count_result = await db.execute(count_stmt)
        doc_count = count_result.scalar_one()

        await db.commit()

        return MerkleBuildResponse(
            tree_date=request.tree_date,
            merkle_root=merkle_root,
            document_count=doc_count,
            message=f"Merkle-Baum für {request.tree_date.isoformat()} mit {doc_count} Dokumenten erstellt",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Fehler beim Erstellen des Merkle-Baums",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Merkle-Baum"),
        )


@router.get(
    "/merkle/proof/{document_id}",
    response_model=MerkleProofResponse,
    summary="Merkle-Beweis für Dokument abrufen",
    description="Gibt den kryptographischen Beweis für die Aufnahme eines Dokuments im Merkle-Baum zurück.",
)
async def get_merkle_proof(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MerkleProofResponse:
    """Merkle-Beweis für ein Dokument abrufen."""
    try:
        # DocumentHash laden
        doc_hash = await _integrity_service.get_document_integrity_status(
            db, document_id
        )
        if doc_hash is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kein Integritaets-Hash für dieses Dokument vorhanden",
            )

        # Multi-Tenant-Prüfung
        if doc_hash.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kein Zugriff auf dieses Dokument",
            )

        is_included, proof_path = await _integrity_service.verify_merkle_proof(
            db, doc_hash.id
        )

        # Baum-Datum und Root ermitteln
        from app.db.models_integrity import MerkleTreeNode

        tree_stmt = select(MerkleTreeNode).where(
            and_(
                MerkleTreeNode.document_hash_id == doc_hash.id,
                MerkleTreeNode.level == 0,
            )
        )
        tree_result = await db.execute(tree_stmt)
        leaf = tree_result.scalar_one_or_none()

        tree_date = leaf.tree_date if leaf else date.today()

        # Root-Hash
        merkle_root = ""
        if leaf:
            root_stmt = select(MerkleTreeNode.merkle_root).where(
                and_(
                    MerkleTreeNode.company_id == doc_hash.company_id,
                    MerkleTreeNode.tree_date == leaf.tree_date,
                    MerkleTreeNode.merkle_root.isnot(None),
                )
            )
            root_result = await db.execute(root_stmt)
            merkle_root = root_result.scalar_one_or_none() or ""

        if is_included:
            message = "Dokument ist im Merkle-Baum enthalten - Integritaet bestätigt"
        else:
            message = (
                "Dokument ist nicht im Merkle-Baum enthalten - "
                "kein kryptographischer Beweis verfügbar"
            )

        return MerkleProofResponse(
            document_id=document_id,
            is_included=is_included,
            proof_path=proof_path,
            merkle_root=merkle_root,
            tree_date=tree_date,
            message=message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Fehler beim Abrufen des Merkle-Beweises",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Merkle-Beweis"),
        )


# =============================================================================
# BERICHTE
# =============================================================================


@router.post(
    "/reports/generate",
    response_model=IntegrityReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Integritaetsbericht generieren",
    description="Erstellt einen umfassenden Integritaetsbericht mit Verifizierungsstatistiken.",
)
async def generate_report(
    request: IntegrityReportRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> IntegrityReportResponse:
    """Integritaetsbericht generieren."""
    try:
        report = await _integrity_service.generate_integrity_report(
            db,
            company_id=company_id,
            user_id=current_user.id,
            report_date=request.report_date,
        )

        await db.commit()

        return IntegrityReportResponse(
            id=report.id,
            report_date=report.report_date,
            total_documents=report.total_documents,
            verified_count=report.verified_count,
            tampered_count=report.tampered_count,
            unverified_count=report.unverified_count,
            merkle_root=report.merkle_root,
            generated_at=report.generated_at,
            report_data=report.report_data or {},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Fehler beim Generieren des Integritaetsberichts",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Integritaetsbericht"),
        )


@router.get(
    "/reports/{report_id}",
    response_model=IntegrityReportResponse,
    summary="Integritaetsbericht abrufen",
    description="Gibt einen bestimmten Integritaetsbericht zurück.",
)
async def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> IntegrityReportResponse:
    """Integritaetsbericht abrufen."""
    try:
        stmt = select(IntegrityReport).where(
            and_(
                IntegrityReport.id == report_id,
                IntegrityReport.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        report = result.scalar_one_or_none()

        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integritaetsbericht nicht gefunden",
            )

        return IntegrityReportResponse(
            id=report.id,
            report_date=report.report_date,
            total_documents=report.total_documents,
            verified_count=report.verified_count,
            tampered_count=report.tampered_count,
            unverified_count=report.unverified_count,
            merkle_root=report.merkle_root,
            generated_at=report.generated_at,
            report_data=report.report_data or {},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Fehler beim Abrufen des Integritaetsberichts",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Integritaetsbericht"),
        )


@router.get(
    "/reports",
    response_model=List[IntegrityReportResponse],
    summary="Integritaetsberichte auflisten",
    description="Gibt eine paginierte Liste aller Integritaetsberichte zurück.",
)
async def list_reports(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[IntegrityReportResponse]:
    """Integritaetsberichte auflisten."""
    try:
        offset = (page - 1) * per_page

        stmt = (
            select(IntegrityReport)
            .where(IntegrityReport.company_id == company_id)
            .order_by(IntegrityReport.report_date.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(stmt)
        reports = result.scalars().all()

        return [
            IntegrityReportResponse(
                id=report.id,
                report_date=report.report_date,
                total_documents=report.total_documents,
                verified_count=report.verified_count,
                tampered_count=report.tampered_count,
                unverified_count=report.unverified_count,
                merkle_root=report.merkle_root,
                generated_at=report.generated_at,
                report_data=report.report_data or {},
            )
            for report in reports
        ]

    except Exception as e:
        logger.error(
            "Fehler beim Auflisten der Integritaetsberichte",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Integritaetsberichte"),
        )

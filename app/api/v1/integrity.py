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
from app.db.models import Company, Document, User
from app.middleware.company_context import require_company
from app.db.models_integrity import DocumentHash, IntegrityReport
from app.db.schemas_integrity import (
    ChainProofInfo,
    DocumentProofResponse,
    IntegrityReportRequest,
    IntegrityReportResponse,
    IntegrityStatusResponse,
    IntegrityVerifyResponse,
    MerkleBuildRequest,
    MerkleBuildResponse,
    MerkleProofResponse,
    ProofVerdictEnum,
    TsaProofInfo,
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


@router.post(
    "/documents/{document_id}/prove",
    response_model=DocumentProofResponse,
    summary="Dokument-Integrität live beweisen",
    description=(
        "Lädt das Original direkt aus dem Storage, berechnet den SHA-256-Hash neu "
        "und vergleicht ihn mit der versiegelten Baseline (GoBD-Archiv bzw. "
        "Integritäts-Hash). Prüft zusätzlich die Beweiskette (Audit-Chain) des "
        "Dokuments und — falls vorhanden — den RFC-3161-Zeitstempel. "
        "Kein Datei-Upload nötig."
    ),
)
async def prove_document_integrity(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> DocumentProofResponse:
    """Live-Beweisführung: Storage-Re-Hash + Beweiskette + Zeitstempel.

    Multi-Tenant: require_company setzt den RLS-Context — ohne ihn liefert
    die RLS-Policy auf documents 0 Zeilen und alles endet als 404.
    """
    from app.services.compliance.archive_service import gobd_archive_service
    from app.services.compliance.audit_chain_service import audit_chain_service
    from app.services.storage_service import StorageService

    company_id: UUID = company.id

    try:
        doc_result = await db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = doc_result.scalar_one_or_none()
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument nicht gefunden oder keine Berechtigung",
            )

        # Baselines auflösen: GoBD-Archiv bevorzugt, sonst Integritäts-Hash
        archive = await gobd_archive_service.get_archive_by_document(
            db=db,
            document_id=document_id,
            company_id=company_id,
        )
        doc_hash = await _integrity_service.get_document_integrity_status(
            db, document_id
        )
        if doc_hash is not None and doc_hash.company_id != company_id:
            doc_hash = None

        # Beweiskette dieses Dokuments prüfen (unabhängig von der Baseline)
        chain_result = await audit_chain_service.verify_document_entries(
            db=db,
            company_id=company_id,
            document_id=document_id,
        )
        if chain_result.valid is None:
            chain_message = (
                "Für dieses Dokument liegen noch keine Einträge "
                "in der Beweiskette vor."
            )
        elif chain_result.valid:
            chain_message = (
                f"{chain_result.verified_entries} Protokoll-Einträge geprüft — "
                "Verkettung lückenlos intakt."
            )
        else:
            chain_message = (
                f"Beweiskette beschädigt bei Sequenz {chain_result.broken_at_sequence}: "
                f"{chain_result.error_message}"
            )
        chain_info = ChainProofInfo(
            entries_total=chain_result.total_entries,
            entries_verified=chain_result.verified_entries,
            valid=chain_result.valid,
            broken_at_sequence=chain_result.broken_at_sequence,
            first_entry_at=chain_result.first_entry_at,
            last_entry_at=chain_result.last_entry_at,
            message=chain_message,
        )

        verified_at = datetime.now(timezone.utc)

        # Ehrlicher Zustand: keine Baseline — nichts zu beweisen
        if archive is None and doc_hash is None:
            await db.commit()
            return DocumentProofResponse(
                document_id=document_id,
                verdict=ProofVerdictEnum.NO_BASELINE,
                file_hash_matches=None,
                baseline_source=None,
                stored_hash=None,
                computed_hash=None,
                archived_at=None,
                archive_id=None,
                chain=chain_info,
                tsa=TsaProofInfo(
                    present=False,
                    valid=None,
                    message=(
                        "Kein qualifizierter Zeitstempel vorhanden — "
                        "wird bei der Archivierung erstellt."
                    ),
                ),
                verified_at=verified_at,
                message_de=(
                    "Für dieses Dokument existiert noch keine versiegelte "
                    "Archiv-Baseline. Die Versiegelung erfolgt automatisch bei der "
                    "nächsten GoBD-Archivierung oder kann von einem Administrator "
                    "sofort ausgelöst werden."
                ),
            )

        if not document.file_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dokument hat keinen gespeicherten Dateipfad",
            )

        storage = StorageService()
        if not storage.available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage-Service nicht verfügbar",
            )

        try:
            document_content = await storage.download_document(document.file_path)
        except Exception as e:
            logger.error(
                "prove_storage_download_failed",
                document_id=str(document_id),
                file_path=document.file_path,
                **safe_error_log(e),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=safe_error_detail(e, "Laden des Dokuments aus dem Storage"),
            )

        tsa_present = False
        tsa_valid: Optional[bool] = None
        archived_at: Optional[datetime] = None
        archive_id: Optional[UUID] = None

        if archive is not None:
            tsa_present = bool(archive.signature_certificate)
            archived_at = archive.archived_at
            archive_id = archive.id
            check_result = await gobd_archive_service.verify_archive_integrity(
                db=db,
                archive_id=archive.id,
                company_id=company_id,
                document_content=document_content,
                triggered_by_id=current_user.id,
                check_type="manual",
            )
            file_hash_matches = check_result.hash_match
            stored_hash = check_result.expected_hash
            computed_hash = check_result.actual_hash
            tsa_valid = check_result.tsa_verified
            baseline_source = "archiv"
        else:
            assert doc_hash is not None  # oben geprüft
            file_hash_matches, _ = await _integrity_service.verify_document(
                db, document_id, document_content
            )
            stored_hash = doc_hash.file_hash
            computed_hash = _integrity_service._compute_sha256(document_content)
            archived_at = doc_hash.computed_at
            baseline_source = "integritaets_hash"

        await db.commit()

        if not tsa_present:
            tsa_message = (
                "Kein qualifizierter RFC-3161-Zeitstempel vorhanden — die "
                "Versiegelung basiert auf der internen Hash-Beweiskette."
            )
        elif tsa_valid is True:
            tsa_message = "Qualifizierter RFC-3161-Zeitstempel erfolgreich verifiziert."
        elif tsa_valid is False:
            tsa_message = (
                "RFC-3161-Zeitstempel konnte NICHT verifiziert werden — "
                "bitte Administrator informieren."
            )
        else:
            tsa_message = (
                "RFC-3161-Zeitstempel vorhanden, Prüfung derzeit nicht möglich."
            )

        chain_broken = chain_info.valid is False
        if file_hash_matches and not chain_broken:
            verdict = ProofVerdictEnum.VERIFIED
            datum = archived_at.strftime("%d.%m.%Y") if archived_at else "der Versiegelung"
            message_de = (
                f"Dieses Dokument ist seit dem {datum} nachweislich unverändert. "
                "Der aktuelle Dateiinhalt stimmt Bit für Bit mit dem versiegelten "
                "SHA-256-Hash überein."
            )
            if chain_info.entries_total > 0:
                message_de += (
                    f" Alle {chain_info.entries_verified} Einträge der "
                    "Beweiskette sind intakt."
                )
        elif file_hash_matches and chain_broken:
            verdict = ProofVerdictEnum.TAMPERED
            message_de = (
                "Der Dateiinhalt stimmt mit der versiegelten Baseline überein, "
                "aber die Beweiskette (Audit-Protokoll) ist beschädigt "
                f"(Sequenz {chain_info.broken_at_sequence}). Bitte umgehend den "
                "Administrator informieren."
            )
        else:
            verdict = ProofVerdictEnum.TAMPERED
            message_de = (
                "Integritätsprüfung FEHLGESCHLAGEN: Der aktuelle Dateiinhalt "
                "stimmt NICHT mit dem versiegelten Archiv-Hash überein — mögliche "
                "Manipulation! Dokument nicht weiterverwenden, umgehend den "
                "Administrator informieren und das Original aus dem Backup "
                "wiederherstellen."
            )
            logger.error(
                "document_proof_failed",
                document_id=str(document_id),
                baseline_source=baseline_source,
                chain_valid=chain_info.valid,
            )

        return DocumentProofResponse(
            document_id=document_id,
            verdict=verdict,
            file_hash_matches=file_hash_matches,
            baseline_source=baseline_source,
            stored_hash=stored_hash,
            computed_hash=computed_hash,
            archived_at=archived_at,
            archive_id=archive_id,
            chain=chain_info,
            tsa=TsaProofInfo(present=tsa_present, valid=tsa_valid, message=tsa_message),
            verified_at=verified_at,
            message_de=message_de,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Fehler bei der Dokument-Beweisführung",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Beweisführung"),
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

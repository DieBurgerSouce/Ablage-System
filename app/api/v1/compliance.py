"""GoBD Compliance API Endpoints.

Stellt REST-Endpoints fuer GoBD-konforme Dokumentenverarbeitung bereit:
- Archivierung
- Aufbewahrungsfristen
- Audit-Chain
- Integritaetspruefungen

GoBD = Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung
       von Buechern, Aufzeichnungen und Unterlagen in elektronischer
       Form sowie zum Datenzugriff
"""

import uuid
from datetime import date
from typing import Optional, List

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import User, Document
from app.db.models.gobd import (
    AuditChainEventType,
    RetentionPolicy,
    RetentionDeletionRequest,
)
from app.services.compliance import (
    audit_chain_service,
    retention_service,
    gobd_archive_service,
)
from app.services.compliance.audit_chain_service import ChainEntry
from app.services.gobd_compliance_service import gobd_compliance_service
from app.services.storage_service import StorageService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/compliance", tags=["GoBD Compliance"])


# ================== Pydantic Schemas ==================

class ArchiveDocumentRequest(BaseModel):
    """Request zum Archivieren eines Dokuments."""
    document_id: uuid.UUID
    category: str = Field(..., description="Dokumentkategorie fuer Aufbewahrungsfrist")
    document_date: Optional[date] = Field(None, description="Datum des Dokuments")
    use_tsa: bool = Field(False, description="RFC 3161 Zeitstempel anfordern")
    metadata: Optional[dict] = Field(None, description="Optionale Metadaten")


class ArchiveDocumentResponse(BaseModel):
    """Response nach Archivierung."""
    archive_id: uuid.UUID
    document_id: uuid.UUID
    content_hash: str
    hash_algorithm: str
    retention_expires_at: date
    tsa_timestamp: Optional[str] = None


class IntegrityCheckRequest(BaseModel):
    """Request fuer Integritaetspruefung."""
    archive_id: uuid.UUID


class IntegrityCheckResponse(BaseModel):
    """Response der Integritaetspruefung."""
    archive_id: uuid.UUID
    status: str
    hash_match: bool
    expected_hash: str
    actual_hash: Optional[str]
    error_message: Optional[str] = None
    duration_ms: float


class AuditChainEntryResponse(BaseModel):
    """Response fuer einen Audit-Chain Eintrag."""
    id: uuid.UUID
    sequence_number: int
    event_type: str
    event_data: dict
    document_id: Optional[uuid.UUID]
    combined_hash: str
    created_at: str
    is_verified: bool


class ChainVerificationResponse(BaseModel):
    """Response der Ketten-Verifikation."""
    status: str
    total_entries: int
    verified_entries: int
    broken_at_sequence: Optional[int] = None
    error_message: Optional[str] = None
    verification_time_ms: float


class ChainStatisticsResponse(BaseModel):
    """Statistiken der Audit-Chain."""
    total_entries: int
    by_event_type: dict
    unverified_count: int
    tsa_timestamped_count: int
    first_entry: dict
    last_entry: dict


class RetentionAlertResponse(BaseModel):
    """Alert fuer ablaufende Aufbewahrungsfrist."""
    archive_id: uuid.UUID
    document_id: uuid.UUID
    category: str
    expires_at: date
    days_remaining: int
    level: str


class RetentionStatsResponse(BaseModel):
    """Statistiken zu Aufbewahrungsfristen."""
    total_archived: int
    by_category: dict
    expiring_30_days: int
    expiring_90_days: int
    expiring_180_days: int
    expired: int


class DeletionRequestCreate(BaseModel):
    """Request zum Erstellen einer Loeschanfrage."""
    archive_id: uuid.UUID
    reason: str = Field(..., min_length=10, description="Begruendung fuer die Loeschung")


class DeletionRequestResponse(BaseModel):
    """Response einer Loeschanfrage."""
    id: uuid.UUID
    archive_id: uuid.UUID
    status: str
    reason: str
    requested_at: str
    retention_expired_at: str


class DeletionApprovalRequest(BaseModel):
    """Request zum Genehmigen/Ablehnen einer Loeschanfrage."""
    comment: Optional[str] = None


class ComplianceReportResponse(BaseModel):
    """Vollstaendiger GoBD-Compliance-Bericht."""
    report_id: str
    company_id: str
    report_date: str
    generated_at: str
    overall_status: str
    overall_score: float
    score_description: str
    summary: dict
    recommendations: List[dict]
    legal_basis: List[dict]
    details: Optional[dict] = None


class RetentionPolicyCreate(BaseModel):
    """Request zum Erstellen einer Aufbewahrungsrichtlinie."""
    category: str
    retention_years: int = Field(..., ge=1, le=30)
    legal_basis: Optional[str] = None
    warning_days_before: int = Field(180, ge=30, le=365)
    critical_days_before: int = Field(30, ge=7, le=90)
    require_approval_for_delete: bool = True


class RetentionPolicyResponse(BaseModel):
    """Response einer Aufbewahrungsrichtlinie."""
    id: uuid.UUID
    document_category: str
    retention_years: int
    legal_basis: Optional[str]
    warning_days_before: int
    critical_days_before: int
    require_approval_for_delete: bool
    is_active: bool


class VerfahrensdokumentationResponse(BaseModel):
    """GoBD-konforme Verfahrensdokumentation."""
    document_id: str
    company_id: str
    generated_at: str
    valid_from: str
    version: str
    legal_basis: List[dict]
    system_description: dict
    system_architecture: dict
    process_descriptions: List[dict]
    user_role_documentation: List[dict]
    change_history: List[dict]


class VerfahrensdokumentationPDFResponse(BaseModel):
    """PDF-Export der Verfahrensdokumentation."""
    document_id: str
    filename: str
    content_type: str
    file_size: int
    download_url: str


# ================== Compliance Report ==================

@router.get("/report", response_model=ComplianceReportResponse)
async def generate_compliance_report(
    include_details: bool = Query(True, description="Details einschliessen"),
    report_date: Optional[date] = Query(None, description="Stichtag"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generiert einen GoBD-Compliance-Bericht.

    Der Bericht bewertet:
    - Archivierungsrate
    - Aufbewahrungsfristen-Compliance
    - Audit-Trail-Vollstaendigkeit
    - Integritaetspruefungen

    Ergebnis: Score 0-100 mit Empfehlungen.
    """
    report = await gobd_compliance_service.generate_compliance_report(
        db=db,
        company_id=current_user.company_id,
        report_date=report_date,
        include_details=include_details,
    )
    return ComplianceReportResponse(**report)


@router.get("/quick-status")
async def get_quick_compliance_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Schneller Compliance-Status fuer Dashboard-Widgets."""
    return await gobd_compliance_service.get_quick_compliance_status(
        db=db,
        company_id=current_user.company_id,
    )


# ================== Archive Endpoints ==================

@router.post("/archive", response_model=ArchiveDocumentResponse, status_code=status.HTTP_201_CREATED)
async def archive_document(
    request: ArchiveDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Archiviert ein Dokument GoBD-konform.

    Erstellt:
    - SHA-256 Hash-Signatur
    - Aufbewahrungsfrist basierend auf Kategorie
    - Optional: RFC 3161 Zeitstempel
    - Audit-Chain Eintrag
    """
    # Lade Dokument aus Datenbank um Storage-Pfad zu erhalten
    result = await db.execute(
        select(Document).where(
            Document.id == request.document_id,
            Document.company_id == current_user.company_id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden oder keine Berechtigung",
        )

    if not document.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dokument hat keinen gespeicherten Dateipfad",
        )

    # Lade echten Dokument-Inhalt aus MinIO Storage
    try:
        storage = StorageService()
        if not storage.available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage-Service nicht verfuegbar",
            )

        document_content = await storage.download_document(document.file_path)

        logger.info(
            "document_content_loaded_for_archive",
            document_id=str(request.document_id),
            file_path=document.file_path,
            content_size=len(document_content),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "storage_download_failed",
            document_id=str(request.document_id),
            file_path=document.file_path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Laden des Dokuments aus dem Storage: {str(e)}",
        )

    try:
        result = await gobd_archive_service.archive_document(
            db=db,
            document_id=request.document_id,
            company_id=current_user.company_id,
            category=request.category,
            document_content=document_content,
            document_date=request.document_date,
            archived_by_id=current_user.id,
            metadata=request.metadata,
            use_tsa=request.use_tsa,
        )

        await db.commit()

        logger.info(
            "document_archived_gobd",
            document_id=str(request.document_id),
            archive_id=str(result.archive_id),
            content_hash=result.content_hash[:16] + "...",
            use_tsa=request.use_tsa,
        )

        return ArchiveDocumentResponse(
            archive_id=result.archive_id,
            document_id=result.document_id,
            content_hash=result.content_hash,
            hash_algorithm=result.hash_algorithm,
            retention_expires_at=result.retention_expires_at,
            tsa_timestamp=result.tsa_timestamp.isoformat() if result.tsa_timestamp else None,
        )

    except Exception as e:
        await db.rollback()
        logger.error(
            "archive_document_failed",
            document_id=str(request.document_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/archive/{document_id}")
async def get_document_archive(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt die Archiv-Informationen fuer ein Dokument."""
    archive = await gobd_archive_service.get_archive_by_document(
        db=db,
        document_id=document_id,
        company_id=current_user.company_id,
    )

    if not archive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein Archiv fuer dieses Dokument gefunden",
        )

    return {
        "id": str(archive.id),
        "document_id": str(archive.document_id),
        "content_hash": archive.content_hash,
        "hash_algorithm": archive.hash_algorithm,
        "retention_category": archive.retention_category,
        "retention_years": archive.retention_years,
        "retention_expires_at": archive.retention_expires_at.isoformat(),
        "is_verified": archive.is_verified,
        "last_verification_at": archive.last_verification_at.isoformat() if archive.last_verification_at else None,
        "archived_at": archive.archived_at.isoformat(),
    }


@router.get("/archive/statistics")
async def get_archive_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt Archivierungs-Statistiken."""
    return await gobd_archive_service.get_archive_statistics(
        db=db,
        company_id=current_user.company_id,
    )


@router.post("/archive/verify", response_model=IntegrityCheckResponse)
async def verify_archive_integrity(
    request: IntegrityCheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifiziert die Integritaet eines archivierten Dokuments.

    Vergleicht den gespeicherten Hash mit dem aktuellen Hash.
    Bei Abweichung: KRITISCHER FEHLER - moegliche Manipulation!
    """
    from app.db.models.gobd import DocumentArchive

    # Lade Archiv-Informationen um document_id zu erhalten
    archive_result = await db.execute(
        select(DocumentArchive).where(
            DocumentArchive.id == request.archive_id,
            DocumentArchive.company_id == current_user.company_id,
        )
    )
    archive = archive_result.scalar_one_or_none()

    if not archive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archiv nicht gefunden oder keine Berechtigung",
        )

    # Lade Dokument um Storage-Pfad zu erhalten
    doc_result = await db.execute(
        select(Document).where(
            Document.id == archive.document_id,
            Document.company_id == current_user.company_id,
        )
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zugehoeriges Dokument nicht gefunden",
        )

    if not document.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dokument hat keinen gespeicherten Dateipfad",
        )

    # Lade echten Dokument-Inhalt aus MinIO Storage
    try:
        storage = StorageService()
        if not storage.available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage-Service nicht verfuegbar",
            )

        document_content = await storage.download_document(document.file_path)

        logger.info(
            "document_content_loaded_for_verification",
            archive_id=str(request.archive_id),
            document_id=str(archive.document_id),
            content_size=len(document_content),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "storage_download_failed_verification",
            archive_id=str(request.archive_id),
            file_path=document.file_path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Laden des Dokuments aus dem Storage: {str(e)}",
        )

    try:
        result = await gobd_archive_service.verify_archive_integrity(
            db=db,
            archive_id=request.archive_id,
            company_id=current_user.company_id,
            document_content=document_content,
            triggered_by_id=current_user.id,
            check_type="manual",
        )

        await db.commit()

        if result.hash_match:
            logger.info(
                "integrity_check_passed",
                archive_id=str(request.archive_id),
                duration_ms=result.duration_ms,
            )
        else:
            logger.error(
                "integrity_check_failed_hash_mismatch",
                archive_id=str(request.archive_id),
                expected_hash=result.expected_hash[:16] + "...",
                actual_hash=result.actual_hash[:16] + "..." if result.actual_hash else None,
            )

        return IntegrityCheckResponse(
            archive_id=result.archive_id,
            status=result.status.value,
            hash_match=result.hash_match,
            expected_hash=result.expected_hash,
            actual_hash=result.actual_hash,
            error_message=result.error_message,
            duration_ms=result.duration_ms,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/archive/failed-verifications")
async def get_failed_verifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt alle Archive mit fehlgeschlagener Integritaetspruefung.

    KRITISCH: Diese Liste sollte immer leer sein!
    """
    archives = await gobd_archive_service.get_archives_with_failed_verification(
        db=db,
        company_id=current_user.company_id,
    )

    return {
        "count": len(archives),
        "archives": [
            {
                "id": str(a.id),
                "document_id": str(a.document_id),
                "content_hash": a.content_hash[:16] + "...",
                "verification_failed_reason": a.verification_failed_reason,
            }
            for a in archives
        ],
    }


# ================== Audit Chain Endpoints ==================

@router.get("/audit-chain", response_model=List[AuditChainEntryResponse])
async def get_audit_chain_entries(
    document_id: Optional[uuid.UUID] = Query(None, description="Filter nach Dokument"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt Eintraege der Audit-Chain.

    Optional gefiltert nach Dokument.
    """
    if document_id:
        entries = await audit_chain_service.get_entries_by_document(
            db=db,
            company_id=current_user.company_id,
            document_id=document_id,
            limit=limit,
        )
    else:
        # Hole allgemeine Eintraege (neueste zuerst)
        from sqlalchemy import select, desc
        from app.db.models.gobd import AuditChainEntry

        result = await db.execute(
            select(AuditChainEntry)
            .where(AuditChainEntry.company_id == current_user.company_id)
            .order_by(desc(AuditChainEntry.sequence_number))
            .offset(offset)
            .limit(limit)
        )
        entries = result.scalars().all()

    return [
        AuditChainEntryResponse(
            id=e.id,
            sequence_number=e.sequence_number,
            event_type=e.event_type,
            event_data=e.event_data,
            document_id=e.document_id,
            combined_hash=e.combined_hash[:16] + "...",
            created_at=e.created_at.isoformat(),
            is_verified=e.is_verified,
        )
        for e in entries
    ]


@router.get("/audit-chain/{sequence_number}", response_model=AuditChainEntryResponse)
async def get_audit_chain_entry(
    sequence_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt einen spezifischen Audit-Chain Eintrag nach Sequenznummer."""
    entry = await audit_chain_service.get_entry_by_sequence(
        db=db,
        company_id=current_user.company_id,
        sequence_number=sequence_number,
    )

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kein Eintrag mit Sequenznummer {sequence_number} gefunden",
        )

    return AuditChainEntryResponse(
        id=entry.id,
        sequence_number=entry.sequence_number,
        event_type=entry.event_type,
        event_data=entry.event_data,
        document_id=entry.document_id,
        combined_hash=entry.combined_hash,
        created_at=entry.created_at.isoformat(),
        is_verified=entry.is_verified,
    )


@router.post("/audit-chain/verify", response_model=ChainVerificationResponse)
async def verify_audit_chain(
    start_sequence: int = Query(1, ge=1, description="Start-Sequenznummer"),
    end_sequence: Optional[int] = Query(None, description="End-Sequenznummer"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifiziert die Integritaet der Audit-Chain.

    Prueft alle Hash-Verkettungen auf Korrektheit.
    Bei Bruch: Die Kette wurde manipuliert!
    """
    result = await audit_chain_service.verify_chain(
        db=db,
        company_id=current_user.company_id,
        start_sequence=start_sequence,
        end_sequence=end_sequence,
    )

    await db.commit()

    return ChainVerificationResponse(
        status=result.status.value,
        total_entries=result.total_entries,
        verified_entries=result.verified_entries,
        broken_at_sequence=result.broken_at_sequence,
        error_message=result.error_message,
        verification_time_ms=result.verification_time_ms,
    )


@router.get("/audit-chain/statistics", response_model=ChainStatisticsResponse)
async def get_audit_chain_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt Statistiken ueber die Audit-Chain."""
    stats = await audit_chain_service.get_chain_statistics(
        db=db,
        company_id=current_user.company_id,
    )
    return ChainStatisticsResponse(**stats)


# ================== Retention Endpoints ==================

@router.get("/retention/alerts", response_model=List[RetentionAlertResponse])
async def get_retention_alerts(
    days_ahead: int = Query(180, ge=1, le=365, description="Tage voraus pruefen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt Warnungen fuer bald ablaufende Aufbewahrungsfristen."""
    alerts = await retention_service.get_expiring_archives(
        db=db,
        company_id=current_user.company_id,
        days_ahead=days_ahead,
    )

    return [
        RetentionAlertResponse(
            archive_id=a.archive_id,
            document_id=a.document_id,
            category=a.category,
            expires_at=a.expires_at,
            days_remaining=a.days_remaining,
            level=a.level.value,
        )
        for a in alerts
    ]


@router.get("/retention/statistics", response_model=RetentionStatsResponse)
async def get_retention_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt Statistiken zu Aufbewahrungsfristen."""
    stats = await retention_service.get_retention_statistics(
        db=db,
        company_id=current_user.company_id,
    )

    return RetentionStatsResponse(
        total_archived=stats.total_archived,
        by_category=stats.by_category,
        expiring_30_days=stats.expiring_30_days,
        expiring_90_days=stats.expiring_90_days,
        expiring_180_days=stats.expiring_180_days,
        expired=stats.expired,
    )


@router.get("/retention/expired")
async def get_expired_archives(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt alle Archive mit abgelaufener Aufbewahrungsfrist."""
    archives = await retention_service.get_expired_archives(
        db=db,
        company_id=current_user.company_id,
    )

    return {
        "count": len(archives),
        "archives": [
            {
                "id": str(a.id),
                "document_id": str(a.document_id),
                "category": a.retention_category,
                "expired_at": a.retention_expires_at.isoformat(),
            }
            for a in archives
        ],
    }


# ================== Retention Policy Endpoints ==================

@router.get("/retention/policies", response_model=List[RetentionPolicyResponse])
async def get_retention_policies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt alle Aufbewahrungsrichtlinien."""
    from sqlalchemy import select

    result = await db.execute(
        select(RetentionPolicy)
        .where(RetentionPolicy.company_id == current_user.company_id)
        .order_by(RetentionPolicy.document_category)
    )
    policies = result.scalars().all()

    return [
        RetentionPolicyResponse(
            id=p.id,
            document_category=p.document_category,
            retention_years=p.retention_years,
            legal_basis=p.legal_basis,
            warning_days_before=p.warning_days_before,
            critical_days_before=p.critical_days_before,
            require_approval_for_delete=p.require_approval_for_delete,
            is_active=p.is_active,
        )
        for p in policies
    ]


@router.post("/retention/policies", response_model=RetentionPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_retention_policy(
    request: RetentionPolicyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Erstellt eine neue Aufbewahrungsrichtlinie."""
    try:
        policy = await retention_service.create_retention_policy(
            db=db,
            company_id=current_user.company_id,
            category=request.category,
            retention_years=request.retention_years,
            legal_basis=request.legal_basis,
            warning_days_before=request.warning_days_before,
            critical_days_before=request.critical_days_before,
            require_approval_for_delete=request.require_approval_for_delete,
            created_by_id=current_user.id,
        )

        await db.commit()

        return RetentionPolicyResponse(
            id=policy.id,
            document_category=policy.document_category,
            retention_years=policy.retention_years,
            legal_basis=policy.legal_basis,
            warning_days_before=policy.warning_days_before,
            critical_days_before=policy.critical_days_before,
            require_approval_for_delete=policy.require_approval_for_delete,
            is_active=policy.is_active,
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/retention/policies/initialize")
async def initialize_retention_policies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initialisiert Standard-Aufbewahrungsrichtlinien nach deutschem Recht."""
    policies = await retention_service.initialize_company_policies(
        db=db,
        company_id=current_user.company_id,
        created_by_id=current_user.id,
    )

    await db.commit()

    return {
        "message": "Aufbewahrungsrichtlinien initialisiert",
        "policies_created": len(policies),
        "categories": [p.document_category for p in policies],
    }


# ================== Deletion Request Endpoints ==================

@router.post("/retention/deletion-requests", response_model=DeletionRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_deletion_request(
    request: DeletionRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Erstellt eine Loeschanfrage fuer ein abgelaufenes Archiv."""
    try:
        deletion_request = await retention_service.request_deletion(
            db=db,
            company_id=current_user.company_id,
            archive_id=request.archive_id,
            reason=request.reason,
            requested_by_id=current_user.id,
        )

        await db.commit()

        return DeletionRequestResponse(
            id=deletion_request.id,
            archive_id=deletion_request.archive_id,
            status=deletion_request.status,
            reason=deletion_request.reason,
            requested_at=deletion_request.requested_at.isoformat(),
            retention_expired_at=deletion_request.retention_expired_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/retention/deletion-requests")
async def get_deletion_requests(
    status_filter: Optional[str] = Query(None, description="Filter nach Status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt alle Loeschanfragen."""
    from sqlalchemy import select

    query = select(RetentionDeletionRequest).where(
        RetentionDeletionRequest.company_id == current_user.company_id
    )

    if status_filter:
        query = query.where(RetentionDeletionRequest.status == status_filter)

    result = await db.execute(query.order_by(RetentionDeletionRequest.requested_at.desc()))
    requests = result.scalars().all()

    return {
        "count": len(requests),
        "requests": [
            {
                "id": str(r.id),
                "archive_id": str(r.archive_id),
                "status": r.status,
                "reason": r.reason,
                "requested_at": r.requested_at.isoformat(),
            }
            for r in requests
        ],
    }


@router.post("/retention/deletion-requests/{request_id}/approve")
async def approve_deletion_request(
    request_id: uuid.UUID,
    request: DeletionApprovalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Genehmigt eine Loeschanfrage."""
    try:
        deletion_request = await retention_service.approve_deletion(
            db=db,
            company_id=current_user.company_id,
            request_id=request_id,
            approved_by_id=current_user.id,
            comment=request.comment,
        )

        await db.commit()

        return {
            "message": "Loeschanfrage genehmigt",
            "request_id": str(deletion_request.id),
            "status": deletion_request.status,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/retention/deletion-requests/{request_id}/reject")
async def reject_deletion_request(
    request_id: uuid.UUID,
    reason: str = Query(..., min_length=10, description="Ablehnungsgrund"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lehnt eine Loeschanfrage ab."""
    try:
        deletion_request = await retention_service.reject_deletion(
            db=db,
            company_id=current_user.company_id,
            request_id=request_id,
            rejected_by_id=current_user.id,
            reason=reason,
        )

        await db.commit()

        return {
            "message": "Loeschanfrage abgelehnt",
            "request_id": str(deletion_request.id),
            "status": deletion_request.status,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ================== Verfahrensdokumentation Endpoints ==================


@router.get("/verfahrensdokumentation", response_model=VerfahrensdokumentationResponse)
async def get_verfahrensdokumentation(
    include_full_history: bool = Query(False, description="Vollstaendige Aenderungshistorie einschliessen"),
    history_limit: int = Query(50, ge=10, le=500, description="Max. Anzahl Historie-Eintraege"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generiert die GoBD-konforme Verfahrensdokumentation.

    Die Verfahrensdokumentation ist ein zentrales Element der GoBD-Compliance
    und beschreibt alle relevanten Prozesse, Systeme und Verantwortlichkeiten.

    Inhalt:
    - Rechtsgrundlagen (§147 AO, §257 HGB, etc.)
    - Systembeschreibung
    - Systemarchitektur
    - Prozessbeschreibungen
    - Benutzer- und Rollendokumentation
    - Aenderungshistorie

    Diese Dokumentation kann als Nachweis gegenueber Pruefern dienen.
    """
    try:
        doc = await gobd_compliance_service.generate_verfahrensdokumentation(
            db=db,
            company_id=current_user.company_id,
            include_full_history=include_full_history,
            history_limit=history_limit,
        )

        return VerfahrensdokumentationResponse(**doc)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler bei der Generierung der Verfahrensdokumentation: {str(e)}",
        )


@router.get("/verfahrensdokumentation/pdf")
async def export_verfahrensdokumentation_pdf(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exportiert die Verfahrensdokumentation als PDF.

    Generiert ein druckbares PDF-Dokument fuer die Vorlage
    bei Steuerberatern, Wirtschaftspruefern oder Finanzamt.

    Das PDF enthaelt:
    - Titelseite mit Firmendaten
    - Inhaltsverzeichnis
    - Alle Sektionen der Verfahrensdokumentation
    - Unterschriftenfelder
    """
    from fastapi.responses import Response
    from app.services.compliance import (
        generate_procedure_documentation,
        DocumentFormat,
    )

    try:
        # Neue Service-Implementation nutzen
        pdf_bytes = await generate_procedure_documentation(
            db=db,
            company_id=current_user.company_id,
            user_id=current_user.id,
            format=DocumentFormat.PDF,
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=verfahrensdokumentation.pdf"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim PDF-Export: {str(e)}",
        )


@router.get("/verfahrensdokumentation/markdown")
async def export_verfahrensdokumentation_markdown(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exportiert die Verfahrensdokumentation als Markdown.

    Ideal fuer Versionskontrolle und interne Dokumentation.
    """
    from fastapi.responses import Response
    from app.services.compliance import (
        generate_procedure_documentation,
        DocumentFormat,
    )

    try:
        md_bytes = await generate_procedure_documentation(
            db=db,
            company_id=current_user.company_id,
            user_id=current_user.id,
            format=DocumentFormat.MARKDOWN,
        )

        return Response(
            content=md_bytes,
            media_type="text/markdown",
            headers={
                "Content-Disposition": "attachment; filename=verfahrensdokumentation.md"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Markdown-Export: {str(e)}",
        )


@router.get("/verfahrensdokumentation/html")
async def export_verfahrensdokumentation_html(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exportiert die Verfahrensdokumentation als HTML.

    Kann im Browser angezeigt oder gedruckt werden.
    """
    from fastapi.responses import HTMLResponse
    from app.services.compliance import (
        generate_procedure_documentation,
        DocumentFormat,
    )

    try:
        html_bytes = await generate_procedure_documentation(
            db=db,
            company_id=current_user.company_id,
            user_id=current_user.id,
            format=DocumentFormat.HTML,
        )

        return HTMLResponse(content=html_bytes.decode("utf-8"))

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim HTML-Export: {str(e)}",
        )


@router.get("/verfahrensdokumentation/steuerberater")
async def get_steuerberater_export(
    zeitraum_von: Optional[date] = Query(None, description="Start des Zeitraums"),
    zeitraum_bis: Optional[date] = Query(None, description="Ende des Zeitraums"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exportiert Daten fuer den Steuerberater-Zugang.

    Stellt alle relevanten Compliance-Daten in einem
    strukturierten Format fuer externe Pruefer bereit.

    Enthaelt:
    - Verfahrensdokumentation (Zusammenfassung)
    - Archivierungsstatistiken
    - Aufbewahrungsfristen-Uebersicht
    - Audit-Trail-Statistiken
    - Integritaetspruefungs-Protokoll
    """
    try:
        # Verfahrensdokumentation (Kurzfassung)
        doc = await gobd_compliance_service.generate_verfahrensdokumentation(
            db=db,
            company_id=current_user.company_id,
            include_full_history=False,
            history_limit=20,
        )

        # Compliance-Report
        report = await gobd_compliance_service.generate_compliance_report(
            db=db,
            company_id=current_user.company_id,
            include_details=True,
        )

        # Archiv-Statistiken
        archive_stats = await gobd_archive_service.get_archive_statistics(
            db=db,
            company_id=current_user.company_id,
        )

        # Retention-Statistiken
        retention_stats = await retention_service.get_retention_statistics(
            db=db,
            company_id=current_user.company_id,
        )

        # Audit-Chain-Statistiken
        chain_stats = await audit_chain_service.get_chain_statistics(
            db=db,
            company_id=current_user.company_id,
        )

        return {
            "export_type": "steuerberater",
            "generated_at": doc["generated_at"],
            "zeitraum": {
                "von": zeitraum_von.isoformat() if zeitraum_von else None,
                "bis": zeitraum_bis.isoformat() if zeitraum_bis else None,
            },
            "verfahrensdokumentation": {
                "document_id": doc["document_id"],
                "version": doc["version"],
                "valid_from": doc["valid_from"],
                "legal_basis": doc["legal_basis"],
                "system_description": doc["system_description"],
            },
            "compliance_status": {
                "overall_score": report.get("overall_score"),
                "overall_status": report.get("overall_status"),
                "recommendations": report.get("recommendations", []),
            },
            "archivierung": {
                "total_archived": archive_stats.get("total_archived", 0),
                "by_category": archive_stats.get("by_category", {}),
                "verification_rate": archive_stats.get("verification_rate", 0),
            },
            "aufbewahrungsfristen": {
                "total_archives": retention_stats.total_archived,
                "by_category": retention_stats.by_category,
                "expiring_soon": {
                    "30_days": retention_stats.expiring_30_days,
                    "90_days": retention_stats.expiring_90_days,
                    "180_days": retention_stats.expiring_180_days,
                },
                "expired": retention_stats.expired,
            },
            "audit_trail": {
                "total_entries": chain_stats.get("total_entries", 0),
                "by_event_type": chain_stats.get("by_event_type", {}),
                "tsa_timestamped": chain_stats.get("tsa_timestamped_count", 0),
            },
            "hinweise": [
                "Diese Daten dienen als Nachweis der GoBD-Konformitaet.",
                "Die Integritaet der Dokumente kann ueber die API verifiziert werden.",
                "Bei Fragen wenden Sie sich an den Systemadministrator.",
            ],
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Steuerberater-Export: {str(e)}",
        )

"""GoBD Compliance API Endpoints.

Stellt REST-Endpoints für GoBD-konforme Dokumentenverarbeitung bereit:
- Archivierung
- Aufbewahrungsfristen
- Audit-Chain
- Integritaetsprüfungen

GoBD = Grundsätze zur ordnungsmaessigen Führung und Aufbewahrung
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

from app.api.dependencies import get_current_user, get_db, get_user_company_id_dep
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User, Document
from app.db.bpmn_models.gobd import (
    AuditChainEventType,
    RetentionPolicy,
    RetentionDeletionRequest,
)
from app.services.compliance import (
    audit_chain_service,
    retention_service,
    gobd_archive_service,
    get_breach_notification_service,
    BreachSeverity,
    BreachType,
    BreachStatus,
    AffectedDataCategory,
    SUPERVISORY_AUTHORITIES,
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
    category: str = Field(..., description="Dokumentkategorie für Aufbewahrungsfrist")
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
    """Request für Integritaetsprüfung."""
    archive_id: uuid.UUID


class IntegrityCheckResponse(BaseModel):
    """Response der Integritaetsprüfung."""
    archive_id: uuid.UUID
    status: str
    hash_match: bool
    expected_hash: str
    actual_hash: Optional[str]
    error_message: Optional[str] = None
    duration_ms: float


class AuditChainEntryResponse(BaseModel):
    """Response für einen Audit-Chain Eintrag."""
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
    """Alert für ablaufende Aufbewahrungsfrist."""
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
    """Request zum Erstellen einer Löschanfrage."""
    archive_id: uuid.UUID
    reason: str = Field(..., min_length=10, description="Begruendung für die Löschung")


class DeletionRequestResponse(BaseModel):
    """Response einer Löschanfrage."""
    id: uuid.UUID
    archive_id: uuid.UUID
    status: str
    reason: str
    requested_at: str
    retention_expired_at: str


class DeletionApprovalRequest(BaseModel):
    """Request zum Genehmigen/Ablehnen einer Löschanfrage."""
    comment: Optional[str] = None


class ComplianceReportResponse(BaseModel):
    """Vollständiger GoBD-Compliance-Bericht."""
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
    include_details: bool = Query(True, description="Details einschließen"),
    report_date: Optional[date] = Query(None, description="Stichtag"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Generiert einen GoBD-Compliance-Bericht.

    Der Bericht bewertet:
    - Archivierungsrate
    - Aufbewahrungsfristen-Compliance
    - Audit-Trail-Vollständigkeit
    - Integritaetsprüfungen

    Ergebnis: Score 0-100 mit Empfehlungen.
    """
    report = await gobd_compliance_service.generate_compliance_report(
        db=db,
        company_id=company_id,
        report_date=report_date,
        include_details=include_details,
    )
    return ComplianceReportResponse(**report)


@router.get("/quick-status")
async def get_quick_compliance_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Schneller Compliance-Status für Dashboard-Widgets."""
    return await gobd_compliance_service.get_quick_compliance_status(
        db=db,
        company_id=company_id,
    )


# ================== Archive Endpoints ==================

@router.post("/archive", response_model=ArchiveDocumentResponse, status_code=status.HTTP_201_CREATED)
async def archive_document(
    request: ArchiveDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
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
            Document.company_id == company_id,
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
                detail="Storage-Service nicht verfügbar",
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
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Laden des Dokuments aus dem Storage"),
        )

    try:
        result = await gobd_archive_service.archive_document(
            db=db,
            document_id=request.document_id,
            company_id=company_id,
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
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Archivierung"),
        )


@router.get("/archive/{document_id}")
async def get_document_archive(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt die Archiv-Informationen für ein Dokument."""
    archive = await gobd_archive_service.get_archive_by_document(
        db=db,
        document_id=document_id,
        company_id=company_id,
    )

    if not archive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein Archiv für dieses Dokument gefunden",
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt Archivierungs-Statistiken."""
    return await gobd_archive_service.get_archive_statistics(
        db=db,
        company_id=company_id,
    )


@router.post("/archive/verify", response_model=IntegrityCheckResponse)
async def verify_archive_integrity(
    request: IntegrityCheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Verifiziert die Integritaet eines archivierten Dokuments.

    Vergleicht den gespeicherten Hash mit dem aktuellen Hash.
    Bei Abweichung: KRITISCHER FEHLER - mögliche Manipulation!
    """
    from app.db.bpmn_models.gobd import DocumentArchive

    # Lade Archiv-Informationen um document_id zu erhalten
    archive_result = await db.execute(
        select(DocumentArchive).where(
            DocumentArchive.id == request.archive_id,
            DocumentArchive.company_id == company_id,
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
            Document.company_id == company_id,
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
                detail="Storage-Service nicht verfügbar",
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
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Laden des Dokuments aus dem Storage"),
        )

    try:
        result = await gobd_archive_service.verify_archive_integrity(
            db=db,
            archive_id=request.archive_id,
            company_id=company_id,
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
            detail=safe_error_detail(e, "Integritätsprüfung"),
        )


@router.get("/archive/failed-verifications")
async def get_failed_verifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt alle Archive mit fehlgeschlagener Integritaetsprüfung.

    KRITISCH: Diese Liste sollte immer leer sein!
    """
    archives = await gobd_archive_service.get_archives_with_failed_verification(
        db=db,
        company_id=company_id,
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
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(100, ge=1, le=500, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt Einträge der Audit-Chain.

    Optional gefiltert nach Dokument.
    """
    if document_id:
        entries = await audit_chain_service.get_entries_by_document(
            db=db,
            company_id=company_id,
            document_id=document_id,
            limit=per_page,
        )
    else:
        # Hole allgemeine Einträge (neueste zuerst)
        from sqlalchemy import select, desc
        from app.db.bpmn_models.gobd import AuditChainEntry

        result = await db.execute(
            select(AuditChainEntry)
            .where(AuditChainEntry.company_id == company_id)
            .order_by(desc(AuditChainEntry.sequence_number))
            .offset((page - 1) * per_page)
            .limit(per_page)
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt einen spezifischen Audit-Chain Eintrag nach Sequenznummer."""
    entry = await audit_chain_service.get_entry_by_sequence(
        db=db,
        company_id=company_id,
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Verifiziert die Integritaet der Audit-Chain.

    Prüft alle Hash-Verkettungen auf Korrektheit.
    Bei Bruch: Die Kette wurde manipuliert!
    """
    result = await audit_chain_service.verify_chain(
        db=db,
        company_id=company_id,
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt Statistiken über die Audit-Chain."""
    stats = await audit_chain_service.get_chain_statistics(
        db=db,
        company_id=company_id,
    )
    return ChainStatisticsResponse(**stats)


# ================== Retention Endpoints ==================

@router.get("/retention/alerts", response_model=List[RetentionAlertResponse])
async def get_retention_alerts(
    days_ahead: int = Query(180, ge=1, le=365, description="Tage voraus prüfen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt Warnungen für bald ablaufende Aufbewahrungsfristen."""
    alerts = await retention_service.get_expiring_archives(
        db=db,
        company_id=company_id,
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt Statistiken zu Aufbewahrungsfristen."""
    stats = await retention_service.get_retention_statistics(
        db=db,
        company_id=company_id,
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt alle Archive mit abgelaufener Aufbewahrungsfrist."""
    archives = await retention_service.get_expired_archives(
        db=db,
        company_id=company_id,
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt alle Aufbewahrungsrichtlinien."""
    from sqlalchemy import select

    result = await db.execute(
        select(RetentionPolicy)
        .where(RetentionPolicy.company_id == company_id)
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Erstellt eine neue Aufbewahrungsrichtlinie."""
    try:
        policy = await retention_service.create_retention_policy(
            db=db,
            company_id=company_id,
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
        logger.error("retention_policy_creation_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Erstellung der Aufbewahrungsrichtlinie"),
        )


@router.post("/retention/policies/initialize")
async def initialize_retention_policies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Initialisiert Standard-Aufbewahrungsrichtlinien nach deutschem Recht."""
    policies = await retention_service.initialize_company_policies(
        db=db,
        company_id=company_id,
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Erstellt eine Löschanfrage für ein abgelaufenes Archiv."""
    try:
        deletion_request = await retention_service.request_deletion(
            db=db,
            company_id=company_id,
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
            detail=safe_error_detail(e, "Löschanfrage"),
        )


@router.get("/retention/deletion-requests")
async def get_deletion_requests(
    status_filter: Optional[str] = Query(None, description="Filter nach Status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt alle Löschanfragen."""
    from sqlalchemy import select

    query = select(RetentionDeletionRequest).where(
        RetentionDeletionRequest.company_id == company_id
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
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Genehmigt eine Löschanfrage."""
    try:
        deletion_request = await retention_service.approve_deletion(
            db=db,
            company_id=company_id,
            request_id=request_id,
            approved_by_id=current_user.id,
            comment=request.comment,
        )

        await db.commit()

        return {
            "message": "Löschanfrage genehmigt",
            "request_id": str(deletion_request.id),
            "status": deletion_request.status,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Genehmigung der Löschanfrage"),
        )


@router.post("/retention/deletion-requests/{request_id}/reject")
async def reject_deletion_request(
    request_id: uuid.UUID,
    reason: str = Query(..., min_length=10, description="Ablehnungsgrund"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Lehnt eine Löschanfrage ab."""
    try:
        deletion_request = await retention_service.reject_deletion(
            db=db,
            company_id=company_id,
            request_id=request_id,
            rejected_by_id=current_user.id,
            reason=reason,
        )

        await db.commit()

        return {
            "message": "Löschanfrage abgelehnt",
            "request_id": str(deletion_request.id),
            "status": deletion_request.status,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Ablehnung der Löschanfrage"),
        )


# ================== Verfahrensdokumentation Endpoints ==================


@router.get("/verfahrensdokumentation", response_model=VerfahrensdokumentationResponse)
async def get_verfahrensdokumentation(
    include_full_history: bool = Query(False, description="Vollständige Änderungshistorie einschließen"),
    history_limit: int = Query(50, ge=10, le=500, description="Max. Anzahl Historie-Einträge"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
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
    - Änderungshistorie

    Diese Dokumentation kann als Nachweis gegenüber Prüfern dienen.
    """
    try:
        doc = await gobd_compliance_service.generate_verfahrensdokumentation(
            db=db,
            company_id=company_id,
            include_change_history=include_full_history,
            
        )

        return VerfahrensdokumentationResponse(**doc)

    except Exception as e:
        logger.error("verfahrensdokumentation_generation_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Generierung der Verfahrensdokumentation"),
        )


@router.get("/verfahrensdokumentation/pdf")
async def export_verfahrensdokumentation_pdf(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Exportiert die Verfahrensdokumentation als PDF.

    Generiert ein druckbares PDF-Dokument für die Vorlage
    bei Steuerberatern, Wirtschaftsprüfern oder Finanzamt.

    Das PDF enthält:
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
            company_id=company_id,
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
        logger.error("verfahrensdokumentation_pdf_export_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "PDF-Export"),
        )


@router.get("/verfahrensdokumentation/markdown")
async def export_verfahrensdokumentation_markdown(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Exportiert die Verfahrensdokumentation als Markdown.

    Ideal für Versionskontrolle und interne Dokumentation.
    """
    from fastapi.responses import Response
    from app.services.compliance import (
        generate_procedure_documentation,
        DocumentFormat,
    )

    try:
        md_bytes = await generate_procedure_documentation(
            db=db,
            company_id=company_id,
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
        logger.error("verfahrensdokumentation_markdown_export_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Markdown-Export"),
        )


@router.get("/verfahrensdokumentation/html")
async def export_verfahrensdokumentation_html(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
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
            company_id=company_id,
            user_id=current_user.id,
            format=DocumentFormat.HTML,
        )

        return HTMLResponse(content=html_bytes.decode("utf-8"))

    except Exception as e:
        logger.error("verfahrensdokumentation_html_export_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "HTML-Export"),
        )


@router.get("/verfahrensdokumentation/steuerberater")
async def get_steuerberater_export(
    zeitraum_von: Optional[date] = Query(None, description="Start des Zeitraums"),
    zeitraum_bis: Optional[date] = Query(None, description="Ende des Zeitraums"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Exportiert Daten für den Steuerberater-Zugang.

    Stellt alle relevanten Compliance-Daten in einem
    strukturierten Format für externe Prüfer bereit.

    Enthält:
    - Verfahrensdokumentation (Zusammenfassung)
    - Archivierungsstatistiken
    - Aufbewahrungsfristen-Übersicht
    - Audit-Trail-Statistiken
    - Integritaetsprüfungs-Protokoll
    """
    try:
        # Verfahrensdokumentation (Kurzfassung)
        doc = await gobd_compliance_service.generate_verfahrensdokumentation(
            db=db,
            company_id=company_id,
            include_change_history=False,
            
        )

        # Compliance-Report
        report = await gobd_compliance_service.generate_compliance_report(
            db=db,
            company_id=company_id,
            include_details=True,
        )

        # Archiv-Statistiken
        archive_stats = await gobd_archive_service.get_archive_statistics(
            db=db,
            company_id=company_id,
        )

        # Retention-Statistiken
        retention_stats = await retention_service.get_retention_statistics(
            db=db,
            company_id=company_id,
        )

        # Audit-Chain-Statistiken
        chain_stats = await audit_chain_service.get_chain_statistics(
            db=db,
            company_id=company_id,
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
                "Diese Daten dienen als Nachweis der GoBD-Konformität.",
                "Die Integritaet der Dokumente kann über die API verifiziert werden.",
                "Bei Fragen wenden Sie sich an den Systemadministrator.",
            ],
        }

    except Exception as e:
        logger.error("steuerberater_export_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Steuerberater-Export"),
        )


# ================== GDPR Breach Notification (Art. 33-34) ==================

class AffectedDataCategorySchema(BaseModel):
    """Schema für betroffene Datenkategorie."""
    category: str = Field(..., description="Kategorie (z.B. 'name', 'email', 'iban')")
    description: str = Field(..., description="Beschreibung der Daten")
    count: int = Field(0, ge=0, description="Anzahl betroffener Datensätze")
    is_sensitive: bool = Field(False, description="Besondere Kategorie nach Art. 9 DSGVO")


class BreachReportRequest(BaseModel):
    """Request zum Melden einer Datenschutzverletzung."""
    breach_type: str = Field(..., description="Art der Verletzung (z.B. 'unauthorized_access')")
    severity: str = Field(..., description="Schweregrad (low, medium, high, critical)")
    description: str = Field(..., min_length=20, description="Beschreibung des Vorfalls")
    affected_subjects_count: int = Field(..., ge=0, description="Anzahl betroffener Personen")
    affected_data_categories: List[AffectedDataCategorySchema] = Field(
        ..., min_length=1, description="Betroffene Datenkategorien"
    )
    occurred_at: Optional[str] = Field(None, description="Zeitpunkt des Vorfalls (ISO 8601)")
    is_estimate: bool = Field(False, description="True wenn Anzahl geschätzt ist")


class BreachReportResponse(BaseModel):
    """Response nach Melden einer Datenschutzverletzung."""
    success: bool
    breach_id: Optional[str] = None
    deadline_72h: Optional[str] = None
    requires_authority_notification: bool = False
    requires_subject_notification: bool = False
    message: str


class BreachStatusUpdateRequest(BaseModel):
    """Request zum Aktualisieren des Breach-Status."""
    status: str = Field(..., description="Neuer Status")
    notes: Optional[str] = Field(None, description="Optionale Notizen")


class BreachMeasureRequest(BaseModel):
    """Request zum Hinzufuegen einer Massnahme."""
    measure: str = Field(..., min_length=10, description="Beschreibung der Massnahme")


class BreachRootCauseRequest(BaseModel):
    """Request für Root-Cause-Analyse."""
    root_cause: str = Field(..., min_length=20, description="Root-Cause-Analyse")
    impact_assessment: str = Field(..., min_length=20, description="Impact-Assessment")


class AuthorityNotificationRequest(BaseModel):
    """Request für Behoerdenbenachrichtigung."""
    state_code: str = Field("DE-DEFAULT", description="Bundesland-Code (DE-BW, DE-BY, etc.)")
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    dpo_name: Optional[str] = None
    dpo_contact: Optional[str] = None


class BreachListResponse(BaseModel):
    """Response für Breach-Liste."""
    breaches: List[dict]
    total: int
    page: int
    per_page: int


@router.post("/breach/report", response_model=BreachReportResponse)
async def report_data_breach(
    request: BreachReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Meldet eine Datenschutzverletzung nach Art. 33 DSGVO.

    WICHTIG: Die 72-Stunden-Frist für die Meldung an die Aufsichtsbehoerde
    beginnt mit dem Zeitpunkt der Erkennung der Verletzung.

    Schweregrade:
    - low: Minimales Risiko, keine Meldepflicht
    - medium: Risiko vorhanden, Meldung an Behoerde erforderlich
    - high: Hohes Risiko, Meldung + Betroffenenbenachrichtigung erforderlich
    - critical: Kritisch, sofortige Eskalation
    """
    try:
        breach_type = BreachType(request.breach_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Breach-Typ. Erlaubt: {[t.value for t in BreachType]}",
        )

    try:
        severity = BreachSeverity(request.severity)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Schweregrad. Erlaubt: {[s.value for s in BreachSeverity]}",
        )

    # Konvertiere Datenkategorien
    categories = [
        AffectedDataCategory(
            category=cat.category,
            description=cat.description,
            count=cat.count,
            is_sensitive=cat.is_sensitive,
        )
        for cat in request.affected_data_categories
    ]

    # Parse occurred_at wenn angegeben
    occurred_at = None
    if request.occurred_at:
        from datetime import datetime
        try:
            occurred_at = datetime.fromisoformat(request.occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültiges Datumsformat für occurred_at. Erwartet: ISO 8601",
            )

    service = get_breach_notification_service()
    result = await service.report_breach(
        db=db,
        breach_type=breach_type,
        severity=severity,
        description=request.description,
        affected_subjects_count=request.affected_subjects_count,
        affected_data_categories=categories,
        reported_by=str(current_user.id),
        company_id=str(company_id) if company_id else None,
        occurred_at=occurred_at,
        is_estimate=request.is_estimate,
    )

    if result.success:
        logger.warning(
            "breach_reported_via_api",
            breach_id=result.breach_id,
            user_id=str(current_user.id)[:8],
            severity=severity.value,
            security_event=True,
        )

        return BreachReportResponse(
            success=True,
            breach_id=result.breach_id,
            deadline_72h=result.deadline_72h.isoformat() if result.deadline_72h else None,
            requires_authority_notification=result.requires_authority_notification,
            requires_subject_notification=result.requires_subject_notification,
            message="Datenschutzverletzung erfolgreich gemeldet. Bitte beachten Sie die 72-Stunden-Frist!",
        )
    else:
        return BreachReportResponse(
            success=False,
            message=result.error or "Fehler beim Melden der Datenschutzverletzung",
        )


@router.get("/breach", response_model=BreachListResponse)
async def list_breaches(
    status_filter: Optional[str] = Query(None, description="Status-Filter"),
    severity_filter: Optional[str] = Query(None, description="Schweregrad-Filter"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Listet alle Datenschutzverletzungen auf.

    Optionale Filter:
    - status_filter: detected, investigating, contained, authority_notified, etc.
    - severity_filter: low, medium, high, critical
    """
    status_enum = None
    if status_filter:
        try:
            status_enum = BreachStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Status. Erlaubt: {[s.value for s in BreachStatus]}",
            )

    severity_enum = None
    if severity_filter:
        try:
            severity_enum = BreachSeverity(severity_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Schweregrad. Erlaubt: {[s.value for s in BreachSeverity]}",
            )

    service = get_breach_notification_service()
    breaches, total = await service.list_breaches(
        db=db,
        company_id=str(company_id) if company_id else None,
        status=status_enum,
        severity=severity_enum,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return BreachListResponse(
        breaches=[
            {
                "id": b.id,
                "breach_type": b.breach_type.value,
                "severity": b.severity.value,
                "status": b.status.value,
                "description": b.description[:200] + "..." if len(b.description) > 200 else b.description,
                "affected_subjects_count": b.affected_subjects_count,
                "detected_at": b.detected_at.isoformat(),
                "deadline_72h": b.deadline_72h.isoformat(),
                "authority_notification": b.authority_notification.value,
                "subjects_notification": b.subjects_notification.value,
            }
            for b in breaches
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/breach/deadlines")
async def get_breach_deadlines(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Gibt alle Breaches mit anstehenden 72-Stunden-Deadlines zurück.

    KRITISCH: Diese Deadlines müssen eingehalten werden!
    """
    service = get_breach_notification_service()
    deadlines = await service.get_pending_deadlines(
        db=db,
        company_id=str(company_id) if company_id else None,
    )

    return {
        "count": len(deadlines),
        "deadlines": deadlines,
    }


@router.get("/breach/{breach_id}")
async def get_breach_details(
    breach_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
):
    """Holt Details einer Datenschutzverletzung."""
    service = get_breach_notification_service()
    breach = await service.get_breach(db, breach_id)

    if not breach:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breach {breach_id} nicht gefunden",
        )

    # Prüfe Company-Zugehoerigkeit
    if breach.company_id and company_id:
        if breach.company_id != str(company_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für diesen Breach",
            )

    return {
        "id": breach.id,
        "breach_type": breach.breach_type.value,
        "severity": breach.severity.value,
        "status": breach.status.value,
        "description": breach.description,
        "root_cause": breach.root_cause,
        "impact_assessment": breach.impact_assessment,
        "detected_at": breach.detected_at.isoformat(),
        "occurred_at": breach.occurred_at.isoformat() if breach.occurred_at else None,
        "contained_at": breach.contained_at.isoformat() if breach.contained_at else None,
        "deadline_72h": breach.deadline_72h.isoformat(),
        "is_deadline_met": breach.is_deadline_met,
        "affected_data_categories": [
            {
                "category": cat.category,
                "description": cat.description,
                "count": cat.count,
                "is_sensitive": cat.is_sensitive,
            }
            for cat in breach.affected_data_categories
        ],
        "affected_subjects_count": breach.affected_subjects_count,
        "affected_subjects_estimate": breach.affected_subjects_estimate,
        "containment_measures": breach.containment_measures,
        "remediation_measures": breach.remediation_measures,
        "preventive_measures": breach.preventive_measures,
        "authority_notification": breach.authority_notification.value,
        "authority_notified_at": breach.authority_notified_at.isoformat() if breach.authority_notified_at else None,
        "subjects_notification": breach.subjects_notification.value,
        "subjects_notified_at": breach.subjects_notified_at.isoformat() if breach.subjects_notified_at else None,
    }


@router.get("/breach/{breach_id}/timeline")
async def get_breach_timeline(
    breach_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt die Timeline einer Datenschutzverletzung."""
    service = get_breach_notification_service()
    timeline = await service.get_timeline(breach_id)

    return {
        "breach_id": breach_id,
        "entries": timeline,
    }


@router.patch("/breach/{breach_id}/status")
async def update_breach_status(
    breach_id: str,
    request: BreachStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aktualisiert den Status einer Datenschutzverletzung."""
    try:
        new_status = BreachStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Status. Erlaubt: {[s.value for s in BreachStatus]}",
        )

    service = get_breach_notification_service()
    success = await service.update_breach_status(
        db=db,
        breach_id=breach_id,
        new_status=new_status,
        updated_by=str(current_user.id),
        notes=request.notes,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breach {breach_id} nicht gefunden",
        )

    logger.info(
        "breach_status_updated_via_api",
        breach_id=breach_id,
        new_status=new_status.value,
        user_id=str(current_user.id)[:8],
    )

    return {"success": True, "breach_id": breach_id, "status": new_status.value}


@router.post("/breach/{breach_id}/containment")
async def add_containment_measure(
    breach_id: str,
    request: BreachMeasureRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fuegt eine Eindaemmungsmassnahme hinzu."""
    service = get_breach_notification_service()
    success = await service.add_containment_measure(
        db=db,
        breach_id=breach_id,
        measure=request.measure,
        added_by=str(current_user.id),
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breach {breach_id} nicht gefunden",
        )

    return {"success": True, "breach_id": breach_id, "message": "Eindaemmungsmassnahme hinzugefuegt"}


@router.post("/breach/{breach_id}/remediation")
async def add_remediation_measure(
    breach_id: str,
    request: BreachMeasureRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fuegt eine Behebungsmassnahme hinzu."""
    service = get_breach_notification_service()
    success = await service.add_remediation_measure(
        db=db,
        breach_id=breach_id,
        measure=request.measure,
        added_by=str(current_user.id),
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breach {breach_id} nicht gefunden",
        )

    return {"success": True, "breach_id": breach_id, "message": "Behebungsmassnahme hinzugefuegt"}


@router.post("/breach/{breach_id}/root-cause")
async def set_breach_root_cause(
    breach_id: str,
    request: BreachRootCauseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Setzt Root-Cause-Analyse und Impact-Assessment."""
    service = get_breach_notification_service()
    success = await service.set_root_cause(
        db=db,
        breach_id=breach_id,
        root_cause=request.root_cause,
        impact_assessment=request.impact_assessment,
        updated_by=str(current_user.id),
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breach {breach_id} nicht gefunden",
        )

    return {"success": True, "breach_id": breach_id, "message": "Root-Cause-Analyse gespeichert"}


@router.post("/breach/{breach_id}/generate-authority-notification")
async def generate_authority_notification(
    breach_id: str,
    request: AuthorityNotificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generiert die Behoerdenbenachrichtigung nach Art. 33 DSGVO.

    Die Benachrichtigung enthält alle Pflichtangaben nach Art. 33 Abs. 3 DSGVO:
    - Art der Verletzung
    - Kategorien und Anzahl der Betroffenen
    - Wahrscheinliche Folgen
    - Ergriffene Massnahmen
    """
    service = get_breach_notification_service()
    template = await service.generate_authority_notification(
        db=db,
        breach_id=breach_id,
        state_code=request.state_code,
        company_name=request.company_name or "",
        company_address=request.company_address or "",
        dpo_name=request.dpo_name or "",
        dpo_contact=request.dpo_contact or "",
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breach {breach_id} nicht gefunden",
        )

    return {
        "breach_id": breach_id,
        "authority_name": template.authority_name,
        "authority_email": template.authority_email,
        "authority_address": template.authority_address,
        "text_content": template.to_text(),
        "html_content": template.to_html(),
        "generated_at": template.generated_at.isoformat(),
    }


@router.post("/breach/{breach_id}/generate-subject-notification")
async def generate_subject_notification(
    breach_id: str,
    company_name: Optional[str] = Query(None),
    dpo_name: Optional[str] = Query(None),
    dpo_contact: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generiert die Betroffenenbenachrichtigung nach Art. 34 DSGVO.

    Die Benachrichtigung ist in klarer, verstaendlicher Sprache verfasst
    und enthält:
    - Art der Verletzung
    - Wahrscheinliche Folgen
    - Ergriffene Massnahmen
    - Empfehlungen für Betroffene
    """
    service = get_breach_notification_service()
    template = await service.generate_subject_notification(
        db=db,
        breach_id=breach_id,
        company_name=company_name or "",
        dpo_name=dpo_name or "",
        dpo_contact=dpo_contact or "",
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breach {breach_id} nicht gefunden",
        )

    return {
        "breach_id": breach_id,
        "text_content": template.to_text(),
        "generated_at": template.generated_at.isoformat(),
    }


@router.get("/breach/supervisory-authorities")
async def get_supervisory_authorities(
    current_user: User = Depends(get_current_user),
):
    """Gibt Liste aller konfigurierten Aufsichtsbehoerden zurück."""
    return {
        "authorities": [
            {
                "code": code,
                "name": auth["name"],
                "email": auth["email"],
                "phone": auth["phone"],
                "address": auth["address"],
                "form_url": auth["form_url"],
            }
            for code, auth in SUPERVISORY_AUTHORITIES.items()
        ]
    }

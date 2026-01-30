"""GoBD Archive API Router - Revisionssichere Dokumentenarchivierung.

API-Endpoints fuer die GoBD-konforme Archivierung:
- Dokumente archivieren mit SHA-256 Signatur
- Integritaetspruefung (Hash-Verifikation)
- Aufbewahrungsfristen verwalten
- Statistiken und Ablaufwarnungen

Erfuellt GoBD-Kriterien:
- Nachvollziehbarkeit: Vollstaendiger Audit-Trail
- Unveraenderbarkeit: SHA-256 Hash-Signatur
- Vollstaendigkeit: Aufbewahrungsfristen-Management
- Ordnung: Kategorisierung nach Dokumenttyp
"""

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user, get_current_superuser
from app.core.exceptions import (
    DocumentNotFoundError,
    ArchiveError,
    ImmutabilityViolationError,
)
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.core.security_auth import build_content_disposition
from app.db.models import User, RetentionCategory
from app.middleware.company_context import require_company, Company
from app.services.archive_service import archive_service
from app.services.procedure_doc_service import procedure_doc_service
from app.services.gdpdu_export_service import gdpdu_export_service, GDPdUExportOptions
from app.services.document_access_service import document_access_service
from app.services.gobd_compliance_service import gobd_compliance_service

router = APIRouter(prefix="/archive", tags=["Archive (GoBD)"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ArchiveDocumentRequest(BaseModel):
    """Request zum Archivieren eines Dokuments."""

    document_id: uuid.UUID = Field(..., description="ID des zu archivierenden Dokuments")
    retention_category: str = Field(
        default=RetentionCategory.OTHER.value,
        description="Aufbewahrungskategorie (invoice, contract, correspondence, etc.)"
    )
    signature_certificate: Optional[str] = Field(
        default=None,
        description="Optionales TSA-Zertifikat fuer qualifizierte Zeitstempel"
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Zusaetzliche Metadaten"
    )


class ArchiveResponse(BaseModel):
    """Response nach erfolgreicher Archivierung."""

    id: uuid.UUID
    document_id: uuid.UUID
    content_hash: str
    hash_algorithm: str
    signature_timestamp: datetime
    retention_category: str
    retention_years: int
    retention_expires_at: date
    archived_at: datetime
    archived_by_id: Optional[uuid.UUID]

    model_config = ConfigDict(from_attributes=True)


class VerificationResponse(BaseModel):
    """Response der Integritaetspruefung."""

    document_id: uuid.UUID
    is_verified: bool
    last_verification_at: datetime
    verification_failed_reason: Optional[str] = None
    message: str


class RetentionSettingResponse(BaseModel):
    """Response fuer Aufbewahrungsfristen-Einstellung."""

    id: uuid.UUID
    category: str
    display_name: str
    description: Optional[str]
    retention_years: int
    legal_basis: Optional[str]
    reminder_days_before: int
    auto_delete_enabled: bool
    requires_approval_for_delete: bool

    model_config = ConfigDict(from_attributes=True)


class RetentionSettingUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer Aufbewahrungsfristen-Einstellung."""

    retention_years: int = Field(..., ge=1, le=30, description="Aufbewahrungsdauer in Jahren")
    reminder_days_before: int = Field(..., ge=0, le=365, description="Tage vor Ablauf fuer Warnung")
    auto_delete_enabled: bool = Field(default=False, description="Auto-Loeschung aktivieren")


class ArchiveStatisticsResponse(BaseModel):
    """Response fuer Archiv-Statistiken."""

    total_archived: int
    by_category: dict
    expiring_soon_90_days: int
    verification_failed: int


class ExpiringArchiveResponse(BaseModel):
    """Response fuer bald ablaufendes Archiv."""

    id: uuid.UUID
    document_id: uuid.UUID
    retention_category: str
    retention_expires_at: date
    days_until_expiry: int


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "/documents",
    response_model=ArchiveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dokument archivieren",
    description="Archiviert ein Dokument GoBD-konform mit SHA-256 Signatur"
)
async def archive_document(
    request: ArchiveDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> ArchiveResponse:
    """Archiviert ein Dokument GoBD-konform.

    - Berechnet SHA-256 Hash des Dokument-Inhalts
    - Setzt Aufbewahrungsfrist basierend auf Kategorie
    - Markiert Dokument als unveraenderbar

    Args:
        request: Archivierungsanfrage mit Dokument-ID und Kategorie
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        ArchiveResponse mit Archiv-Details

    Raises:
        404: Dokument nicht gefunden
        400: Dokument bereits archiviert
        403: Keine Berechtigung fuer dieses Dokument
    """
    # SECURITY: IDOR-Schutz - Dokument muss zur Company gehoeren
    from sqlalchemy import select
    from app.db.models import Document

    stmt = select(Document).where(Document.id == request.document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    if document.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument"
        )

    try:
        archive = await archive_service.archive_document(
            db=db,
            document_id=request.document_id,
            user_id=current_user.id,
            retention_category=request.retention_category,
            signature_certificate=request.signature_certificate,
            metadata=request.metadata,
        )
        return ArchiveResponse.model_validate(archive)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message_de
        )
    except ArchiveError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.user_message_de
        )


@router.get(
    "/documents/{document_id}",
    response_model=ArchiveResponse,
    summary="Archiv-Informationen abrufen",
    description="Holt die Archiv-Informationen fuer ein Dokument"
)
async def get_archive(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> ArchiveResponse:
    """Holt die Archiv-Informationen fuer ein Dokument.

    Args:
        document_id: ID des Dokuments
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        ArchiveResponse mit Archiv-Details

    Raises:
        404: Archiv nicht gefunden
    """
    archive = await archive_service.get_archive(db, document_id)
    if not archive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archiv nicht gefunden"
        )

    # IDOR-Schutz: Nur Archives der eigenen Company erlauben
    if archive.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Archiv"
        )

    return ArchiveResponse.model_validate(archive)


@router.post(
    "/documents/{document_id}/verify",
    response_model=VerificationResponse,
    summary="Integritaet pruefen",
    description="Verifiziert die Integritaet eines archivierten Dokuments durch Hash-Vergleich"
)
async def verify_document_integrity(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> VerificationResponse:
    """Verifiziert die Integritaet eines archivierten Dokuments.

    Vergleicht den aktuellen Hash mit dem archivierten Hash.

    Args:
        document_id: ID des Dokuments
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        VerificationResponse mit Verifikationsergebnis

    Raises:
        404: Dokument nicht gefunden
        400: Dokument nicht archiviert
    """
    try:
        # IDOR-Schutz: Zuerst pruefen ob das Dokument zur Company gehoert
        archive = await archive_service.get_archive(db, document_id)
        if archive and archive.company_id != company.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung fuer dieses Archiv"
            )

        is_verified = await archive_service.verify_document_integrity(db, document_id)
        # Archive neu laden nach Verifikation (aktualisierte Timestamps)
        archive = await archive_service.get_archive(db, document_id)

        if is_verified:
            message = "Dokumentintegritaet bestaetigt - Hash stimmt ueberein"
        else:
            message = "WARNUNG: Dokumentintegritaet moeglicherweise kompromittiert!"

        return VerificationResponse(
            document_id=document_id,
            is_verified=is_verified,
            last_verification_at=archive.last_verification_at,
            verification_failed_reason=archive.verification_failed_reason,
            message=message,
        )
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message_de
        )
    except ArchiveError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.user_message_de
        )


@router.get(
    "/statistics",
    response_model=ArchiveStatisticsResponse,
    summary="Archiv-Statistiken",
    description="Holt Statistiken zur Archivierung fuer die aktuelle Firma"
)
async def get_archive_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> ArchiveStatisticsResponse:
    """Holt Archiv-Statistiken fuer die aktuelle Firma.

    Args:
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        ArchiveStatisticsResponse mit Statistiken
    """
    stats = await archive_service.get_archive_statistics(db, company.id)
    return ArchiveStatisticsResponse(**stats)


@router.get(
    "/expiring",
    response_model=list[ExpiringArchiveResponse],
    summary="Bald ablaufende Archive",
    description="Listet Archive auf, die bald ablaufen"
)
async def get_expiring_archives(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> list[ExpiringArchiveResponse]:
    """Findet Archive, die bald ablaufen.

    Args:
        days: Tage bis zum Ablauf (default: 90)
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        Liste von bald ablaufenden Archiven
    """
    archives = await archive_service.get_expiring_archives(
        db, company.id, days_until_expiry=days
    )

    today = date.today()
    return [
        ExpiringArchiveResponse(
            id=archive.id,
            document_id=archive.document_id,
            retention_category=archive.retention_category,
            retention_expires_at=archive.retention_expires_at,
            days_until_expiry=(archive.retention_expires_at - today).days,
        )
        for archive in archives
    ]


# =============================================================================
# Retention Settings Endpoints (Admin only)
# =============================================================================


@router.get(
    "/retention-settings",
    response_model=list[RetentionSettingResponse],
    summary="Aufbewahrungsfristen-Einstellungen",
    description="Listet alle Aufbewahrungsfristen-Einstellungen auf"
)
async def get_retention_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RetentionSettingResponse]:
    """Holt alle Aufbewahrungsfristen-Einstellungen.

    Args:
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        Liste aller RetentionSettings
    """
    settings = await archive_service.get_retention_settings(db)
    return [RetentionSettingResponse.model_validate(s) for s in settings]


@router.put(
    "/retention-settings/{category}",
    response_model=RetentionSettingResponse,
    summary="Aufbewahrungsfristen-Einstellung aktualisieren",
    description="Aktualisiert eine Aufbewahrungsfristen-Einstellung (nur Admin)"
)
async def update_retention_setting(
    category: str,
    request: RetentionSettingUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> RetentionSettingResponse:
    """Aktualisiert eine Aufbewahrungsfristen-Einstellung.

    Nur fuer Administratoren.

    Args:
        category: Kategorie-Name
        request: Aktualisierungsdaten
        db: Datenbank-Session
        current_user: Admin-Benutzer

    Returns:
        Aktualisierte RetentionSetting

    Raises:
        404: Kategorie nicht gefunden
    """
    try:
        setting = await archive_service.update_retention_setting(
            db=db,
            category=category,
            retention_years=request.retention_years,
            reminder_days_before=request.reminder_days_before,
            auto_delete_enabled=request.auto_delete_enabled,
            updated_by_id=current_user.id,
        )
        return RetentionSettingResponse.model_validate(setting)
    except ArchiveError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message_de
        )


# =============================================================================
# Retention Categories Reference
# =============================================================================


@router.get(
    "/categories",
    response_model=dict,
    summary="Verfuegbare Kategorien",
    description="Listet alle verfuegbaren Aufbewahrungskategorien auf"
)
async def get_categories() -> dict:
    """Gibt alle verfuegbaren Aufbewahrungskategorien zurueck.

    Returns:
        Dictionary mit Kategorien und deren Beschreibung
    """
    return {
        "categories": [
            {
                "value": RetentionCategory.INVOICE.value,
                "display_name": "Rechnung",
                "description": "Ein- und ausgehende Rechnungen",
                "default_years": 10,
                "legal_basis": "§147 AO, §14b UStG"
            },
            {
                "value": RetentionCategory.CONTRACT.value,
                "display_name": "Vertrag",
                "description": "Vertraege und Vereinbarungen",
                "default_years": 10,
                "legal_basis": "§147 AO, §257 HGB"
            },
            {
                "value": RetentionCategory.CORRESPONDENCE.value,
                "display_name": "Geschaeftsbrief",
                "description": "Handels- und Geschaeftsbriefe",
                "default_years": 6,
                "legal_basis": "§257 HGB"
            },
            {
                "value": RetentionCategory.BOOKING_DOCUMENT.value,
                "display_name": "Buchungsbeleg",
                "description": "Buchungsbelege und Kontoauszuege",
                "default_years": 10,
                "legal_basis": "§147 AO"
            },
            {
                "value": RetentionCategory.ANNUAL_REPORT.value,
                "display_name": "Jahresabschluss",
                "description": "Jahresabschluesse und Bilanzen",
                "default_years": 10,
                "legal_basis": "§257 HGB"
            },
            {
                "value": RetentionCategory.TAX_DOCUMENT.value,
                "display_name": "Steuerbeleg",
                "description": "Steuerbescheide und -erklaerungen",
                "default_years": 10,
                "legal_basis": "§147 AO"
            },
            {
                "value": RetentionCategory.EMPLOYEE_DOCUMENT.value,
                "display_name": "Personalakte",
                "description": "Personalunterlagen",
                "default_years": 10,
                "legal_basis": "§257 HGB"
            },
            {
                "value": RetentionCategory.OTHER.value,
                "display_name": "Sonstiges",
                "description": "Sonstige steuerrelevante Dokumente",
                "default_years": 6,
                "legal_basis": "§147 AO"
            },
        ]
    }


# =============================================================================
# Verfahrensdokumentation Endpoints
# =============================================================================


class ProcedureDocVersionResponse(BaseModel):
    """Response fuer Verfahrensdokumentation-Version."""

    id: uuid.UUID
    version: str
    generated_at: datetime
    generated_by: str
    content_hash: str
    change_summary: Optional[str] = None
    company_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)


class ProcedureDocDetailResponse(ProcedureDocVersionResponse):
    """Detaillierte Response mit Inhalt."""

    content: dict
    change_details: Optional[dict] = None


@router.post(
    "/procedure-documentation",
    response_model=ProcedureDocVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verfahrensdokumentation generieren",
    description="Generiert eine neue Version der GoBD-Verfahrensdokumentation"
)
async def generate_procedure_documentation(
    change_summary: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    company: Company = Depends(require_company),
) -> ProcedureDocVersionResponse:
    """Generiert eine neue Version der Verfahrensdokumentation.

    Nur fuer Administratoren.

    Args:
        change_summary: Zusammenfassung der Aenderungen
        db: Datenbank-Session
        current_user: Admin-Benutzer
        company: Aktuelle Firma

    Returns:
        Neue Dokumentationsversion
    """
    version = await procedure_doc_service.generate_documentation(
        db=db,
        company_id=company.id,
        change_summary=change_summary,
    )
    return ProcedureDocVersionResponse.model_validate(version)


@router.get(
    "/procedure-documentation",
    response_model=ProcedureDocDetailResponse,
    summary="Aktuelle Verfahrensdokumentation",
    description="Holt die neueste Version der Verfahrensdokumentation"
)
async def get_current_procedure_documentation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> ProcedureDocDetailResponse:
    """Holt die aktuelle Verfahrensdokumentation.

    Args:
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        Aktuelle Dokumentationsversion

    Raises:
        404: Keine Dokumentation vorhanden
    """
    version = await procedure_doc_service.get_latest_version(db, company.id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Verfahrensdokumentation vorhanden. Bitte zuerst generieren."
        )
    return ProcedureDocDetailResponse.model_validate(version)


@router.get(
    "/procedure-documentation/history",
    response_model=list[ProcedureDocVersionResponse],
    summary="Versionshistorie",
    description="Holt die Versionshistorie der Verfahrensdokumentation"
)
async def get_procedure_documentation_history(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> list[ProcedureDocVersionResponse]:
    """Holt die Versionshistorie.

    Args:
        limit: Maximale Anzahl Versionen
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        Liste der Versionen
    """
    versions = await procedure_doc_service.get_version_history(
        db, company.id, limit=limit
    )
    return [ProcedureDocVersionResponse.model_validate(v) for v in versions]


@router.get(
    "/procedure-documentation/{version_id}",
    response_model=ProcedureDocDetailResponse,
    summary="Bestimmte Version abrufen",
    description="Holt eine bestimmte Version der Verfahrensdokumentation"
)
async def get_procedure_documentation_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> ProcedureDocDetailResponse:
    """Holt eine bestimmte Version.

    Args:
        version_id: Versions-ID
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        Dokumentationsversion

    Raises:
        404: Version nicht gefunden
        403: Keine Berechtigung
    """
    version = await procedure_doc_service.get_version_by_id(db, version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version nicht gefunden"
        )

    # SECURITY: IDOR-Schutz - Version muss zur Company gehoeren
    if version.company_id and version.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Version"
        )

    return ProcedureDocDetailResponse.model_validate(version)


@router.get(
    "/procedure-documentation/{version_id}/export",
    summary="Als Markdown exportieren",
    description="Exportiert die Verfahrensdokumentation als Markdown"
)
async def export_procedure_documentation_markdown(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """Exportiert die Verfahrensdokumentation als Markdown.

    Args:
        version_id: Versions-ID
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        Markdown-Datei

    Raises:
        404: Version nicht gefunden
        403: Keine Berechtigung
    """
    from fastapi.responses import Response

    # SECURITY: IDOR-Schutz - Version muss zur Company gehoeren
    version = await procedure_doc_service.get_version_by_id(db, version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version nicht gefunden"
        )

    if version.company_id and version.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Version"
        )

    try:
        markdown = await procedure_doc_service.export_as_markdown(db, version_id)
        return Response(
            content=markdown,
            media_type="text/markdown",
            headers={
                "Content-Disposition": build_content_disposition(f"verfahrensdokumentation_{version_id}.md", "attachment")
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Export")
        )


# =============================================================================
# GDPdU Export Endpoints (Betriebspruefung)
# =============================================================================


class GDPdUExportRequest(BaseModel):
    """Request fuer GDPdU-Export."""

    start_date: date = Field(..., description="Startdatum des Exportzeitraums")
    end_date: date = Field(..., description="Enddatum des Exportzeitraums")
    include_documents: bool = Field(default=True, description="Dokumente exportieren")
    include_archives: bool = Field(default=True, description="Archive exportieren")
    include_invoices: bool = Field(default=True, description="Rechnungen exportieren")
    include_contracts: bool = Field(default=True, description="Vertraege exportieren")
    comment: Optional[str] = Field(default=None, description="Optionaler Kommentar fuer den Export")


class GDPdUExportPreviewResponse(BaseModel):
    """Response fuer GDPdU-Export Vorschau."""

    zeitraum: dict
    anzahl: dict
    tabellen: list
    geschaetzte_groesse_kb: float


@router.post(
    "/export/gdpdu/preview",
    response_model=GDPdUExportPreviewResponse,
    summary="GDPdU-Export Vorschau",
    description="Zeigt eine Vorschau des GDPdU-Exports an (Anzahl Datensaetze, geschaetzte Groesse)"
)
async def preview_gdpdu_export(
    request: GDPdUExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    company: Company = Depends(require_company),
) -> GDPdUExportPreviewResponse:
    """Zeigt eine Vorschau des GDPdU-Exports an.

    Zeigt an, wie viele Datensaetze exportiert werden und die geschaetzte Groesse.
    Nur fuer Administratoren.

    Args:
        request: Export-Optionen
        db: Datenbank-Session
        current_user: Admin-Benutzer
        company: Aktuelle Firma

    Returns:
        GDPdUExportPreviewResponse mit Statistiken
    """
    options = GDPdUExportOptions(
        company_id=company.id,
        start_date=request.start_date,
        end_date=request.end_date,
        include_documents=request.include_documents,
        include_archives=request.include_archives,
        include_invoices=request.include_invoices,
        include_contracts=request.include_contracts,
        comment=request.comment,
    )

    preview = await gdpdu_export_service.get_export_preview(db, options)

    # Filter None-Werte aus Tabellen-Liste
    preview["tabellen"] = [t for t in preview["tabellen"] if t is not None]

    return GDPdUExportPreviewResponse(**preview)


@router.post(
    "/export/gdpdu",
    summary="GDPdU-Export erstellen",
    description="Erstellt einen GDPdU-konformen Export fuer Betriebspruefungen (ZIP-Archiv)"
)
async def create_gdpdu_export(
    request: GDPdUExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    company: Company = Depends(require_company),
):
    """Erstellt einen GDPdU-Export als ZIP-Archiv.

    Erstellt einen vollstaendigen GDPdU-Export mit:
    - index.xml: GDPdU-Strukturbeschreibung
    - DTD-Datei: Dokumenttyp-Definition
    - CSV-Datendateien: Dokumente, Archive, Rechnungen, Vertraege
    - README: Erklaerungen und rechtliche Grundlagen

    Nur fuer Administratoren.

    Args:
        request: Export-Optionen
        db: Datenbank-Session
        current_user: Admin-Benutzer
        company: Aktuelle Firma

    Returns:
        ZIP-Archiv als Download
    """
    from fastapi.responses import Response

    options = GDPdUExportOptions(
        company_id=company.id,
        start_date=request.start_date,
        end_date=request.end_date,
        include_documents=request.include_documents,
        include_archives=request.include_archives,
        include_invoices=request.include_invoices,
        include_contracts=request.include_contracts,
        comment=request.comment,
    )

    try:
        zip_content = await gdpdu_export_service.create_export(db, options)

        filename = (
            f"gdpdu_export_{company.name.replace(' ', '_')}_"
            f"{request.start_date.strftime('%Y%m%d')}_"
            f"{request.end_date.strftime('%Y%m%d')}.zip"
        )

        return Response(
            content=zip_content,
            media_type="application/zip",
            headers={
                "Content-Disposition": build_content_disposition(filename, "attachment")
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Export")
        )


# =============================================================================
# Tax Authority Export (§90 III AO) - Feature 20
# =============================================================================


class TaxExportRequest(BaseModel):
    """Anfrage fuer Tax Authority Export nach §90 III AO."""

    period_start: date = Field(..., description="Beginn Pruefungszeitraum")
    period_end: date = Field(..., description="Ende Pruefungszeitraum")
    include_invoices: bool = Field(True, description="Rechnungen einschliessen")
    include_transactions: bool = Field(True, description="Bankbewegungen einschliessen")
    include_documents: bool = Field(True, description="Belege einschliessen")
    include_audit_log: bool = Field(True, description="Aenderungsprotokoll einschliessen")
    output_dir: Optional[str] = Field(None, description="Optionales Ausgabeverzeichnis")


class TaxExportPreviewResponse(BaseModel):
    """Vorschau eines Tax Authority Exports."""

    period_start: date
    period_end: date
    estimated_records: int = Field(..., description="Geschaetzte Anzahl Datensaetze")
    categories: dict = Field(default_factory=dict, description="Datensaetze pro Kategorie")
    tables: list = Field(default_factory=list, description="Verfuegbare Tabellen")


class TaxExportResultResponse(BaseModel):
    """Ergebnis eines Tax Authority Exports."""

    success: bool
    export_id: str
    format: str
    period_start: date
    period_end: date
    company_name: str
    created_at: datetime
    total_records: int
    files: list = Field(default_factory=list)
    archive_path: Optional[str] = None
    error: Optional[str] = None


@router.get(
    "/export/tax-authority/tables",
    response_model=dict,
    summary="Verfuegbare Export-Tabellen",
    description="Listet alle verfuegbaren Tabellen fuer den Steuerpruefer-Export auf."
)
async def list_tax_export_tables(
    current_user: User = Depends(get_current_superuser),
) -> dict:
    """
    Listet alle Tabellendefinitionen fuer den Tax Authority Export.

    Tabellen:
    - rechnungen: Ausgangs- und Eingangsrechnungen
    - bankbewegungen: Kontoumsaetze
    - belege: Archivierte Dokumente
    - aenderungsprotokoll: Audit-Trail
    """
    from app.services.compliance.tax_authority_export_service import (
        get_invoice_table_definition,
        get_bank_transaction_table_definition,
        get_document_table_definition,
        get_audit_log_table_definition,
    )

    tables = [
        get_invoice_table_definition(),
        get_bank_transaction_table_definition(),
        get_document_table_definition(),
        get_audit_log_table_definition(),
    ]

    return {
        "tables": [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "primary_key": t.primary_key,
                "fields_count": len(t.fields),
                "fields": [
                    {
                        "name": f.name,
                        "description": f.description,
                        "data_type": f.data_type,
                        "required": f.required,
                    }
                    for f in t.fields
                ],
            }
            for t in tables
        ],
        "total_tables": len(tables),
    }


@router.post(
    "/export/tax-authority/preview",
    response_model=TaxExportPreviewResponse,
    summary="Tax Authority Export Vorschau",
    description="Zeigt eine Vorschau des Exports fuer Betriebspruefungen nach §90 III AO."
)
async def preview_tax_authority_export(
    request: TaxExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    company: Company = Depends(require_company),
) -> TaxExportPreviewResponse:
    """
    Erstellt eine Vorschau des Tax Authority Exports.

    Zeigt:
    - Geschaetzte Anzahl Datensaetze
    - Aufschluesselung nach Kategorien
    - Verfuegbare Tabellen
    """
    from app.services.compliance.tax_authority_export_service import (
        get_tax_authority_export_service,
    )

    service = get_tax_authority_export_service(db)

    # Datensaetze zaehlen
    categories = await service.count_records_by_category(
        company_id=company.id,
        period_start=request.period_start,
        period_end=request.period_end,
    )

    tables = []
    if request.include_invoices:
        tables.append("rechnungen")
    if request.include_transactions:
        tables.append("bankbewegungen")
    if request.include_documents:
        tables.append("belege")
    if request.include_audit_log:
        tables.append("aenderungsprotokoll")

    return TaxExportPreviewResponse(
        period_start=request.period_start,
        period_end=request.period_end,
        estimated_records=sum(categories.values()),
        categories=categories,
        tables=tables,
    )


@router.post(
    "/export/tax-authority",
    summary="Tax Authority Export erstellen",
    description="Erstellt einen GDPdU-konformen Export fuer Betriebspruefungen nach §90 III AO."
)
async def create_tax_authority_export(
    request: TaxExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    company: Company = Depends(require_company),
):
    """
    Erstellt einen vollstaendigen Export fuer die Datenueberlassung
    an Finanzbehroeden nach §90 III AO / §147 VI AO.

    Der Export enthaelt:
    - index.xml: Strukturbeschreibung (GDPdU-konform)
    - DTD-Datei: Validierungsschema
    - CSV-Dateien: Tabellarische Daten
    - MD5-Pruefsummen: Integritaetssicherung

    Hinweis: Dieser Endpoint ist nur fuer Superuser zugaenglich.
    """
    from app.services.compliance.tax_authority_export_service import (
        get_tax_authority_export_service,
    )

    service = get_tax_authority_export_service(db)

    try:
        result = await service.create_gdpdu_export(
            company_id=company.id,
            period_start=request.period_start,
            period_end=request.period_end,
            output_dir=request.output_dir,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.error or "Export fehlgeschlagen",
            )

        # ZIP-Archiv zurueckgeben
        if result.archive_path:
            with open(result.archive_path, "rb") as f:
                zip_content = f.read()

            filename = (
                f"tax_authority_export_{company.name.replace(' ', '_')}_"
                f"{request.period_start.strftime('%Y%m%d')}_"
                f"{request.period_end.strftime('%Y%m%d')}.zip"
            )

            from fastapi import Response
            return Response(
                content=zip_content,
                media_type="application/zip",
                headers={
                    "Content-Disposition": build_content_disposition(filename, "attachment")
                }
            )

        # Falls kein Archiv, Metadaten zurueckgeben
        return TaxExportResultResponse(
            success=result.success,
            export_id=result.export_id,
            format=result.format.value,
            period_start=result.period_start,
            period_end=result.period_end,
            company_name=result.company_name,
            created_at=result.created_at,
            total_records=result.statistics.total_records,
            files=result.files,
            archive_path=result.archive_path,
            error=result.error,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Export")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Export")
        )


# =============================================================================
# Document Access Audit Trail Endpoints (GoBD Nachvollziehbarkeit)
# =============================================================================


class DocumentAccessLogResponse(BaseModel):
    """Response fuer einen einzelnen Dokumentzugriff."""

    id: uuid.UUID
    document_id: uuid.UUID
    user_id: Optional[uuid.UUID]
    access_type: str
    access_reason: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    success: bool
    error_message: Optional[str] = None
    bytes_transferred: Optional[int] = None
    accessed_at: datetime
    access_metadata: Optional[dict] = None
    sequence_number: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentAuditTrailResponse(BaseModel):
    """Response fuer Dokument-Audit-Trail."""

    document_id: uuid.UUID
    access_logs: list[DocumentAccessLogResponse]
    total_count: int
    has_gaps: bool
    gap_count: int
    first_access: Optional[datetime] = None
    last_access: Optional[datetime] = None


class AccessStatisticsResponse(BaseModel):
    """Response fuer Zugriffs-Statistiken."""

    total_accesses: int
    by_access_type: dict
    by_day: list[dict]
    top_documents: list[dict]
    top_users: list[dict]
    failed_access_count: int


class AuditTrailIntegrityResponse(BaseModel):
    """Response fuer Audit-Trail Integritaetspruefung."""

    is_valid: bool
    total_records: int
    expected_sequence: int
    gaps_found: list[dict]
    message: str


class AccessLogListResponse(BaseModel):
    """Paginierte Liste von Access-Logs."""

    items: list[DocumentAccessLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get(
    "/documents/{document_id}/audit-trail",
    response_model=DocumentAuditTrailResponse,
    summary="Dokument-Zugriffshistorie",
    description="Holt die vollstaendige Zugriffshistorie fuer ein Dokument (GoBD Nachvollziehbarkeit)"
)
async def get_document_audit_trail(
    document_id: uuid.UUID,
    access_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> DocumentAuditTrailResponse:
    """Holt die Zugriffshistorie fuer ein Dokument.

    GoBD-Anforderung: Nachvollziehbarkeit - Wer hat wann was mit dem Dokument gemacht?

    Args:
        document_id: ID des Dokuments
        access_type: Optionaler Filter fuer Zugriffstyp
        start_date: Optionaler Filter - Startdatum
        end_date: Optionaler Filter - Enddatum
        limit: Maximale Anzahl Ergebnisse (default: 100)
        offset: Offset fuer Paginierung (default: 0)
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        DocumentAuditTrailResponse mit Zugriffshistorie

    Raises:
        404: Dokument nicht gefunden
        403: Keine Berechtigung
    """
    # IDOR-Schutz: Pruefen ob Dokument zur Firma gehoert
    from sqlalchemy import select
    from app.db.models import Document

    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    if document.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument"
        )

    # Audit Trail abrufen
    audit_trail = await document_access_service.get_document_audit_trail(
        db=db,
        document_id=document_id,
        company_id=company.id,
        access_type=access_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return DocumentAuditTrailResponse(
        document_id=document_id,
        access_logs=[DocumentAccessLogResponse.model_validate(log) for log in audit_trail["logs"]],
        total_count=audit_trail["total_count"],
        has_gaps=audit_trail["has_gaps"],
        gap_count=audit_trail["gap_count"],
        first_access=audit_trail.get("first_access"),
        last_access=audit_trail.get("last_access"),
    )


@router.get(
    "/access-statistics",
    response_model=AccessStatisticsResponse,
    summary="Zugriffs-Statistiken",
    description="Holt aggregierte Zugriffs-Statistiken fuer die aktuelle Firma"
)
async def get_access_statistics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> AccessStatisticsResponse:
    """Holt Zugriffs-Statistiken fuer die aktuelle Firma.

    Zeigt aggregierte Statistiken ueber Dokumentzugriffe:
    - Gesamtzugriffe
    - Aufschluesselung nach Zugriffstyp
    - Tages-Verlauf
    - Top-Dokumente und Top-Benutzer

    Args:
        start_date: Optionaler Filter - Startdatum
        end_date: Optionaler Filter - Enddatum
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        AccessStatisticsResponse mit aggregierten Statistiken
    """
    stats = await document_access_service.get_company_access_statistics(
        db=db,
        company_id=company.id,
        start_date=start_date,
        end_date=end_date,
    )

    return AccessStatisticsResponse(**stats)


@router.post(
    "/verify-audit-trail",
    response_model=AuditTrailIntegrityResponse,
    summary="Audit-Trail Integritaet pruefen",
    description="Prueft die Integritaet des Audit-Trails auf Luecken (GoBD Vollstaendigkeit)"
)
async def verify_audit_trail_integrity(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    company: Company = Depends(require_company),
) -> AuditTrailIntegrityResponse:
    """Prueft die Integritaet des Audit-Trails.

    GoBD-Anforderung: Vollstaendigkeit - Der Audit-Trail muss lueckenlos sein.
    Diese Pruefung erkennt fehlende Sequenznummern.

    Nur fuer Administratoren.

    Args:
        start_date: Optionaler Filter - Startdatum
        end_date: Optionaler Filter - Enddatum
        db: Datenbank-Session
        current_user: Admin-Benutzer
        company: Aktuelle Firma

    Returns:
        AuditTrailIntegrityResponse mit Integritaetspruefung
    """
    integrity = await document_access_service.verify_audit_trail_integrity(
        db=db,
        company_id=company.id,
        start_date=start_date,
        end_date=end_date,
    )

    if integrity["is_valid"]:
        message = "Audit-Trail ist vollstaendig - keine Luecken gefunden"
    else:
        message = (
            f"WARNUNG: {len(integrity['gaps'])} Luecken im Audit-Trail gefunden! "
            f"GoBD-Vollstaendigkeit moeglicherweise verletzt."
        )

    return AuditTrailIntegrityResponse(
        is_valid=integrity["is_valid"],
        total_records=integrity["total_records"],
        expected_sequence=integrity["expected_sequence"],
        gaps_found=integrity["gaps"],
        message=message,
    )


@router.get(
    "/access-logs",
    response_model=AccessLogListResponse,
    summary="Zugriffsprotokolle (Admin)",
    description="Listet alle Zugriffsprotokolle der Firma auf (nur Admin)"
)
async def list_access_logs(
    page: int = 1,
    page_size: int = 50,
    access_type: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
    document_id: Optional[uuid.UUID] = None,
    success_only: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    company: Company = Depends(require_company),
) -> AccessLogListResponse:
    """Listet alle Zugriffsprotokolle der Firma auf.

    Paginierte Liste mit umfangreichen Filtermoglichkeiten.
    Nur fuer Administratoren.

    Args:
        page: Seitennummer (default: 1)
        page_size: Eintraege pro Seite (default: 50, max: 200)
        access_type: Optionaler Filter fuer Zugriffstyp
        user_id: Optionaler Filter fuer Benutzer
        document_id: Optionaler Filter fuer Dokument
        success_only: Optionaler Filter - nur erfolgreiche Zugriffe
        start_date: Optionaler Filter - Startdatum
        end_date: Optionaler Filter - Enddatum
        db: Datenbank-Session
        current_user: Admin-Benutzer
        company: Aktuelle Firma

    Returns:
        AccessLogListResponse mit paginierten Zugriffsprotokollen
    """
    # Paginierung limitieren
    page_size = min(page_size, 200)
    offset = (page - 1) * page_size

    # Filter zusammenstellen
    from sqlalchemy import select, func
    from app.db.models import DocumentAccessLog

    # Basis-Query
    base_query = select(DocumentAccessLog).where(
        DocumentAccessLog.company_id == company.id
    )

    if access_type:
        base_query = base_query.where(DocumentAccessLog.access_type == access_type)
    if user_id:
        base_query = base_query.where(DocumentAccessLog.user_id == user_id)
    if document_id:
        base_query = base_query.where(DocumentAccessLog.document_id == document_id)
    if success_only is not None:
        base_query = base_query.where(DocumentAccessLog.success == success_only)
    if start_date:
        base_query = base_query.where(DocumentAccessLog.accessed_at >= start_date)
    if end_date:
        base_query = base_query.where(DocumentAccessLog.accessed_at <= end_date)

    # Count Query
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Data Query mit Paginierung
    data_query = base_query.order_by(
        DocumentAccessLog.accessed_at.desc()
    ).offset(offset).limit(page_size)

    result = await db.execute(data_query)
    logs = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    return AccessLogListResponse(
        items=[DocumentAccessLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# =============================================================================
# GoBD Compliance Report Endpoints
# =============================================================================


class ComplianceReportResponse(BaseModel):
    """Response fuer GoBD-Compliance-Bericht."""

    report_id: str
    company_id: str
    report_date: str
    generated_at: str
    overall_status: str
    overall_score: float
    score_description: str
    summary: dict
    recommendations: list
    legal_basis: list
    details: Optional[dict] = None


class QuickComplianceResponse(BaseModel):
    """Response fuer schnellen Compliance-Status."""

    status: str
    failed_verifications: int
    audit_trail_gaps: int
    checked_at: str


@router.get(
    "/compliance/report",
    response_model=ComplianceReportResponse,
    summary="GoBD-Compliance-Bericht",
    description="Generiert einen vollstaendigen GoBD-Compliance-Bericht"
)
async def get_compliance_report(
    report_date: Optional[date] = None,
    include_details: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> ComplianceReportResponse:
    """Generiert einen GoBD-Compliance-Bericht.

    Der Bericht umfasst:
    - Archivierungsstatus (Anteil archivierter Dokumente, Hash-Signaturen)
    - Aufbewahrungsfristen-Compliance (abgelaufen, bald ablaufend)
    - Audit-Trail-Vollstaendigkeit (Nachvollziehbarkeit)
    - Integritaetspruefungen (Unveraenderbarkeit)
    - Gesamt-Score und Handlungsempfehlungen

    Args:
        report_date: Stichtag fuer den Bericht (default: heute)
        include_details: Detaillierte Metriken einschliessen
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        ComplianceReportResponse mit vollstaendigem Bericht
    """
    report = await gobd_compliance_service.generate_compliance_report(
        db=db,
        company_id=company.id,
        report_date=report_date,
        include_details=include_details,
    )

    return ComplianceReportResponse(**report)


@router.get(
    "/compliance/status",
    response_model=QuickComplianceResponse,
    summary="Schneller Compliance-Status",
    description="Gibt einen schnellen Compliance-Status zurueck (fuer Dashboard)"
)
async def get_quick_compliance_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> QuickComplianceResponse:
    """Gibt einen schnellen Compliance-Status zurueck.

    Fuer Dashboard-Widgets und Uebersichten.
    Prueft nur die kritischsten Metriken.

    Args:
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        QuickComplianceResponse mit Status und kritischen Metriken
    """
    status = await gobd_compliance_service.get_quick_compliance_status(
        db=db,
        company_id=company.id,
    )

    return QuickComplianceResponse(**status)


@router.get(
    "/compliance/export",
    summary="Compliance-Bericht als PDF exportieren",
    description="Exportiert den GoBD-Compliance-Bericht als PDF (fuer Steuerberater)"
)
async def export_compliance_report_pdf(
    report_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """Exportiert den Compliance-Bericht als PDF.

    Fuer Steuerberater und Betriebspruefungen.

    Args:
        report_date: Stichtag fuer den Bericht
        db: Datenbank-Session
        current_user: Aktueller Benutzer
        company: Aktuelle Firma

    Returns:
        PDF-Datei als Download
    """
    from fastapi.responses import Response

    # Generiere Bericht
    report = await gobd_compliance_service.generate_compliance_report(
        db=db,
        company_id=company.id,
        report_date=report_date,
        include_details=True,
    )

    # Erzeuge Markdown-Inhalt (PDF-Generierung wuerde externe Library benoetigen)
    markdown = _generate_compliance_markdown(report, company.name)

    filename = (
        f"gobd_compliance_{company.name.replace(' ', '_')}_"
        f"{report['report_date']}.md"
    )

    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": build_content_disposition(filename, "attachment")
        }
    )


def _generate_compliance_markdown(report: dict, company_name: str) -> str:
    """Generiert Markdown-Inhalt fuer den Compliance-Bericht."""
    lines = [
        f"# GoBD-Compliance-Bericht",
        f"",
        f"**Firma:** {company_name}",
        f"**Stichtag:** {report['report_date']}",
        f"**Erstellt am:** {report['generated_at']}",
        f"",
        f"---",
        f"",
        f"## Zusammenfassung",
        f"",
        f"| Metrik | Wert |",
        f"|--------|------|",
        f"| **Gesamt-Status** | {report['overall_status'].upper()} |",
        f"| **Compliance-Score** | {report['overall_score']}/100 |",
        f"| **Bewertung** | {report['score_description']} |",
        f"",
        f"### Bereichs-Uebersicht",
        f"",
        f"| Bereich | Status | Compliant | Warnung | Non-Compliant |",
        f"|---------|--------|-----------|---------|---------------|",
    ]

    for area_name, area_data in report['summary'].items():
        lines.append(
            f"| {area_name.replace('_', ' ').title()} | "
            f"{area_data['status'].upper()} | "
            f"{area_data.get('compliant', 0)} | "
            f"{area_data.get('warning', 0)} | "
            f"{area_data.get('non_compliant', 0)} |"
        )

    lines.extend([
        f"",
        f"---",
        f"",
        f"## Handlungsempfehlungen",
        f"",
    ])

    if report['recommendations']:
        for rec in report['recommendations']:
            severity_emoji = "🔴" if rec['severity'] == 'non_compliant' else "🟡"
            lines.append(f"{rec['priority']}. {severity_emoji} **{rec['metric']}**: {rec['recommendation']}")
    else:
        lines.append("✅ Keine Handlungsempfehlungen - alle Pruefungen bestanden!")

    lines.extend([
        f"",
        f"---",
        f"",
        f"## Rechtliche Grundlagen",
        f"",
    ])

    for basis in report['legal_basis']:
        lines.append(f"- **{basis['law']}**: {basis['description']}")

    if 'details' in report and report['details']:
        lines.extend([
            f"",
            f"---",
            f"",
            f"## Details",
            f"",
        ])

        for area_name, metrics in report['details'].items():
            lines.append(f"### {area_name.replace('_', ' ').title()}")
            lines.append("")
            lines.append("| Metrik | Wert | Status | Beschreibung |")
            lines.append("|--------|------|--------|--------------|")

            for metric in metrics:
                status_icon = (
                    "✅" if metric['status'] == 'compliant'
                    else "⚠️" if metric['status'] == 'warning'
                    else "❌"
                )
                lines.append(
                    f"| {metric['name']} | {metric['value']} | "
                    f"{status_icon} | {metric['description'][:50]}... |"
                )

            lines.append("")

    lines.extend([
        f"",
        f"---",
        f"",
        f"*Dieser Bericht wurde automatisch generiert. "
        f"Bei Fragen wenden Sie sich an Ihren Steuerberater.*",
    ])

    return "\n".join(lines)

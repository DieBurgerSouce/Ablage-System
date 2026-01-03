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
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user, get_current_superuser
from app.core.exceptions import (
    DocumentNotFoundError,
    ArchiveError,
    ImmutabilityViolationError,
)
from app.db.models import User, RetentionCategory
from app.middleware.company_context import require_company, Company
from app.services.archive_service import archive_service
from app.services.procedure_doc_service import procedure_doc_service
from app.services.gdpdu_export_service import gdpdu_export_service, GDPdUExportOptions

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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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
    """
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
        is_verified = await archive_service.verify_document_integrity(db, document_id)
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

    class Config:
        from_attributes = True


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
) -> ProcedureDocDetailResponse:
    """Holt eine bestimmte Version.

    Args:
        version_id: Versions-ID
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        Dokumentationsversion

    Raises:
        404: Version nicht gefunden
    """
    version = await procedure_doc_service.get_version_by_id(db, version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version nicht gefunden"
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
):
    """Exportiert die Verfahrensdokumentation als Markdown.

    Args:
        version_id: Versions-ID
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        Markdown-Datei
    """
    from fastapi.responses import Response

    try:
        markdown = await procedure_doc_service.export_as_markdown(db, version_id)
        return Response(
            content=markdown,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=verfahrensdokumentation_{version_id}.md"
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
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
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

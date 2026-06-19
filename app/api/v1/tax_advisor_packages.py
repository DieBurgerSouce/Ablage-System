"""
Steuerberater-Paket API Endpoints.

API für automatische Buchhaltungspakete:
- Konfigurationen erstellen und verwalten
- Pakete erstellen und generieren
- Pakete herunterladen
- Fehlende Dokumente identifizieren
- Push-Benachrichtigungen

GoBD-Konformität garantiert.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_user, get_current_superuser
from app.api.dependencies import get_user_company_id  # F-31 company-id resolution
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.core.security_auth import build_content_disposition
from app.db.models import User, Company
from app.middleware.company_context import require_company
from app.services.tax_advisor_package_service import (
    TaxAdvisorPackageService,
    PackageConfiguration,
    TaxAdvisorPackage,
    PackageFrequency,
    PackageStatus,
    MissingDocument,
    MissingDocumentType,
    MissingItem,
    CompletenessReport,
    get_tax_advisor_package_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tax-advisor/packages", tags=["Steuerberater-Pakete"])


# ==================== Pydantic Schemas ====================


class PackageConfigurationCreate(BaseModel):
    """Schema zum Erstellen einer Paket-Konfiguration."""

    name: str = Field(..., min_length=3, max_length=100, description="Name der Konfiguration")
    frequency: str = Field("monthly", description="Häufigkeit: monthly, quarterly, yearly, on_demand")
    document_categories: Optional[List[str]] = Field(
        None,
        description="Dokumentkategorien (default: alle relevanten)"
    )

    period_start_day: int = Field(1, ge=1, le=28, description="Tag des Monats für Periodenstart")
    delivery_delay_days: int = Field(5, ge=1, le=30, description="Tage nach Periodenende bis Versand")

    auto_send: bool = Field(True, description="Automatischer Versand")
    auto_reminder: bool = Field(True, description="Automatische Erinnerungen")
    reminder_days_before: int = Field(3, ge=1, le=14, description="Tage vor Deadline für Erinnerung")

    recipient_email: Optional[EmailStr] = Field(None, description="E-Mail für Versand")
    tax_advisor_user_id: Optional[UUID] = Field(None, description="Steuerberater-User-ID")

    include_datev_export: bool = Field(True, description="DATEV-Export einschließen")
    include_pdf_copies: bool = Field(True, description="PDF-Kopien einschließen")
    include_summary_report: bool = Field(True, description="Zusammenfassung einschließen")


class PackageConfigurationResponse(BaseModel):
    """Antwort-Schema für Paket-Konfiguration."""

    id: UUID
    company_id: UUID
    name: str
    frequency: str
    document_categories: List[str]
    period_start_day: int
    delivery_delay_days: int
    auto_send: bool
    auto_reminder: bool
    reminder_days_before: int
    recipient_email: Optional[str]
    tax_advisor_user_id: Optional[UUID]
    include_datev_export: bool
    include_pdf_copies: bool
    include_summary_report: bool
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_config(cls, config: PackageConfiguration) -> "PackageConfigurationResponse":
        return cls(
            id=config.id,
            company_id=config.company_id,
            name=config.name,
            frequency=config.frequency.value,
            document_categories=config.document_categories,
            period_start_day=config.period_start_day,
            delivery_delay_days=config.delivery_delay_days,
            auto_send=config.auto_send,
            auto_reminder=config.auto_reminder,
            reminder_days_before=config.reminder_days_before,
            recipient_email=config.recipient_email,
            tax_advisor_user_id=config.tax_advisor_user_id,
            include_datev_export=config.include_datev_export,
            include_pdf_copies=config.include_pdf_copies,
            include_summary_report=config.include_summary_report,
            is_active=config.is_active,
            created_at=config.created_at,
        )


class PackageCreateRequest(BaseModel):
    """Schema zum Erstellen eines Pakets."""

    period: str = Field(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2]|Q[1-4])$",
        description="Zeitraum: YYYY-MM oder YYYY-QN (z.B. 2026-01, 2026-Q1)"
    )
    config_id: Optional[UUID] = Field(None, description="Konfiguration (optional)")


class MissingDocumentResponse(BaseModel):
    """Schema für fehlendes Dokument."""

    document_type: str
    description: str
    expected_date: Optional[str]
    importance: str
    notes: Optional[str]


class PackageResponse(BaseModel):
    """Antwort-Schema für Paket."""

    id: UUID
    configuration_id: Optional[UUID]
    company_id: UUID
    period_start: str
    period_end: str
    period_label: str
    status: str
    document_count: int
    total_size_bytes: int
    datev_export_path: Optional[str]
    pdf_archive_path: Optional[str]
    summary_report_path: Optional[str]
    created_at: datetime
    sent_at: Optional[datetime]
    downloaded_at: Optional[datetime]
    expires_at: Optional[datetime]
    missing_documents: List[MissingDocumentResponse]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_package(cls, package: TaxAdvisorPackage) -> "PackageResponse":
        return cls(
            id=package.id,
            configuration_id=package.configuration_id if package.configuration_id != UUID("00000000-0000-0000-0000-000000000000") else None,
            company_id=package.company_id,
            period_start=package.period_start.isoformat(),
            period_end=package.period_end.isoformat(),
            period_label=package.period_label,
            status=package.status.value,
            document_count=package.document_count,
            total_size_bytes=package.total_size_bytes,
            datev_export_path=package.datev_export_path,
            pdf_archive_path=package.pdf_archive_path,
            summary_report_path=package.summary_report_path,
            created_at=package.created_at,
            sent_at=package.sent_at,
            downloaded_at=package.downloaded_at,
            expires_at=package.expires_at,
            missing_documents=[
                MissingDocumentResponse(
                    document_type=doc.get("document_type", "other"),
                    description=doc.get("description", ""),
                    expected_date=doc.get("expected_date"),
                    importance=doc.get("importance", "required"),
                    notes=doc.get("notes"),
                )
                for doc in package.missing_documents
            ],
        )


class SendPackageRequest(BaseModel):
    """Schema zum Versenden eines Pakets."""

    recipient_email: Optional[EmailStr] = Field(None, description="Optionale E-Mail (sonst aus Konfiguration)")


class ReminderRequest(BaseModel):
    """Schema für Erinnerung."""

    admin_email: EmailStr = Field(..., description="E-Mail für Benachrichtigung")
    tax_advisor_name: Optional[str] = Field(None, description="Name des Steuerberaters")


class MessageResponse(BaseModel):
    """Einfache Nachricht-Antwort."""

    message: str
    details: Optional[dict] = None


class MissingItemResponse(BaseModel):
    """Schema für fehlendes Element."""

    category: str
    description: str
    severity: str
    suggestion: str


class CompletenessReportResponse(BaseModel):
    """Schema für Vollständigkeits-Bericht."""

    period: str
    period_start: str
    period_end: str
    completeness_score: float = Field(..., ge=0.0, le=100.0)
    checks_passed: int
    total_checks: int
    missing_items: List[MissingItemResponse]
    is_complete: bool

    @classmethod
    def from_report(cls, report: CompletenessReport) -> "CompletenessReportResponse":
        return cls(
            period=report.period,
            period_start=report.period_start.isoformat(),
            period_end=report.period_end.isoformat(),
            completeness_score=report.completeness_score,
            checks_passed=report.checks_passed,
            total_checks=report.total_checks,
            missing_items=[
                MissingItemResponse(
                    category=item.category,
                    description=item.description,
                    severity=item.severity,
                    suggestion=item.suggestion,
                )
                for item in report.missing_items
            ],
            is_complete=report.is_complete,
        )


# ==================== In-Memory Storage (simplified for MVP) ====================

# In Produktion: DB-Modelle verwenden
_packages: dict[UUID, TaxAdvisorPackage] = {}


# ==================== Configuration Endpoints ====================


@router.post(
    "/configurations",
    response_model=PackageConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Paket-Konfiguration erstellen",
    description="Erstellt eine neue Konfiguration für automatische Steuerberater-Pakete"
)
async def create_configuration(
    data: PackageConfigurationCreate,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> PackageConfigurationResponse:
    """
    Erstellt eine neue Paket-Konfiguration.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    try:
        frequency = PackageFrequency(data.frequency)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültige Häufigkeit: {data.frequency}. Erlaubt: monthly, quarterly, yearly, on_demand"
        )

    service = get_tax_advisor_package_service(db)

    config = await service.create_configuration(
        company_id=company_id,
        name=data.name,
        frequency=frequency,
        document_categories=data.document_categories,
        recipient_email=data.recipient_email,
        tax_advisor_user_id=data.tax_advisor_user_id,
        period_start_day=data.period_start_day,
        delivery_delay_days=data.delivery_delay_days,
        auto_send=data.auto_send,
        auto_reminder=data.auto_reminder,
        reminder_days_before=data.reminder_days_before,
        include_datev_export=data.include_datev_export,
        include_pdf_copies=data.include_pdf_copies,
        include_summary_report=data.include_summary_report,
    )

    logger.info(
        "package_configuration_created_via_api",
        config_id=str(config.id),
        company_id=str(company_id),
        created_by=str(current_user.id),
    )

    return PackageConfigurationResponse.from_config(config)


@router.get(
    "/configurations",
    response_model=List[PackageConfigurationResponse],
    summary="Konfigurationen auflisten",
    description="Listet alle Paket-Konfigurationen für die aktuelle Firma"
)
async def list_configurations(
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[PackageConfigurationResponse]:
    """
    Listet alle Paket-Konfigurationen.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    service = get_tax_advisor_package_service(db)
    configs = await service.get_configurations_for_company(company_id)

    return [PackageConfigurationResponse.from_config(c) for c in configs]


@router.get(
    "/configurations/{config_id}",
    response_model=PackageConfigurationResponse,
    summary="Konfiguration abrufen",
    description="Ruft eine spezifische Paket-Konfiguration ab"
)
async def get_configuration(
    config_id: UUID,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> PackageConfigurationResponse:
    """
    Ruft eine Konfiguration ab.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    service = get_tax_advisor_package_service(db)
    config = await service.get_configuration(config_id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    if config.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Konfiguration"
        )

    return PackageConfigurationResponse.from_config(config)


# ==================== Package Endpoints ====================


@router.post(
    "",
    response_model=PackageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Paket erstellen",
    description="Erstellt ein neues Buchhaltungspaket für einen Zeitraum"
)
async def create_package(
    data: PackageCreateRequest,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> PackageResponse:
    """
    Erstellt ein neues Buchhaltungspaket.

    Der Zeitraum kann als Monat (YYYY-MM) oder Quartal (YYYY-QN) angegeben werden.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    service = get_tax_advisor_package_service(db)

    try:
        package = await service.create_package_for_period(
            company_id=company_id,
            period=data.period,
            config_id=data.config_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Steuerberater-Paket")
        )

    # In-Memory speichern (in Produktion: DB)
    _packages[package.id] = package

    logger.info(
        "package_created_via_api",
        package_id=str(package.id),
        company_id=str(company_id),
        period=data.period,
        created_by=str(current_user.id),
    )

    return PackageResponse.from_package(package)


@router.get(
    "",
    response_model=List[PackageResponse],
    summary="Pakete auflisten",
    description="Listet alle Pakete für die aktuelle Firma"
)
async def list_packages(
    status_filter: Optional[str] = Query(None, description="Nach Status filtern"),
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[PackageResponse]:
    """
    Listet alle Pakete.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    packages = [
        p for p in _packages.values()
        if p.company_id == company_id
    ]

    if status_filter:
        try:
            filter_status = PackageStatus(status_filter)
            packages = [p for p in packages if p.status == filter_status]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Status: {status_filter}"
            )

    # Nach Erstelldatum sortieren (neueste zuerst)
    packages.sort(key=lambda p: p.created_at, reverse=True)

    return [PackageResponse.from_package(p) for p in packages]


@router.get(
    "/{package_id}",
    response_model=PackageResponse,
    summary="Paket abrufen",
    description="Ruft ein spezifisches Paket ab"
)
async def get_package(
    package_id: UUID,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PackageResponse:
    """
    Ruft ein Paket ab.

    Zugaenglich für Administratoren und zugeordnete Steuerberater.
    """
    company_id = company.id
    package = _packages.get(package_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden"
        )

    # Berechtigungsprüfung
    if package.company_id != company_id:
        # Steuerberater können zugeordnete Pakete sehen
        if not current_user.is_superuser and not current_user.is_tax_advisor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für dieses Paket"
            )

    return PackageResponse.from_package(package)


@router.post(
    "/{package_id}/generate",
    response_model=PackageResponse,
    summary="Paket-Dateien generieren",
    description="Generiert DATEV-Export, PDF-Archiv und Zusammenfassung"
)
async def generate_package(
    package_id: UUID,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> PackageResponse:
    """
    Generiert die Paket-Dateien.

    Erstellt DATEV-Export, PDF-Archiv und Zusammenfassungs-Bericht.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    package = _packages.get(package_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden"
        )

    if package.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für dieses Paket"
        )

    service = get_tax_advisor_package_service(db)
    package = await service.generate_package_files(package)

    # In-Memory aktualisieren
    _packages[package_id] = package

    logger.info(
        "package_generated_via_api",
        package_id=str(package_id),
        company_id=str(company_id),
        generated_by=str(current_user.id),
    )

    return PackageResponse.from_package(package)


@router.post(
    "/{package_id}/send",
    response_model=MessageResponse,
    summary="Paket versenden",
    description="Versendet das Paket per E-Mail an den Steuerberater"
)
async def send_package(
    package_id: UUID,
    data: SendPackageRequest,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Versendet ein Paket per E-Mail.

    Das Paket muss den Status 'ready' haben.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    package = _packages.get(package_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden"
        )

    if package.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für dieses Paket"
        )

    if package.status != PackageStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Paket kann nicht versendet werden (Status: {package.status.value})"
        )

    service = get_tax_advisor_package_service(db)
    success = await service.send_package(package, data.recipient_email)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Paket konnte nicht versendet werden"
        )

    # In-Memory aktualisieren
    _packages[package_id] = package

    logger.info(
        "package_sent_via_api",
        package_id=str(package_id),
        company_id=str(company_id),
        sent_by=str(current_user.id),
    )

    return MessageResponse(
        message="Paket erfolgreich versendet",
        details={
            "package_id": str(package_id),
            "sent_at": package.sent_at.isoformat() if package.sent_at else None,
        }
    )


@router.get(
    "/{package_id}/download",
    summary="Paket herunterladen",
    description="Laedt das Paket-Archiv herunter"
)
async def download_package(
    package_id: UUID,
    file_type: str = Query("all", description="Dateityp: all, datev, pdf, report"),
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Laedt Paket-Dateien herunter.

    Zugaenglich für Administratoren und zugeordnete Steuerberater.
    """
    company_id = company.id
    package = _packages.get(package_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden"
        )

    # Berechtigungsprüfung
    if package.company_id != company_id:
        if not current_user.is_superuser and not current_user.is_tax_advisor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für dieses Paket"
            )

    # Ablauf prüfen
    if package.expires_at and package.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Download-Link ist abgelaufen"
        )

    # Dateipfad bestimmen
    file_paths = {
        "datev": package.datev_export_path,
        "pdf": package.pdf_archive_path,
        "report": package.summary_report_path,
    }

    if file_type == "all":
        # In Praxis: Alle Dateien in ZIP zusammenfassen
        # Hier vereinfacht: DATEV-Export zurückgeben
        file_path = package.datev_export_path
        filename = f"paket_{package.period_label.replace('/', '-')}_komplett.zip"
    elif file_type in file_paths:
        file_path = file_paths[file_type]
        filename = f"paket_{package.period_label.replace('/', '-')}_{file_type}.zip"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Dateityp: {file_type}"
        )

    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Datei nicht verfügbar: {file_type}"
        )

    # Download-Tracking
    package.downloaded_at = datetime.now(timezone.utc)
    package.status = PackageStatus.DOWNLOADED
    _packages[package_id] = package

    logger.info(
        "package_downloaded",
        package_id=str(package_id),
        file_type=file_type,
        downloaded_by=str(current_user.id),
    )

    # In Praxis: FileResponse mit tatsaechlicher Datei
    # Hier: JSON-Response für MVP
    return Response(
        content=f"Download für {filename} (Pfad: {file_path})",
        media_type="text/plain",
        headers={
            "Content-Disposition": build_content_disposition(filename, "attachment"),
        }
    )


# ==================== Notification Endpoints ====================


@router.post(
    "/{package_id}/remind",
    response_model=MessageResponse,
    summary="Erinnerung senden",
    description="Sendet eine Erinnerung für fehlende Dokumente"
)
async def send_reminder(
    package_id: UUID,
    data: ReminderRequest,
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Sendet eine Erinnerung für fehlende Dokumente.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    package = _packages.get(package_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden"
        )

    if package.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für dieses Paket"
        )

    if not package.missing_documents:
        return MessageResponse(
            message="Keine fehlenden Dokumente - keine Erinnerung notwendig"
        )

    service = get_tax_advisor_package_service(db)
    success = await service.send_missing_documents_notification(
        package=package,
        admin_email=data.admin_email,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erinnerung konnte nicht gesendet werden"
        )

    # In-Memory aktualisieren
    _packages[package_id] = package

    logger.info(
        "package_reminder_sent",
        package_id=str(package_id),
        company_id=str(company_id),
        sent_by=str(current_user.id),
    )

    return MessageResponse(
        message="Erinnerung erfolgreich gesendet",
        details={
            "package_id": str(package_id),
            "missing_count": len(package.missing_documents),
            "reminder_sent_at": package.reminder_sent_at.isoformat() if package.reminder_sent_at else None,
        }
    )


# ==================== Statistics Endpoints ====================


@router.get(
    "/statistics/summary",
    summary="Paket-Statistiken",
    description="Zeigt Statistiken über erstellte Pakete"
)
async def get_package_statistics(
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Zeigt Statistiken über Pakete.

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    packages = [p for p in _packages.values() if p.company_id == company_id]

    # Statistiken berechnen
    total = len(packages)
    by_status = {}
    total_documents = 0
    total_size = 0
    packages_with_missing = 0

    for p in packages:
        by_status[p.status.value] = by_status.get(p.status.value, 0) + 1
        total_documents += p.document_count
        total_size += p.total_size_bytes
        if p.missing_documents:
            packages_with_missing += 1

    return {
        "total_packages": total,
        "by_status": by_status,
        "total_documents": total_documents,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2) if total_size > 0 else 0,
        "packages_with_missing_documents": packages_with_missing,
        "completion_rate": round((total - packages_with_missing) / total * 100, 1) if total > 0 else 100,
    }


# ==================== Completeness Check (Feature #9) ====================


@router.post(
    "/completeness-check",
    response_model=CompletenessReportResponse,
    summary="Vollständigkeits-Check",
    description="Prüft die Vollständigkeit der Dokumente für einen Zeitraum"
)
async def check_completeness(
    year: int = Query(..., ge=2020, le=2030, description="Jahr (z.B. 2026)"),
    quarter: Optional[int] = Query(None, ge=1, le=4, description="Quartal (1-4), None = ganzes Jahr"),
    company: Company = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> CompletenessReportResponse:
    """
    Prüft die Vollständigkeit der Dokumente für einen Zeitraum.

    **Checks:**
    - Alle Monate haben Kontoauszuege
    - Rechnungen haben Zahlungen oder sind als offen markiert
    - Pflichtdokumente sind vorhanden (Eingangs-/Ausgangsrechnungen)
    - DATEV-Export ist validierungsbereit
    - Keine Compliance-Issues

    **Completeness-Score:**
    - 100% = Alle Checks bestanden
    - 80-99% = Kleine Maengel (recommended)
    - <80% = Grosse Maengel (required)

    **Parameter:**
    - `year`: Jahr (2020-2030)
    - `quarter`: Optional Quartal (1-4), None = ganzes Jahr

    Nur für Administratoren zugaenglich.
    """
    company_id = company.id
    try:
        service = get_tax_advisor_package_service(db)
        report = await service.check_completeness(
            company_id=company_id,
            year=year,
            quarter=quarter,
        )

        logger.info(
            "completeness_check_performed",
            company_id=str(company_id),
            year=year,
            quarter=quarter,
            score=report.completeness_score,
            user_id=str(current_user.id),
        )

        return CompletenessReportResponse.from_report(report)

    except Exception as e:
        logger.error(
            "completeness_check_api_error",
            company_id=str(company_id),
            year=year,
            quarter=quarter,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vollständigkeits-Check"),
        )

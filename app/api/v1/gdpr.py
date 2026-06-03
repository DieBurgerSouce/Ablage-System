"""
GDPR API Endpoints - Art. 6, 7, 15-21 DSGVO.

Implementiert:
- Art. 6, 7: Einwilligungsverwaltung (Consent Management)
- Art. 15: Recht auf Auskunft (Right to Access)
- Art. 16: Recht auf Berichtigung (Right to Rectification)
- Art. 17: Recht auf Löschung (Right to Erasure)
- Art. 18: Recht auf Einschränkung (Right to Restriction)
- Art. 20: Recht auf Datenübertragbarkeit (Data Portability)
- Art. 21: Widerspruchsrecht (Right to Object)

Alle Antworten auf Deutsch für Benutzerfreundlichkeit.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

# SECURITY FIX 27-7: Rate Limiting für GDPR Endpoints
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_detail, safe_error_log

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.db.models import User
from app.db.schemas import (
    DeletionRequestCreate,
    DeletionStatusResponse,
    DeletionCancelRequest,
    DeletionExecutionResponse,
    DeletionExecutionStats,
    MessageResponse,
    ExportRequestCreate,
    ExportStatusResponse,
    ExportListResponse
)
from app.services.gdpr_service import get_gdpr_service, GDPRService
from app.services.data_export_service import get_data_export_service, DataExportService
from app.core.exceptions import GDPRError, UserNotFoundError, ExportError
from app.services.compliance import (
    ConsentManagementService,
    consent_management_service,
    get_consent_management_service,
    ConsentScope,
    ConsentMethod,
    ConsentStatus,
    DataSubjectRightsService,
    data_subject_rights_service,
    get_data_subject_rights_service,
    DSRType,
    DSRStatus,
    DataCategory,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users/me/gdpr", tags=["GDPR"])


# ==================== Art. 17 - Recht auf Löschung ====================

# SECURITY FIX 27-7: Rate-Limit für Account-Löschung - nur 3x pro Tag!
@limiter.limit("3/day", key_func=get_user_identifier)
@router.post(
    "/request-deletion",
    response_model=DeletionStatusResponse,
    summary="Kontolöschung anfordern",
    description="Art. 17 DSGVO - Recht auf Löschung. "
                "Nach Bestätigung wird das Konto nach 30 Tagen gelöscht."
)
async def request_account_deletion(
    request: Request,  # SECURITY FIX 27-7: Required for rate limiter
    deletion_request: DeletionRequestCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DeletionStatusResponse:
    """
    Art. 17 DSGVO - Löschung des Benutzerkontos anfordern.

    Nach Bestätigung wird das Konto nach 30 Tagen gelöscht.
    Innerhalb dieser Frist kann die Löschung abgebrochen werden.

    Args:
        request: Löschanfrage mit Bestätigung
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Status der Löschanfrage

    Raises:
        400: Bestätigung fehlt
        409: Bereits Löschantrag vorhanden
    """
    gdpr_service = get_gdpr_service()

    try:
        scheduled_for = await gdpr_service.request_deletion(
            db, current_user.id, deletion_request.reason
        )

        now = datetime.now(timezone.utc)
        days_remaining = (scheduled_for - now).days

        formatted_date = scheduled_for.strftime('%d.%m.%Y')

        logger.info(
            "gdpr_deletion_requested_via_api",
            user_id=str(current_user.id)[:8] + "...",
            days_remaining=days_remaining
        )

        return DeletionStatusResponse(
            deletion_requested=True,
            deletion_requested_at=now,
            deletion_scheduled_for=scheduled_for,
            days_remaining=days_remaining,
            can_cancel=True,
            nachricht=f"Ihr Konto wird am {formatted_date} gelöscht. "
                      f"Sie können die Löschung innerhalb von {days_remaining} Tagen abbrechen."
        )
    except GDPRError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e.user_message_de)
        )


@router.get(
    "/deletion-status",
    response_model=DeletionStatusResponse,
    summary="Löschstatus abfragen",
    description="Zeigt den aktuellen Status einer Löschanfrage"
)
async def get_deletion_status(
    current_user: User = Depends(get_current_active_user)
) -> DeletionStatusResponse:
    """
    Status der Löschanfrage abrufen.

    Args:
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Aktueller Löschstatus
    """
    gdpr_service = get_gdpr_service()
    status_data = await gdpr_service.get_deletion_status(current_user)

    return DeletionStatusResponse(**status_data)


@router.post(
    "/cancel-deletion",
    response_model=MessageResponse,
    summary="Löschanfrage abbrechen",
    description="Zieht eine Löschanfrage innerhalb der 30-Tage-Frist zurück"
)
async def cancel_deletion(
    request: Optional[DeletionCancelRequest] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """
    Löschanfrage zurückziehen.

    Nur möglich innerhalb der 30-Tage-Widerrufsfrist.

    Args:
        request: Optionaler Abbruchgrund
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Bestätigungsnachricht

    Raises:
        400: Kein aktiver Antrag oder Frist abgelaufen
    """
    gdpr_service = get_gdpr_service()

    try:
        await gdpr_service.cancel_deletion(db, current_user.id)

        logger.info(
            "gdpr_deletion_cancelled_via_api",
            user_id=str(current_user.id)[:8] + "..."
        )

        return MessageResponse(
            message="Löschantrag erfolgreich zurückgezogen",
            detail="Ihr Konto wird nicht gelöscht. Sie können es weiterhin normal nutzen."
        )
    except GDPRError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.user_message_de)
        )


# ==================== Admin Endpoints ====================

admin_router = APIRouter(prefix="/admin/gdpr", tags=["Admin - GDPR"])


@admin_router.delete(
    "/users/{user_id}",
    response_model=DeletionExecutionResponse,
    summary="Benutzer sofort löschen (Admin)",
    description="Führt sofortige Löschung eines Benutzerkontos durch (nur Admins)"
)
async def admin_delete_user(
    user_id: UUID,
    hard_delete: bool = Query(
        False,
        description="True = physische Löschung, False = Anonymisierung"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DeletionExecutionResponse:
    """
    Admin: Sofortige Löschung eines Benutzerkontos.

    ACHTUNG: Diese Aktion ist unwiderruflich!

    Args:
        user_id: ID des zu löschenden Benutzers
        hard_delete: Physische Löschung vs. Anonymisierung
        current_user: Admin-Benutzer
        db: Datenbank-Session

    Returns:
        Löschstatistiken

    Raises:
        403: Nicht autorisiert
        404: Benutzer nicht gefunden
    """
    # Admin-Check
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Benutzer löschen"
        )

    gdpr_service = get_gdpr_service()

    try:
        stats = await gdpr_service.execute_deletion(db, user_id, hard_delete)

        logger.warning(
            "gdpr_admin_deletion_executed",
            target_user_id=str(user_id)[:8] + "...",
            admin_id=str(current_user.id)[:8] + "...",
            hard_delete=hard_delete,
            stats=stats
        )

        return DeletionExecutionResponse(
            success=True,
            user_id=user_id,
            stats=DeletionExecutionStats(
                documents_deleted=stats["documents"],
                api_keys_deleted=stats["api_keys"],
                audit_logs_anonymized=stats["audit_logs"],
                user_deleted=True,
                hard_delete=hard_delete
            ),
            nachricht=f"Benutzer erfolgreich {'gelöscht' if hard_delete else 'anonymisiert'}. "
                      f"Dokumente: {stats['documents']}, API-Keys: {stats['api_keys']}, "
                      f"Audit-Logs anonymisiert: {stats['audit_logs']}"
        )
    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden"
        )
    except GDPRError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.user_message_de)
        )


@admin_router.get(
    "/pending-deletions",
    summary="Fällige Löschanfragen anzeigen",
    description="Zeigt alle Benutzer mit fälligen Löschanfragen"
)
async def get_pending_deletions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Admin: Liste aller fälligen Löschanfragen.

    Args:
        current_user: Admin-Benutzer
        db: Datenbank-Session

    Returns:
        Liste der fälligen Löschungen
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können diese Information abrufen"
        )

    gdpr_service = get_gdpr_service()
    pending = await gdpr_service.get_pending_deletions(db)

    return {
        "total": len(pending),
        "pending_deletions": [
            {
                "user_id": str(user.id),
                "email": user.email[:3] + "***@***",  # Teilweise maskiert
                "deletion_scheduled_for": user.deletion_scheduled_for.isoformat() if user.deletion_scheduled_for else None,
                "reason": user.deletion_reason[:50] + "..." if user.deletion_reason and len(user.deletion_reason) > 50 else user.deletion_reason
            }
            for user in pending
        ]
    }


# ==================== Art. 20 - Datenportabilität ====================

@router.post(
    "/request-export",
    response_model=ExportStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Datenexport anfordern",
    description="Art. 20 DSGVO - Recht auf Datenübertragbarkeit. "
                "Exportiert alle Ihre Daten in maschinenlesbarem Format."
)
async def request_data_export(
    request: ExportRequestCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> ExportStatusResponse:
    """
    Art. 20 DSGVO - Datenexport anfordern.

    Erstellt einen Export aller Benutzerdaten in einem
    strukturierten, maschinenlesbaren Format (JSON/CSV).

    Der Export wird asynchron erstellt und ist 7 Tage gültig.

    Args:
        request: Export-Anfrage mit Format-Auswahl
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Export-Status

    Raises:
        409: Bereits ein Export in Bearbeitung
    """
    export_service = get_data_export_service()

    try:
        export = await export_service.create_export_request(
            db, current_user.id, request.format
        )

        # Trigger Celery task for async processing
        # from app.workers.tasks.gdpr_tasks import generate_export_task
        # generate_export_task.delay(str(export.id))

        # For now: synchronous generation (can be moved to Celery later)
        export = await export_service.generate_export(db, export.id)

        return ExportStatusResponse(
            export_id=export.id,
            status=export.status,
            format=export.format if isinstance(export.format, str) else export.format.value,
            requested_at=export.requested_at,
            completed_at=export.completed_at,
            expires_at=export.expires_at,
            file_size_bytes=export.file_size_bytes,
            download_count=export.download_count,
            nachricht="Export wurde erstellt. Sie können ihn jetzt herunterladen."
        )

    except ExportError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e.user_message_de)
        )


@router.get(
    "/exports",
    response_model=ExportListResponse,
    summary="Alle Exports auflisten",
    description="Zeigt alle Ihre Datenexports (auch abgelaufene)"
)
async def list_exports(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> ExportListResponse:
    """
    Listet alle Datenexports des Benutzers auf.

    Args:
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Liste aller Exports
    """
    export_service = get_data_export_service()
    exports = await export_service.get_exports_for_user(db, current_user.id)

    export_responses = []
    for export in exports:
        status_msg = _get_export_status_message(export.status)
        export_responses.append(
            ExportStatusResponse(
                export_id=export.id,
                status=export.status,
                format=export.format if isinstance(export.format, str) else export.format.value,
                requested_at=export.requested_at,
                completed_at=export.completed_at,
                expires_at=export.expires_at,
                file_size_bytes=export.file_size_bytes,
                download_count=export.download_count,
                error_message=export.error_message,
                nachricht=status_msg
            )
        )

    return ExportListResponse(
        exports=export_responses,
        total=len(export_responses)
    )


@router.get(
    "/exports/{export_id}",
    response_model=ExportStatusResponse,
    summary="Export-Status abfragen",
    description="Zeigt den Status eines spezifischen Exports"
)
async def get_export_status(
    export_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> ExportStatusResponse:
    """
    Status eines spezifischen Exports abrufen.

    Args:
        export_id: Export UUID
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Export-Status

    Raises:
        404: Export nicht gefunden
    """
    export_service = get_data_export_service()
    export = await export_service.get_export(db, export_id, current_user.id)

    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export nicht gefunden"
        )

    status_msg = _get_export_status_message(export.status)

    return ExportStatusResponse(
        export_id=export.id,
        status=export.status,
        format=export.format if isinstance(export.format, str) else export.format.value,
        requested_at=export.requested_at,
        completed_at=export.completed_at,
        expires_at=export.expires_at,
        file_size_bytes=export.file_size_bytes,
        download_count=export.download_count,
        error_message=export.error_message,
        nachricht=status_msg
    )


@router.get(
    "/exports/{export_id}/download",
    summary="Export herunterladen",
    description="Lädt den Datenexport als ZIP-Datei herunter"
)
async def download_export(
    export_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Download eines Datenexports.

    Args:
        export_id: Export UUID
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        ZIP-Datei als FileResponse

    Raises:
        404: Export nicht gefunden
        400: Export nicht bereit oder abgelaufen
        403: Zugriff auf Pfad verweigert (Path Traversal Schutz)
    """
    from fastapi.responses import FileResponse
    from pathlib import Path
    import os

    export_service = get_data_export_service()

    try:
        file_path = await export_service.get_download_path(
            db, export_id, current_user.id
        )

        # T.3 SECURITY FIX: Path Traversal Protection
        # Normalisiere Pfad und validiere gegen erlaubtes Basisverzeichnis
        path = Path(file_path)
        normalized_path = os.path.normpath(os.path.abspath(str(path)))

        # Hole das konfigurierte Export-Verzeichnis (aus Settings oder Default)
        from app.core.config import settings
        export_base_dir = os.path.normpath(os.path.abspath(
            getattr(settings, 'GDPR_EXPORT_DIR', '/app/data/exports')
        ))

        # Validiere dass der Pfad innerhalb des erlaubten Verzeichnisses liegt
        if not normalized_path.startswith(export_base_dir):
            logger.warning(
                "path_traversal_attempt_blocked",
                requested_path=file_path,
                normalized_path=normalized_path,
                allowed_base=export_base_dir,
                user_id=str(current_user.id)[:8] + "..."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Zugriff auf diesen Pfad verweigert"
            )

        if not os.path.exists(normalized_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export-Datei nicht gefunden"
            )

        logger.info(
            "gdpr_export_downloaded",
            export_id=str(export_id),
            user_id=str(current_user.id)[:8] + "..."
        )

        return FileResponse(
            path=normalized_path,
            filename=f"datenexport_{export_id}.zip",
            media_type="application/zip"
        )

    except ExportError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.user_message_de)
        )


def _get_export_status_message(export_status: str) -> str:
    """Gibt eine deutsche Statusnachricht zurück."""
    messages = {
        "pending": "Export wartet auf Verarbeitung",
        "processing": "Export wird erstellt...",
        "completed": "Export bereit zum Download",
        "failed": "Export fehlgeschlagen",
        "expired": "Export abgelaufen - bitte neuen anfordern"
    }
    return messages.get(export_status, "Unbekannter Status")


# ==================== Pydantic Schemas für Consent Management ====================

class ConsentScopeInfo(BaseModel):
    """Information über einen einzelnen Einwilligungs-Bereich."""
    scope: str
    scope_description: str
    consent_given: bool
    consent_version: Optional[str] = None
    granted_at: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class ConsentStatusResponse(BaseModel):
    """Aktueller Einwilligungs-Status des Benutzers."""
    user_id: UUID
    scopes: List[ConsentScopeInfo]
    total_consents: int
    active_consents: int
    nachricht: str


class ConsentGrantRequest(BaseModel):
    """Request zum Erteilen einer Einwilligung."""
    scope: str = Field(..., description="Bereich der Einwilligung (z.B. personal_data, analytics)")
    consent_given: bool = Field(..., description="True = Einwilligung erteilen, False = ablehnen")
    valid_until: Optional[datetime] = Field(None, description="Optionales Ablaufdatum")


class ConsentGrantResponse(BaseModel):
    """Response nach Erteilung einer Einwilligung."""
    success: bool
    consent_id: UUID
    scope: str
    consent_given: bool
    consent_version: Optional[str] = None
    granted_at: datetime
    nachricht: str


class ConsentWithdrawResponse(BaseModel):
    """Response nach Widerruf einer Einwilligung."""
    success: bool
    scope: str
    withdrawn_at: datetime
    consent_id: UUID
    nachricht: str


class ConsentHistoryEntryResponse(BaseModel):
    """Ein Eintrag in der Einwilligungs-Historie."""
    id: UUID
    action: str
    scope: str
    previous_value: Optional[bool]
    new_value: bool
    consent_version: Optional[str]
    ip_address: Optional[str]
    reason: Optional[str]
    created_at: datetime


class ConsentHistoryResponse(BaseModel):
    """Liste der Einwilligungs-Historie."""
    user_id: UUID
    history: List[ConsentHistoryEntryResponse]
    total: int


class DSRCreateRequest(BaseModel):
    """Request zum Erstellen einer Betroffenenrechte-Anfrage."""
    request_type: str = Field(..., description="Typ: access, rectification, erasure, restriction, portability, objection")
    description: Optional[str] = Field(None, description="Optionale Beschreibung")
    affected_data_categories: Optional[List[str]] = Field(None, description="Betroffene Datenkategorien")
    rectification_details: Optional[dict] = Field(None, description="Details für Berichtigungen (Art. 16)")


class DSRCreateResponse(BaseModel):
    """Response nach Erstellung einer DSR-Anfrage."""
    success: bool
    request_id: UUID
    request_type: str
    status: str
    due_date: datetime
    verification_required: bool
    nachricht: str


class DSRStatusResponse(BaseModel):
    """Status einer Betroffenenrechte-Anfrage."""
    request_id: UUID
    request_type: str
    status: str
    requested_at: datetime
    due_date: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    days_remaining: int
    response_notes: Optional[str]
    nachricht: str


class DSRListResponse(BaseModel):
    """Liste aller Betroffenenrechte-Anfragen."""
    requests: List[DSRStatusResponse]
    total: int


class DSRVerifyRequest(BaseModel):
    """Request zur Identitätsverifikation."""
    verification_token: str = Field(..., description="Verifikations-Token aus der Email")


class DSRVerifyResponse(BaseModel):
    """Response nach Verifikation."""
    success: bool
    request_id: UUID
    verified_at: Optional[datetime] = None
    nachricht: str


class RectificationRequest(BaseModel):
    """Request zur Datenberichtigung (Art. 16)."""
    corrections: dict = Field(..., description="Zu korrigierende Felder und neue Werte")
    reason: Optional[str] = Field(None, description="Begründung")


class RectificationResponse(BaseModel):
    """Response nach Datenberichtigung."""
    success: bool
    corrected_fields: List[str]
    skipped_fields: List[str]
    protected_fields: List[str]
    nachricht: str


# ==================== Art. 6, 7 - Einwilligungsverwaltung (Consent) ====================

consent_router = APIRouter(prefix="/consent", tags=["GDPR - Einwilligung"])


@consent_router.get(
    "",
    response_model=ConsentStatusResponse,
    summary="Einwilligungs-Status abrufen",
    description="Art. 7 DSGVO - Zeigt alle aktuellen Einwilligungen"
)
async def get_consent_status(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ConsentStatusResponse:
    """
    Zeigt den aktuellen Einwilligungs-Status für alle Bereiche.

    Args:
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Aktueller Consent-Status für alle Scopes
    """
    consent_service = get_consent_management_service()

    # Hole Status für alle Scopes
    scopes_info = []
    active_count = 0

    for scope in ConsentScope:
        result = await consent_service.check_consent(
            db=db,
            user_id=current_user.id,
            scope=scope,
            company_id=company_id
        )

        scope_descriptions = {
            ConsentScope.PERSONAL_DATA: "Verarbeitung personenbezogener Daten",
            ConsentScope.FINANCIAL_DATA: "Verarbeitung finanzieller Daten",
            ConsentScope.DOCUMENT_PROCESSING: "Dokumentenverarbeitung und OCR",
            ConsentScope.ANALYTICS: "Analyse und Statistiken",
            ConsentScope.MARKETING: "Marketing-Kommunikation",
            ConsentScope.THIRD_PARTY_SHARING: "Weitergabe an Dritte",
            ConsentScope.AUTOMATED_DECISIONS: "Automatisierte Entscheidungen",
        }

        scopes_info.append(ConsentScopeInfo(
            scope=scope.value,
            scope_description=scope_descriptions.get(scope, scope.value),
            consent_given=result.consent_given,
            consent_version=result.consent_version,
            granted_at=result.granted_at,
            valid_until=result.valid_until,
        ))

        if result.consent_given:
            active_count += 1

    return ConsentStatusResponse(
        user_id=current_user.id,
        scopes=scopes_info,
        total_consents=len(scopes_info),
        active_consents=active_count,
        nachricht=f"Sie haben {active_count} von {len(scopes_info)} Einwilligungen erteilt."
    )


@consent_router.post(
    "",
    response_model=ConsentGrantResponse,
    summary="Einwilligung erteilen/aktualisieren",
    description="Art. 6, 7 DSGVO - Einwilligung für einen Bereich erteilen"
)
async def grant_consent(
    request: Request,
    consent_request: ConsentGrantRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ConsentGrantResponse:
    """
    Erteilt oder aktualisiert eine Einwilligung für einen bestimmten Bereich.

    Args:
        consent_request: Einwilligungs-Daten
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Bestätigung der Einwilligung

    Raises:
        400: Ungültiger Scope
    """
    consent_service = get_consent_management_service()

    # Validiere Scope
    try:
        scope = ConsentScope(consent_request.scope)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Einwilligungs-Bereich: {consent_request.scope}. "
                   f"Gültige Werte: {[s.value for s in ConsentScope]}"
        )

    # IP-Adresse aus Request extrahieren
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")

    try:
        if consent_request.consent_given:
            result = await consent_service.grant_consent(
                db=db,
                user_id=current_user.id,
                scope=scope,
                company_id=company_id,
                consent_method=ConsentMethod.WEB_FORM,
                ip_address=client_ip,
                user_agent=user_agent[:500] if user_agent else None,
                valid_until=consent_request.valid_until,
            )
            nachricht = f"Einwilligung für '{scope.value}' erfolgreich erteilt."
        else:
            # Consent ablehnen = withdraw
            result = await consent_service.withdraw_consent(
                db=db,
                user_id=current_user.id,
                scope=scope,
                company_id=company_id,
                reason="Benutzer hat Einwilligung abgelehnt",
                ip_address=client_ip,
                user_agent=user_agent[:500] if user_agent else None,
            )
            # Return a grant response for consistency
            return ConsentGrantResponse(
                success=True,
                consent_id=result.consent_scope_id,
                scope=scope.value,
                consent_given=False,
                consent_version=None,
                granted_at=result.withdrawn_at,
                nachricht=f"Einwilligung für '{scope.value}' wurde abgelehnt/widerrufen."
            )

        await db.commit()

        logger.info(
            "gdpr_consent_granted",
            user_id=str(current_user.id)[:8] + "...",
            scope=scope.value,
            consent_given=consent_request.consent_given
        )

        return ConsentGrantResponse(
            success=result.success,
            consent_id=result.consent_scope_id,
            scope=scope.value,
            consent_given=True,
            consent_version=result.consent_version,
            granted_at=result.granted_at,
            nachricht=nachricht
        )

    except Exception as e:
        await db.rollback()
        logger.error(
            "gdpr_consent_grant_failed",
            user_id=str(current_user.id)[:8] + "...",
            scope=consent_request.scope,
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Fehler beim Erteilen der Einwilligung")
        )


@consent_router.delete(
    "/{scope}",
    response_model=ConsentWithdrawResponse,
    summary="Einwilligung widerrufen",
    description="Art. 7(3) DSGVO - Einwilligung jederzeit widerrufen"
)
async def withdraw_consent(
    scope: str,
    request: Request,
    reason: Optional[str] = Query(None, description="Optionaler Grund"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ConsentWithdrawResponse:
    """
    Widerruft eine bestehende Einwilligung.

    Art. 7(3) DSGVO: Die betroffene Person hat das Recht, ihre Einwilligung
    jederzeit zu widerrufen. Der Widerruf muss so einfach wie die Erteilung sein.

    Args:
        scope: Bereich der Einwilligung
        reason: Optionaler Grund für den Widerruf
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Bestätigung des Widerrufs

    Raises:
        400: Ungültiger Scope oder keine aktive Einwilligung
    """
    consent_service = get_consent_management_service()

    # Validiere Scope
    try:
        consent_scope = ConsentScope(scope)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Einwilligungs-Bereich: {scope}"
        )

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")

    try:
        result = await consent_service.withdraw_consent(
            db=db,
            user_id=current_user.id,
            scope=consent_scope,
            company_id=company_id,
            reason=reason,
            ip_address=client_ip,
            user_agent=user_agent[:500] if user_agent else None,
        )

        await db.commit()

        logger.info(
            "gdpr_consent_withdrawn",
            user_id=str(current_user.id)[:8] + "...",
            scope=scope
        )

        return ConsentWithdrawResponse(
            success=result.success,
            scope=scope,
            withdrawn_at=result.withdrawn_at,
            consent_id=result.consent_scope_id,
            nachricht=f"Einwilligung für '{scope}' erfolgreich widerrufen. "
                      f"Die Verarbeitung Ihrer Daten in diesem Bereich wird eingestellt."
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Fehler beim Widerruf")
        )


@consent_router.get(
    "/history",
    response_model=ConsentHistoryResponse,
    summary="Einwilligungs-Historie abrufen",
    description="Vollständige Historie aller Einwilligungs-Änderungen"
)
async def get_consent_history(
    scope: Optional[str] = Query(None, description="Filter nach Bereich"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ConsentHistoryResponse:
    """
    Zeigt die vollständige Historie aller Einwilligungs-Änderungen.

    Args:
        scope: Optionaler Filter nach Bereich
        limit: Maximale Anzahl der Einträge
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Liste der Historie-Einträge
    """
    consent_service = get_consent_management_service()

    # Validiere Scope wenn angegeben
    consent_scope = None
    if scope:
        try:
            consent_scope = ConsentScope(scope)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Einwilligungs-Bereich: {scope}"
            )

    history = await consent_service.get_consent_history(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        scope=consent_scope,
        limit=limit
    )

    history_entries = [
        ConsentHistoryEntryResponse(
            id=entry.id,
            action=entry.action.value if hasattr(entry.action, 'value') else entry.action,
            scope=entry.scope.value if hasattr(entry.scope, 'value') else entry.scope,
            previous_value=entry.previous_value,
            new_value=entry.new_value,
            consent_version=entry.consent_version,
            ip_address=entry.ip_address,
            reason=entry.reason,
            created_at=entry.created_at
        )
        for entry in history
    ]

    return ConsentHistoryResponse(
        user_id=current_user.id,
        history=history_entries,
        total=len(history_entries)
    )


# ==================== Art. 15-21 - Betroffenenrechte (DSR) ====================

dsr_router = APIRouter(prefix="/dsr", tags=["GDPR - Betroffenenrechte"])


@dsr_router.post(
    "",
    response_model=DSRCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Betroffenenrechte-Anfrage erstellen",
    description="Art. 15-21 DSGVO - Antrag auf Auskunft, Berichtigung, Löschung etc."
)
async def create_dsr_request(
    request: Request,
    dsr_request: DSRCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DSRCreateResponse:
    """
    Erstellt eine neue Betroffenenrechte-Anfrage (Data Subject Request).

    Unterstützte Antragstypen:
    - access: Art. 15 - Recht auf Auskunft
    - rectification: Art. 16 - Recht auf Berichtigung
    - erasure: Art. 17 - Recht auf Löschung
    - restriction: Art. 18 - Recht auf Einschränkung
    - portability: Art. 20 - Recht auf Datenübertragbarkeit
    - objection: Art. 21 - Widerspruchsrecht

    Die Anfrage muss innerhalb von 30 Tagen bearbeitet werden (DSGVO-Frist).

    Args:
        dsr_request: Anfrage-Daten
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Bestätigung mit Anfrage-ID und Frist
    """
    dsr_service = get_data_subject_rights_service()

    # Validiere Request-Type
    try:
        request_type = DSRType(dsr_request.request_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Antragstyp: {dsr_request.request_type}. "
                   f"Gültige Werte: {[t.value for t in DSRType]}"
        )

    # Validiere Data Categories wenn angegeben
    data_categories = None
    if dsr_request.affected_data_categories:
        data_categories = []
        for cat in dsr_request.affected_data_categories:
            try:
                data_categories.append(DataCategory(cat))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ungültige Datenkategorie: {cat}"
                )

    try:
        result = await dsr_service.create_request(
            db=db,
            request_type=request_type,
            requester_email=current_user.email,
            user_id=current_user.id,
            company_id=company_id,
            description=dsr_request.description,
            affected_data_categories=data_categories,
            rectification_details=dsr_request.rectification_details,
        )

        await db.commit()

        type_descriptions = {
            DSRType.ACCESS: "Auskunftsantrag (Art. 15)",
            DSRType.RECTIFICATION: "Berichtigungsantrag (Art. 16)",
            DSRType.ERASURE: "Löschantrag (Art. 17)",
            DSRType.RESTRICTION: "Einschränkungsantrag (Art. 18)",
            DSRType.PORTABILITY: "Portabilitätsantrag (Art. 20)",
            DSRType.OBJECTION: "Widerspruch (Art. 21)",
        }

        logger.info(
            "gdpr_dsr_created",
            user_id=str(current_user.id)[:8] + "...",
            request_type=request_type.value,
            request_id=str(result.request_id)[:8] + "..."
        )

        return DSRCreateResponse(
            success=True,
            request_id=result.request_id,
            request_type=request_type.value,
            status=result.status.value if hasattr(result.status, 'value') else result.status,
            due_date=result.due_date,
            verification_required=result.verification_required,
            nachricht=f"{type_descriptions.get(request_type, 'Antrag')} wurde erstellt. "
                      f"Bearbeitungsfrist: {result.due_date.strftime('%d.%m.%Y')} (30 Tage)."
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Fehler beim Erstellen der Anfrage")
        )


@dsr_router.get(
    "",
    response_model=DSRListResponse,
    summary="Alle DSR-Anfragen auflisten",
    description="Liste aller eigenen Betroffenenrechte-Anfragen"
)
async def list_dsr_requests(
    status_filter: Optional[str] = Query(None, description="Filter nach Status"),
    request_type: Optional[str] = Query(None, description="Filter nach Typ"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DSRListResponse:
    """
    Listet alle Betroffenenrechte-Anfragen des Benutzers auf.

    Args:
        status_filter: Optionaler Filter nach Status
        request_type: Optionaler Filter nach Antragstyp
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Liste der Anfragen
    """
    dsr_service = get_data_subject_rights_service()

    # Validiere Filter
    dsr_status = None
    if status_filter:
        try:
            dsr_status = DSRStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Status: {status_filter}"
            )

    dsr_type = None
    if request_type:
        try:
            dsr_type = DSRType(request_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Antragstyp: {request_type}"
            )

    requests = await dsr_service.list_requests(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        status=dsr_status,
        request_type=dsr_type,
    )

    now = datetime.now(timezone.utc)

    status_messages = {
        "pending": "Antrag eingereicht, warte auf Bearbeitung",
        "verified": "Identität verifiziert, Bearbeitung beginnt",
        "in_progress": "Antrag wird bearbeitet",
        "completed": "Antrag abgeschlossen",
        "rejected": "Antrag abgelehnt",
        "cancelled": "Antrag storniert",
    }

    response_requests = []
    for req in requests:
        days_remaining = (req.due_date - now).days if req.due_date > now else 0
        response_requests.append(DSRStatusResponse(
            request_id=req.id,
            request_type=req.request_type.value if hasattr(req.request_type, 'value') else req.request_type,
            status=req.status.value if hasattr(req.status, 'value') else req.status,
            requested_at=req.requested_at,
            due_date=req.due_date,
            started_at=req.started_at,
            completed_at=req.completed_at,
            days_remaining=days_remaining,
            response_notes=req.response_notes,
            nachricht=status_messages.get(req.status.value if hasattr(req.status, 'value') else req.status, "Status unbekannt")
        ))

    return DSRListResponse(
        requests=response_requests,
        total=len(response_requests)
    )


@dsr_router.get(
    "/{request_id}",
    response_model=DSRStatusResponse,
    summary="DSR-Anfrage-Status abrufen",
    description="Status einer spezifischen Betroffenenrechte-Anfrage"
)
async def get_dsr_status(
    request_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DSRStatusResponse:
    """
    Zeigt den Status einer spezifischen Betroffenenrechte-Anfrage.

    Args:
        request_id: ID der Anfrage
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Aktueller Status der Anfrage

    Raises:
        404: Anfrage nicht gefunden
    """
    dsr_service = get_data_subject_rights_service()

    req = await dsr_service.get_request(
        db=db,
        request_id=request_id,
        user_id=current_user.id,
    )

    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anfrage nicht gefunden oder keine Berechtigung"
        )

    now = datetime.now(timezone.utc)
    days_remaining = (req.due_date - now).days if req.due_date > now else 0

    status_messages = {
        "pending": "Antrag eingereicht, warte auf Bearbeitung",
        "verified": "Identität verifiziert, Bearbeitung beginnt",
        "in_progress": "Antrag wird bearbeitet",
        "completed": "Antrag abgeschlossen",
        "rejected": "Antrag abgelehnt",
        "cancelled": "Antrag storniert",
    }

    req_status = req.status.value if hasattr(req.status, 'value') else req.status

    return DSRStatusResponse(
        request_id=req.id,
        request_type=req.request_type.value if hasattr(req.request_type, 'value') else req.request_type,
        status=req_status,
        requested_at=req.requested_at,
        due_date=req.due_date,
        started_at=req.started_at,
        completed_at=req.completed_at,
        days_remaining=days_remaining,
        response_notes=req.response_notes,
        nachricht=status_messages.get(req_status, "Status unbekannt")
    )


@dsr_router.post(
    "/{request_id}/verify",
    response_model=DSRVerifyResponse,
    summary="Identität verifizieren",
    description="Verifikation der Identität für eine DSR-Anfrage"
)
async def verify_dsr_identity(
    request_id: UUID,
    verify_request: DSRVerifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DSRVerifyResponse:
    """
    Verifiziert die Identität des Antragstellers.

    Args:
        request_id: ID der Anfrage
        verify_request: Verifikations-Token
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Bestätigung der Verifikation

    Raises:
        400: Ungültiger Token
        404: Anfrage nicht gefunden
    """
    dsr_service = get_data_subject_rights_service()

    try:
        result = await dsr_service.verify_identity(
            db=db,
            request_id=request_id,
            verification_token=verify_request.verification_token,
        )

        await db.commit()

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error_message or "Verifikation fehlgeschlagen"
            )

        return DSRVerifyResponse(
            success=True,
            request_id=request_id,
            verified_at=result.verified_at,
            nachricht="Identität erfolgreich verifiziert. Ihr Antrag wird nun bearbeitet."
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Verifikation fehlgeschlagen")
        )


@dsr_router.delete(
    "/{request_id}",
    response_model=MessageResponse,
    summary="DSR-Anfrage stornieren",
    description="Storniert eine noch nicht abgeschlossene Anfrage"
)
async def cancel_dsr_request(
    request_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """
    Storniert eine Betroffenenrechte-Anfrage.

    Nur möglich wenn die Anfrage noch nicht abgeschlossen ist.

    Args:
        request_id: ID der Anfrage
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Bestätigung der Stornierung

    Raises:
        400: Anfrage kann nicht storniert werden
        404: Anfrage nicht gefunden
    """
    dsr_service = get_data_subject_rights_service()

    try:
        await dsr_service.cancel_request(
            db=db,
            request_id=request_id,
            user_id=current_user.id,
        )

        await db.commit()

        logger.info(
            "gdpr_dsr_cancelled",
            user_id=str(current_user.id)[:8] + "...",
            request_id=str(request_id)[:8] + "..."
        )

        return MessageResponse(
            message="Antrag storniert",
            detail="Ihre Betroffenenrechte-Anfrage wurde erfolgreich storniert."
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Ungültiger Wert")
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Stornierung fehlgeschlagen")
        )


# ==================== Art. 15 - Recht auf Auskunft (My Data) ====================

@router.get(
    "/my-data",
    summary="Alle meine Daten abrufen",
    description="Art. 15 DSGVO - Vollständige Auskunft über gespeicherte personenbezogene Daten"
)
async def get_my_data(
    include_documents: bool = Query(True, description="Dokumente einschließen"),
    include_activity: bool = Query(True, description="Aktivitäten einschließen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """
    Vollständige Auskunft über alle gespeicherten personenbezogenen Daten.

    Art. 15 DSGVO garantiert das Recht auf Auskunft über:
    - Verarbeitungszwecke
    - Kategorien personenbezogener Daten
    - Empfänger der Daten
    - Geplante Speicherdauer
    - Herkunft der Daten

    Args:
        include_documents: Ob Dokumente eingeschlossen werden sollen
        include_activity: Ob Aktivitäten eingeschlossen werden sollen
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Vollständiger Datenauszug
    """
    dsr_service = get_data_subject_rights_service()

    try:
        export = await dsr_service.export_personal_data_summary(
            db=db,
            user_id=current_user.id,
            company_id=company_id,
            include_documents=include_documents,
            include_activity=include_activity,
        )

        return {
            "export_date": export.export_date.isoformat(),
            "user_id": str(export.user_id),
            "data_categories": [cat.value if hasattr(cat, 'value') else cat for cat in export.data_categories],
            "personal_data": export.personal_data,
            "total_records": export.total_records,
            "hinweis": "Dies ist eine vollständige Auskunft gemäß Art. 15 DSGVO. "
                       "Sie haben das Recht auf Berichtigung (Art. 16), Löschung (Art. 17) "
                       "und Datenportabilität (Art. 20)."
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Abrufen der Daten")
        )


# ==================== Art. 16 - Recht auf Berichtigung ====================

@router.patch(
    "/rectify",
    response_model=RectificationResponse,
    summary="Daten berichtigen",
    description="Art. 16 DSGVO - Recht auf Berichtigung unrichtiger Daten"
)
async def rectify_data(
    rectification: RectificationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> RectificationResponse:
    """
    Berichtigt unrichtige personenbezogene Daten.

    Art. 16 DSGVO: Betroffene haben das Recht, unverzüglich die
    Berichtigung unrichtiger Daten zu verlangen.

    Berichtigbare Felder:
    - Persönliche Daten (Name, etc.)
    - Kontaktdaten
    - Präferenzen

    Geschützte Felder (nicht berichtigbar):
    - System-IDs
    - Audit-Logs
    - Authentifizierungsdaten

    Args:
        rectification: Zu korrigierende Felder
        current_user: Aktuell angemeldeter Benutzer
        db: Datenbank-Session

    Returns:
        Ergebnis der Berichtigung
    """
    dsr_service = get_data_subject_rights_service()

    try:
        result = await dsr_service.rectify_data(
            db=db,
            user_id=current_user.id,
            corrections=rectification.corrections,
            reason=rectification.reason,
        )

        await db.commit()

        logger.info(
            "gdpr_data_rectified",
            user_id=str(current_user.id)[:8] + "...",
            corrected_fields=result.corrected_fields
        )

        nachricht_parts = []
        if result.corrected_fields:
            nachricht_parts.append(f"{len(result.corrected_fields)} Feld(er) korrigiert")
        if result.skipped_fields:
            nachricht_parts.append(f"{len(result.skipped_fields)} Feld(er) übersprungen")
        if result.protected_fields:
            nachricht_parts.append(f"{len(result.protected_fields)} geschützte Feld(er) nicht änderbar")

        return RectificationResponse(
            success=result.success,
            corrected_fields=result.corrected_fields,
            skipped_fields=result.skipped_fields,
            protected_fields=result.protected_fields,
            nachricht=". ".join(nachricht_parts) + "."
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Berichtigung fehlgeschlagen")
        )


# Registriere Sub-Router am Haupt-Router
router.include_router(consent_router)
router.include_router(dsr_router)

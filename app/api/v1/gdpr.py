"""
GDPR API Endpoints - Art. 17 & Art. 20 DSGVO.

Implementiert:
- Art. 17: Recht auf Löschung (Right to Erasure)
- Art. 20: Recht auf Datenübertragbarkeit (Data Portability)

Alle Antworten auf Deutsch für Benutzerfreundlichkeit.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
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

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users/me/gdpr", tags=["GDPR"])


# ==================== Art. 17 - Recht auf Löschung ====================

@router.post(
    "/request-deletion",
    response_model=DeletionStatusResponse,
    summary="Kontolöschung anfordern",
    description="Art. 17 DSGVO - Recht auf Löschung. "
                "Nach Bestätigung wird das Konto nach 30 Tagen gelöscht."
)
async def request_account_deletion(
    request: DeletionRequestCreate,
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
            db, current_user.id, request.reason
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
    """
    from fastapi.responses import FileResponse
    from pathlib import Path

    export_service = get_data_export_service()

    try:
        file_path = await export_service.get_download_path(
            db, export_id, current_user.id
        )

        path = Path(file_path)
        if not path.exists():
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
            path=str(path),
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

"""
Audit Log Administration API Endpoints.

Provides audit log viewing and export for admins:
- List and search audit logs
- View admin actions
- Export audit data
- Get audit statistics
"""

from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User
from app.db.schemas import (
    AuditLogView,
    AuditLogFilters,
    AuditLogListResponse,
    SortOrder,
)
from app.services.admin.audit_service import AuditService


router = APIRouter(prefix="/audit", tags=["Admin - Audit-Logs"])


# ==================== List Audit Logs ====================

@router.get(
    "/logs",
    response_model=AuditLogListResponse,
    summary="Audit-Logs auflisten",
    description="Listet Audit-Logs mit Filter- und Paginierungsoptionen auf"
)
async def list_audit_logs(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    user_id: Optional[UUID] = Query(None, description="Nach Benutzer filtern"),
    action: Optional[str] = Query(None, description="Nach Aktion filtern (Teilsuche)"),
    resource_type: Optional[str] = Query(None, description="Nach Ressourcentyp filtern"),
    resource_id: Optional[str] = Query(None, description="Nach Ressourcen-ID filtern"),
    ip_address: Optional[str] = Query(None, description="Nach IP-Adresse filtern"),
    from_date: Optional[datetime] = Query(None, description="Ab Datum (ISO-Format)"),
    to_date: Optional[datetime] = Query(None, description="Bis Datum (ISO-Format)"),
    success: Optional[bool] = Query(None, description="Nur erfolgreiche/fehlgeschlagene"),
    sort_by: str = Query("created_at", description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    """
    Listet alle Audit-Logs im System auf.

    Nur fuer Administratoren zugaenglich.

    **Filter:**
    - **user_id**: Logs eines bestimmten Benutzers
    - **action**: Aktionstyp (z.B. "login", "document_upload")
    - **resource_type**: Ressourcentyp (z.B. "document", "user")
    - **resource_id**: Spezifische Ressourcen-ID
    - **ip_address**: Client-IP-Adresse
    - **from_date/to_date**: Zeitraumfilter
    - **success**: true = nur erfolgreiche Aktionen

    **Sortierung:**
    - Standardmaessig nach Zeitstempel absteigend
    """
    filters = AuditLogFilters(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        from_date=from_date,
        to_date=to_date,
        success=success,
    )

    return await AuditService.list_audit_logs(
        db=db,
        page=page,
        per_page=per_page,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ==================== Get Single Audit Log ====================

@router.get(
    "/logs/{log_id}",
    response_model=AuditLogView,
    summary="Audit-Log abrufen",
    description="Ruft einen einzelnen Audit-Log-Eintrag ab"
)
async def get_audit_log(
    log_id: UUID,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> AuditLogView:
    """
    Ruft einen einzelnen Audit-Log-Eintrag ab.

    Nur fuer Administratoren zugaenglich.
    """
    log = await AuditService.get_audit_log(db, log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit-Log-Eintrag nicht gefunden",
        )

    return log


# ==================== List Admin Actions ====================

@router.get(
    "/actions",
    summary="Admin-Aktionen auflisten",
    description="Listet alle Admin-Aktionen auf (Benutzerverwaltung, Konfigurationsaenderungen)"
)
async def list_admin_actions(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    admin_id: Optional[UUID] = Query(None, description="Nach ausfuehrendem Admin filtern"),
    target_user_id: Optional[UUID] = Query(None, description="Nach Zielbenutzer filtern"),
    action: Optional[str] = Query(None, description="Nach Aktionstyp filtern"),
    from_date: Optional[datetime] = Query(None, description="Ab Datum (ISO-Format)"),
    to_date: Optional[datetime] = Query(None, description="Bis Datum (ISO-Format)"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Listet alle Admin-Aktionen auf.

    Zeigt Aktionen wie:
    - Benutzererstellung/-aenderung/-loeschung
    - Rollenaenderungen
    - Passwort-Resets
    - Rate-Limit-Aenderungen
    - Job-Abbrueche

    **Filter:**
    - **admin_id**: Aktionen eines bestimmten Administrators
    - **target_user_id**: Aktionen, die einen bestimmten Benutzer betreffen
    - **action**: Aktionstyp (z.B. "create_user", "reset_password")
    """
    return await AuditService.list_admin_actions(
        db=db,
        page=page,
        per_page=per_page,
        admin_id=admin_id,
        target_user_id=target_user_id,
        action=action,
        from_date=from_date,
        to_date=to_date,
        sort_order=sort_order,
    )


# ==================== Get User Audit Trail ====================

@router.get(
    "/users/{user_id}/trail",
    summary="Benutzer-Audit-Trail",
    description="Ruft den vollstaendigen Audit-Trail eines Benutzers ab"
)
async def get_user_audit_trail(
    user_id: UUID,
    limit: int = Query(100, ge=1, le=500, description="Maximale Anzahl Eintraege"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft den vollstaendigen Audit-Trail eines Benutzers ab.

    Kombiniert:
    - Aktionen des Benutzers (Logins, Dokumentenoperationen)
    - Admin-Aktionen, die den Benutzer betreffen

    Nuetzlich fuer:
    - Sicherheitsueberpruefungen
    - Compliance-Anforderungen
    - Fehlerbehebung
    """
    return await AuditService.get_user_audit_trail(
        db=db,
        user_id=user_id,
        limit=limit,
    )


# ==================== Export Audit Logs ====================

@router.get(
    "/export",
    summary="Audit-Logs exportieren",
    description="Exportiert Audit-Logs als CSV oder JSON"
)
async def export_audit_logs(
    format: str = Query("csv", description="Exportformat (csv oder json)"),
    user_id: Optional[UUID] = Query(None, description="Nach Benutzer filtern"),
    action: Optional[str] = Query(None, description="Nach Aktion filtern"),
    resource_type: Optional[str] = Query(None, description="Nach Ressourcentyp filtern"),
    from_date: Optional[datetime] = Query(None, description="Ab Datum (ISO-Format)"),
    to_date: Optional[datetime] = Query(None, description="Bis Datum (ISO-Format)"),
    success: Optional[bool] = Query(None, description="Nur erfolgreiche/fehlgeschlagene"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """
    Exportiert Audit-Logs als Datei.

    **Formate:**
    - **csv**: Komma-separierte Werte (Excel-kompatibel)
    - **json**: JSON-Array

    **Limit:** Maximal 10.000 Eintraege pro Export

    Die Datei wird als Download bereitgestellt.
    """
    if format not in ["csv", "json"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltiges Format. Verwenden Sie 'csv' oder 'json'.",
        )

    filters = AuditLogFilters(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        from_date=from_date,
        to_date=to_date,
        success=success,
    )

    content = await AuditService.export_audit_logs(
        db=db,
        filters=filters,
        format=format,
    )

    # Set appropriate headers for download
    filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"

    if format == "csv":
        media_type = "text/csv; charset=utf-8"
    else:
        media_type = "application/json; charset=utf-8"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )


# ==================== Audit Statistics ====================

@router.get(
    "/stats",
    summary="Audit-Statistiken",
    description="Ruft zusammenfassende Statistiken ueber Audit-Logs ab"
)
async def get_audit_statistics(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft zusammenfassende Statistiken ueber Audit-Logs ab.

    Zeigt:
    - Gesamtzahl der Eintraege
    - Eintraege nach Aktionstyp
    - Eintraege nach Ressourcentyp
    - Erfolgs-/Fehlerquote
    - Aktivste Benutzer
    - Anzahl Admin-Aktionen
    """
    return await AuditService.get_statistics(
        db=db,
        days=days,
    )


# ==================== Search Audit Logs ====================

@router.get(
    "/search",
    response_model=AuditLogListResponse,
    summary="Audit-Logs durchsuchen",
    description="Durchsucht Audit-Logs nach Freitext"
)
async def search_audit_logs(
    q: str = Query(..., min_length=2, description="Suchbegriff"),
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    from_date: Optional[datetime] = Query(None, description="Ab Datum (ISO-Format)"),
    to_date: Optional[datetime] = Query(None, description="Bis Datum (ISO-Format)"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    """
    Durchsucht Audit-Logs nach Freitext.

    Durchsucht:
    - Aktionsname
    - Ressourcentyp
    - Ressourcen-ID
    - Fehlermeldungen

    **Mindestlaenge:** 2 Zeichen
    """
    filters = AuditLogFilters(
        action=q,  # Will be used as partial match
        from_date=from_date,
        to_date=to_date,
    )

    return await AuditService.list_audit_logs(
        db=db,
        page=page,
        per_page=per_page,
        filters=filters,
        sort_order=SortOrder.DESC,
    )

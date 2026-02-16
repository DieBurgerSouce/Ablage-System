"""
Audit Log Administration API Endpoints.

Provides audit log viewing and export for admins:
- List and search audit logs
- View admin actions
- Export audit data
- Get audit statistics
- Permission audit and compliance reporting (Phase 1.2)
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser, get_current_user
from app.core.german_messages import HTTPErrors
from app.core.security import build_content_disposition
from app.db.models import User
from app.db.schemas import (
    AuditLogView,
    AuditLogFilters,
    AuditLogListResponse,
    AuditSortField,
    SortOrder,
)
from app.services.admin.audit_service import AuditService
from app.services.permission_audit_service import (
    PermissionAuditService,
    PermissionChangeType,
    PermissionChangeRecord,
    PermissionAuditExport,
)


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
    per_page: int = Query(50, ge=1, le=200, description="Einträge pro Seite"),
    user_id: Optional[UUID] = Query(None, description="Nach Benutzer filtern"),
    action: Optional[str] = Query(None, description="Nach Aktion filtern (Teilsuche)"),
    resource_type: Optional[str] = Query(None, description="Nach Ressourcentyp filtern"),
    resource_id: Optional[str] = Query(None, description="Nach Ressourcen-ID filtern"),
    ip_address: Optional[str] = Query(None, description="Nach IP-Adresse filtern"),
    from_date: Optional[datetime] = Query(None, description="Ab Datum (ISO-Format)"),
    to_date: Optional[datetime] = Query(None, description="Bis Datum (ISO-Format)"),
    success: Optional[bool] = Query(None, description="Nur erfolgreiche/fehlgeschlagene"),
    sort_by: AuditSortField = Query(AuditSortField.CREATED_AT, description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    """
    Listet alle Audit-Logs im System auf.

    Nur für Administratoren zugänglich.

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

    Nur für Administratoren zugänglich.
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
    description="Listet alle Admin-Aktionen auf (Benutzerverwaltung, Konfigurationsänderungen)"
)
async def list_admin_actions(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(50, ge=1, le=200, description="Einträge pro Seite"),
    admin_id: Optional[UUID] = Query(None, description="Nach ausführendem Admin filtern"),
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
    - Benutzererstellung/-änderung/-löschung
    - Rollenänderungen
    - Passwort-Resets
    - Rate-Limit-Änderungen
    - Job-Abbrüche

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
    description="Ruft den vollständigen Audit-Trail eines Benutzers ab"
)
async def get_user_audit_trail(
    user_id: UUID,
    limit: int = Query(100, ge=1, le=500, description="Maximale Anzahl Einträge"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft den vollständigen Audit-Trail eines Benutzers ab.

    Kombiniert:
    - Aktionen des Benutzers (Logins, Dokumentenoperationen)
    - Admin-Aktionen, die den Benutzer betreffen

    Nützlich für:
    - Sicherheitsüberprüfungen
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

    **Limit:** Maximal 10.000 Einträge pro Export

    Die Datei wird als Download bereitgestellt.
    """
    if format not in ["csv", "json"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=HTTPErrors.EXPORT_FORMAT_INVALID,
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
            # SECURITY: Use sanitized Content-Disposition (Phase 10)
            "Content-Disposition": build_content_disposition(filename, "attachment"),
        },
    )


# ==================== Audit Statistics ====================

@router.get(
    "/stats",
    summary="Audit-Statistiken",
    description="Ruft zusammenfassende Statistiken über Audit-Logs ab"
)
async def get_audit_statistics(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft zusammenfassende Statistiken über Audit-Logs ab.

    Zeigt:
    - Gesamtzahl der Einträge
    - Einträge nach Aktionstyp
    - Einträge nach Ressourcentyp
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
    per_page: int = Query(50, ge=1, le=200, description="Einträge pro Seite"),
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

    **Mindestlänge:** 2 Zeichen
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


# ==================== Permission Audit (Phase 1.2) ====================


@router.get(
    "/permissions",
    response_model=PermissionAuditExport,
    summary="Berechtigungs-Audit abrufen",
    description="Listet alle Berechtigungsänderungen für die Company auf",
)
async def get_permission_audit(
    start_date: Optional[datetime] = Query(None, description="Ab Datum (ISO-Format)"),
    end_date: Optional[datetime] = Query(None, description="Bis Datum (ISO-Format)"),
    change_type: Optional[PermissionChangeType] = Query(
        None, description="Nach Änderungstyp filtern"
    ),
    limit: int = Query(500, ge=1, le=5000, description="Maximale Anzahl Einträge"),
    offset: int = Query(0, ge=0, description="Offset für Pagination"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> PermissionAuditExport:
    """
    Ruft alle Berechtigungsänderungen für die aktuelle Company ab.

    **Phase 1.2 - Berechtigungsprotokoll für Compliance**

    Enthält:
    - Rollenzuweisungen/-entzüge
    - Einzelne Permission-Grants/-Revokes
    - Gruppenmitgliedschafts-Änderungen
    - Delegationen (Phase 3)

    **DSGVO Art. 30 konform** - Alle Änderungen sind nachvollziehbar.

    **Tenant-isoliert** - Nur Daten der eigenen Company.
    """
    if not admin.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = PermissionAuditService(db)

    change_types = [change_type] if change_type else None

    return await service.get_company_permission_audit(
        company_id=str(admin.company_id),
        start_date=start_date,
        end_date=end_date,
        change_types=change_types,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/permissions/user/{user_id}",
    response_model=List[PermissionChangeRecord],
    summary="Benutzer-Berechtigungs-Historie",
    description="Ruft die Berechtigungsänderungs-Historie für einen Benutzer ab",
)
async def get_user_permission_history(
    user_id: UUID,
    start_date: Optional[datetime] = Query(None, description="Ab Datum"),
    end_date: Optional[datetime] = Query(None, description="Bis Datum"),
    limit: int = Query(100, ge=1, le=1000, description="Maximale Anzahl"),
    offset: int = Query(0, ge=0, description="Offset"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[PermissionChangeRecord]:
    """
    Ruft die komplette Berechtigungs-Historie für einen Benutzer ab.

    **Use Cases:**
    - Compliance-Audits: "Wer hatte wann welche Rechte?"
    - Security-Reviews: "Wie haben sich die Rechte entwickelt?"
    - Incident Response: "Hatte der User zum Zeitpunkt X Zugriff auf Y?"

    **Tenant-isoliert** - Nur für Benutzer der eigenen Company.
    """
    if not admin.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = PermissionAuditService(db)

    return await service.get_user_permission_history(
        user_id=str(user_id),
        company_id=str(admin.company_id),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/permissions/export",
    summary="Berechtigungs-Audit exportieren",
    description="Exportiert Berechtigungsänderungen als CSV oder JSON",
)
async def export_permission_audit(
    format: str = Query("csv", description="Exportformat (csv oder json)"),
    start_date: Optional[datetime] = Query(None, description="Ab Datum"),
    end_date: Optional[datetime] = Query(None, description="Bis Datum"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportiert Berechtigungsänderungen für Compliance-Reports.

    **Formate:**
    - **csv**: Semikolon-getrennt (Excel-kompatibel, deutsche Spaltenköpfe)
    - **json**: JSON mit vollständigen Metadaten

    **DSGVO Art. 30** - Export für Verzeichnis der Verarbeitungstätigkeiten.

    **Limit**: Maximal 10.000 Einträge pro Export.
    """
    if not admin.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company-Zuordnung gefunden",
        )

    if format not in ["csv", "json"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiges Format. Erlaubt: csv, json",
        )

    service = PermissionAuditService(db)

    if format == "csv":
        content = await service.export_csv(
            company_id=str(admin.company_id),
            start_date=start_date,
            end_date=end_date,
        )
        media_type = "text/csv; charset=utf-8"
    else:
        content = await service.export_json(
            company_id=str(admin.company_id),
            start_date=start_date,
            end_date=end_date,
        )
        media_type = "application/json; charset=utf-8"

    filename = f"berechtigungen_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": build_content_disposition(filename, "attachment"),
        },
    )


@router.get(
    "/permissions/summary",
    summary="Berechtigungs-Audit Zusammenfassung",
    description="Gibt eine Compliance-Zusammenfassung der Berechtigungsänderungen zurück",
)
async def get_permission_audit_summary(
    days: int = Query(30, ge=1, le=365, description="Betrachtungszeitraum in Tagen"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Erstellt eine Compliance-Zusammenfassung für Berechtigungsänderungen.

    **Enthält:**
    - Gesamtzahl der Änderungen im Zeitraum
    - Aufschlüsselung nach Änderungstyp
    - Top betroffene Benutzer
    - Top Administratoren
    - Zeitraumstatistiken

    **Nützlich für:**
    - Compliance-Dashboard
    - Audit-Vorbereitung
    - Security-Reviews
    """
    if not admin.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = PermissionAuditService(db)

    return await service.get_compliance_summary(
        company_id=str(admin.company_id),
        period_days=days,
    )

# -*- coding: utf-8 -*-
"""
API-Endpunkte fuer Backup-Operationen.

Alle Endpunkte erfordern Admin-Authentifizierung.

Feinpoliert und durchdacht - Enterprise Backup API.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_superuser
from app.db.models import User
from app.services.backup_service import BackupResult, get_backup_service
from app.services.backup_validator import (
    BackupValidator,
    ValidationLevel,
    ValidationStatus,
    get_backup_validator,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])


# =============================================================================
# Response Models
# =============================================================================


class BackupResponse(BaseModel):
    """Antwort fuer einzelne Backup-Operation."""

    erfolg: bool = Field(..., description="War das Backup erfolgreich?")
    backup_typ: str = Field(..., description="postgres, redis, minio, config")
    pfad: Optional[str] = Field(None, description="Pfad zur Backup-Datei")
    groesse_bytes: int = Field(0, description="Groesse in Bytes")
    groesse_mb: float = Field(0.0, description="Groesse in MB")
    validiert: bool = Field(False, description="Wurde Backup validiert?")
    verschluesselt: bool = Field(False, description="Ist Backup verschluesselt?")
    remote_sync: bool = Field(False, description="Wurde zum Remote synchronisiert?")
    fehler: Optional[str] = Field(None, description="Fehlermeldung bei Misserfolg")

    @classmethod
    def from_result(cls, result: BackupResult) -> "BackupResponse":
        """Erstelle Response aus BackupResult."""
        return cls(
            erfolg=result.success,
            backup_typ=result.backup_type,
            pfad=str(result.path) if result.path else None,
            groesse_bytes=result.size_bytes,
            groesse_mb=round(result.size_bytes / 1024 / 1024, 2),
            validiert=result.validated,
            verschluesselt=result.encrypted,
            remote_sync=result.remote_synced,
            fehler=result.error,
        )


class FullBackupResponse(BaseModel):
    """Antwort fuer vollstaendiges Backup."""

    erfolg: bool = Field(..., description="Waren alle Backups erfolgreich?")
    erfolgreich: int = Field(..., description="Anzahl erfolgreicher Backups")
    fehlgeschlagen: int = Field(..., description="Anzahl fehlgeschlagener Backups")
    backups: List[BackupResponse] = Field(..., description="Details je Backup")
    nachricht: str = Field(..., description="Zusammenfassung")


class BackupListItem(BaseModel):
    """Element in der Backup-Liste."""

    typ: str = Field(..., description="Backup-Typ")
    name: str = Field(..., description="Dateiname")
    pfad: str = Field(..., description="Vollstaendiger Pfad")
    groesse_bytes: int = Field(..., description="Groesse in Bytes")
    groesse_mb: float = Field(..., description="Groesse in MB")
    erstellt: str = Field(..., description="Erstellungszeitpunkt (ISO)")
    verschluesselt: bool = Field(..., description="Ist verschluesselt?")


class BackupListResponse(BaseModel):
    """Antwort fuer Backup-Liste."""

    anzahl: int = Field(..., description="Anzahl der Backups")
    backups: List[BackupListItem] = Field(..., description="Liste der Backups")


class RetentionResponse(BaseModel):
    """Antwort fuer Retention Policy."""

    erfolg: bool = Field(..., description="War Aufraeumen erfolgreich?")
    geloescht_gesamt: int = Field(..., description="Gesamtzahl geloeschter Backups")
    details: Dict[str, int] = Field(..., description="Geloescht pro Typ")
    nachricht: str = Field(..., description="Zusammenfassung")


class BackupStatusResponse(BaseModel):
    """Status des Backup-Systems."""

    service_aktiv: bool = Field(..., description="Ist Backup-Service aktiv?")
    encryption_aktiviert: bool = Field(..., description="Ist Verschluesselung aktiv?")
    remote_sync_aktiviert: bool = Field(..., description="Ist Remote-Sync aktiv?")
    backup_verzeichnis: str = Field(..., description="Pfad zum Backup-Verzeichnis")
    aufbewahrung_tage: int = Field(..., description="Retention in Tagen")
    speicherplatz: Dict[str, Any] = Field(..., description="Speicherplatz-Info")
    backup_dateien: Dict[str, int] = Field(..., description="Anzahl Dateien pro Typ")


class AsyncBackupResponse(BaseModel):
    """Antwort fuer asynchron gestartetes Backup."""

    gestartet: bool = Field(True, description="Wurde Backup gestartet?")
    backup_typ: str = Field(..., description="Gestarteter Backup-Typ")
    nachricht: str = Field(..., description="Info-Nachricht")


class RestoreRequest(BaseModel):
    """Anfrage fuer Restore-Operation."""

    backup_pfad: str = Field(..., description="Pfad zur Backup-Datei")
    dry_run: bool = Field(False, description="Nur simulieren, nicht ausfuehren")


class RestoreMinioRequest(BaseModel):
    """Anfrage fuer MinIO-Restore."""

    backup_pfad: str = Field(..., description="Pfad zur Backup-Datei")
    bucket: Optional[str] = Field(None, description="Ziel-Bucket (optional)")
    dry_run: bool = Field(False, description="Nur simulieren, nicht ausfuehren")


class FullRestoreRequest(BaseModel):
    """Anfrage fuer vollstaendigen Restore."""

    backup_verzeichnis: str = Field(..., description="Verzeichnis mit Backup-Dateien")
    komponenten: Optional[List[str]] = Field(
        None, description="Komponenten: postgres, redis, minio, config"
    )
    dry_run: bool = Field(False, description="Nur simulieren, nicht ausfuehren")


class RestoreResponse(BaseModel):
    """Antwort fuer Restore-Operation."""

    erfolg: bool = Field(..., description="War Restore erfolgreich?")
    backup_typ: str = Field(..., description="postgres, redis, minio, config")
    dry_run: bool = Field(..., description="War es ein Dry-Run?")
    validiert: bool = Field(False, description="Wurde Backup vor Restore validiert?")
    fehler: Optional[str] = Field(None, description="Fehlermeldung bei Misserfolg")
    nachricht: str = Field(..., description="Zusammenfassung")

    @classmethod
    def from_result(cls, result: BackupResult, dry_run: bool = False) -> "RestoreResponse":
        """Erstelle Response aus BackupResult."""
        if result.success:
            nachricht = f"Restore von {result.backup_type} erfolgreich"
            if dry_run:
                nachricht += " (Dry-Run)"
        else:
            nachricht = f"Restore von {result.backup_type} fehlgeschlagen"

        return cls(
            erfolg=result.success,
            backup_typ=result.backup_type,
            dry_run=dry_run,
            validiert=result.validated,
            fehler=result.error,
            nachricht=nachricht,
        )


class FullRestoreResponse(BaseModel):
    """Antwort fuer vollstaendigen Restore."""

    erfolg: bool = Field(..., description="Waren alle Restores erfolgreich?")
    erfolgreich: int = Field(..., description="Anzahl erfolgreicher Restores")
    fehlgeschlagen: int = Field(..., description="Anzahl fehlgeschlagener Restores")
    dry_run: bool = Field(..., description="War es ein Dry-Run?")
    restores: List[RestoreResponse] = Field(..., description="Details je Restore")
    nachricht: str = Field(..., description="Zusammenfassung")


class ValidationIssueResponse(BaseModel):
    """Einzelnes Validierungsproblem."""
    schweregrad: str = Field(..., description="error, warning, info")
    code: str = Field(..., description="Fehlercode")
    nachricht: str = Field(..., description="Beschreibung des Problems")
    details: Optional[Dict[str, Any]] = Field(None, description="Zusaetzliche Details")


class ValidateBackupResponse(BaseModel):
    """Antwort fuer Backup-Validierung."""

    gueltig: bool = Field(..., description="Ist Backup gueltig?")
    status: str = Field(..., description="valid, invalid, warning, skipped")
    backup_typ: str = Field(..., description="Erkannter Backup-Typ")
    groesse_bytes: int = Field(..., description="Groesse in Bytes")
    datei_anzahl: int = Field(0, description="Anzahl Dateien (bei Archiven)")
    checksum_sha256: Optional[str] = Field(None, description="SHA256 Checksum")
    verschluesselt: bool = Field(..., description="Ist Backup verschluesselt?")
    komprimiert: bool = Field(..., description="Ist Backup komprimiert?")
    validierung_level: str = Field("standard", description="quick, standard, deep, full")
    validierung_dauer_ms: int = Field(0, description="Dauer der Validierung in ms")
    probleme: List[ValidationIssueResponse] = Field(default_factory=list, description="Gefundene Probleme")
    anzahl_fehler: int = Field(0, description="Anzahl Fehler")
    anzahl_warnungen: int = Field(0, description="Anzahl Warnungen")
    details: Dict[str, Any] = Field(default_factory=dict, description="Weitere Metadaten")
    fehler: Optional[str] = Field(None, description="Hauptfehlermeldung bei ungueltigem Backup")


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/status",
    response_model=BackupStatusResponse,
    summary="Backup-System Status",
    description="Zeigt den aktuellen Status des Backup-Systems an.",
)
async def get_backup_status(
    current_user: User = Depends(get_current_superuser),
) -> BackupStatusResponse:
    """Hole Status des Backup-Systems."""
    service = get_backup_service()
    metrics = service.metrics

    # Speicherplatz und Dateien aktualisieren
    disk_usage = metrics.update_disk_usage()
    file_counts = metrics.update_backup_file_counts()

    logger.info(
        "backup_status_abgefragt",
        user_id=str(current_user.id),
    )

    return BackupStatusResponse(
        service_aktiv=True,
        encryption_aktiviert=service.config.encryption_enabled,
        remote_sync_aktiviert=service.config.remote_enabled,
        backup_verzeichnis=str(service.config.backup_dir),
        aufbewahrung_tage=service.config.retention_days,
        speicherplatz={
            "total_gb": round(disk_usage.total_bytes / 1024 / 1024 / 1024, 2),
            "verwendet_gb": round(disk_usage.used_bytes / 1024 / 1024 / 1024, 2),
            "frei_gb": round(disk_usage.free_bytes / 1024 / 1024 / 1024, 2),
            "verwendung_prozent": round(disk_usage.usage_percent, 1),
        },
        backup_dateien=file_counts,
    )


@router.get(
    "/list",
    response_model=BackupListResponse,
    summary="Liste alle Backups",
    description="Listet alle vorhandenen Backups auf.",
)
async def list_backups(
    backup_typ: Optional[str] = None,
    current_user: User = Depends(get_current_superuser),
) -> BackupListResponse:
    """Liste alle Backups auf."""
    service = get_backup_service()
    backups = service.list_backups(backup_type=backup_typ)

    items = [
        BackupListItem(
            typ=b["type"],
            name=b["name"],
            pfad=b["path"],
            groesse_bytes=b["size_bytes"],
            groesse_mb=b["size_mb"],
            erstellt=b["created"],
            verschluesselt=b["encrypted"],
        )
        for b in backups
    ]

    logger.info(
        "backup_liste_abgefragt",
        user_id=str(current_user.id),
        filter_typ=backup_typ,
        anzahl=len(items),
    )

    return BackupListResponse(anzahl=len(items), backups=items)


@router.post(
    "/postgres",
    response_model=BackupResponse,
    summary="PostgreSQL Backup",
    description="Erstellt ein PostgreSQL-Backup mit pg_dump.",
)
async def backup_postgres(
    current_user: User = Depends(get_current_superuser),
) -> BackupResponse:
    """Erstelle PostgreSQL-Backup."""
    logger.info(
        "postgres_backup_angefordert",
        user_id=str(current_user.id),
    )

    service = get_backup_service()
    result = await service.backup_postgres()

    return BackupResponse.from_result(result)


@router.post(
    "/redis",
    response_model=BackupResponse,
    summary="Redis Backup",
    description="Erstellt ein Redis-Backup (RDB Snapshot).",
)
async def backup_redis(
    current_user: User = Depends(get_current_superuser),
) -> BackupResponse:
    """Erstelle Redis-Backup."""
    logger.info(
        "redis_backup_angefordert",
        user_id=str(current_user.id),
    )

    service = get_backup_service()
    result = await service.backup_redis()

    return BackupResponse.from_result(result)


@router.post(
    "/minio",
    response_model=BackupResponse,
    summary="MinIO Backup",
    description="Erstellt ein MinIO-Backup (Bucket-Mirror).",
)
async def backup_minio(
    current_user: User = Depends(get_current_superuser),
) -> BackupResponse:
    """Erstelle MinIO-Backup."""
    logger.info(
        "minio_backup_angefordert",
        user_id=str(current_user.id),
    )

    service = get_backup_service()
    result = await service.backup_minio()

    return BackupResponse.from_result(result)


@router.post(
    "/config",
    response_model=BackupResponse,
    summary="Konfigurations-Backup",
    description="Erstellt ein Konfigurations-Backup (tar.gz).",
)
async def backup_config(
    current_user: User = Depends(get_current_superuser),
) -> BackupResponse:
    """Erstelle Konfigurations-Backup."""
    logger.info(
        "config_backup_angefordert",
        user_id=str(current_user.id),
    )

    service = get_backup_service()
    result = await service.backup_config()

    return BackupResponse.from_result(result)


@router.post(
    "/full",
    response_model=FullBackupResponse,
    summary="Vollstaendiges Backup",
    description="Erstellt Backups aller Komponenten (PostgreSQL, Redis, MinIO, Config).",
)
async def backup_full(
    current_user: User = Depends(get_current_superuser),
) -> FullBackupResponse:
    """Erstelle vollstaendiges Backup aller Komponenten."""
    logger.info(
        "vollstaendiges_backup_angefordert",
        user_id=str(current_user.id),
    )

    service = get_backup_service()
    results = await service.backup_full()

    success_count = sum(1 for r in results if r.success)
    failure_count = len(results) - success_count
    all_success = failure_count == 0

    responses = [BackupResponse.from_result(r) for r in results]

    if all_success:
        nachricht = f"Alle {len(results)} Backups erfolgreich erstellt."
    else:
        nachricht = f"{success_count} von {len(results)} Backups erfolgreich. {failure_count} fehlgeschlagen."

    return FullBackupResponse(
        erfolg=all_success,
        erfolgreich=success_count,
        fehlgeschlagen=failure_count,
        backups=responses,
        nachricht=nachricht,
    )


@router.post(
    "/full/async",
    response_model=AsyncBackupResponse,
    summary="Vollstaendiges Backup (Hintergrund)",
    description="Startet vollstaendiges Backup im Hintergrund.",
)
async def backup_full_async(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_superuser),
) -> AsyncBackupResponse:
    """Starte vollstaendiges Backup im Hintergrund."""
    logger.info(
        "vollstaendiges_backup_async_angefordert",
        user_id=str(current_user.id),
    )

    async def run_full_backup() -> None:
        service = get_backup_service()
        await service.backup_full()

    background_tasks.add_task(run_full_backup)

    return AsyncBackupResponse(
        gestartet=True,
        backup_typ="full",
        nachricht="Vollstaendiges Backup wurde im Hintergrund gestartet. Fortschritt in Logs und Metriken sichtbar.",
    )


@router.post(
    "/retention",
    response_model=RetentionResponse,
    summary="Retention Policy anwenden",
    description="Loescht alte Backups gemaess Retention Policy.",
)
async def apply_retention(
    current_user: User = Depends(get_current_superuser),
) -> RetentionResponse:
    """Wende Retention Policy an - loesche alte Backups."""
    logger.info(
        "retention_policy_angefordert",
        user_id=str(current_user.id),
    )

    service = get_backup_service()
    deleted = await service.apply_retention_policy()
    total_deleted = sum(deleted.values())

    if total_deleted > 0:
        nachricht = f"{total_deleted} alte Backup(s) geloescht."
    else:
        nachricht = "Keine alten Backups zum Loeschen gefunden."

    return RetentionResponse(
        erfolg=True,
        geloescht_gesamt=total_deleted,
        details=deleted,
        nachricht=nachricht,
    )


@router.post(
    "/sync",
    response_model=BackupResponse,
    summary="Remote-Synchronisation",
    description="Synchronisiert lokale Backups zum Remote-Server.",
)
async def sync_to_remote(
    current_user: User = Depends(get_current_superuser),
) -> BackupResponse:
    """Synchronisiere Backups zum Remote-Server."""
    logger.info(
        "remote_sync_angefordert",
        user_id=str(current_user.id),
    )

    service = get_backup_service()

    if not service.config.remote_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Remote-Synchronisation ist nicht konfiguriert.",
        )

    success = await service.sync_to_remote()

    return BackupResponse(
        erfolg=success,
        backup_typ="remote_sync",
        pfad=service.config.remote_target if success else None,
        groesse_bytes=0,
        groesse_mb=0.0,
        validiert=False,
        verschluesselt=False,
        remote_sync=success,
        fehler=None if success else "Remote-Synchronisation fehlgeschlagen. Details in Logs.",
    )


@router.get(
    "/remote/list",
    summary="Liste Remote-Backups",
    description="Listet Backups auf dem Remote-Server auf.",
)
async def list_remote_backups(
    current_user: User = Depends(get_current_superuser),
) -> Dict[str, Any]:
    """Liste Backups auf dem Remote-Server auf."""
    service = get_backup_service()

    if not service.config.remote_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Remote-Synchronisation ist nicht konfiguriert.",
        )

    backups = await service.list_remote_backups()

    return {
        "remote_ziel": service.config.remote_target,
        "anzahl": len(backups),
        "backups": backups,
    }


# =============================================================================
# Restore Endpoints
# =============================================================================


@router.post(
    "/restore/postgres",
    response_model=RestoreResponse,
    summary="PostgreSQL Restore",
    description="Stellt PostgreSQL-Datenbank aus Backup wieder her. ACHTUNG: Ueberschreibt aktuelle Daten!",
)
async def restore_postgres(
    request: RestoreRequest,
    current_user: User = Depends(get_current_superuser),
) -> RestoreResponse:
    """Stelle PostgreSQL aus Backup wieder her."""
    logger.warning(
        "postgres_restore_angefordert",
        user_id=str(current_user.id),
        backup_pfad=request.backup_pfad,
        dry_run=request.dry_run,
    )

    backup_path = Path(request.backup_pfad)

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup-Datei nicht gefunden: {request.backup_pfad}",
        )

    service = get_backup_service()
    result = await service.restore_postgres(backup_path, dry_run=request.dry_run)

    return RestoreResponse.from_result(result, dry_run=request.dry_run)


@router.post(
    "/restore/redis",
    response_model=RestoreResponse,
    summary="Redis Restore",
    description="Stellt Redis-Cache aus Backup wieder her. ACHTUNG: Ueberschreibt aktuelle Daten!",
)
async def restore_redis(
    request: RestoreRequest,
    current_user: User = Depends(get_current_superuser),
) -> RestoreResponse:
    """Stelle Redis aus Backup wieder her."""
    logger.warning(
        "redis_restore_angefordert",
        user_id=str(current_user.id),
        backup_pfad=request.backup_pfad,
        dry_run=request.dry_run,
    )

    backup_path = Path(request.backup_pfad)

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup-Datei nicht gefunden: {request.backup_pfad}",
        )

    service = get_backup_service()
    result = await service.restore_redis(backup_path, dry_run=request.dry_run)

    return RestoreResponse.from_result(result, dry_run=request.dry_run)


@router.post(
    "/restore/minio",
    response_model=RestoreResponse,
    summary="MinIO Restore",
    description="Stellt MinIO-Bucket aus Backup wieder her. ACHTUNG: Ueberschreibt aktuelle Daten!",
)
async def restore_minio(
    request: RestoreMinioRequest,
    current_user: User = Depends(get_current_superuser),
) -> RestoreResponse:
    """Stelle MinIO aus Backup wieder her."""
    logger.warning(
        "minio_restore_angefordert",
        user_id=str(current_user.id),
        backup_pfad=request.backup_pfad,
        bucket=request.bucket,
        dry_run=request.dry_run,
    )

    backup_path = Path(request.backup_pfad)

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup-Datei nicht gefunden: {request.backup_pfad}",
        )

    service = get_backup_service()
    result = await service.restore_minio(
        backup_path, bucket=request.bucket, dry_run=request.dry_run
    )

    return RestoreResponse.from_result(result, dry_run=request.dry_run)


@router.post(
    "/restore/full",
    response_model=FullRestoreResponse,
    summary="Vollstaendiger Restore",
    description="Stellt alle Komponenten aus Backup-Verzeichnis wieder her. ACHTUNG: Ueberschreibt alle Daten!",
)
async def restore_full(
    request: FullRestoreRequest,
    current_user: User = Depends(get_current_superuser),
) -> FullRestoreResponse:
    """Stelle alle Komponenten aus Backup wieder her."""
    logger.warning(
        "vollstaendiger_restore_angefordert",
        user_id=str(current_user.id),
        backup_verzeichnis=request.backup_verzeichnis,
        komponenten=request.komponenten,
        dry_run=request.dry_run,
    )

    backup_dir = Path(request.backup_verzeichnis)

    if not backup_dir.exists() or not backup_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup-Verzeichnis nicht gefunden: {request.backup_verzeichnis}",
        )

    service = get_backup_service()
    results = await service.restore_full(
        backup_dir, dry_run=request.dry_run, components=request.komponenten
    )

    success_count = sum(1 for r in results if r.success)
    failure_count = len(results) - success_count
    all_success = failure_count == 0

    responses = [RestoreResponse.from_result(r, dry_run=request.dry_run) for r in results]

    if all_success:
        nachricht = f"Alle {len(results)} Restores erfolgreich"
        if request.dry_run:
            nachricht += " (Dry-Run)"
    else:
        nachricht = f"{success_count} von {len(results)} Restores erfolgreich. {failure_count} fehlgeschlagen."

    return FullRestoreResponse(
        erfolg=all_success,
        erfolgreich=success_count,
        fehlgeschlagen=failure_count,
        dry_run=request.dry_run,
        restores=responses,
        nachricht=nachricht,
    )


@router.post(
    "/validate",
    response_model=ValidateBackupResponse,
    summary="Backup validieren",
    description="Validiert eine Backup-Datei mit tiefgehender Analyse ohne Restore.",
)
async def validate_backup(
    backup_pfad: str,
    level: str = "standard",
    current_user: User = Depends(get_current_superuser),
) -> ValidateBackupResponse:
    """
    Validiere eine Backup-Datei mit konfigurierbarer Tiefe.

    Args:
        backup_pfad: Pfad zur Backup-Datei
        level: Validierungsstufe (quick, standard, deep, full)
    """
    logger.info(
        "backup_validierung_angefordert",
        user_id=str(current_user.id),
        backup_pfad=backup_pfad,
        level=level,
    )

    backup_path = Path(backup_pfad)

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup-Datei nicht gefunden: {backup_pfad}",
        )

    # Validierungslevel parsen
    valid_levels = ["quick", "standard", "deep", "full"]
    try:
        validation_level = ValidationLevel(level.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Validierungslevel: '{level}'. "
                   f"Erlaubte Werte: {', '.join(valid_levels)}",
        )

    # BackupValidator verwenden
    validator = get_backup_validator()
    result = await validator.validate_backup(backup_path, level=validation_level)

    # Datei-Eigenschaften
    filename = backup_path.name.lower()
    verschluesselt = filename.endswith(".gpg")
    komprimiert = ".gz" in filename or ".tar" in filename

    # Probleme konvertieren
    probleme = [
        ValidationIssueResponse(
            schweregrad=issue.severity,
            code=issue.code,
            nachricht=issue.message,
            details=issue.details,
        )
        for issue in result.issues
    ]

    # Hauptfehler extrahieren
    fehler = None
    if result.error_count > 0:
        error_issues = [i for i in result.issues if i.severity == "error"]
        if error_issues:
            fehler = error_issues[0].message

    return ValidateBackupResponse(
        gueltig=result.is_valid,
        status=result.status.value,
        backup_typ=result.backup_type,
        groesse_bytes=result.total_size_bytes,
        datei_anzahl=result.file_count,
        checksum_sha256=result.checksum_sha256,
        verschluesselt=verschluesselt,
        komprimiert=komprimiert,
        validierung_level=validation_level.value,
        validierung_dauer_ms=result.validation_duration_ms,
        probleme=probleme,
        anzahl_fehler=result.error_count,
        anzahl_warnungen=result.warning_count,
        details=result.metadata,
        fehler=fehler,
    )


@router.post(
    "/validate-all",
    response_model=List[ValidateBackupResponse],
    summary="Alle Backups validieren",
    description="Validiert alle Backups im Backup-Verzeichnis.",
)
async def validate_all_backups(
    level: str = "standard",
    current_user: User = Depends(get_current_superuser),
) -> List[ValidateBackupResponse]:
    """
    Validiere alle Backups im konfigurierten Backup-Verzeichnis.

    Args:
        level: Validierungsstufe (quick, standard, deep, full)
    """
    logger.info(
        "alle_backups_validierung_angefordert",
        user_id=str(current_user.id),
        level=level,
    )

    # Validierungslevel parsen
    valid_levels = ["quick", "standard", "deep", "full"]
    try:
        validation_level = ValidationLevel(level.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Validierungslevel: '{level}'. "
                   f"Erlaubte Werte: {', '.join(valid_levels)}",
        )

    # Backup-Service und Validator
    service = get_backup_service()
    validator = get_backup_validator()

    # Alle Backups validieren
    results = await validator.validate_all_backups(
        service.config.backup_dir,
        level=validation_level,
    )

    # Ergebnisse konvertieren
    responses = []
    for result in results:
        filename = result.backup_path.name.lower()
        verschluesselt = filename.endswith(".gpg")
        komprimiert = ".gz" in filename or ".tar" in filename

        probleme = [
            ValidationIssueResponse(
                schweregrad=issue.severity,
                code=issue.code,
                nachricht=issue.message,
                details=issue.details,
            )
            for issue in result.issues
        ]

        fehler = None
        if result.error_count > 0:
            error_issues = [i for i in result.issues if i.severity == "error"]
            if error_issues:
                fehler = error_issues[0].message

        responses.append(ValidateBackupResponse(
            gueltig=result.is_valid,
            status=result.status.value,
            backup_typ=result.backup_type,
            groesse_bytes=result.total_size_bytes,
            datei_anzahl=result.file_count,
            checksum_sha256=result.checksum_sha256,
            verschluesselt=verschluesselt,
            komprimiert=komprimiert,
            validierung_level=validation_level.value,
            validierung_dauer_ms=result.validation_duration_ms,
            probleme=probleme,
            anzahl_fehler=result.error_count,
            anzahl_warnungen=result.warning_count,
            details={**result.metadata, "pfad": str(result.backup_path)},
            fehler=fehler,
        ))

    logger.info(
        "alle_backups_validiert",
        gesamt=len(responses),
        gueltig=sum(1 for r in responses if r.gueltig),
        ungueltig=sum(1 for r in responses if not r.gueltig),
    )

    return responses

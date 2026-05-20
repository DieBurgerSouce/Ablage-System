# -*- coding: utf-8 -*-
"""Admin-API fuer Field-Level Encryption.

Endpunkte fuer die Verwaltung der Feldbezogenen Verschluesselung:
- Status aller verschluesselten Felder abrufen
- Verschluesselungs-Migration starten
- Key-Rotation ausloesen
- Integritaet verifizieren

Nur fuer System-Administratoren zugaenglich.

DSGVO Art. 32 - Sicherheit der Verarbeitung.
Feinpoliert und durchdacht - Enterprise Encryption Management API.
"""

from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_superuser, get_db
from app.db.models import User
from app.core.safe_errors import safe_error_log
from app.services.encryption.field_encryption_service import (
    FieldEncryptionService,
    ENCRYPTED_FIELDS,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/encryption", tags=["encryption-admin"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class EncryptionFieldStatus(BaseModel):
    """Status eines einzelnen verschluesselten Feldes."""

    tabelle: str = Field(description="Name der Datenbank-Tabelle")
    spalte: str = Field(description="Name der verschluesselten Spalte")
    algorithmus: str = Field(description="Verwendeter Verschluesselungsalgorithmus")
    key_version: str = Field(description="Aktuelle Key-Version")
    status: str = Field(description="Status: active, pending, rotating, deprecated")
    zeilen_verschluesselt: str = Field(description="Anzahl verschluesselter Zeilen")
    letzte_rotation: str = Field(description="Zeitpunkt der letzten Key-Rotation")


class EncryptionStatusResponse(BaseModel):
    """Gesamtstatus der Field-Level Encryption."""

    felder: List[EncryptionFieldStatus]
    gesamt_felder: int = Field(description="Gesamtzahl verschluesselter Felder")
    aktive_felder: int = Field(description="Anzahl aktiver verschluesselter Felder")


class EncryptionMigrateRequest(BaseModel):
    """Request zum Starten einer Verschluesselungs-Migration."""

    tabelle: str = Field(description="Name der Tabelle")
    spalte: str = Field(description="Name der Spalte")
    batch_groesse: int = Field(
        default=500,
        ge=10,
        le=5000,
        description="Anzahl Zeilen pro Batch (10-5000)",
    )


class EncryptionMigrateResponse(BaseModel):
    """Response nach Start einer Verschluesselungs-Migration."""

    task_id: str = Field(description="Celery Task-ID fuer Fortschrittsueberwachung")
    nachricht: str = Field(description="Statusnachricht")
    tabelle: str
    spalte: str


class KeyRotationRequest(BaseModel):
    """Request fuer Key-Rotation."""

    tabelle: str = Field(description="Name der Tabelle")
    spalte: str = Field(description="Name der Spalte")
    batch_groesse: int = Field(
        default=500,
        ge=10,
        le=5000,
        description="Anzahl Zeilen pro Batch (10-5000)",
    )


class KeyRotationResponse(BaseModel):
    """Response nach Start einer Key-Rotation."""

    task_id: str = Field(description="Celery Task-ID")
    nachricht: str = Field(description="Statusnachricht")
    tabelle: str
    spalte: str


class EncryptionVerifyResponse(BaseModel):
    """Response der Verschluesselungs-Verifizierung."""

    task_id: str = Field(description="Celery Task-ID")
    nachricht: str = Field(description="Statusnachricht")


class EncryptionVerifyDetailResponse(BaseModel):
    """Detailliertes Ergebnis der Verschluesselungs-Verifizierung."""

    tabelle: str
    spalte: str
    stichprobe: int
    verschluesselt: int
    entschluesselbar: int
    klartext: int
    fehler: int
    intakt: bool


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/status",
    response_model=EncryptionStatusResponse,
    summary="Verschluesselungsstatus abrufen",
    description="Zeigt den Status aller verschluesselten Felder an. "
    "Nur fuer Administratoren.",
)
async def get_encryption_status(
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> EncryptionStatusResponse:
    """Gibt den Verschluesselungsstatus aller Felder zurueck.

    Zeigt fuer jedes verschluesselte Feld:
    - Verwendeter Algorithmus und Key-Version
    - Anzahl verschluesselter Zeilen
    - Status (active/pending/rotating/deprecated)
    - Zeitpunkt der letzten Key-Rotation
    """
    try:
        service = FieldEncryptionService(db)
        field_statuses = await service.get_encryption_status()

        felder = [EncryptionFieldStatus(**fs) for fs in field_statuses]
        aktive = sum(1 for f in felder if f.status == "active")

        return EncryptionStatusResponse(
            felder=felder,
            gesamt_felder=len(felder),
            aktive_felder=aktive,
        )
    except Exception as exc:
        logger.error("encryption_status_failed", **safe_error_log(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verschluesselungsstatus konnte nicht abgerufen werden.",
        )


@router.post(
    "/migrate",
    response_model=EncryptionMigrateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Verschluesselungs-Migration starten",
    description="Startet die Verschluesselung bestehender Klartext-Daten "
    "als Hintergrund-Task. Nur fuer Administratoren.",
)
async def start_encryption_migration(
    request: EncryptionMigrateRequest,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> EncryptionMigrateResponse:
    """Startet eine Verschluesselungs-Migration fuer ein Feld.

    Die Migration laeuft als Celery-Task im Hintergrund.
    Bestehende Klartext-Werte werden mit AES-256-GCM verschluesselt.
    Bereits verschluesselte Werte werden uebersprungen.
    """
    # Validierung: Feld muss in der Whitelist stehen
    valid_field = False
    for field in ENCRYPTED_FIELDS:
        if field["table"] == request.tabelle and field["column"] == request.spalte:
            valid_field = True
            break

    if not valid_field:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Ungueltiges Feld: {request.tabelle}.{request.spalte}. "
                f"Nur registrierte verschluesselte Felder sind erlaubt."
            ),
        )

    try:
        from app.workers.tasks.encryption_tasks import encrypt_field_task

        task = encrypt_field_task.delay(
            table_name=request.tabelle,
            column_name=request.spalte,
            batch_size=request.batch_groesse,
        )

        logger.info(
            "encryption_migration_started",
            task_id=task.id,
            table=request.tabelle,
            column=request.spalte,
            user_id=str(current_user.id),
        )

        return EncryptionMigrateResponse(
            task_id=task.id,
            nachricht=(
                f"Verschluesselung fuer {request.tabelle}.{request.spalte} "
                f"gestartet. Task-ID: {task.id}"
            ),
            tabelle=request.tabelle,
            spalte=request.spalte,
        )

    except Exception as exc:
        logger.error(
            "encryption_migration_start_failed",
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verschluesselungs-Migration konnte nicht gestartet werden.",
        )


@router.post(
    "/rotate",
    response_model=KeyRotationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Key-Rotation starten",
    description="Startet die Key-Rotation fuer ein verschluesseltes Feld "
    "als Hintergrund-Task. Nur fuer Administratoren.",
)
async def start_key_rotation(
    request: KeyRotationRequest,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> KeyRotationResponse:
    """Startet eine Key-Rotation fuer ein verschluesseltes Feld.

    Alle Werte werden mit dem alten Key entschluesselt und mit dem
    neuen Key neu verschluesselt. Der Fortschritt wird im
    key_rotation_logs protokolliert.
    """
    # Validierung: Feld muss in der Whitelist stehen
    valid_field = False
    for field in ENCRYPTED_FIELDS:
        if field["table"] == request.tabelle and field["column"] == request.spalte:
            valid_field = True
            break

    if not valid_field:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Ungueltiges Feld: {request.tabelle}.{request.spalte}. "
                f"Nur registrierte verschluesselte Felder sind erlaubt."
            ),
        )

    try:
        from app.workers.tasks.encryption_tasks import rotate_key_task

        task = rotate_key_task.delay(
            table_name=request.tabelle,
            column_name=request.spalte,
            batch_size=request.batch_groesse,
        )

        logger.info(
            "key_rotation_started",
            task_id=task.id,
            table=request.tabelle,
            column=request.spalte,
            user_id=str(current_user.id),
        )

        return KeyRotationResponse(
            task_id=task.id,
            nachricht=(
                f"Key-Rotation fuer {request.tabelle}.{request.spalte} "
                f"gestartet. Task-ID: {task.id}"
            ),
            tabelle=request.tabelle,
            spalte=request.spalte,
        )

    except Exception as exc:
        logger.error(
            "key_rotation_start_failed",
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Key-Rotation konnte nicht gestartet werden.",
        )


@router.get(
    "/verify",
    response_model=EncryptionVerifyResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Verschluesselung verifizieren",
    description="Startet die Verifizierung aller verschluesselten Felder "
    "als Hintergrund-Task. Nur fuer Administratoren.",
)
async def verify_encryption(
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> EncryptionVerifyResponse:
    """Startet die Verifizierung der Verschluesselungs-Integritaet.

    Prueft eine Stichprobe pro verschluesseltem Feld:
    - Sind die Daten verschluesselt?
    - Koennen sie korrekt entschluesselt werden?
    """
    try:
        from app.workers.tasks.encryption_tasks import verify_encryption_task

        task = verify_encryption_task.delay(sample_size=10)

        logger.info(
            "encryption_verify_started",
            task_id=task.id,
            user_id=str(current_user.id),
        )

        return EncryptionVerifyResponse(
            task_id=task.id,
            nachricht=(
                f"Verschluesselungs-Verifizierung gestartet. "
                f"Task-ID: {task.id}"
            ),
        )

    except Exception as exc:
        logger.error(
            "encryption_verify_start_failed",
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verschluesselungs-Verifizierung konnte nicht gestartet werden.",
        )


@router.get(
    "/verify/inline",
    response_model=List[EncryptionVerifyDetailResponse],
    summary="Verschluesselung direkt verifizieren",
    description="Verifiziert alle verschluesselten Felder synchron "
    "(fuer kleine Datenmengen). Nur fuer Administratoren.",
)
async def verify_encryption_inline(
    sample_size: int = 10,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[EncryptionVerifyDetailResponse]:
    """Verifiziert die Verschluesselung aller Felder synchron.

    Im Gegensatz zum asynchronen Endpunkt gibt dieser die Ergebnisse
    direkt zurueck. Geeignet fuer kleine Stichproben.

    Args:
        sample_size: Anzahl zu pruefender Zeilen pro Feld (1-100).
    """
    if sample_size < 1 or sample_size > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stichprobengroesse muss zwischen 1 und 100 liegen.",
        )

    try:
        service = FieldEncryptionService(db)
        results: List[EncryptionVerifyDetailResponse] = []

        for field in ENCRYPTED_FIELDS:
            try:
                verification = await service.verify_encryption(
                    table_name=field["table"],
                    column_name=field["column"],
                    sample_size=sample_size,
                )
                results.append(EncryptionVerifyDetailResponse(
                    tabelle=str(verification["tabelle"]),
                    spalte=str(verification["spalte"]),
                    stichprobe=int(verification["stichprobe"]),
                    verschluesselt=int(verification["verschluesselt"]),
                    entschluesselbar=int(verification["entschluesselbar"]),
                    klartext=int(verification["klartext"]),
                    fehler=int(verification["fehler"]),
                    intakt=bool(verification["intakt"]),
                ))
            except ValueError:
                results.append(EncryptionVerifyDetailResponse(
                    tabelle=field["table"],
                    spalte=field["column"],
                    stichprobe=0,
                    verschluesselt=0,
                    entschluesselbar=0,
                    klartext=0,
                    fehler=0,
                    intakt=False,
                ))

        return results

    except Exception as exc:
        logger.error("encryption_verify_inline_failed", **safe_error_log(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verschluesselungs-Verifizierung fehlgeschlagen.",
        )

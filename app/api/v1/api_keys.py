# -*- coding: utf-8 -*-
"""
API Key Management Endpoints für Ablage-System OCR.

CRUD-Operationen für programmatischen API-Zugriff:
- API-Keys erstellen, auflisten, aktualisieren, löschen
- Berechtigungen verwalten
- Rate Limits konfigurieren

Alle Antworten auf Deutsch.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.db.models import User
from app.db.schemas import (
    APIKeyCreate,
    APIKeyResponse,
    APIKeyCreateResponse,
    APIKeyUpdate,
    APIKeyListResponse,
    APIKeyDeleteResponse
)
from app.services.api_key_service import (
    get_api_key_service,
    APIKeyError,
    APIKeyLimitError,
    APIKeyNotFoundError
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="API-Key erstellen",
    description="Erstellt einen neuen API-Key für programmatischen Zugriff"
)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> APIKeyCreateResponse:
    """
    Erstellt einen neuen API-Key.

    **WICHTIG:** Der vollständige API-Key wird nur einmal bei der Erstellung
    angezeigt. Speichern Sie ihn sicher!

    - **name**: Name zur Identifikation des Keys
    - **description**: Optionale Beschreibung (z.B. "CI/CD Pipeline")
    - **permissions**: Liste von Berechtigungen
    - **rate_limit**: Maximale Anfragen pro Stunde
    - **expires_in_days**: Ablaufdatum in Tagen (optional)

    **Verfügbare Berechtigungen:**
    - `read:documents` - Dokumente lesen
    - `write:documents` - Dokumente erstellen/aktualisieren
    - `delete:documents` - Dokumente löschen
    - `ocr:process` - OCR-Verarbeitung starten
    - `search` - Suche verwenden
    - `admin` - Vollzugriff

    **Beispiel-Aufruf mit API-Key:**
    ```
    Authorization: Bearer ablage_abc123...
    ```
    """
    service = get_api_key_service()

    try:
        # Konvertiere Permissions Enum zu Strings
        permissions = [p.value for p in key_data.permissions]

        db_key, api_key = await service.create_api_key(
            db=db,
            user_id=current_user.id,
            name=key_data.name,
            description=key_data.description,
            permissions=permissions,
            rate_limit=key_data.rate_limit,
            expires_in_days=key_data.expires_in_days
        )

        # Extrahiere Key-Prefix für Identifikation
        key_prefix = api_key.replace("ablage_", "")[:8]

        logger.info(
            "api_key_created_by_user",
            user_id=str(current_user.id)[:8] + "...",
            key_name=key_data.name
        )

        return APIKeyCreateResponse(
            id=db_key.id,
            name=db_key.name,
            api_key=api_key,
            key_prefix=key_prefix,
            permissions=db_key.permissions,
            rate_limit=db_key.rate_limit,
            expires_at=db_key.expires_at
        )

    except APIKeyLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.user_message_de
        )


@router.get(
    "",
    response_model=APIKeyListResponse,
    summary="API-Keys auflisten",
    description="Listet alle API-Keys des aktuellen Benutzers auf"
)
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> APIKeyListResponse:
    """
    Listet alle API-Keys des aktuellen Benutzers auf.

    Zeigt für jeden Key:
    - Name und Beschreibung
    - Berechtigungen
    - Rate Limit
    - Erstellungsdatum
    - Letzte Verwendung
    - Ablaufdatum (falls gesetzt)
    - Status (aktiv/inaktiv)

    **Hinweis:** Der vollständige API-Key wird nie angezeigt,
    nur die ersten 8 Zeichen zur Identifikation.
    """
    service = get_api_key_service()
    keys = await service.get_user_keys(db, current_user.id)

    api_key_responses = []
    for key in keys:
        api_key_responses.append(APIKeyResponse(
            id=key.id,
            name=key.name,
            description=key.description,
            permissions=key.permissions,
            rate_limit=key.rate_limit,
            is_active=key.is_active,
            created_at=key.created_at,
            last_used=key.last_used,
            expires_at=key.expires_at,
            key_prefix=key.key_hash[:8] if key.key_hash else None
        ))

    return APIKeyListResponse(
        api_keys=api_key_responses,
        total=len(api_key_responses)
    )


@router.get(
    "/{key_id}",
    response_model=APIKeyResponse,
    summary="API-Key Details",
    description="Zeigt Details eines spezifischen API-Keys"
)
async def get_api_key(
    key_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> APIKeyResponse:
    """
    Gibt Details eines spezifischen API-Keys zurück.

    **Hinweis:** Sie können nur Ihre eigenen API-Keys abrufen.
    """
    service = get_api_key_service()
    db_key = await service.get_key_by_id(db, key_id, current_user.id)

    if not db_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API-Key nicht gefunden"
        )

    return APIKeyResponse(
        id=db_key.id,
        name=db_key.name,
        description=db_key.description,
        permissions=db_key.permissions,
        rate_limit=db_key.rate_limit,
        is_active=db_key.is_active,
        created_at=db_key.created_at,
        last_used=db_key.last_used,
        expires_at=db_key.expires_at,
        key_prefix=db_key.key_hash[:8] if db_key.key_hash else None
    )


@router.patch(
    "/{key_id}",
    response_model=APIKeyResponse,
    summary="API-Key aktualisieren",
    description="Aktualisiert einen API-Key"
)
async def update_api_key(
    key_id: UUID,
    update_data: APIKeyUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> APIKeyResponse:
    """
    Aktualisiert einen API-Key.

    **Aktualisierbare Felder:**
    - name
    - description
    - permissions
    - rate_limit
    - is_active (zum Deaktivieren/Reaktivieren)

    **Hinweis:** Der API-Key selbst kann nicht geändert werden.
    Erstellen Sie einen neuen Key, wenn Sie den Schlüssel ändern möchten.
    """
    service = get_api_key_service()

    try:
        # Konvertiere Permissions Enum zu Strings wenn vorhanden
        permissions = None
        if update_data.permissions is not None:
            permissions = [p.value for p in update_data.permissions]

        db_key = await service.update_key(
            db=db,
            key_id=key_id,
            user_id=current_user.id,
            name=update_data.name,
            description=update_data.description,
            permissions=permissions,
            rate_limit=update_data.rate_limit,
            is_active=update_data.is_active
        )

        return APIKeyResponse(
            id=db_key.id,
            name=db_key.name,
            description=db_key.description,
            permissions=db_key.permissions,
            rate_limit=db_key.rate_limit,
            is_active=db_key.is_active,
            created_at=db_key.created_at,
            last_used=db_key.last_used,
            expires_at=db_key.expires_at,
            key_prefix=db_key.key_hash[:8] if db_key.key_hash else None
        )

    except APIKeyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message_de
        )


@router.delete(
    "/{key_id}",
    response_model=APIKeyDeleteResponse,
    summary="API-Key löschen",
    description="Löscht einen API-Key permanent"
)
async def delete_api_key(
    key_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> APIKeyDeleteResponse:
    """
    Löscht einen API-Key permanent.

    **WARNUNG:** Diese Aktion kann nicht rückgängig gemacht werden!
    Alle Anwendungen, die diesen Key verwenden, verlieren den Zugriff.

    **Empfehlung:** Deaktivieren Sie den Key zuerst (PATCH mit is_active=false),
    um zu prüfen, ob noch Anwendungen ihn verwenden.
    """
    service = get_api_key_service()

    try:
        key_name = await service.delete_key(
            db=db,
            key_id=key_id,
            user_id=current_user.id
        )

        logger.info(
            "api_key_deleted_by_user",
            user_id=str(current_user.id)[:8] + "...",
            key_id=str(key_id)[:8] + "...",
            key_name=key_name
        )

        return APIKeyDeleteResponse(
            success=True,
            nachricht=f"API-Key '{key_name}' wurde erfolgreich gelöscht",
            deleted_key_name=key_name
        )

    except APIKeyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message_de
        )


@router.post(
    "/revoke-all",
    response_model=APIKeyDeleteResponse,
    summary="Alle API-Keys widerrufen",
    description="Deaktiviert alle API-Keys des Benutzers"
)
async def revoke_all_api_keys(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> APIKeyDeleteResponse:
    """
    Deaktiviert alle API-Keys des aktuellen Benutzers.

    **Anwendungsfälle:**
    - Bei Verdacht auf kompromittierte Keys
    - Beim Verlassen eines Projekts
    - Für Sicherheitsaudits

    **Hinweis:** Die Keys werden nicht gelöscht, sondern nur deaktiviert.
    Sie können einzelne Keys später wieder aktivieren.
    """
    service = get_api_key_service()
    count = await service.revoke_all_keys(db, current_user.id)

    logger.info(
        "all_api_keys_revoked_by_user",
        user_id=str(current_user.id)[:8] + "...",
        count=count
    )

    return APIKeyDeleteResponse(
        success=True,
        nachricht=f"{count} API-Key(s) wurden deaktiviert",
        deleted_key_name=f"{count} Keys"
    )

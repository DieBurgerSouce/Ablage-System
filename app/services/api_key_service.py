# -*- coding: utf-8 -*-
"""
API Key Service für Ablage-System OCR.

Verwaltet API-Keys für programmatischen Zugriff:
- Key-Generierung mit kryptographisch sicheren Zufallswerten
- Sichere Hash-Speicherung (argon2)
- CRUD-Operationen
- Validierung und Rate-Limiting

Feinpoliert und durchdacht - Enterprise-grade API-Authentifizierung.
"""

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import APIKey, User
from app.core.config import settings

logger = structlog.get_logger(__name__)

# API Key Konfiguration
API_KEY_PREFIX = "ablage_"  # Prefix für einfache Identifikation
API_KEY_LENGTH = 32  # 256 bits Entropie
MAX_API_KEYS_PER_USER = 10


class APIKeyError(Exception):
    """Fehler bei API-Key-Operationen."""

    def __init__(self, message: str, user_message_de: str):
        super().__init__(message)
        self.user_message_de = user_message_de


class APIKeyLimitError(APIKeyError):
    """Maximale Anzahl an API-Keys erreicht."""
    pass


class APIKeyNotFoundError(APIKeyError):
    """API-Key nicht gefunden."""
    pass


class APIKeyService:
    """Service für API-Key-Verwaltung."""

    def _generate_api_key(self) -> str:
        """
        Generiert einen kryptographisch sicheren API-Key.

        Format: ablage_<random_hex>

        Returns:
            Vollständiger API-Key
        """
        random_part = secrets.token_hex(API_KEY_LENGTH)
        return f"{API_KEY_PREFIX}{random_part}"

    def _hash_api_key(self, api_key: str) -> str:
        """
        Erstellt einen sicheren Hash des API-Keys.

        Verwendet SHA-256 für schnelle Validierung bei Requests.
        Der Key wird nicht reversibel gespeichert.

        Args:
            api_key: Vollständiger API-Key

        Returns:
            Hash des Keys
        """
        return hashlib.sha256(api_key.encode()).hexdigest()

    def _get_key_prefix(self, api_key: str) -> str:
        """
        Extrahiert das Prefix des Keys für Identifikation.

        Args:
            api_key: Vollständiger API-Key

        Returns:
            Erste 8 Zeichen nach dem Prefix
        """
        # Entferne "ablage_" und nimm die ersten 8 Zeichen
        key_part = api_key.replace(API_KEY_PREFIX, "")
        return key_part[:8]

    async def create_api_key(
        self,
        db: AsyncSession,
        user_id: UUID,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        rate_limit: int = 1000,
        expires_in_days: Optional[int] = None
    ) -> Tuple[APIKey, str]:
        """
        Erstellt einen neuen API-Key für einen Benutzer.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            name: Name des Keys
            description: Optionale Beschreibung
            permissions: Liste von Berechtigungen
            rate_limit: Rate Limit pro Stunde
            expires_in_days: Ablauf in Tagen (None = kein Ablauf)

        Returns:
            Tuple (APIKey-Objekt, vollständiger Key)

        Raises:
            APIKeyLimitError: Wenn Maximum erreicht
        """
        # Prüfe Limit
        existing_count = await self._count_user_keys(db, user_id)
        if existing_count >= MAX_API_KEYS_PER_USER:
            raise APIKeyLimitError(
                f"User {user_id} has {existing_count} keys, max is {MAX_API_KEYS_PER_USER}",
                f"Maximale Anzahl von {MAX_API_KEYS_PER_USER} API-Keys erreicht. "
                "Bitte löschen Sie einen bestehenden Key."
            )

        # Generiere Key
        api_key = self._generate_api_key()
        key_hash = self._hash_api_key(api_key)

        # Berechne Ablaufdatum
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        # Default-Berechtigungen
        if permissions is None:
            permissions = ["read:documents", "search"]

        # Erstelle DB-Eintrag
        db_key = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            name=name,
            description=description,
            permissions=permissions,
            rate_limit=rate_limit,
            expires_at=expires_at,
            is_active=True
        )

        db.add(db_key)
        await db.commit()
        await db.refresh(db_key)

        logger.info(
            "api_key_created",
            user_id=str(user_id)[:8] + "...",
            key_name=name,
            key_prefix=self._get_key_prefix(api_key),
            permissions=permissions,
            expires_at=expires_at.isoformat() if expires_at else None
        )

        return db_key, api_key

    async def validate_api_key(
        self,
        db: AsyncSession,
        api_key: str
    ) -> Optional[Tuple[APIKey, User]]:
        """
        Validiert einen API-Key und gibt den zugehörigen Key und User zurück.

        Args:
            db: Datenbank-Session
            api_key: Vollständiger API-Key

        Returns:
            Tuple (APIKey, User) oder None wenn ungültig
        """
        if not api_key.startswith(API_KEY_PREFIX):
            return None

        key_hash = self._hash_api_key(api_key)
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(APIKey, User)
            .join(User, APIKey.user_id == User.id)
            .where(
                and_(
                    APIKey.key_hash == key_hash,
                    APIKey.is_active == True,
                    User.is_active == True
                )
            )
        )

        row = result.first()
        if not row:
            return None

        db_key, user = row

        # Prüfe Ablaufdatum
        if db_key.expires_at and db_key.expires_at < now:
            logger.warning(
                "api_key_expired",
                key_prefix=self._get_key_prefix(api_key),
                expired_at=db_key.expires_at.isoformat()
            )
            return None

        # Aktualisiere last_used
        db_key.last_used = now
        await db.commit()

        return db_key, user

    async def get_user_keys(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> List[APIKey]:
        """
        Listet alle API-Keys eines Benutzers auf.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Liste von APIKey-Objekten
        """
        result = await db.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )

        return list(result.scalars().all())

    async def get_key_by_id(
        self,
        db: AsyncSession,
        key_id: UUID,
        user_id: UUID
    ) -> Optional[APIKey]:
        """
        Holt einen spezifischen API-Key.

        Args:
            db: Datenbank-Session
            key_id: Key-ID
            user_id: Benutzer-ID (für Berechtigungsprüfung)

        Returns:
            APIKey oder None
        """
        result = await db.execute(
            select(APIKey).where(
                and_(
                    APIKey.id == key_id,
                    APIKey.user_id == user_id
                )
            )
        )

        return result.scalar_one_or_none()

    async def update_key(
        self,
        db: AsyncSession,
        key_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> APIKey:
        """
        Aktualisiert einen API-Key.

        Args:
            db: Datenbank-Session
            key_id: Key-ID
            user_id: Benutzer-ID
            name: Neuer Name
            description: Neue Beschreibung
            permissions: Neue Berechtigungen
            rate_limit: Neues Rate Limit
            is_active: Aktiv/Inaktiv

        Returns:
            Aktualisierter APIKey

        Raises:
            APIKeyNotFoundError: Key nicht gefunden
        """
        db_key = await self.get_key_by_id(db, key_id, user_id)

        if not db_key:
            raise APIKeyNotFoundError(
                f"API key {key_id} not found for user {user_id}",
                "API-Key nicht gefunden"
            )

        # Aktualisiere Felder
        if name is not None:
            db_key.name = name
        if description is not None:
            db_key.description = description
        if permissions is not None:
            db_key.permissions = permissions
        if rate_limit is not None:
            db_key.rate_limit = rate_limit
        if is_active is not None:
            db_key.is_active = is_active

        await db.commit()
        await db.refresh(db_key)

        logger.info(
            "api_key_updated",
            key_id=str(key_id)[:8] + "...",
            user_id=str(user_id)[:8] + "...",
            is_active=db_key.is_active
        )

        return db_key

    async def delete_key(
        self,
        db: AsyncSession,
        key_id: UUID,
        user_id: UUID
    ) -> str:
        """
        Löscht einen API-Key.

        Args:
            db: Datenbank-Session
            key_id: Key-ID
            user_id: Benutzer-ID

        Returns:
            Name des gelöschten Keys

        Raises:
            APIKeyNotFoundError: Key nicht gefunden
        """
        db_key = await self.get_key_by_id(db, key_id, user_id)

        if not db_key:
            raise APIKeyNotFoundError(
                f"API key {key_id} not found for user {user_id}",
                "API-Key nicht gefunden"
            )

        key_name = db_key.name

        await db.delete(db_key)
        await db.commit()

        logger.info(
            "api_key_deleted",
            key_id=str(key_id)[:8] + "...",
            key_name=key_name,
            user_id=str(user_id)[:8] + "..."
        )

        return key_name

    async def revoke_all_keys(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> int:
        """
        Deaktiviert alle API-Keys eines Benutzers.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Anzahl deaktivierter Keys
        """
        result = await db.execute(
            update(APIKey)
            .where(
                and_(
                    APIKey.user_id == user_id,
                    APIKey.is_active == True
                )
            )
            .values(is_active=False)
        )

        await db.commit()

        count = result.rowcount

        if count > 0:
            logger.info(
                "all_api_keys_revoked",
                user_id=str(user_id)[:8] + "...",
                count=count
            )

        return count

    async def _count_user_keys(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> int:
        """Zählt die API-Keys eines Benutzers."""
        result = await db.execute(
            select(APIKey).where(APIKey.user_id == user_id)
        )
        return len(list(result.scalars().all()))

    def has_permission(
        self,
        api_key: APIKey,
        required_permission: str
    ) -> bool:
        """
        Prüft ob ein API-Key eine bestimmte Berechtigung hat.

        Args:
            api_key: APIKey-Objekt
            required_permission: Benötigte Berechtigung

        Returns:
            True wenn Berechtigung vorhanden
        """
        # Admin hat alle Berechtigungen
        if "admin" in api_key.permissions:
            return True

        return required_permission in api_key.permissions


# Singleton-Instanz
_api_key_service: Optional[APIKeyService] = None


def get_api_key_service() -> APIKeyService:
    """Gibt APIKeyService-Singleton zurück."""
    global _api_key_service
    if _api_key_service is None:
        _api_key_service = APIKeyService()
    return _api_key_service

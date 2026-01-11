# -*- coding: utf-8 -*-
"""
TempFileStorageService - Temporaere Datei-Speicherung fuer OCR-Review-Workflow.

Speichert Dateien temporaer in Redis mit 1 Stunde TTL.
Verwendet im Upload-Workflow:
1. OCR/process speichert Datei temporaer
2. User reviewed OCR-Ergebnis im Frontend
3. upload-complete holt Datei und speichert permanent in MinIO

Feinpoliert und durchdacht - fuer Enterprise Upload-Flows.
"""

import base64
import uuid
import json
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.core.redis_state import RedisStateManager

logger = structlog.get_logger(__name__)

# TTL fuer temporaere Dateien: 1 Stunde
TEMP_FILE_TTL_SECONDS = 3600

# Maximale Dateigroesse fuer Temp Storage: 50MB
# (Base64 encoding erhoeht Groesse um ~33%)
MAX_TEMP_FILE_SIZE_MB = 50
MAX_TEMP_FILE_SIZE_BYTES = MAX_TEMP_FILE_SIZE_MB * 1024 * 1024


@dataclass
class TempFileInfo:
    """Information ueber eine temporaer gespeicherte Datei."""
    temp_file_id: str
    original_filename: str
    mime_type: str
    file_size: int
    created_at: str
    user_id: str


@dataclass
class TempFile:
    """Temporaer gespeicherte Datei mit Inhalt."""
    temp_file_id: str
    original_filename: str
    mime_type: str
    file_size: int
    content: bytes
    created_at: str
    user_id: str


class TempFileStorageService:
    """
    Service fuer temporaere Datei-Speicherung.

    Speichert Dateien in Redis mit TTL fuer OCR-Review-Workflow.
    Automatisches Cleanup nach 1 Stunde.
    """

    def __init__(self):
        self._redis_manager: Optional[RedisStateManager] = None

    @property
    def redis(self) -> RedisStateManager:
        """Lazy-init Redis Manager."""
        if self._redis_manager is None:
            self._redis_manager = RedisStateManager.get_instance()
        return self._redis_manager

    async def store(
        self,
        file_content: bytes,
        original_filename: str,
        mime_type: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TempFileInfo:
        """
        Speichert Datei temporaer in Redis.

        Args:
            file_content: Dateiinhalt als Bytes
            original_filename: Originaler Dateiname
            mime_type: MIME-Type der Datei
            user_id: ID des hochladenden Users
            metadata: Optionale zusaetzliche Metadaten

        Returns:
            TempFileInfo mit temp_file_id

        Raises:
            ValueError: Wenn Datei zu gross
        """
        # Groessen-Check
        file_size = len(file_content)
        if file_size > MAX_TEMP_FILE_SIZE_BYTES:
            raise ValueError(
                f"Datei zu gross fuer temporaere Speicherung: {file_size / (1024*1024):.1f}MB. "
                f"Maximum: {MAX_TEMP_FILE_SIZE_MB}MB"
            )

        # Generiere eindeutige ID
        temp_file_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        # Datei als Base64 kodieren (Redis String-Speicherung)
        content_b64 = base64.b64encode(file_content).decode('utf-8')

        # Daten-Struktur
        data = {
            "temp_file_id": temp_file_id,
            "original_filename": original_filename,
            "mime_type": mime_type,
            "file_size": file_size,
            "content_b64": content_b64,
            "created_at": created_at,
            "user_id": user_id,
            "metadata": metadata or {},
        }

        # In Redis speichern mit TTL
        await self.redis._ensure_connection()
        key = f"temp_file:{temp_file_id}"
        await self.redis._redis.setex(
            key,
            TEMP_FILE_TTL_SECONDS,
            json.dumps(data)
        )

        logger.info(
            "temp_file_stored",
            temp_file_id=temp_file_id,
            filename=original_filename,
            size_mb=round(file_size / (1024*1024), 2),
            ttl_seconds=TEMP_FILE_TTL_SECONDS
        )

        return TempFileInfo(
            temp_file_id=temp_file_id,
            original_filename=original_filename,
            mime_type=mime_type,
            file_size=file_size,
            created_at=created_at,
            user_id=user_id
        )

    async def get(self, temp_file_id: str) -> Optional[TempFile]:
        """
        Holt temporaere Datei aus Redis.

        Args:
            temp_file_id: ID der temporaeren Datei

        Returns:
            TempFile mit Inhalt oder None wenn nicht gefunden/abgelaufen
        """
        await self.redis._ensure_connection()
        key = f"temp_file:{temp_file_id}"
        data_str = await self.redis._redis.get(key)

        if not data_str:
            logger.debug("temp_file_not_found", temp_file_id=temp_file_id)
            return None

        data = json.loads(data_str)

        # Base64 dekodieren
        content = base64.b64decode(data["content_b64"])

        logger.debug(
            "temp_file_retrieved",
            temp_file_id=temp_file_id,
            filename=data["original_filename"]
        )

        return TempFile(
            temp_file_id=data["temp_file_id"],
            original_filename=data["original_filename"],
            mime_type=data["mime_type"],
            file_size=data["file_size"],
            content=content,
            created_at=data["created_at"],
            user_id=data["user_id"]
        )

    async def get_info(self, temp_file_id: str) -> Optional[TempFileInfo]:
        """
        Holt nur Metadaten einer temporaeren Datei (ohne Inhalt).

        Args:
            temp_file_id: ID der temporaeren Datei

        Returns:
            TempFileInfo oder None
        """
        await self.redis._ensure_connection()
        key = f"temp_file:{temp_file_id}"
        data_str = await self.redis._redis.get(key)

        if not data_str:
            return None

        data = json.loads(data_str)

        return TempFileInfo(
            temp_file_id=data["temp_file_id"],
            original_filename=data["original_filename"],
            mime_type=data["mime_type"],
            file_size=data["file_size"],
            created_at=data["created_at"],
            user_id=data["user_id"]
        )

    async def delete(self, temp_file_id: str) -> bool:
        """
        Loescht temporaere Datei aus Redis.

        Args:
            temp_file_id: ID der temporaeren Datei

        Returns:
            True wenn geloescht, False wenn nicht gefunden
        """
        await self.redis._ensure_connection()
        key = f"temp_file:{temp_file_id}"
        deleted = await self.redis._redis.delete(key)

        if deleted:
            logger.info("temp_file_deleted", temp_file_id=temp_file_id)
            return True

        logger.debug("temp_file_delete_not_found", temp_file_id=temp_file_id)
        return False

    async def extend_ttl(self, temp_file_id: str, additional_seconds: int = 1800) -> bool:
        """
        Verlaengert TTL einer temporaeren Datei.

        Nuetzlich wenn User laenger im Review-Dialog bleibt.

        Args:
            temp_file_id: ID der temporaeren Datei
            additional_seconds: Zusaetzliche Sekunden (default: 30 Minuten)

        Returns:
            True wenn erfolgreich, False wenn nicht gefunden
        """
        await self.redis._ensure_connection()
        key = f"temp_file:{temp_file_id}"

        # Aktuelle TTL holen
        current_ttl = await self.redis._redis.ttl(key)
        if current_ttl < 0:
            return False

        # Neue TTL setzen (max 2 Stunden)
        new_ttl = min(current_ttl + additional_seconds, 7200)
        await self.redis._redis.expire(key, new_ttl)

        logger.debug(
            "temp_file_ttl_extended",
            temp_file_id=temp_file_id,
            new_ttl_seconds=new_ttl
        )

        return True


# Singleton-Instanz
_temp_file_storage: Optional[TempFileStorageService] = None


def get_temp_file_storage() -> TempFileStorageService:
    """Gibt Singleton-Instanz des TempFileStorageService zurueck."""
    global _temp_file_storage
    if _temp_file_storage is None:
        _temp_file_storage = TempFileStorageService()
    return _temp_file_storage

"""Audit Archive Service - WORM Storage für Audit-Logs.

Phase 1.4: Audit-Log Encryption + WORM Storage

Implementiert:
- MinIO Object Lock (GOVERNANCE mode) für unveränderbare Speicherung
- 10-Jahre Retention gemäß GoBD-Anforderungen
- Batch-Archivierung von Audit-Logs
- Integritätsprüfung archivierter Logs
- Export-Funktionen für Compliance-Audits

GoBD-Compliance:
- Aufbewahrungspflicht: 10 Jahre (§ 147 AO)
- Unveränderbarkeit: WORM (Write Once Read Many)
- Nachvollziehbarkeit: Hash-Chain + Verschlüsselung
- Verfügbarkeit: Jederzeit lesbar während Aufbewahrungsfrist
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from enum import Enum
from io import BytesIO
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Tuple

import structlog
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.core.audit_logger import (
    verify_audit_chain,
    get_audit_logs_for_export,
    decrypt_audit_metadata,
    GENESIS_HASH,
)

if TYPE_CHECKING:
    from minio import Minio

logger = structlog.get_logger(__name__)


# ==================== Configuration ====================

# MinIO Object Lock Retention (10 Jahre für GoBD)
AUDIT_RETENTION_YEARS = 10

# Batch-Größe für Archivierung
ARCHIVE_BATCH_SIZE = 1000

# Object Lock Mode: GOVERNANCE erlaubt Admin-Override, COMPLIANCE nicht
OBJECT_LOCK_MODE = "GOVERNANCE"

# Bucket-Name für Audit-Archive
AUDIT_ARCHIVE_BUCKET = "audit-archive"

# Prefix für archivierte Logs
ARCHIVE_PREFIX = "audit-logs"


class ArchiveStatus(str, Enum):
    """Status einer Archivierung."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"


@dataclass
class ArchiveResult:
    """Ergebnis einer Audit-Log-Archivierung."""
    archive_id: str
    object_key: str
    entries_archived: int
    start_sequence: int
    end_sequence: int
    content_hash: str
    retention_until: date
    created_at: datetime
    status: ArchiveStatus


@dataclass
class ArchiveVerificationResult:
    """Ergebnis einer Archiv-Verifikation."""
    archive_id: str
    is_valid: bool
    expected_hash: str
    actual_hash: str
    entries_verified: int
    chain_intact: bool
    retention_active: bool
    error_message: Optional[str] = None


class AuditArchiveService:
    """Service für die WORM-Archivierung von Audit-Logs.

    Archiviert Audit-Logs in MinIO mit Object Lock für unveränderbare
    Langzeit-Speicherung gemäß GoBD-Anforderungen.
    """

    def __init__(self) -> None:
        """Initialisiert den Archive Service."""
        self._minio_client: Optional[Minio] = None
        self._bucket_initialized = False

    @property
    def minio_client(self) -> Optional[Minio]:
        """Lazy-Initialisierung des MinIO-Clients."""
        if self._minio_client is None:
            try:
                from minio import Minio

                # MinIO-Konfiguration aus Settings
                endpoint = getattr(settings, 'MINIO_ENDPOINT', 'localhost:9000')
                access_key = getattr(settings, 'MINIO_ACCESS_KEY', None)
                secret_key = getattr(settings, 'MINIO_SECRET_KEY', None)
                secure = getattr(settings, 'MINIO_SECURE', False)

                if access_key and secret_key:
                    # SecretStr handling
                    access_key_val = access_key.get_secret_value() if hasattr(access_key, 'get_secret_value') else access_key
                    secret_key_val = secret_key.get_secret_value() if hasattr(secret_key, 'get_secret_value') else secret_key

                    self._minio_client = Minio(
                        endpoint,
                        access_key=access_key_val,
                        secret_key=secret_key_val,
                        secure=secure,
                    )
                else:
                    logger.warning("minio_credentials_not_configured")
                    return None

            except ImportError:
                logger.warning("minio_library_not_installed")
                return None
            except Exception as e:
                logger.error("minio_client_init_failed", **safe_error_log(e))
                return None

        return self._minio_client

    async def ensure_bucket_with_object_lock(self) -> bool:
        """Erstellt den Bucket mit Object Lock falls nicht vorhanden.

        WICHTIG: Object Lock muss beim Erstellen des Buckets aktiviert werden.
        Kann nachträglich nicht mehr aktiviert werden.

        Returns:
            True wenn Bucket bereit ist
        """
        if self._bucket_initialized:
            return True

        client = self.minio_client
        if not client:
            return False

        try:
            # Prüfe ob Bucket existiert
            if not client.bucket_exists(AUDIT_ARCHIVE_BUCKET):
                # Erstelle Bucket mit Object Lock
                client.make_bucket(AUDIT_ARCHIVE_BUCKET, object_lock=True)
                logger.info(
                    "audit_archive_bucket_created",
                    bucket=AUDIT_ARCHIVE_BUCKET,
                    object_lock=True,
                )

            # Setze Default-Retention (optional)
            # Dies setzt eine Standard-Retention für alle neuen Objekte
            try:
                from minio.retention import Retention
                from minio.commonconfig import GOVERNANCE

                retention = Retention(
                    GOVERNANCE,
                    datetime.now(timezone.utc) + timedelta(days=AUDIT_RETENTION_YEARS * 365),
                )
                # Default-Retention wird pro Objekt gesetzt, nicht auf Bucket-Ebene
            except ImportError:
                pass

            self._bucket_initialized = True
            return True

        except Exception as e:
            logger.error(
                "audit_archive_bucket_setup_failed",
                **safe_error_log(e),
            )
            return False

    async def archive_audit_logs(
        self,
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime,
        company_id: Optional[uuid.UUID] = None,
    ) -> ArchiveResult:
        """Archiviert Audit-Logs für einen Zeitraum in WORM-Storage.

        Args:
            db: Datenbank-Session
            start_date: Startdatum
            end_date: Enddatum
            company_id: Optional - nur Logs einer Firma

        Returns:
            ArchiveResult mit Details

        Raises:
            RuntimeError: Bei Archivierungsfehlern
        """
        from app.db.models import AuditLog


        # 1. Prüfe MinIO-Verfügbarkeit
        if not await self.ensure_bucket_with_object_lock():
            raise RuntimeError("MinIO-Bucket nicht verfügbar oder Object Lock nicht konfiguriert")

        # 2. Hole Audit-Logs aus DB
        query = select(AuditLog).where(
            and_(
                AuditLog.created_at >= start_date,
                AuditLog.created_at <= end_date,
            )
        ).order_by(AuditLog.sequence_number)

        if company_id:
            # Falls company_id Feld existiert (Multi-Tenant)
            if hasattr(AuditLog, 'company_id'):
                query = query.where(AuditLog.company_id == company_id)

        result = await db.execute(query.limit(ARCHIVE_BATCH_SIZE))
        entries = result.scalars().all()

        if not entries:
            raise ValueError("Keine Audit-Logs im angegebenen Zeitraum gefunden")

        # 3. Verifiziere Chain-Integrität vor Archivierung
        is_valid, errors = await verify_audit_chain(
            db,
            start_sequence=entries[0].sequence_number,
            end_sequence=entries[-1].sequence_number,
        )

        if not is_valid:
            logger.error(
                "audit_chain_invalid_before_archive",
                errors=errors[:5],  # Erste 5 Fehler
            )
            raise RuntimeError(f"Audit-Chain-Integrität verletzt: {errors[0] if errors else 'Unknown'}")

        # 4. Serialisiere Logs (inkl. verschlüsselter Metadaten)
        archive_data = {
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "entries_count": len(entries),
            "start_sequence": entries[0].sequence_number,
            "end_sequence": entries[-1].sequence_number,
            "first_hash": entries[0].integrity_hash,
            "last_hash": entries[-1].integrity_hash,
            "entries": [],
        }

        for entry in entries:
            archive_data["entries"].append({
                "id": str(entry.id),
                "sequence_number": entry.sequence_number,
                "user_id": str(entry.user_id) if entry.user_id else None,
                "action": entry.action,
                "resource_type": entry.resource_type,
                "resource_id": str(entry.resource_id) if entry.resource_id else None,
                "ip_address": entry.ip_address,
                "metadata": entry.audit_metadata,  # Bleibt verschlüsselt
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "integrity_hash": entry.integrity_hash,
                "previous_hash": entry.previous_hash,
            })

        # 5. Serialisiere zu JSON und berechne Hash
        archive_json = json.dumps(archive_data, sort_keys=True, ensure_ascii=False)
        archive_bytes = archive_json.encode('utf-8')
        content_hash = hashlib.sha256(archive_bytes).hexdigest()

        # 6. Generiere Object Key
        archive_id = str(uuid.uuid4())
        year_month = start_date.strftime("%Y/%m")
        object_key = f"{ARCHIVE_PREFIX}/{year_month}/{archive_id}.json"

        # 7. Upload mit Object Lock Retention
        retention_until = date.today() + timedelta(days=AUDIT_RETENTION_YEARS * 365)

        try:
            from minio.retention import Retention
            from minio.commonconfig import GOVERNANCE

            client = self.minio_client

            # Upload Objekt
            client.put_object(
                AUDIT_ARCHIVE_BUCKET,
                object_key,
                BytesIO(archive_bytes),
                len(archive_bytes),
                content_type="application/json",
                metadata={
                    "x-amz-meta-content-hash": content_hash,
                    "x-amz-meta-start-sequence": str(entries[0].sequence_number),
                    "x-amz-meta-end-sequence": str(entries[-1].sequence_number),
                    "x-amz-meta-entries-count": str(len(entries)),
                },
            )

            # Setze Object Lock Retention
            retention = Retention(
                GOVERNANCE,
                datetime.combine(retention_until, datetime.min.time()).replace(tzinfo=timezone.utc),
            )
            client.set_object_retention(
                AUDIT_ARCHIVE_BUCKET,
                object_key,
                retention,
            )

            logger.info(
                "audit_logs_archived",
                archive_id=archive_id,
                object_key=object_key,
                entries=len(entries),
                retention_until=retention_until.isoformat(),
            )

            return ArchiveResult(
                archive_id=archive_id,
                object_key=object_key,
                entries_archived=len(entries),
                start_sequence=entries[0].sequence_number,
                end_sequence=entries[-1].sequence_number,
                content_hash=content_hash,
                retention_until=retention_until,
                created_at=datetime.now(timezone.utc),
                status=ArchiveStatus.COMPLETED,
            )

        except Exception as e:
            logger.error(
                "audit_archive_upload_failed",
                **safe_error_log(e),
                archive_id=archive_id,
            )
            raise RuntimeError(f"Archivierung fehlgeschlagen: {str(e)}")

    async def verify_archive(
        self,
        object_key: str,
    ) -> ArchiveVerificationResult:
        """Verifiziert die Integrität eines archivierten Audit-Log-Pakets.

        Args:
            object_key: MinIO Object Key

        Returns:
            ArchiveVerificationResult mit Verifikationsstatus
        """
        client = self.minio_client
        if not client:
            return ArchiveVerificationResult(
                archive_id="",
                is_valid=False,
                expected_hash="",
                actual_hash="",
                entries_verified=0,
                chain_intact=False,
                retention_active=False,
                error_message="MinIO-Client nicht verfügbar",
            )

        try:
            # 1. Lade Archiv
            response = client.get_object(AUDIT_ARCHIVE_BUCKET, object_key)
            archive_bytes = response.read()
            response.close()
            response.release_conn()

            # 2. Berechne aktuellen Hash
            actual_hash = hashlib.sha256(archive_bytes).hexdigest()

            # 3. Hole erwarteten Hash aus Metadaten
            stat = client.stat_object(AUDIT_ARCHIVE_BUCKET, object_key)
            expected_hash = stat.metadata.get("x-amz-meta-content-hash", "")

            # 4. Parse Archiv
            archive_data = json.loads(archive_bytes.decode('utf-8'))
            archive_id = object_key.split("/")[-1].replace(".json", "")

            # 5. Verifiziere Hash-Chain der Einträge
            entries = archive_data.get("entries", [])
            chain_intact = True
            previous_hash = None

            for entry in entries:
                if previous_hash is not None:
                    if entry.get("previous_hash") != previous_hash:
                        chain_intact = False
                        break
                previous_hash = entry.get("integrity_hash")

            # 6. Prüfe Retention-Status
            retention_active = False
            try:
                retention = client.get_object_retention(AUDIT_ARCHIVE_BUCKET, object_key)
                if retention and retention.retain_until_date:
                    retention_active = retention.retain_until_date > datetime.now(timezone.utc)
            except Exception:
                # Object Lock nicht aktiv oder Fehler
                pass

            is_valid = (actual_hash == expected_hash) and chain_intact

            return ArchiveVerificationResult(
                archive_id=archive_id,
                is_valid=is_valid,
                expected_hash=expected_hash,
                actual_hash=actual_hash,
                entries_verified=len(entries),
                chain_intact=chain_intact,
                retention_active=retention_active,
                error_message=None if is_valid else "Hash-Mismatch oder Chain-Bruch",
            )

        except Exception as e:
            logger.error(
                "audit_archive_verification_failed",
                object_key=object_key,
                **safe_error_log(e),
            )
            return ArchiveVerificationResult(
                archive_id="",
                is_valid=False,
                expected_hash="",
                actual_hash="",
                entries_verified=0,
                chain_intact=False,
                retention_active=False,
                error_message=safe_error_detail(e, "Audit-Archiv"),
            )

    async def list_archives(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Listet alle archivierten Audit-Log-Pakete.

        Args:
            year: Optional - Filter nach Jahr
            month: Optional - Filter nach Monat

        Returns:
            Liste von Archiv-Informationen
        """
        client = self.minio_client
        if not client:
            return []

        prefix = ARCHIVE_PREFIX
        if year:
            prefix = f"{ARCHIVE_PREFIX}/{year}"
            if month:
                prefix = f"{ARCHIVE_PREFIX}/{year}/{month:02d}"

        try:
            objects = client.list_objects(
                AUDIT_ARCHIVE_BUCKET,
                prefix=prefix,
                recursive=True,
            )

            archives = []
            for obj in objects:
                if obj.object_name.endswith(".json"):
                    # Hole Metadaten
                    try:
                        stat = client.stat_object(AUDIT_ARCHIVE_BUCKET, obj.object_name)
                        metadata = stat.metadata
                    except Exception:
                        metadata = {}

                    archives.append({
                        "object_key": obj.object_name,
                        "size": obj.size,
                        "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                        "content_hash": metadata.get("x-amz-meta-content-hash"),
                        "entries_count": metadata.get("x-amz-meta-entries-count"),
                        "start_sequence": metadata.get("x-amz-meta-start-sequence"),
                        "end_sequence": metadata.get("x-amz-meta-end-sequence"),
                    })

            return archives

        except Exception as e:
            logger.error("audit_archive_list_failed", **safe_error_log(e))
            return []

    async def get_archive_content(
        self,
        object_key: str,
        decrypt_metadata: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Lädt und parst ein Audit-Log-Archiv.

        Args:
            object_key: MinIO Object Key
            decrypt_metadata: Ob verschlüsselte Metadaten entschlüsselt werden

        Returns:
            Archiv-Inhalt als Dict oder None
        """
        client = self.minio_client
        if not client:
            return None

        try:
            response = client.get_object(AUDIT_ARCHIVE_BUCKET, object_key)
            archive_bytes = response.read()
            response.close()
            response.release_conn()

            archive_data = json.loads(archive_bytes.decode('utf-8'))

            if decrypt_metadata:
                for entry in archive_data.get("entries", []):
                    if entry.get("metadata"):
                        entry["metadata"] = decrypt_audit_metadata(
                            entry["metadata"],
                            entry.get("id", ""),
                        )

            return archive_data

        except Exception as e:
            logger.error(
                "audit_archive_get_failed",
                object_key=object_key,
                **safe_error_log(e),
            )
            return None

    async def get_archive_statistics(self) -> Dict[str, Any]:
        """Holt Statistiken über alle Archive.

        Returns:
            Dict mit Archiv-Statistiken
        """
        client = self.minio_client
        if not client:
            return {
                "available": False,
                "error": "MinIO-Client nicht verfügbar",
            }

        try:
            objects = list(client.list_objects(
                AUDIT_ARCHIVE_BUCKET,
                prefix=ARCHIVE_PREFIX,
                recursive=True,
            ))

            total_size = sum(obj.size or 0 for obj in objects)
            total_archives = len([o for o in objects if o.object_name.endswith(".json")])

            # Gruppiere nach Jahr
            by_year: Dict[str, int] = {}
            for obj in objects:
                if obj.object_name.endswith(".json"):
                    parts = obj.object_name.split("/")
                    if len(parts) >= 2:
                        year = parts[1]
                        by_year[year] = by_year.get(year, 0) + 1

            return {
                "available": True,
                "total_archives": total_archives,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "by_year": by_year,
                "retention_years": AUDIT_RETENTION_YEARS,
                "object_lock_mode": OBJECT_LOCK_MODE,
            }

        except Exception as e:
            return {
                "available": False,
                "error": safe_error_detail(e, "Vorgang"),
            }


# Singleton-Instanz
audit_archive_service = AuditArchiveService()


# ==================== Convenience Functions ====================

async def archive_monthly_audit_logs(
    db: AsyncSession,
    year: int,
    month: int,
    company_id: Optional[uuid.UUID] = None,
) -> ArchiveResult:
    """Archiviert alle Audit-Logs eines Monats.

    Args:
        db: Datenbank-Session
        year: Jahr
        month: Monat (1-12)
        company_id: Optional - nur Logs einer Firma

    Returns:
        ArchiveResult
    """
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    return await audit_archive_service.archive_audit_logs(
        db, start_date, end_date, company_id
    )


async def verify_all_archives(
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Verifiziert alle Archive eines Jahres.

    Args:
        year: Jahr (default: aktuelles Jahr)

    Returns:
        Dict mit Verifikationsergebnissen
    """
    if year is None:
        year = date.today().year

    archives = await audit_archive_service.list_archives(year=year)

    results = {
        "year": year,
        "total_archives": len(archives),
        "verified": 0,
        "valid": 0,
        "invalid": 0,
        "errors": [],
    }

    for archive in archives:
        try:
            result = await audit_archive_service.verify_archive(archive["object_key"])
            results["verified"] += 1

            if result.is_valid:
                results["valid"] += 1
            else:
                results["invalid"] += 1
                results["errors"].append({
                    "object_key": archive["object_key"],
                    "error": result.error_message,
                })

        except Exception as e:
            results["errors"].append({
                "object_key": archive["object_key"],
                "error": safe_error_detail(e, "Vorgang"),
            })

    return results

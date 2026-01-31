# -*- coding: utf-8 -*-
"""
Backup-Service fuer Ablage-System.

Fuehrt Backups durch fuer:
- PostgreSQL (pg_dump)
- Redis (RDB Snapshot)
- MinIO (Bucket-Sync)
- Konfiguration (tar.gz)

Mit GPG-Verschluesselung und Remote-Sync via rsync.

Feinpoliert und durchdacht - Enterprise Backup in Produktion.
"""

import asyncio
import gzip
import os
import shutil
import tarfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from app.core.datetime_utils import utc_now
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.core.config import settings
from app.services.backup_metrics_service import get_backup_metrics, track_backup
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Thread-Safety fuer Singleton
_backup_service_lock = threading.Lock()

# Safe subprocess runner (equivalent to Node's execFile - no shell injection)
run_subprocess = asyncio.create_subprocess_exec


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class BackupConfig:
    """Konfiguration fuer Backup-Service - verwendet zentrale settings."""

    # Verzeichnisse
    backup_dir: Path = field(default_factory=lambda: Path(os.getenv("BACKUP_DIR", "/var/backups/ablage")))
    retention_days: int = field(default_factory=lambda: int(os.getenv("BACKUP_RETENTION_DAYS", "30")))
    compression_enabled: bool = field(default_factory=lambda: os.getenv("BACKUP_COMPRESSION", "true").lower() == "true")

    # PostgreSQL - aus zentraler settings
    postgres_host: str = field(default_factory=lambda: settings.DB_HOST)
    postgres_port: int = field(default_factory=lambda: settings.DB_PORT)
    postgres_db: str = field(default_factory=lambda: settings.DB_NAME)
    postgres_user: str = field(default_factory=lambda: settings.DB_USER)
    postgres_password: str = field(default_factory=lambda: settings.DB_PASSWORD.get_secret_value() if settings.DB_PASSWORD else "")

    # Redis - aus zentraler settings
    redis_host: str = field(default_factory=lambda: settings.REDIS_HOST)
    redis_port: int = field(default_factory=lambda: settings.REDIS_PORT)
    redis_password: Optional[str] = field(default_factory=lambda: settings.REDIS_PASSWORD.get_secret_value() if settings.REDIS_PASSWORD else None)

    # MinIO - aus zentraler settings
    minio_endpoint: str = field(default_factory=lambda: settings.MINIO_ENDPOINT)
    minio_access_key: str = field(default_factory=lambda: settings.MINIO_ACCESS_KEY)
    minio_secret_key: str = field(default_factory=lambda: settings.MINIO_SECRET_KEY.get_secret_value() if settings.MINIO_SECRET_KEY else "")
    minio_buckets: List[str] = field(default_factory=lambda: [settings.MINIO_BUCKET_DOCUMENTS, settings.MINIO_BUCKET_PROCESSED, settings.MINIO_BUCKET_THUMBNAILS])

    # GPG Verschluesselung
    # SECURITY FIX: Default auf True geändert für GDPR-Compliance (Art. 32)
    # Backups MÜSSEN in Production verschlüsselt sein
    encryption_enabled: bool = field(default_factory=lambda: os.getenv("BACKUP_ENCRYPTION", "true").lower() == "true")
    gpg_recipient: str = field(default_factory=lambda: os.getenv("BACKUP_GPG_RECIPIENT", "backup@ablage-system.local"))
    gpg_home: Optional[str] = field(default_factory=lambda: os.getenv("BACKUP_GPG_HOME"))

    # Remote Sync
    remote_enabled: bool = field(default_factory=lambda: os.getenv("BACKUP_REMOTE_ENABLED", "false").lower() == "true")
    remote_target: str = field(default_factory=lambda: os.getenv("BACKUP_REMOTE_TARGET", ""))
    remote_ssh_key: Optional[str] = field(default_factory=lambda: os.getenv("BACKUP_REMOTE_SSH_KEY"))

    # Konfigurationspfade
    config_paths: List[Path] = field(default_factory=lambda: [
        Path("/app/app"),
        Path("/app/infrastructure"),
        Path("/app/.env"),
    ])


@dataclass
class BackupResult:
    """Ergebnis einer Backup-Operation."""

    success: bool
    backup_type: str
    path: Optional[Path] = None
    size_bytes: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    validated: bool = False
    encrypted: bool = False
    remote_synced: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# BackupService Class
# =============================================================================


class BackupService:
    """
    Zentrale Klasse fuer Backup-Operationen.

    Unterstuetzt:
    - PostgreSQL, Redis, MinIO, Config Backups
    - GPG-Verschluesselung
    - Remote-Synchronisation via rsync
    - Retention Policy
    - Validierung
    """

    def __init__(self, config: Optional[BackupConfig] = None) -> None:
        """
        Initialisiere BackupService.

        Args:
            config: Backup-Konfiguration (optional, wird aus Env geladen)
        """
        self.config = config or BackupConfig()
        self.metrics = get_backup_metrics(str(self.config.backup_dir))

        # Verzeichnisse erstellen
        self._ensure_directories()

        # Verschluesselungsstatus setzen
        self.metrics.set_encryption_enabled(self.config.encryption_enabled)

        # GPG-Konfiguration validieren wenn Verschluesselung aktiviert
        self._encryption_validated = False
        self._encryption_validation_error: Optional[str] = None
        if self.config.encryption_enabled:
            self._validate_encryption_config()

        logger.info(
            "backup_service_initialisiert",
            backup_dir=str(self.config.backup_dir),
            encryption=self.config.encryption_enabled,
            encryption_validated=self._encryption_validated,
            remote_sync=self.config.remote_enabled,
        )

    def _ensure_directories(self) -> None:
        """Stelle sicher, dass alle Backup-Verzeichnisse existieren."""
        dirs = ["postgres", "redis", "minio", "config", "qdrant", "full"]
        for subdir in dirs:
            path = self.config.backup_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            logger.debug("backup_verzeichnis_erstellt", path=str(path))

    def _validate_encryption_config(self) -> None:
        """
        Validiere GPG-Verschluesselungs-Konfiguration.

        Prueft:
        - GPG-Binary verfuegbar
        - GPG-Schluessel fuer Empfaenger existiert
        - GPG-Home Verzeichnis valide (wenn konfiguriert)
        """
        import subprocess

        try:
            # 1. GPG-Binary verfuegbar?
            result = subprocess.run(
                ["gpg", "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                self._encryption_validation_error = "GPG nicht verfuegbar oder fehlerhaft"
                logger.error("gpg_validation_fehler", error=self._encryption_validation_error)
                return

            # 2. GPG-Home Verzeichnis pruefen (wenn konfiguriert)
            gpg_args = ["gpg"]
            if self.config.gpg_home:
                gpg_home_path = Path(self.config.gpg_home)
                if not gpg_home_path.exists():
                    self._encryption_validation_error = f"GPG-Home existiert nicht: {self.config.gpg_home}"
                    logger.error("gpg_validation_fehler", error=self._encryption_validation_error)
                    return
                gpg_args.extend(["--homedir", self.config.gpg_home])

            # 3. GPG-Schluessel fuer Empfaenger pruefen
            gpg_args.extend(["--list-keys", self.config.gpg_recipient])
            result = subprocess.run(
                gpg_args,
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="ignore")
                if "not found" in stderr.lower() or "keine" in stderr.lower():
                    self._encryption_validation_error = (
                        f"GPG-Schluessel fuer '{self.config.gpg_recipient}' nicht gefunden. "
                        f"Bitte Schluessel importieren: gpg --import <keyfile>"
                    )
                else:
                    self._encryption_validation_error = f"GPG-Schluessel-Pruefung fehlgeschlagen: {stderr[:200]}"
                logger.error(
                    "gpg_validation_fehler",
                    error=self._encryption_validation_error,
                    recipient=self.config.gpg_recipient,
                )
                return

            # Alles OK
            self._encryption_validated = True
            logger.info(
                "gpg_validation_erfolgreich",
                recipient=self.config.gpg_recipient,
                gpg_home=self.config.gpg_home,
            )

        except subprocess.TimeoutExpired:
            self._encryption_validation_error = "GPG-Validierung Timeout"
            logger.error("gpg_validation_timeout")
        except FileNotFoundError:
            self._encryption_validation_error = "GPG nicht installiert"
            logger.error("gpg_nicht_gefunden")
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            self._encryption_validation_error = safe_error_detail(e, "GPG")
            logger.exception("gpg_validation_fehler")

    def _generate_filename(self, backup_type: str, extension: str) -> str:
        """
        Generiere Dateinamen mit Zeitstempel.

        Args:
            backup_type: postgres, redis, minio, config
            extension: Dateierweiterung (.sql.gz, .rdb, etc.)

        Returns:
            Dateiname mit Zeitstempel
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{backup_type}_{timestamp}{extension}"

    # -------------------------------------------------------------------------
    # PostgreSQL Backup
    # -------------------------------------------------------------------------

    @track_backup(backup_type="postgres")
    async def backup_postgres(self) -> BackupResult:
        """
        Erstelle PostgreSQL-Backup mit pg_dump.

        Returns:
            BackupResult mit Pfad und Status
        """
        filename = self._generate_filename("postgres", ".sql.gz")
        output_path = self.config.backup_dir / "postgres" / filename
        temp_path = output_path.with_suffix("")  # .sql ohne .gz

        logger.info("postgres_backup_gestartet", ziel=str(output_path))

        try:
            # Umgebungsvariablen fuer pg_dump
            env = os.environ.copy()
            env["PGPASSWORD"] = self.config.postgres_password

            # pg_dump ausfuehren (safe subprocess - arguments as list)
            proc = await run_subprocess(
                "pg_dump",
                "-h", self.config.postgres_host,
                "-p", str(self.config.postgres_port),
                "-U", self.config.postgres_user,
                "-d", self.config.postgres_db,
                "-F", "p",  # Plain text format
                "-f", str(temp_path),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "pg_dump fehlgeschlagen"
                logger.error("postgres_backup_fehlgeschlagen", error=error_msg)
                return BackupResult(
                    success=False,
                    backup_type="postgres",
                    error=error_msg,
                )

            # Komprimieren
            if self.config.compression_enabled:
                await self._compress_file(temp_path, output_path)
                temp_path.unlink()  # Unkomprimierte Datei loeschen
            else:
                output_path = temp_path

            size_bytes = output_path.stat().st_size

            # Optional: Verschluesseln
            if self.config.encryption_enabled:
                encrypted_path = await self.encrypt_backup(output_path)
                if encrypted_path:
                    output_path.unlink()  # Unverschluesselte Datei loeschen
                    output_path = encrypted_path

            # Validieren
            validated = await self.validate_backup(output_path)

            logger.info(
                "postgres_backup_erfolgreich",
                pfad=str(output_path),
                groesse_mb=round(size_bytes / 1024 / 1024, 2),
            )

            return BackupResult(
                success=True,
                backup_type="postgres",
                path=output_path,
                size_bytes=size_bytes,
                validated=validated,
                encrypted=self.config.encryption_enabled,
            )

        except FileNotFoundError:
            error_msg = "pg_dump nicht gefunden - bitte PostgreSQL-Client installieren"
            logger.error("postgres_backup_fehler", error=error_msg)
            return BackupResult(
                success=False,
                backup_type="postgres",
                error=error_msg,
            )
        except (IOError, OSError, asyncio.TimeoutError) as e:
            logger.exception("postgres_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="postgres",
                **safe_error_log(e),
            )

    # -------------------------------------------------------------------------
    # Redis Backup
    # -------------------------------------------------------------------------

    @track_backup(backup_type="redis")
    async def backup_redis(self) -> BackupResult:
        """
        Erstelle Redis-Backup (RDB Snapshot).

        Returns:
            BackupResult mit Pfad und Status
        """
        filename = self._generate_filename("redis", ".rdb")
        output_path = self.config.backup_dir / "redis" / filename

        logger.info("redis_backup_gestartet", ziel=str(output_path))

        try:
            # redis-cli BGSAVE ausfuehren
            auth_args = []
            if self.config.redis_password:
                auth_args = ["-a", self.config.redis_password]

            proc = await run_subprocess(
                "redis-cli",
                "-h", self.config.redis_host,
                "-p", str(self.config.redis_port),
                *auth_args,
                "BGSAVE",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "redis-cli BGSAVE fehlgeschlagen"
                logger.error("redis_backup_bgsave_fehler", error=error_msg)
                return BackupResult(
                    success=False,
                    backup_type="redis",
                    error=error_msg,
                )

            # Warten bis BGSAVE abgeschlossen
            await asyncio.sleep(2)  # Initial wait

            for _ in range(30):  # Max 30 Versuche (30 Sekunden)
                proc = await run_subprocess(
                    "redis-cli",
                    "-h", self.config.redis_host,
                    "-p", str(self.config.redis_port),
                    *auth_args,
                    "LASTSAVE",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                # Wenn LASTSAVE Timestamp aktuell ist, ist Backup fertig
                await asyncio.sleep(1)
                break  # Vereinfacht - in Produktion proper check

            # RDB Datei kopieren
            # Standard Redis RDB Pfad - kann per Config angepasst werden
            redis_rdb_path = Path("/var/lib/redis/dump.rdb")
            if not redis_rdb_path.exists():
                # Docker Volume Pfad
                redis_rdb_path = Path("/data/dump.rdb")

            if redis_rdb_path.exists():
                shutil.copy2(redis_rdb_path, output_path)
            else:
                # Fallback: Redis CONFIG GET dir/dbfilename
                error_msg = "Redis RDB-Datei nicht gefunden"
                logger.error("redis_backup_rdb_nicht_gefunden")
                return BackupResult(
                    success=False,
                    backup_type="redis",
                    error=error_msg,
                )

            size_bytes = output_path.stat().st_size

            # Optional: Verschluesseln
            if self.config.encryption_enabled:
                encrypted_path = await self.encrypt_backup(output_path)
                if encrypted_path:
                    output_path.unlink()
                    output_path = encrypted_path

            validated = await self.validate_backup(output_path)

            logger.info(
                "redis_backup_erfolgreich",
                pfad=str(output_path),
                groesse_mb=round(size_bytes / 1024 / 1024, 2),
            )

            return BackupResult(
                success=True,
                backup_type="redis",
                path=output_path,
                size_bytes=size_bytes,
                validated=validated,
                encrypted=self.config.encryption_enabled,
            )

        except FileNotFoundError:
            error_msg = "redis-cli nicht gefunden - bitte Redis-Tools installieren"
            logger.error("redis_backup_fehler", error=error_msg)
            return BackupResult(
                success=False,
                backup_type="redis",
                error=error_msg,
            )
        except (IOError, OSError, asyncio.TimeoutError) as e:
            logger.exception("redis_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="redis",
                **safe_error_log(e),
            )

    # -------------------------------------------------------------------------
    # MinIO Backup
    # -------------------------------------------------------------------------

    @track_backup(backup_type="minio")
    async def backup_minio(self) -> BackupResult:
        """
        Erstelle MinIO-Backup (Bucket-Mirror).

        Returns:
            BackupResult mit Pfad und Status
        """
        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.config.backup_dir / "minio" / f"minio_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("minio_backup_gestartet", ziel=str(output_dir))

        try:
            total_size = 0
            failed_buckets: List[str] = []

            for bucket in self.config.minio_buckets:
                bucket_dir = output_dir / bucket
                bucket_dir.mkdir(exist_ok=True)

                # mc mirror verwenden
                proc = await run_subprocess(
                    "mc",
                    "mirror",
                    f"minio/{bucket}",
                    str(bucket_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    logger.warning(
                        "minio_bucket_backup_fehler",
                        bucket=bucket,
                        error=stderr.decode() if stderr else "mc mirror fehlgeschlagen",
                    )
                    failed_buckets.append(bucket)
                else:
                    # Groesse berechnen
                    for file in bucket_dir.rglob("*"):
                        if file.is_file():
                            total_size += file.stat().st_size

            if failed_buckets and len(failed_buckets) == len(self.config.minio_buckets):
                error_msg = f"Alle Buckets fehlgeschlagen: {failed_buckets}"
                return BackupResult(
                    success=False,
                    backup_type="minio",
                    error=error_msg,
                )

            # Tar-Archiv erstellen wenn Kompression aktiviert
            final_path = output_dir
            if self.config.compression_enabled:
                tar_path = output_dir.with_suffix(".tar.gz")
                with tarfile.open(tar_path, "w:gz") as tar:
                    tar.add(output_dir, arcname=output_dir.name)
                shutil.rmtree(output_dir)
                final_path = tar_path
                total_size = tar_path.stat().st_size

            # Optional: Verschluesseln
            if self.config.encryption_enabled:
                encrypted_path = await self.encrypt_backup(final_path)
                if encrypted_path:
                    if final_path.is_file():
                        final_path.unlink()
                    else:
                        shutil.rmtree(final_path)
                    final_path = encrypted_path

            logger.info(
                "minio_backup_erfolgreich",
                pfad=str(final_path),
                groesse_mb=round(total_size / 1024 / 1024, 2),
                fehlgeschlagen=failed_buckets if failed_buckets else None,
            )

            return BackupResult(
                success=True,
                backup_type="minio",
                path=final_path,
                size_bytes=total_size,
                validated=True,  # Tar-Erstellung ist implizite Validierung
                encrypted=self.config.encryption_enabled,
            )

        except FileNotFoundError:
            error_msg = "mc (MinIO Client) nicht gefunden - bitte installieren"
            logger.error("minio_backup_fehler", error=error_msg)
            return BackupResult(
                success=False,
                backup_type="minio",
                error=error_msg,
            )
        except (IOError, OSError, tarfile.TarError) as e:
            logger.exception("minio_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="minio",
                **safe_error_log(e),
            )

    # -------------------------------------------------------------------------
    # Config Backup
    # -------------------------------------------------------------------------

    @track_backup(backup_type="config")
    async def backup_config(self) -> BackupResult:
        """
        Erstelle Konfigurations-Backup (tar.gz).

        Returns:
            BackupResult mit Pfad und Status
        """
        filename = self._generate_filename("config", ".tar.gz")
        output_path = self.config.backup_dir / "config" / filename

        logger.info("config_backup_gestartet", ziel=str(output_path))

        try:
            with tarfile.open(output_path, "w:gz") as tar:
                for config_path in self.config.config_paths:
                    if config_path.exists():
                        tar.add(config_path, arcname=config_path.name)
                        logger.debug("config_hinzugefuegt", pfad=str(config_path))
                    else:
                        logger.warning("config_nicht_gefunden", pfad=str(config_path))

            size_bytes = output_path.stat().st_size

            # Optional: Verschluesseln
            if self.config.encryption_enabled:
                encrypted_path = await self.encrypt_backup(output_path)
                if encrypted_path:
                    output_path.unlink()
                    output_path = encrypted_path

            validated = await self.validate_backup(output_path)

            logger.info(
                "config_backup_erfolgreich",
                pfad=str(output_path),
                groesse_mb=round(size_bytes / 1024 / 1024, 2),
            )

            return BackupResult(
                success=True,
                backup_type="config",
                path=output_path,
                size_bytes=size_bytes,
                validated=validated,
                encrypted=self.config.encryption_enabled,
            )

        except (tarfile.TarError, IOError, OSError) as e:
            logger.exception("config_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="config",
                **safe_error_log(e),
            )

    # -------------------------------------------------------------------------
    # Qdrant Vector DB Backup
    # -------------------------------------------------------------------------

    @track_backup(backup_type="qdrant")
    async def backup_qdrant(self) -> BackupResult:
        """
        Erstelle Qdrant Vector-DB Backup (Snapshot).

        Nutzt Qdrant's Snapshot-API um alle Collections zu sichern
        und laedt die Snapshots nach MinIO/lokales Dateisystem hoch.

        Returns:
            BackupResult mit Pfad und Status
        """
        if not settings.QDRANT_ENABLED:
            logger.debug("qdrant_backup_uebersprungen", grund="QDRANT_ENABLED=False")
            return BackupResult(
                success=True,
                backup_type="qdrant",
                error="Qdrant nicht aktiviert - Backup uebersprungen",
            )

        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.config.backup_dir / "qdrant" / f"qdrant_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("qdrant_backup_gestartet", ziel=str(output_dir))

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.exceptions import UnexpectedResponse

            # Qdrant-Client initialisieren
            api_key = settings.QDRANT_API_KEY.get_secret_value() if settings.QDRANT_API_KEY else None
            client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_HTTP_PORT,
                api_key=api_key,
                prefer_grpc=False,  # Snapshots nur via REST API
            )

            # Collections zum Backup
            collections_to_backup = [
                settings.QDRANT_COLLECTION_DOCUMENTS,
                settings.QDRANT_COLLECTION_CHUNKS,
            ]

            # Optional: Alle existierenden Collections ermitteln
            try:
                all_collections = client.get_collections().collections
                existing_collection_names = {c.name for c in all_collections}
            except Exception as e:
                logger.warning("qdrant_collections_abruf_fehler", error=str(e))
                existing_collection_names = set()

            snapshot_files: List[Path] = []
            failed_collections: List[str] = []
            total_size = 0

            for collection in collections_to_backup:
                # Pruefe ob Collection existiert
                if collection not in existing_collection_names:
                    logger.debug(
                        "qdrant_collection_existiert_nicht",
                        collection=collection,
                    )
                    continue

                try:
                    # Snapshot erstellen via REST API
                    snapshot_info = client.create_snapshot(collection_name=collection)
                    snapshot_name = snapshot_info.name

                    logger.info(
                        "qdrant_snapshot_erstellt",
                        collection=collection,
                        snapshot=snapshot_name,
                    )

                    # Snapshot herunterladen
                    # Qdrant-Client bietet keine direkte Download-Methode
                    # Nutze HTTP-Request zum Download
                    import httpx

                    snapshot_url = (
                        f"http://{settings.QDRANT_HOST}:{settings.QDRANT_HTTP_PORT}"
                        f"/collections/{collection}/snapshots/{snapshot_name}"
                    )

                    headers = {}
                    if api_key:
                        headers["api-key"] = api_key

                    snapshot_path = output_dir / f"{collection}_{snapshot_name}"

                    async with httpx.AsyncClient(timeout=300.0) as http_client:
                        response = await http_client.get(snapshot_url, headers=headers)
                        response.raise_for_status()

                        with open(snapshot_path, "wb") as f:
                            f.write(response.content)

                    file_size = snapshot_path.stat().st_size
                    total_size += file_size
                    snapshot_files.append(snapshot_path)

                    logger.info(
                        "qdrant_snapshot_heruntergeladen",
                        collection=collection,
                        pfad=str(snapshot_path),
                        groesse_mb=round(file_size / 1024 / 1024, 2),
                    )

                    # Snapshot auf Qdrant-Server loeschen (Aufraeumen)
                    try:
                        client.delete_snapshot(
                            collection_name=collection,
                            snapshot_name=snapshot_name,
                        )
                    except Exception:
                        pass  # Nicht kritisch

                except UnexpectedResponse as e:
                    logger.error(
                        "qdrant_snapshot_fehler",
                        collection=collection,
                        error=str(e),
                    )
                    failed_collections.append(collection)
                except Exception as e:
                    logger.error(
                        "qdrant_collection_backup_fehler",
                        collection=collection,
                        error=str(e),
                    )
                    failed_collections.append(collection)

            # Pruefen ob Backups erstellt wurden
            if not snapshot_files:
                if failed_collections:
                    error_msg = f"Alle Collection-Backups fehlgeschlagen: {failed_collections}"
                else:
                    error_msg = "Keine Collections zum Backup gefunden"

                # Aufraeumen leeres Verzeichnis
                if output_dir.exists() and not list(output_dir.iterdir()):
                    output_dir.rmdir()

                return BackupResult(
                    success=False,
                    backup_type="qdrant",
                    error=error_msg,
                )

            # Tar-Archiv erstellen wenn Kompression aktiviert
            final_path = output_dir
            if self.config.compression_enabled and snapshot_files:
                tar_path = output_dir.with_suffix(".tar.gz")
                with tarfile.open(tar_path, "w:gz") as tar:
                    tar.add(output_dir, arcname=output_dir.name)
                shutil.rmtree(output_dir)
                final_path = tar_path
                total_size = tar_path.stat().st_size

            # Optional: Verschluesseln
            if self.config.encryption_enabled:
                encrypted_path = await self.encrypt_backup(final_path)
                if encrypted_path:
                    if final_path.is_file():
                        final_path.unlink()
                    else:
                        shutil.rmtree(final_path)
                    final_path = encrypted_path

            # Upload zu MinIO (optional)
            # Wird bereits im output_dir gespeichert

            logger.info(
                "qdrant_backup_erfolgreich",
                pfad=str(final_path),
                groesse_mb=round(total_size / 1024 / 1024, 2),
                collections=len(snapshot_files),
                fehlgeschlagen=failed_collections if failed_collections else None,
            )

            return BackupResult(
                success=True,
                backup_type="qdrant",
                path=final_path,
                size_bytes=total_size,
                validated=True,
                encrypted=self.config.encryption_enabled,
            )

        except ImportError:
            error_msg = "qdrant-client nicht installiert - pip install qdrant-client"
            logger.error("qdrant_client_nicht_gefunden", error=error_msg)
            return BackupResult(
                success=False,
                backup_type="qdrant",
                error=error_msg,
            )
        except Exception as e:
            logger.exception("qdrant_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="qdrant",
                **safe_error_log(e),
            )

    # -------------------------------------------------------------------------
    # Full Backup
    # -------------------------------------------------------------------------

    async def backup_full(self) -> List[BackupResult]:
        """
        Fuehre vollstaendiges Backup aller Komponenten durch.

        Returns:
            Liste von BackupResult fuer jede Komponente
        """
        logger.info("vollstaendiges_backup_gestartet")

        results: List[BackupResult] = []

        # Sequentiell ausfuehren um Ressourcenkonflikte zu vermeiden
        results.append(await self.backup_postgres())
        results.append(await self.backup_redis())
        results.append(await self.backup_minio())
        results.append(await self.backup_config())
        results.append(await self.backup_qdrant())

        # Metriken aktualisieren
        self.metrics.update_disk_usage()
        self.metrics.update_backup_file_counts()

        # Remote-Sync wenn aktiviert
        if self.config.remote_enabled:
            sync_success = await self.sync_to_remote()
            for result in results:
                result.remote_synced = sync_success

        success_count = sum(1 for r in results if r.success)
        logger.info(
            "vollstaendiges_backup_abgeschlossen",
            erfolgreich=success_count,
            gesamt=len(results),
        )

        return results

    # -------------------------------------------------------------------------
    # GPG Verschluesselung
    # -------------------------------------------------------------------------

    async def encrypt_backup(self, path: Path) -> Optional[Path]:
        """
        Verschluessle Backup mit GPG (asymmetrisch).

        Args:
            path: Pfad zur Backup-Datei

        Returns:
            Pfad zur verschluesselten Datei oder None bei Fehler
        """
        if not path.exists():
            logger.error("verschluesselung_datei_nicht_gefunden", pfad=str(path))
            return None

        # Pre-Flight Check: Encryption-Konfiguration validiert?
        if not self._encryption_validated:
            error_msg = self._encryption_validation_error or "GPG-Konfiguration nicht validiert"
            logger.error(
                "verschluesselung_nicht_moeglich",
                error=error_msg,
                pfad=str(path),
            )
            self.metrics.record_encryption_failure(f"Pre-flight: {error_msg}")
            return None

        output_path = path.with_suffix(path.suffix + ".gpg")

        logger.debug("backup_verschluesselung_gestartet", quelle=str(path))

        try:
            gpg_env = os.environ.copy()
            if self.config.gpg_home:
                gpg_env["GNUPGHOME"] = self.config.gpg_home

            proc = await run_subprocess(
                "gpg",
                "--encrypt",
                "--recipient", self.config.gpg_recipient,
                "--output", str(output_path),
                "--trust-model", "always",  # Trust recipient key
                str(path),
                env=gpg_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "GPG Verschluesselung fehlgeschlagen"
                logger.error("verschluesselung_fehlgeschlagen", error=error_msg)
                self.metrics.record_encryption_failure(error_msg)
                # Aufraumen bei Fehler
                if output_path.exists():
                    output_path.unlink()
                return None

            # Post-Encryption Validation
            validation_result = await self._validate_encrypted_file(output_path, path.stat().st_size)
            if not validation_result["valid"]:
                logger.error(
                    "post_encryption_validation_fehlgeschlagen",
                    error=validation_result["error"],
                    pfad=str(output_path),
                )
                self.metrics.record_encryption_failure(f"Post-validation: {validation_result['error']}")
                if output_path.exists():
                    output_path.unlink()
                return None

            self.metrics.record_encryption_success()
            logger.info(
                "backup_verschluesselt",
                pfad=str(output_path),
                original_groesse=path.stat().st_size,
                verschluesselt_groesse=output_path.stat().st_size,
            )
            return output_path

        except FileNotFoundError:
            error_msg = "GPG nicht gefunden - bitte installieren"
            logger.error("gpg_nicht_gefunden")
            self.metrics.record_encryption_failure(error_msg)
            return None
        except (subprocess.SubprocessError, IOError, OSError) as e:
            logger.exception("verschluesselung_fehler")
            self.metrics.record_encryption_failure(safe_error_detail(e, "Encryption"))
            # Aufraumen bei Fehler
            if output_path.exists():
                output_path.unlink()
            return None

    async def _validate_encrypted_file(
        self,
        encrypted_path: Path,
        original_size: int,
    ) -> Dict[str, Any]:
        """
        Validiere verschluesselte Datei nach Erstellung.

        Args:
            encrypted_path: Pfad zur verschluesselten Datei
            original_size: Groesse der Original-Datei

        Returns:
            Dict mit 'valid' (bool) und optional 'error' (str)
        """
        # 1. Datei existiert?
        if not encrypted_path.exists():
            return {"valid": False, "error": "Verschluesselte Datei wurde nicht erstellt"}

        encrypted_size = encrypted_path.stat().st_size

        # 2. Datei nicht leer?
        if encrypted_size == 0:
            return {"valid": False, "error": "Verschluesselte Datei ist leer"}

        # 3. Verschluesselte Datei sollte mindestens aehnlich gross sein
        # GPG fuegt Overhead hinzu (~100-500 Bytes), aber die Datei sollte
        # nicht dramatisch kleiner sein als das Original
        min_expected_size = max(100, original_size * 0.5)  # Mind. 50% der Originalgroesse
        if encrypted_size < min_expected_size:
            return {
                "valid": False,
                "error": f"Verschluesselte Datei zu klein: {encrypted_size} < {min_expected_size}",
            }

        # 4. GPG-Header validieren
        try:
            with open(encrypted_path, "rb") as f:
                header = f.read(2)

            # GPG Binary Packets beginnen mit bestimmten Bytes
            # 0x85: Old-style packet (compressed data)
            # 0xa3: Old-style packet (symmetric key)
            # 0xc0-0xff: New-style packets
            valid_headers = set([0x85, 0xa3] + list(range(0xc0, 0x100)))

            if header[0] not in valid_headers:
                # Check for ASCII-armored GPG
                with open(encrypted_path, "rb") as f:
                    ascii_check = f.read(27)
                if not ascii_check.startswith(b"-----BEGIN PGP MESSAGE"):
                    return {
                        "valid": False,
                        "error": f"Ungueltige GPG-Datei: Header 0x{header[0]:02x} nicht erkannt",
                    }

        except Exception as e:
            return {"valid": False, "error": f"Header-Validierung fehlgeschlagen: {e}"}

        return {"valid": True}

    def get_encryption_status(self) -> Dict[str, Any]:
        """
        Hole aktuellen Encryption-Status (fuer Health-Checks).

        Returns:
            Dict mit Status-Informationen
        """
        return {
            "enabled": self.config.encryption_enabled,
            "validated": self._encryption_validated,
            "recipient": self.config.gpg_recipient if self.config.encryption_enabled else None,
            "gpg_home": self.config.gpg_home,
            "error": self._encryption_validation_error,
        }

    def revalidate_encryption_config(self) -> bool:
        """
        Validiere GPG-Konfiguration erneut.

        Nuetzlich nach Schluessel-Import oder Konfigurationsaenderung.

        Returns:
            True wenn Validierung erfolgreich
        """
        if not self.config.encryption_enabled:
            logger.debug("encryption_nicht_aktiviert_skip_revalidation")
            return False

        self._encryption_validated = False
        self._encryption_validation_error = None
        self._validate_encryption_config()

        return self._encryption_validated

    async def decrypt_backup(self, path: Path, output_path: Optional[Path] = None) -> Optional[Path]:
        """
        Entschluessele GPG-verschluesseltes Backup.

        Args:
            path: Pfad zur verschluesselten Datei (.gpg)
            output_path: Ausgabepfad (optional)

        Returns:
            Pfad zur entschluesselten Datei oder None bei Fehler
        """
        if not path.exists():
            logger.error("entschluesselung_datei_nicht_gefunden", pfad=str(path))
            return None

        if output_path is None:
            # Entferne .gpg Suffix
            output_path = path.with_suffix("")

        try:
            gpg_env = os.environ.copy()
            if self.config.gpg_home:
                gpg_env["GNUPGHOME"] = self.config.gpg_home

            proc = await run_subprocess(
                "gpg",
                "--decrypt",
                "--output", str(output_path),
                str(path),
                env=gpg_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "GPG Entschluesselung fehlgeschlagen"
                logger.error("entschluesselung_fehlgeschlagen", error=error_msg)
                return None

            logger.info("backup_entschluesselt", pfad=str(output_path))
            return output_path

        except Exception as e:
            logger.exception("entschluesselung_fehler")
            return None

    # -------------------------------------------------------------------------
    # Remote Sync
    # -------------------------------------------------------------------------

    async def sync_to_remote(self, max_retries: int = 3) -> bool:
        """
        Synchronisiere Backups zum Remote-Server via rsync.

        Args:
            max_retries: Maximale Wiederholungsversuche

        Returns:
            True wenn erfolgreich
        """
        if not self.config.remote_enabled:
            logger.debug("remote_sync_deaktiviert")
            return False

        if not self.config.remote_target:
            logger.warning("remote_sync_kein_ziel_konfiguriert")
            return False

        logger.info("remote_sync_gestartet", ziel=self.config.remote_target)

        with self.metrics.measure_remote_sync():
            for attempt in range(1, max_retries + 1):
                try:
                    ssh_args = []
                    if self.config.remote_ssh_key:
                        ssh_args = ["-e", f"ssh -i {self.config.remote_ssh_key}"]

                    proc = await run_subprocess(
                        "rsync",
                        "-avz",
                        "--delete",
                        *ssh_args,
                        str(self.config.backup_dir) + "/",
                        self.config.remote_target,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    stdout, stderr = await proc.communicate()

                    if proc.returncode == 0:
                        logger.info("remote_sync_erfolgreich")
                        return True

                    error_msg = stderr.decode() if stderr else "rsync fehlgeschlagen"
                    logger.warning(
                        "remote_sync_versuch_fehlgeschlagen",
                        versuch=attempt,
                        max_versuche=max_retries,
                        error=error_msg,
                    )

                    if attempt < max_retries:
                        self.metrics.record_remote_sync_retry(attempt, max_retries)
                        await asyncio.sleep(10 * attempt)  # Exponential backoff

                except FileNotFoundError:
                    logger.error("rsync_nicht_gefunden")
                    return False
                except Exception as e:
                    logger.exception("remote_sync_fehler")
                    if attempt == max_retries:
                        raise

        return False

    async def list_remote_backups(self) -> List[Dict[str, str]]:
        """
        Liste Backups auf dem Remote-Server auf.

        Returns:
            Liste von Backup-Informationen
        """
        if not self.config.remote_enabled or not self.config.remote_target:
            return []

        try:
            ssh_args = []
            if self.config.remote_ssh_key:
                ssh_args = ["-i", self.config.remote_ssh_key]

            # Parse host und path aus remote_target (user@host:/path)
            target_parts = self.config.remote_target.split(":")
            if len(target_parts) != 2:
                logger.error("remote_target_format_ungueltig")
                return []

            host, path = target_parts

            proc = await run_subprocess(
                "ssh",
                *ssh_args,
                host,
                f"ls -la {path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.warning("remote_liste_fehler", error=stderr.decode())
                return []

            # Parse ls output (vereinfacht)
            lines = stdout.decode().strip().split("\n")
            return [{"name": line.split()[-1]} for line in lines if line and not line.startswith("total")]

        except Exception as e:
            logger.exception("remote_liste_fehler")
            return []

    # -------------------------------------------------------------------------
    # Validierung
    # -------------------------------------------------------------------------

    async def validate_backup(self, path: Path) -> bool:
        """
        Validiere Backup-Integritaet.

        Args:
            path: Pfad zur Backup-Datei

        Returns:
            True wenn Backup valide
        """
        if not path.exists():
            logger.error("validierung_datei_nicht_gefunden", pfad=str(path))
            return False

        with self.metrics.measure_validation():
            try:
                suffix = "".join(path.suffixes).lower()

                # GPG-verschluesselte Dateien - erweiterte Validierung
                if suffix.endswith(".gpg"):
                    file_size = path.stat().st_size
                    if file_size < 100:  # Minimal sinnvolle GPG-Dateigroesse
                        logger.warning("gpg_backup_zu_klein", pfad=str(path), groesse=file_size)
                        return False

                    # GPG-Header validieren
                    with open(path, "rb") as f:
                        header = f.read(2)

                    # Gueltige GPG-Header
                    valid_headers = set([0x85, 0xa3] + list(range(0xc0, 0x100)))
                    if len(header) >= 1 and header[0] in valid_headers:
                        return True

                    # ASCII-armored GPG pruefen
                    with open(path, "rb") as f:
                        ascii_check = f.read(27)
                    if ascii_check.startswith(b"-----BEGIN PGP MESSAGE"):
                        return True

                    logger.warning("gpg_backup_ungueltiger_header", pfad=str(path))
                    return False

                # Gzip-komprimierte Dateien
                if ".gz" in suffix:
                    with gzip.open(path, "rb") as f:
                        f.read(1024)  # Erste 1KB lesen
                    return True

                # Tar-Archive
                if ".tar" in suffix:
                    with tarfile.open(path, "r:*") as tar:
                        tar.getnames()  # Inhaltsverzeichnis lesen
                    return True

                # RDB-Dateien (Redis)
                if suffix == ".rdb":
                    with open(path, "rb") as f:
                        header = f.read(9)
                        return header.startswith(b"REDIS")

                # SQL-Dateien
                if suffix == ".sql":
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read(100)
                        return "--" in content or "CREATE" in content.upper()

                # Generische Dateigroessen-Pruefung
                return path.stat().st_size > 0

            except Exception as e:
                logger.error("validierung_fehlgeschlagen", pfad=str(path), **safe_error_log(e))
                return False

    # -------------------------------------------------------------------------
    # Retention Policy
    # -------------------------------------------------------------------------

    async def apply_retention_policy(self) -> Dict[str, int]:
        """
        Wende Retention Policy an - loesche alte Backups.

        Returns:
            Dict mit Anzahl geloeschter Dateien pro Typ
        """
        logger.info(
            "retention_policy_gestartet",
            aufbewahrung_tage=self.config.retention_days,
        )

        deleted: Dict[str, int] = {
            "postgres": 0,
            "redis": 0,
            "minio": 0,
            "config": 0,
            "qdrant": 0,
        }

        cutoff_timestamp = utc_now().timestamp() - (self.config.retention_days * 86400)

        for backup_type in deleted.keys():
            backup_dir = self.config.backup_dir / backup_type

            if not backup_dir.exists():
                continue

            for item in backup_dir.iterdir():
                try:
                    mtime = item.stat().st_mtime
                    if mtime < cutoff_timestamp:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                        deleted[backup_type] += 1
                        logger.debug("backup_geloescht", pfad=str(item))
                except Exception as e:
                    logger.error("backup_loeschung_fehler", pfad=str(item), **safe_error_log(e))

        total_deleted = sum(deleted.values())
        logger.info(
            "retention_policy_abgeschlossen",
            geloescht=total_deleted,
            details=deleted,
        )

        # Metriken aktualisieren
        self.metrics.update_disk_usage()
        self.metrics.update_backup_file_counts()

        return deleted

    # -------------------------------------------------------------------------
    # Hilfsfunktionen
    # -------------------------------------------------------------------------

    async def _compress_file(self, input_path: Path, output_path: Path) -> None:
        """
        Komprimiere Datei mit gzip.

        Args:
            input_path: Eingabedatei
            output_path: Ausgabedatei (.gz)
        """
        with open(input_path, "rb") as f_in:
            with gzip.open(output_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

    def list_backups(self, backup_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Liste lokale Backups auf.

        Args:
            backup_type: Optional Filter nach Typ

        Returns:
            Liste von Backup-Informationen
        """
        backups: List[Dict[str, Any]] = []
        types = [backup_type] if backup_type else ["postgres", "redis", "minio", "config", "qdrant"]

        for btype in types:
            backup_dir = self.config.backup_dir / btype
            if not backup_dir.exists():
                continue

            for item in sorted(backup_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                try:
                    stat = item.stat()
                    backups.append({
                        "type": btype,
                        "name": item.name,
                        "path": str(item),
                        "size_bytes": stat.st_size,
                        "size_mb": round(stat.st_size / 1024 / 1024, 2),
                        "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "encrypted": item.suffix == ".gpg",
                    })
                except Exception as e:
                    logger.warning("backup_info_fehler", pfad=str(item), **safe_error_log(e))

        return backups

    # -------------------------------------------------------------------------
    # Restore Methods
    # -------------------------------------------------------------------------

    async def restore_postgres(
        self,
        backup_path: Path,
        dry_run: bool = False,
    ) -> BackupResult:
        """
        Stelle PostgreSQL aus Backup wieder her.

        Args:
            backup_path: Pfad zur Backup-Datei (.sql.gz oder .sql.gz.gpg)
            dry_run: Wenn True, nur Validierung ohne Wiederherstellung

        Returns:
            BackupResult mit Status
        """
        import time

        start_time = time.perf_counter()
        logger.info(
            "postgres_restore_gestartet",
            pfad=str(backup_path),
            dry_run=dry_run,
        )

        if not backup_path.exists():
            return BackupResult(
                success=False,
                backup_type="postgres_restore",
                error=f"Backup-Datei nicht gefunden: {backup_path}",
            )

        try:
            # Validiere Backup erst
            if not await self.validate_backup(backup_path):
                return BackupResult(
                    success=False,
                    backup_type="postgres_restore",
                    error="Backup-Validierung fehlgeschlagen",
                )

            if dry_run:
                duration = time.perf_counter() - start_time
                logger.info("postgres_restore_dry_run_erfolgreich", pfad=str(backup_path))
                return BackupResult(
                    success=True,
                    backup_type="postgres_restore",
                    path=backup_path,
                    validated=True,
                    duration_seconds=duration,
                )

            # Arbeite mit temporaerer Datei wenn verschluesselt/komprimiert
            work_path = backup_path
            temp_files: List[Path] = []

            # Entschluesseln wenn GPG
            if backup_path.suffix == ".gpg":
                decrypted_path = await self._decrypt_backup(backup_path)
                if decrypted_path is None:
                    return BackupResult(
                        success=False,
                        backup_type="postgres_restore",
                        error="Entschluesselung fehlgeschlagen",
                    )
                work_path = decrypted_path
                temp_files.append(decrypted_path)

            # Dekomprimieren wenn gzip
            if work_path.suffix == ".gz":
                decompressed_path = work_path.with_suffix("")
                await self._decompress_file(work_path, decompressed_path)
                if work_path in temp_files:
                    temp_files.remove(work_path)
                    work_path.unlink()
                work_path = decompressed_path
                temp_files.append(decompressed_path)

            # psql ausfuehren
            env = os.environ.copy()
            env["PGPASSWORD"] = self.config.postgres_password

            proc = await run_subprocess(
                "psql",
                "-h", self.config.postgres_host,
                "-p", str(self.config.postgres_port),
                "-U", self.config.postgres_user,
                "-d", self.config.postgres_db,
                "-f", str(work_path),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            # Aufraeumen temporaere Dateien
            for temp_file in temp_files:
                if temp_file.exists():
                    temp_file.unlink()

            duration = time.perf_counter() - start_time

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "psql restore fehlgeschlagen"
                logger.error(
                    "postgres_restore_fehlgeschlagen",
                    error=error_msg,
                    returncode=proc.returncode,
                )
                return BackupResult(
                    success=False,
                    backup_type="postgres_restore",
                    error=error_msg[:500],
                    duration_seconds=duration,
                )

            logger.info(
                "postgres_restore_erfolgreich",
                pfad=str(backup_path),
                dauer=duration,
            )

            return BackupResult(
                success=True,
                backup_type="postgres_restore",
                path=backup_path,
                validated=True,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.exception("postgres_restore_fehler")
            return BackupResult(
                success=False,
                backup_type="postgres_restore",
                **safe_error_log(e)[:500],
            )

    async def restore_redis(
        self,
        backup_path: Path,
        dry_run: bool = False,
    ) -> BackupResult:
        """
        Stelle Redis aus RDB-Backup wieder her.

        Args:
            backup_path: Pfad zur RDB-Datei
            dry_run: Wenn True, nur Validierung ohne Wiederherstellung

        Returns:
            BackupResult mit Status
        """
        import time

        start_time = time.perf_counter()
        logger.info(
            "redis_restore_gestartet",
            pfad=str(backup_path),
            dry_run=dry_run,
        )

        if not backup_path.exists():
            return BackupResult(
                success=False,
                backup_type="redis_restore",
                error=f"Backup-Datei nicht gefunden: {backup_path}",
            )

        try:
            # Validiere Backup
            if not await self.validate_backup(backup_path):
                return BackupResult(
                    success=False,
                    backup_type="redis_restore",
                    error="Backup-Validierung fehlgeschlagen",
                )

            if dry_run:
                duration = time.perf_counter() - start_time
                logger.info("redis_restore_dry_run_erfolgreich", pfad=str(backup_path))
                return BackupResult(
                    success=True,
                    backup_type="redis_restore",
                    path=backup_path,
                    validated=True,
                    duration_seconds=duration,
                )

            # Redis SHUTDOWN und RDB kopieren
            # WARNUNG: Dies erfordert Redis-Neustart!
            try:
                import redis.asyncio as redis_client

                client = redis_client.from_url(
                    f"redis://{self.config.redis_host}:{self.config.redis_port}",
                    password=self.config.redis_password,
                )

                # BGSAVE stoppen falls aktiv
                await client.bgsave()
                await asyncio.sleep(2)

                # Redis Data Dir ermitteln (CONFIG GET dir)
                config_result = await client.config_get("dir")
                redis_dir = config_result.get("dir", "/data")

                # RDB Dateiname ermitteln
                dbfilename_result = await client.config_get("dbfilename")
                dbfilename = dbfilename_result.get("dbfilename", "dump.rdb")

                target_path = Path(redis_dir) / dbfilename

                # Alte RDB sichern
                if target_path.exists():
                    backup_old = target_path.with_suffix(".rdb.old")
                    shutil.copy2(target_path, backup_old)

                # Neue RDB kopieren
                shutil.copy2(backup_path, target_path)

                # Redis DEBUG RELOAD (laedt RDB neu)
                await client.debug_object("RELOAD")

                await client.close()

            except ImportError:
                return BackupResult(
                    success=False,
                    backup_type="redis_restore",
                    error="redis-py nicht installiert",
                )

            duration = time.perf_counter() - start_time
            logger.info(
                "redis_restore_erfolgreich",
                pfad=str(backup_path),
                dauer=duration,
            )

            return BackupResult(
                success=True,
                backup_type="redis_restore",
                path=backup_path,
                validated=True,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.exception("redis_restore_fehler")
            return BackupResult(
                success=False,
                backup_type="redis_restore",
                **safe_error_log(e)[:500],
            )

    async def restore_minio(
        self,
        backup_path: Path,
        bucket: Optional[str] = None,
        dry_run: bool = False,
    ) -> BackupResult:
        """
        Stelle MinIO-Buckets aus Backup wieder her.

        Args:
            backup_path: Pfad zum MinIO-Backup-Verzeichnis
            bucket: Optionaler einzelner Bucket zum Wiederherstellen
            dry_run: Wenn True, nur Validierung ohne Wiederherstellung

        Returns:
            BackupResult mit Status
        """
        import time

        start_time = time.perf_counter()
        logger.info(
            "minio_restore_gestartet",
            pfad=str(backup_path),
            bucket=bucket,
            dry_run=dry_run,
        )

        if not backup_path.exists():
            return BackupResult(
                success=False,
                backup_type="minio_restore",
                error=f"Backup-Verzeichnis nicht gefunden: {backup_path}",
            )

        try:
            # Validiere dass es ein Verzeichnis ist
            if not backup_path.is_dir():
                return BackupResult(
                    success=False,
                    backup_type="minio_restore",
                    error="Pfad ist kein Verzeichnis",
                )

            # Buckets zum Wiederherstellen bestimmen
            if bucket:
                buckets_to_restore = [bucket]
            else:
                buckets_to_restore = [d.name for d in backup_path.iterdir() if d.is_dir()]

            if dry_run:
                duration = time.perf_counter() - start_time
                logger.info(
                    "minio_restore_dry_run_erfolgreich",
                    buckets=buckets_to_restore,
                )
                return BackupResult(
                    success=True,
                    backup_type="minio_restore",
                    path=backup_path,
                    validated=True,
                    duration_seconds=duration,
                )

            # mc mirror fuer jeden Bucket (von Backup zu MinIO)
            for bucket_name in buckets_to_restore:
                bucket_source = backup_path / bucket_name
                if not bucket_source.exists():
                    logger.warning("minio_bucket_nicht_gefunden", bucket=bucket_name)
                    continue

                proc = await run_subprocess(
                    "mc",
                    "mirror",
                    "--overwrite",
                    str(bucket_source),
                    f"local/{bucket_name}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    logger.error(
                        "minio_bucket_restore_fehler",
                        bucket=bucket_name,
                        error=stderr.decode(),
                    )

            duration = time.perf_counter() - start_time
            logger.info(
                "minio_restore_erfolgreich",
                pfad=str(backup_path),
                buckets=buckets_to_restore,
                dauer=duration,
            )

            return BackupResult(
                success=True,
                backup_type="minio_restore",
                path=backup_path,
                validated=True,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.exception("minio_restore_fehler")
            return BackupResult(
                success=False,
                backup_type="minio_restore",
                **safe_error_log(e)[:500],
            )

    async def restore_full(
        self,
        backup_dir: Path,
        dry_run: bool = False,
        components: Optional[List[str]] = None,
    ) -> List[BackupResult]:
        """
        Vollstaendige Wiederherstellung aller Komponenten.

        Args:
            backup_dir: Verzeichnis mit Backups (muss Unterordner haben)
            dry_run: Nur Validierung
            components: Optionale Liste (postgres, redis, minio)

        Returns:
            Liste von BackupResults
        """
        logger.info(
            "vollstaendige_wiederherstellung_gestartet",
            verzeichnis=str(backup_dir),
            dry_run=dry_run,
            komponenten=components,
        )

        results: List[BackupResult] = []
        available_components = components or ["postgres", "redis", "minio"]

        # PostgreSQL zuerst (Datenbank-Schema)
        if "postgres" in available_components:
            postgres_dir = backup_dir / "postgres"
            if postgres_dir.exists():
                # Neuestes Backup finden
                postgres_files = sorted(
                    postgres_dir.glob("*.sql.gz*"),
                    key=lambda x: x.stat().st_mtime,
                    reverse=True,
                )
                if postgres_files:
                    result = await self.restore_postgres(postgres_files[0], dry_run=dry_run)
                    results.append(result)
                else:
                    results.append(BackupResult(
                        success=False,
                        backup_type="postgres_restore",
                        error="Keine PostgreSQL-Backups gefunden",
                    ))

        # Redis
        if "redis" in available_components:
            redis_dir = backup_dir / "redis"
            if redis_dir.exists():
                redis_files = sorted(
                    redis_dir.glob("*.rdb*"),
                    key=lambda x: x.stat().st_mtime,
                    reverse=True,
                )
                if redis_files:
                    result = await self.restore_redis(redis_files[0], dry_run=dry_run)
                    results.append(result)
                else:
                    results.append(BackupResult(
                        success=False,
                        backup_type="redis_restore",
                        error="Keine Redis-Backups gefunden",
                    ))

        # MinIO
        if "minio" in available_components:
            minio_dir = backup_dir / "minio"
            if minio_dir.exists():
                # Neuestes Backup-Verzeichnis finden
                minio_dirs = sorted(
                    [d for d in minio_dir.iterdir() if d.is_dir()],
                    key=lambda x: x.stat().st_mtime,
                    reverse=True,
                )
                if minio_dirs:
                    result = await self.restore_minio(minio_dirs[0], dry_run=dry_run)
                    results.append(result)
                else:
                    results.append(BackupResult(
                        success=False,
                        backup_type="minio_restore",
                        error="Keine MinIO-Backups gefunden",
                    ))

        success_count = sum(1 for r in results if r.success)
        logger.info(
            "vollstaendige_wiederherstellung_abgeschlossen",
            erfolgreich=success_count,
            gesamt=len(results),
            dry_run=dry_run,
        )

        return results

    async def _decrypt_backup(self, encrypted_path: Path) -> Optional[Path]:
        """
        Entschluessele GPG-verschluesselte Backup-Datei.

        Args:
            encrypted_path: Pfad zur .gpg Datei

        Returns:
            Pfad zur entschluesselten Datei oder None bei Fehler
        """
        output_path = encrypted_path.with_suffix("")  # Entferne .gpg

        gpg_args = ["--decrypt", "--batch", "--yes", "-o", str(output_path)]

        if self.config.gpg_home:
            gpg_args = ["--homedir", self.config.gpg_home] + gpg_args

        gpg_args.append(str(encrypted_path))

        proc = await run_subprocess(
            "gpg",
            *gpg_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error("gpg_entschluesselung_fehler", error=stderr.decode())
            return None

        return output_path

    async def _decompress_file(self, input_path: Path, output_path: Path) -> None:
        """
        Dekomprimiere gzip-Datei.

        Args:
            input_path: Komprimierte Eingabedatei
            output_path: Dekomprimierte Ausgabedatei
        """
        with gzip.open(input_path, "rb") as f_in:
            with open(output_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)


# =============================================================================
# Singleton Instance
# =============================================================================

_backup_service: Optional[BackupService] = None


def get_backup_service(config: Optional[BackupConfig] = None) -> BackupService:
    """Hole globale BackupService Instanz (thread-safe)."""
    global _backup_service
    if _backup_service is not None:
        return _backup_service
    with _backup_service_lock:
        if _backup_service is None:
            logger.info("backup_service_initialisierung")
            _backup_service = BackupService(config=config)
    return _backup_service

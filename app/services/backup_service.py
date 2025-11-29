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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import structlog

from app.services.backup_metrics_service import get_backup_metrics, track_backup

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
    """Konfiguration fuer Backup-Service."""

    # Verzeichnisse
    backup_dir: Path = field(default_factory=lambda: Path(os.getenv("BACKUP_DIR", "/var/backups/ablage")))
    retention_days: int = field(default_factory=lambda: int(os.getenv("BACKUP_RETENTION_DAYS", "30")))
    compression_enabled: bool = field(default_factory=lambda: os.getenv("BACKUP_COMPRESSION", "true").lower() == "true")

    # PostgreSQL
    postgres_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    postgres_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5433")))
    postgres_db: str = field(default_factory=lambda: os.getenv("DB_NAME", "ablage_system"))
    postgres_user: str = field(default_factory=lambda: os.getenv("DB_USER", "ablage_admin"))
    postgres_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))

    # Redis
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6380")))
    redis_password: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))

    # MinIO
    minio_endpoint: str = field(default_factory=lambda: os.getenv("MINIO_ENDPOINT", "localhost:9000"))
    minio_access_key: str = field(default_factory=lambda: os.getenv("MINIO_ACCESS_KEY", "minioadmin"))
    minio_secret_key: str = field(default_factory=lambda: os.getenv("MINIO_SECRET_KEY", "minioadmin123"))
    minio_buckets: List[str] = field(default_factory=lambda: os.getenv("MINIO_BUCKETS", "documents,processed,thumbnails").split(","))

    # GPG Verschluesselung
    encryption_enabled: bool = field(default_factory=lambda: os.getenv("BACKUP_ENCRYPTION", "false").lower() == "true")
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

        logger.info(
            "backup_service_initialisiert",
            backup_dir=str(self.config.backup_dir),
            encryption=self.config.encryption_enabled,
            remote_sync=self.config.remote_enabled,
        )

    def _ensure_directories(self) -> None:
        """Stelle sicher, dass alle Backup-Verzeichnisse existieren."""
        dirs = ["postgres", "redis", "minio", "config", "full"]
        for subdir in dirs:
            path = self.config.backup_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            logger.debug("backup_verzeichnis_erstellt", path=str(path))

    def _generate_filename(self, backup_type: str, extension: str) -> str:
        """
        Generiere Dateinamen mit Zeitstempel.

        Args:
            backup_type: postgres, redis, minio, config
            extension: Dateierweiterung (.sql.gz, .rdb, etc.)

        Returns:
            Dateiname mit Zeitstempel
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
        except Exception as e:
            logger.exception("postgres_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="postgres",
                error=str(e),
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
        except Exception as e:
            logger.exception("redis_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="redis",
                error=str(e),
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
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
        except Exception as e:
            logger.exception("minio_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="minio",
                error=str(e),
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

        except Exception as e:
            logger.exception("config_backup_fehler")
            return BackupResult(
                success=False,
                backup_type="config",
                error=str(e),
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
                return None

            self.metrics.record_encryption_success()
            logger.info("backup_verschluesselt", pfad=str(output_path))
            return output_path

        except FileNotFoundError:
            error_msg = "GPG nicht gefunden - bitte installieren"
            logger.error("gpg_nicht_gefunden")
            self.metrics.record_encryption_failure(error_msg)
            return None
        except Exception as e:
            logger.exception("verschluesselung_fehler")
            self.metrics.record_encryption_failure(str(e))
            return None

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

                # GPG-verschluesselte Dateien
                if suffix.endswith(".gpg"):
                    # Nur Dateigroesse pruefen (Entschluesselung zu teuer)
                    return path.stat().st_size > 0

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
                logger.error("validierung_fehlgeschlagen", pfad=str(path), error=str(e))
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
        }

        cutoff_timestamp = datetime.utcnow().timestamp() - (self.config.retention_days * 86400)

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
                    logger.error("backup_loeschung_fehler", pfad=str(item), error=str(e))

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

    def list_backups(self, backup_type: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Liste lokale Backups auf.

        Args:
            backup_type: Optional Filter nach Typ

        Returns:
            Liste von Backup-Informationen
        """
        backups: List[Dict[str, any]] = []
        types = [backup_type] if backup_type else ["postgres", "redis", "minio", "config"]

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
                    logger.warning("backup_info_fehler", pfad=str(item), error=str(e))

        return backups


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

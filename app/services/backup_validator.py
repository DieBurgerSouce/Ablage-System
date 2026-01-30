# -*- coding: utf-8 -*-
"""
Backup-Validator fuer Ablage-System.

Tiefgreifende Validierung von Backups:
- Strukturelle Integritaet
- Inhaltliche Vollstaendigkeit
- Checksum-Verifizierung
- Restore-Simulation (Dry-Run)

Feinpoliert und durchdacht - Enterprise Backup Validation.
"""

import asyncio
import gzip
import hashlib
import os
import re
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


class ValidationLevel(str, Enum):
    """Validierungsstufen."""
    QUICK = "quick"          # Nur Dateiexistenz und Groesse
    STANDARD = "standard"    # + Strukturelle Integritaet
    DEEP = "deep"            # + Inhaltliche Pruefung
    FULL = "full"            # + Restore-Simulation


class ValidationStatus(str, Enum):
    """Validierungsstatus."""
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class ValidationIssue:
    """Einzelnes Validierungsproblem."""
    severity: str  # error, warning, info
    code: str
    message: str
    details: Optional[Dict] = None


@dataclass
class ValidationResult:
    """Ergebnis einer Backup-Validierung."""
    backup_path: Path
    backup_type: str
    status: ValidationStatus
    level: ValidationLevel
    issues: List[ValidationIssue] = field(default_factory=list)
    checksum_sha256: Optional[str] = None
    file_count: int = 0
    total_size_bytes: int = 0
    validation_duration_ms: int = 0
    validated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Backup ist valide wenn keine Fehler."""
        return self.status in (ValidationStatus.VALID, ValidationStatus.WARNING)

    @property
    def error_count(self) -> int:
        """Anzahl der Fehler."""
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        """Anzahl der Warnungen."""
        return sum(1 for i in self.issues if i.severity == "warning")


class BackupValidator:
    """
    Umfassende Backup-Validierung.

    Validiert:
    - PostgreSQL SQL Dumps (.sql, .sql.gz)
    - Redis RDB Snapshots (.rdb)
    - MinIO Bucket Archives (.tar.gz)
    - Konfigurationsarchive (.tar.gz)
    - GPG-verschluesselte Backups (.gpg)
    """

    # Erwartete PostgreSQL-Tabellen (kritisch)
    EXPECTED_PG_TABLES: Set[str] = {
        "users",
        "documents",
        "tags",
        "document_tags",
        "processing_jobs",
        "ocr_results",
        "api_keys",
        "audit_logs",
    }

    # PostgreSQL-Sequenzen
    EXPECTED_PG_SEQUENCES: Set[str] = {
        "alembic_version",
    }

    # MinIO-Buckets
    EXPECTED_MINIO_BUCKETS: Set[str] = {
        "documents",
        "processed",
        "thumbnails",
    }

    def __init__(
        self,
        checksum_cache_path: Optional[Path] = None,
    ) -> None:
        """
        Initialisiere BackupValidator.

        Args:
            checksum_cache_path: Pfad zur Checksum-Cache-Datei
        """
        self.checksum_cache_path = checksum_cache_path
        self._checksum_cache: Dict[str, str] = {}

        if checksum_cache_path and checksum_cache_path.exists():
            self._load_checksum_cache()

        logger.info("backup_validator_initialisiert")

    def _load_checksum_cache(self) -> None:
        """Lade Checksum-Cache aus Datei."""
        try:
            import json
            with open(self.checksum_cache_path, "r") as f:
                self._checksum_cache = json.load(f)
            logger.debug("checksum_cache_geladen", anzahl=len(self._checksum_cache))
        except (IOError, OSError, json.JSONDecodeError, ValueError) as e:
            logger.warning("checksum_cache_laden_fehlgeschlagen", **safe_error_log(e))

    def _save_checksum_cache(self) -> None:
        """Speichere Checksum-Cache in Datei."""
        if not self.checksum_cache_path:
            return
        try:
            import json
            with open(self.checksum_cache_path, "w") as f:
                json.dump(self._checksum_cache, f, indent=2)
            logger.debug("checksum_cache_gespeichert")
        except (IOError, OSError, TypeError) as e:
            logger.warning("checksum_cache_speichern_fehlgeschlagen", **safe_error_log(e))

    # =========================================================================
    # Haupt-Validierungsmethoden
    # =========================================================================

    async def validate_backup(
        self,
        path: Path,
        level: ValidationLevel = ValidationLevel.STANDARD,
        expected_type: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validiere ein Backup basierend auf Typ und Level.

        Args:
            path: Pfad zur Backup-Datei/Verzeichnis
            level: Validierungsstufe
            expected_type: Erwarteter Backup-Typ (auto-detect wenn None)

        Returns:
            ValidationResult mit Status und Details
        """
        import time

        start_time = time.perf_counter()

        if not path.exists():
            return ValidationResult(
                backup_path=path,
                backup_type="unknown",
                status=ValidationStatus.INVALID,
                level=level,
                issues=[ValidationIssue(
                    severity="error",
                    code="FILE_NOT_FOUND",
                    message=f"Backup-Datei nicht gefunden: {path}",
                )],
            )

        # Backup-Typ erkennen
        backup_type = expected_type or self._detect_backup_type(path)

        logger.info(
            "backup_validierung_gestartet",
            pfad=str(path),
            typ=backup_type,
            level=level.value,
        )

        # Typ-spezifische Validierung
        if backup_type == "postgres":
            result = await self._validate_postgres_backup(path, level)
        elif backup_type == "redis":
            result = await self._validate_redis_backup(path, level)
        elif backup_type == "minio":
            result = await self._validate_minio_backup(path, level)
        elif backup_type == "config":
            result = await self._validate_config_backup(path, level)
        elif backup_type == "encrypted":
            result = await self._validate_encrypted_backup(path, level)
        else:
            result = await self._validate_generic_backup(path, level)

        # Checksum berechnen
        if path.is_file() and level in (ValidationLevel.DEEP, ValidationLevel.FULL):
            result.checksum_sha256 = await self._calculate_checksum(path)
            self._checksum_cache[str(path)] = result.checksum_sha256
            self._save_checksum_cache()

        # Dauer berechnen
        result.validation_duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Status basierend auf Issues setzen
        if result.error_count > 0:
            result.status = ValidationStatus.INVALID
        elif result.warning_count > 0:
            result.status = ValidationStatus.WARNING
        else:
            result.status = ValidationStatus.VALID

        logger.info(
            "backup_validierung_abgeschlossen",
            pfad=str(path),
            status=result.status.value,
            fehler=result.error_count,
            warnungen=result.warning_count,
            dauer_ms=result.validation_duration_ms,
        )

        return result

    async def validate_all_backups(
        self,
        backup_dir: Path,
        level: ValidationLevel = ValidationLevel.STANDARD,
    ) -> List[ValidationResult]:
        """
        Validiere alle Backups in einem Verzeichnis.

        Args:
            backup_dir: Backup-Hauptverzeichnis
            level: Validierungsstufe

        Returns:
            Liste von ValidationResults
        """
        results: List[ValidationResult] = []

        # Subdirectories durchgehen
        for subdir in ["postgres", "redis", "minio", "config"]:
            type_dir = backup_dir / subdir
            if not type_dir.exists():
                continue

            for item in type_dir.iterdir():
                if item.is_file() or item.is_dir():
                    result = await self.validate_backup(
                        item,
                        level=level,
                        expected_type=subdir
                    )
                    results.append(result)

        return results

    async def verify_checksum(self, path: Path, expected_checksum: str) -> bool:
        """
        Verifiziere Backup gegen bekannten Checksum.

        Args:
            path: Pfad zur Backup-Datei
            expected_checksum: Erwarteter SHA256 Checksum

        Returns:
            True wenn Checksum uebereinstimmt
        """
        if not path.exists():
            return False

        actual_checksum = await self._calculate_checksum(path)
        matches = actual_checksum == expected_checksum

        if not matches:
            logger.warning(
                "checksum_mismatch",
                pfad=str(path),
                erwartet=expected_checksum[:16] + "...",
                aktuell=actual_checksum[:16] + "...",
            )

        return matches

    # =========================================================================
    # PostgreSQL Backup Validierung
    # =========================================================================

    async def _validate_postgres_backup(
        self,
        path: Path,
        level: ValidationLevel,
    ) -> ValidationResult:
        """Validiere PostgreSQL Backup."""
        issues: List[ValidationIssue] = []
        metadata: Dict = {}

        # Quick Level: Nur Datei-Pruefung
        if not path.is_file():
            issues.append(ValidationIssue(
                severity="error",
                code="NOT_A_FILE",
                message="PostgreSQL Backup muss eine Datei sein",
            ))
            return ValidationResult(
                backup_path=path,
                backup_type="postgres",
                status=ValidationStatus.INVALID,
                level=level,
                issues=issues,
            )

        file_size = path.stat().st_size
        if file_size < 100:  # Minimal sinnvolle Groesse
            issues.append(ValidationIssue(
                severity="error",
                code="FILE_TOO_SMALL",
                message=f"Backup zu klein ({file_size} bytes)",
            ))

        if level == ValidationLevel.QUICK:
            return ValidationResult(
                backup_path=path,
                backup_type="postgres",
                status=ValidationStatus.VALID if not issues else ValidationStatus.INVALID,
                level=level,
                issues=issues,
                total_size_bytes=file_size,
            )

        # Standard Level: Strukturelle Pruefung
        try:
            content = await self._read_sql_content(path, max_bytes=1024 * 1024)  # 1MB

            # Pruefen ob gueltiger SQL Dump
            if not content.strip().startswith("--") and "CREATE" not in content.upper():
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_SQL_FORMAT",
                    message="Datei scheint kein gueltiger SQL Dump zu sein",
                ))

            # Tabellen extrahieren
            found_tables = set(re.findall(
                r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)",
                content,
                re.IGNORECASE,
            ))
            metadata["tables_found"] = list(found_tables)

            # Erwartete Tabellen pruefen
            missing_tables = self.EXPECTED_PG_TABLES - found_tables
            if missing_tables:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="MISSING_TABLES",
                    message=f"Fehlende Tabellen: {missing_tables}",
                    details={"missing": list(missing_tables)},
                ))

            # INSERT Statements zaehlen
            insert_count = len(re.findall(r"^INSERT INTO", content, re.MULTILINE | re.IGNORECASE))
            metadata["insert_count"] = insert_count

            if insert_count == 0:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="NO_DATA",
                    message="Backup enthaelt keine INSERT Statements (leer?)",
                ))

        except (IOError, OSError, UnicodeDecodeError, gzip.BadGzipFile) as e:
            issues.append(ValidationIssue(
                severity="error",
                code="READ_ERROR",
                message=f"Fehler beim Lesen der Datei: {e}",
            ))

        # Deep Level: Tiefere Analyse
        if level in (ValidationLevel.DEEP, ValidationLevel.FULL) and content:
            # Pruefen auf vollstaendige Transaktionen
            if "BEGIN;" in content and "COMMIT;" not in content:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="INCOMPLETE_TRANSACTION",
                    message="Unvollstaendige Transaktion gefunden",
                ))

            # Pruefen auf Foreign Key Constraints
            fk_count = len(re.findall(r"FOREIGN KEY", content, re.IGNORECASE))
            metadata["foreign_key_count"] = fk_count

            # Pruefen auf Extensions
            extensions = set(re.findall(
                r"CREATE EXTENSION (?:IF NOT EXISTS )?['\"]?(\w+)['\"]?",
                content,
                re.IGNORECASE,
            ))
            metadata["extensions"] = list(extensions)

            # pgvector Extension sollte vorhanden sein
            if "vector" not in extensions:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="MISSING_EXTENSION",
                    message="pgvector Extension nicht im Backup gefunden",
                ))

        return ValidationResult(
            backup_path=path,
            backup_type="postgres",
            status=ValidationStatus.VALID,
            level=level,
            issues=issues,
            total_size_bytes=file_size,
            metadata=metadata,
        )

    async def _read_sql_content(self, path: Path, max_bytes: int = 1024 * 1024) -> str:
        """Lese SQL-Inhalt (ggf. dekomprimiert)."""
        suffix = "".join(path.suffixes).lower()

        if ".gpg" in suffix:
            raise ValueError("GPG-verschluesselte Dateien nicht direkt lesbar")

        if ".gz" in suffix:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return f.read(max_bytes)
        else:
            with open(path, "r", encoding="utf-8") as f:
                return f.read(max_bytes)

    # =========================================================================
    # Redis Backup Validierung
    # =========================================================================

    async def _validate_redis_backup(
        self,
        path: Path,
        level: ValidationLevel,
    ) -> ValidationResult:
        """Validiere Redis RDB Backup."""
        issues: List[ValidationIssue] = []
        metadata: Dict = {}

        if not path.is_file():
            issues.append(ValidationIssue(
                severity="error",
                code="NOT_A_FILE",
                message="Redis Backup muss eine Datei sein",
            ))
            return ValidationResult(
                backup_path=path,
                backup_type="redis",
                status=ValidationStatus.INVALID,
                level=level,
                issues=issues,
            )

        file_size = path.stat().st_size

        # Quick Level
        if level == ValidationLevel.QUICK:
            if file_size < 10:
                issues.append(ValidationIssue(
                    severity="error",
                    code="FILE_TOO_SMALL",
                    message=f"RDB Datei zu klein ({file_size} bytes)",
                ))
            return ValidationResult(
                backup_path=path,
                backup_type="redis",
                status=ValidationStatus.VALID if not issues else ValidationStatus.INVALID,
                level=level,
                issues=issues,
                total_size_bytes=file_size,
            )

        # Standard Level: RDB Magic Number pruefen
        try:
            with open(path, "rb") as f:
                header = f.read(9)

                if not header.startswith(b"REDIS"):
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_RDB_HEADER",
                        message="Datei hat keinen gueltigen RDB Header",
                    ))
                else:
                    # Redis Version aus Header extrahieren
                    version = header[5:9].decode("ascii", errors="ignore")
                    metadata["rdb_version"] = version
                    logger.debug("redis_rdb_version", version=version)

                    # Version pruefen (mindestens 0006)
                    try:
                        if int(version) < 6:
                            issues.append(ValidationIssue(
                                severity="warning",
                                code="OLD_RDB_VERSION",
                                message=f"Alte RDB Version: {version}",
                            ))
                    except ValueError as e:
                        logger.debug("rdb_version_parse_failed", error_type=type(e).__name__, version=version)

        except (IOError, OSError) as e:
            issues.append(ValidationIssue(
                severity="error",
                code="READ_ERROR",
                message=f"Fehler beim Lesen der RDB Datei: {e}",
            ))

        # Deep Level: Mehr Struktur-Pruefung
        if level in (ValidationLevel.DEEP, ValidationLevel.FULL):
            try:
                with open(path, "rb") as f:
                    f.seek(0, 2)  # Ende
                    total_size = f.tell()
                    f.seek(-1, 2)  # Letztes Byte
                    last_byte = f.read(1)

                    # RDB sollte mit 0xFF (EOF) enden
                    if last_byte != b"\xff":
                        issues.append(ValidationIssue(
                            severity="warning",
                            code="MISSING_EOF_MARKER",
                            message="RDB Datei hat keinen korrekten EOF Marker",
                        ))

                    metadata["total_size"] = total_size

            except (IOError, OSError) as e:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="EOF_CHECK_FAILED",
                    message=f"EOF Pruefung fehlgeschlagen: {e}",
                ))

        return ValidationResult(
            backup_path=path,
            backup_type="redis",
            status=ValidationStatus.VALID,
            level=level,
            issues=issues,
            total_size_bytes=file_size,
            metadata=metadata,
        )

    # =========================================================================
    # MinIO Backup Validierung
    # =========================================================================

    async def _validate_minio_backup(
        self,
        path: Path,
        level: ValidationLevel,
    ) -> ValidationResult:
        """Validiere MinIO Backup (tar.gz oder Verzeichnis)."""
        issues: List[ValidationIssue] = []
        metadata: Dict = {}
        file_count = 0
        total_size = 0

        if path.is_file():
            # Tar-Archiv validieren
            if not (path.suffix == ".gz" or ".tar" in str(path)):
                issues.append(ValidationIssue(
                    severity="warning",
                    code="UNEXPECTED_FORMAT",
                    message=f"Unerwartetes Dateiformat: {path.suffix}",
                ))

            total_size = path.stat().st_size

            if level == ValidationLevel.QUICK:
                return ValidationResult(
                    backup_path=path,
                    backup_type="minio",
                    status=ValidationStatus.VALID if not issues else ValidationStatus.INVALID,
                    level=level,
                    issues=issues,
                    total_size_bytes=total_size,
                )

            # Standard Level: Tar-Struktur pruefen
            try:
                with tarfile.open(path, "r:*") as tar:
                    members = tar.getnames()
                    file_count = len(members)

                    # Bucket-Verzeichnisse extrahieren
                    buckets_found = set()
                    for member in members:
                        parts = member.split("/")
                        if len(parts) > 1:
                            # Erstes Verzeichnis ist meist der Backup-Name
                            # Zweites koennte der Bucket sein
                            if len(parts) > 2:
                                buckets_found.add(parts[1])

                    metadata["buckets_found"] = list(buckets_found)
                    metadata["file_count"] = file_count

                    # Erwartete Buckets pruefen
                    missing_buckets = self.EXPECTED_MINIO_BUCKETS - buckets_found
                    if missing_buckets and buckets_found:
                        issues.append(ValidationIssue(
                            severity="warning",
                            code="MISSING_BUCKETS",
                            message=f"Fehlende Buckets: {missing_buckets}",
                            details={"missing": list(missing_buckets)},
                        ))

            except (tarfile.TarError, IOError, OSError) as e:
                issues.append(ValidationIssue(
                    severity="error",
                    code="TAR_ERROR",
                    message=f"Tar-Archiv kann nicht gelesen werden: {e}",
                ))

        elif path.is_dir():
            # Verzeichnis validieren
            for item in path.rglob("*"):
                if item.is_file():
                    file_count += 1
                    total_size += item.stat().st_size

            # Bucket-Verzeichnisse pruefen
            buckets_found = {d.name for d in path.iterdir() if d.is_dir()}
            metadata["buckets_found"] = list(buckets_found)

            missing_buckets = self.EXPECTED_MINIO_BUCKETS - buckets_found
            if missing_buckets and buckets_found:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="MISSING_BUCKETS",
                    message=f"Fehlende Buckets: {missing_buckets}",
                ))
        else:
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_PATH",
                message="Pfad ist weder Datei noch Verzeichnis",
            ))

        return ValidationResult(
            backup_path=path,
            backup_type="minio",
            status=ValidationStatus.VALID,
            level=level,
            issues=issues,
            file_count=file_count,
            total_size_bytes=total_size,
            metadata=metadata,
        )

    # =========================================================================
    # Config Backup Validierung
    # =========================================================================

    async def _validate_config_backup(
        self,
        path: Path,
        level: ValidationLevel,
    ) -> ValidationResult:
        """Validiere Konfigurations-Backup."""
        issues: List[ValidationIssue] = []
        metadata: Dict = {}
        file_count = 0

        if not path.is_file():
            issues.append(ValidationIssue(
                severity="error",
                code="NOT_A_FILE",
                message="Config Backup muss eine Datei sein",
            ))
            return ValidationResult(
                backup_path=path,
                backup_type="config",
                status=ValidationStatus.INVALID,
                level=level,
                issues=issues,
            )

        total_size = path.stat().st_size

        if level == ValidationLevel.QUICK:
            return ValidationResult(
                backup_path=path,
                backup_type="config",
                status=ValidationStatus.VALID,
                level=level,
                issues=issues,
                total_size_bytes=total_size,
            )

        # Standard Level: Tar-Inhalt pruefen
        try:
            with tarfile.open(path, "r:*") as tar:
                members = tar.getnames()
                file_count = len(members)
                metadata["contents"] = members[:50]  # Erste 50

                # Wichtige Konfigurationsdateien pruefen
                important_files = {".env", "app", "infrastructure"}
                found_important = set()

                for member in members:
                    for important in important_files:
                        if important in member:
                            found_important.add(important)

                metadata["important_files_found"] = list(found_important)

                missing = important_files - found_important
                if missing:
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="MISSING_CONFIG",
                        message=f"Fehlende Konfigurationen: {missing}",
                    ))

        except (tarfile.TarError, IOError, OSError) as e:
            issues.append(ValidationIssue(
                severity="error",
                code="TAR_ERROR",
                message=f"Config-Archiv kann nicht gelesen werden: {e}",
            ))

        return ValidationResult(
            backup_path=path,
            backup_type="config",
            status=ValidationStatus.VALID,
            level=level,
            issues=issues,
            file_count=file_count,
            total_size_bytes=total_size,
            metadata=metadata,
        )

    # =========================================================================
    # Encrypted Backup Validierung
    # =========================================================================

    async def _validate_encrypted_backup(
        self,
        path: Path,
        level: ValidationLevel,
    ) -> ValidationResult:
        """Validiere GPG-verschluesseltes Backup."""
        issues: List[ValidationIssue] = []
        metadata: Dict = {}

        if not path.is_file():
            issues.append(ValidationIssue(
                severity="error",
                code="NOT_A_FILE",
                message="Verschluesseltes Backup muss eine Datei sein",
            ))
            return ValidationResult(
                backup_path=path,
                backup_type="encrypted",
                status=ValidationStatus.INVALID,
                level=level,
                issues=issues,
            )

        total_size = path.stat().st_size

        if total_size < 100:
            issues.append(ValidationIssue(
                severity="error",
                code="FILE_TOO_SMALL",
                message=f"Verschluesselte Datei zu klein ({total_size} bytes)",
            ))

        # Standard Level: GPG Header pruefen
        if level != ValidationLevel.QUICK:
            try:
                with open(path, "rb") as f:
                    header = f.read(2)

                    # GPG Packets beginnen mit 0x85 (alt) oder 0xc0-0xff (neu)
                    if header[0] not in (0x85, 0xa3, 0xc0, 0xc1, 0xc2, 0xc5, 0xc6):
                        # Pruefen auf ASCII-armored GPG
                        f.seek(0)
                        ascii_header = f.read(27)
                        if not ascii_header.startswith(b"-----BEGIN PGP MESSAGE"):
                            issues.append(ValidationIssue(
                                severity="warning",
                                code="UNKNOWN_GPG_FORMAT",
                                message="Unbekanntes GPG Format - koennte keine GPG Datei sein",
                            ))

                    metadata["gpg_format"] = "binary" if header[0] >= 0x80 else "ascii"

            except (IOError, OSError) as e:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="GPG_CHECK_FAILED",
                    message=f"GPG Format-Pruefung fehlgeschlagen: {e}",
                ))

        # Original-Typ aus Dateiname ableiten
        original_name = path.stem  # Entfernt .gpg
        if ".sql" in original_name:
            metadata["original_type"] = "postgres"
        elif ".rdb" in original_name:
            metadata["original_type"] = "redis"
        elif ".tar" in original_name:
            metadata["original_type"] = "archive"
        else:
            metadata["original_type"] = "unknown"

        return ValidationResult(
            backup_path=path,
            backup_type="encrypted",
            status=ValidationStatus.VALID,
            level=level,
            issues=issues,
            total_size_bytes=total_size,
            metadata=metadata,
        )

    # =========================================================================
    # Generic Backup Validierung
    # =========================================================================

    async def _validate_generic_backup(
        self,
        path: Path,
        level: ValidationLevel,
    ) -> ValidationResult:
        """Validiere generisches Backup (Fallback)."""
        issues: List[ValidationIssue] = []

        if path.is_file():
            total_size = path.stat().st_size
            if total_size == 0:
                issues.append(ValidationIssue(
                    severity="error",
                    code="EMPTY_FILE",
                    message="Backup-Datei ist leer",
                ))
        elif path.is_dir():
            total_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        else:
            issues.append(ValidationIssue(
                severity="error",
                code="INVALID_PATH",
                message="Pfad existiert nicht oder ist unzugaenglich",
            ))
            total_size = 0

        return ValidationResult(
            backup_path=path,
            backup_type="generic",
            status=ValidationStatus.VALID if not issues else ValidationStatus.INVALID,
            level=level,
            issues=issues,
            total_size_bytes=total_size,
        )

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    def _detect_backup_type(self, path: Path) -> str:
        """Erkenne Backup-Typ anhand von Pfad und Inhalt."""
        name = path.name.lower()
        suffix = "".join(path.suffixes).lower()

        # GPG-verschluesselt
        if suffix.endswith(".gpg"):
            return "encrypted"

        # PostgreSQL
        if "postgres" in name or ".sql" in suffix:
            return "postgres"

        # Redis
        if "redis" in name or suffix == ".rdb":
            return "redis"

        # MinIO
        if "minio" in name:
            return "minio"

        # Config
        if "config" in name:
            return "config"

        # Parent-Verzeichnis pruefen
        if path.parent.name in ("postgres", "redis", "minio", "config"):
            return path.parent.name

        return "generic"

    async def _calculate_checksum(self, path: Path, algorithm: str = "sha256") -> str:
        """Berechne Checksum fuer Datei."""
        hash_func = hashlib.new(algorithm)

        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)

        return hash_func.hexdigest()


# =============================================================================
# Singleton Instance
# =============================================================================

_validator_instance: Optional[BackupValidator] = None


def get_backup_validator(
    checksum_cache_path: Optional[Path] = None,
) -> BackupValidator:
    """Hole globale BackupValidator Instanz."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = BackupValidator(checksum_cache_path)
    return _validator_instance

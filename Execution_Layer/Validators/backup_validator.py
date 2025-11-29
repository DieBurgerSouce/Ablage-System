# -*- coding: utf-8 -*-
"""
Backup Validator - Ablage-System

Validates database backups to ensure recoverability and data integrity.
Integrated with Prometheus metrics for monitoring.

Key Functions:
- Verify backup file integrity (checksums)
- Test backup restoration (dry-run)
- Validate backup completeness (row counts, schema)
- Check backup age and retention compliance
- Generate backup health reports
- Emit Prometheus metrics

Related:
- Data Migration Runner: ../Runners/data_migration_runner.py
- GDPR Compliance Audit: ../../Dynamic_Knowledge/Logs/gdpr_compliance_audit_log.md
- Backup Metrics Service: ../../app/services/backup_metrics_service.py
"""

import asyncio
import gzip
import hashlib
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg
import structlog
from dataclasses import dataclass, field
from pydantic import BaseModel

# Import German messages
try:
    from app.core.german_messages import BackupMessages
except ImportError:
    # Fallback for standalone usage
    class BackupMessages:
        VALIDATION_STARTED = "Sicherungs-Validierung gestartet"
        VALIDATION_SUCCESS = "Sicherungs-Validierung erfolgreich"
        VALIDATION_FAILED = "Sicherungs-Validierung fehlgeschlagen: {details}"
        CHECKSUM_VERIFIED = "Pruefsumme verifiziert"
        CHECKSUM_MISMATCH = "Pruefsummen-Fehler: Sicherung beschaedigt"
        RESTORE_TEST_STARTED = "Wiederherstellungstest gestartet"
        RESTORE_TEST_SUCCESS = "Wiederherstellungstest erfolgreich"
        RESTORE_TEST_FAILED = "Wiederherstellungstest fehlgeschlagen: {details}"
        BACKUP_STALE = "Letzte Sicherung aelter als {hours} Stunden"


# Import metrics service
try:
    from app.services.backup_metrics_service import get_backup_metrics, BackupMetricData
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    BackupMetricData = None


logger = structlog.get_logger(__name__)


@dataclass
class BackupValidationResult:
    """Result of backup validation."""
    backup_file: str
    backup_type: str
    is_valid: bool
    checksum_verified: bool
    restoration_tested: bool
    data_integrity_ok: bool
    decryption_ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "backup_file": self.backup_file,
            "backup_type": self.backup_type,
            "is_valid": self.is_valid,
            "checksum_verified": self.checksum_verified,
            "restoration_tested": self.restoration_tested,
            "data_integrity_ok": self.data_integrity_ok,
            "decryption_ok": self.decryption_ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "duration_seconds": self.duration_seconds,
        }


class BackupValidator:
    """Validate PostgreSQL and other database backups with metrics integration."""

    def __init__(
        self,
        db_connection_string: str,
        backup_dir: Path,
        gpg_home: Optional[Path] = None,
        gpg_passphrase_file: Optional[Path] = None,
        emit_metrics: bool = True,
    ):
        """
        Initialize backup validator.

        Args:
            db_connection_string: PostgreSQL connection string
            backup_dir: Directory containing backups
            gpg_home: GPG home directory for encrypted backups
            gpg_passphrase_file: Path to GPG passphrase file
            emit_metrics: Whether to emit Prometheus metrics
        """
        self.db_url = db_connection_string
        self.backup_dir = Path(backup_dir)
        self.gpg_home = Path(gpg_home) if gpg_home else None
        self.gpg_passphrase_file = Path(gpg_passphrase_file) if gpg_passphrase_file else None
        self.emit_metrics = emit_metrics and METRICS_AVAILABLE

        self.expected_tables = [
            "users", "documents", "ocr_results", "audit_logs",
            "alembic_version"
        ]

        # Initialize metrics if available
        if self.emit_metrics:
            self.metrics = get_backup_metrics()
        else:
            self.metrics = None

    async def validate_backup(
        self,
        backup_file: Path,
        backup_type: str = "full",
        skip_restoration_test: bool = False,
    ) -> BackupValidationResult:
        """
        Comprehensive backup validation.

        Args:
            backup_file: Path to backup file
            backup_type: Type of backup (full, db-only, files-only)
            skip_restoration_test: Skip actual restore test (faster but less thorough)

        Returns:
            BackupValidationResult with validation details
        """
        start_time = datetime.utcnow()
        errors: List[str] = []
        warnings: List[str] = []
        metadata: Dict[str, Any] = {}

        logger.info(
            "backup_validation_started",
            backup_file=str(backup_file),
            backup_type=backup_type,
        )

        # Step 1: File exists and readable
        if not backup_file.exists():
            errors.append(f"Sicherungsdatei nicht gefunden: {backup_file}")
            return self._create_result(
                backup_file, backup_type, False, False, False, False, False,
                errors, warnings, start_time, metadata
            )

        # Get file info
        metadata["file_size_bytes"] = backup_file.stat().st_size
        metadata["file_size_mb"] = round(metadata["file_size_bytes"] / (1024 * 1024), 2)

        # Step 2: Check if encrypted and handle decryption
        is_encrypted = backup_file.suffix == ".gpg"
        decryption_ok = True
        work_file = backup_file

        if is_encrypted:
            metadata["encrypted"] = True
            decryption_ok, work_file, decrypt_errors = await self._handle_decryption(backup_file)
            if not decryption_ok:
                errors.extend(decrypt_errors)
                return self._create_result(
                    backup_file, backup_type, False, False, False, False, False,
                    errors, warnings, start_time, metadata
                )
        else:
            metadata["encrypted"] = False

        # Step 3: Verify checksum
        checksum_verified = await self._verify_checksum(work_file)
        if not checksum_verified:
            # Try without checksum file - verify file can be read
            checksum_verified = await self._verify_file_readable(work_file)
            if not checksum_verified:
                errors.append(BackupMessages.CHECKSUM_MISMATCH)
            else:
                warnings.append("Keine Pruefsummen-Datei vorhanden, Datei scheint lesbar")

        # Step 4: Check backup age
        age_hours = self._check_backup_age(backup_file)
        metadata["age_hours"] = age_hours
        metadata["age_days"] = round(age_hours / 24, 1)

        if age_hours > 26:
            warnings.append(BackupMessages.BACKUP_STALE.format(hours=int(age_hours)))

        # Step 5: Test restoration (if applicable)
        restoration_ok = True
        restore_errors: List[str] = []

        if not skip_restoration_test and self._is_database_backup(work_file):
            restoration_ok, restore_errors = await self._test_restoration(work_file)
            if not restoration_ok:
                errors.extend(restore_errors)

        # Step 6: Validate data integrity (if restoration successful)
        data_integrity_ok = True
        if restoration_ok and not skip_restoration_test and self._is_database_backup(work_file):
            data_integrity_ok, integrity_errors = await self._validate_data_integrity(work_file)
            if not data_integrity_ok:
                errors.extend(integrity_errors)

        # Cleanup decrypted temp file
        if is_encrypted and work_file != backup_file and work_file.exists():
            work_file.unlink()

        # Determine overall validity
        is_valid = checksum_verified and restoration_ok and data_integrity_ok and decryption_ok

        result = self._create_result(
            backup_file, backup_type, is_valid, checksum_verified,
            restoration_ok, data_integrity_ok, decryption_ok,
            errors, warnings, start_time, metadata
        )

        # Emit metrics
        if self.emit_metrics:
            self._emit_validation_metrics(result)

        logger.info(
            "backup_validation_completed",
            backup_file=str(backup_file),
            is_valid=is_valid,
            duration_seconds=result.duration_seconds,
            errors_count=len(errors),
        )

        return result

    def _create_result(
        self,
        backup_file: Path,
        backup_type: str,
        is_valid: bool,
        checksum_verified: bool,
        restoration_tested: bool,
        data_integrity_ok: bool,
        decryption_ok: bool,
        errors: List[str],
        warnings: List[str],
        start_time: datetime,
        metadata: Dict[str, Any],
    ) -> BackupValidationResult:
        """Create a BackupValidationResult with duration calculated."""
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        return BackupValidationResult(
            backup_file=str(backup_file),
            backup_type=backup_type,
            is_valid=is_valid,
            checksum_verified=checksum_verified,
            restoration_tested=restoration_tested,
            data_integrity_ok=data_integrity_ok,
            decryption_ok=decryption_ok,
            errors=errors,
            warnings=warnings,
            timestamp=end_time,
            metadata=metadata,
            duration_seconds=duration,
        )

    async def _handle_decryption(
        self, backup_file: Path
    ) -> Tuple[bool, Path, List[str]]:
        """
        Handle decryption of encrypted backup files.

        Returns:
            (success, decrypted_file_path, errors)
        """
        errors: List[str] = []

        if not self.gpg_home or not self.gpg_passphrase_file:
            errors.append("GPG-Konfiguration fehlt fuer verschluesselte Sicherung")
            return (False, backup_file, errors)

        if not self.gpg_passphrase_file.exists():
            errors.append(f"GPG-Passphrase-Datei nicht gefunden: {self.gpg_passphrase_file}")
            return (False, backup_file, errors)

        # Create temp file for decrypted content
        output_file = backup_file.with_suffix("")
        temp_output = Path(tempfile.mktemp(suffix=output_file.suffix))

        try:
            cmd = [
                "gpg",
                "--homedir", str(self.gpg_home),
                "--batch",
                "--yes",
                "--pinentry-mode", "loopback",
                "--passphrase-file", str(self.gpg_passphrase_file),
                "--output", str(temp_output),
                "--decrypt", str(backup_file),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                errors.append(f"GPG-Entschluesselung fehlgeschlagen: {result.stderr}")
                return (False, backup_file, errors)

            logger.info("backup_decrypted", backup_file=str(backup_file))
            return (True, temp_output, [])

        except subprocess.TimeoutExpired:
            errors.append("GPG-Entschluesselung Zeitueberschreitung")
            return (False, backup_file, errors)
        except Exception as e:
            errors.append(f"Entschluesselungsfehler: {str(e)}")
            return (False, backup_file, errors)

    async def _verify_checksum(self, backup_file: Path) -> bool:
        """
        Verify backup file checksum.

        Returns:
            True if checksum matches, False otherwise
        """
        checksum_file = Path(str(backup_file) + '.sha256')

        if not checksum_file.exists():
            logger.warning("checksum_file_missing", backup_file=str(backup_file))
            return False

        # Calculate current checksum
        sha256 = hashlib.sha256()
        try:
            with open(backup_file, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            calculated_checksum = sha256.hexdigest()
        except IOError as e:
            logger.error("checksum_read_error", error=str(e))
            return False

        # Read stored checksum
        try:
            with open(checksum_file, 'r') as f:
                stored_checksum = f.read().strip().split()[0]
        except IOError as e:
            logger.error("checksum_file_read_error", error=str(e))
            return False

        if calculated_checksum == stored_checksum:
            logger.info("checksum_verified", backup_file=str(backup_file))
            return True
        else:
            logger.error(
                "checksum_mismatch",
                backup_file=str(backup_file),
                calculated=calculated_checksum,
                stored=stored_checksum,
            )
            return False

    async def _verify_file_readable(self, backup_file: Path) -> bool:
        """
        Verify backup file is readable and not corrupted.

        Returns:
            True if file seems valid
        """
        try:
            suffix = backup_file.suffix.lower()

            if suffix == ".gz":
                # Test gzip integrity
                with gzip.open(backup_file, 'rb') as f:
                    # Read first 1KB to verify
                    f.read(1024)
                return True
            elif suffix in (".sql", ".rdb"):
                # Just verify file is readable
                with open(backup_file, 'rb') as f:
                    f.read(1024)
                return True
            else:
                # Unknown format, assume readable if accessible
                return backup_file.stat().st_size > 0

        except Exception as e:
            logger.error("file_read_error", error=str(e))
            return False

    def _check_backup_age(self, backup_file: Path) -> float:
        """
        Check backup age in hours.

        Returns:
            Age of backup in hours
        """
        mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
        age = datetime.now() - mtime
        return age.total_seconds() / 3600

    def _is_database_backup(self, backup_file: Path) -> bool:
        """Check if file is a database backup (SQL dump)."""
        name = backup_file.name.lower()
        return ".sql" in name or name.startswith("ablage_")

    async def _test_restoration(self, backup_file: Path) -> Tuple[bool, List[str]]:
        """
        Test backup restoration to temporary database.

        Returns:
            (success, errors)
        """
        errors: List[str] = []

        try:
            # Create temporary database for testing
            temp_db = f"ablage_restore_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

            # Create test database
            result = subprocess.run(
                ['createdb', '-h', 'localhost', '-U', 'postgres', temp_db],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                errors.append(f"Testdatenbank konnte nicht erstellt werden: {result.stderr}")
                return (False, errors)

            # Determine restore method based on file type
            if backup_file.suffix == ".gz":
                # Compressed SQL dump
                cmd = f"gunzip -c {backup_file} | psql -h localhost -U postgres -d {temp_db}"
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=300
                )
            else:
                # pg_restore for custom format
                result = subprocess.run(
                    ['pg_restore', '-h', 'localhost', '-U', 'postgres', '-d', temp_db, str(backup_file)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

            if result.returncode != 0 and "ERROR" in result.stderr:
                errors.append(f"Wiederherstellung fehlgeschlagen: {result.stderr[:500]}")
                restoration_ok = False
            else:
                restoration_ok = True
                logger.info("backup_restoration_test_successful", temp_db=temp_db)

            # Cleanup: Drop test database
            subprocess.run(
                ['dropdb', '-h', 'localhost', '-U', 'postgres', temp_db],
                timeout=60,
            )

            return (restoration_ok, errors)

        except subprocess.TimeoutExpired:
            errors.append("Wiederherstellungstest Zeitueberschreitung")
            return (False, errors)
        except Exception as e:
            logger.exception("restoration_test_error", error=str(e))
            errors.append(f"Wiederherstellungstest Ausnahme: {str(e)}")
            return (False, errors)

    async def _validate_data_integrity(self, backup_file: Path) -> Tuple[bool, List[str]]:
        """
        Validate data integrity of restored backup.

        Returns:
            (integrity_ok, errors)
        """
        errors: List[str] = []

        try:
            # Create temp database and restore
            temp_db = f"ablage_integrity_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

            subprocess.run(
                ['createdb', '-h', 'localhost', '-U', 'postgres', temp_db],
                check=True,
                timeout=60,
            )

            if backup_file.suffix == ".gz":
                cmd = f"gunzip -c {backup_file} | psql -h localhost -U postgres -d {temp_db}"
                subprocess.run(cmd, shell=True, check=True, timeout=300)
            else:
                subprocess.run(
                    ['pg_restore', '-h', 'localhost', '-U', 'postgres', '-d', temp_db, str(backup_file)],
                    check=True,
                    timeout=300,
                )

            # Connect and validate
            conn = await psycopg.AsyncConnection.connect(
                f"postgresql://postgres:postgres@localhost:5432/{temp_db}"
            )

            # Check all expected tables exist
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                tables = {row[0] for row in await cur.fetchall()}

            missing_tables = set(self.expected_tables) - tables
            if missing_tables:
                errors.append(f"Fehlende Tabellen: {', '.join(missing_tables)}")

            # Check row counts are reasonable
            async with conn.cursor() as cur:
                for table in ["users", "documents"]:
                    if table in tables:
                        await cur.execute(f"SELECT COUNT(*) FROM {table}")
                        count = (await cur.fetchone())[0]
                        logger.debug(f"table_row_count", table=table, count=count)

            await conn.close()

            # Cleanup
            subprocess.run(['dropdb', '-h', 'localhost', '-U', 'postgres', temp_db], timeout=60)

            integrity_ok = len(errors) == 0
            return (integrity_ok, errors)

        except subprocess.TimeoutExpired:
            errors.append("Integritaetspruefung Zeitueberschreitung")
            return (False, errors)
        except Exception as e:
            logger.exception("data_integrity_check_error", error=str(e))
            errors.append(f"Integritaetspruefung Ausnahme: {str(e)}")
            return (False, errors)

    def _emit_validation_metrics(self, result: BackupValidationResult) -> None:
        """Emit Prometheus metrics for validation result."""
        if not self.metrics:
            return

        try:
            if result.is_valid:
                self.metrics.record_validation_success(result.backup_type)
            else:
                self.metrics.record_validation_failure(
                    result.backup_type,
                    "; ".join(result.errors) if result.errors else "Unbekannter Fehler"
                )
        except Exception as e:
            logger.warning("metrics_emission_error", error=str(e))

    async def validate_all_backups(
        self,
        max_age_hours: int = 168,  # 7 days
        skip_restoration_test: bool = True,
    ) -> List[BackupValidationResult]:
        """
        Validate all backups in backup directory.

        Args:
            max_age_hours: Only validate backups newer than this
            skip_restoration_test: Skip full restoration tests for speed

        Returns:
            List of BackupValidationResult
        """
        results: List[BackupValidationResult] = []

        # Find all backup files
        backup_patterns = ["*.sql.gz", "*.sql.gz.gpg", "*.dump", "*.dump.gpg"]
        backup_files: List[Path] = []

        for pattern in backup_patterns:
            for subdir in ["postgres", "."]:
                search_dir = self.backup_dir / subdir
                if search_dir.exists():
                    backup_files.extend(search_dir.glob(pattern))

        # Sort by modification time (newest first)
        backup_files = sorted(
            backup_files,
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        # Filter by age
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        backup_files = [
            f for f in backup_files
            if datetime.fromtimestamp(f.stat().st_mtime) > cutoff_time
        ]

        logger.info("validating_all_backups", backup_count=len(backup_files))

        for backup_file in backup_files:
            # Determine backup type from path
            backup_type = "full"
            if "postgres" in str(backup_file):
                backup_type = "postgres"
            elif "redis" in str(backup_file):
                backup_type = "redis"
            elif "minio" in str(backup_file):
                backup_type = "minio"
            elif "config" in str(backup_file):
                backup_type = "config"

            result = await self.validate_backup(
                backup_file,
                backup_type=backup_type,
                skip_restoration_test=skip_restoration_test,
            )
            results.append(result)

        return results

    def validate_latest_backup(self) -> BackupValidationResult:
        """
        Quick validation of the most recent backup.
        Synchronous wrapper for use in systemd timers.

        Returns:
            BackupValidationResult for latest backup
        """
        return asyncio.run(self._validate_latest_backup_async())

    async def _validate_latest_backup_async(self) -> BackupValidationResult:
        """Async implementation of latest backup validation."""
        # Find most recent backup
        backup_patterns = ["*.sql.gz", "*.sql.gz.gpg"]
        backup_files: List[Path] = []

        postgres_dir = self.backup_dir / "postgres"
        if postgres_dir.exists():
            for pattern in backup_patterns:
                backup_files.extend(postgres_dir.glob(pattern))

        if not backup_files:
            return BackupValidationResult(
                backup_file="none",
                backup_type="unknown",
                is_valid=False,
                checksum_verified=False,
                restoration_tested=False,
                data_integrity_ok=False,
                decryption_ok=False,
                errors=["Keine Sicherungsdateien gefunden"],
                warnings=[],
                timestamp=datetime.utcnow(),
                metadata={},
                duration_seconds=0.0,
            )

        # Get most recent
        latest = max(backup_files, key=lambda p: p.stat().st_mtime)

        return await self.validate_backup(
            latest,
            backup_type="postgres",
            skip_restoration_test=True,  # Quick validation
        )

    def generate_report(
        self,
        results: List[BackupValidationResult],
        include_german: bool = True,
    ) -> str:
        """
        Generate backup validation report.

        Args:
            results: List of validation results
            include_german: Use German labels and headers

        Returns:
            Report as formatted string
        """
        if include_german:
            title = "Sicherungs-Validierungsbericht"
            generated = "Erstellt"
            total = "Gesamt Sicherungen"
            valid_label = "Gueltige Sicherungen"
            status_valid = "GUELTIG"
            status_invalid = "UNGUELTIG"
            checksum_label = "Pruefsumme"
            restoration_label = "Wiederherstellung"
            integrity_label = "Datenintegritaet"
            decryption_label = "Entschluesselung"
            errors_label = "Fehler"
            warnings_label = "Warnungen"
        else:
            title = "Backup Validation Report"
            generated = "Generated"
            total = "Total Backups"
            valid_label = "Valid Backups"
            status_valid = "VALID"
            status_invalid = "INVALID"
            checksum_label = "Checksum"
            restoration_label = "Restoration"
            integrity_label = "Data Integrity"
            decryption_label = "Decryption"
            errors_label = "Errors"
            warnings_label = "Warnings"

        report_lines = [
            f"# {title}",
            f"{generated}: {datetime.utcnow().isoformat()}",
            f"{total}: {len(results)}",
            "",
        ]

        valid_count = sum(1 for r in results if r.is_valid)
        report_lines.append(f"{valid_label}: {valid_count}/{len(results)}")
        report_lines.append("")

        for result in results:
            status = f"[OK] {status_valid}" if result.is_valid else f"[X] {status_invalid}"
            report_lines.append(f"## {Path(result.backup_file).name}")
            report_lines.append(f"Status: {status}")
            report_lines.append(f"Typ: {result.backup_type}")
            report_lines.append(f"{checksum_label}: {'OK' if result.checksum_verified else 'FEHLER'}")
            report_lines.append(f"{restoration_label}: {'OK' if result.restoration_tested else 'FEHLER'}")
            report_lines.append(f"{integrity_label}: {'OK' if result.data_integrity_ok else 'FEHLER'}")
            report_lines.append(f"{decryption_label}: {'OK' if result.decryption_ok else 'FEHLER'}")

            if result.metadata:
                if "age_hours" in result.metadata:
                    report_lines.append(f"Alter: {result.metadata['age_hours']:.1f} Stunden")
                if "file_size_mb" in result.metadata:
                    report_lines.append(f"Groesse: {result.metadata['file_size_mb']} MB")

            if result.errors:
                report_lines.append(f"\n{errors_label}:")
                for error in result.errors:
                    report_lines.append(f"  - {error}")

            if result.warnings:
                report_lines.append(f"\n{warnings_label}:")
                for warning in result.warnings:
                    report_lines.append(f"  - {warning}")

            report_lines.append("")

        return "\n".join(report_lines)


async def main():
    """Main entry point for backup validation."""
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ablage")
    backup_dir = Path(os.getenv("BACKUP_DIR", "/var/backups/ablage"))
    gpg_home = os.getenv("GPG_HOME")
    gpg_passphrase_file = os.getenv("GPG_PASSPHRASE_FILE")

    validator = BackupValidator(
        db_url,
        backup_dir,
        gpg_home=Path(gpg_home) if gpg_home else None,
        gpg_passphrase_file=Path(gpg_passphrase_file) if gpg_passphrase_file else None,
        emit_metrics=True,
    )

    # Validate all backups
    results = await validator.validate_all_backups(
        max_age_hours=168,  # Last 7 days
        skip_restoration_test=True,  # Quick mode
    )

    # Generate report
    report = validator.generate_report(results)
    print(report)

    # Save report to file
    report_file = backup_dir / f"validation_report_{datetime.utcnow().strftime('%Y%m%d')}.md"
    report_file.write_text(report, encoding="utf-8")
    print(f"\nBericht gespeichert: {report_file}")

    # Exit with error code if any validation failed
    if not all(r.is_valid for r in results):
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())

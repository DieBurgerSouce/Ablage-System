"""
Backup Validator - Ablage-System

Validates database backups to ensure recoverability and data integrity.

Key Functions:
- Verify backup file integrity (checksums)
- Test backup restoration (dry-run)
- Validate backup completeness (row counts, schema)
- Check backup age and retention compliance
- Generate backup health reports

Related:
- Data Migration Runner: ../Runners/data_migration_runner.py
- GDPR Compliance Audit: ../../Dynamic_Knowledge/Logs/gdpr_compliance_audit_log.md
"""

import hashlib
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass

import psycopg
from pydantic import BaseModel

import structlog
logger = structlog.get_logger(__name__)


@dataclass
class BackupValidationResult:
    """Result of backup validation."""
    backup_file: str
    is_valid: bool
    checksum_verified: bool
    restoration_tested: bool
    data_integrity_ok: bool
    errors: List[str]
    warnings: List[str]
    timestamp: datetime
    metadata: Dict[str, Any]


class BackupValidator:
    """Validate PostgreSQL database backups."""

    def __init__(self, db_connection_string: str, backup_dir: Path):
        """
        Initialize backup validator.

        Args:
            db_connection_string: PostgreSQL connection string
            backup_dir: Directory containing backups
        """
        self.db_url = db_connection_string
        self.backup_dir = backup_dir
        self.expected_tables = [
            "users", "documents", "ocr_results", "audit_logs",
            "alembic_version"
        ]

    async def validate_backup(self, backup_file: Path) -> BackupValidationResult:
        """
        Comprehensive backup validation.

        Args:
            backup_file: Path to backup file

        Returns:
            BackupValidationResult with validation details
        """
        errors = []
        warnings = []
        metadata = {}

        logger.info("backup_validation_started", backup_file=str(backup_file))

        # Step 1: File exists and readable
        if not backup_file.exists():
            errors.append(f"Backup file not found: {backup_file}")
            return BackupValidationResult(
                backup_file=str(backup_file),
                is_valid=False,
                checksum_verified=False,
                restoration_tested=False,
                data_integrity_ok=False,
                errors=errors,
                warnings=warnings,
                timestamp=datetime.utcnow(),
                metadata=metadata
            )

        # Step 2: Verify checksum
        checksum_verified = self._verify_checksum(backup_file)
        if not checksum_verified:
            errors.append("Checksum verification failed")

        # Step 3: Check backup age
        age_days = self._check_backup_age(backup_file)
        metadata["age_days"] = age_days
        if age_days > 1:
            warnings.append(f"Backup is {age_days} days old (> 24 hours)")

        # Step 4: Test restoration (dry-run)
        restoration_ok, restore_errors = await self._test_restoration(backup_file)
        if not restoration_ok:
            errors.extend(restore_errors)

        # Step 5: Validate data integrity (if restoration successful)
        data_integrity_ok = False
        if restoration_ok:
            data_integrity_ok, integrity_errors = await self._validate_data_integrity(backup_file)
            if not data_integrity_ok:
                errors.extend(integrity_errors)

        # Determine overall validity
        is_valid = checksum_verified and restoration_ok and data_integrity_ok

        result = BackupValidationResult(
            backup_file=str(backup_file),
            is_valid=is_valid,
            checksum_verified=checksum_verified,
            restoration_tested=restoration_ok,
            data_integrity_ok=data_integrity_ok,
            errors=errors,
            warnings=warnings,
            timestamp=datetime.utcnow(),
            metadata=metadata
        )

        logger.info(
            "backup_validation_completed",
            backup_file=str(backup_file),
            is_valid=is_valid,
            errors_count=len(errors)
        )

        return result

    def _verify_checksum(self, backup_file: Path) -> bool:
        """
        Verify backup file checksum.

        Returns:
            True if checksum matches, False otherwise
        """
        checksum_file = backup_file.with_suffix(backup_file.suffix + '.sha256')

        if not checksum_file.exists():
            logger.warning("checksum_file_missing", backup_file=str(backup_file))
            return False

        # Calculate current checksum
        sha256 = hashlib.sha256()
        with open(backup_file, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        calculated_checksum = sha256.hexdigest()

        # Read stored checksum
        with open(checksum_file, 'r') as f:
            stored_checksum = f.read().strip().split()[0]

        if calculated_checksum == stored_checksum:
            logger.info("checksum_verified", backup_file=str(backup_file))
            return True
        else:
            logger.error(
                "checksum_mismatch",
                backup_file=str(backup_file),
                calculated=calculated_checksum,
                stored=stored_checksum
            )
            return False

    def _check_backup_age(self, backup_file: Path) -> int:
        """
        Check backup age in days.

        Returns:
            Age of backup in days
        """
        mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
        age = datetime.now() - mtime
        return age.days

    async def _test_restoration(self, backup_file: Path) -> Tuple[bool, List[str]]:
        """
        Test backup restoration to temporary database.

        Returns:
            (success, errors)
        """
        errors = []

        try:
            # Create temporary database for testing
            temp_db = f"ablage_restore_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

            # Create test database
            result = subprocess.run(
                ['createdb', '-h', 'localhost', '-U', 'postgres', temp_db],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                errors.append(f"Failed to create test database: {result.stderr}")
                return (False, errors)

            # Restore backup to test database
            result = subprocess.run(
                ['pg_restore', '-h', 'localhost', '-U', 'postgres', '-d', temp_db, str(backup_file)],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                errors.append(f"Backup restoration failed: {result.stderr}")
                restoration_ok = False
            else:
                restoration_ok = True
                logger.info("backup_restoration_test_successful", temp_db=temp_db)

            # Cleanup: Drop test database
            subprocess.run(['dropdb', '-h', 'localhost', '-U', 'postgres', temp_db])

            return (restoration_ok, errors)

        except Exception as e:
            logger.exception("restoration_test_error", error=str(e))
            errors.append(f"Restoration test exception: {str(e)}")
            return (False, errors)

    async def _validate_data_integrity(self, backup_file: Path) -> Tuple[bool, List[str]]:
        """
        Validate data integrity of restored backup.

        Returns:
            (integrity_ok, errors)
        """
        errors = []

        try:
            # Create temp database and restore (simplified for validation)
            temp_db = f"ablage_integrity_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

            subprocess.run(['createdb', '-h', 'localhost', '-U', 'postgres', temp_db], check=True)
            subprocess.run(['pg_restore', '-h', 'localhost', '-U', 'postgres', '-d', temp_db, str(backup_file)], check=True)

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
                errors.append(f"Missing tables: {missing_tables}")

            # Check row counts are reasonable
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM users")
                user_count = (await cur.fetchone())[0]

                if user_count == 0:
                    errors.append("No users found in backup (expected > 0)")

            await conn.close()

            # Cleanup
            subprocess.run(['dropdb', '-h', 'localhost', '-U', 'postgres', temp_db])

            integrity_ok = len(errors) == 0
            return (integrity_ok, errors)

        except Exception as e:
            logger.exception("data_integrity_check_error", error=str(e))
            errors.append(f"Data integrity check exception: {str(e)}")
            return (False, errors)

    async def validate_all_backups(self) -> List[BackupValidationResult]:
        """
        Validate all backups in backup directory.

        Returns:
            List of BackupValidationResult
        """
        results = []

        backup_files = sorted(
            self.backup_dir.glob("*.dump"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        logger.info("validating_all_backups", backup_count=len(backup_files))

        for backup_file in backup_files:
            result = await self.validate_backup(backup_file)
            results.append(result)

        return results

    def generate_report(self, results: List[BackupValidationResult]) -> str:
        """
        Generate backup validation report.

        Args:
            results: List of validation results

        Returns:
            Report as formatted string
        """
        report_lines = [
            "# Backup Validation Report",
            f"Generated: {datetime.utcnow().isoformat()}",
            f"Total Backups: {len(results)}",
            ""
        ]

        valid_count = sum(1 for r in results if r.is_valid)
        report_lines.append(f"Valid Backups: {valid_count}/{len(results)}")
        report_lines.append("")

        for result in results:
            status = "✅ VALID" if result.is_valid else "❌ INVALID"
            report_lines.append(f"## {result.backup_file}")
            report_lines.append(f"Status: {status}")
            report_lines.append(f"Checksum: {'✅' if result.checksum_verified else '❌'}")
            report_lines.append(f"Restoration: {'✅' if result.restoration_tested else '❌'}")
            report_lines.append(f"Data Integrity: {'✅' if result.data_integrity_ok else '❌'}")

            if result.errors:
                report_lines.append("\nErrors:")
                for error in result.errors:
                    report_lines.append(f"  - {error}")

            if result.warnings:
                report_lines.append("\nWarnings:")
                for warning in result.warnings:
                    report_lines.append(f"  - {warning}")

            report_lines.append("")

        return "\n".join(report_lines)


async def main():
    """Main entry point for backup validation."""
    import os

    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ablage")
    backup_dir = Path(os.getenv("BACKUP_DIR", "/backups/postgresql"))

    validator = BackupValidator(db_url, backup_dir)

    # Validate all backups
    results = await validator.validate_all_backups()

    # Generate report
    report = validator.generate_report(results)
    print(report)

    # Save report to file
    report_file = backup_dir / f"validation_report_{datetime.utcnow().strftime('%Y%m%d')}.md"
    report_file.write_text(report)
    print(f"\nReport saved to: {report_file}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

"""
Data Migration Runner - Safe database migration execution for Ablage-System.

This runner provides comprehensive database migration capabilities with:
- Pre-migration validation and health checks
- Automatic backup before migration
- Dry-run mode for testing
- Rollback on failure
- PostgreSQL-specific optimizations
- GDPR compliance tracking
- Progress monitoring and logging

Author: Ablage-System Team
Version: 1.0.0
Last Updated: 2025-11-22
"""

import os
import sys
import time
import asyncio
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field

import asyncpg
import structlog
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class MigrationConfig:
    """Configuration for migration runner."""

    # Database connection
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "ablage"
    db_user: str = "postgres"
    db_password: str = ""

    # Migration settings
    alembic_config_path: str = "alembic.ini"
    migrations_dir: str = "migrations"
    backup_dir: str = "/var/backups/ablage"

    # Safety settings
    require_backup: bool = True
    require_confirmation: bool = True
    max_migration_time_minutes: int = 60
    allow_data_loss: bool = False

    # GDPR compliance
    log_schema_changes: bool = True
    retention_policy_days: int = 2555  # 7 years for audit

    def get_db_url(self) -> str:
        """Get database connection URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    def get_async_db_url(self) -> str:
        """Get async database connection URL."""
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


@dataclass
class MigrationResult:
    """Result of a migration execution."""

    success: bool
    revision: str
    description: str
    execution_time_seconds: float
    backup_path: Optional[str] = None
    rows_affected: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    rollback_performed: bool = False


# ============================================================================
# Database Health Checker
# ============================================================================

class DatabaseHealthChecker:
    """Check database health before migration."""

    def __init__(self, config: MigrationConfig):
        self.config = config

    async def check_connection(self) -> Tuple[bool, str]:
        """Check database connectivity.

        Returns:
            Tuple of (success, message)
        """
        try:
            conn = await asyncpg.connect(
                host=self.config.db_host,
                port=self.config.db_port,
                database=self.config.db_name,
                user=self.config.db_user,
                password=self.config.db_password,
                timeout=10
            )
            await conn.close()
            return True, "Datenbankverbindung erfolgreich"
        except Exception as e:
            return False, f"Verbindungsfehler: {str(e)}"

    async def check_disk_space(self, min_free_gb: float = 1.0) -> Tuple[bool, str]:
        """Check available disk space.

        Args:
            min_free_gb: Minimum free space in GB

        Returns:
            Tuple of (success, message)
        """
        try:
            import shutil
            stat = shutil.disk_usage(self.config.backup_dir)
            free_gb = stat.free / (1024 ** 3)

            if free_gb < min_free_gb:
                return False, f"Nicht genügend Speicherplatz: {free_gb:.2f} GB (min {min_free_gb} GB)"

            return True, f"Speicherplatz verfügbar: {free_gb:.2f} GB"
        except Exception as e:
            return False, f"Fehler beim Prüfen des Speicherplatzes: {str(e)}"

    async def check_active_connections(self, max_connections: int = 50) -> Tuple[bool, str]:
        """Check number of active database connections.

        Args:
            max_connections: Maximum allowed active connections

        Returns:
            Tuple of (success, message)
        """
        try:
            conn = await asyncpg.connect(
                host=self.config.db_host,
                port=self.config.db_port,
                database=self.config.db_name,
                user=self.config.db_user,
                password=self.config.db_password
            )

            result = await conn.fetchval("""
                SELECT count(*)
                FROM pg_stat_activity
                WHERE datname = $1 AND state = 'active'
            """, self.config.db_name)

            await conn.close()

            if result > max_connections:
                return False, f"Zu viele aktive Verbindungen: {result} (max {max_connections})"

            return True, f"Aktive Verbindungen: {result}"
        except Exception as e:
            return False, f"Fehler beim Prüfen der Verbindungen: {str(e)}"

    async def check_locks(self) -> Tuple[bool, str]:
        """Check for active table locks.

        Returns:
            Tuple of (success, message)
        """
        try:
            conn = await asyncpg.connect(
                host=self.config.db_host,
                port=self.config.db_port,
                database=self.config.db_name,
                user=self.config.db_user,
                password=self.config.db_password
            )

            result = await conn.fetch("""
                SELECT
                    locktype,
                    relation::regclass,
                    mode,
                    granted
                FROM pg_locks
                WHERE NOT granted
                AND database = (SELECT oid FROM pg_database WHERE datname = $1)
            """, self.config.db_name)

            await conn.close()

            if result:
                locks = [f"{r['relation']} ({r['mode']})" for r in result]
                return False, f"Aktive Locks gefunden: {', '.join(locks)}"

            return True, "Keine Locks vorhanden"
        except Exception as e:
            return False, f"Fehler beim Prüfen der Locks: {str(e)}"

    async def run_all_checks(self) -> Tuple[bool, List[str]]:
        """Run all health checks.

        Returns:
            Tuple of (all_passed, messages)
        """
        checks = [
            ("Verbindung", self.check_connection()),
            ("Speicherplatz", self.check_disk_space()),
            ("Aktive Verbindungen", self.check_active_connections()),
            ("Locks", self.check_locks())
        ]

        results = []
        all_passed = True

        for name, check_coro in checks:
            success, message = await check_coro
            status = "✓" if success else "✗"
            results.append(f"{status} {name}: {message}")

            if not success:
                all_passed = False
                logger.warning("health_check_failed", check=name, message=message)
            else:
                logger.info("health_check_passed", check=name)

        return all_passed, results


# ============================================================================
# Backup Manager
# ============================================================================

class BackupManager:
    """Manage database backups before migration."""

    def __init__(self, config: MigrationConfig):
        self.config = config

    def _get_backup_filename(self) -> str:
        """Generate backup filename with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"ablage_pre_migration_{timestamp}.dump"

    async def create_backup(self) -> Tuple[bool, str, Optional[str]]:
        """Create database backup using pg_dump.

        Returns:
            Tuple of (success, message, backup_path)
        """
        backup_dir = Path(self.config.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_filename = self._get_backup_filename()
        backup_path = backup_dir / backup_filename

        logger.info("creating_backup", path=str(backup_path))

        try:
            # Use pg_dump with custom format for best compression
            cmd = [
                "pg_dump",
                "-h", self.config.db_host,
                "-p", str(self.config.db_port),
                "-U", self.config.db_user,
                "-d", self.config.db_name,
                "-Fc",  # Custom format (compressed)
                "-f", str(backup_path),
                "--verbose"
            ]

            # Set password via environment variable
            env = os.environ.copy()
            env["PGPASSWORD"] = self.config.db_password

            start_time = time.time()

            process = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )

            elapsed = time.time() - start_time

            if process.returncode != 0:
                logger.error("backup_failed", stderr=process.stderr)
                return False, f"Backup fehlgeschlagen: {process.stderr}", None

            # Verify backup file exists and has reasonable size
            if not backup_path.exists():
                return False, "Backup-Datei wurde nicht erstellt", None

            size_mb = backup_path.stat().st_size / (1024 * 1024)

            if size_mb < 0.1:
                return False, f"Backup-Datei zu klein: {size_mb:.2f} MB", None

            logger.info(
                "backup_created",
                path=str(backup_path),
                size_mb=size_mb,
                duration_seconds=elapsed
            )

            return True, f"Backup erstellt: {backup_filename} ({size_mb:.2f} MB, {elapsed:.1f}s)", str(backup_path)

        except subprocess.TimeoutExpired:
            return False, "Backup-Timeout (>10 Minuten)", None
        except Exception as e:
            logger.exception("backup_error")
            return False, f"Backup-Fehler: {str(e)}", None

    async def restore_backup(self, backup_path: str) -> Tuple[bool, str]:
        """Restore database from backup.

        Args:
            backup_path: Path to backup file

        Returns:
            Tuple of (success, message)
        """
        logger.warning("restoring_backup", path=backup_path)

        try:
            # Drop and recreate database
            logger.info("dropping_database")

            # Use pg_restore
            cmd = [
                "pg_restore",
                "-h", self.config.db_host,
                "-p", str(self.config.db_port),
                "-U", self.config.db_user,
                "-d", self.config.db_name,
                "--clean",  # Drop objects before restoring
                "--if-exists",  # Don't fail if objects don't exist
                "--verbose",
                backup_path
            ]

            env = os.environ.copy()
            env["PGPASSWORD"] = self.config.db_password

            start_time = time.time()

            process = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600
            )

            elapsed = time.time() - start_time

            if process.returncode != 0:
                logger.error("restore_failed", stderr=process.stderr)
                return False, f"Wiederherstellung fehlgeschlagen: {process.stderr}"

            logger.info(
                "backup_restored",
                path=backup_path,
                duration_seconds=elapsed
            )

            return True, f"Backup wiederhergestellt ({elapsed:.1f}s)"

        except subprocess.TimeoutExpired:
            return False, "Wiederherstellungs-Timeout (>10 Minuten)"
        except Exception as e:
            logger.exception("restore_error")
            return False, f"Wiederherstellungs-Fehler: {str(e)}"


# ============================================================================
# Migration Runner
# ============================================================================

class MigrationRunner:
    """Execute Alembic database migrations with safety checks."""

    def __init__(self, config: MigrationConfig):
        self.config = config
        self.health_checker = DatabaseHealthChecker(config)
        self.backup_manager = BackupManager(config)

    def _get_alembic_config(self) -> Config:
        """Get Alembic configuration."""
        alembic_cfg = Config(self.config.alembic_config_path)
        alembic_cfg.set_main_option("sqlalchemy.url", self.config.get_db_url())
        return alembic_cfg

    async def get_current_revision(self) -> Optional[str]:
        """Get current database revision.

        Returns:
            Current revision or None if no migrations applied
        """
        try:
            conn = await asyncpg.connect(
                host=self.config.db_host,
                port=self.config.db_port,
                database=self.config.db_name,
                user=self.config.db_user,
                password=self.config.db_password
            )

            # Check if alembic_version table exists
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'alembic_version'
                )
            """)

            if not table_exists:
                await conn.close()
                return None

            # Get current version
            version = await conn.fetchval("SELECT version_num FROM alembic_version")
            await conn.close()

            return version

        except Exception as e:
            logger.error("failed_to_get_revision", error=str(e))
            return None

    def get_pending_migrations(self) -> List[Dict[str, Any]]:
        """Get list of pending migrations.

        Returns:
            List of migration info dicts
        """
        alembic_cfg = self._get_alembic_config()
        script = ScriptDirectory.from_config(alembic_cfg)

        current = asyncio.run(self.get_current_revision())

        pending = []
        for revision in script.iterate_revisions(current, "heads"):
            if current is None or revision.revision != current:
                pending.append({
                    "revision": revision.revision,
                    "down_revision": revision.down_revision,
                    "description": revision.doc or "No description",
                    "module_path": revision.module.__file__ if revision.module else None
                })

        return list(reversed(pending))  # Oldest first

    async def run_migration(
        self,
        target_revision: str = "head",
        dry_run: bool = False
    ) -> MigrationResult:
        """Run database migration.

        Args:
            target_revision: Target revision (default: "head")
            dry_run: If True, only show what would be done

        Returns:
            MigrationResult with execution details
        """
        start_time = time.time()
        backup_path = None
        rollback_performed = False
        warnings = []
        errors = []

        logger.info(
            "migration_started",
            target=target_revision,
            dry_run=dry_run
        )

        try:
            # Step 1: Health checks
            logger.info("running_health_checks")
            checks_passed, check_messages = await self.health_checker.run_all_checks()

            for msg in check_messages:
                print(msg)

            if not checks_passed:
                errors.append("Health checks fehlgeschlagen")
                return MigrationResult(
                    success=False,
                    revision="",
                    description="Health checks failed",
                    execution_time_seconds=time.time() - start_time,
                    errors=errors
                )

            # Step 2: Get current and pending migrations
            current_rev = await self.get_current_revision()
            pending = self.get_pending_migrations()

            logger.info(
                "migration_info",
                current_revision=current_rev,
                pending_count=len(pending)
            )

            if not pending:
                return MigrationResult(
                    success=True,
                    revision=current_rev or "",
                    description="Keine ausstehenden Migrationen",
                    execution_time_seconds=time.time() - start_time
                )

            # Print pending migrations
            print(f"\n{len(pending)} ausstehende Migration(en):")
            for mig in pending:
                print(f"  - {mig['revision'][:8]}: {mig['description']}")

            if dry_run:
                print("\n[DRY RUN] Migration würde ausgeführt werden")
                return MigrationResult(
                    success=True,
                    revision=pending[-1]["revision"],
                    description=f"Dry run: {len(pending)} migrations",
                    execution_time_seconds=time.time() - start_time,
                    warnings=["Dry run - keine Änderungen vorgenommen"]
                )

            # Step 3: Confirmation
            if self.config.require_confirmation:
                response = input("\nMigration durchführen? (ja/nein): ")
                if response.lower() not in ["ja", "yes", "y"]:
                    return MigrationResult(
                        success=False,
                        revision="",
                        description="Migration abgebrochen durch Benutzer",
                        execution_time_seconds=time.time() - start_time,
                        warnings=["Von Benutzer abgebrochen"]
                    )

            # Step 4: Create backup
            if self.config.require_backup:
                print("\nErstelle Backup...")
                backup_success, backup_msg, backup_path = await self.backup_manager.create_backup()
                print(backup_msg)

                if not backup_success:
                    errors.append(f"Backup fehlgeschlagen: {backup_msg}")
                    return MigrationResult(
                        success=False,
                        revision="",
                        description="Backup failed",
                        execution_time_seconds=time.time() - start_time,
                        errors=errors
                    )

            # Step 5: Run migration
            print("\nFühre Migration durch...")
            alembic_cfg = self._get_alembic_config()

            try:
                command.upgrade(alembic_cfg, target_revision)
                print("✓ Migration erfolgreich")

            except Exception as e:
                logger.exception("migration_failed")
                errors.append(f"Migration fehlgeschlagen: {str(e)}")

                # Rollback if backup exists
                if backup_path and self.config.require_backup:
                    print("\n⚠ Führe Rollback durch...")
                    restore_success, restore_msg = await self.backup_manager.restore_backup(backup_path)
                    print(restore_msg)

                    if restore_success:
                        rollback_performed = True
                        warnings.append("Rollback erfolgreich")
                    else:
                        errors.append(f"Rollback fehlgeschlagen: {restore_msg}")

                return MigrationResult(
                    success=False,
                    revision="",
                    description="Migration failed",
                    execution_time_seconds=time.time() - start_time,
                    backup_path=backup_path,
                    errors=errors,
                    warnings=warnings,
                    rollback_performed=rollback_performed
                )

            # Step 6: Verify migration
            new_rev = await self.get_current_revision()
            logger.info(
                "migration_completed",
                old_revision=current_rev,
                new_revision=new_rev,
                duration_seconds=time.time() - start_time
            )

            return MigrationResult(
                success=True,
                revision=new_rev or "",
                description=f"Migrated from {current_rev} to {new_rev}",
                execution_time_seconds=time.time() - start_time,
                backup_path=backup_path,
                warnings=warnings
            )

        except Exception as e:
            logger.exception("migration_runner_error")
            errors.append(f"Unerwarteter Fehler: {str(e)}")

            return MigrationResult(
                success=False,
                revision="",
                description="Unexpected error",
                execution_time_seconds=time.time() - start_time,
                backup_path=backup_path,
                errors=errors,
                rollback_performed=rollback_performed
            )


# ============================================================================
# CLI Interface
# ============================================================================

def print_banner():
    """Print application banner."""
    print("=" * 70)
    print("  Ablage-System Database Migration Runner")
    print("  Sichere Datenbankmigrationen mit automatischem Backup")
    print("=" * 70)
    print()


async def main():
    """Main CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ablage-System Database Migration Runner"
    )
    parser.add_argument(
        "--target",
        default="head",
        help="Target revision (default: head)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup creation (not recommended)"
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--db-host",
        default="localhost",
        help="Database host"
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=5432,
        help="Database port"
    )
    parser.add_argument(
        "--db-name",
        default="ablage",
        help="Database name"
    )
    parser.add_argument(
        "--db-user",
        default="postgres",
        help="Database user"
    )

    args = parser.parse_args()

    print_banner()

    # Get password from environment or prompt
    db_password = os.environ.get("POSTGRES_PASSWORD", "")
    if not db_password:
        import getpass
        db_password = getpass.getpass("Database password: ")

    # Create configuration
    config = MigrationConfig(
        db_host=args.db_host,
        db_port=args.db_port,
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=db_password,
        require_backup=not args.no_backup,
        require_confirmation=not args.no_confirm
    )

    # Run migration
    runner = MigrationRunner(config)
    result = await runner.run_migration(
        target_revision=args.target,
        dry_run=args.dry_run
    )

    # Print results
    print("\n" + "=" * 70)
    print("Migration Results:")
    print("=" * 70)
    print(f"Status: {'✓ Erfolgreich' if result.success else '✗ Fehlgeschlagen'}")
    print(f"Revision: {result.revision}")
    print(f"Dauer: {result.execution_time_seconds:.2f}s")

    if result.backup_path:
        print(f"Backup: {result.backup_path}")

    if result.rollback_performed:
        print("⚠ Rollback durchgeführt")

    if result.warnings:
        print("\nWarnungen:")
        for warning in result.warnings:
            print(f"  - {warning}")

    if result.errors:
        print("\nFehler:")
        for error in result.errors:
            print(f"  - {error}")

    print("=" * 70)

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    asyncio.run(main())

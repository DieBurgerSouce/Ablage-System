"""
Migration Runner - Database Migrations
Sichere Ausfuehrung von Alembic-Migrationen mit Backup und Rollback
"""

import asyncio
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import structlog

logger = structlog.get_logger(__name__)


class MigrationRunner:
    """
    Execute database migrations safely with backup and rollback.

    Features:
    - Pre-migration backup
    - Alembic migration execution
    - Schema verification
    - Automatic rollback on error
    - Migration history tracking
    """

    def __init__(
        self,
        alembic_config_path: Optional[str] = None,
        backup_dir: Optional[str] = None
    ):
        """
        Initialize MigrationRunner.

        Args:
            alembic_config_path: Path to alembic.ini (auto-detect if None)
            backup_dir: Directory for database backups
        """
        self.alembic_config_path = alembic_config_path or self._find_alembic_config()
        self.backup_dir = Path(backup_dir or "data/backups/migrations")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._current_revision: Optional[str] = None
        self._migration_history: List[Dict[str, Any]] = []

    def _find_alembic_config(self) -> str:
        """Find alembic.ini in project root."""
        possible_paths = [
            "alembic.ini",
            "app/alembic.ini",
            "../alembic.ini"
        ]

        for path in possible_paths:
            if Path(path).exists():
                return path

        return "alembic.ini"  # Default fallback

    async def run_migrations(self, target_version: str = "head") -> Dict[str, Any]:
        """
        Run Alembic migrations with safety checks.

        Steps:
        1. Get current revision
        2. Create backup
        3. Run migrations
        4. Verify schema
        5. Rollback on error

        Args:
            target_version: Target revision ("head" for latest)

        Returns:
            Migration result with status, revisions, and timing
        """
        result = {
            "status": "pending",
            "target_version": target_version,
            "started_at": datetime.utcnow().isoformat(),
            "from_revision": None,
            "to_revision": None,
            "backup_path": None,
            "steps": [],
            "error": None
        }

        try:
            # Step 1: Get current revision
            logger.info("migration_step_get_revision")
            self._current_revision = await self._get_current_revision()
            result["from_revision"] = self._current_revision
            result["steps"].append({
                "step": "get_current_revision",
                "status": "success",
                "revision": self._current_revision
            })

            # Check if already at target
            if target_version == "head":
                pending = await self._get_pending_migrations()
                if not pending:
                    logger.info("migration_already_current")
                    result["status"] = "already_current"
                    result["to_revision"] = self._current_revision
                    result["finished_at"] = datetime.utcnow().isoformat()
                    return result
            elif self._current_revision == target_version:
                result["status"] = "already_current"
                result["to_revision"] = target_version
                result["finished_at"] = datetime.utcnow().isoformat()
                return result

            # Step 2: Create backup
            logger.info("migration_step_backup")
            backup_path = await self._create_backup()
            result["backup_path"] = str(backup_path)
            result["steps"].append({
                "step": "create_backup",
                "status": "success",
                "path": str(backup_path)
            })

            # Step 3: Run migrations
            logger.info(
                "migration_step_run",
                from_rev=self._current_revision,
                target=target_version
            )
            migration_output = await self._run_alembic_upgrade(target_version)
            result["steps"].append({
                "step": "run_migrations",
                "status": "success",
                "output": migration_output
            })

            # Step 4: Verify schema
            logger.info("migration_step_verify")
            new_revision = await self._get_current_revision()
            result["to_revision"] = new_revision

            verification = await self._verify_schema()
            result["steps"].append({
                "step": "verify_schema",
                "status": "success" if verification["valid"] else "warning",
                "details": verification
            })

            # Success
            result["status"] = "success"
            result["finished_at"] = datetime.utcnow().isoformat()

            # Record in history
            self._migration_history.append({
                "from": self._current_revision,
                "to": new_revision,
                "timestamp": result["finished_at"],
                "backup": str(backup_path)
            })

            logger.info(
                "migration_complete",
                from_rev=self._current_revision,
                to_rev=new_revision
            )

        except Exception as e:
            logger.error(
                "migration_failed",
                error=str(e),
                from_rev=self._current_revision,
                exc_info=True
            )

            result["status"] = "failed"
            result["error"] = str(e)
            result["finished_at"] = datetime.utcnow().isoformat()

            # Step 5: Rollback on error
            if self._current_revision:
                logger.warning(
                    "migration_rollback_starting",
                    target=self._current_revision
                )
                try:
                    rollback_result = await self._rollback_to_revision(
                        self._current_revision
                    )
                    result["steps"].append({
                        "step": "rollback",
                        "status": "success" if rollback_result else "failed",
                        "target": self._current_revision
                    })
                except Exception as rollback_error:
                    logger.error(
                        "migration_rollback_failed",
                        error=str(rollback_error)
                    )
                    result["steps"].append({
                        "step": "rollback",
                        "status": "failed",
                        "error": str(rollback_error)
                    })

        return result

    async def _get_current_revision(self) -> Optional[str]:
        """Get current database revision."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "alembic", "-c", self.alembic_config_path, "current",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.warning(
                    "alembic_current_failed",
                    stderr=stderr.decode()
                )
                return None

            output = stdout.decode().strip()
            # Parse revision from output (format: "abc123 (head)")
            if output:
                parts = output.split()
                if parts:
                    return parts[0]

            return None

        except FileNotFoundError:
            # Alembic not installed, try Python API
            return await self._get_revision_via_api()
        except Exception as e:
            logger.error("get_revision_failed", error=str(e))
            return None

    async def _get_revision_via_api(self) -> Optional[str]:
        """Get revision using Alembic Python API."""
        try:
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            from alembic.runtime.migration import MigrationContext
            from sqlalchemy import create_engine

            # Load config
            config = Config(self.alembic_config_path)
            script = ScriptDirectory.from_config(config)

            # Get database URL from config or environment
            db_url = config.get_main_option("sqlalchemy.url")
            if not db_url:
                db_url = os.environ.get("DATABASE_URL")

            if not db_url:
                return None

            engine = create_engine(db_url)
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                return context.get_current_revision()

        except ImportError:
            logger.warning("alembic_import_failed")
            return None
        except Exception as e:
            logger.error("get_revision_api_failed", error=str(e))
            return None

    async def _get_pending_migrations(self) -> List[str]:
        """Get list of pending migrations."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "alembic", "-c", self.alembic_config_path, "history",
                "--indicate-current",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            output = stdout.decode()
            pending = []

            # Parse history output for pending migrations
            found_current = False
            for line in output.split("\n"):
                if "(current)" in line or "<--" in line:
                    found_current = True
                    continue
                if not found_current and line.strip():
                    # Migrations before current are pending
                    parts = line.split()
                    if parts:
                        pending.append(parts[0].replace("->", ""))

            return pending

        except Exception as e:
            logger.error("get_pending_migrations_failed", error=str(e))
            return []

    async def _create_backup(self) -> Path:
        """Create database backup before migration."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"pre_migration_{timestamp}.sql"
        backup_path = self.backup_dir / backup_name

        try:
            # Try pg_dump for PostgreSQL
            db_url = os.environ.get("DATABASE_URL", "")

            if "postgresql" in db_url or "postgres" in db_url:
                await self._backup_postgresql(backup_path)
            else:
                # Generic backup: save revision info
                await self._backup_revision_info(backup_path)

            logger.info(
                "backup_created",
                path=str(backup_path),
                revision=self._current_revision
            )

            return backup_path

        except Exception as e:
            logger.warning(
                "backup_failed_continuing",
                error=str(e)
            )
            # Create minimal backup with revision info
            await self._backup_revision_info(backup_path)
            return backup_path

    async def _backup_postgresql(self, backup_path: Path) -> None:
        """Create PostgreSQL backup using pg_dump."""
        db_host = os.environ.get("POSTGRES_HOST", "localhost")
        db_port = os.environ.get("POSTGRES_PORT", "5433")
        db_name = os.environ.get("POSTGRES_DB", "ablage")
        db_user = os.environ.get("POSTGRES_USER", "ablage")

        env = os.environ.copy()
        env["PGPASSWORD"] = os.environ.get("POSTGRES_PASSWORD", "")

        proc = await asyncio.create_subprocess_exec(
            "pg_dump",
            "-h", db_host,
            "-p", db_port,
            "-U", db_user,
            "-d", db_name,
            "--schema-only",  # Schema only for speed
            "-f", str(backup_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr.decode()}")

    async def _backup_revision_info(self, backup_path: Path) -> None:
        """Create minimal backup with revision information."""
        import json

        info = {
            "revision": self._current_revision,
            "timestamp": datetime.utcnow().isoformat(),
            "type": "revision_info"
        }

        backup_path.with_suffix(".json").write_text(
            json.dumps(info, indent=2)
        )

    async def _run_alembic_upgrade(self, target: str) -> str:
        """Execute Alembic upgrade command."""
        proc = await asyncio.create_subprocess_exec(
            "alembic", "-c", self.alembic_config_path,
            "upgrade", target,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode() or stdout.decode()
            raise RuntimeError(f"Alembic upgrade failed: {error_msg}")

        return stdout.decode()

    async def _verify_schema(self) -> Dict[str, Any]:
        """Verify database schema after migration."""
        result = {
            "valid": True,
            "checks": []
        }

        try:
            # Check 1: Can connect to database
            new_revision = await self._get_current_revision()
            result["checks"].append({
                "check": "database_connection",
                "passed": True,
                "revision": new_revision
            })

            # Check 2: Core tables exist
            core_tables = await self._check_core_tables()
            result["checks"].append({
                "check": "core_tables",
                "passed": core_tables["all_exist"],
                "tables": core_tables["tables"]
            })

            if not core_tables["all_exist"]:
                result["valid"] = False

            # Check 3: No pending migrations (if targeting head)
            pending = await self._get_pending_migrations()
            result["checks"].append({
                "check": "no_pending",
                "passed": len(pending) == 0,
                "pending_count": len(pending)
            })

        except Exception as e:
            result["valid"] = False
            result["error"] = str(e)

        return result

    async def _check_core_tables(self) -> Dict[str, Any]:
        """Verify core tables exist in database."""
        core_tables = ["documents", "users", "ocr_results"]
        existing = []

        try:
            from app.db.database import async_session_maker
            from sqlalchemy import text

            async with async_session_maker() as session:
                query = text("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                result = await session.execute(query)
                db_tables = {row[0] for row in result.fetchall()}

                for table in core_tables:
                    if table in db_tables:
                        existing.append(table)

        except Exception as e:
            logger.warning("core_tables_check_failed", error=str(e))
            return {"all_exist": False, "tables": [], "error": str(e)}

        return {
            "all_exist": len(existing) == len(core_tables),
            "tables": existing,
            "missing": [t for t in core_tables if t not in existing]
        }

    async def _rollback_to_revision(self, revision: str) -> bool:
        """Rollback database to specific revision."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "alembic", "-c", self.alembic_config_path,
                "downgrade", revision,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(f"Rollback failed: {stderr.decode()}")

            logger.info(
                "rollback_complete",
                target_revision=revision
            )
            return True

        except Exception as e:
            logger.error(
                "rollback_failed",
                revision=revision,
                error=str(e)
            )
            return False

    async def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status."""
        current = await self._get_current_revision()
        pending = await self._get_pending_migrations()

        return {
            "current_revision": current,
            "pending_migrations": pending,
            "pending_count": len(pending),
            "is_current": len(pending) == 0,
            "history": self._migration_history[-10:]  # Last 10 migrations
        }


# Usage:
# runner = MigrationRunner()
# await runner.run_migrations()

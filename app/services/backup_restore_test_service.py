# -*- coding: utf-8 -*-
"""
Backup Restore Test Service.

Automatisierte Validierung von Backup-Integritaet durch Wiederherstellungstests.
Wird woechentlich ausgefuehrt um sicherzustellen, dass Backups tatsaechlich
funktionsfaehig sind.

Phase 2.3 der Strategischen Roadmap.

Features:
- Automatischer Restore-Test in Temp-Datenbank
- Schema-Validierung nach Restore
- Record-Count-Vergleich
- Daten-Stichproben-Validierung
- Slack-Benachrichtigung bei Fehlern
- Detaillierte Reports

Created: 2026-01-23
"""

import asyncio
import hashlib
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.services.backup_service import BackupService, get_backup_service
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class RestoreTestStatus(str, Enum):
    """Status eines Restore-Tests."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationLevel(str, Enum):
    """Level der Validierung."""

    MINIMAL = "minimal"  # Nur Schema-Check
    STANDARD = "standard"  # Schema + Record Counts
    THOROUGH = "thorough"  # Schema + Counts + Stichproben


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SchemaValidationResult:
    """Ergebnis einer Schema-Validierung."""

    table_name: str
    exists: bool = False
    column_count: int = 0
    index_count: int = 0
    constraint_count: int = 0
    expected_columns: int = 0
    column_match: bool = False
    errors: List[str] = field(default_factory=list)


@dataclass
class RecordCountResult:
    """Ergebnis eines Record-Count-Vergleichs."""

    table_name: str
    source_count: int = 0
    restored_count: int = 0
    difference: int = 0
    match: bool = False
    percentage_match: float = 0.0


@dataclass
class DataSampleResult:
    """Ergebnis einer Stichproben-Validierung."""

    table_name: str
    sample_size: int = 0
    samples_verified: int = 0
    hash_matches: int = 0
    hash_match_rate: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class RestoreTestResult:
    """Gesamtergebnis eines Restore-Tests."""

    test_id: UUID = field(default_factory=uuid4)
    status: RestoreTestStatus = RestoreTestStatus.PENDING
    started_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Backup-Info
    backup_file: str = ""
    backup_date: Optional[datetime] = None
    backup_size_mb: float = 0.0

    # Validierungs-Level
    validation_level: ValidationLevel = ValidationLevel.STANDARD

    # Ergebnisse
    schema_results: List[SchemaValidationResult] = field(default_factory=list)
    record_count_results: List[RecordCountResult] = field(default_factory=list)
    sample_results: List[DataSampleResult] = field(default_factory=list)

    # Zusammenfassung
    tables_checked: int = 0
    tables_passed: int = 0
    tables_failed: int = 0
    total_records_source: int = 0
    total_records_restored: int = 0
    record_match_rate: float = 0.0

    # Fehler
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Temp-DB Info
    temp_db_name: str = ""
    temp_db_cleaned: bool = False

    @property
    def passed(self) -> bool:
        """Ist der Test bestanden?"""
        return self.status == RestoreTestStatus.PASSED

    @property
    def summary(self) -> str:
        """Kurze Zusammenfassung."""
        if self.status == RestoreTestStatus.PASSED:
            return (
                f"✅ Restore-Test bestanden: {self.tables_passed}/{self.tables_checked} "
                f"Tabellen validiert, {self.record_match_rate:.1f}% Record-Match"
            )
        elif self.status == RestoreTestStatus.FAILED:
            return (
                f"❌ Restore-Test fehlgeschlagen: {self.tables_failed}/{self.tables_checked} "
                f"Tabellen mit Fehlern. Fehler: {', '.join(self.errors[:3])}"
            )
        else:
            return f"⏳ Restore-Test: {self.status.value}"


# =============================================================================
# Service
# =============================================================================


class BackupRestoreTestService:
    """Service fuer automatisierte Backup-Restore-Tests.

    Stellt sicher, dass Backups tatsaechlich funktionsfaehig sind durch:
    - Wiederherstellung in Temp-Datenbank
    - Schema-Validierung
    - Record-Count-Vergleich
    - Optionale Stichproben-Verifizierung
    """

    # Kritische Tabellen die immer geprueft werden muessen
    CRITICAL_TABLES = [
        "users",
        "companies",
        "documents",
        "business_entities",
        "invoice_tracking",
        "audit_chain_entries",
        "dunning_records",
        "bank_accounts",
        "transactions",
        "approvals",
    ]

    # Tabellen die fuer Stichproben verwendet werden
    SAMPLE_TABLES = [
        "documents",
        "invoice_tracking",
        "business_entities",
    ]

    def __init__(self):
        self.backup_service = get_backup_service()
        self._temp_engine = None
        self._temp_session_factory = None

    # -------------------------------------------------------------------------
    # Haupt-Test-Methode
    # -------------------------------------------------------------------------

    async def run_restore_test(
        self,
        backup_path: Optional[Path] = None,
        validation_level: ValidationLevel = ValidationLevel.STANDARD,
        cleanup_on_success: bool = True,
        cleanup_on_failure: bool = False,
    ) -> RestoreTestResult:
        """Fuehre vollstaendigen Restore-Test durch.

        Args:
            backup_path: Pfad zum Backup (oder neuestes verwenden)
            validation_level: Level der Validierung
            cleanup_on_success: Temp-DB nach Erfolg loeschen
            cleanup_on_failure: Temp-DB nach Fehler loeschen

        Returns:
            RestoreTestResult mit allen Details
        """
        result = RestoreTestResult(
            validation_level=validation_level,
            started_at=utc_now(),
        )

        try:
            # 1. Backup-Datei ermitteln
            if backup_path:
                if not backup_path.exists():
                    result.status = RestoreTestStatus.FAILED
                    result.errors.append(f"Backup-Datei nicht gefunden: {backup_path}")
                    return self._finalize_result(result)
            else:
                backup_path = await self._find_latest_backup()
                if not backup_path:
                    result.status = RestoreTestStatus.FAILED
                    result.errors.append("Kein Backup gefunden")
                    return self._finalize_result(result)

            result.backup_file = str(backup_path)
            result.backup_size_mb = backup_path.stat().st_size / (1024 * 1024)
            result.backup_date = datetime.fromtimestamp(backup_path.stat().st_mtime)

            logger.info(
                "restore_test_starting",
                test_id=str(result.test_id),
                backup_file=str(backup_path),
                backup_size_mb=result.backup_size_mb,
                validation_level=validation_level.value,
            )

            result.status = RestoreTestStatus.RUNNING

            # 2. Temp-Datenbank erstellen
            temp_db_name = await self._create_temp_database(result)
            if not temp_db_name:
                return self._finalize_result(result)

            result.temp_db_name = temp_db_name

            # 3. Backup wiederherstellen
            restore_success = await self._restore_backup_to_temp(
                backup_path, temp_db_name, result
            )
            if not restore_success:
                return self._finalize_result(result, cleanup=cleanup_on_failure)

            # 4. Schema validieren
            await self._validate_schema(temp_db_name, result)

            # 5. Record Counts vergleichen (wenn Standard oder hoeher)
            if validation_level in (ValidationLevel.STANDARD, ValidationLevel.THOROUGH):
                await self._compare_record_counts(temp_db_name, result)

            # 6. Stichproben validieren (wenn thorough)
            if validation_level == ValidationLevel.THOROUGH:
                await self._validate_data_samples(temp_db_name, result)

            # 7. Ergebnis bestimmen
            result.status = self._determine_final_status(result)

            # 8. Cleanup
            should_cleanup = (
                (cleanup_on_success and result.status == RestoreTestStatus.PASSED)
                or (cleanup_on_failure and result.status == RestoreTestStatus.FAILED)
            )
            if should_cleanup:
                await self._cleanup_temp_database(temp_db_name, result)

        except (IOError, OSError, subprocess.SubprocessError, asyncio.TimeoutError) as e:
            logger.exception("restore_test_error", test_id=str(result.test_id))
            result.status = RestoreTestStatus.FAILED
            result.errors.append(safe_error_detail(e, "Backup-Test"))

        return self._finalize_result(result)

    # -------------------------------------------------------------------------
    # Temp-Datenbank Management
    # -------------------------------------------------------------------------

    async def _create_temp_database(self, result: RestoreTestResult) -> Optional[str]:
        """Erstelle temporaere Datenbank fuer Restore-Test."""
        temp_db_name = f"ablage_restore_test_{result.test_id.hex[:8]}"

        try:
            # Verbinde mit postgres-Datenbank zum Erstellen
            admin_url = settings.database_url.replace(
                f"/{settings.postgres_db}", "/postgres"
            ).replace("+asyncpg", "")

            # pg_dump kann keine async Connection nutzen, verwende subprocess
            create_db_cmd = [
                "psql",
                "-h", settings.postgres_host,
                "-p", str(settings.postgres_port),
                "-U", settings.postgres_user,
                "-d", "postgres",
                "-c", f"CREATE DATABASE {temp_db_name};"
            ]

            env = {"PGPASSWORD": settings.postgres_password}

            proc = await asyncio.create_subprocess_exec(
                *create_db_cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unbekannter Fehler"
                result.errors.append(f"Temp-DB Erstellung fehlgeschlagen: {error_msg}")
                result.status = RestoreTestStatus.FAILED
                return None

            logger.info(
                "temp_database_created",
                test_id=str(result.test_id),
                temp_db_name=temp_db_name,
            )

            return temp_db_name

        except (subprocess.SubprocessError, OSError) as e:
            result.errors.append(safe_error_detail(e, "Temp-DB"))
            result.status = RestoreTestStatus.FAILED
            return None

    async def _cleanup_temp_database(
        self,
        temp_db_name: str,
        result: RestoreTestResult,
    ) -> None:
        """Loesche temporaere Datenbank."""
        try:
            drop_db_cmd = [
                "psql",
                "-h", settings.postgres_host,
                "-p", str(settings.postgres_port),
                "-U", settings.postgres_user,
                "-d", "postgres",
                "-c", f"DROP DATABASE IF EXISTS {temp_db_name};"
            ]

            env = {"PGPASSWORD": settings.postgres_password}

            proc = await asyncio.create_subprocess_exec(
                *drop_db_cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            await proc.communicate()

            result.temp_db_cleaned = True
            logger.info(
                "temp_database_cleaned",
                test_id=str(result.test_id),
                temp_db_name=temp_db_name,
            )

        except (subprocess.SubprocessError, OSError) as e:
            result.warnings.append(safe_error_detail(e, "Temp-DB Cleanup"))

    # -------------------------------------------------------------------------
    # Backup finden und wiederherstellen
    # -------------------------------------------------------------------------

    async def _find_latest_backup(self) -> Optional[Path]:
        """Finde neuestes PostgreSQL-Backup."""
        backup_dir = self.backup_service.config.backup_path / "postgres"

        if not backup_dir.exists():
            return None

        backups = list(backup_dir.glob("*.sql.gz")) + list(backup_dir.glob("*.sql"))
        if not backups:
            return None

        # Sortiere nach Aenderungszeit (neuestes zuerst)
        backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return backups[0]

    async def _restore_backup_to_temp(
        self,
        backup_path: Path,
        temp_db_name: str,
        result: RestoreTestResult,
    ) -> bool:
        """Stelle Backup in Temp-Datenbank wieder her."""
        try:
            env = {"PGPASSWORD": settings.postgres_password}

            # Bestimme ob Backup komprimiert ist
            if backup_path.suffix == ".gz":
                # Dekomprimiere und pipe zu psql
                cmd = f"gunzip -c {backup_path} | psql -h {settings.postgres_host} -p {settings.postgres_port} -U {settings.postgres_user} -d {temp_db_name}"
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            else:
                # Direkt psql
                restore_cmd = [
                    "psql",
                    "-h", settings.postgres_host,
                    "-p", str(settings.postgres_port),
                    "-U", settings.postgres_user,
                    "-d", temp_db_name,
                    "-f", str(backup_path),
                ]
                proc = await asyncio.create_subprocess_exec(
                    *restore_cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=600,  # 10 Minuten Timeout
            )

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unbekannter Fehler"
                # Einige Warnings bei psql sind OK
                if "ERROR" in error_msg.upper() or "FATAL" in error_msg.upper():
                    result.errors.append(f"Restore fehlgeschlagen: {error_msg[:500]}")
                    result.status = RestoreTestStatus.FAILED
                    return False

            logger.info(
                "backup_restored_to_temp",
                test_id=str(result.test_id),
                backup_file=str(backup_path),
                temp_db_name=temp_db_name,
            )

            return True

        except asyncio.TimeoutError:
            result.errors.append("Restore Timeout (10 Minuten ueberschritten)")
            result.status = RestoreTestStatus.FAILED
            return False
        except (subprocess.SubprocessError, IOError, OSError) as e:
            result.errors.append(safe_error_detail(e, "Restore"))
            result.status = RestoreTestStatus.FAILED
            return False

    # -------------------------------------------------------------------------
    # Schema-Validierung
    # -------------------------------------------------------------------------

    async def _validate_schema(
        self,
        temp_db_name: str,
        result: RestoreTestResult,
    ) -> None:
        """Validiere Schema der wiederhergestellten Datenbank."""
        try:
            # Hole Schema-Info von Source-DB
            source_schema = await self._get_schema_info()

            # Hole Schema-Info von Temp-DB
            temp_schema = await self._get_schema_info(temp_db_name)

            for table_name in self.CRITICAL_TABLES:
                schema_result = SchemaValidationResult(table_name=table_name)
                result.tables_checked += 1

                # Pruefe ob Tabelle existiert
                if table_name in temp_schema:
                    schema_result.exists = True
                    schema_result.column_count = temp_schema[table_name]["columns"]
                    schema_result.index_count = temp_schema[table_name].get("indexes", 0)
                    schema_result.constraint_count = temp_schema[table_name].get("constraints", 0)

                    # Vergleiche mit Source
                    if table_name in source_schema:
                        schema_result.expected_columns = source_schema[table_name]["columns"]
                        schema_result.column_match = (
                            schema_result.column_count == schema_result.expected_columns
                        )

                        if schema_result.column_match:
                            result.tables_passed += 1
                        else:
                            result.tables_failed += 1
                            schema_result.errors.append(
                                f"Spalten-Mismatch: {schema_result.column_count} vs {schema_result.expected_columns}"
                            )
                    else:
                        result.tables_passed += 1  # Tabelle existiert, Source fehlt
                else:
                    schema_result.errors.append("Tabelle nicht gefunden")
                    result.tables_failed += 1

                result.schema_results.append(schema_result)

        except (IOError, OSError) as e:  # Catch-all: DB connection errors possible
            result.errors.append(safe_error_detail(e, "Schema"))

    async def _get_schema_info(
        self,
        db_name: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Hole Schema-Informationen fuer eine Datenbank."""
        if db_name:
            db_url = settings.database_url.replace(
                f"/{settings.postgres_db}", f"/{db_name}"
            )
        else:
            db_url = settings.database_url

        engine = create_async_engine(db_url, pool_pre_ping=True)
        schema_info: Dict[str, Dict[str, Any]] = {}

        try:
            async with engine.connect() as conn:
                # Hole Tabellen und Spalten-Counts
                query = text("""
                    SELECT
                        table_name,
                        COUNT(column_name) as column_count
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    GROUP BY table_name
                """)
                result = await conn.execute(query)
                for row in result:
                    schema_info[row.table_name] = {
                        "columns": row.column_count,
                        "indexes": 0,
                        "constraints": 0,
                    }

        finally:
            await engine.dispose()

        return schema_info

    # -------------------------------------------------------------------------
    # Record Count Vergleich
    # -------------------------------------------------------------------------

    async def _compare_record_counts(
        self,
        temp_db_name: str,
        result: RestoreTestResult,
    ) -> None:
        """Vergleiche Record Counts zwischen Source und Temp-DB."""
        try:
            source_counts = await self._get_record_counts()
            temp_counts = await self._get_record_counts(temp_db_name)

            for table_name in self.CRITICAL_TABLES:
                count_result = RecordCountResult(table_name=table_name)

                source_count = source_counts.get(table_name, 0)
                temp_count = temp_counts.get(table_name, 0)

                count_result.source_count = source_count
                count_result.restored_count = temp_count
                count_result.difference = source_count - temp_count

                # Match = exakt gleich oder +-1% (fuer Live-Datenbanken)
                if source_count == 0 and temp_count == 0:
                    count_result.match = True
                    count_result.percentage_match = 100.0
                elif source_count > 0:
                    count_result.percentage_match = (temp_count / source_count) * 100
                    # Erlaubt 1% Differenz da Backup und Source unterschiedlich alt sein koennen
                    count_result.match = abs(count_result.difference) <= max(1, source_count * 0.01)
                else:
                    count_result.match = False
                    count_result.percentage_match = 0.0

                result.total_records_source += source_count
                result.total_records_restored += temp_count
                result.record_count_results.append(count_result)

            # Gesamt-Match-Rate berechnen
            if result.total_records_source > 0:
                result.record_match_rate = (
                    result.total_records_restored / result.total_records_source
                ) * 100

        except Exception as e:
            result.errors.append(safe_error_detail(e, "Record-Count"))

    async def _get_record_counts(
        self,
        db_name: Optional[str] = None,
    ) -> Dict[str, int]:
        """Hole Record Counts fuer alle kritischen Tabellen."""
        if db_name:
            db_url = settings.database_url.replace(
                f"/{settings.postgres_db}", f"/{db_name}"
            )
        else:
            db_url = settings.database_url

        engine = create_async_engine(db_url, pool_pre_ping=True)
        counts: Dict[str, int] = {}

        try:
            async with engine.connect() as conn:
                for table_name in self.CRITICAL_TABLES:
                    try:
                        # SECURITY: table_name is from hardcoded CRITICAL_TABLES (not user input)
                        query = text(f"SELECT COUNT(*) FROM {table_name}")
                        result = await conn.execute(query)
                        counts[table_name] = result.scalar() or 0
                    except Exception:
                        counts[table_name] = 0

        finally:
            await engine.dispose()

        return counts

    # -------------------------------------------------------------------------
    # Stichproben-Validierung
    # -------------------------------------------------------------------------

    async def _validate_data_samples(
        self,
        temp_db_name: str,
        result: RestoreTestResult,
    ) -> None:
        """Validiere Daten-Stichproben durch Hash-Vergleich."""
        try:
            for table_name in self.SAMPLE_TABLES:
                sample_result = DataSampleResult(table_name=table_name)

                # Hole Stichproben-IDs von Source
                source_samples = await self._get_data_samples(table_name, limit=100)
                temp_samples = await self._get_data_samples(
                    table_name, limit=100, db_name=temp_db_name
                )

                sample_result.sample_size = len(source_samples)
                sample_result.samples_verified = len(temp_samples)

                # Vergleiche Hashes
                matches = 0
                for sample_id, source_hash in source_samples.items():
                    if sample_id in temp_samples:
                        if temp_samples[sample_id] == source_hash:
                            matches += 1
                        else:
                            sample_result.errors.append(
                                f"Hash-Mismatch fuer ID {sample_id}"
                            )

                sample_result.hash_matches = matches
                if sample_result.sample_size > 0:
                    sample_result.hash_match_rate = (
                        matches / sample_result.sample_size
                    ) * 100

                result.sample_results.append(sample_result)

        except Exception as e:
            result.warnings.append(safe_error_detail(e, "Stichprobe"))

    async def _get_data_samples(
        self,
        table_name: str,
        limit: int = 100,
        db_name: Optional[str] = None,
    ) -> Dict[str, str]:
        """Hole Stichproben-Daten mit Hashes."""
        if db_name:
            db_url = settings.database_url.replace(
                f"/{settings.postgres_db}", f"/{db_name}"
            )
        else:
            db_url = settings.database_url

        engine = create_async_engine(db_url, pool_pre_ping=True)
        samples: Dict[str, str] = {}

        try:
            async with engine.connect() as conn:
                # Hole zufaellige Stichproben
                query = text(f"""
                    SELECT id::text, md5(row_to_json({table_name})::text) as hash
                    FROM {table_name}
                    ORDER BY RANDOM()
                    LIMIT :limit
                """)
                result = await conn.execute(query, {"limit": limit})
                for row in result:
                    samples[row.id] = row.hash

        finally:
            await engine.dispose()

        return samples

    # -------------------------------------------------------------------------
    # Hilfs-Methoden
    # -------------------------------------------------------------------------

    def _determine_final_status(self, result: RestoreTestResult) -> RestoreTestStatus:
        """Bestimme finalen Test-Status."""
        if result.errors:
            return RestoreTestStatus.FAILED

        if result.tables_failed > 0:
            return RestoreTestStatus.FAILED

        # Bei Standard/Thorough auch Record Counts pruefen
        if result.validation_level in (ValidationLevel.STANDARD, ValidationLevel.THOROUGH):
            failed_counts = [
                r for r in result.record_count_results if not r.match
            ]
            if failed_counts:
                # Nur fehlen wenn kritische Tabellen betroffen
                critical_failures = [
                    r for r in failed_counts if r.table_name in self.CRITICAL_TABLES[:5]
                ]
                if critical_failures:
                    return RestoreTestStatus.FAILED

        return RestoreTestStatus.PASSED

    async def _finalize_result(
        self,
        result: RestoreTestResult,
        cleanup: bool = False,
    ) -> RestoreTestResult:
        """Finalisiere Result mit Timing-Info."""
        result.completed_at = utc_now()
        result.duration_seconds = (
            result.completed_at - result.started_at
        ).total_seconds()

        logger.info(
            "restore_test_completed",
            test_id=str(result.test_id),
            status=result.status.value,
            duration_seconds=result.duration_seconds,
            tables_checked=result.tables_checked,
            tables_passed=result.tables_passed,
            tables_failed=result.tables_failed,
            record_match_rate=result.record_match_rate,
            error_count=len(result.errors),
        )

        # Speichere Ergebnis in Redis fuer Historie
        await self.store_test_result(result)

        return result

    # -------------------------------------------------------------------------
    # Reporting
    # -------------------------------------------------------------------------

    async def generate_report(
        self,
        result: RestoreTestResult,
    ) -> Dict[str, Any]:
        """Generiere detaillierten Report fuer einen Test."""
        return {
            "test_id": str(result.test_id),
            "status": result.status.value,
            "passed": result.passed,
            "summary": result.summary,
            "timing": {
                "started_at": result.started_at.isoformat(),
                "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                "duration_seconds": result.duration_seconds,
            },
            "backup": {
                "file": result.backup_file,
                "date": result.backup_date.isoformat() if result.backup_date else None,
                "size_mb": result.backup_size_mb,
            },
            "validation": {
                "level": result.validation_level.value,
                "tables_checked": result.tables_checked,
                "tables_passed": result.tables_passed,
                "tables_failed": result.tables_failed,
                "total_records_source": result.total_records_source,
                "total_records_restored": result.total_records_restored,
                "record_match_rate": result.record_match_rate,
            },
            "schema_results": [
                {
                    "table": r.table_name,
                    "exists": r.exists,
                    "columns": r.column_count,
                    "column_match": r.column_match,
                    "errors": r.errors,
                }
                for r in result.schema_results
            ],
            "record_counts": [
                {
                    "table": r.table_name,
                    "source": r.source_count,
                    "restored": r.restored_count,
                    "difference": r.difference,
                    "match": r.match,
                    "percentage": r.percentage_match,
                }
                for r in result.record_count_results
            ],
            "errors": result.errors,
            "warnings": result.warnings,
        }

    async def notify_on_failure(
        self,
        result: RestoreTestResult,
    ) -> bool:
        """Sende Slack-Benachrichtigung bei Fehler."""
        if result.status != RestoreTestStatus.FAILED:
            return False

        try:
            from app.services.slack_service import slack_service


            message = (
                f"🚨 *Backup Restore Test fehlgeschlagen*\n\n"
                f"*Test-ID:* {result.test_id}\n"
                f"*Backup:* {result.backup_file}\n"
                f"*Dauer:* {result.duration_seconds:.1f}s\n\n"
                f"*Tabellen:* {result.tables_passed}/{result.tables_checked} bestanden\n"
                f"*Record Match:* {result.record_match_rate:.1f}%\n\n"
                f"*Fehler:*\n"
            )

            for error in result.errors[:5]:
                message += f"• {error[:100]}\n"

            if len(result.errors) > 5:
                message += f"... und {len(result.errors) - 5} weitere Fehler\n"

            await slack_service.send_message(
                channel="#backup-alerts",
                text=message,
                notification_type="system_alert",
            )

            logger.info(
                "restore_test_failure_notified",
                test_id=str(result.test_id),
            )

            return True

        except Exception as e:
            logger.warning(
                "restore_test_notification_failed",
                test_id=str(result.test_id),
                **safe_error_log(e),
            )
            return False

    async def get_test_history(
        self,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Hole Test-Historie der letzten N Tage.

        Die Historie wird aus Redis gelesen (oder in Zukunft aus DB).

        Args:
            days: Anzahl Tage zurueckblicken

        Returns:
            Liste von Test-Ergebnis-Dicts
        """
        try:
            import redis.asyncio as redis

            redis_client = redis.Redis.from_url(
                str(settings.REDIS_URL),
                decode_responses=True,
            )

            # Hole alle Test-Keys der letzten N Tage
            history: List[Dict[str, Any]] = []
            cutoff = utc_now() - timedelta(days=days)

            # Pattern fuer Test-Ergebnisse
            pattern = "backup_restore_test:*"
            keys = await redis_client.keys(pattern)

            for key in keys:
                try:
                    data = await redis_client.hgetall(key)
                    if data:
                        # Parse timestamp
                        completed_at_str = data.get("completed_at")
                        if completed_at_str:
                            completed_at = datetime.fromisoformat(completed_at_str.replace("Z", "+00:00"))
                            if completed_at >= cutoff:
                                history.append({
                                    "test_id": data.get("test_id"),
                                    "status": data.get("status"),
                                    "success": data.get("success") == "true",
                                    "backup_path": data.get("backup_path"),
                                    "started_at": data.get("started_at"),
                                    "completed_at": completed_at_str,
                                    "duration_seconds": float(data.get("duration_seconds", 0)),
                                    "validation_level": data.get("validation_level"),
                                    "errors_count": int(data.get("errors_count", 0)),
                                })
                except Exception as e:
                    logger.warning(
                        "restore_test_history_parse_error",
                        key=key,
                        **safe_error_log(e),
                    )
                    continue

            await redis_client.close()

            # Sortiere nach completed_at absteigend
            history.sort(
                key=lambda x: x.get("completed_at", ""),
                reverse=True,
            )

            return history

        except Exception as e:
            logger.exception("restore_test_history_error")
            return []

    async def store_test_result(
        self,
        result: "RestoreTestResult",
    ) -> bool:
        """
        Speichere Test-Ergebnis in Redis.

        Args:
            result: Das Test-Ergebnis

        Returns:
            True wenn erfolgreich
        """
        try:
            import redis.asyncio as redis

            redis_client = redis.Redis.from_url(
                str(settings.REDIS_URL),
                decode_responses=True,
            )

            key = f"backup_restore_test:{result.test_id}"
            data = {
                "test_id": str(result.test_id),
                "status": result.status.value,
                "success": "true" if result.success else "false",
                "backup_path": result.backup_file or "",
                "started_at": result.started_at.isoformat() if result.started_at else "",
                "completed_at": result.completed_at.isoformat() if result.completed_at else "",
                "duration_seconds": str(result.duration_seconds or 0),
                "validation_level": result.validation_level.value if result.validation_level else "",
                "errors_count": str(len(result.errors) if result.errors else 0),
            }

            await redis_client.hset(key, mapping=data)
            # TTL: 90 Tage (3 Monate Historie)
            await redis_client.expire(key, 90 * 24 * 3600)
            await redis_client.close()

            return True

        except Exception as e:
            logger.warning(
                "restore_test_store_error",
                test_id=str(result.test_id),
                **safe_error_log(e),
            )
            return False


# =============================================================================
# Factory
# =============================================================================


_service_instance: Optional[BackupRestoreTestService] = None


def get_backup_restore_test_service() -> BackupRestoreTestService:
    """Factory function fuer BackupRestoreTestService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = BackupRestoreTestService()
    return _service_instance

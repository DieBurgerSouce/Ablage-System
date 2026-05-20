# -*- coding: utf-8 -*-
"""
Training Data Migration Service.

Migriert bestehende Trainingsdaten aus SQLite nach PostgreSQL.

Unterstützte Quellen:
- _validation_system/training_data.db (Legacy)
- Trainings_Data/ Verzeichnis (Ground Truth Dateien)

Feinpoliert und durchdacht - Datenmigration für OCR Training.
"""

import asyncio
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    OCRTrainingSample,
    OCRBackendBenchmark,
    OCRValidationCorrection,
)
from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class TrainingMigrationService:
    """
    Service für die Migration von Trainingsdaten.

    Migriert:
    - Ground Truth Samples aus SQLite
    - Benchmark-Ergebnisse
    - Korrekturen/Feedback
    - Dateien aus dem Trainings_Data Verzeichnis
    """

    # Pfade für Datenquellen
    LEGACY_SQLITE_PATH = Path("Trainings_Data/_validation_system/training_data.db")
    TRAINING_DATA_DIR = Path("Trainings_Data")

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialisiere Migration Service.

        Args:
            session: Async SQLAlchemy Session
        """
        self.session = session
        self._stats = {
            "samples_migrated": 0,
            "samples_skipped": 0,
            "benchmarks_migrated": 0,
            "corrections_migrated": 0,
            "files_discovered": 0,
            "errors": [],
        }

    async def check_migration_sources(self) -> Dict[str, Any]:
        """
        Prüfe verfügbare Migrationsquellen.

        Returns:
            Dictionary mit verfügbaren Quellen und deren Status
        """
        sources = {
            "sqlite_legacy": {
                "available": self.LEGACY_SQLITE_PATH.exists(),
                "path": str(self.LEGACY_SQLITE_PATH),
                "tables": [],
            },
            "training_data_dir": {
                "available": self.TRAINING_DATA_DIR.exists(),
                "path": str(self.TRAINING_DATA_DIR),
                "file_count": 0,
                "file_types": {},
            },
        }

        # Prüfe SQLite Tabellen
        if sources["sqlite_legacy"]["available"]:
            try:
                conn = sqlite3.connect(str(self.LEGACY_SQLITE_PATH))
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                sources["sqlite_legacy"]["tables"] = [row[0] for row in cursor.fetchall()]
                conn.close()
            except Exception as e:
                sources["sqlite_legacy"]["error"] = safe_error_detail(e, "Migration")

        # Prüfe Training Data Verzeichnis
        if sources["training_data_dir"]["available"]:
            try:
                file_types: Dict[str, int] = {}
                for file_path in self.TRAINING_DATA_DIR.rglob("*"):
                    if file_path.is_file():
                        ext = file_path.suffix.lower()
                        file_types[ext] = file_types.get(ext, 0) + 1

                sources["training_data_dir"]["file_count"] = sum(file_types.values())
                sources["training_data_dir"]["file_types"] = file_types
            except Exception as e:
                sources["training_data_dir"]["error"] = safe_error_detail(e, "Migration")

        return sources

    async def migrate_from_sqlite(
        self,
        sqlite_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Migriere Daten aus SQLite Datenbank.

        Args:
            sqlite_path: Pfad zur SQLite Datenbank (default: Legacy-Pfad)
            dry_run: Nur prüfen, nicht migrieren

        Returns:
            Migrations-Statistiken
        """
        path = sqlite_path or self.LEGACY_SQLITE_PATH

        if not path.exists():
            return {
                "success": False,
                "error": f"SQLite Datenbank nicht gefunden: {path}",
            }

        logger.info("sqlite_migration_starting", path=str(path), dry_run=dry_run)

        try:
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row

            # Migriere Training Samples
            await self._migrate_sqlite_samples(conn, dry_run)

            # Migriere Benchmarks
            await self._migrate_sqlite_benchmarks(conn, dry_run)

            # Migriere Korrekturen
            await self._migrate_sqlite_corrections(conn, dry_run)

            conn.close()

            if not dry_run:
                await self.session.commit()

            logger.info(
                "sqlite_migration_completed",
                samples=self._stats["samples_migrated"],
                benchmarks=self._stats["benchmarks_migrated"],
                corrections=self._stats["corrections_migrated"],
                dry_run=dry_run,
            )

            return {
                "success": True,
                "dry_run": dry_run,
                "stats": dict(self._stats),
            }

        except Exception as e:
            logger.exception("sqlite_migration_failed", **safe_error_log(e))
            return {
                "success": False,
                "error": safe_error_detail(e, "Vorgang"),
                "stats": dict(self._stats),
            }

    # P.1 SECURITY FIX: Whitelist für erlaubte Tabellennamen (SQL Injection Prevention)
    ALLOWED_MIGRATION_TABLES = frozenset({"training_samples", "documents"})

    async def _migrate_sqlite_samples(
        self,
        conn: sqlite3.Connection,
        dry_run: bool,
    ) -> None:
        """Migriere Training Samples aus SQLite."""
        # Prüfe ob 'training_samples' oder 'documents' Tabelle existiert
        # P.1 SECURITY FIX: Parameterisierte Query statt f-string
        table_name = None
        for tbl in ["training_samples", "documents"]:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,)
            )
            if cursor.fetchone():
                table_name = tbl
                break

        if not table_name:
            logger.info("sqlite_no_samples_or_documents_table")
            return

        # P.1 SECURITY FIX: Whitelist-Validierung vor dynamischem Tabellennamen
        if table_name not in self.ALLOWED_MIGRATION_TABLES:
            logger.error(
                "sqlite_invalid_table_name",
                table=table_name,
                allowed=list(self.ALLOWED_MIGRATION_TABLES)
            )
            raise ValueError(f"Ungültige Tabelle: {table_name}")

        logger.info("sqlite_migrating_table", table=table_name)
        # SECURITY NOTE (Phase 8.2): f-string hier ist SICHER weil:
        # 1. table_name kommt NUR aus ALLOWED_MIGRATION_TABLES (frozenset, unveränderbar)
        # 2. Whitelist-Validierung erfolgt direkt oben (Zeile 208)
        # 3. SQLite unterstützt keine parametrisierten Tabellennamen
        # Alternative waere text(f"SELECT * FROM {table_name}") - gleiche Sicherheit
        cursor = conn.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        for row in rows:
            try:
                row_keys = row.keys()

                # Prüfe ob Sample bereits existiert (anhand file_hash)
                file_hash = row["file_hash"] if "file_hash" in row_keys else None

                if file_hash:
                    existing = await self.session.execute(
                        select(OCRTrainingSample).where(
                            OCRTrainingSample.file_hash == file_hash
                        )
                    )
                    if existing.scalar_one_or_none():
                        self._stats["samples_skipped"] += 1
                        continue

                if not dry_run:
                    # Mapping: SQLite 'documents' → PostgreSQL 'ocr_training_samples'
                    # Feld-Mapping für unterschiedliche Spaltennamen
                    file_path = row.get("file_path", "")
                    language = row.get("doc_language") or row.get("language", "de")
                    document_type = row.get("doc_type") or row.get("document_type")
                    status = row.get("ground_truth_status") or row.get("status", "pending")

                    # OCR-Text als Ground Truth wenn vorhanden und verifiziert
                    ground_truth = row.get("ground_truth_text")
                    if not ground_truth and status == "verified":
                        ground_truth = row.get("ocr_text")

                    # Nutze existierenden Hash aus SQLite oder generiere Pfad-basierten Hash
                    # NICHT Dateiinhalt lesen (Netzwerkpfade können Fehler verursachen)
                    final_hash = file_hash or hashlib.sha256(file_path.encode()).hexdigest()

                    sample = OCRTrainingSample(
                        id=uuid4(),
                        file_path=file_path,
                        file_hash=final_hash,
                        thumbnail_path=row.get("thumbnail_path"),
                        ground_truth_text=ground_truth,
                        language=language or "de",
                        document_type=document_type,
                        difficulty=row.get("difficulty", "medium"),
                        has_umlauts=bool(row.get("has_umlauts", False)),
                        has_fraktur=bool(row.get("has_fraktur", False)),
                        has_tables=bool(row.get("has_tables", False)),
                        has_handwriting=bool(row.get("has_handwriting", False)),
                        has_stamps=bool(row.get("has_stamps", False)),
                        has_signatures=bool(row.get("has_signatures", False)),
                        status=self._map_status(status),
                        created_at=self._parse_datetime(row.get("created_at")),
                    )
                    self.session.add(sample)

                self._stats["samples_migrated"] += 1

            except Exception as e:
                self._stats["errors"].append(f"Sample migration error: {e}")
                logger.warning("sample_migration_error", **safe_error_log(e))

    def _map_status(self, sqlite_status: Optional[str]) -> str:
        """Map SQLite Status auf PostgreSQL TrainingSampleStatus."""
        status_map = {
            "pending": "pending",
            "annotated": "annotated",
            "verified": "verified",
            "rejected": "rejected",
            "needs_review": "pending",
            None: "pending",
            "": "pending",
        }
        return status_map.get(sqlite_status, "pending")

    async def _migrate_sqlite_benchmarks(
        self,
        conn: sqlite3.Connection,
        dry_run: bool,
    ) -> None:
        """Migriere Benchmark-Ergebnisse aus SQLite."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='benchmarks'"
        )
        if not cursor.fetchone():
            logger.info("sqlite_no_benchmarks_table")
            return

        cursor = conn.execute("SELECT * FROM benchmarks")
        rows = cursor.fetchall()

        for row in rows:
            try:
                if not dry_run:
                    # Finde zugehöriges Sample
                    sample_id = row.get("sample_id") or row.get("training_sample_id")
                    if not sample_id:
                        continue

                    benchmark = OCRBackendBenchmark(
                        id=str(uuid4()),
                        training_sample_id=sample_id,
                        backend_name=row.get("backend_name", "unknown"),
                        backend_version=row.get("backend_version"),
                        raw_text=row.get("raw_text"),
                        confidence_score=row.get("confidence_score"),
                        cer=row.get("cer"),
                        wer=row.get("wer"),
                        umlaut_accuracy=row.get("umlaut_accuracy"),
                        processing_time_ms=row.get("processing_time_ms"),
                        processed_at=self._parse_datetime(row.get("processed_at")),
                    )
                    self.session.add(benchmark)

                self._stats["benchmarks_migrated"] += 1

            except Exception as e:
                self._stats["errors"].append(f"Benchmark migration error: {e}")
                logger.warning("benchmark_migration_error", **safe_error_log(e))

    async def _migrate_sqlite_corrections(
        self,
        conn: sqlite3.Connection,
        dry_run: bool,
    ) -> None:
        """Migriere Korrekturen aus SQLite."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='corrections'"
        )
        if not cursor.fetchone():
            logger.info("sqlite_no_corrections_table")
            return

        cursor = conn.execute("SELECT * FROM corrections")
        rows = cursor.fetchall()

        for row in rows:
            try:
                if not dry_run:
                    correction = OCRValidationCorrection(
                        id=str(uuid4()),
                        document_id=row.get("document_id"),
                        original_text=row.get("original_text", ""),
                        corrected_text=row.get("corrected_text", ""),
                        correction_type=row.get("correction_type", "text"),
                        field_corrected=row.get("field_corrected"),
                        backend_used=row.get("backend_used", "unknown"),
                        confidence_before=row.get("confidence_before"),
                        applies_to_training=bool(row.get("applies_to_training", True)),
                        learning_processed=bool(row.get("learning_processed", False)),
                        created_at=self._parse_datetime(row.get("created_at")),
                    )
                    self.session.add(correction)

                self._stats["corrections_migrated"] += 1

            except Exception as e:
                self._stats["errors"].append(f"Correction migration error: {e}")
                logger.warning("correction_migration_error", **safe_error_log(e))

    async def discover_training_files(
        self,
        directory: Optional[Path] = None,
        extensions: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Entdecke Trainingsdateien im Verzeichnis.

        Args:
            directory: Verzeichnis zum Durchsuchen (default: TRAINING_DATA_DIR)
            extensions: Erlaubte Dateierweiterungen

        Returns:
            Liste der gefundenen Dateien mit Metadaten
        """
        directory = directory or self.TRAINING_DATA_DIR
        extensions = extensions or [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"]

        if not directory.exists():
            return []

        files = []
        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in extensions:
                files.append({
                    "path": str(file_path),
                    "name": file_path.name,
                    "extension": file_path.suffix.lower(),
                    "size_bytes": file_path.stat().st_size,
                    "modified_at": datetime.fromtimestamp(
                        file_path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                })

        self._stats["files_discovered"] = len(files)
        return files

    async def import_training_files(
        self,
        directory: Optional[Path] = None,
        language: str = "de",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Importiere Trainingsdateien als neue Samples.

        Args:
            directory: Verzeichnis mit Trainingsdateien
            language: Standard-Sprache für Samples
            dry_run: Nur prüfen, nicht importieren

        Returns:
            Import-Statistiken
        """
        directory = directory or self.TRAINING_DATA_DIR

        logger.info("training_file_import_starting", directory=str(directory), dry_run=dry_run)

        files = await self.discover_training_files(directory)

        if not files:
            return {
                "success": True,
                "message": "Keine Dateien gefunden",
                "files_found": 0,
            }

        imported = 0
        skipped = 0
        errors = []

        for file_info in files:
            try:
                file_path = Path(file_info["path"])
                file_hash = self._generate_hash(str(file_path))

                # Prüfe ob bereits existiert
                existing = await self.session.execute(
                    select(OCRTrainingSample).where(
                        OCRTrainingSample.file_hash == file_hash
                    )
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue

                if not dry_run:
                    # Analysiere Dateinamen für Metadaten
                    metadata = self._extract_metadata_from_filename(file_path.name)

                    sample = OCRTrainingSample(
                        id=str(uuid4()),
                        file_path=str(file_path),
                        file_hash=file_hash,
                        language=metadata.get("language", language),
                        document_type=metadata.get("document_type"),
                        difficulty="medium",
                        has_umlauts=False,
                        has_fraktur=False,
                        has_tables=False,
                        has_handwriting=False,
                        has_stamps=False,
                        has_signatures=False,
                        status="pending",
                    )
                    self.session.add(sample)

                imported += 1

            except Exception as e:
                errors.append(f"{file_info['name']}: {e}")
                logger.warning("file_import_error", file=file_info["name"], **safe_error_log(e))

        if not dry_run:
            await self.session.commit()

        logger.info(
            "training_file_import_completed",
            imported=imported,
            skipped=skipped,
            errors=len(errors),
            dry_run=dry_run,
        )

        return {
            "success": True,
            "dry_run": dry_run,
            "files_found": len(files),
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
        }

    def _generate_hash(self, file_path: str) -> str:
        """Generiere Hash für Datei oder Pfad."""
        try:
            path = Path(file_path)
            if path.exists():
                # Hash basierend auf Dateiinhalt
                hasher = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        hasher.update(chunk)
                return hasher.hexdigest()
        except Exception as e:
            logger.debug(
                "file_hash_calculation_failed",
                error_type=type(e).__name__,
            )

        # Fallback: Hash basierend auf Pfad
        return hashlib.sha256(file_path.encode()).hexdigest()

    def _parse_datetime(self, value: Union[str, datetime, None]) -> datetime:
        """Parse datetime aus verschiedenen Formaten."""
        if value is None:
            return datetime.now(timezone.utc)

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as e:
                logger.debug(
                    "datetime_isoformat_parse_failed",
                    error_type=type(e).__name__,
                )

            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError as e:
                logger.debug(
                    "datetime_strptime_parse_failed",
                    error_type=type(e).__name__,
                )

        return datetime.now(timezone.utc)

    def _extract_metadata_from_filename(self, filename: str) -> Dict[str, Any]:
        """Extrahiere Metadaten aus Dateinamen."""
        metadata: Dict[str, Any] = {}

        filename_lower = filename.lower()

        # Sprache erkennen
        if "_de_" in filename_lower or "_german" in filename_lower:
            metadata["language"] = "de"
        elif "_en_" in filename_lower or "_english" in filename_lower:
            metadata["language"] = "en"
        elif "_nl_" in filename_lower or "_dutch" in filename_lower:
            metadata["language"] = "nl"
        elif "_pl_" in filename_lower or "_polish" in filename_lower:
            metadata["language"] = "pl"

        # Dokumenttyp erkennen
        if "invoice" in filename_lower or "rechnung" in filename_lower:
            metadata["document_type"] = "invoice"
        elif "contract" in filename_lower or "vertrag" in filename_lower:
            metadata["document_type"] = "contract"
        elif "letter" in filename_lower or "brief" in filename_lower:
            metadata["document_type"] = "letter"
        elif "report" in filename_lower or "bericht" in filename_lower:
            metadata["document_type"] = "report"

        return metadata

    def get_migration_stats(self) -> Dict[str, Any]:
        """Hole aktuelle Migrations-Statistiken."""
        return dict(self._stats)


# Singleton-Instanz
_migration_service: Optional[TrainingMigrationService] = None


async def get_training_migration_service(
    session: AsyncSession,
) -> TrainingMigrationService:
    """
    Hole Training Migration Service Instanz.

    Args:
        session: Async SQLAlchemy Session

    Returns:
        TrainingMigrationService Instanz
    """
    return TrainingMigrationService(session)

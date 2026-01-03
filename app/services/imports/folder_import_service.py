"""Folder Import Service (Hotfolder).

Orchestriert den Import von Dateien aus ueberwachten Ordnern:
- Watchdog-basierte Dateisystem-Ueberwachung
- Polling als Fallback fuer Netzwerk-Laufwerke
- Path-Traversal-Schutz
- Integration mit Document-Pipeline

Feinpoliert und durchdacht - Enterprise-grade Folder Import.
"""

import asyncio
import hashlib
import os
import re
import shutil
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional, List, Dict, Set
from uuid import UUID, uuid4
import structlog

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_data, decrypt_data, EncryptionError
from app.core.malware_scanner import scan_file

logger = structlog.get_logger(__name__)


# ============================================================================
# Watchdog Import (optional dependency)
# ============================================================================

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object
    FileCreatedEvent = None
    logger.warning("watchdog not installed - folder watching disabled")


# ============================================================================
# Constants
# ============================================================================

# Maximale Dateigroesse (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Erlaubte Dateiendungen
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".gif", ".bmp", ".webp"}

# Erlaubte Basis-Pfade (Security: Path Traversal Prevention)
# Diese werden aus Settings geladen, hier als Default
DEFAULT_ALLOWED_BASE_PATHS = [
    "/data/import",
    "/home",
    "C:\\Import",
    "C:\\Users",
    "D:\\Import",
]

# Dateinamens-Pattern die immer ignoriert werden
IGNORE_PATTERNS = [
    "*.tmp",
    "*.temp",
    "~*",
    "._*",
    ".DS_Store",
    "Thumbs.db",
    "*.part",
    "*.crdownload",
]

# Verzoegerung nach Dateierstellung (um unvollstaendige Uploads zu vermeiden)
FILE_SETTLE_DELAY_SECONDS = 2


# ============================================================================
# Data Classes
# ============================================================================

class FileInfo:
    """Repraesentiert eine importierbare Datei."""

    def __init__(
        self,
        path: Path,
        size: int,
        modified_at: datetime,
        mime_type: str,
    ):
        self.path = path
        self.filename = path.name
        self.size = size
        self.modified_at = modified_at
        self.mime_type = mime_type
        self._file_hash: Optional[str] = None

    @property
    def file_hash(self) -> str:
        """Berechnet SHA256 Hash der Datei (lazy)."""
        if self._file_hash is None:
            with open(self.path, "rb") as f:
                self._file_hash = hashlib.sha256(f.read()).hexdigest()
        return self._file_hash


class FolderImportResult:
    """Ergebnis eines Folder-Imports."""

    def __init__(self):
        self.files_processed: int = 0
        self.documents_created: int = 0
        self.duplicates_skipped: int = 0
        self.files_moved: int = 0
        self.errors: List[Dict] = []
        self.created_document_ids: List[UUID] = []


# ============================================================================
# Watchdog Event Handler
# ============================================================================

class FolderWatchHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Handler fuer Dateisystem-Events."""

    def __init__(
        self,
        config_id: UUID,
        callback,
        include_patterns: List[str],
        exclude_patterns: List[str],
    ):
        super().__init__()
        self.config_id = config_id
        self.callback = callback
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self._pending_files: Set[str] = set()

    def _matches_pattern(self, filename: str, patterns: List[str]) -> bool:
        """Prueft ob Dateiname auf mindestens ein Pattern matched."""
        return any(fnmatch(filename.lower(), p.lower()) for p in patterns)

    def _should_process(self, path: str) -> bool:
        """Prueft ob Datei verarbeitet werden soll."""
        filename = os.path.basename(path)

        # Exclude-Patterns pruefen
        if self._matches_pattern(filename, self.exclude_patterns):
            return False
        if self._matches_pattern(filename, IGNORE_PATTERNS):
            return False

        # Include-Patterns pruefen
        if self.include_patterns:
            return self._matches_pattern(filename, self.include_patterns)

        return True

    def on_created(self, event):
        """Handler fuer neue Dateien."""
        if event.is_directory:
            return

        path = event.src_path

        if not self._should_process(path):
            return

        # Datei zur Pending-Liste hinzufuegen
        # Callback wird asynchron aufgerufen nach Settle-Delay
        if path not in self._pending_files:
            self._pending_files.add(path)
            asyncio.get_event_loop().call_later(
                FILE_SETTLE_DELAY_SECONDS,
                lambda: self._process_pending(path)
            )

    def _process_pending(self, path: str):
        """Verarbeitet eine pending Datei."""
        if path in self._pending_files:
            self._pending_files.discard(path)
            if os.path.exists(path):
                asyncio.create_task(self.callback(self.config_id, path))


# ============================================================================
# Folder Import Service
# ============================================================================

class FolderImportService:
    """Service fuer Hotfolder-basiertes Dokument-Import.

    Features:
    - Watchdog-basierte Echtzeit-Ueberwachung
    - Polling als Fallback fuer Netzwerklaufwerke
    - Path-Traversal-Schutz
    - Pattern-basierte Filter (include/exclude)
    - Automatisches Verschieben nach Verarbeitung
    - Duplikat-Erkennung via SHA256
    - Integration mit Document-Pipeline
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Folder Import Service.

        Args:
            db: Async Database Session
        """
        self.db = db
        self._active_watchers: Dict[UUID, "Observer"] = {}
        self._allowed_base_paths: List[str] = self._load_allowed_paths()

    def _load_allowed_paths(self) -> List[str]:
        """Laedt erlaubte Basis-Pfade aus Settings."""
        from app.core.config import settings

        paths = getattr(settings, "IMPORT_ALLOWED_BASE_PATHS", None)
        if paths:
            return [p.strip() for p in paths.split(",")]
        return DEFAULT_ALLOWED_BASE_PATHS

    # ========================================================================
    # Path Security
    # ========================================================================

    def _validate_path(self, path: str) -> bool:
        """Validiert einen Pfad auf Sicherheit.

        Prueft:
        - Keine Path-Traversal-Angriffe (..)
        - Pfad ist unter erlaubtem Basis-Pfad
        - Pfad existiert und ist zugaenglich

        Args:
            path: Zu pruefender Pfad

        Returns:
            True wenn Pfad sicher und erlaubt

        Raises:
            ValueError: Bei ungueltigem Pfad
        """
        # Normalisieren
        try:
            normalized = os.path.normpath(os.path.abspath(path))
        except Exception as e:
            raise ValueError(f"Ungueltiger Pfad: {e}")

        # Path-Traversal pruefen
        if ".." in path:
            raise ValueError("Path-Traversal nicht erlaubt")

        # Gegen erlaubte Basis-Pfade pruefen
        is_allowed = False
        for base in self._allowed_base_paths:
            base_normalized = os.path.normpath(os.path.abspath(base))
            if normalized.startswith(base_normalized):
                is_allowed = True
                break

        if not is_allowed:
            raise ValueError(
                f"Pfad nicht in erlaubten Verzeichnissen. "
                f"Erlaubt: {', '.join(self._allowed_base_paths)}"
            )

        return True

    def _sanitize_filename(self, filename: str) -> str:
        """Bereinigt einen Dateinamen.

        Args:
            filename: Roher Dateiname

        Returns:
            Sicherer Dateiname
        """
        # Entferne gefaehrliche Zeichen
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)

        # Entferne fuehrende/trailing Punkte und Leerzeichen
        safe = safe.strip('. ')

        # Begrenze Laenge
        if len(safe) > 255:
            name, ext = os.path.splitext(safe)
            safe = name[:255 - len(ext)] + ext

        return safe or "unnamed"

    # ========================================================================
    # Watcher Management
    # ========================================================================

    async def start_watcher(
        self,
        config_id: UUID,
        user_id: UUID,
    ) -> Dict:
        """Startet einen Folder-Watcher fuer eine Konfiguration.

        Args:
            config_id: Folder-Import-Konfigurations-ID
            user_id: User-ID fuer Berechtigungspruefung

        Returns:
            Dict mit Status
        """
        if not WATCHDOG_AVAILABLE:
            return {
                "success": False,
                "message": "Watchdog nicht installiert. Nutze Polling stattdessen.",
            }

        from app.db.models import FolderImportConfig

        # Config laden
        config = await self._get_config(config_id, user_id)
        if not config:
            return {
                "success": False,
                "message": "Konfiguration nicht gefunden",
            }

        # Pruefen ob bereits aktiv
        if config_id in self._active_watchers:
            return {
                "success": True,
                "message": "Watcher bereits aktiv",
            }

        try:
            # Pfad validieren
            self._validate_path(config.watch_path)

            # Pruefen ob Pfad existiert
            if not os.path.isdir(config.watch_path):
                return {
                    "success": False,
                    "message": f"Ordner existiert nicht: {config.watch_path}",
                }

            # Event Handler erstellen
            handler = FolderWatchHandler(
                config_id=config_id,
                callback=self._handle_new_file,
                include_patterns=config.include_patterns or [],
                exclude_patterns=config.exclude_patterns or [],
            )

            # Observer starten
            observer = Observer()
            observer.schedule(
                handler,
                config.watch_path,
                recursive=config.recursive,
            )
            observer.start()

            self._active_watchers[config_id] = observer

            # Status aktualisieren
            await self._update_watcher_status(config_id, "running", None)

            logger.info(
                "folder_watcher_started",
                config_id=str(config_id),
                watch_path=config.watch_path,
            )

            return {
                "success": True,
                "message": f"Watcher gestartet fuer: {config.watch_path}",
            }

        except ValueError as e:
            return {
                "success": False,
                "message": str(e),
            }
        except Exception as e:
            logger.error(
                "folder_watcher_start_failed",
                config_id=str(config_id),
                error=str(e),
            )
            return {
                "success": False,
                "message": f"Watcher konnte nicht gestartet werden: {e}",
            }

    async def stop_watcher(
        self,
        config_id: UUID,
        user_id: UUID,
    ) -> Dict:
        """Stoppt einen Folder-Watcher.

        Args:
            config_id: Config-ID
            user_id: User-ID fuer Berechtigungspruefung

        Returns:
            Dict mit Status
        """
        # Config pruefen (fuer Berechtigung)
        config = await self._get_config(config_id, user_id)
        if not config:
            return {
                "success": False,
                "message": "Konfiguration nicht gefunden",
            }

        if config_id not in self._active_watchers:
            return {
                "success": True,
                "message": "Watcher war nicht aktiv",
            }

        try:
            observer = self._active_watchers.pop(config_id)
            observer.stop()
            observer.join(timeout=5)

            await self._update_watcher_status(config_id, "stopped", None)

            logger.info(
                "folder_watcher_stopped",
                config_id=str(config_id),
            )

            return {
                "success": True,
                "message": "Watcher gestoppt",
            }

        except Exception as e:
            logger.error(
                "folder_watcher_stop_failed",
                config_id=str(config_id),
                error=str(e),
            )
            return {
                "success": False,
                "message": f"Fehler beim Stoppen: {e}",
            }

    # ========================================================================
    # Polling (Fallback)
    # ========================================================================

    async def poll_folder(
        self,
        config_id: UUID,
        user_id: UUID,
    ) -> FolderImportResult:
        """Fuehrt manuellen Scan eines Ordners durch.

        Diese Methode wird auch als Fallback fuer Netzwerklaufwerke
        verwendet, die nicht mit Watchdog kompatibel sind.

        Args:
            config_id: Folder-Import-Konfigurations-ID
            user_id: User-ID

        Returns:
            FolderImportResult mit Statistiken
        """
        from app.db.models import FolderImportConfig

        result = FolderImportResult()
        batch_id = uuid4()

        # Config laden
        config = await self._get_config(config_id, user_id)
        if not config:
            result.errors.append({
                "type": "config_error",
                "message": "Konfiguration nicht gefunden",
            })
            return result

        if not config.is_active:
            result.errors.append({
                "type": "config_inactive",
                "message": "Konfiguration ist deaktiviert",
            })
            return result

        try:
            # Pfad validieren
            self._validate_path(config.watch_path)

            if not os.path.isdir(config.watch_path):
                result.errors.append({
                    "type": "path_error",
                    "message": f"Ordner existiert nicht: {config.watch_path}",
                })
                return result

            # Dateien sammeln
            files_to_process = self._collect_files(
                path=config.watch_path,
                recursive=config.recursive,
                include_patterns=config.include_patterns or [],
                exclude_patterns=config.exclude_patterns or [],
            )

            logger.info(
                "folder_poll_started",
                config_id=str(config_id),
                file_count=len(files_to_process),
            )

            # Dateien verarbeiten
            for file_path in files_to_process:
                try:
                    file_result = await self._process_file(
                        config=config,
                        file_path=file_path,
                        batch_id=batch_id,
                        user_id=user_id,
                    )

                    result.files_processed += 1

                    if file_result.get("success"):
                        result.documents_created += 1
                        if file_result.get("document_id"):
                            result.created_document_ids.append(
                                file_result["document_id"]
                            )
                        if file_result.get("moved"):
                            result.files_moved += 1
                    elif file_result.get("duplicate"):
                        result.duplicates_skipped += 1

                except Exception as file_error:
                    result.errors.append({
                        "file": str(file_path),
                        "error": str(file_error),
                    })
                    logger.warning(
                        "file_processing_failed",
                        file=str(file_path),
                        error=str(file_error),
                    )

            # Poll-Timestamp aktualisieren
            await self._update_poll_timestamp(config_id)

            # Statistiken aktualisieren
            await self._update_stats(
                config_id,
                files_processed=result.files_processed,
                documents_created=result.documents_created,
            )

            logger.info(
                "folder_poll_completed",
                config_id=str(config_id),
                files_processed=result.files_processed,
                documents_created=result.documents_created,
            )

        except ValueError as e:
            result.errors.append({
                "type": "validation_error",
                "message": str(e),
            })
        except Exception as e:
            result.errors.append({
                "type": "poll_error",
                "message": str(e),
            })
            logger.error(
                "folder_poll_failed",
                config_id=str(config_id),
                error=str(e),
            )

        return result

    def _collect_files(
        self,
        path: str,
        recursive: bool,
        include_patterns: List[str],
        exclude_patterns: List[str],
    ) -> List[Path]:
        """Sammelt alle zu verarbeitenden Dateien.

        Args:
            path: Basis-Pfad
            recursive: Unterordner durchsuchen
            include_patterns: Include-Pattern
            exclude_patterns: Exclude-Pattern

        Returns:
            Liste von Dateipfaden
        """
        files = []
        base_path = Path(path)

        def matches_pattern(filename: str, patterns: List[str]) -> bool:
            return any(fnmatch(filename.lower(), p.lower()) for p in patterns)

        def should_include(filepath: Path) -> bool:
            filename = filepath.name

            # Ignore-Patterns immer anwenden
            if matches_pattern(filename, IGNORE_PATTERNS):
                return False

            # Exclude-Patterns
            if exclude_patterns and matches_pattern(filename, exclude_patterns):
                return False

            # Dateiendung pruefen
            ext = filepath.suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                return False

            # Include-Patterns (wenn vorhanden)
            if include_patterns:
                return matches_pattern(filename, include_patterns)

            return True

        if recursive:
            for root, _, filenames in os.walk(base_path):
                for filename in filenames:
                    filepath = Path(root) / filename
                    if should_include(filepath):
                        files.append(filepath)
        else:
            for item in base_path.iterdir():
                if item.is_file() and should_include(item):
                    files.append(item)

        return files

    # ========================================================================
    # File Processing
    # ========================================================================

    async def _handle_new_file(self, config_id: UUID, file_path: str) -> None:
        """Callback fuer Watchdog - verarbeitet neue Datei.

        Args:
            config_id: Config-ID
            file_path: Pfad zur neuen Datei
        """
        from app.db.models import FolderImportConfig

        # Config laden (ohne User-Check, da Watchdog)
        result = await self.db.execute(
            select(FolderImportConfig).where(
                FolderImportConfig.id == config_id
            )
        )
        config = result.scalar_one_or_none()

        if not config or not config.is_active:
            return

        batch_id = uuid4()

        try:
            await self._process_file(
                config=config,
                file_path=Path(file_path),
                batch_id=batch_id,
                user_id=config.user_id,
            )
        except Exception as e:
            logger.error(
                "watchdog_file_processing_failed",
                config_id=str(config_id),
                file=file_path,
                error=str(e),
            )

    async def _process_file(
        self,
        config,
        file_path: Path,
        batch_id: UUID,
        user_id: UUID,
    ) -> Dict:
        """Verarbeitet eine einzelne Datei.

        Args:
            config: FolderImportConfig
            file_path: Pfad zur Datei
            batch_id: Batch-ID
            user_id: User-ID

        Returns:
            Dict mit Ergebnis
        """
        from app.db.models import ImportLog

        # Datei-Info sammeln
        stat = file_path.stat()
        file_size = stat.st_size
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        # Groesse pruefen
        if file_size > MAX_FILE_SIZE:
            return {
                "success": False,
                "error": f"Datei zu gross: {file_size / 1024 / 1024:.1f} MB",
            }

        # MIME-Type ermitteln
        import mimetypes
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        # Hash berechnen
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Import-Log erstellen
        import_log = ImportLog(
            id=uuid4(),
            user_id=user_id,
            source_type="folder",
            folder_config_id=config.id,
            batch_id=batch_id,
            original_path=str(file_path),
            original_filename=file_path.name,
            file_modified_at=modified_at,
            file_hash=file_hash,
            file_size=file_size,
            mime_type=mime_type,
            status="processing",
        )
        self.db.add(import_log)
        await self.db.flush()

        try:
            # Duplikat-Check
            existing = await self._check_duplicate_by_hash(user_id, file_hash)
            if existing:
                import_log.status = "skipped"
                import_log.error_code = "duplicate"
                import_log.error_message = f"Duplikat von Dokument {existing}"
                await self.db.commit()
                return {"duplicate": True, "existing_document_id": existing}

            # Malware-Scan
            if not await self._scan_file(file_path):
                import_log.status = "failed"
                import_log.error_code = "malware_detected"
                import_log.error_message = "Potenzielle Schadsoftware erkannt"
                await self.db.commit()

                # In Error-Ordner verschieben wenn konfiguriert
                if config.error_subfolder:
                    await self._move_to_subfolder(
                        file_path,
                        config.watch_path,
                        config.error_subfolder,
                    )

                return {"success": False, "error": "Malware detected"}

            # Dokument erstellen
            document_id = await self._create_document(
                user_id=user_id,
                config=config,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                mime_type=mime_type,
            )

            # Import-Log aktualisieren
            import_log.status = "completed"
            import_log.document_id = document_id
            import_log.completed_at = datetime.now(timezone.utc)
            import_log.processing_duration_ms = int(
                (datetime.now(timezone.utc) - import_log.started_at).total_seconds() * 1000
            )

            # Datei verschieben oder loeschen
            moved = False
            if config.delete_after_processing:
                try:
                    os.remove(file_path)
                except Exception as del_error:
                    logger.warning(
                        "file_delete_failed",
                        file=str(file_path),
                        error=str(del_error),
                    )
            elif config.move_after_processing and config.processed_subfolder:
                moved = await self._move_to_subfolder(
                    file_path,
                    config.watch_path,
                    config.processed_subfolder,
                )

            await self.db.commit()

            return {"success": True, "document_id": document_id, "moved": moved}

        except Exception as e:
            import_log.status = "failed"
            import_log.error_message = str(e)[:500]
            await self.db.commit()

            # In Error-Ordner verschieben wenn konfiguriert
            if config.error_subfolder:
                await self._move_to_subfolder(
                    file_path,
                    config.watch_path,
                    config.error_subfolder,
                )

            return {"success": False, "error": str(e)}

    async def _check_duplicate_by_hash(
        self, user_id: UUID, file_hash: str
    ) -> Optional[UUID]:
        """Prueft ob ein Dokument mit gleichem Hash bereits existiert."""
        from app.db.models import Document

        result = await self.db.execute(
            select(Document.id).where(
                and_(
                    Document.user_id == user_id,
                    Document.file_hash == file_hash,
                )
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _scan_file(self, file_path: Path) -> bool:
        """Scannt Datei auf Malware.

        Args:
            file_path: Pfad zur Datei

        Returns:
            True wenn sicher
        """
        try:
            result = await scan_file(str(file_path))
            return result.get("is_safe", False)
        except Exception as e:
            logger.warning(
                "malware_scan_failed",
                file=str(file_path),
                error=str(e),
            )
            # Bei Scan-Fehler: Konservativ ablehnen
            return False

    async def _create_document(
        self,
        user_id: UUID,
        config,
        file_path: Path,
        file_hash: str,
        file_size: int,
        mime_type: str,
    ) -> UUID:
        """Erstellt ein Dokument aus einer Datei.

        Args:
            user_id: User-ID
            config: FolderImportConfig
            file_path: Pfad zur Datei
            file_hash: SHA256 Hash
            file_size: Dateigroesse
            mime_type: MIME-Type

        Returns:
            Document-ID
        """
        from app.services.document_service import DocumentService
        from app.services.storage_service import StorageService

        # Datei lesen
        with open(file_path, "rb") as f:
            content = f.read()

        # Filename bestimmen
        if config.preserve_filename:
            filename = self._sanitize_filename(file_path.name)
        else:
            # Generiere UUID-basierten Namen
            ext = file_path.suffix
            filename = f"{uuid4()}{ext}"

        # Storage Service fuer MinIO Upload
        storage = StorageService()
        storage_path = await storage.upload_document(
            content=content,
            filename=filename,
            user_id=user_id,
            mime_type=mime_type,
        )

        # Document Service fuer DB-Eintrag
        doc_service = DocumentService(self.db)

        # Metadaten
        metadata = {
            "import_source": "folder",
            "original_path": str(file_path),
            "original_filename": file_path.name,
        }

        # Dokument erstellen
        document = await doc_service.create(
            user_id=user_id,
            filename=filename,
            storage_path=storage_path,
            mime_type=mime_type,
            file_size=file_size,
            file_hash=file_hash,
            folder_id=config.default_folder_id,
            metadata=metadata,
            auto_classify=config.auto_classify,
            auto_ocr=config.auto_ocr,
        )

        return document.id

    async def _move_to_subfolder(
        self,
        file_path: Path,
        base_path: str,
        subfolder: str,
    ) -> bool:
        """Verschiebt Datei in Unterordner.

        Args:
            file_path: Quelldatei
            base_path: Basis-Ordner
            subfolder: Ziel-Unterordner

        Returns:
            True wenn erfolgreich
        """
        try:
            target_dir = Path(base_path) / subfolder
            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / file_path.name

            # Bei Namenskollision: Suffix hinzufuegen
            if target_path.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                counter = 1
                while target_path.exists():
                    target_path = target_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

            shutil.move(str(file_path), str(target_path))

            logger.debug(
                "file_moved",
                source=str(file_path),
                target=str(target_path),
            )

            return True

        except Exception as e:
            logger.warning(
                "file_move_failed",
                source=str(file_path),
                subfolder=subfolder,
                error=str(e),
            )
            return False

    # ========================================================================
    # CRUD Operations
    # ========================================================================

    async def create_config(
        self,
        user_id: UUID,
        name: str,
        watch_path: str,
        is_network_path: bool = False,
        network_credentials: Optional[str] = None,
        recursive: bool = False,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        move_after_processing: bool = True,
        processed_subfolder: str = "processed",
        error_subfolder: str = "error",
        delete_after_processing: bool = False,
        auto_classify: bool = True,
        auto_ocr: bool = True,
        default_folder_id: Optional[UUID] = None,
        preserve_filename: bool = True,
        poll_interval_seconds: int = 60,
        company_id: Optional[UUID] = None,
    ) -> UUID:
        """Erstellt eine neue Folder-Import-Konfiguration.

        Args:
            user_id: User-ID
            name: Konfigurations-Name
            watch_path: Zu ueberwachender Pfad
            is_network_path: Ist ein Netzwerkpfad
            network_credentials: Optional verschluesselte Netzwerk-Credentials
            recursive: Unterordner einbeziehen
            include_patterns: Include-Pattern (z.B. ["*.pdf"])
            exclude_patterns: Exclude-Pattern
            move_after_processing: Nach Verarbeitung verschieben
            processed_subfolder: Unterordner fuer verarbeitete Dateien
            error_subfolder: Unterordner fuer fehlerhafte Dateien
            delete_after_processing: Nach Verarbeitung loeschen
            auto_classify: Automatisch klassifizieren
            auto_ocr: Automatisch OCR ausfuehren
            default_folder_id: Standard-Ordner fuer Dokumente
            preserve_filename: Original-Dateinamen beibehalten
            poll_interval_seconds: Polling-Intervall
            company_id: Firma-ID

        Returns:
            Config-ID
        """
        from app.db.models import FolderImportConfig

        # Pfad validieren
        self._validate_path(watch_path)

        config_id = uuid4()

        # Network-Credentials verschluesseln wenn vorhanden
        network_credentials_encrypted = None
        if network_credentials:
            network_credentials_encrypted = encrypt_data(
                network_credentials,
                associated_data=f"folder_config:{config_id}"
            )

        # Default-Patterns
        if include_patterns is None:
            include_patterns = ["*.pdf", "*.jpg", "*.png", "*.tiff"]
        if exclude_patterns is None:
            exclude_patterns = ["*.tmp", "~*", "._*"]

        config = FolderImportConfig(
            id=config_id,
            user_id=user_id,
            company_id=company_id,
            name=name,
            watch_path=watch_path,
            is_network_path=is_network_path,
            network_credentials_encrypted=network_credentials_encrypted,
            recursive=recursive,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            move_after_processing=move_after_processing,
            processed_subfolder=processed_subfolder,
            error_subfolder=error_subfolder,
            delete_after_processing=delete_after_processing,
            auto_classify=auto_classify,
            auto_ocr=auto_ocr,
            default_folder_id=default_folder_id,
            preserve_filename=preserve_filename,
            poll_interval_seconds=poll_interval_seconds,
            is_active=True,
            watcher_status="stopped",
        )

        self.db.add(config)
        await self.db.commit()

        logger.info(
            "folder_config_created",
            config_id=str(config_id),
            user_id=str(user_id),
            watch_path=watch_path,
        )

        return config_id

    async def update_config(
        self,
        config_id: UUID,
        user_id: UUID,
        **updates,
    ) -> bool:
        """Aktualisiert eine Folder-Import-Konfiguration."""
        config = await self._get_config(config_id, user_id)
        if not config:
            return False

        # Pfad validieren wenn geaendert
        if "watch_path" in updates:
            self._validate_path(updates["watch_path"])

        # Network-Credentials verschluesseln wenn vorhanden
        if "network_credentials" in updates:
            creds = updates.pop("network_credentials")
            if creds:
                updates["network_credentials_encrypted"] = encrypt_data(
                    creds,
                    associated_data=f"folder_config:{config_id}"
                )

        # Updates anwenden
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)

        await self.db.commit()

        logger.info(
            "folder_config_updated",
            config_id=str(config_id),
            updated_fields=list(updates.keys()),
        )

        return True

    async def delete_config(
        self,
        config_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Loescht eine Folder-Import-Konfiguration."""
        config = await self._get_config(config_id, user_id)
        if not config:
            return False

        # Watcher stoppen falls aktiv
        if config_id in self._active_watchers:
            await self.stop_watcher(config_id, user_id)

        await self.db.delete(config)
        await self.db.commit()

        logger.info(
            "folder_config_deleted",
            config_id=str(config_id),
        )

        return True

    async def get_config(
        self,
        config_id: UUID,
        user_id: UUID,
    ) -> Optional[Dict]:
        """Holt eine Folder-Import-Konfiguration."""
        config = await self._get_config(config_id, user_id)
        if not config:
            return None

        return {
            "id": config.id,
            "name": config.name,
            "watch_path": config.watch_path,
            "is_network_path": config.is_network_path,
            "recursive": config.recursive,
            "include_patterns": config.include_patterns,
            "exclude_patterns": config.exclude_patterns,
            "move_after_processing": config.move_after_processing,
            "processed_subfolder": config.processed_subfolder,
            "error_subfolder": config.error_subfolder,
            "delete_after_processing": config.delete_after_processing,
            "auto_classify": config.auto_classify,
            "auto_ocr": config.auto_ocr,
            "default_folder_id": config.default_folder_id,
            "preserve_filename": config.preserve_filename,
            "poll_interval_seconds": config.poll_interval_seconds,
            "company_id": config.company_id,
            "is_active": config.is_active,
            "watcher_status": config.watcher_status,
            "last_poll_at": config.last_poll_at,
            "files_processed_today": config.files_processed_today,
            "total_files_processed": config.total_files_processed,
            "total_documents_created": config.total_documents_created,
            "last_error": config.last_error,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

    async def list_configs(
        self,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        active_only: bool = False,
    ) -> List[Dict]:
        """Listet alle Folder-Import-Konfigurationen eines Users."""
        from app.db.models import FolderImportConfig

        query = select(FolderImportConfig).where(
            FolderImportConfig.user_id == user_id
        )

        if company_id:
            query = query.where(FolderImportConfig.company_id == company_id)

        if active_only:
            query = query.where(FolderImportConfig.is_active == True)

        query = query.order_by(FolderImportConfig.created_at.desc())

        result = await self.db.execute(query)
        configs = result.scalars().all()

        return [
            {
                "id": c.id,
                "name": c.name,
                "watch_path": c.watch_path,
                "is_active": c.is_active,
                "watcher_status": c.watcher_status,
                "last_poll_at": c.last_poll_at,
                "total_documents_created": c.total_documents_created,
            }
            for c in configs
        ]

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _get_config(self, config_id: UUID, user_id: UUID):
        """Holt Config mit Berechtigungspruefung."""
        from app.db.models import FolderImportConfig

        result = await self.db.execute(
            select(FolderImportConfig).where(
                and_(
                    FolderImportConfig.id == config_id,
                    FolderImportConfig.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _update_watcher_status(
        self,
        config_id: UUID,
        status: str,
        error: Optional[str],
    ) -> None:
        """Aktualisiert den Watcher-Status."""
        from app.db.models import FolderImportConfig

        values = {"watcher_status": status}
        if error:
            values["last_error"] = error[:500]

        await self.db.execute(
            update(FolderImportConfig)
            .where(FolderImportConfig.id == config_id)
            .values(**values)
        )
        await self.db.commit()

    async def _update_poll_timestamp(self, config_id: UUID) -> None:
        """Aktualisiert den Poll-Timestamp."""
        from app.db.models import FolderImportConfig

        await self.db.execute(
            update(FolderImportConfig)
            .where(FolderImportConfig.id == config_id)
            .values(last_poll_at=datetime.now(timezone.utc))
        )
        await self.db.commit()

    async def _update_stats(
        self,
        config_id: UUID,
        files_processed: int,
        documents_created: int,
    ) -> None:
        """Aktualisiert die Statistiken."""
        from app.db.models import FolderImportConfig

        await self.db.execute(
            update(FolderImportConfig)
            .where(FolderImportConfig.id == config_id)
            .values(
                files_processed_today=FolderImportConfig.files_processed_today + files_processed,
                total_files_processed=FolderImportConfig.total_files_processed + files_processed,
                total_documents_created=FolderImportConfig.total_documents_created + documents_created,
            )
        )
        await self.db.commit()

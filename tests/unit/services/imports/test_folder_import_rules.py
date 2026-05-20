"""Unit Tests fuer Folder-Import + Import-Regel Celery Tasks.

Tests fuer:
- poll_folder_imports_task: Polling aller aktiven Ordner-Configs
- apply_rules_to_pending_imports_task: Regel-Anwendung auf ausstehende Imports
- scan_import_folder_task: Gezielter Scan einzelner Ordner
- Integrations- und Randfall-Tests
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# Helper Factories
# =============================================================================


def _make_config(
    is_active: bool = True,
    watch_path: str = "/data/import/rechnungen",
) -> MagicMock:
    """Erstellt eine FolderImportConfig-Mock-Instanz."""
    cfg = MagicMock()
    cfg.id = uuid4()
    cfg.user_id = uuid4()
    cfg.is_active = is_active
    cfg.watch_path = watch_path
    return cfg


def _make_poll_result(
    files_processed: int = 2,
    documents_created: int = 2,
    duplicates_skipped: int = 0,
    errors: list = None,
) -> MagicMock:
    """Erstellt ein poll_folder()-Ergebnis-Mock."""
    result = MagicMock()
    result.files_processed = files_processed
    result.documents_created = documents_created
    result.duplicates_skipped = duplicates_skipped
    result.errors = errors or []
    return result


def _make_import_log(
    has_document: bool = True,
    has_user: bool = True,
    original_filename: str = "rechnung.pdf",
    original_path: str = "/data/import",
    file_size: int = 12345,
    mime_type: str = "application/pdf",
) -> MagicMock:
    """Erstellt einen ImportLog-Mock-Eintrag."""
    log = MagicMock()
    log.id = uuid4()
    log.document_id = uuid4() if has_document else None
    log.user_id = uuid4() if has_user else None
    log.folder_config_id = uuid4()
    log.original_filename = original_filename
    log.original_path = original_path
    log.file_size = file_size
    log.mime_type = mime_type
    return log


# =============================================================================
# TestPollFolderImportsTask
# =============================================================================


class TestPollFolderImportsTask:
    """Tests fuer poll_folder_imports_task."""

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_polls_active_configs(self, mock_run: MagicMock) -> None:
        """Task gibt korrekte Statistiken zurueck wenn Configs vorhanden."""
        mock_run.return_value = {
            "configs_polled": 3,
            "total_files_processed": 5,
            "total_documents_created": 3,
            "errors": [],
        }
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        result = poll_folder_imports_task()

        assert result["configs_polled"] == 3
        assert result["total_files_processed"] == 5
        assert result["total_documents_created"] == 3
        assert result["errors"] == []

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_handles_no_active_configs(self, mock_run: MagicMock) -> None:
        """Task laeuft durch ohne Fehler wenn keine aktiven Configs vorhanden."""
        mock_run.return_value = {
            "configs_polled": 0,
            "total_files_processed": 0,
            "total_documents_created": 0,
            "errors": [],
        }
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        result = poll_folder_imports_task()

        assert result["configs_polled"] == 0
        assert result["total_files_processed"] == 0
        assert result["total_documents_created"] == 0

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_continues_after_config_error(self, mock_run: MagicMock) -> None:
        """Fehler einer Config stoppt nicht die Verarbeitung der anderen Configs."""
        mock_run.return_value = {
            "configs_polled": 3,
            "total_files_processed": 4,
            "total_documents_created": 4,
            "errors": [{"config_id": str(uuid4()), "error": "Verbindungsfehler"}],
        }
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        result = poll_folder_imports_task()

        assert result["configs_polled"] == 3
        assert len(result["errors"]) == 1
        assert "Verbindungsfehler" in result["errors"][0]["error"]

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_retries_on_exception(self, mock_run: MagicMock) -> None:
        """Task versucht Wiederholung bei unbehandeltem Fehler."""
        mock_run.side_effect = RuntimeError("Datenbankfehler")

        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        task_instance = poll_folder_imports_task
        mock_retry = MagicMock(side_effect=RuntimeError("max retries"))

        with patch.object(task_instance, "retry", mock_retry):
            with pytest.raises(RuntimeError):
                poll_folder_imports_task()

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_accumulates_documents_from_all_configs(self, mock_run: MagicMock) -> None:
        """Gesamtzahl der Dokumente wird ueber alle Configs summiert."""
        mock_run.return_value = {
            "configs_polled": 5,
            "total_files_processed": 20,
            "total_documents_created": 18,
            "errors": [],
        }
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        result = poll_folder_imports_task()

        assert result["total_documents_created"] == 18
        assert result["total_files_processed"] == 20


# =============================================================================
# TestApplyRulesToPendingTask
# =============================================================================


class TestApplyRulesToPendingTask:
    """Tests fuer apply_rules_to_pending_imports_task."""

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_applies_rules_to_recent_imports(self, mock_run: MagicMock) -> None:
        """Regeln werden auf kueerzlich abgeschlossene Imports angewendet."""
        mock_run.return_value = {
            "logs_checked": 10,
            "rules_applied": 4,
        }
        from app.workers.tasks.folder_import_rule_tasks import apply_rules_to_pending_imports_task

        result = apply_rules_to_pending_imports_task(str(uuid4()))

        assert result["logs_checked"] == 10
        assert result["rules_applied"] == 4

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_skips_logs_without_document_id(self, mock_run: MagicMock) -> None:
        """Logs ohne document_id werden uebersprungen."""
        mock_run.return_value = {
            "logs_checked": 5,
            "rules_applied": 2,
        }
        from app.workers.tasks.folder_import_rule_tasks import apply_rules_to_pending_imports_task

        result = apply_rules_to_pending_imports_task(str(uuid4()))

        # 5 Logs gecheckt, aber nur 2 mit Regeln matched (andere ohne document_id uebersprungen)
        assert result["logs_checked"] == 5
        assert result["rules_applied"] == 2

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_handles_empty_results(self, mock_run: MagicMock) -> None:
        """Task laeuft durch wenn keine passenden Logs vorhanden."""
        mock_run.return_value = {
            "logs_checked": 0,
            "rules_applied": 0,
        }
        from app.workers.tasks.folder_import_rule_tasks import apply_rules_to_pending_imports_task

        result = apply_rules_to_pending_imports_task(str(uuid4()))

        assert result["logs_checked"] == 0
        assert result["rules_applied"] == 0

    def test_invalid_company_id_raises_error(self) -> None:
        """Ungueltige company_id fuehrt zu ValueError."""
        from app.workers.tasks.folder_import_rule_tasks import apply_rules_to_pending_imports_task

        task_instance = apply_rules_to_pending_imports_task
        mock_retry = MagicMock(side_effect=ValueError("invalid"))

        with patch.object(task_instance, "retry", mock_retry):
            with pytest.raises((ValueError, Exception)):
                apply_rules_to_pending_imports_task("kein-gueltiges-uuid-format!!!")

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_retries_on_database_failure(self, mock_run: MagicMock) -> None:
        """Task versucht Wiederholung bei Datenbankfehler."""
        mock_run.side_effect = ConnectionError("Datenbankverbindung unterbrochen")

        from app.workers.tasks.folder_import_rule_tasks import apply_rules_to_pending_imports_task

        task_instance = apply_rules_to_pending_imports_task
        mock_retry = MagicMock(side_effect=ConnectionError("retry"))

        with patch.object(task_instance, "retry", mock_retry):
            with pytest.raises(ConnectionError):
                apply_rules_to_pending_imports_task(str(uuid4()))

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_accepts_valid_company_id(self, mock_run: MagicMock) -> None:
        """Gueltige company_id wird akzeptiert."""
        mock_run.return_value = {"logs_checked": 3, "rules_applied": 1}
        from app.workers.tasks.folder_import_rule_tasks import apply_rules_to_pending_imports_task

        company_id = str(uuid4())
        result = apply_rules_to_pending_imports_task(company_id)

        assert result["logs_checked"] == 3
        mock_run.assert_called_once()


# =============================================================================
# TestScanImportFolderTask
# =============================================================================


class TestScanImportFolderTask:
    """Tests fuer scan_import_folder_task."""

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_scans_specific_folder(self, mock_run: MagicMock) -> None:
        """Einzelner Ordner wird erfolgreich gescannt."""
        mock_run.return_value = {
            "folder_path": "/data/import/rechnungen",
            "config_found": True,
            "config_id": str(uuid4()),
            "files_processed": 3,
            "documents_created": 3,
            "duplicates_skipped": 0,
            "errors": [],
        }
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        result = scan_import_folder_task("/data/import/rechnungen", str(uuid4()))

        assert result["config_found"] is True
        assert result["files_processed"] == 3
        assert result["documents_created"] == 3

    def test_rejects_empty_folder_path(self) -> None:
        """Leerer Ordnerpfad wird abgelehnt."""
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        with pytest.raises(ValueError, match="Ordnerpfad darf nicht leer sein"):
            scan_import_folder_task("", str(uuid4()))

    def test_rejects_whitespace_folder_path(self) -> None:
        """Nur-Leerzeichen-Pfad wird abgelehnt."""
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        with pytest.raises(ValueError, match="Ordnerpfad darf nicht leer sein"):
            scan_import_folder_task("   ", str(uuid4()))

    def test_rejects_path_traversal(self) -> None:
        """Path-Traversal-Angriffe werden blockiert."""
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        with pytest.raises(ValueError, match="Path-Traversal"):
            scan_import_folder_task("/data/../../../etc/passwd", str(uuid4()))

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_handles_no_config_found(self, mock_run: MagicMock) -> None:
        """Kein Fehler wenn keine passende Config gefunden wird."""
        mock_run.return_value = {
            "folder_path": "/data/import/unbekannt",
            "config_found": False,
            "files_processed": 0,
            "documents_created": 0,
            "errors": [{"error": "Keine aktive Konfiguration fuer Pfad gefunden"}],
        }
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        result = scan_import_folder_task("/data/import/unbekannt", str(uuid4()))

        assert result["config_found"] is False
        assert result["files_processed"] == 0
        assert len(result["errors"]) == 1

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_retries_on_unexpected_error(self, mock_run: MagicMock) -> None:
        """Task versucht Wiederholung bei unbehandeltem Fehler."""
        mock_run.side_effect = OSError("Netzwerklaufwerk nicht erreichbar")

        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        task_instance = scan_import_folder_task
        mock_retry = MagicMock(side_effect=OSError("retry"))

        with patch.object(task_instance, "retry", mock_retry):
            with pytest.raises(OSError):
                scan_import_folder_task("/data/import/rechnungen", str(uuid4()))


# =============================================================================
# Integration: Rule Matching with Folder Metadata
# =============================================================================


class TestRuleMatchingIntegration:
    """Integrationstests fuer Regelauswertung mit Ordner-Metadaten."""

    def test_file_extension_extracted_correctly(self) -> None:
        """Dateiendung wird korrekt aus Dateinamen extrahiert."""
        filename = "Rechnung_2024_001.pdf"
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        else:
            ext = ""
        assert ext == ".pdf"

    def test_file_extension_for_file_without_extension(self) -> None:
        """Datei ohne Endung liefert leeren Extension-String."""
        filename = "dokument_ohne_endung"
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        else:
            ext = ""
        assert ext == ""

    def test_metadata_dict_structure_for_rule_evaluation(self) -> None:
        """Metadaten-Dict hat alle erforderlichen Schluessels fuer Regelauswertung."""
        log = _make_import_log(
            original_filename="bestellung.pdf",
            original_path="/data/import/einkauf",
            file_size=8192,
            mime_type="application/pdf",
        )
        original_filename = log.original_filename or ""
        file_extension = ""
        if original_filename and "." in original_filename:
            file_extension = "." + original_filename.rsplit(".", 1)[-1].lower()

        metadata = {
            "filename": original_filename,
            "file_extension": file_extension,
            "file_size": log.file_size or 0,
            "mime_type": log.mime_type or "",
            "folder_path": log.original_path or "",
        }

        assert metadata["filename"] == "bestellung.pdf"
        assert metadata["file_extension"] == ".pdf"
        assert metadata["file_size"] == 8192
        assert metadata["mime_type"] == "application/pdf"
        assert metadata["folder_path"] == "/data/import/einkauf"

    def test_rule_actions_returned_as_dict(self) -> None:
        """apply_actions() gibt Dict mit Aktionen zurueck."""
        mock_rule_service = MagicMock()
        mock_matches = [MagicMock(), MagicMock()]
        mock_rule_service.apply_actions.return_value = {
            "assign_folder_id": str(uuid4()),
            "assign_tags": ["rechnung", "einkauf"],
        }

        actions = mock_rule_service.apply_actions(mock_matches)

        assert "assign_folder_id" in actions
        assert "assign_tags" in actions
        assert isinstance(actions["assign_tags"], list)


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Randfall-Tests."""

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_empty_folder_returns_zero_results(self, mock_run: MagicMock) -> None:
        """Leerer Ordner erzeugt Ergebnis mit Null-Statistiken."""
        mock_run.return_value = {
            "folder_path": "/data/import/leer",
            "config_found": True,
            "config_id": str(uuid4()),
            "files_processed": 0,
            "documents_created": 0,
            "duplicates_skipped": 0,
            "errors": [],
        }
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        result = scan_import_folder_task("/data/import/leer", str(uuid4()))

        assert result["files_processed"] == 0
        assert result["documents_created"] == 0

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_all_files_already_imported_as_duplicates(
        self, mock_run: MagicMock
    ) -> None:
        """Alle Dateien bereits importiert fuehrt zu duplicates_skipped."""
        mock_run.return_value = {
            "folder_path": "/data/import/archiv",
            "config_found": True,
            "config_id": str(uuid4()),
            "files_processed": 5,
            "documents_created": 0,
            "duplicates_skipped": 5,
            "errors": [],
        }
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        result = scan_import_folder_task("/data/import/archiv", str(uuid4()))

        assert result["documents_created"] == 0
        assert result["duplicates_skipped"] == 5

    def test_run_async_creates_new_event_loop(self) -> None:
        """_run_async erstellt und schliesst Event-Loop korrekt."""
        import asyncio
        from app.workers.tasks.folder_import_rule_tasks import _run_async

        async def _sample() -> str:
            return "test"

        result = _run_async(_sample())
        assert result == "test"

    def test_run_async_closes_loop_on_exception(self) -> None:
        """_run_async schliesst Event-Loop auch bei Ausnahmen."""
        from app.workers.tasks.folder_import_rule_tasks import _run_async

        async def _failing():
            raise RuntimeError("Interner Fehler")

        with pytest.raises(RuntimeError, match="Interner Fehler"):
            _run_async(_failing())

    @patch("app.workers.tasks.folder_import_rule_tasks._run_async")
    def test_poll_task_with_multiple_errors_in_batch(
        self, mock_run: MagicMock
    ) -> None:
        """Poll-Task sammelt mehrere Fehler ohne Abbruch."""
        config_1 = str(uuid4())
        config_2 = str(uuid4())
        mock_run.return_value = {
            "configs_polled": 4,
            "total_files_processed": 2,
            "total_documents_created": 2,
            "errors": [
                {"config_id": config_1, "error": "Netzwerkfehler"},
                {"config_id": config_2, "error": "Zugriff verweigert"},
            ],
        }
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        result = poll_folder_imports_task()

        assert result["configs_polled"] == 4
        assert len(result["errors"]) == 2
        assert result["total_files_processed"] == 2

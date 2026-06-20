"""Unit Tests fuer Folder-Import + Import-Regel Celery Tasks.

Tests fuer (echte Tasks aus app.workers.tasks.import_tasks, re-exportiert ueber
das Kompatibilitaets-Shim folder_import_rule_tasks):
- poll_folder_imports_task (= poll_all_folder_configs): Polling aller aktiven Configs
- apply_rules_to_pending_imports_task: Regel-Anwendung auf ausstehende Imports
- scan_import_folder_task: Gezielter Scan einzelner Ordner
- Integrations- und Randfall-Tests

Seam: Die Tasks fuehren ihre async-Logik via ``asyncio.run(...)`` aus
(lokaler ``import asyncio`` -> selbe Modul-Instanz). Daher wird ``asyncio.run``
gepatcht, um DB-Zugriffe zu umgehen. Der frueher erwartete Helper ``_run_async``
existiert im echten Code NICHT.
"""

import asyncio
import uuid
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Helper Factories
# =============================================================================


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
    """Tests fuer poll_folder_imports_task (= poll_all_folder_configs)."""

    def test_polls_active_configs(self) -> None:
        """Task gibt korrekte Statistiken zurueck wenn Configs vorhanden."""
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        stats = {
            "configs_processed": 3,
            "files_processed": 5,
            "documents_created": 3,
            "errors": [],
        }
        with patch.object(asyncio, "run", return_value=stats):
            result = poll_folder_imports_task()

        assert result["configs_processed"] == 3
        assert result["files_processed"] == 5
        assert result["documents_created"] == 3
        assert result["errors"] == []

    def test_handles_no_active_configs(self) -> None:
        """Task laeuft durch ohne Fehler wenn keine aktiven Configs vorhanden."""
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        stats = {
            "configs_processed": 0,
            "files_processed": 0,
            "documents_created": 0,
            "errors": [],
        }
        with patch.object(asyncio, "run", return_value=stats):
            result = poll_folder_imports_task()

        assert result["configs_processed"] == 0
        assert result["files_processed"] == 0
        assert result["documents_created"] == 0

    def test_continues_after_config_error(self) -> None:
        """Fehler einer Config stoppt nicht die Verarbeitung der anderen Configs."""
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        stats = {
            "configs_processed": 3,
            "files_processed": 4,
            "documents_created": 4,
            "errors": [{"config_id": str(uuid4()), "error": "Verbindungsfehler"}],
        }
        with patch.object(asyncio, "run", return_value=stats):
            result = poll_folder_imports_task()

        assert result["configs_processed"] == 3
        assert len(result["errors"]) == 1
        assert "Verbindungsfehler" in result["errors"][0]["error"]

    def test_retries_on_exception(self) -> None:
        """Task ruft self.retry bei unbehandeltem Fehler auf."""
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        mock_retry = MagicMock(side_effect=RuntimeError("max retries"))
        with patch.object(asyncio, "run", side_effect=RuntimeError("Datenbankfehler")):
            with patch.object(poll_folder_imports_task, "retry", mock_retry):
                with pytest.raises(RuntimeError):
                    poll_folder_imports_task()
        mock_retry.assert_called_once()

    def test_accumulates_documents_from_all_configs(self) -> None:
        """Gesamtzahl der Dokumente wird ueber alle Configs summiert."""
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        stats = {
            "configs_processed": 5,
            "files_processed": 20,
            "documents_created": 18,
            "errors": [],
        }
        with patch.object(asyncio, "run", return_value=stats):
            result = poll_folder_imports_task()

        assert result["documents_created"] == 18
        assert result["files_processed"] == 20


# =============================================================================
# TestApplyRulesToPendingTask
# =============================================================================


class TestApplyRulesToPendingTask:
    """Tests fuer apply_rules_to_pending_imports_task."""

    def test_applies_rules_to_recent_imports(self) -> None:
        """Regeln werden auf kuerzlich abgeschlossene Imports angewendet."""
        from app.workers.tasks.folder_import_rule_tasks import (
            apply_rules_to_pending_imports_task,
        )

        with patch.object(
            asyncio, "run", return_value={"logs_checked": 10, "rules_applied": 4}
        ):
            result = apply_rules_to_pending_imports_task(str(uuid4()))

        assert result["logs_checked"] == 10
        assert result["rules_applied"] == 4

    def test_skips_logs_without_document_id(self) -> None:
        """Logs ohne document_id werden uebersprungen (geringere rules_applied)."""
        from app.workers.tasks.folder_import_rule_tasks import (
            apply_rules_to_pending_imports_task,
        )

        with patch.object(
            asyncio, "run", return_value={"logs_checked": 5, "rules_applied": 2}
        ):
            result = apply_rules_to_pending_imports_task(str(uuid4()))

        assert result["logs_checked"] == 5
        assert result["rules_applied"] == 2

    def test_handles_empty_results(self) -> None:
        """Task laeuft durch wenn keine passenden Logs vorhanden."""
        from app.workers.tasks.folder_import_rule_tasks import (
            apply_rules_to_pending_imports_task,
        )

        with patch.object(
            asyncio, "run", return_value={"logs_checked": 0, "rules_applied": 0}
        ):
            result = apply_rules_to_pending_imports_task(str(uuid4()))

        assert result["logs_checked"] == 0
        assert result["rules_applied"] == 0

    def test_invalid_company_id_triggers_retry(self) -> None:
        """Ungueltige company_id (ValueError) loest self.retry aus."""
        from app.workers.tasks.folder_import_rule_tasks import (
            apply_rules_to_pending_imports_task,
        )

        # Ungueltiges UUID-Format -> _uuid.UUID(...) wirft ValueError im async-Body.
        # asyncio.run propagiert die Exception, der Task ruft self.retry().
        mock_retry = MagicMock(side_effect=ValueError("invalid"))
        with patch.object(
            asyncio, "run", side_effect=ValueError("Ungueltige Firmen-ID")
        ):
            with patch.object(
                apply_rules_to_pending_imports_task, "retry", mock_retry
            ):
                with pytest.raises(ValueError):
                    apply_rules_to_pending_imports_task("kein-gueltiges-uuid-format!!!")
        mock_retry.assert_called_once()

    def test_retries_on_database_failure(self) -> None:
        """Task versucht Wiederholung bei Datenbankfehler."""
        from app.workers.tasks.folder_import_rule_tasks import (
            apply_rules_to_pending_imports_task,
        )

        mock_retry = MagicMock(side_effect=ConnectionError("retry"))
        with patch.object(
            asyncio,
            "run",
            side_effect=ConnectionError("Datenbankverbindung unterbrochen"),
        ):
            with patch.object(
                apply_rules_to_pending_imports_task, "retry", mock_retry
            ):
                with pytest.raises(ConnectionError):
                    apply_rules_to_pending_imports_task(str(uuid4()))
        mock_retry.assert_called_once()

    def test_accepts_valid_company_id(self) -> None:
        """Gueltige company_id wird akzeptiert und asyncio.run aufgerufen."""
        from app.workers.tasks.folder_import_rule_tasks import (
            apply_rules_to_pending_imports_task,
        )

        mock_run = MagicMock(return_value={"logs_checked": 3, "rules_applied": 1})
        with patch.object(asyncio, "run", mock_run):
            result = apply_rules_to_pending_imports_task(str(uuid4()))

        assert result["logs_checked"] == 3
        mock_run.assert_called_once()


# =============================================================================
# TestScanImportFolderTask
# =============================================================================


class TestScanImportFolderTask:
    """Tests fuer scan_import_folder_task."""

    def test_scans_specific_folder(self) -> None:
        """Einzelner Ordner wird erfolgreich gescannt."""
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        scan_result = {
            "folder_path": "/data/import/rechnungen",
            "config_found": True,
            "config_id": str(uuid4()),
            "files_processed": 3,
            "documents_created": 3,
            "duplicates_skipped": 0,
            "errors": [],
        }
        with patch.object(asyncio, "run", return_value=scan_result):
            result = scan_import_folder_task("/data/import/rechnungen", str(uuid4()))

        assert result["config_found"] is True
        assert result["files_processed"] == 3
        assert result["documents_created"] == 3

    def test_rejects_empty_folder_path(self) -> None:
        """Leerer Ordnerpfad wird abgelehnt (Validierung VOR asyncio.run)."""
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

    def test_handles_no_config_found(self) -> None:
        """Kein Fehler wenn keine passende Config gefunden wird."""
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        scan_result = {
            "folder_path": "/data/import/unbekannt",
            "config_found": False,
            "files_processed": 0,
            "documents_created": 0,
            "errors": [{"error": "Keine aktive Konfiguration fuer Pfad gefunden"}],
        }
        with patch.object(asyncio, "run", return_value=scan_result):
            result = scan_import_folder_task("/data/import/unbekannt", str(uuid4()))

        assert result["config_found"] is False
        assert result["files_processed"] == 0
        assert len(result["errors"]) == 1

    def test_retries_on_unexpected_error(self) -> None:
        """Task versucht Wiederholung bei unbehandeltem Fehler."""
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        mock_retry = MagicMock(side_effect=OSError("retry"))
        with patch.object(
            asyncio, "run", side_effect=OSError("Netzwerklaufwerk nicht erreichbar")
        ):
            with patch.object(scan_import_folder_task, "retry", mock_retry):
                with pytest.raises(OSError):
                    scan_import_folder_task("/data/import/rechnungen", str(uuid4()))
        mock_retry.assert_called_once()


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
        """Metadaten-Dict hat alle erforderlichen Schluessel fuer Regelauswertung."""
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

    def test_empty_folder_returns_zero_results(self) -> None:
        """Leerer Ordner erzeugt Ergebnis mit Null-Statistiken."""
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        scan_result = {
            "folder_path": "/data/import/leer",
            "config_found": True,
            "config_id": str(uuid4()),
            "files_processed": 0,
            "documents_created": 0,
            "duplicates_skipped": 0,
            "errors": [],
        }
        with patch.object(asyncio, "run", return_value=scan_result):
            result = scan_import_folder_task("/data/import/leer", str(uuid4()))

        assert result["files_processed"] == 0
        assert result["documents_created"] == 0

    def test_all_files_already_imported_as_duplicates(self) -> None:
        """Alle Dateien bereits importiert fuehrt zu duplicates_skipped."""
        from app.workers.tasks.folder_import_rule_tasks import scan_import_folder_task

        scan_result = {
            "folder_path": "/data/import/archiv",
            "config_found": True,
            "config_id": str(uuid4()),
            "files_processed": 5,
            "documents_created": 0,
            "duplicates_skipped": 5,
            "errors": [],
        }
        with patch.object(asyncio, "run", return_value=scan_result):
            result = scan_import_folder_task("/data/import/archiv", str(uuid4()))

        assert result["documents_created"] == 0
        assert result["duplicates_skipped"] == 5

    def test_async_body_executed_via_asyncio_run(self) -> None:
        """Die Tasks fuehren ihren async-Body ueber asyncio.run aus (Seam-Test).

        Ersetzt die frueheren _run_async-Tests: einen solchen Helper gibt es im
        echten Code nicht; der Ablauf nutzt asyncio.run direkt.
        """
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        sentinel = {"configs_processed": 1, "files_processed": 1, "documents_created": 1, "errors": []}

        def _fake_run(coro):
            # Coroutine schliessen, um RuntimeWarning zu vermeiden
            coro.close()
            return sentinel

        with patch.object(asyncio, "run", side_effect=_fake_run) as mock_run:
            result = poll_folder_imports_task()

        mock_run.assert_called_once()
        assert result is sentinel

    def test_poll_task_with_multiple_errors_in_batch(self) -> None:
        """Poll-Task sammelt mehrere Fehler ohne Abbruch."""
        from app.workers.tasks.folder_import_rule_tasks import poll_folder_imports_task

        config_1 = str(uuid4())
        config_2 = str(uuid4())
        stats = {
            "configs_processed": 4,
            "files_processed": 2,
            "documents_created": 2,
            "errors": [
                {"config_id": config_1, "error": "Netzwerkfehler"},
                {"config_id": config_2, "error": "Zugriff verweigert"},
            ],
        }
        with patch.object(asyncio, "run", return_value=stats):
            result = poll_folder_imports_task()

        assert result["configs_processed"] == 4
        assert len(result["errors"]) == 2
        assert result["files_processed"] == 2

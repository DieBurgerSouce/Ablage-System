# -*- coding: utf-8 -*-
"""Unit-Tests fuer die GoBD-Auto-Archivierung des Eingangskanals.

Neuausrichtung Welle D, Defekt 3: Der Beat-Task gobd_auto_archive_task
archiviert Eingangs-Dokumente (email/folder/wa_we_altbestand) automatisch
GoBD-konform. Getestet werden:
- Kategorie-Mapping (Klassifikation -> Retention-Kategorie, Fallback receipt)
- Quellen-Auswahl (odoo_mirror AUSGESCHLOSSEN — der Spiegel archiviert selbst)
- Selektions-Query (Karenz-Cutoff, bereits-archiviert-Skip, Status, Limit)
- Fehler-Isolation pro Dokument
- Enabled-Guard + Beat-/Routen-Registrierung
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# Kategorie-Mapping
# =============================================================================


class TestGobdKategorieMapping:
    def test_rechnung_wird_eingangsrechnung(self):
        from app.workers.tasks.gobd_compliance_tasks import (
            gobd_category_for_document_type,
        )

        # Eingangskanal: Rechnungen sind Eingangsrechnungen (die Odoo-Belege
        # mit out_/in_-Unterscheidung archiviert der Mirror selbst).
        assert gobd_category_for_document_type("invoice") == "invoice_incoming"
        assert gobd_category_for_document_type("credit_note") == "invoice_incoming"
        assert gobd_category_for_document_type("INVOICE") == "invoice_incoming"

    def test_fallback_ist_neutrale_beleg_kategorie(self):
        from app.workers.tasks.gobd_compliance_tasks import (
            gobd_category_for_document_type,
        )

        assert gobd_category_for_document_type(None) == "receipt"
        assert gobd_category_for_document_type("") == "receipt"
        assert gobd_category_for_document_type("unknown") == "receipt"
        assert gobd_category_for_document_type("other") == "receipt"

    def test_weitere_klassifikationen(self):
        from app.workers.tasks.gobd_compliance_tasks import (
            gobd_category_for_document_type,
        )

        assert gobd_category_for_document_type("contract") == "contract"
        assert gobd_category_for_document_type("delivery_note") == "delivery_note"
        assert gobd_category_for_document_type("bank_statement") == "bank_statement"
        assert gobd_category_for_document_type("letter") == "correspondence"

    def test_alle_zielkategorien_existieren_im_retention_service(self):
        """Jede gemappte Kategorie muss eine definierte Aufbewahrungsfrist haben."""
        from app.services.compliance.retention_service import (
            DEFAULT_RETENTION_PERIODS,
        )
        from app.workers.tasks.gobd_compliance_tasks import (
            AUTO_ARCHIVE_FALLBACK_CATEGORY,
            GOBD_CATEGORY_BY_DOCUMENT_TYPE,
        )

        for category in set(GOBD_CATEGORY_BY_DOCUMENT_TYPE.values()):
            assert category in DEFAULT_RETENTION_PERIODS
        assert AUTO_ARCHIVE_FALLBACK_CATEGORY in DEFAULT_RETENTION_PERIODS


# =============================================================================
# Quellen-Auswahl
# =============================================================================


class TestAutoArchiveQuellen:
    def test_eingangskanal_quellen_enthalten(self):
        from app.workers.tasks.gobd_compliance_tasks import (
            AUTO_ARCHIVE_IMPORT_SOURCES,
        )

        assert "email" in AUTO_ARCHIVE_IMPORT_SOURCES
        assert "folder" in AUTO_ARCHIVE_IMPORT_SOURCES
        assert "wa_we_altbestand" in AUTO_ARCHIVE_IMPORT_SOURCES

    def test_odoo_mirror_ist_ausgeschlossen(self):
        """Der Odoo-Spiegel archiviert selbst — Doppel-Archivierung vermeiden."""
        from app.workers.tasks.gobd_compliance_tasks import (
            AUTO_ARCHIVE_IMPORT_SOURCES,
        )

        assert "odoo_mirror" not in AUTO_ARCHIVE_IMPORT_SOURCES


# =============================================================================
# Belegdatum
# =============================================================================


class TestArchiveDocumentDate:
    def test_periode_wird_monatsletzter(self):
        from app.workers.tasks.gobd_compliance_tasks import archive_document_date

        doc = SimpleNamespace(
            document_metadata={"periode": "2019-03"},
            created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        assert archive_document_date(doc) == date(2019, 3, 31)

    def test_schaltjahr_februar(self):
        from app.workers.tasks.gobd_compliance_tasks import archive_document_date

        doc = SimpleNamespace(
            document_metadata={"periode": "2024-02"},
            created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        assert archive_document_date(doc) == date(2024, 2, 29)

    def test_fallback_auf_created_at(self):
        from app.workers.tasks.gobd_compliance_tasks import archive_document_date

        doc = SimpleNamespace(
            document_metadata={"import_source": "email"},
            created_at=datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc),
        )
        assert archive_document_date(doc) == date(2026, 7, 5)

    def test_kaputte_periode_faellt_auf_created_at(self):
        from app.workers.tasks.gobd_compliance_tasks import archive_document_date

        doc = SimpleNamespace(
            document_metadata={"periode": "20XX-YY"},
            created_at=datetime(2026, 7, 5, tzinfo=timezone.utc),
        )
        assert archive_document_date(doc) == date(2026, 7, 5)


# =============================================================================
# Selektions-Query
# =============================================================================


class TestAutoArchiveSelektion:
    def test_query_enthaelt_alle_selektionskriterien(self):
        """Karenz-Cutoff, Quellen-Filter, Status, NOT-EXISTS, Soft-Delete, Limit."""
        from sqlalchemy.dialects import postgresql

        from app.workers.tasks.gobd_compliance_tasks import build_auto_archive_stmt

        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        stmt = build_auto_archive_stmt(cutoff, batch_limit=500)
        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        # (a) bereits archivierte Dokumente ausgeschlossen (Anti-Join)
        assert "NOT (EXISTS" in sql or "NOT EXISTS" in sql
        assert "document_archives" in sql
        # (b) Quellen-Filter auf import_source (JSON-Pfad-Key ist Bind-Param)
        assert "document_metadata" in sql
        # (c) Karenz: created_at < Cutoff
        assert "documents.created_at <" in sql
        # (d) Status abgeschlossen + kein Soft-Delete
        assert "documents.status =" in sql
        assert "documents.deleted_at IS NULL" in sql
        # Batch-Limit
        assert "LIMIT" in sql

        params = compiled.params
        assert cutoff in params.values()
        assert "completed" in params.values()
        assert 500 in params.values()
        # JSON-Pfad-Key als Parameter gebunden
        assert "import_source" in params.values()

    def test_query_parameter_enthalten_nur_eingangsquellen(self):
        from sqlalchemy.dialects import postgresql

        from app.workers.tasks.gobd_compliance_tasks import (
            AUTO_ARCHIVE_IMPORT_SOURCES,
            build_auto_archive_stmt,
        )

        stmt = build_auto_archive_stmt(
            datetime.now(timezone.utc), batch_limit=10
        )
        compiled = stmt.compile(dialect=postgresql.dialect())

        # Der IN-Ausdruck bindet die Quellen-Liste als expanding Parameter
        sources_param = next(
            value
            for value in compiled.params.values()
            if isinstance(value, list)
        )
        assert sources_param == list(AUTO_ARCHIVE_IMPORT_SOURCES)
        assert "odoo_mirror" not in sources_param


# =============================================================================
# Lauf-Logik (Fehler-Isolation, Skips)
# =============================================================================


def _doc(import_source: str = "email", file_path: str = "u/x.pdf"):
    return SimpleNamespace(
        id=uuid4(),
        file_path=file_path,
        company_id=uuid4(),
        document_type="invoice",
        document_metadata={"import_source": import_source},
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


def _db_with_documents(documents):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = documents
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


class TestRunGobdAutoArchive:
    @pytest.mark.asyncio
    async def test_fehler_isolation_pro_dokument(self):
        """Ein fehlerhaftes Dokument kippt den Batch nicht."""
        from app.workers.tasks.gobd_compliance_tasks import _run_gobd_auto_archive

        ok_doc, bad_doc = _doc(), _doc()
        db = _db_with_documents([ok_doc, bad_doc])

        storage = MagicMock()
        storage.download_document = AsyncMock(return_value=b"%PDF-1.4")

        archive_service = MagicMock()
        archive_service.archive_document = AsyncMock(
            side_effect=[MagicMock(), RuntimeError("MinIO weg")]
        )

        with patch(
            "app.services.storage_service.get_storage_service",
            return_value=storage,
        ), patch(
            "app.services.compliance.archive_service.GoBDArchiveService",
            return_value=archive_service,
        ):
            result = await _run_gobd_auto_archive(db, batch_limit=500)

        assert result["candidates"] == 2
        assert result["archived"] == 1
        assert result["errors"] == 1
        assert len(result["error_details"]) == 1
        # Erfolg committet, Fehler rollbackt — pro Dokument isoliert
        db.commit.assert_awaited_once()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_archivierung_nutzt_kategorie_und_systemlauf(self):
        from app.workers.tasks.gobd_compliance_tasks import _run_gobd_auto_archive

        doc = _doc(import_source="folder")
        db = _db_with_documents([doc])

        storage = MagicMock()
        storage.download_document = AsyncMock(return_value=b"%PDF-1.4")
        archive_service = MagicMock()
        archive_service.archive_document = AsyncMock(return_value=MagicMock())

        with patch(
            "app.services.storage_service.get_storage_service",
            return_value=storage,
        ), patch(
            "app.services.compliance.archive_service.GoBDArchiveService",
            return_value=archive_service,
        ):
            result = await _run_gobd_auto_archive(db, batch_limit=500)

        assert result["archived"] == 1
        kwargs = archive_service.archive_document.await_args.kwargs
        assert kwargs["document_id"] == doc.id
        assert kwargs["company_id"] == doc.company_id
        assert kwargs["category"] == "invoice_incoming"  # document_type=invoice
        assert kwargs["archived_by_id"] is None  # Systemlauf (Beat)
        assert kwargs["use_tsa"] is False
        assert kwargs["metadata"]["auto_archived"] is True
        assert kwargs["metadata"]["import_source"] == "folder"
        storage.download_document.assert_awaited_once_with(doc.file_path)

    @pytest.mark.asyncio
    async def test_dokument_ohne_storage_pfad_wird_uebersprungen(self):
        from app.workers.tasks.gobd_compliance_tasks import _run_gobd_auto_archive

        doc = _doc(file_path="")
        db = _db_with_documents([doc])

        storage = MagicMock()
        storage.download_document = AsyncMock()
        archive_service = MagicMock()
        archive_service.archive_document = AsyncMock()

        with patch(
            "app.services.storage_service.get_storage_service",
            return_value=storage,
        ), patch(
            "app.services.compliance.archive_service.GoBDArchiveService",
            return_value=archive_service,
        ):
            result = await _run_gobd_auto_archive(db, batch_limit=500)

        assert result["skipped_no_content"] == 1
        assert result["archived"] == 0
        archive_service.archive_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_keine_kandidaten_kein_storage_zugriff(self):
        from app.workers.tasks.gobd_compliance_tasks import _run_gobd_auto_archive

        db = _db_with_documents([])
        with patch(
            "app.services.storage_service.get_storage_service"
        ) as get_storage:
            result = await _run_gobd_auto_archive(db, batch_limit=500)

        assert result["candidates"] == 0
        assert result["archived"] == 0
        get_storage.assert_not_called()


# =============================================================================
# Task-Guard + Registrierung
# =============================================================================


class TestGobdAutoArchiveTask:
    def test_task_registriert(self):
        from app.workers.tasks.gobd_compliance_tasks import gobd_auto_archive_task

        assert gobd_auto_archive_task.name == (
            "app.workers.tasks.gobd_compliance_tasks.gobd_auto_archive_task"
        )
        assert gobd_auto_archive_task.max_retries == 3

    def test_disabled_guard_verhindert_lauf(self, monkeypatch):
        """GOBD_AUTO_ARCHIVE_ENABLED=False -> No-Op ohne DB-Zugriff."""
        from app.core.config import settings
        from app.workers.tasks.gobd_compliance_tasks import gobd_auto_archive_task

        monkeypatch.setattr(settings, "GOBD_AUTO_ARCHIVE_ENABLED", False)

        result = gobd_auto_archive_task(batch_limit=5)

        assert result["enabled"] is False
        assert result["candidates"] == 0
        assert result["archived"] == 0

    def test_beat_eintrag_taeglich_0330_queue_maintenance(self):
        from app.workers.celery_app import celery_app

        beat = celery_app.conf.beat_schedule
        assert "gobd-auto-archive-daily" in beat
        entry = beat["gobd-auto-archive-daily"]
        assert entry["task"] == (
            "app.workers.tasks.gobd_compliance_tasks.gobd_auto_archive_task"
        )
        assert entry["schedule"].hour == {3}
        assert entry["schedule"].minute == {30}
        assert entry["options"]["queue"] == "maintenance"

    def test_task_route_auf_maintenance_queue(self):
        from app.workers.celery_app import celery_app

        routes = celery_app.conf.task_routes
        route = routes[
            "app.workers.tasks.gobd_compliance_tasks.gobd_auto_archive_task"
        ]
        assert route["queue"] == "maintenance"

    def test_default_konfiguration(self):
        """Default: aktiviert, 3 Tage Karenz (Fenster fuer manuelle Korrekturen)."""
        from app.core.config import settings

        assert settings.GOBD_AUTO_ARCHIVE_ENABLED is True
        assert settings.GOBD_AUTO_ARCHIVE_GRACE_DAYS == 3

# -*- coding: utf-8 -*-
"""Unit-Tests fuer den kanonischen Import-Anlage-Pfad (Welle D, Defekt 1).

Vorher riefen folder_import_service/email_import_service
``DocumentService(self.db).create(...)`` auf — diese Klasse hat weder einen
db-Konstruktor noch eine create()-Methode (Laufzeit-TypeError; zusaetzlich
war der StorageService-Aufruf mit falschen kwargs/Rueckgabe-Annahme kaputt).
Getestet wird der neue Pfad:
- create_import_document: MinIO-Upload (korrekte Signatur) + Document-ORM
  (checksum/company_id/document_metadata) + OCR-Task best-effort
- resolve_import_company_id: Config-Company vor User-Company, Fehler ehrlich
- Verdrahtung: beide Import-Services rufen den kanonischen Pfad mit
  unveraenderten Metadaten (import_source, E-Mail-Felder, Pfad-Feldern)
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# Helpers
# =============================================================================


def _fake_ocr_module() -> ModuleType:
    """Ersatz fuer app.workers.tasks.ocr_tasks (vermeidet Celery/GPU-Import)."""
    module = ModuleType("app.workers.tasks.ocr_tasks")
    module.process_document_task = MagicMock()
    return module


def _storage_mock() -> MagicMock:
    storage = MagicMock()
    storage.upload_document = AsyncMock(
        return_value={"storage_path": "userx/deadbeef.pdf", "size": 4}
    )
    return storage


def _db_mock() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


# =============================================================================
# ascii_safe_filename
# =============================================================================


class TestAsciiSafeFilename:
    def test_umlaute_werden_transliteriert(self):
        from app.services.imports.document_creation import ascii_safe_filename

        assert (
            ascii_safe_filename("Rechnung_März_Müller_süß.pdf")
            == "Rechnung_Maerz_Mueller_suess.pdf"
        )

    def test_nicht_ascii_wird_entfernt_leer_wird_unnamed(self):
        from app.services.imports.document_creation import ascii_safe_filename

        assert ascii_safe_filename("é€") == "unnamed"
        assert ascii_safe_filename("ok.pdf") == "ok.pdf"


# =============================================================================
# resolve_import_company_id
# =============================================================================


class TestResolveImportCompanyId:
    @pytest.mark.asyncio
    async def test_config_company_hat_vorrang(self):
        from app.services.imports.document_creation import (
            resolve_import_company_id,
        )

        db = AsyncMock()
        config_company = uuid4()

        result = await resolve_import_company_id(db, uuid4(), config_company)

        assert result == config_company
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_auf_user_company(self):
        from app.services.imports.document_creation import (
            resolve_import_company_id,
        )

        user_company = uuid4()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = user_company
        db.execute = AsyncMock(return_value=result_mock)

        result = await resolve_import_company_id(db, uuid4(), None)

        assert result == user_company

    @pytest.mark.asyncio
    async def test_ohne_firma_wird_ehrlich_gefehlert(self):
        """Document.company_id ist NOT NULL — ohne Firma kein stiller Import."""
        from app.services.imports.document_creation import (
            resolve_import_company_id,
        )

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError, match="Keine aktive Firma"):
            await resolve_import_company_id(db, uuid4(), None)


# =============================================================================
# create_import_document
# =============================================================================


class TestCreateImportDocument:
    @pytest.mark.asyncio
    async def test_anlage_pfad_erzeugt_document_und_storage_call(self):
        """Kern-Regression Defekt 1: Storage-Upload + Document-Zeile + OCR-Task."""
        from app.services.imports.document_creation import create_import_document

        db = _db_mock()
        storage = _storage_mock()
        ocr_module = _fake_ocr_module()
        user_id, company_id = uuid4(), uuid4()
        metadata = {"import_source": "folder", "original_path": "C:/Import/a.pdf"}

        with patch(
            "app.services.storage_service.get_storage_service",
            return_value=storage,
        ), patch.dict(sys.modules, {"app.workers.tasks.ocr_tasks": ocr_module}):
            doc_id = await create_import_document(
                db,
                user_id=user_id,
                company_id=company_id,
                content=b"%PDF",
                filename="Rechnung_März.pdf",
                original_filename="Rechnung_März.pdf",
                mime_type="application/pdf",
                file_size=4,
                file_hash="cafe" * 16,
                import_metadata=metadata,
                auto_ocr=True,
            )

        assert isinstance(doc_id, UUID)

        # Storage: korrekte kwargs (file_data/content_type — NICHT die alten
        # kaputten content/mime_type) + ASCII-sicherer Objektname
        storage_kwargs = storage.upload_document.await_args.kwargs
        assert storage_kwargs["file_data"] == b"%PDF"
        assert storage_kwargs["content_type"] == "application/pdf"
        assert storage_kwargs["filename"] == "Rechnung_Maerz.pdf"
        assert storage_kwargs["user_id"] == str(user_id)

        # Document-ORM-Zeile mit allen Pflichtfeldern
        document = db.add.call_args_list[0].args[0]
        assert document.id == doc_id
        assert document.checksum == "cafe" * 16
        assert document.company_id == company_id
        assert document.owner_id == user_id
        assert document.file_path == "userx/deadbeef.pdf"
        assert document.original_filename == "Rechnung_März.pdf"
        assert document.status == "pending"
        assert document.document_metadata == metadata
        # Original-Metadaten-Dict wird nicht geteilt (Neuzuweisungs-Muster)
        assert document.document_metadata is not metadata

        # Erst Commit (Zeile persistiert), dann OCR-Task
        db.commit.assert_awaited()
        ocr_kwargs = ocr_module.process_document_task.apply_async.call_args.kwargs
        assert ocr_kwargs["kwargs"]["document_id"] == str(doc_id)
        assert ocr_kwargs["kwargs"]["backend"] == "auto"
        assert ocr_kwargs["kwargs"]["language"] == "de"

    @pytest.mark.asyncio
    async def test_ohne_auto_ocr_status_uploaded_und_kein_task(self):
        from app.services.imports.document_creation import create_import_document

        db = _db_mock()
        storage = _storage_mock()
        ocr_module = _fake_ocr_module()

        with patch(
            "app.services.storage_service.get_storage_service",
            return_value=storage,
        ), patch.dict(sys.modules, {"app.workers.tasks.ocr_tasks": ocr_module}):
            await create_import_document(
                db,
                user_id=uuid4(),
                company_id=uuid4(),
                content=b"x",
                filename="a.pdf",
                original_filename="a.pdf",
                mime_type="application/pdf",
                file_size=1,
                file_hash="ab" * 32,
                import_metadata={"import_source": "email"},
                auto_ocr=False,
            )

        document = db.add.call_args_list[0].args[0]
        assert document.status == "uploaded"
        ocr_module.process_document_task.apply_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_ocr_einreihung_fehlgeschlagen_bricht_import_nicht(self):
        """Redis weg etc.: Status faellt auf 'uploaded', kein Raise."""
        from app.services.imports.document_creation import create_import_document

        db = _db_mock()
        storage = _storage_mock()
        ocr_module = _fake_ocr_module()
        ocr_module.process_document_task.apply_async.side_effect = RuntimeError(
            "Redis nicht erreichbar"
        )

        with patch(
            "app.services.storage_service.get_storage_service",
            return_value=storage,
        ), patch.dict(sys.modules, {"app.workers.tasks.ocr_tasks": ocr_module}):
            doc_id = await create_import_document(
                db,
                user_id=uuid4(),
                company_id=uuid4(),
                content=b"x",
                filename="a.pdf",
                original_filename="a.pdf",
                mime_type="application/pdf",
                file_size=1,
                file_hash="ab" * 32,
                import_metadata={"import_source": "email"},
                auto_ocr=True,
            )

        assert isinstance(doc_id, UUID)
        document = db.add.call_args_list[0].args[0]
        assert document.status == "uploaded"
        assert db.commit.await_count == 2  # Anlage + Status-Rueckfall


# =============================================================================
# Verdrahtung der Import-Services (Defekt-1-Regression)
# =============================================================================


class TestFolderImportNutztKanonischenPfad:
    @pytest.mark.asyncio
    async def test_folder_create_document_ruft_kanonischen_pfad(self, tmp_path):
        from app.services.imports.folder_import_service import FolderImportService

        file_path = tmp_path / "Lieferschein_März.pdf"
        file_path.write_bytes(b"%PDF-scan")

        config = MagicMock()
        config.preserve_filename = True
        config.company_id = None
        config.default_folder_id = None
        config.auto_ocr = True
        config.auto_classify = True

        user_id, company_id, expected_doc_id = uuid4(), uuid4(), uuid4()
        service = FolderImportService(AsyncMock())

        with patch(
            "app.services.imports.document_creation.create_import_document",
            new=AsyncMock(return_value=expected_doc_id),
        ) as create_mock, patch(
            "app.services.imports.document_creation.resolve_import_company_id",
            new=AsyncMock(return_value=company_id),
        ) as resolve_mock:
            result = await service._create_document(
                user_id=user_id,
                config=config,
                file_path=file_path,
                file_hash="ff" * 32,
                file_size=9,
                mime_type="application/pdf",
            )

        assert result == expected_doc_id
        resolve_mock.assert_awaited_once()

        kwargs = create_mock.await_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["company_id"] == company_id
        assert kwargs["content"] == b"%PDF-scan"
        assert kwargs["file_hash"] == "ff" * 32
        assert kwargs["auto_ocr"] is True
        # Bestehende Folder-Metadaten unveraendert erhalten
        metadata = kwargs["import_metadata"]
        assert metadata["import_source"] == "folder"
        assert metadata["original_filename"] == "Lieferschein_März.pdf"
        assert metadata["original_path"] == str(file_path)

    @pytest.mark.asyncio
    async def test_folder_ohne_preserve_filename_uuid_name(self, tmp_path):
        from app.services.imports.folder_import_service import FolderImportService

        file_path = tmp_path / "scan.pdf"
        file_path.write_bytes(b"%PDF")

        config = MagicMock()
        config.preserve_filename = False
        config.company_id = uuid4()
        config.default_folder_id = None
        config.auto_ocr = False
        config.auto_classify = False

        service = FolderImportService(AsyncMock())

        with patch(
            "app.services.imports.document_creation.create_import_document",
            new=AsyncMock(return_value=uuid4()),
        ) as create_mock, patch(
            "app.services.imports.document_creation.resolve_import_company_id",
            new=AsyncMock(return_value=config.company_id),
        ):
            await service._create_document(
                user_id=uuid4(),
                config=config,
                file_path=file_path,
                file_hash="aa" * 32,
                file_size=4,
                mime_type="application/pdf",
            )

        kwargs = create_mock.await_args.kwargs
        # UUID-basierter Zielname, Original bleibt in original_filename
        assert kwargs["filename"].endswith(".pdf")
        assert kwargs["filename"] != "scan.pdf"
        assert UUID(kwargs["filename"].rsplit(".", 1)[0])  # parsebar
        assert kwargs["original_filename"] == "scan.pdf"
        assert kwargs["auto_ocr"] is False


class TestEmailImportNutztKanonischenPfad:
    @pytest.mark.asyncio
    async def test_email_create_document_ruft_kanonischen_pfad(self):
        from datetime import datetime, timezone

        from app.services.imports.email_import_service import (
            EmailAttachment,
            EmailImportService,
        )

        attachment = EmailAttachment(
            filename="Rechnung_Müller.pdf",
            content=b"%PDF-rechnung",
            mime_type="application/pdf",
        )
        email = MagicMock()
        email.from_address = "buchhaltung@mueller-gmbh.de"
        email.subject = "Rechnung 2026-0815"
        email.date = datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)
        email.message_id = "<msg-1@mueller-gmbh.de>"

        config = MagicMock()
        config.company_id = None
        config.default_folder_id = None
        config.auto_ocr = True
        config.auto_classify = True

        user_id, company_id, expected_doc_id = uuid4(), uuid4(), uuid4()
        service = EmailImportService(AsyncMock())

        with patch(
            "app.services.imports.document_creation.create_import_document",
            new=AsyncMock(return_value=expected_doc_id),
        ) as create_mock, patch(
            "app.services.imports.document_creation.resolve_import_company_id",
            new=AsyncMock(return_value=company_id),
        ):
            result = await service._create_document(
                user_id=user_id,
                config=config,
                email=email,
                attachment=attachment,
            )

        assert result == expected_doc_id

        kwargs = create_mock.await_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["company_id"] == company_id
        assert kwargs["content"] == b"%PDF-rechnung"
        assert kwargs["file_hash"] == attachment.file_hash
        assert kwargs["file_size"] == attachment.size
        assert kwargs["auto_ocr"] is True
        # Bestehende E-Mail-Metadaten (Absender-Matching etc.) unveraendert
        metadata = kwargs["import_metadata"]
        assert metadata["import_source"] == "email"
        assert metadata["email_from"] == "buchhaltung@mueller-gmbh.de"
        assert metadata["email_subject"] == "Rechnung 2026-0815"
        assert metadata["email_message_id"] == "<msg-1@mueller-gmbh.de>"
        assert metadata["email_date"] == "2026-07-01T08:00:00+00:00"

    def test_kein_toter_document_service_import_mehr(self):
        """Die Landmine (DocumentService(db).create) ist aus beiden Services raus."""
        import inspect

        from app.services.imports import email_import_service, folder_import_service

        for module in (email_import_service, folder_import_service):
            source = inspect.getsource(module)
            assert (
                "from app.services.document_service import DocumentService"
                not in source
            )
            assert "doc_service.create(" not in source
            assert "doc_service = DocumentService" not in source

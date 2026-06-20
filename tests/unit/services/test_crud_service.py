# -*- coding: utf-8 -*-
"""Tests fuer DocumentCRUDService.

Unit-Tests mit gemockter Datenbankschicht.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestDocumentCRUDServiceImport:
    """Stellt sicher, dass der CRUD-Service importiert werden kann."""

    def test_import_modul(self):
        """CRUD-Service-Modul laesst sich importieren."""
        import app.services.document_services.crud_service as module
        assert module is not None

    def test_import_service_klasse(self):
        """DocumentCRUDService-Klasse kann importiert werden."""
        from app.services.document_services.crud_service import DocumentCRUDService
        assert DocumentCRUDService is not None

    def test_import_factory_funktion(self):
        """get_crud_service Factory-Funktion kann importiert werden."""
        from app.services.document_services.crud_service import get_crud_service
        assert get_crud_service is not None


class TestDocumentCRUDServiceInit:
    """Stellt sicher, dass der CRUD-Service korrekt initialisiert wird."""

    @patch("app.services.document_services.crud_service.get_filter_service")
    def test_instanz_erstellen(self, mock_get_filter_service):
        """DocumentCRUDService kann instanziiert werden."""
        from app.services.document_services.crud_service import DocumentCRUDService

        mock_filter_service = MagicMock()
        mock_get_filter_service.return_value = mock_filter_service

        service = DocumentCRUDService()
        assert service is not None
        assert service._filter_service is mock_filter_service

    @patch("app.services.document_services.crud_service.get_filter_service")
    def test_singleton_factory(self, mock_get_filter_service):
        """get_crud_service gibt immer dieselbe Instanz zurueck."""
        from app.services.document_services.crud_service import get_crud_service

        mock_get_filter_service.return_value = MagicMock()

        # Singleton-State zuruecksetzen
        import app.services.document_services.crud_service as m
        m._crud_service_instance = None

        service1 = get_crud_service()
        service2 = get_crud_service()
        assert service1 is service2


class TestGetDocument:
    """Tests fuer get_document()."""

    @pytest.mark.asyncio
    @patch("app.services.document_services.crud_service.get_filter_service")
    async def test_get_document_nicht_gefunden(self, mock_get_filter_service):
        """get_document gibt None zurueck wenn Dokument nicht existiert."""
        from app.services.document_services.crud_service import DocumentCRUDService

        mock_get_filter_service.return_value = MagicMock()
        service = DocumentCRUDService()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_document(mock_db, uuid4(), uuid4())
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.document_services.crud_service.get_filter_service")
    async def test_get_document_gefunden(self, mock_get_filter_service):
        """get_document ruft _to_detail_response auf wenn Dokument gefunden."""
        from app.services.document_services.crud_service import DocumentCRUDService

        mock_get_filter_service.return_value = MagicMock()
        service = DocumentCRUDService()

        mock_doc = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_response = MagicMock()
        service._to_detail_response = MagicMock(return_value=mock_response)

        result = await service.get_document(mock_db, uuid4(), uuid4())
        assert result is mock_response
        service._to_detail_response.assert_called_once_with(mock_doc)


class TestDeleteDocument:
    """Tests fuer delete_document()."""

    @pytest.mark.asyncio
    @patch("app.services.document_services.crud_service.get_filter_service")
    async def test_delete_nicht_gefunden_gibt_false(self, mock_get_filter_service):
        """delete_document gibt False zurueck wenn Dokument nicht gefunden."""
        from app.services.document_services.crud_service import DocumentCRUDService

        mock_get_filter_service.return_value = MagicMock()
        service = DocumentCRUDService()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.delete_document(mock_db, uuid4(), uuid4())
        assert result is False

    @pytest.mark.asyncio
    @patch("app.services.document_services.crud_service.get_filter_service")
    async def test_delete_gefunden_gibt_true(self, mock_get_filter_service):
        """delete_document gibt True zurueck und loescht das Dokument."""
        from app.services.document_services.crud_service import DocumentCRUDService

        mock_get_filter_service.return_value = MagicMock()
        service = DocumentCRUDService()

        mock_doc = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        service._invalidate_document_cache = AsyncMock()
        service._invalidate_central_cache = AsyncMock()

        result = await service.delete_document(mock_db, uuid4(), uuid4())
        assert result is True
        mock_db.delete.assert_called_once_with(mock_doc)
        mock_db.commit.assert_called_once()


class TestListDocuments:
    """Tests fuer list_documents() Pagination."""

    @pytest.mark.asyncio
    @patch("app.services.document_services.crud_service.get_filter_service")
    async def test_list_ohne_filter(self, mock_get_filter_service):
        """list_documents liefert paginierten Response ohne Filter."""
        from app.services.document_services.crud_service import DocumentCRUDService
        from app.db.models import Document

        mock_filter_service = MagicMock()
        mock_filter_service.build_filter_conditions.return_value = []
        # get_sort_column liefert real eine SQLAlchemy-Spalte (vgl.
        # DocumentFilterService.get_sort_column -> Document.created_at).
        # Ein MagicMock laesst query.order_by(...) mit "ORDER BY expression
        # expected" scheitern, daher echte Spalte mocken.
        mock_filter_service.get_sort_column.return_value = Document.created_at
        mock_get_filter_service.return_value = mock_filter_service

        service = DocumentCRUDService()
        service._to_summary = MagicMock(return_value=MagicMock())

        mock_db = AsyncMock()

        # Ergebnis-Mock fuer Dokumente
        mock_docs_result = MagicMock()
        mock_docs_result.scalars.return_value.all.return_value = []

        # Ergebnis-Mock fuer Count
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_db.execute = AsyncMock(
            side_effect=[mock_docs_result, mock_count_result]
        )

        result = await service.list_documents(mock_db, uuid4())
        assert result.total == 0
        assert result.page == 1
        assert result.documents == []

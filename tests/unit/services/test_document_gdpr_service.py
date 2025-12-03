# -*- coding: utf-8 -*-
"""
Tests für DocumentGDPRService.

Testet GDPR-konforme Soft-Delete, Wiederherstellung und permanente Löschung.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.document_gdpr_service import (
    DocumentGDPRService,
    get_document_gdpr_service,
)


class TestDocumentGDPRService:
    """Tests für DocumentGDPRService."""

    @pytest.fixture
    def service(self):
        """Erstellt DocumentGDPRService-Instanz."""
        return DocumentGDPRService()

    @pytest.fixture
    def mock_db(self):
        """Mock AsyncSession."""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.delete = AsyncMock()
        return db

    @pytest.fixture
    def mock_document(self):
        """Mock Document."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = uuid4()
        doc.filename = "test_document.pdf"
        doc.document_type = "invoice"
        doc.deleted_at = None
        doc.deleted_by_id = None
        doc.document_metadata = {}
        doc.updated_at = datetime.now(timezone.utc)
        return doc

    @pytest.fixture
    def mock_deleted_document(self, mock_document):
        """Mock gelöschtes Document."""
        mock_document.deleted_at = datetime.now(timezone.utc) - timedelta(days=5)
        mock_document.deleted_by_id = mock_document.owner_id
        mock_document.document_metadata = {"deletion_reason": "Test-Löschung"}
        return mock_document

    # Tests für soft_delete_document

    @pytest.mark.asyncio
    async def test_soft_delete_document_success(self, service, mock_db, mock_document):
        """soft_delete_document sollte Dokument als gelöscht markieren."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(service, '_invalidate_caches', new_callable=AsyncMock):
            result = await service.soft_delete_document(
                db=mock_db,
                document_id=mock_document.id,
                user_id=mock_document.owner_id,
                reason="GDPR-Anfrage"
            )

        assert result is not None
        assert result.document_id == mock_document.id
        assert result.deleted_at is not None
        assert mock_document.deleted_at is not None
        assert mock_document.document_metadata["deletion_reason"] == "GDPR-Anfrage"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_document_not_found(self, service, mock_db):
        """soft_delete_document sollte None zurückgeben wenn Dokument nicht existiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.soft_delete_document(
            db=mock_db,
            document_id=uuid4(),
            user_id=uuid4()
        )

        assert result is None
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_soft_delete_document_without_reason(self, service, mock_db, mock_document):
        """soft_delete_document sollte auch ohne Grund funktionieren."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(service, '_invalidate_caches', new_callable=AsyncMock):
            result = await service.soft_delete_document(
                db=mock_db,
                document_id=mock_document.id,
                user_id=mock_document.owner_id
            )

        assert result is not None
        assert "deletion_reason" not in mock_document.document_metadata

    @pytest.mark.asyncio
    async def test_soft_delete_calculates_restore_deadline(self, service, mock_db, mock_document):
        """soft_delete_document sollte Wiederherstellungsfrist berechnen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(service, '_invalidate_caches', new_callable=AsyncMock):
            result = await service.soft_delete_document(
                db=mock_db,
                document_id=mock_document.id,
                user_id=mock_document.owner_id
            )

        # Wiederherstellungsfrist sollte 30 Tage in der Zukunft sein
        expected_deadline = result.deleted_at + timedelta(days=30)
        assert result.can_restore_until == expected_deadline

    # Tests für restore_document

    @pytest.mark.asyncio
    async def test_restore_document_success(self, service, mock_db, mock_deleted_document):
        """restore_document sollte gelöschtes Dokument wiederherstellen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_deleted_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.restore_document(
            db=mock_db,
            document_id=mock_deleted_document.id,
            user_id=mock_deleted_document.owner_id
        )

        assert result is not None
        assert result.document_id == mock_deleted_document.id
        assert mock_deleted_document.deleted_at is None
        assert mock_deleted_document.deleted_by_id is None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_document_removes_deletion_reason(self, service, mock_db, mock_deleted_document):
        """restore_document sollte Löschgrund aus Metadaten entfernen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_deleted_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        await service.restore_document(
            db=mock_db,
            document_id=mock_deleted_document.id,
            user_id=mock_deleted_document.owner_id
        )

        assert "deletion_reason" not in mock_deleted_document.document_metadata

    @pytest.mark.asyncio
    async def test_restore_document_not_found(self, service, mock_db):
        """restore_document sollte None zurückgeben wenn Dokument nicht existiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.restore_document(
            db=mock_db,
            document_id=uuid4(),
            user_id=uuid4()
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_restore_document_expired_retention(self, service, mock_db, mock_deleted_document):
        """restore_document sollte Fehler werfen wenn Frist abgelaufen."""
        # Dokument vor mehr als 30 Tagen gelöscht
        mock_deleted_document.deleted_at = datetime.now(timezone.utc) - timedelta(days=35)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_deleted_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError) as exc:
            await service.restore_document(
                db=mock_db,
                document_id=mock_deleted_document.id,
                user_id=mock_deleted_document.owner_id
            )

        assert "nicht mehr moeglich" in str(exc.value)
        assert "35 Tagen" in str(exc.value)

    # Tests für list_deleted_documents

    @pytest.mark.asyncio
    async def test_list_deleted_documents(self, service, mock_db, mock_deleted_document):
        """list_deleted_documents sollte alle gelöschten Dokumente auflisten."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_deleted_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.list_deleted_documents(
            db=mock_db,
            user_id=mock_deleted_document.owner_id
        )

        assert result.total == 1
        assert len(result.documents) == 1
        assert result.documents[0].id == mock_deleted_document.id
        assert result.documents[0].can_restore is True

    @pytest.mark.asyncio
    async def test_list_deleted_documents_empty(self, service, mock_db):
        """list_deleted_documents sollte leere Liste für User ohne gelöschte Dokumente."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.list_deleted_documents(
            db=mock_db,
            user_id=uuid4()
        )

        assert result.total == 0
        assert len(result.documents) == 0

    @pytest.mark.asyncio
    async def test_list_deleted_documents_calculates_remaining_days(self, service, mock_db, mock_deleted_document):
        """list_deleted_documents sollte verbleibende Tage berechnen."""
        # 5 Tage seit Löschung
        mock_deleted_document.deleted_at = datetime.now(timezone.utc) - timedelta(days=5)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_deleted_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.list_deleted_documents(
            db=mock_db,
            user_id=mock_deleted_document.owner_id
        )

        # 30 - 5 = 25 Tage verbleibend
        assert result.documents[0].days_until_permanent_deletion == 25
        assert result.documents[0].can_restore is True

    @pytest.mark.asyncio
    async def test_list_deleted_documents_expired_not_restorable(self, service, mock_db, mock_deleted_document):
        """Abgelaufene Dokumente sollten nicht wiederherstellbar sein."""
        mock_deleted_document.deleted_at = datetime.now(timezone.utc) - timedelta(days=35)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_deleted_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.list_deleted_documents(
            db=mock_db,
            user_id=mock_deleted_document.owner_id
        )

        assert result.documents[0].days_until_permanent_deletion == 0
        assert result.documents[0].can_restore is False

    # Tests für permanently_delete_expired

    @pytest.mark.asyncio
    async def test_permanently_delete_expired(self, service, mock_db, mock_deleted_document):
        """permanently_delete_expired sollte abgelaufene Dokumente löschen."""
        # Dokument vor mehr als 30 Tagen gelöscht
        mock_deleted_document.deleted_at = datetime.now(timezone.utc) - timedelta(days=35)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_deleted_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        count = await service.permanently_delete_expired(db=mock_db)

        assert count == 1
        mock_db.delete.assert_called_once_with(mock_deleted_document)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_permanently_delete_expired_none(self, service, mock_db):
        """permanently_delete_expired sollte 0 zurückgeben wenn keine abgelaufenen Dokumente."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        count = await service.permanently_delete_expired(db=mock_db)

        assert count == 0
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_permanently_delete_expired_custom_threshold(self, service, mock_db, mock_deleted_document):
        """permanently_delete_expired sollte Custom-Threshold unterstützen."""
        # Dokument vor 10 Tagen gelöscht
        mock_deleted_document.deleted_at = datetime.now(timezone.utc) - timedelta(days=10)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_deleted_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Mit 7-Tage-Threshold sollte das Dokument gelöscht werden
        count = await service.permanently_delete_expired(db=mock_db, days_threshold=7)

        assert count == 1

    @pytest.mark.asyncio
    async def test_permanently_delete_expired_multiple(self, service, mock_db):
        """permanently_delete_expired sollte mehrere Dokumente löschen."""
        docs = []
        for _ in range(5):
            doc = MagicMock()
            doc.id = uuid4()
            doc.deleted_at = datetime.now(timezone.utc) - timedelta(days=35)
            docs.append(doc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = docs
        mock_db.execute = AsyncMock(return_value=mock_result)

        count = await service.permanently_delete_expired(db=mock_db)

        assert count == 5
        assert mock_db.delete.call_count == 5

    # Tests für get_retention_info

    @pytest.mark.asyncio
    async def test_get_retention_info_not_deleted(self, service, mock_db, mock_document):
        """get_retention_info sollte korrekten Status für nicht gelöschtes Dokument."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_retention_info(
            db=mock_db,
            document_id=mock_document.id,
            user_id=mock_document.owner_id
        )

        assert result is not None
        assert result["is_deleted"] is False
        assert result["can_restore"] is False
        assert result["deleted_at"] is None

    @pytest.mark.asyncio
    async def test_get_retention_info_deleted(self, service, mock_db, mock_deleted_document):
        """get_retention_info sollte korrekten Status für gelöschtes Dokument."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_deleted_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_retention_info(
            db=mock_db,
            document_id=mock_deleted_document.id,
            user_id=mock_deleted_document.owner_id
        )

        assert result is not None
        assert result["is_deleted"] is True
        assert result["can_restore"] is True
        assert result["deleted_at"] is not None
        assert result["deletion_reason"] == "Test-Löschung"
        assert result["days_until_permanent_deletion"] > 0
        assert "permanent_deletion_date" in result

    @pytest.mark.asyncio
    async def test_get_retention_info_not_found(self, service, mock_db):
        """get_retention_info sollte None für nicht existierendes Dokument."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_retention_info(
            db=mock_db,
            document_id=uuid4(),
            user_id=uuid4()
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_retention_info_expired(self, service, mock_db, mock_deleted_document):
        """get_retention_info sollte korrekten Status für abgelaufenes Dokument."""
        mock_deleted_document.deleted_at = datetime.now(timezone.utc) - timedelta(days=35)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_deleted_document
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_retention_info(
            db=mock_db,
            document_id=mock_deleted_document.id,
            user_id=mock_deleted_document.owner_id
        )

        assert result["is_deleted"] is True
        assert result["can_restore"] is False
        assert result["days_until_permanent_deletion"] == 0

    # Tests für _invalidate_caches

    @pytest.mark.asyncio
    async def test_invalidate_caches_handles_errors(self, service):
        """_invalidate_caches sollte Fehler loggen aber nicht werfen."""
        with patch('app.services.document_gdpr_service._get_search_service') as mock_search:
            mock_search.side_effect = Exception("Service nicht verfügbar")

            with patch('app.services.document_gdpr_service.invalidate_on_document_change', new_callable=AsyncMock) as mock_invalidate:
                mock_invalidate.side_effect = Exception("Cache nicht verfügbar")

                # Sollte keine Exception werfen
                await service._invalidate_caches(
                    document_id=uuid4(),
                    user_id=uuid4(),
                    reason="test"
                )


class TestDocumentGDPRServiceConstants:
    """Tests für Service-Konstanten."""

    def test_default_retention_days(self):
        """DEFAULT_RETENTION_DAYS sollte 30 sein."""
        assert DocumentGDPRService.DEFAULT_RETENTION_DAYS == 30


class TestDocumentGDPRServiceSingleton:
    """Tests für Singleton-Funktion."""

    def test_get_document_gdpr_service_singleton(self):
        """get_document_gdpr_service sollte immer dieselbe Instanz zurückgeben."""
        s1 = get_document_gdpr_service()
        s2 = get_document_gdpr_service()
        assert s1 is s2

    def test_get_document_gdpr_service_is_initialized(self):
        """Singleton sollte korrekt initialisiert sein."""
        service = get_document_gdpr_service()
        assert service.DEFAULT_RETENTION_DAYS == 30

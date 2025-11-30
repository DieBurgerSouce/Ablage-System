"""
Unit tests for Data Export Service (Art. 20 DSGVO - Datenportabilität).

Tests:
- Export-Anfrage erstellen
- Export generieren
- Export herunterladen
- Abgelaufene Exports bereinigen
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from pathlib import Path

from app.services.data_export_service import DataExportService, EXPORT_EXPIRY_DAYS
from app.db.models import ExportStatus, ExportFormat
from app.core.exceptions import ExportError, UserNotFoundError


@pytest.fixture
def export_service():
    """Create Data Export service instance."""
    return DataExportService()


@pytest.fixture
def mock_user():
    """Create mock user object."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.username = "testuser"
    user.full_name = "Test User"
    user.created_at = datetime.now(timezone.utc)
    user.last_login = datetime.now(timezone.utc)
    user.totp_enabled = False
    user.is_active = True
    return user


@pytest.fixture
def mock_export():
    """Create mock export object."""
    export = MagicMock()
    export.id = uuid4()
    export.user_id = uuid4()
    export.status = ExportStatus.PENDING
    export.format = ExportFormat.JSON
    export.requested_at = datetime.now(timezone.utc)
    export.completed_at = None
    export.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    export.file_path = None
    export.file_size_bytes = None
    export.error_message = None
    export.download_count = 0
    return export


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


class TestCreateExportRequest:
    """Tests for create_export_request method."""

    @pytest.mark.asyncio
    async def test_create_export_success(self, export_service, mock_db, mock_user):
        """Export-Anfrage erfolgreich erstellen."""
        # No existing exports
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        export = await export_service.create_export_request(
            mock_db, mock_user.id, "json"
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_export_already_pending(self, export_service, mock_db, mock_user, mock_export):
        """Fehler wenn bereits Export läuft."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_export
        mock_db.execute.return_value = mock_result

        with pytest.raises(ExportError) as exc_info:
            await export_service.create_export_request(mock_db, mock_user.id)

        assert "bereits ein Export" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_create_export_invalid_format(self, export_service, mock_db, mock_user):
        """Fehler bei ungültigem Format."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ExportError) as exc_info:
            await export_service.create_export_request(mock_db, mock_user.id, "xml")

        assert "Ungültiges Format" in str(exc_info.value.user_message_de)


class TestGenerateExport:
    """Tests for generate_export method."""

    @pytest.mark.asyncio
    async def test_export_not_found(self, export_service, mock_db):
        """Fehler wenn Export nicht existiert."""
        mock_db.get.return_value = None

        with pytest.raises(ExportError) as exc_info:
            await export_service.generate_export(mock_db, uuid4())

        assert "nicht gefunden" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_user_not_found(self, export_service, mock_db, mock_export):
        """Fehler wenn User nicht existiert."""
        mock_db.get.side_effect = [mock_export, None]

        with pytest.raises(UserNotFoundError):
            await export_service.generate_export(mock_db, mock_export.id)


class TestGetDownloadPath:
    """Tests for get_download_path method."""

    @pytest.mark.asyncio
    async def test_download_success(self, export_service, mock_db, mock_export):
        """Download erfolgreich."""
        mock_export.status = ExportStatus.COMPLETED
        mock_export.file_path = "/path/to/export.zip"
        mock_export.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        mock_db.get.return_value = mock_export

        path = await export_service.get_download_path(
            mock_db, mock_export.id, mock_export.user_id
        )

        assert path == "/path/to/export.zip"
        assert mock_export.download_count == 1
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_not_found(self, export_service, mock_db):
        """Fehler wenn Export nicht gefunden."""
        mock_db.get.return_value = None

        with pytest.raises(ExportError) as exc_info:
            await export_service.get_download_path(mock_db, uuid4(), uuid4())

        assert "nicht gefunden" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_download_wrong_user(self, export_service, mock_db, mock_export):
        """Fehler bei falschem Benutzer."""
        mock_db.get.return_value = mock_export
        different_user_id = uuid4()

        with pytest.raises(ExportError) as exc_info:
            await export_service.get_download_path(
                mock_db, mock_export.id, different_user_id
            )

        assert "keine Berechtigung" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_download_not_completed(self, export_service, mock_db, mock_export):
        """Fehler wenn Export nicht fertig."""
        mock_export.status = ExportStatus.PROCESSING
        mock_db.get.return_value = mock_export

        with pytest.raises(ExportError) as exc_info:
            await export_service.get_download_path(
                mock_db, mock_export.id, mock_export.user_id
            )

        assert "nicht bereit" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_download_expired(self, export_service, mock_db, mock_export):
        """Fehler wenn Export abgelaufen."""
        mock_export.status = ExportStatus.COMPLETED
        mock_export.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        mock_db.get.return_value = mock_export

        with pytest.raises(ExportError) as exc_info:
            await export_service.get_download_path(
                mock_db, mock_export.id, mock_export.user_id
            )

        assert "abgelaufen" in str(exc_info.value.user_message_de)


class TestCleanupExpiredExports:
    """Tests for cleanup_expired_exports method."""

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, export_service, mock_db):
        """Abgelaufene Exports bereinigen."""
        expired_export = MagicMock()
        expired_export.id = uuid4()
        expired_export.file_path = None  # No file to delete
        expired_export.status = ExportStatus.COMPLETED

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [expired_export]
        mock_db.execute.return_value = mock_result

        count = await export_service.cleanup_expired_exports(mock_db)

        assert count == 1
        assert expired_export.status == ExportStatus.EXPIRED
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_file(self, export_service, mock_db, tmp_path):
        """Abgelaufene Exports mit Datei bereinigen."""
        # Create temp file
        temp_file = tmp_path / "export.zip"
        temp_file.write_text("test")

        expired_export = MagicMock()
        expired_export.id = uuid4()
        expired_export.file_path = str(temp_file)
        expired_export.status = ExportStatus.COMPLETED

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [expired_export]
        mock_db.execute.return_value = mock_result

        count = await export_service.cleanup_expired_exports(mock_db)

        assert count == 1
        assert not temp_file.exists()  # File should be deleted


class TestCollectUserData:
    """Tests for _collect_user_data method."""

    @pytest.mark.asyncio
    async def test_collect_data_structure(self, export_service, mock_db, mock_user):
        """Prüfe Struktur der gesammelten Daten."""
        # Mock documents
        mock_docs_result = MagicMock()
        mock_docs_result.scalars.return_value.all.return_value = []

        # Mock audit logs
        mock_audit_result = MagicMock()
        mock_audit_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_docs_result, mock_audit_result]

        data = await export_service._collect_user_data(mock_db, mock_user)

        assert "profile" in data
        assert "documents" in data
        assert "activity_log" in data
        assert "export_metadaten" in data

        # Check profile fields
        assert data["profile"]["email"] == mock_user.email
        assert data["profile"]["benutzername"] == mock_user.username

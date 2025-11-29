# -*- coding: utf-8 -*-
"""
Unit-Tests für Storage Service (MinIO).

Testet:
- Upload-Operationen (Dokumente, Thumbnails)
- Download-Operationen
- Presigned URLs
- Lösch-Operationen (einzeln, batch, GDPR)
- Health Checks
- Statistiken
- Fehlerbehandlung

Feinpoliert und durchdacht - Objektspeicher-Tests.
"""

import pytest
from datetime import timedelta
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from io import BytesIO
import hashlib


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_minio_client():
    """Create mock MinIO client."""
    client = Mock()
    client.list_buckets = Mock(return_value=[])
    client.bucket_exists = Mock(return_value=True)
    client.make_bucket = Mock()
    client.put_object = Mock()
    client.get_object = Mock()
    client.remove_object = Mock()
    client.list_objects = Mock(return_value=[])
    client.presigned_get_object = Mock(return_value="https://minio.local/presigned-url")
    return client


@pytest.fixture
def sample_file_data() -> bytes:
    """Provide sample file data."""
    return b"Dies ist ein Testdokument mit deutschen Umlauten: \xc3\xa4\xc3\xb6\xc3\xbc"


@pytest.fixture
def sample_pdf_data() -> bytes:
    """Provide sample PDF-like data."""
    return b"%PDF-1.4 Test document content"


@pytest.fixture
def sample_image_data() -> bytes:
    """Provide sample image data (PNG header)."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@pytest.fixture
def storage_config():
    """Provide storage configuration."""
    return {
        "ENDPOINT": "localhost:9000",
        "ACCESS_KEY": "minioadmin",
        "SECRET_KEY": "minioadmin",
        "SECURE": False,
        "DOCUMENTS_BUCKET": "documents",
        "THUMBNAILS_BUCKET": "thumbnails",
        "EXPORTS_BUCKET": "exports",
        "PRESIGNED_URL_EXPIRY_HOURS": 24,
        "MAX_FILE_SIZE_MB": 50,
    }


# ========================= Configuration Tests =========================


class TestStorageConfig:
    """Tests for StorageConfig class."""

    def test_storage_config_defaults(self):
        """Standardkonfiguration sollte korrekt sein."""
        from app.services.storage_service import StorageConfig

        with patch.dict('os.environ', {}, clear=True):
            config = StorageConfig()

            assert config.ENDPOINT == "localhost:9000"
            assert config.ACCESS_KEY == "minioadmin"
            assert config.DOCUMENTS_BUCKET == "documents"
            assert config.SECURE is False

    def test_storage_config_from_env(self):
        """Konfiguration aus Umgebungsvariablen."""
        from app.services.storage_service import StorageConfig

        env_vars = {
            "MINIO_ENDPOINT": "minio.production:9000",
            "MINIO_ACCESS_KEY": "prod-access-key",
            "MINIO_SECRET_KEY": "prod-secret-key",
            "MINIO_SECURE": "true",
            "MINIO_DOCUMENTS_BUCKET": "prod-documents",
        }

        with patch.dict('os.environ', env_vars):
            config = StorageConfig()

            assert config.ENDPOINT == "minio.production:9000"
            assert config.ACCESS_KEY == "prod-access-key"
            assert config.SECURE is True
            assert config.DOCUMENTS_BUCKET == "prod-documents"


# ========================= Initialization Tests =========================


class TestStorageServiceInitialization:
    """Tests for StorageService initialization."""

    @patch('app.services.storage_service.MINIO_AVAILABLE', True)
    def test_initialization_success(self, mock_minio_client):
        """Erfolgreiche Initialisierung."""
        with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
            from app.services.storage_service import StorageService

            service = StorageService()

            assert service.available is True
            assert service.client is not None

    @patch('app.services.storage_service.MINIO_AVAILABLE', False)
    def test_initialization_without_minio(self):
        """Initialisierung ohne MinIO-Bibliothek."""
        from app.services.storage_service import StorageService

        service = StorageService()

        assert service.available is False

    @patch('app.services.storage_service.MINIO_AVAILABLE', True)
    def test_initialization_connection_failure(self):
        """Initialisierung bei Verbindungsfehler."""
        with patch('app.services.storage_service.Minio') as MockMinio:
            MockMinio.side_effect = Exception("Connection refused")

            from app.services.storage_service import StorageService

            service = StorageService()

            assert service.available is False

    @patch('app.services.storage_service.MINIO_AVAILABLE', True)
    def test_ensure_buckets_created(self, mock_minio_client):
        """Buckets sollten erstellt werden wenn nicht vorhanden."""
        mock_minio_client.bucket_exists.return_value = False

        with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
            from app.services.storage_service import StorageService

            service = StorageService()

            # Should have tried to create 3 buckets
            assert mock_minio_client.make_bucket.call_count == 3


# ========================= Upload Tests =========================


class TestStorageServiceUpload:
    """Tests for upload operations."""

    @pytest.mark.asyncio
    async def test_upload_document_success(self, mock_minio_client, sample_file_data):
        """Dokument erfolgreich hochladen."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.upload_document(
                    file_data=sample_file_data,
                    filename="test_document.pdf",
                    content_type="application/pdf",
                    user_id="user-123"
                )

                assert result["success"] is True
                assert "storage_path" in result
                assert result["bucket"] == "documents"
                assert result["size_bytes"] == len(sample_file_data)
                mock_minio_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_document_generates_hash(self, mock_minio_client, sample_file_data):
        """Upload sollte SHA256-Hash generieren."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.upload_document(
                    file_data=sample_file_data,
                    filename="test.pdf",
                    user_id="user-123"
                )

                expected_hash = hashlib.sha256(sample_file_data).hexdigest()
                assert result["sha256"] == expected_hash

    @pytest.mark.asyncio
    async def test_upload_document_auto_detect_content_type(self, mock_minio_client, sample_pdf_data):
        """Content-Type sollte automatisch erkannt werden."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.upload_document(
                    file_data=sample_pdf_data,
                    filename="document.pdf",
                    user_id="user-123"
                )

                assert result["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_upload_document_anonymous_user(self, mock_minio_client, sample_file_data):
        """Upload ohne User-ID sollte 'anonymous' verwenden."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.upload_document(
                    file_data=sample_file_data,
                    filename="test.pdf"
                )

                assert "anonymous/" in result["storage_path"]

    @pytest.mark.asyncio
    async def test_upload_document_with_metadata(self, mock_minio_client, sample_file_data):
        """Upload mit zusätzlichen Metadaten."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                metadata = {"source": "scan", "priority": "high"}

                result = await service.upload_document(
                    file_data=sample_file_data,
                    filename="test.pdf",
                    metadata=metadata
                )

                assert result["success"] is True
                # Verify metadata was passed to put_object
                call_args = mock_minio_client.put_object.call_args
                assert "metadata" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_upload_document_minio_unavailable(self, sample_file_data):
        """Upload sollte fehlschlagen wenn MinIO nicht verfügbar."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', False):
            from app.services.storage_service import StorageService

            service = StorageService()

            with pytest.raises(RuntimeError, match="MinIO not available"):
                await service.upload_document(
                    file_data=sample_file_data,
                    filename="test.pdf"
                )

    @pytest.mark.asyncio
    async def test_upload_thumbnail_success(self, mock_minio_client, sample_image_data):
        """Thumbnail erfolgreich hochladen."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.upload_thumbnail(
                    thumbnail_data=sample_image_data,
                    document_id="doc-123",
                    format="png"
                )

                assert result == "doc-123/thumbnail.png"
                mock_minio_client.put_object.assert_called()


# ========================= Download Tests =========================


class TestStorageServiceDownload:
    """Tests for download operations."""

    @pytest.mark.asyncio
    async def test_download_document_success(self, mock_minio_client, sample_file_data):
        """Dokument erfolgreich herunterladen."""
        mock_response = Mock()
        mock_response.read.return_value = sample_file_data
        mock_response.close = Mock()
        mock_response.release_conn = Mock()
        mock_minio_client.get_object.return_value = mock_response

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.download_document("user-123/doc.pdf")

                assert result == sample_file_data
                mock_response.close.assert_called_once()
                mock_response.release_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_document_minio_unavailable(self):
        """Download sollte fehlschlagen wenn MinIO nicht verfügbar."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', False):
            from app.services.storage_service import StorageService

            service = StorageService()

            with pytest.raises(RuntimeError, match="MinIO not available"):
                await service.download_document("user-123/doc.pdf")

    @pytest.mark.asyncio
    async def test_download_document_not_found(self, mock_minio_client):
        """Download eines nicht existierenden Dokuments."""
        from app.services.storage_service import S3Error

        mock_minio_client.get_object.side_effect = S3Error(
            "NoSuchKey",
            "The specified key does not exist",
            resource="test.pdf"
        )

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                with pytest.raises(S3Error):
                    await service.download_document("nonexistent/doc.pdf")


# ========================= Presigned URL Tests =========================


class TestStorageServicePresignedUrl:
    """Tests for presigned URL generation."""

    @pytest.mark.asyncio
    async def test_get_presigned_url_success(self, mock_minio_client):
        """Presigned URL erfolgreich generieren."""
        expected_url = "https://minio.local/documents/user-123/doc.pdf?signature=abc"
        mock_minio_client.presigned_get_object.return_value = expected_url

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.get_presigned_url("user-123/doc.pdf")

                assert result == expected_url
                mock_minio_client.presigned_get_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_presigned_url_custom_expiry(self, mock_minio_client):
        """Presigned URL mit benutzerdefinierter Gültigkeit."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                await service.get_presigned_url("user-123/doc.pdf", expiry_hours=48)

                call_args = mock_minio_client.presigned_get_object.call_args
                assert call_args.kwargs["expires"] == timedelta(hours=48)

    @pytest.mark.asyncio
    async def test_get_presigned_url_minio_unavailable(self):
        """Presigned URL sollte fehlschlagen wenn MinIO nicht verfügbar."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', False):
            from app.services.storage_service import StorageService

            service = StorageService()

            with pytest.raises(RuntimeError, match="MinIO not available"):
                await service.get_presigned_url("user-123/doc.pdf")


# ========================= Delete Tests =========================


class TestStorageServiceDelete:
    """Tests for delete operations."""

    @pytest.mark.asyncio
    async def test_delete_document_success(self, mock_minio_client):
        """Dokument erfolgreich löschen."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.delete_document("user-123/doc.pdf")

                assert result is True
                mock_minio_client.remove_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_document_failure(self, mock_minio_client):
        """Löschfehler sollte False zurückgeben."""
        mock_minio_client.remove_object.side_effect = Exception("Delete failed")

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.delete_document("user-123/doc.pdf")

                assert result is False

    @pytest.mark.asyncio
    async def test_delete_document_minio_unavailable(self):
        """Löschen sollte fehlschlagen wenn MinIO nicht verfügbar."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', False):
            from app.services.storage_service import StorageService

            service = StorageService()

            with pytest.raises(RuntimeError, match="MinIO not available"):
                await service.delete_document("user-123/doc.pdf")

    @pytest.mark.asyncio
    async def test_delete_user_documents_success(self, mock_minio_client):
        """Alle Benutzerdokumente löschen (GDPR)."""
        # Mock objects to delete
        mock_obj1 = Mock()
        mock_obj1.object_name = "user-123/doc1.pdf"
        mock_obj2 = Mock()
        mock_obj2.object_name = "user-123/doc2.pdf"

        mock_minio_client.list_objects.return_value = [mock_obj1, mock_obj2]

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.delete_user_documents("user-123")

                assert result == 2
                assert mock_minio_client.remove_object.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_user_documents_empty(self, mock_minio_client):
        """Keine Dokumente zu löschen."""
        mock_minio_client.list_objects.return_value = []

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.delete_user_documents("user-456")

                assert result == 0
                mock_minio_client.remove_object.assert_not_called()


# ========================= Health Check Tests =========================


class TestStorageServiceHealthCheck:
    """Tests for health check."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, mock_minio_client):
        """Gesunder Status."""
        mock_bucket = Mock()
        mock_bucket.name = "documents"
        mock_minio_client.list_buckets.return_value = [mock_bucket]

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.health_check()

                assert result["status"] == "healthy"
                assert result["buckets"] == 1
                assert "documents" in result["available_buckets"]

    @pytest.mark.asyncio
    async def test_health_check_unavailable(self):
        """Nicht verfügbarer Status."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', False):
            from app.services.storage_service import StorageService

            service = StorageService()

            result = await service.health_check()

            assert result["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_minio_client):
        """Ungesunder Status bei Fehler."""
        mock_minio_client.list_buckets.side_effect = Exception("Connection lost")

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()
                # Force client to be set for the test
                service.client = mock_minio_client
                service.available = True

                result = await service.health_check()

                assert result["status"] == "unhealthy"
                assert "error" in result


# ========================= Statistics Tests =========================


class TestStorageServiceStats:
    """Tests for storage statistics."""

    @pytest.mark.asyncio
    async def test_get_storage_stats_success(self, mock_minio_client):
        """Statistiken erfolgreich abrufen."""
        mock_obj = Mock()
        mock_obj.size = 1024

        mock_minio_client.list_objects.return_value = [mock_obj, mock_obj]

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.get_storage_stats()

                assert "documents" in result
                assert "total_size_bytes" in result
                assert "total_count" in result

    @pytest.mark.asyncio
    async def test_get_storage_stats_unavailable(self):
        """Statistiken bei nicht verfügbarem MinIO."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', False):
            from app.services.storage_service import StorageService

            service = StorageService()

            result = await service.get_storage_stats()

            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_storage_stats_error(self, mock_minio_client):
        """Statistiken bei Fehler."""
        mock_minio_client.list_objects.side_effect = Exception("Stats failed")

        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()
                service.client = mock_minio_client
                service.available = True

                result = await service.get_storage_stats()

                assert "error" in result


# ========================= Factory Tests =========================


class TestStorageServiceFactory:
    """Tests for factory function."""

    def test_get_storage_service_singleton(self):
        """get_storage_service sollte Singleton zurückgeben."""
        from app.services.storage_service import get_storage_service, _storage_service
        import app.services.storage_service as module

        # Reset singleton
        module._storage_service = None

        with patch('app.services.storage_service.MINIO_AVAILABLE', False):
            service1 = get_storage_service()
            service2 = get_storage_service()

            assert service1 is service2


# ========================= Edge Cases =========================


class TestStorageServiceEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_upload_unknown_file_type(self, mock_minio_client):
        """Upload mit unbekanntem Dateityp."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.upload_document(
                    file_data=b"unknown content",
                    filename="file.unknown"
                )

                assert result["content_type"] == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_upload_empty_file(self, mock_minio_client):
        """Upload einer leeren Datei."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.upload_document(
                    file_data=b"",
                    filename="empty.pdf"
                )

                assert result["size_bytes"] == 0

    @pytest.mark.asyncio
    async def test_upload_with_special_characters_in_filename(self, mock_minio_client, sample_file_data):
        """Upload mit Sonderzeichen im Dateinamen."""
        with patch('app.services.storage_service.MINIO_AVAILABLE', True):
            with patch('app.services.storage_service.Minio', return_value=mock_minio_client):
                from app.services.storage_service import StorageService

                service = StorageService()

                result = await service.upload_document(
                    file_data=sample_file_data,
                    filename="Prüfbericht_2024_Änderungen.pdf",
                    user_id="user-123"
                )

                assert result["success"] is True

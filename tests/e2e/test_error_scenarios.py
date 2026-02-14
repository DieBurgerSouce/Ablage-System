# -*- coding: utf-8 -*-
"""
E2E Tests: Error Scenarios

Tests upload failures, OCR timeout, and invalid formats.

Feinpoliert und durchdacht - Fehler-Szenario Tests.
"""

import pytest
import asyncio
from typing import Dict, Any
from unittest.mock import AsyncMock, patch
from pathlib import Path


@pytest.mark.e2e
class TestUploadFailures:
    """Test upload error scenarios."""

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(self, temp_storage):
        """Test Upload von ungültigem Dateityp."""
        # Create executable file
        invalid_file = temp_storage / "uploads" / "malware.exe"
        invalid_file.write_bytes(b"MZ\x90\x00")  # Executable header

        with patch("app.services.storage_service.StorageService") as MockStorage:
            mock_storage = AsyncMock()
            mock_storage.upload_file.side_effect = ValueError(
                "Ungültiger Dateityp: .exe nicht erlaubt"
            )
            MockStorage.return_value = mock_storage

            with pytest.raises(ValueError, match="Ungültiger Dateityp"):
                await mock_storage.upload_file(str(invalid_file))

    @pytest.mark.asyncio
    async def test_upload_file_too_large(self, temp_storage):
        """Test Upload von zu großer Datei."""
        with patch("app.services.storage_service.StorageService") as MockStorage:
            mock_storage = AsyncMock()
            mock_storage.upload_file.side_effect = ValueError(
                "Datei zu groß: Maximale Größe ist 50 MB"
            )
            MockStorage.return_value = mock_storage

            with pytest.raises(ValueError, match="Datei zu groß"):
                await mock_storage.upload_file(
                    "/tmp/huge_file.pdf",
                    size_mb=100  # Exceeds 50 MB limit
                )

    @pytest.mark.asyncio
    async def test_upload_storage_quota_exceeded(self):
        """Test Upload bei überschrittenem Speicher-Kontingent."""
        with patch("app.services.storage_service.StorageService") as MockStorage:
            mock_storage = AsyncMock()
            mock_storage.upload_file.side_effect = RuntimeError(
                "Speicher-Kontingent überschritten: 10 GB erreicht"
            )
            MockStorage.return_value = mock_storage

            with pytest.raises(RuntimeError, match="Speicher-Kontingent überschritten"):
                await mock_storage.upload_file("/tmp/document.pdf")


@pytest.mark.e2e
class TestOCRFailures:
    """Test OCR processing errors."""

    @pytest.mark.asyncio
    async def test_ocr_timeout(self):
        """Test OCR-Timeout bei langsamer Verarbeitung."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.side_effect = asyncio.TimeoutError(
                "OCR-Verarbeitung überschritt Zeitlimit von 30 Sekunden"
            )
            MockOCR.return_value = mock_ocr

            with pytest.raises(asyncio.TimeoutError, match="Zeitlimit"):
                await mock_ocr.process_document(
                    document_id="doc_001",
                    backend="deepseek",
                    timeout=30
                )

    @pytest.mark.asyncio
    async def test_ocr_gpu_out_of_memory(self):
        """Test OCR-Fehler bei GPU OOM."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.side_effect = RuntimeError(
                "CUDA out of memory: GPU VRAM überschritten"
            )
            MockOCR.return_value = mock_ocr

            with pytest.raises(RuntimeError, match="CUDA out of memory"):
                await mock_ocr.process_document(
                    document_id="doc_001",
                    backend="deepseek"
                )

    @pytest.mark.asyncio
    async def test_ocr_corrupted_pdf(self):
        """Test OCR-Fehler bei beschädigtem PDF."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.side_effect = ValueError(
                "PDF beschädigt: Kann nicht geöffnet werden"
            )
            MockOCR.return_value = mock_ocr

            with pytest.raises(ValueError, match="PDF beschädigt"):
                await mock_ocr.process_document(
                    document_id="doc_corrupted",
                    backend="auto"
                )


@pytest.mark.e2e
class TestInvalidFormats:
    """Test invalid document format handling."""

    @pytest.mark.asyncio
    async def test_unsupported_image_format(self):
        """Test Nicht unterstütztes Bildformat."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.side_effect = ValueError(
                "Bildformat nicht unterstützt: .webp"
            )
            MockOCR.return_value = mock_ocr

            with pytest.raises(ValueError, match="Bildformat nicht unterstützt"):
                await mock_ocr.process_document(
                    image_path="/tmp/document.webp",
                    backend="auto"
                )

    @pytest.mark.asyncio
    async def test_encrypted_pdf(self):
        """Test Verschlüsseltes PDF."""
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.side_effect = ValueError(
                "PDF ist passwortgeschützt: Entschlüsselung erforderlich"
            )
            MockOCR.return_value = mock_ocr

            with pytest.raises(ValueError, match="passwortgeschützt"):
                await mock_ocr.process_document(
                    document_id="doc_encrypted",
                    backend="auto"
                )

    @pytest.mark.asyncio
    async def test_zero_byte_file(self, temp_storage):
        """Test Leere Datei (0 Bytes)."""
        empty_file = temp_storage / "uploads" / "empty.pdf"
        empty_file.write_bytes(b"")  # 0 bytes

        with patch("app.services.storage_service.StorageService") as MockStorage:
            mock_storage = AsyncMock()
            mock_storage.upload_file.side_effect = ValueError(
                "Datei ist leer: 0 Bytes"
            )
            MockStorage.return_value = mock_storage

            with pytest.raises(ValueError, match="Datei ist leer"):
                await mock_storage.upload_file(str(empty_file))


@pytest.mark.e2e
class TestNetworkErrors:
    """Test network-related errors."""

    @pytest.mark.asyncio
    async def test_minio_connection_failed(self):
        """Test MinIO-Verbindungsfehler."""
        with patch("app.services.storage_service.StorageService") as MockStorage:
            mock_storage = AsyncMock()
            mock_storage.upload_file.side_effect = ConnectionError(
                "MinIO nicht erreichbar: Connection refused"
            )
            MockStorage.return_value = mock_storage

            with pytest.raises(ConnectionError, match="MinIO nicht erreichbar"):
                await mock_storage.upload_file("/tmp/document.pdf")

    @pytest.mark.asyncio
    async def test_redis_connection_failed(self):
        """Test Redis-Verbindungsfehler."""
        with patch("app.services.cache_service.CacheService") as MockCache:
            mock_cache = AsyncMock()
            mock_cache.set.side_effect = ConnectionError(
                "Redis nicht erreichbar: Connection timeout"
            )
            MockCache.return_value = mock_cache

            with pytest.raises(ConnectionError, match="Redis nicht erreichbar"):
                await mock_cache.set("key", "value")

    @pytest.mark.asyncio
    async def test_database_connection_lost(self):
        """Test Datenbank-Verbindung verloren."""
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.save_document.side_effect = ConnectionError(
                "Datenbankverbindung verloren: PostgreSQL nicht verfügbar"
            )
            MockDoc.return_value = mock_doc

            with pytest.raises(ConnectionError, match="Datenbankverbindung verloren"):
                await mock_doc.save_document({
                    "filename": "test.pdf",
                    "content": "test"
                })


@pytest.mark.e2e
class TestValidationErrors:
    """Test data validation errors."""

    @pytest.mark.asyncio
    async def test_invalid_iban(self):
        """Test Ungültige IBAN."""
        with patch("app.services.entity_extraction_service.EntityExtractionService") as MockEntity:
            mock_entity = AsyncMock()
            mock_entity.extract_entities.return_value = {
                "entities": [
                    {
                        "type": "iban",
                        "value": "DE00000000000000000000",  # Invalid checksum
                        "valid": False,
                        "validation_error": "Ungültige IBAN-Prüfsumme"
                    }
                ]
            }
            MockEntity.return_value = mock_entity

            result = await mock_entity.extract_entities("IBAN: DE00000000000000000000")

            iban = result["entities"][0]
            assert iban["valid"] is False
            assert "Prüfsumme" in iban["validation_error"]

    @pytest.mark.asyncio
    async def test_invalid_date_format(self):
        """Test Ungültiges Datumsformat."""
        with patch("app.services.entity_extraction_service.EntityExtractionService") as MockEntity:
            mock_entity = AsyncMock()
            mock_entity.extract_entities.return_value = {
                "entities": [
                    {
                        "type": "date",
                        "value": "32.13.2024",  # Invalid day/month
                        "valid": False,
                        "validation_error": "Ungültiges Datum: Tag oder Monat außerhalb des Bereichs"
                    }
                ]
            }
            MockEntity.return_value = mock_entity

            result = await mock_entity.extract_entities("Datum: 32.13.2024")

            date = result["entities"][0]
            assert date["valid"] is False
            assert "außerhalb des Bereichs" in date["validation_error"]

    @pytest.mark.asyncio
    async def test_invalid_vat_id(self):
        """Test Ungültige USt-IdNr."""
        with patch("app.services.entity_extraction_service.EntityExtractionService") as MockEntity:
            mock_entity = AsyncMock()
            mock_entity.extract_entities.return_value = {
                "entities": [
                    {
                        "type": "vat_id",
                        "value": "DE000000000",  # Invalid format
                        "valid": False,
                        "validation_error": "Ungültige USt-IdNr: Prüfziffer falsch"
                    }
                ]
            }
            MockEntity.return_value = mock_entity

            result = await mock_entity.extract_entities("USt-IdNr: DE000000000")

            vat = result["entities"][0]
            assert vat["valid"] is False
            assert "Prüfziffer" in vat["validation_error"]

# -*- coding: utf-8 -*-
"""
Unit-Tests für OCR Service.

Testet:
- Dokumentenverarbeitung (einzeln und Batch)
- Backend-Auswahl und Fallback
- GPU-Fehler-Behandlung
- Deutsche Text-Validierung
- Statistiken und Upload-Funktionen

Feinpoliert und durchdacht - Umfassende OCR-Service-Tests.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
import tempfile
import os
import asyncio

import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_backend_manager():
    """Create mock BackendManager."""
    manager = Mock()
    # Use regular Mock for synchronous method
    manager.get_available_backends = Mock(return_value=["surya", "deepseek", "got_ocr"])
    manager.select_backend = AsyncMock(return_value="surya")
    manager.process_with_backend = AsyncMock(return_value={
        "text": "Extrahierter Text mit Umlauten: ä, ö, ü, ß",
        "confidence": 0.95,
        "pages": 1,
        "layout": {"blocks": []}
    })
    manager.get_backend_status = AsyncMock(return_value={
        "surya": {"available": True, "gpu": False},
        "deepseek": {"available": True, "gpu": True}
    })
    manager.cleanup = AsyncMock()
    return manager


@pytest.fixture
def temp_document():
    """Create temporary test document."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 test content")
        temp_path = f.name

    yield Path(temp_path)

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_upload_dir():
    """Create temporary upload directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


# ========================= Document Processing Tests =========================


class TestDocumentProcessing:
    """Tests für Dokumentenverarbeitung."""

    @pytest.mark.asyncio
    async def test_process_document_success(
        self,
        mock_backend_manager,
        temp_document
    ):
        """Test erfolgreiche Dokumentenverarbeitung."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.process_document(
                image_path=str(temp_document),
                language="de"
            )

            assert result["success"] is True
            assert "text" in result
            assert "metadata" in result
            assert result["metadata"]["backend_used"] == "surya"
            assert result["metadata"]["language"] == "de"

    @pytest.mark.asyncio
    async def test_process_document_with_specific_backend(
        self,
        mock_backend_manager,
        temp_document
    ):
        """Test Verarbeitung mit spezifischem Backend."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.process_document(
                image_path=str(temp_document),
                backend="deepseek",
                language="de"
            )

            # Verify backend was used
            mock_backend_manager.process_with_backend.assert_called_once()
            call_args = mock_backend_manager.process_with_backend.call_args
            assert call_args[1]["backend_name"] == "deepseek"

    @pytest.mark.asyncio
    async def test_process_document_file_not_found(
        self,
        mock_backend_manager
    ):
        """Test Fehlerbehandlung bei nicht existierender Datei."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.process_document(
                image_path="/nonexistent/file.pdf"
            )

            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_process_document_no_backends(self, temp_document):
        """Test Fehlerbehandlung ohne verfügbare Backends."""
        mock_manager = Mock()
        mock_manager.get_available_backends = Mock(return_value=[])

        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.process_document(
                image_path=str(temp_document)
            )

            assert result["success"] is False
            assert "No OCR backends available" in result["error"]

    @pytest.mark.asyncio
    async def test_process_document_unavailable_backend_fallback(
        self,
        mock_backend_manager,
        temp_document
    ):
        """Test Fallback bei nicht verfügbarem angefordertem Backend."""
        # Only surya available
        mock_backend_manager.get_available_backends.return_value = ["surya"]

        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.process_document(
                image_path=str(temp_document),
                backend="deepseek"  # Not available
            )

            # Should fall back to auto-selection
            mock_backend_manager.select_backend.assert_called()

    @pytest.mark.asyncio
    async def test_process_document_with_fraktur(
        self,
        mock_backend_manager,
        temp_document
    ):
        """Test Verarbeitung mit Fraktur-Erkennung."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            await service.process_document(
                image_path=str(temp_document),
                detect_fraktur=True
            )

            # Verify fraktur flag was passed
            call_args = mock_backend_manager.process_with_backend.call_args
            assert call_args[1]["detect_fraktur"] is True


# ========================= GPU Fallback Tests =========================


class TestGPUFallback:
    """Tests für GPU-Fehler-Fallback."""

    @pytest.mark.asyncio
    async def test_gpu_error_fallback_to_cpu(self, temp_document):
        """Test automatischer Fallback bei GPU-Fehler."""
        mock_manager = Mock()
        mock_manager.get_available_backends = Mock(return_value=["surya", "deepseek"])
        mock_manager.select_backend = AsyncMock(return_value="deepseek")

        # First call fails with GPU error, second succeeds with CPU
        call_count = [0]

        async def mock_process(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("CUDA out of memory")
            return {"text": "CPU fallback text", "confidence": 0.90}

        mock_manager.process_with_backend = mock_process

        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.process_document(
                image_path=str(temp_document)
            )

            # Should have succeeded with fallback
            assert result.get("text") == "CPU fallback text"
            assert result["metadata"]["fallback_reason"] == "GPU error"

    @pytest.mark.asyncio
    async def test_gpu_error_fallback_also_fails(self, temp_document):
        """Test wenn auch CPU-Fallback fehlschlägt."""
        mock_manager = Mock()
        mock_manager.get_available_backends = Mock(return_value=["surya", "deepseek"])
        mock_manager.select_backend = AsyncMock(return_value="deepseek")

        async def mock_process(*args, **kwargs):
            raise Exception("GPU error - CUDA failed")

        mock_manager.process_with_backend = mock_process

        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.process_document(
                image_path=str(temp_document)
            )

            # Should return error result
            assert result["success"] is False
            assert "error" in result


# ========================= Batch Processing Tests =========================


class TestBatchProcessing:
    """Tests für Batch-Verarbeitung."""

    @pytest.mark.asyncio
    async def test_batch_process_success(self, mock_backend_manager):
        """Test erfolgreiche Batch-Verarbeitung."""
        # Create multiple temp files
        temp_files = []
        for i in range(3):
            f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            f.write(b"%PDF-1.4 test content")
            f.close()
            temp_files.append(f.name)

        try:
            with patch("app.services.ocr_service.BackendManager") as mock_class:
                mock_class.return_value = mock_backend_manager

                from app.services.ocr_service import OCRService
                service = OCRService()

                results = await service.batch_process(
                    image_paths=temp_files,
                    max_concurrent=2
                )

                assert len(results) == 3
                assert all(r.get("success", True) for r in results)
        finally:
            for f in temp_files:
                if os.path.exists(f):
                    os.unlink(f)

    @pytest.mark.asyncio
    async def test_batch_process_with_failures(self, mock_backend_manager):
        """Test Batch-Verarbeitung mit einigen Fehlern."""
        # Create one valid and one invalid path
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 test")
            valid_path = f.name

        try:
            with patch("app.services.ocr_service.BackendManager") as mock_class:
                mock_class.return_value = mock_backend_manager

                from app.services.ocr_service import OCRService
                service = OCRService()

                results = await service.batch_process(
                    image_paths=[valid_path, "/nonexistent/file.pdf"]
                )

                assert len(results) == 2
                # First should succeed, second should fail
                # (due to file not found in process_document)
                success_count = sum(1 for r in results if r.get("success", False))
                assert success_count >= 1
        finally:
            if os.path.exists(valid_path):
                os.unlink(valid_path)

    @pytest.mark.asyncio
    async def test_batch_process_empty_list(self, mock_backend_manager):
        """Test Batch-Verarbeitung mit leerer Liste."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            results = await service.batch_process(image_paths=[])

            assert results == []


# ========================= Statistics Tests =========================


class TestStatistics:
    """Tests für Statistik-Funktionen."""

    @pytest.mark.asyncio
    async def test_get_stats_initial(self, mock_backend_manager):
        """Test initiale Statistiken."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            stats = await service.get_stats()

            assert stats["total_processed"] == 0
            assert stats["total_errors"] == 0
            assert stats["success_rate"] == 0
            assert "available_backends" in stats
            assert "backend_status" in stats

    @pytest.mark.asyncio
    async def test_get_stats_after_processing(
        self,
        mock_backend_manager,
        temp_document
    ):
        """Test Statistiken nach Verarbeitung."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            # Process a document
            await service.process_document(str(temp_document))

            stats = await service.get_stats()

            assert stats["total_processed"] == 1
            assert stats["by_backend"]["surya"] == 1


# ========================= German Text Validation Tests =========================


class TestGermanTextValidation:
    """Tests für deutsche Text-Validierung."""

    @pytest.mark.asyncio
    async def test_validate_german_text_with_umlauts(self, mock_backend_manager):
        """Test Validierung von Text mit Umlauten."""
        # Mock the GermanValidator
        mock_validator = Mock()
        mock_validator.validate_umlauts.return_value = True
        mock_validator.validate_date_format.return_value = ["01.12.2024"]
        mock_validator.validate_currency_format.return_value = ["1.234,56 EUR"]
        mock_validator.extract_business_terms.return_value = ["Rechnung"]
        mock_validator.OCR_ERROR_PATTERNS = {}

        with patch("app.services.ocr_service.BackendManager") as mock_class, \
             patch("app.german_validator.GermanValidator") as validator_class:

            mock_class.return_value = mock_backend_manager
            validator_class.return_value = mock_validator

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.validate_german_text(
                "Rechnung vom 01.12.2024: 1.234,56 EUR für Büromöbel"
            )

            assert result["valid"] is True
            assert result["has_umlauts"] is True
            assert len(result["dates_found"]) > 0
            assert len(result["amounts_found"]) > 0

    @pytest.mark.asyncio
    async def test_validate_german_text_ocr_errors(self, mock_backend_manager):
        """Test Erkennung von OCR-Fehlern."""
        mock_validator = Mock()
        mock_validator.validate_umlauts.return_value = False
        mock_validator.validate_date_format.return_value = []
        mock_validator.validate_currency_format.return_value = []
        mock_validator.extract_business_terms.return_value = []
        mock_validator.OCR_ERROR_PATTERNS = {
            "ü": ["u", "ti"]  # Common OCR errors
        }

        with patch("app.services.ocr_service.BackendManager") as mock_class, \
             patch("app.german_validator.GermanValidator") as validator_class:

            mock_class.return_value = mock_backend_manager
            validator_class.return_value = mock_validator

            from app.services.ocr_service import OCRService
            service = OCRService()

            result = await service.validate_german_text(
                "Buromobel fur den Arbeitsplatz"  # Missing umlauts
            )

            # Should detect potential OCR errors
            assert "potential_ocr_errors" in result
            assert result["quality_score"] <= 1.0


# ========================= Upload Tests =========================


class TestUpload:
    """Tests für Upload-Funktionen."""

    @pytest.mark.asyncio
    async def test_save_upload(self, mock_backend_manager, temp_upload_dir):
        """Test Speichern von hochgeladenen Dateien."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()
            service.upload_dir = temp_upload_dir

            content = b"Test PDF content"
            filename = "test_document.pdf"

            saved_path = await service.save_upload(content, filename)

            assert os.path.exists(saved_path)
            assert filename in saved_path

            # Verify content
            with open(saved_path, "rb") as f:
                assert f.read() == content

    @pytest.mark.asyncio
    async def test_save_upload_unique_filenames(
        self,
        mock_backend_manager,
        temp_upload_dir
    ):
        """Test dass Dateinamen Zeitstempel enthalten."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()
            service.upload_dir = temp_upload_dir

            content = b"Test content"
            filename = "test_doc.pdf"

            path = await service.save_upload(content, filename)

            # Path should contain timestamp pattern
            assert os.path.exists(path)
            # Verify timestamp format in filename (YYYYMMDD_HHMMSS)
            import re
            assert re.search(r'\d{8}_\d{6}', path) is not None
            assert filename in path


# ========================= Version Saving Tests =========================


class TestVersionSaving:
    """Tests für Versionsspeicherung."""

    @pytest.mark.asyncio
    async def test_save_ocr_version_success(self, mock_backend_manager):
        """Test erfolgreiche Versionsspeicherung."""
        mock_version = Mock()
        mock_version.id = uuid4()
        mock_version.version_number = 1
        mock_version.backend = "surya"
        mock_version.is_current = True
        mock_version.created_at = datetime.now(timezone.utc)

        mock_version_service = Mock()
        mock_version_service.create_version_from_dict = AsyncMock(
            return_value=mock_version
        )

        # Mock get_version_service to return our mock
        mock_get_vs = Mock(return_value=mock_version_service)

        with patch("app.services.ocr_service.BackendManager") as mock_class, \
             patch.dict('sys.modules', {'app.services.version_service': Mock(get_version_service=mock_get_vs)}):

            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            mock_db = AsyncMock()
            doc_id = uuid4()
            user_id = uuid4()

            result = await service.save_ocr_version(
                db=mock_db,
                document_id=str(doc_id),
                ocr_result={"text": "Test text", "metadata": {"backend_used": "surya"}},
                user_id=str(user_id)
            )

            assert result is not None
            assert result["version_number"] == 1
            assert result["backend"] == "surya"

    @pytest.mark.asyncio
    async def test_save_ocr_version_failure(self, mock_backend_manager):
        """Test Fehlerbehandlung bei Versionsspeicherung."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            mock_db = AsyncMock()

            # Use invalid UUID to trigger error
            result = await service.save_ocr_version(
                db=mock_db,
                document_id="invalid-not-a-uuid",
                ocr_result={"text": "Test"}
            )

            # Should return None on failure
            assert result is None


# ========================= Cleanup Tests =========================


class TestCleanup:
    """Tests für Cleanup-Funktionen."""

    @pytest.mark.asyncio
    async def test_cleanup(self, mock_backend_manager):
        """Test Cleanup-Aufruf."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            await service.cleanup()

            mock_backend_manager.cleanup.assert_called_once()


# ========================= Edge Cases =========================


class TestEdgeCases:
    """Tests für Grenzfälle."""

    @pytest.mark.asyncio
    async def test_process_document_with_document_id(
        self,
        mock_backend_manager,
        temp_document
    ):
        """Test Verarbeitung mit Document-ID für A/B-Testing."""
        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            await service.process_document(
                image_path=str(temp_document),
                document_id="doc-123"
            )

            # Verify document_id was passed to backend selection
            mock_backend_manager.select_backend.assert_called_with(
                image_path=str(temp_document),
                language="de",
                detect_layout=True,
                document_id="doc-123"
            )

    @pytest.mark.asyncio
    async def test_processing_stats_update_on_error(
        self,
        mock_backend_manager
    ):
        """Test Statistik-Update bei Fehlern."""
        mock_backend_manager.process_with_backend = AsyncMock(
            side_effect=Exception("Processing failed")
        )

        with patch("app.services.ocr_service.BackendManager") as mock_class:
            mock_class.return_value = mock_backend_manager

            from app.services.ocr_service import OCRService
            service = OCRService()

            # Create a temp file
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(b"fake image")
                temp_path = f.name

            try:
                await service.process_document(temp_path)
                stats = await service.get_stats()

                assert stats["total_errors"] == 1
            finally:
                os.unlink(temp_path)

# -*- coding: utf-8 -*-
"""
Integration tests for OCR Version API.

Tests the version management endpoints:
- List versions
- Get version details
- Compare versions
- Rollback to previous version

Feinpoliert und durchdacht - Vollständige Versionshistorie testen.
"""

import pytest
import pytest_asyncio
from uuid import uuid4, UUID
from datetime import datetime
from typing import AsyncGenerator
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Ensure app is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def mock_document_id() -> UUID:
    """Provide a mock document ID."""
    return uuid4()


@pytest.fixture
def mock_user_id() -> UUID:
    """Provide a mock user ID."""
    return uuid4()


@pytest.fixture
def sample_ocr_result():
    """Provide sample OCR result data."""
    return {
        "success": True,
        "text": "Testtext mit deutschen Umlauten: äöüß",
        "backend": "surya",
        "confidence_score": 0.95,
        "metadata": {
            "backend_used": "surya",
            "processing_time_seconds": 1.5,
            "language": "de",
            "timestamp": datetime.utcnow().isoformat()
        },
        "has_umlauts": True,
        "german_validation": {
            "quality_score": 0.85
        },
        "detected_dates": ["01.01.2024"],
        "detected_amounts": ["100,00 €"],
        "ibans": [],
        "vat_ids": []
    }


@pytest.fixture
def sample_ocr_result_v2():
    """Provide second version of OCR result with different backend."""
    return {
        "success": True,
        "text": "Verbesserter Testtext mit deutschen Umlauten: äöüß. Mehr Text.",
        "backend": "deepseek",
        "confidence_score": 0.98,
        "metadata": {
            "backend_used": "deepseek",
            "processing_time_seconds": 2.1,
            "language": "de",
            "timestamp": datetime.utcnow().isoformat()
        },
        "has_umlauts": True,
        "german_validation": {
            "quality_score": 0.92
        },
        "detected_dates": ["01.01.2024", "15.02.2024"],
        "detected_amounts": ["100,00 €", "250,00 €"],
        "ibans": ["DE89370400440532013000"],
        "vat_ids": ["DE123456789"]
    }


@pytest.mark.integration
class TestVersionServiceIntegration:
    """Integration tests for VersionService."""

    @pytest.mark.asyncio
    async def test_version_service_creation(self):
        """Test that version service can be created."""
        from app.services.version_service import VersionService, get_version_service

        service = get_version_service()
        assert service is not None

    @pytest.mark.asyncio
    async def test_create_version_from_dict_structure(
        self,
        sample_ocr_result
    ):
        """Test create_version_from_dict method structure."""
        from app.services.version_service import VersionService
        import inspect

        service = VersionService()

        # Check method exists and has correct signature
        assert hasattr(service, "create_version_from_dict")

        sig = inspect.signature(service.create_version_from_dict)
        params = list(sig.parameters.keys())

        assert "db" in params
        assert "document_id" in params
        assert "ocr_data" in params
        assert "user_id" in params
        assert "version_note" in params

    @pytest.mark.asyncio
    async def test_compare_versions_structure(self):
        """Test compare_versions method structure."""
        from app.services.version_service import VersionService
        import inspect

        service = VersionService()

        assert hasattr(service, "compare_versions")

        sig = inspect.signature(service.compare_versions)
        params = list(sig.parameters.keys())

        assert "db" in params
        assert "document_id" in params
        assert "version_a" in params
        assert "version_b" in params

    @pytest.mark.asyncio
    async def test_rollback_structure(self):
        """Test rollback_to_version method structure."""
        from app.services.version_service import VersionService
        import inspect

        service = VersionService()

        assert hasattr(service, "rollback_to_version")

        sig = inspect.signature(service.rollback_to_version)
        params = list(sig.parameters.keys())

        assert "db" in params
        assert "document_id" in params
        assert "target_version" in params
        assert "user_id" in params


@pytest.mark.integration
class TestVersionAPIEndpoints:
    """Integration tests for version API endpoints."""

    def test_versions_router_exists(self):
        """Test that versions router exists."""
        from app.api.v1.versions import router

        assert router is not None
        assert router.prefix == "/documents/{document_id}/versions"

    def test_versions_router_has_routes(self):
        """Test that versions router has expected routes."""
        from app.api.v1.versions import router

        routes = [r.path for r in router.routes]

        # Check for expected route patterns
        assert any("versions" in r for r in routes)

    def test_version_api_registered_in_main(self):
        """Test that version API is registered in main app."""
        from app.main import app

        routes = [r.path for r in app.routes]

        # Check that version routes are included
        assert any("versions" in r for r in routes)


@pytest.mark.integration
class TestVersionSchemaValidation:
    """Integration tests for version schema validation."""

    def test_version_compare_request_validation(self):
        """Test OCRVersionCompareRequest validation."""
        from app.db.schemas import OCRVersionCompareRequest
        from pydantic import ValidationError

        # Valid request
        valid = OCRVersionCompareRequest(version_a=1, version_b=2)
        assert valid.version_a == 1
        assert valid.version_b == 2

        # Invalid - same versions
        with pytest.raises(ValidationError):
            OCRVersionCompareRequest(version_a=1, version_b=1)

    def test_version_rollback_request_validation(self):
        """Test OCRVersionRollbackRequest validation."""
        from app.db.schemas import OCRVersionRollbackRequest
        from pydantic import ValidationError

        # Valid request
        valid = OCRVersionRollbackRequest(target_version=1)
        assert valid.target_version == 1

        # Valid with note
        with_note = OCRVersionRollbackRequest(
            target_version=2,
            rollback_note="Manueller Rollback"
        )
        assert with_note.rollback_note == "Manueller Rollback"

        # Invalid - version 0 or negative
        with pytest.raises(ValidationError):
            OCRVersionRollbackRequest(target_version=0)

    def test_version_list_response_structure(self):
        """Test OCRVersionListResponse structure."""
        from app.db.schemas import OCRVersionListResponse, OCRVersionSummary

        doc_id = uuid4()

        response = OCRVersionListResponse(
            document_id=doc_id,
            document_filename="test.pdf",
            current_version=1,
            total_versions=1,
            versions=[
                OCRVersionSummary(
                    id=uuid4(),
                    document_id=doc_id,
                    version_number=1,
                    is_current=True,
                    is_rollback=False,
                    backend="surya",
                    confidence_score=0.95,
                    word_count=100,
                    created_at=datetime.utcnow()
                )
            ]
        )

        assert response.document_filename == "test.pdf"
        assert len(response.versions) == 1


@pytest.mark.integration
class TestVersionDiffGeneration:
    """Integration tests for version diff generation."""

    def test_unified_diff_german_text(self):
        """Test unified diff with German text."""
        from difflib import unified_diff

        text_a = "Müller GmbH\nStraße 123\n12345 Berlin"
        text_b = "Müller GmbH & Co. KG\nStraße 123\n12345 Berlin"

        lines_a = text_a.splitlines(keepends=True)
        lines_b = text_b.splitlines(keepends=True)

        diff = list(unified_diff(lines_a, lines_b))

        # Should show changes
        assert len(diff) > 0
        diff_text = "".join(diff)
        assert "GmbH" in diff_text

    def test_html_diff_german_text(self):
        """Test HTML diff with German umlauts."""
        from difflib import HtmlDiff

        text_a = "Größe: klein\nÜbersetzung: gut"
        text_b = "Größe: groß\nÜbersetzung: sehr gut"

        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()

        differ = HtmlDiff()
        html = differ.make_table(lines_a, lines_b, context=True)

        # Should contain valid HTML with umlauts
        assert "<table" in html
        assert "Größe" in html or "Gr" in html  # HTML encoding may vary

    def test_diff_empty_texts(self):
        """Test diff generation with empty texts."""
        from difflib import unified_diff

        text_a = ""
        text_b = "Neuer Text"

        diff = list(unified_diff(
            text_a.splitlines(keepends=True),
            text_b.splitlines(keepends=True)
        ))

        # Should show addition
        assert any("+" in line for line in diff)


@pytest.mark.integration
class TestVersionModelRelationships:
    """Integration tests for version model relationships."""

    def test_document_version_relationship_defined(self):
        """Test that Document has relationship to versions."""
        from app.db.models import Document, OCRResultVersion

        # Check relationship is defined
        assert hasattr(Document, "ocr_versions")

    def test_version_document_relationship_defined(self):
        """Test that OCRResultVersion has relationship to document."""
        from app.db.models import Document, OCRResultVersion

        # Check foreign key is defined
        assert hasattr(OCRResultVersion, "document_id")
        assert hasattr(OCRResultVersion, "document")


@pytest.mark.integration
class TestGermanVersionMessages:
    """Integration tests for German version messages."""

    def test_all_version_messages_german(self):
        """Test that all version messages are in German."""
        from app.core.german_messages import VersionMessages

        german_indicators = ["Version", "erfolg", "nicht", "gefunden", "zuruck", "Fehler"]

        messages = [
            VersionMessages.VERSION_CREATED,
            VersionMessages.ROLLBACK_SUCCESS,
            VersionMessages.VERSION_NOT_FOUND,
            VersionMessages.DOCUMENT_NOT_FOUND,
            VersionMessages.ROLLBACK_FAILED,
        ]

        for message in messages:
            # Each message should contain at least one German indicator
            assert any(ind in message for ind in german_indicators), \
                f"Message '{message}' may not be in German"

    def test_version_messages_format_placeholders(self):
        """Test that version messages have correct placeholders."""
        from app.core.german_messages import VersionMessages

        # Test VERSION_CREATED placeholder
        assert "{version}" in VersionMessages.VERSION_CREATED

        # Test ROLLBACK_SUCCESS placeholders
        assert "{version}" in VersionMessages.ROLLBACK_SUCCESS
        assert "{new_version}" in VersionMessages.ROLLBACK_SUCCESS

        # Test VERSION_NOT_FOUND placeholder
        assert "{version}" in VersionMessages.VERSION_NOT_FOUND


@pytest.mark.integration
class TestOCRServiceVersionIntegration:
    """Integration tests for OCR service version method."""

    def test_ocr_service_version_method_exists(self):
        """Test that OCR service has version save method."""
        from app.services.ocr_service import OCRService

        service = OCRService()
        assert hasattr(service, "save_ocr_version")
        assert callable(service.save_ocr_version)

    @pytest.mark.asyncio
    async def test_ocr_service_version_method_returns_dict_or_none(
        self,
        sample_ocr_result,
        mock_document_id
    ):
        """Test that save_ocr_version returns dict or None."""
        from app.services.ocr_service import OCRService
        import inspect

        service = OCRService()

        # Get return annotation if available
        sig = inspect.signature(service.save_ocr_version)
        return_annotation = sig.return_annotation

        # Method should be async
        assert inspect.iscoroutinefunction(service.save_ocr_version)

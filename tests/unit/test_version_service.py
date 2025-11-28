"""
Unit tests for OCR Version Service.

Tests version creation, listing, comparison, and rollback functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4, UUID
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Check if version service dependencies are available
try:
    from app.services.version_service import VersionService
    VERSION_SERVICE_AVAILABLE = True
except ImportError:
    VERSION_SERVICE_AVAILABLE = False

requires_version_service = pytest.mark.skipif(
    not VERSION_SERVICE_AVAILABLE,
    reason="Version service dependencies not installed (pgvector)"
)


@requires_version_service
@pytest.mark.unit
class TestVersionService:
    """Test OCR version service functionality."""

    def setup_method(self):
        """Setup before each test."""
        # Create mock objects
        self.mock_db = AsyncMock()
        self.document_id = uuid4()
        self.user_id = uuid4()

    def _create_mock_version(
        self,
        version_number: int = 1,
        is_current: bool = True,
        backend: str = "surya",
        text: str = "Test extracted text",
        confidence: float = 0.95
    ) -> Mock:
        """Create a mock version object."""
        version = Mock()
        version.id = uuid4()
        version.document_id = self.document_id
        version.version_number = version_number
        version.is_current = is_current
        version.is_rollback = False
        version.rollback_from_version = None
        version.backend = backend
        version.extracted_text = text
        version.confidence_score = confidence
        version.word_count = len(text.split()) if text else 0
        version.char_count = len(text) if text else 0
        version.detected_dates = []
        version.detected_amounts = []
        version.detected_ibans = []
        version.detected_vat_ids = []
        version.business_terms = []
        version.detected_layout = {}
        version.bounding_boxes = []
        version.processing_time_ms = 1500
        version.german_validation_score = 0.85
        version.has_umlauts = True
        version.created_at = datetime.now(timezone.utc)
        version.created_by_id = self.user_id
        version.version_note = f"OCR mit {backend}"
        return version

    @pytest.mark.asyncio
    async def test_version_service_init(self):
        """Test version service initialization."""
        from app.services.version_service import VersionService

        service = VersionService()

        assert service is not None
        assert hasattr(service, "_html_differ")

    @pytest.mark.asyncio
    async def test_get_next_version_number_first_version(self):
        """Test getting next version number when no versions exist."""
        from app.services.version_service import VersionService

        service = VersionService()

        # Mock database response for no existing versions
        mock_result = Mock()
        mock_result.scalar.return_value = None
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        next_version = await service._get_next_version_number(
            self.mock_db,
            self.document_id
        )

        assert next_version == 1

    @pytest.mark.asyncio
    async def test_get_next_version_number_with_existing(self):
        """Test getting next version number with existing versions."""
        from app.services.version_service import VersionService

        service = VersionService()

        # Mock database response with existing versions
        mock_result = Mock()
        mock_result.scalar.return_value = 3  # Max version is 3
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        next_version = await service._get_next_version_number(
            self.mock_db,
            self.document_id
        )

        assert next_version == 4

    def test_ocr_version_diff_calculation(self):
        """Test diff calculation between versions."""
        from app.db.schemas import OCRVersionDiff

        diff = OCRVersionDiff(
            backend_changed=True,
            text_length_delta=100,
            dates_count_delta=2,
            amounts_count_delta=1,
            ibans_count_delta=0,
            vat_ids_count_delta=1,
            confidence_improved=True
        )

        assert diff.backend_changed == True
        assert diff.text_length_delta == 100
        assert diff.confidence_improved == True

    def test_unified_diff_generation(self):
        """Test unified diff generation."""
        from difflib import unified_diff

        text_a = "Zeile 1\nZeile 2\nZeile 3"
        text_b = "Zeile 1\nGeänderte Zeile\nZeile 3"

        lines_a = text_a.splitlines(keepends=True)
        lines_b = text_b.splitlines(keepends=True)

        diff = list(unified_diff(
            lines_a,
            lines_b,
            fromfile="Version 1",
            tofile="Version 2"
        ))

        assert len(diff) > 0
        # Diff should show changes
        diff_text = "".join(diff)
        assert "-Zeile 2" in diff_text or "Zeile 2" in diff_text

    def test_html_diff_generation(self):
        """Test HTML diff generation."""
        from difflib import HtmlDiff

        text_a = "Zeile 1\nZeile 2"
        text_b = "Zeile 1\nGeänderte Zeile"

        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()

        differ = HtmlDiff(wrapcolumn=80)
        html = differ.make_table(
            lines_a,
            lines_b,
            fromdesc="Version 1",
            todesc="Version 2",
            context=True
        )

        assert "<table" in html
        assert "Version 1" in html
        assert "Version 2" in html


@pytest.mark.unit
class TestVersionSchemas:
    """Test version-related Pydantic schemas."""

    def test_ocr_version_summary_schema(self):
        """Test OCRVersionSummary schema."""
        from app.db.schemas import OCRVersionSummary

        summary = OCRVersionSummary(
            id=uuid4(),
            document_id=uuid4(),
            version_number=1,
            is_current=True,
            is_rollback=False,
            backend="surya",
            confidence_score=0.95,
            word_count=100,
            created_at=datetime.now(timezone.utc),
            version_note="Test version"
        )

        assert summary.version_number == 1
        assert summary.is_current == True
        assert summary.backend == "surya"
        assert summary.confidence_score == 0.95

    def test_ocr_version_response_schema(self):
        """Test OCRVersionResponse schema."""
        from app.db.schemas import OCRVersionResponse

        response = OCRVersionResponse(
            id=uuid4(),
            document_id=uuid4(),
            version_number=1,
            is_current=True,
            is_rollback=False,
            rollback_from_version=None,
            backend="surya",
            extracted_text="Testtext mit Umlauten: äöü",
            confidence_score=0.95,
            word_count=5,
            char_count=26,
            detected_dates=[],
            detected_amounts=[],
            detected_ibans=[],
            detected_vat_ids=[],
            business_terms=[],
            processing_time_ms=1500,
            has_umlauts=True,
            created_at=datetime.now(timezone.utc),
            version_note="Test"
        )

        assert response.extracted_text == "Testtext mit Umlauten: äöü"
        assert response.has_umlauts == True

    def test_ocr_version_list_response_schema(self):
        """Test OCRVersionListResponse schema."""
        from app.db.schemas import OCRVersionListResponse, OCRVersionSummary

        list_response = OCRVersionListResponse(
            document_id=uuid4(),
            document_filename="test.pdf",
            current_version=2,
            total_versions=2,
            versions=[
                OCRVersionSummary(
                    id=uuid4(),
                    document_id=uuid4(),
                    version_number=2,
                    is_current=True,
                    is_rollback=False,
                    backend="surya",
                    confidence_score=0.95,
                    word_count=100,
                    created_at=datetime.now(timezone.utc)
                ),
                OCRVersionSummary(
                    id=uuid4(),
                    document_id=uuid4(),
                    version_number=1,
                    is_current=False,
                    is_rollback=False,
                    backend="deepseek",
                    confidence_score=0.90,
                    word_count=95,
                    created_at=datetime.now(timezone.utc)
                )
            ]
        )

        assert list_response.current_version == 2
        assert list_response.total_versions == 2
        assert len(list_response.versions) == 2

    def test_ocr_version_compare_request(self):
        """Test OCRVersionCompareRequest schema."""
        from app.db.schemas import OCRVersionCompareRequest

        request = OCRVersionCompareRequest(
            version_a=1,
            version_b=2
        )

        assert request.version_a == 1
        assert request.version_b == 2

    def test_ocr_version_rollback_request(self):
        """Test OCRVersionRollbackRequest schema."""
        from app.db.schemas import OCRVersionRollbackRequest

        request = OCRVersionRollbackRequest(
            target_version=1,
            rollback_note="Rollback zu Version 1"
        )

        assert request.target_version == 1
        assert "Rollback" in request.rollback_note

    def test_ocr_version_rollback_response(self):
        """Test OCRVersionRollbackResponse schema."""
        from app.db.schemas import OCRVersionRollbackResponse

        response = OCRVersionRollbackResponse(
            success=True,
            new_version_number=3,
            rolled_back_from=1,
            message="Erfolgreich zu Version 1 zuruckgesetzt. Neue Version: 3"
        )

        assert response.success == True
        assert response.new_version_number == 3
        assert response.rolled_back_from == 1


@pytest.mark.unit
class TestVersionMessages:
    """Test German version messages."""

    def test_version_messages_exist(self):
        """Test that version messages class exists."""
        from app.core.german_messages import VersionMessages

        assert hasattr(VersionMessages, "VERSION_CREATED")
        assert hasattr(VersionMessages, "ROLLBACK_SUCCESS")
        assert hasattr(VersionMessages, "VERSION_NOT_FOUND")

    def test_version_created_message(self):
        """Test VERSION_CREATED message formatting."""
        from app.core.german_messages import VersionMessages

        message = VersionMessages.VERSION_CREATED.format(version=1)
        assert "Version 1" in message
        assert "erfolgreich" in message

    def test_rollback_success_message(self):
        """Test ROLLBACK_SUCCESS message formatting."""
        from app.core.german_messages import VersionMessages

        message = VersionMessages.ROLLBACK_SUCCESS.format(version=1, new_version=3)
        assert "Version 1" in message
        assert "3" in message

    def test_version_not_found_message(self):
        """Test VERSION_NOT_FOUND message formatting."""
        from app.core.german_messages import VersionMessages

        message = VersionMessages.VERSION_NOT_FOUND.format(version=5)
        assert "Version 5" in message
        assert "nicht gefunden" in message


@requires_version_service
@pytest.mark.unit
class TestVersionModel:
    """Test OCRResultVersion model."""

    def test_version_model_fields(self):
        """Test that version model has required fields."""
        from app.db.models import OCRResultVersion

        # Check model has required columns
        assert hasattr(OCRResultVersion, "id")
        assert hasattr(OCRResultVersion, "document_id")
        assert hasattr(OCRResultVersion, "version_number")
        assert hasattr(OCRResultVersion, "is_current")
        assert hasattr(OCRResultVersion, "is_rollback")
        assert hasattr(OCRResultVersion, "backend")
        assert hasattr(OCRResultVersion, "extracted_text")
        assert hasattr(OCRResultVersion, "confidence_score")
        assert hasattr(OCRResultVersion, "detected_dates")
        assert hasattr(OCRResultVersion, "detected_ibans")
        assert hasattr(OCRResultVersion, "detected_vat_ids")

    def test_version_model_tablename(self):
        """Test version model table name."""
        from app.db.models import OCRResultVersion

        assert OCRResultVersion.__tablename__ == "ocr_result_versions"


@requires_version_service
@pytest.mark.unit
class TestDocumentVersionFields:
    """Test Document model version fields."""

    def test_document_has_version_fields(self):
        """Test that Document model has version tracking fields."""
        from app.db.models import Document

        assert hasattr(Document, "current_version_number")
        assert hasattr(Document, "total_versions")
        assert hasattr(Document, "ocr_versions")


@requires_version_service
@pytest.mark.unit
class TestOCRServiceVersionIntegration:
    """Test OCR service version integration."""

    def test_ocr_service_has_version_method(self):
        """Test that OCR service has version save method."""
        from app.services.ocr_service import OCRService

        service = OCRService()
        assert hasattr(service, "save_ocr_version")

    @pytest.mark.asyncio
    async def test_save_ocr_version_signature(self):
        """Test save_ocr_version method signature."""
        from app.services.ocr_service import OCRService
        import inspect

        service = OCRService()
        sig = inspect.signature(service.save_ocr_version)

        params = list(sig.parameters.keys())
        assert "db" in params
        assert "document_id" in params
        assert "ocr_result" in params
        assert "user_id" in params
        assert "version_note" in params


@requires_version_service
@pytest.mark.unit
class TestVersionServiceSingleton:
    """Test version service singleton pattern."""

    def test_get_version_service_returns_same_instance(self):
        """Test that get_version_service returns singleton."""
        from app.services.version_service import get_version_service

        service1 = get_version_service()
        service2 = get_version_service()

        assert service1 is service2

    def test_version_service_singleton_type(self):
        """Test version service singleton is correct type."""
        from app.services.version_service import get_version_service, VersionService

        service = get_version_service()
        assert isinstance(service, VersionService)

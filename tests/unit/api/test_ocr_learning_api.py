"""
Tests fuer OCR Self-Learning API Endpoints.

Enterprise-Level Tests mit:
- Security Tests (Auth, Validation)
- Input Validation Tests
- Response Format Tests
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.ocr_learning import (
    CorrectionFeedbackRequest,
    CalibratedConfidenceRequest,
    ABTestStartRequest,
    ABTestEndRequest,
    ALLOWED_OCR_BACKENDS,
    ALLOWED_CORRECTION_TYPES,
    ALLOWED_FIELD_PATTERN,
    ALLOWED_TEST_ID_PATTERN,
    validate_test_id_path_param,
)


# ============================================================================
# INPUT VALIDATION TESTS
# ============================================================================


class TestCorrectionFeedbackRequestValidation:
    """Tests fuer CorrectionFeedbackRequest Validierung."""

    def test_valid_request(self) -> None:
        """Gueltiger Request wird akzeptiert."""
        request = CorrectionFeedbackRequest(
            document_id=uuid4(),
            field_name="invoice_number",
            original_value="INV-12345",
            corrected_value="INV-123456",
            ocr_backend="deepseek",
            original_confidence=0.85,
            correction_type="text",
        )

        assert request.field_name == "invoice_number"
        assert request.ocr_backend == "deepseek"

    def test_invalid_backend_rejected(self) -> None:
        """Ungueltiges Backend wird abgelehnt."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name="test",
                original_value="old",
                corrected_value="new",
                ocr_backend="invalid_backend",  # INVALID
                original_confidence=0.85,
            )

        assert "Ungültiges OCR-Backend" in str(exc_info.value)

    def test_backend_case_insensitive(self) -> None:
        """Backend-Validierung ist case-insensitive."""
        request = CorrectionFeedbackRequest(
            document_id=uuid4(),
            field_name="test",
            original_value="old",
            corrected_value="new",
            ocr_backend="DeepSeek",  # Mixed case
            original_confidence=0.85,
        )

        assert request.ocr_backend == "deepseek"  # Normalized

    def test_invalid_field_name_rejected(self) -> None:
        """Ungueltiger Feldname wird abgelehnt (Injection Prevention)."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name="../../etc/passwd",  # Path Traversal Attempt
                original_value="old",
                corrected_value="new",
                ocr_backend="deepseek",
                original_confidence=0.85,
            )

        assert "Feldname muss mit Buchstabe beginnen" in str(exc_info.value)

    def test_field_name_starts_with_number_rejected(self) -> None:
        """Feldname mit Zahl am Anfang wird abgelehnt."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name="123field",  # Starts with number
                original_value="old",
                corrected_value="new",
                ocr_backend="deepseek",
                original_confidence=0.85,
            )

        assert "Feldname muss mit Buchstabe beginnen" in str(exc_info.value)

    def test_field_name_with_special_chars_rejected(self) -> None:
        """Feldname mit Sonderzeichen wird abgelehnt."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name="field-with-dashes",  # Dashes not allowed
                original_value="old",
                corrected_value="new",
                ocr_backend="deepseek",
                original_confidence=0.85,
            )

        assert "Feldname muss mit Buchstabe beginnen" in str(exc_info.value)

    def test_valid_field_names(self) -> None:
        """Gueltige Feldnamen werden akzeptiert."""
        valid_names = [
            "invoice_number",
            "InvoiceNumber",
            "field123",
            "a",
            "field_with_underscore_123",
        ]

        for name in valid_names:
            request = CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name=name,
                original_value="old",
                corrected_value="new",
                ocr_backend="deepseek",
                original_confidence=0.85,
            )
            assert request.field_name == name

    def test_invalid_correction_type_rejected(self) -> None:
        """Ungueltiger Korrektur-Typ wird abgelehnt."""
        with pytest.raises(ValidationError) as exc_info:
            CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name="test",
                original_value="old",
                corrected_value="new",
                ocr_backend="deepseek",
                original_confidence=0.85,
                correction_type="invalid_type",  # INVALID
            )

        assert "Ungültiger Korrektur-Typ" in str(exc_info.value)

    def test_correction_type_case_insensitive(self) -> None:
        """Korrektur-Typ Validierung ist case-insensitive."""
        request = CorrectionFeedbackRequest(
            document_id=uuid4(),
            field_name="test",
            original_value="old",
            corrected_value="new",
            ocr_backend="deepseek",
            original_confidence=0.85,
            correction_type="TEXT",  # Uppercase
        )

        assert request.correction_type == "text"  # Normalized

    def test_confidence_range_validation(self) -> None:
        """Confidence muss zwischen 0 und 1 liegen."""
        # Too low
        with pytest.raises(ValidationError):
            CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name="test",
                original_value="old",
                corrected_value="new",
                ocr_backend="deepseek",
                original_confidence=-0.1,  # INVALID
            )

        # Too high
        with pytest.raises(ValidationError):
            CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name="test",
                original_value="old",
                corrected_value="new",
                ocr_backend="deepseek",
                original_confidence=1.1,  # INVALID
            )

    def test_max_length_validation(self) -> None:
        """Max Length wird validiert."""
        long_value = "x" * 10001  # Over limit

        with pytest.raises(ValidationError):
            CorrectionFeedbackRequest(
                document_id=uuid4(),
                field_name="test",
                original_value=long_value,  # Too long
                corrected_value="new",
                ocr_backend="deepseek",
                original_confidence=0.85,
            )


class TestCalibratedConfidenceRequestValidation:
    """Tests fuer CalibratedConfidenceRequest Validierung."""

    def test_valid_request(self) -> None:
        """Gueltiger Request wird akzeptiert."""
        request = CalibratedConfidenceRequest(
            backend="deepseek",
            field="invoice_number",
            raw_confidence=0.85,
        )

        assert request.backend == "deepseek"

    def test_invalid_backend_rejected(self) -> None:
        """Ungueltiges Backend wird abgelehnt."""
        with pytest.raises(ValidationError) as exc_info:
            CalibratedConfidenceRequest(
                backend="invalid",
                field="test",
                raw_confidence=0.85,
            )

        assert "Ungültiges OCR-Backend" in str(exc_info.value)

    def test_invalid_field_rejected(self) -> None:
        """Ungueltiges Feld wird abgelehnt."""
        with pytest.raises(ValidationError) as exc_info:
            CalibratedConfidenceRequest(
                backend="deepseek",
                field="sql'; DROP TABLE--",  # SQL Injection Attempt
                raw_confidence=0.85,
            )

        assert "Feldname muss mit Buchstabe beginnen" in str(exc_info.value)


class TestABTestStartRequestValidation:
    """Tests fuer ABTestStartRequest Validierung."""

    def test_valid_request(self) -> None:
        """Gueltiger Request wird akzeptiert."""
        request = ABTestStartRequest(
            test_id="test-2026-01-19",
            candidate_version="candidate_a",
            traffic_split=0.2,
            min_samples=100,
            max_duration_days=7,
        )

        assert request.test_id == "test-2026-01-19"

    def test_valid_test_ids(self) -> None:
        """Gueltige Test-IDs werden akzeptiert."""
        valid_ids = [
            "abc",                    # Min length (3)
            "test-2026-01-19",        # With dashes
            "test_123_abc",           # With underscores
            "A1B2C3",                 # Mixed alphanumeric
            "model-v2-experiment",    # Real-world example
            "a" * 64,                 # Max length (64)
        ]

        for test_id in valid_ids:
            request = ABTestStartRequest(
                test_id=test_id,
                candidate_version="candidate_a",
            )
            assert request.test_id == test_id

    def test_invalid_test_id_too_short(self) -> None:
        """Test-ID unter 3 Zeichen wird abgelehnt."""
        with pytest.raises(ValidationError) as exc_info:
            ABTestStartRequest(
                test_id="ab",  # Only 2 chars
                candidate_version="candidate_a",
            )

        # Should fail min_length or pattern validation
        assert "test_id" in str(exc_info.value).lower()

    def test_invalid_test_id_too_long(self) -> None:
        """Test-ID ueber 64 Zeichen wird abgelehnt."""
        with pytest.raises(ValidationError) as exc_info:
            ABTestStartRequest(
                test_id="a" * 65,  # 65 chars
                candidate_version="candidate_a",
            )

        assert "test_id" in str(exc_info.value).lower()

    def test_invalid_test_id_special_chars(self) -> None:
        """Test-ID mit Sonderzeichen wird abgelehnt."""
        invalid_ids = [
            "../etc/passwd",          # Path traversal
            "test id",                # Space
            "test.id",                # Dot
            "test@id",                # At sign
            "test/id",                # Slash
            "test\\id",               # Backslash
            "<script>",               # XSS attempt
            "'; DROP TABLE--",        # SQL injection
        ]

        for test_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                ABTestStartRequest(
                    test_id=test_id,
                    candidate_version="candidate_a",
                )

            assert "Test-ID" in str(exc_info.value) or "test_id" in str(exc_info.value).lower()

    def test_invalid_test_id_starts_with_special(self) -> None:
        """Test-ID mit Sonderzeichen am Anfang wird abgelehnt."""
        invalid_ids = [
            "-test",                  # Starts with dash
            "_test",                  # Starts with underscore
        ]

        for test_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                ABTestStartRequest(
                    test_id=test_id,
                    candidate_version="candidate_a",
                )

            assert "Test-ID" in str(exc_info.value) or "test_id" in str(exc_info.value).lower()

    def test_traffic_split_range(self) -> None:
        """Traffic Split muss zwischen 0.01 und 0.5 liegen."""
        # Too low
        with pytest.raises(ValidationError):
            ABTestStartRequest(
                test_id="test",
                candidate_version="candidate_a",
                traffic_split=0.001,  # Below 0.01
            )

        # Too high
        with pytest.raises(ValidationError):
            ABTestStartRequest(
                test_id="test",
                candidate_version="candidate_a",
                traffic_split=0.6,  # Above 0.5
            )

    def test_min_samples_range(self) -> None:
        """Min Samples muss >= 10 sein."""
        with pytest.raises(ValidationError):
            ABTestStartRequest(
                test_id="test",
                candidate_version="candidate_a",
                min_samples=5,  # Below 10
            )

    def test_max_duration_range(self) -> None:
        """Max Duration muss zwischen 1 und 30 liegen."""
        # Too low
        with pytest.raises(ValidationError):
            ABTestStartRequest(
                test_id="test",
                candidate_version="candidate_a",
                max_duration_days=0,  # Below 1
            )

        # Too high
        with pytest.raises(ValidationError):
            ABTestStartRequest(
                test_id="test",
                candidate_version="candidate_a",
                max_duration_days=31,  # Above 30
            )


class TestABTestEndRequestValidation:
    """Tests fuer ABTestEndRequest Validierung."""

    def test_valid_actions(self) -> None:
        """Gueltige Actions werden akzeptiert."""
        for action in ["promote", "rollback"]:
            request = ABTestEndRequest(action=action)
            assert request.action == action


# ============================================================================
# WHITELIST TESTS
# ============================================================================


class TestWhitelists:
    """Tests fuer Security Whitelists."""

    def test_allowed_ocr_backends(self) -> None:
        """Alle erlaubten Backends sind definiert."""
        expected = {
            "deepseek",
            "got_ocr",
            "surya",
            "surya_gpu",
            "paddle",
            "qwen",
            "hybrid",
        }
        assert ALLOWED_OCR_BACKENDS == expected

    def test_allowed_correction_types(self) -> None:
        """Alle erlaubten Korrektur-Typen sind definiert."""
        expected = {"text", "amount", "date", "entity"}
        assert ALLOWED_CORRECTION_TYPES == expected

    def test_field_pattern_allows_valid(self) -> None:
        """Field Pattern erlaubt gueltige Namen."""
        valid = [
            "field",
            "Field",
            "field123",
            "field_name",
            "FIELD_NAME_123",
            "a",
        ]
        for name in valid:
            assert ALLOWED_FIELD_PATTERN.match(name), f"{name} should be valid"

    def test_field_pattern_rejects_invalid(self) -> None:
        """Field Pattern lehnt ungueltige Namen ab."""
        invalid = [
            "123field",  # Starts with number
            "_field",    # Starts with underscore
            "field-name", # Contains dash
            "field.name", # Contains dot
            "field name", # Contains space
            "",           # Empty
            "../passwd",  # Path traversal
        ]
        for name in invalid:
            assert not ALLOWED_FIELD_PATTERN.match(name), f"{name} should be invalid"

    def test_test_id_pattern_allows_valid(self) -> None:
        """Test-ID Pattern erlaubt gueltige IDs."""
        valid = [
            "abc",                    # Min length
            "test123",                # Alphanumeric
            "test-id",                # With dash
            "test_id",                # With underscore
            "Test-ID-2026",           # Mixed
            "a" + "b" * 63,           # Max length (64)
        ]
        for test_id in valid:
            assert ALLOWED_TEST_ID_PATTERN.match(test_id), f"{test_id} should be valid"

    def test_test_id_pattern_rejects_invalid(self) -> None:
        """Test-ID Pattern lehnt ungueltige IDs ab."""
        invalid = [
            "ab",                     # Too short (2 chars)
            "-test",                  # Starts with dash
            "_test",                  # Starts with underscore
            "test.id",                # Contains dot
            "test id",                # Contains space
            "test@id",                # Contains special char
            "../passwd",              # Path traversal
            "",                       # Empty
            "a" + "b" * 64,           # Too long (65 chars)
        ]
        for test_id in invalid:
            assert not ALLOWED_TEST_ID_PATTERN.match(test_id), f"{test_id} should be invalid"


class TestValidateTestIdPathParam:
    """Tests fuer validate_test_id_path_param Funktion."""

    def test_valid_test_id_passes(self) -> None:
        """Gueltige Test-ID wird durchgelassen."""
        result = validate_test_id_path_param("valid-test-id")
        assert result == "valid-test-id"

    def test_invalid_test_id_raises_http_exception(self) -> None:
        """Ungueltige Test-ID wirft HTTPException mit Status 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_test_id_path_param("../etc/passwd")

        assert exc_info.value.status_code == 400
        assert "Test-ID" in exc_info.value.detail

    def test_too_short_raises_http_exception(self) -> None:
        """Zu kurze Test-ID wirft HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            validate_test_id_path_param("ab")

        assert exc_info.value.status_code == 400

    def test_special_chars_raise_http_exception(self) -> None:
        """Test-ID mit Sonderzeichen wirft HTTPException."""
        malicious_ids = [
            "'; DROP TABLE tests--",   # SQL injection
            "<script>alert(1)</script>",  # XSS
            "test\x00id",              # Null byte
            "test\nid",                # Newline
        ]

        for test_id in malicious_ids:
            with pytest.raises(HTTPException) as exc_info:
                validate_test_id_path_param(test_id)

            assert exc_info.value.status_code == 400

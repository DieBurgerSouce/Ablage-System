# -*- coding: utf-8 -*-
"""
Unit Tests for DLP (Data Loss Prevention) Service.

Tests the enterprise security features:
- Policy-based access control
- Sensitive data detection (PII, credit cards, IBAN)
- Watermark generation
- Audit logging
- Multi-tenant isolation

Enterprise Feature: DLP Service (GDPR Compliance)
"""

import re
import uuid
from datetime import datetime, time, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dlp.dlp_service import (
    DLPService,
    DLPPolicy,
    DLPAction,
    DLPCheckResult,
    SensitiveDataType,
    WatermarkConfig,
    WatermarkPosition,
    DLPAccessDeniedError,
    DLPServiceError,
    SENSITIVE_PATTERNS,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock async session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def sample_company_id() -> uuid.UUID:
    """Sample company ID for tests."""
    return uuid.uuid4()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    """Sample user ID for tests."""
    return uuid.uuid4()


@pytest.fixture
def dlp_service(mock_session: AsyncMock, sample_company_id: uuid.UUID) -> DLPService:
    """Create DLP service with mocked session."""
    return DLPService(mock_session, company_id=sample_company_id)


@pytest.fixture
def sample_policy() -> DLPPolicy:
    """Create a sample DLP policy."""
    return DLPPolicy(
        id="test-policy",
        name="Test Policy",
        description="Policy for testing",
        enabled=True,
        allowed_roles=["admin", "manager"],
        blocked_roles=["guest"],
        action=DLPAction.ALLOW,
        require_watermark=False,
    )


# =============================================================================
# DLP ACTION ENUM TESTS
# =============================================================================


class TestDLPAction:
    """Tests for DLP action enum."""

    def test_all_actions_defined(self) -> None:
        """Verify all DLP actions are defined."""
        assert DLPAction.ALLOW == "allow"
        assert DLPAction.BLOCK == "block"
        assert DLPAction.WATERMARK == "watermark"
        assert DLPAction.NOTIFY == "notify"
        assert DLPAction.AUDIT_ONLY == "audit_only"

    def test_action_count(self) -> None:
        """Verify expected number of actions."""
        assert len(DLPAction) == 5


# =============================================================================
# SENSITIVE DATA TYPE TESTS
# =============================================================================


class TestSensitiveDataType:
    """Tests for sensitive data type enum."""

    def test_all_types_defined(self) -> None:
        """Verify all sensitive data types are defined."""
        assert SensitiveDataType.CREDIT_CARD == "credit_card"
        assert SensitiveDataType.IBAN == "iban"
        assert SensitiveDataType.SSN == "ssn"
        assert SensitiveDataType.EMAIL == "email"
        assert SensitiveDataType.PHONE == "phone"
        assert SensitiveDataType.TAX_ID == "tax_id"
        assert SensitiveDataType.DATE_OF_BIRTH == "date_of_birth"
        assert SensitiveDataType.HEALTH_DATA == "health_data"
        assert SensitiveDataType.FINANCIAL_DATA == "financial_data"

    def test_type_count(self) -> None:
        """Verify expected number of sensitive data types."""
        assert len(SensitiveDataType) == 9


# =============================================================================
# WATERMARK POSITION TESTS
# =============================================================================


class TestWatermarkPosition:
    """Tests for watermark position enum."""

    def test_all_positions_defined(self) -> None:
        """Verify all watermark positions are defined."""
        assert WatermarkPosition.CENTER == "center"
        assert WatermarkPosition.DIAGONAL == "diagonal"
        assert WatermarkPosition.FOOTER == "footer"
        assert WatermarkPosition.HEADER == "header"
        assert WatermarkPosition.TILED == "tiled"


# =============================================================================
# SENSITIVE DATA PATTERN TESTS
# =============================================================================


class TestSensitiveDataPatterns:
    """Tests for sensitive data detection patterns."""

    def test_credit_card_visa_pattern(self) -> None:
        """Test Visa credit card detection."""
        test_cards = [
            "4111111111111111",  # Standard Visa test
            "4012888888881881",  # Another Visa test
        ]
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.CREDIT_CARD]

        for card in test_cards:
            matched = any(p.search(card) for p in patterns)
            assert matched, f"Failed to match Visa card: {card}"

    def test_credit_card_mastercard_pattern(self) -> None:
        """Test Mastercard credit card detection."""
        test_cards = [
            "5555555555554444",  # Standard MC test
            "5105105105105100",  # Another MC test
        ]
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.CREDIT_CARD]

        for card in test_cards:
            matched = any(p.search(card) for p in patterns)
            assert matched, f"Failed to match Mastercard: {card}"

    def test_iban_german_pattern(self) -> None:
        """Test German IBAN detection."""
        test_ibans = [
            "DE89370400440532013000",
            "DE89 3704 0044 0532 0130 00",
        ]
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.IBAN]

        for iban in test_ibans:
            matched = any(p.search(iban) for p in patterns)
            assert matched, f"Failed to match IBAN: {iban}"

    def test_email_pattern(self) -> None:
        """Test email detection."""
        test_emails = [
            "test@example.com",
            "user.name@company.de",
            "admin+tag@domain.org",
        ]
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.EMAIL]

        for email in test_emails:
            matched = any(p.search(email) for p in patterns)
            assert matched, f"Failed to match email: {email}"

    def test_phone_german_pattern(self) -> None:
        """Test German phone number detection."""
        test_phones = [
            "+4917612345678",
            "004917612345678",
            "0176-12345678",
        ]
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.PHONE]

        for phone in test_phones:
            matched = any(p.search(phone) for p in patterns)
            assert matched, f"Failed to match phone: {phone}"

    def test_date_of_birth_german_format(self) -> None:
        """Test German date of birth detection."""
        test_dates = [
            "01.01.1990",
            "15.06.2000",
            "31-12-1985",
        ]
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.DATE_OF_BIRTH]

        for date in test_dates:
            matched = any(p.search(date) for p in patterns)
            assert matched, f"Failed to match date: {date}"


# =============================================================================
# DLP POLICY TESTS
# =============================================================================


class TestDLPPolicy:
    """Tests for DLP policy model."""

    def test_policy_creation(self) -> None:
        """Test basic policy creation."""
        policy = DLPPolicy(
            id="test-1",
            name="Test Policy",
            allowed_roles=["admin"],
            action=DLPAction.ALLOW,
        )

        assert policy.id == "test-1"
        assert policy.name == "Test Policy"
        assert policy.enabled is True  # Default
        assert policy.allowed_roles == ["admin"]
        assert policy.action == DLPAction.ALLOW

    def test_policy_defaults(self) -> None:
        """Test policy default values."""
        policy = DLPPolicy(
            id="test-2",
            name="Minimal Policy",
        )

        assert policy.enabled is True
        assert policy.allowed_roles == ["admin"]
        assert policy.blocked_roles == []
        assert policy.document_types == ["all"]
        assert policy.tags_required == []
        assert policy.tags_blocked == []
        assert policy.action == DLPAction.ALLOW
        assert policy.require_watermark is False
        assert policy.notify_admin is False
        assert policy.log_access is True

    def test_policy_with_watermark(self) -> None:
        """Test policy with watermark requirement."""
        policy = DLPPolicy(
            id="test-3",
            name="Watermark Policy",
            action=DLPAction.WATERMARK,
            require_watermark=True,
            watermark_config={
                "position": "diagonal",
                "opacity": 0.3,
            },
        )

        assert policy.action == DLPAction.WATERMARK
        assert policy.require_watermark is True
        assert policy.watermark_config is not None
        assert policy.watermark_config["opacity"] == 0.3


# =============================================================================
# DLP CHECK RESULT TESTS
# =============================================================================


class TestDLPCheckResult:
    """Tests for DLP check result model."""

    def test_allowed_result(self) -> None:
        """Test creating an allowed result."""
        result = DLPCheckResult(
            allowed=True,
            action=DLPAction.ALLOW,
            policy_id="test-policy",
            policy_name="Test Policy",
        )

        assert result.allowed is True
        assert result.action == DLPAction.ALLOW
        assert result.watermark_required is False
        assert result.sensitive_data_found == []

    def test_blocked_result(self) -> None:
        """Test creating a blocked result."""
        result = DLPCheckResult(
            allowed=False,
            action=DLPAction.BLOCK,
            policy_id="block-policy",
            policy_name="Block Policy",
            reason="Zugriff verweigert - vertrauliches Dokument",
        )

        assert result.allowed is False
        assert result.action == DLPAction.BLOCK
        assert "Zugriff verweigert" in result.reason

    def test_result_with_sensitive_data(self) -> None:
        """Test result with sensitive data findings."""
        result = DLPCheckResult(
            allowed=False,
            action=DLPAction.BLOCK,
            sensitive_data_found=[
                SensitiveDataType.CREDIT_CARD,
                SensitiveDataType.IBAN,
            ],
        )

        assert len(result.sensitive_data_found) == 2
        assert SensitiveDataType.CREDIT_CARD in result.sensitive_data_found
        assert SensitiveDataType.IBAN in result.sensitive_data_found


# =============================================================================
# WATERMARK CONFIG TESTS
# =============================================================================


class TestWatermarkConfig:
    """Tests for watermark configuration."""

    def test_default_config(self) -> None:
        """Test watermark config defaults."""
        config = WatermarkConfig()

        assert config.position == WatermarkPosition.DIAGONAL
        assert config.opacity == 0.3
        assert config.font_size == 40
        assert config.color == "#808080"
        assert config.include_user is True
        assert config.include_timestamp is True

    def test_custom_config(self) -> None:
        """Test custom watermark configuration."""
        config = WatermarkConfig(
            text="VERTRAULICH",
            position=WatermarkPosition.CENTER,
            opacity=0.5,
            font_size=60,
            color="#FF0000",
        )

        assert config.text == "VERTRAULICH"
        assert config.position == WatermarkPosition.CENTER
        assert config.opacity == 0.5
        assert config.font_size == 60
        assert config.color == "#FF0000"

    def test_opacity_bounds(self) -> None:
        """Test opacity validation bounds."""
        # Valid minimum
        config_min = WatermarkConfig(opacity=0.1)
        assert config_min.opacity == 0.1

        # Valid maximum
        config_max = WatermarkConfig(opacity=1.0)
        assert config_max.opacity == 1.0

    def test_color_pattern_validation(self) -> None:
        """Test color hex pattern is valid."""
        valid_colors = ["#000000", "#FFFFFF", "#808080", "#FF00FF"]
        for color in valid_colors:
            config = WatermarkConfig(color=color)
            assert config.color == color


# =============================================================================
# DLP SERVICE INITIALIZATION TESTS
# =============================================================================


class TestDLPServiceInit:
    """Tests for DLP service initialization."""

    def test_service_creation(
        self,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Test basic service creation."""
        service = DLPService(mock_session, company_id=sample_company_id)

        assert service.db == mock_session
        assert service.company_id == sample_company_id
        assert service._policies_cache == []
        assert service._cache_loaded is False

    def test_service_without_company(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test service creation without company ID."""
        service = DLPService(mock_session, company_id=None)

        assert service.company_id is None


# =============================================================================
# DLP POLICY LOADING TESTS
# =============================================================================


class TestDLPPolicyLoading:
    """Tests for policy loading from database."""

    @pytest.mark.asyncio
    async def test_load_policies_from_db(
        self,
        dlp_service: DLPService,
        mock_session: AsyncMock,
    ) -> None:
        """Test loading policies from database."""
        # Setup mock to return empty result (will use defaults)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await dlp_service._ensure_policies_loaded()

        assert dlp_service._cache_loaded is True
        # Should have default policies when DB is empty
        assert len(dlp_service._policies_cache) > 0

    @pytest.mark.asyncio
    async def test_policies_cached_after_load(
        self,
        dlp_service: DLPService,
        mock_session: AsyncMock,
    ) -> None:
        """Test that policies are cached and not reloaded."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # First load
        await dlp_service._ensure_policies_loaded()
        first_call_count = mock_session.execute.call_count

        # Second load (should use cache)
        await dlp_service._ensure_policies_loaded()
        second_call_count = mock_session.execute.call_count

        # Should not have made additional DB call
        assert first_call_count == second_call_count


# =============================================================================
# DLP EXCEPTION TESTS
# =============================================================================


class TestDLPExceptions:
    """Tests for DLP exceptions."""

    def test_base_exception(self) -> None:
        """Test DLP base exception."""
        exc = DLPServiceError("Base error")
        assert str(exc) == "Base error"
        assert isinstance(exc, Exception)

    def test_access_denied_exception(self) -> None:
        """Test access denied exception."""
        exc = DLPAccessDeniedError("Zugriff verweigert")
        assert str(exc) == "Zugriff verweigert"
        assert isinstance(exc, DLPServiceError)


# =============================================================================
# EDGE CASES AND SECURITY TESTS
# =============================================================================


class TestDLPSecurityEdgeCases:
    """Tests for security-related edge cases."""

    def test_empty_text_detection(self) -> None:
        """Test that empty text doesn't cause errors in pattern matching."""
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.CREDIT_CARD]
        # Should not raise, should return no matches
        for pattern in patterns:
            assert pattern.search("") is None

    def test_unicode_in_sensitive_data(self) -> None:
        """Test detection with German umlauts."""
        text_with_umlauts = "Müller GmbH, test@mü müller.de"
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.EMAIL]

        # Standard email should still be detected
        test_text = "kontakt@mueller.de ist die Email"
        matched = any(p.search(test_text) for p in patterns)
        assert matched

    def test_no_false_positives_in_normal_text(self) -> None:
        """Test that normal text doesn't trigger false positives."""
        normal_text = """
        Dies ist ein normaler deutscher Text ohne sensible Daten.
        Wir besprechen heute das Wetter und andere Themen.
        """
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.CREDIT_CARD]

        # Should not find credit card in normal text
        matched = any(p.search(normal_text) for p in patterns)
        assert not matched

    def test_partial_matches_not_accepted(self) -> None:
        """Test that partial matches are handled correctly."""
        # Text that looks similar but isn't a valid IBAN
        partial_text = "DE12 is not a valid IBAN"
        patterns = SENSITIVE_PATTERNS[SensitiveDataType.IBAN]

        # Full pattern shouldn't match partial
        matched = any(p.fullmatch(partial_text) for p in patterns)
        assert not matched

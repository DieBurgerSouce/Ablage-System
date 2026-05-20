# -*- coding: utf-8 -*-
"""
Unit Tests for Alert Center Service.

Tests the enterprise alert management system:
- Alert creation, retrieval, updates
- Status workflow (new -> acknowledged -> resolved)
- Bulk operations
- Auto-dismiss cleanup
- Dashboard statistics

Enterprise Feature: Alert Center (Migration 117)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_alert import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertStatus,
)
from app.services.alert_center_service import (
    AlertCenterService,
    AlertCodes,
    ALERT_TEMPLATES,
    get_alert_center_service,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock async session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def alert_service(mock_session: AsyncMock) -> AlertCenterService:
    """Create alert center service with mocked session."""
    return AlertCenterService(mock_session)


@pytest.fixture
def sample_company_id() -> uuid.UUID:
    """Sample company ID for tests."""
    return uuid.uuid4()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    """Sample user ID for tests."""
    return uuid.uuid4()


@pytest.fixture
def sample_document_id() -> uuid.UUID:
    """Sample document ID for tests."""
    return uuid.uuid4()


@pytest.fixture
def sample_entity_id() -> uuid.UUID:
    """Sample entity ID for tests."""
    return uuid.uuid4()


@pytest.fixture
def sample_alert(sample_company_id: uuid.UUID) -> Alert:
    """Create a sample alert for testing."""
    return Alert(
        id=uuid.uuid4(),
        company_id=sample_company_id,
        alert_code=AlertCodes.FRAUD_DUPLICATE_INVOICE,
        category=AlertCategory.FRAUD.value,
        severity=AlertSeverity.HIGH.value,
        status=AlertStatus.NEW.value,
        title="Moegliche Duplikat-Rechnung erkannt",
        message="Die Rechnung RE-2024-001 von Lieferant ABC ist moeglicherweise ein Duplikat.",
        created_at=datetime.now(timezone.utc),
    )


# =============================================================================
# ALERT CODES AND TEMPLATES
# =============================================================================


class TestAlertCodes:
    """Tests for alert code definitions."""

    def test_fraud_codes_defined(self) -> None:
        """Verify all fraud codes are defined."""
        assert AlertCodes.FRAUD_DUPLICATE_INVOICE == "FRAUD_001"
        assert AlertCodes.FRAUD_PRICE_ANOMALY == "FRAUD_002"
        assert AlertCodes.FRAUD_PHANTOM_SUPPLIER == "FRAUD_003"
        assert AlertCodes.FRAUD_INTERNAL_PATTERN == "FRAUD_004"

    def test_risk_codes_defined(self) -> None:
        """Verify all risk codes are defined."""
        assert AlertCodes.RISK_HIGH_SCORE == "RISK_001"
        assert AlertCodes.RISK_PAYMENT_DELAY == "RISK_002"
        assert AlertCodes.RISK_INSOLVENCY_WARNING == "RISK_003"
        assert AlertCodes.RISK_CREDIT_LIMIT == "RISK_004"

    def test_compliance_codes_defined(self) -> None:
        """Verify all compliance codes are defined."""
        assert AlertCodes.COMPLIANCE_GDPR_VIOLATION == "COMP_001"
        assert AlertCodes.COMPLIANCE_GOBD_VIOLATION == "COMP_002"
        assert AlertCodes.COMPLIANCE_DLP_VIOLATION == "COMP_005"

    def test_system_codes_defined(self) -> None:
        """Verify all system codes are defined."""
        assert AlertCodes.SYSTEM_GPU_MEMORY == "SYS_001"
        assert AlertCodes.SYSTEM_DISK_SPACE == "SYS_002"
        assert AlertCodes.SYSTEM_OCR_FAILURE_RATE == "SYS_003"

    def test_security_codes_defined(self) -> None:
        """Verify all security codes are defined."""
        assert AlertCodes.SECURITY_LOGIN_FAILED == "SEC_001"
        assert AlertCodes.SECURITY_SUSPICIOUS_ACCESS == "SEC_002"
        assert AlertCodes.SECURITY_API_ABUSE == "SEC_003"


class TestAlertTemplates:
    """Tests for alert message templates."""

    def test_fraud_templates_have_german_text(self) -> None:
        """Verify fraud templates use German text."""
        template = ALERT_TEMPLATES.get(AlertCodes.FRAUD_DUPLICATE_INVOICE)
        assert template is not None
        assert "Duplikat" in template["title"]
        assert "moeglicherweise" in template["message"]

    def test_deadline_templates_have_placeholders(self) -> None:
        """Verify deadline templates have proper placeholders."""
        template = ALERT_TEMPLATES.get(AlertCodes.DEADLINE_SKONTO_EXPIRING)
        assert template is not None
        assert "{invoice_number}" in template["message"]
        assert "{days}" in template["message"]
        assert "{savings}" in template["message"]

    def test_system_templates_exist(self) -> None:
        """Verify system alert templates exist."""
        template = ALERT_TEMPLATES.get(AlertCodes.SYSTEM_GPU_MEMORY)
        assert template is not None
        assert "{usage}" in template["message"]


# =============================================================================
# ALERT CREATION
# =============================================================================


class TestAlertCreation:
    """Tests for alert creation functionality."""

    @pytest.mark.asyncio
    async def test_create_alert_basic(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Test basic alert creation."""
        # Setup mock to return the added alert
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', uuid.uuid4()))

        alert = await alert_service.create_alert(
            company_id=sample_company_id,
            alert_code=AlertCodes.FRAUD_DUPLICATE_INVOICE,
            category=AlertCategory.FRAUD,
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            message="Test message",
        )

        # Verify session.add was called
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_alert_with_document_reference(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
        sample_document_id: uuid.UUID,
    ) -> None:
        """Test alert creation with document reference."""
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', uuid.uuid4()))

        alert = await alert_service.create_alert(
            company_id=sample_company_id,
            alert_code=AlertCodes.QUALITY_LOW_OCR_CONFIDENCE,
            category=AlertCategory.QUALITY,
            severity=AlertSeverity.MEDIUM,
            title="Niedrige OCR-Qualitaet",
            message="Dokument mit 65% Konfidenz erkannt",
            document_id=sample_document_id,
        )

        mock_session.add.assert_called_once()
        added_alert = mock_session.add.call_args[0][0]
        assert added_alert.document_id == sample_document_id

    @pytest.mark.asyncio
    async def test_create_alert_with_entity_reference(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
        sample_entity_id: uuid.UUID,
    ) -> None:
        """Test alert creation with entity reference."""
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', uuid.uuid4()))

        alert = await alert_service.create_alert(
            company_id=sample_company_id,
            alert_code=AlertCodes.RISK_HIGH_SCORE,
            category=AlertCategory.RISK,
            severity=AlertSeverity.HIGH,
            title="Hoher Risiko-Score",
            message="Risiko-Score von 85/100",
            entity_id=sample_entity_id,
        )

        mock_session.add.assert_called_once()
        added_alert = mock_session.add.call_args[0][0]
        assert added_alert.entity_id == sample_entity_id

    @pytest.mark.asyncio
    async def test_create_alert_with_auto_dismiss(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Test alert creation with auto-dismiss configured."""
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', uuid.uuid4()))

        alert = await alert_service.create_alert(
            company_id=sample_company_id,
            alert_code=AlertCodes.SYSTEM_QUEUE_BACKLOG,
            category=AlertCategory.SYSTEM,
            severity=AlertSeverity.LOW,
            title="Queue Backlog",
            message="Temporaerer Queue Backlog",
            auto_dismiss_hours=24,
        )

        mock_session.add.assert_called_once()
        added_alert = mock_session.add.call_args[0][0]
        assert added_alert.auto_dismiss_at is not None

    @pytest.mark.asyncio
    async def test_create_alert_with_metadata(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Test alert creation with metadata."""
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', uuid.uuid4()))
        metadata = {
            "invoice_number": "RE-2024-001",
            "amount": 1234.56,
            "vendor_name": "Test GmbH",
        }

        alert = await alert_service.create_alert(
            company_id=sample_company_id,
            alert_code=AlertCodes.FRAUD_DUPLICATE_INVOICE,
            category=AlertCategory.FRAUD,
            severity=AlertSeverity.HIGH,
            title="Duplikat erkannt",
            message="Rechnung ist ein Duplikat",
            metadata=metadata,
        )

        mock_session.add.assert_called_once()
        added_alert = mock_session.add.call_args[0][0]
        assert added_alert.metadata == metadata


# =============================================================================
# ALERT STATUS WORKFLOW
# =============================================================================


class TestAlertStatusWorkflow:
    """Tests for alert status transitions."""

    @pytest.mark.asyncio
    async def test_acknowledge_alert(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_alert: Alert,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Test acknowledging an alert."""
        # Setup mock query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = sample_alert
        mock_session.execute.return_value = mock_result

        result = await alert_service.acknowledge_alert(
            alert_id=sample_alert.id,
            user_id=sample_user_id,
        )

        assert sample_alert.status == AlertStatus.ACKNOWLEDGED.value
        assert sample_alert.acknowledged_by_id == sample_user_id
        assert sample_alert.acknowledged_at is not None
        mock_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_dismiss_alert(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_alert: Alert,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Test dismissing an alert."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = sample_alert
        mock_session.execute.return_value = mock_result

        result = await alert_service.dismiss_alert(
            alert_id=sample_alert.id,
            user_id=sample_user_id,
            reason="False positive",
        )

        assert sample_alert.status == AlertStatus.DISMISSED.value
        assert sample_alert.resolution_note == "False positive"
        assert sample_alert.resolved_at is not None

    @pytest.mark.asyncio
    async def test_resolve_alert(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_alert: Alert,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Test resolving an alert."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = sample_alert
        mock_session.execute.return_value = mock_result

        result = await alert_service.resolve_alert(
            alert_id=sample_alert.id,
            user_id=sample_user_id,
            resolution_note="Issue fixed",
            resolution_action="manual_fix",
        )

        assert sample_alert.status == AlertStatus.RESOLVED.value
        assert sample_alert.resolution_note == "Issue fixed"
        assert sample_alert.resolution_action == "manual_fix"

    @pytest.mark.asyncio
    async def test_alert_not_found_returns_none(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Test that operations on non-existent alert return None."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await alert_service.acknowledge_alert(
            alert_id=uuid.uuid4(),
            user_id=sample_user_id,
        )

        assert result is None


# =============================================================================
# AUTO-DISMISS CLEANUP
# =============================================================================


class TestAutoDismissCleanup:
    """Tests for auto-dismiss functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_auto_dismissed_bulk_update(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
    ) -> None:
        """Test that cleanup uses bulk UPDATE (N+1 optimization)."""
        # Setup mock to return rowcount
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        count = await alert_service.cleanup_auto_dismissed()

        assert count == 5
        # Verify execute was called (bulk UPDATE)
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_auto_dismissed_no_alerts(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
    ) -> None:
        """Test cleanup when no alerts need dismissing."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await alert_service.cleanup_auto_dismissed()

        assert count == 0


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


class TestFactoryFunction:
    """Tests for the service factory function."""

    def test_get_alert_center_service(self, mock_session: AsyncMock) -> None:
        """Test factory function creates service correctly."""
        service = get_alert_center_service(mock_session)

        assert isinstance(service, AlertCenterService)
        assert service.session == mock_session


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_create_alert_with_empty_metadata(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Test alert creation with empty metadata dict."""
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', uuid.uuid4()))

        alert = await alert_service.create_alert(
            company_id=sample_company_id,
            alert_code=AlertCodes.SYSTEM_DISK_SPACE,
            category=AlertCategory.SYSTEM,
            severity=AlertSeverity.MEDIUM,
            title="Disk Space",
            message="Low disk space",
            metadata={},
        )

        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_alert_all_severities(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Test alert creation with all severity levels."""
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', uuid.uuid4()))

        severities = [
            AlertSeverity.INFO,
            AlertSeverity.LOW,
            AlertSeverity.MEDIUM,
            AlertSeverity.HIGH,
            AlertSeverity.CRITICAL,
        ]

        for severity in severities:
            mock_session.add.reset_mock()

            await alert_service.create_alert(
                company_id=sample_company_id,
                alert_code=AlertCodes.SYSTEM_QUEUE_BACKLOG,
                category=AlertCategory.SYSTEM,
                severity=severity,
                title=f"Test {severity.value}",
                message="Test message",
            )

            mock_session.add.assert_called_once()
            added_alert = mock_session.add.call_args[0][0]
            assert added_alert.severity == severity.value

    @pytest.mark.asyncio
    async def test_create_alert_all_categories(
        self,
        alert_service: AlertCenterService,
        mock_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Test alert creation with all category types."""
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, 'id', uuid.uuid4()))

        categories = [
            AlertCategory.FRAUD,
            AlertCategory.RISK,
            AlertCategory.COMPLIANCE,
            AlertCategory.DEADLINE,
            AlertCategory.SYSTEM,
            AlertCategory.SECURITY,
            AlertCategory.QUALITY,
            AlertCategory.WORKFLOW,
        ]

        for category in categories:
            mock_session.add.reset_mock()

            await alert_service.create_alert(
                company_id=sample_company_id,
                alert_code="TEST_001",
                category=category,
                severity=AlertSeverity.MEDIUM,
                title=f"Test {category.value}",
                message="Test message",
            )

            mock_session.add.assert_called_once()
            added_alert = mock_session.add.call_args[0][0]
            assert added_alert.category == category.value

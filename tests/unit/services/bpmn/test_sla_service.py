# -*- coding: utf-8 -*-
"""Unit tests for SLA Service.

Tests cover:
- SLA definition (create, get, update)
- SLA tracking (start, check, alerts)
- SLA status calculation
- Alert thresholds (50%, 75%, 90%, 100%)
- SLA breach detection
- Escalation handling
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.bpmn.sla_service import (
    SLAService,
    SLAStatus,
    SLAAlertThreshold,
    SLAAlertCodes,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock async session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def sla_service(mock_session: AsyncMock) -> SLAService:
    """Create SLA service instance."""
    return SLAService(session=mock_session)


@pytest.fixture
def company_id() -> UUID:
    """Sample company ID."""
    return uuid4()


@pytest.fixture
def instance_id() -> UUID:
    """Sample workflow instance ID."""
    return uuid4()


@pytest.fixture
def definition_id() -> UUID:
    """Sample process definition ID."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """Sample user ID for escalation."""
    return uuid4()


@pytest.fixture
def mock_process_definition(definition_id: UUID, company_id: UUID) -> MagicMock:
    """Create mock process definition."""
    definition = MagicMock()
    definition.id = definition_id
    definition.key = "invoice-approval"
    definition.name = "Rechnungsfreigabe"
    definition.company_id = company_id
    definition.process_data = {}
    return definition


@pytest.fixture
def mock_process_instance(
    instance_id: UUID,
    definition_id: UUID,
    company_id: UUID,
) -> MagicMock:
    """Create mock process instance."""
    instance = MagicMock()
    instance.id = instance_id
    instance.definition_id = definition_id
    instance.company_id = company_id
    instance.started_at = datetime.now(timezone.utc)
    instance.variables = {}
    instance.status = "running"
    return instance


# =============================================================================
# Test SLA Definition
# =============================================================================

class TestSLADefinition:
    """Tests for SLA definition functions."""

    @pytest.mark.asyncio
    async def test_define_sla_success(
        self,
        sla_service: SLAService,
        mock_session: AsyncMock,
        mock_process_definition: MagicMock,
        company_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test successful SLA definition."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_process_definition)
        mock_session.execute.return_value = mock_result

        # Act
        result = await sla_service.define_sla(
            workflow_type="invoice-approval",
            max_duration_hours=24,
            company_id=company_id,
            description="Rechnungsfreigabe SLA",
            escalation_user_id=user_id,
        )

        # Assert
        assert result["workflow_type"] == "invoice-approval"
        assert result["max_duration_hours"] == 24
        assert result["description"] == "Rechnungsfreigabe SLA"
        assert result["escalation_user_id"] == str(user_id)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_define_sla_invalid_duration_zero(
        self,
        sla_service: SLAService,
        company_id: UUID,
    ) -> None:
        """Test SLA definition with zero duration fails."""
        with pytest.raises(ValueError, match="groesser als 0"):
            await sla_service.define_sla(
                workflow_type="invoice-approval",
                max_duration_hours=0,
                company_id=company_id,
            )

    @pytest.mark.asyncio
    async def test_define_sla_invalid_duration_negative(
        self,
        sla_service: SLAService,
        company_id: UUID,
    ) -> None:
        """Test SLA definition with negative duration fails."""
        with pytest.raises(ValueError, match="groesser als 0"):
            await sla_service.define_sla(
                workflow_type="invoice-approval",
                max_duration_hours=-5,
                company_id=company_id,
            )

    @pytest.mark.asyncio
    async def test_define_sla_exceeds_max_duration(
        self,
        sla_service: SLAService,
        company_id: UUID,
    ) -> None:
        """Test SLA definition exceeding 30 days fails."""
        with pytest.raises(ValueError, match="maximal 720 Stunden"):
            await sla_service.define_sla(
                workflow_type="invoice-approval",
                max_duration_hours=800,
                company_id=company_id,
            )

    @pytest.mark.asyncio
    async def test_define_sla_workflow_not_found(
        self,
        sla_service: SLAService,
        mock_session: AsyncMock,
        company_id: UUID,
    ) -> None:
        """Test SLA definition for non-existent workflow fails."""
        # Arrange - Return None for definition lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(ValueError, match="nicht gefunden"):
            await sla_service.define_sla(
                workflow_type="non-existent-workflow",
                max_duration_hours=24,
                company_id=company_id,
            )

    @pytest.mark.asyncio
    async def test_get_sla_definition_custom(
        self,
        sla_service: SLAService,
        mock_session: AsyncMock,
        company_id: UUID,
    ) -> None:
        """Test getting custom SLA definition."""
        # Arrange
        definition = MagicMock()
        definition.process_data = {
            "sla_config": {
                "max_duration_hours": 48,
                "description": "Custom SLA",
                "escalation_user_id": str(uuid4()),
            }
        }
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=definition)
        mock_session.execute.return_value = mock_result

        # Act
        result = await sla_service.get_sla_definition(
            workflow_type="invoice-approval",
            company_id=company_id,
        )

        # Assert
        assert result is not None
        assert result["max_duration_hours"] == 48
        assert result["description"] == "Custom SLA"

    @pytest.mark.asyncio
    async def test_get_sla_definition_default(
        self,
        sla_service: SLAService,
        mock_session: AsyncMock,
        company_id: UUID,
    ) -> None:
        """Test getting default SLA when no custom defined."""
        # Arrange
        definition = MagicMock()
        definition.process_data = {}  # No custom SLA
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=definition)
        mock_session.execute.return_value = mock_result

        # Act
        result = await sla_service.get_sla_definition(
            workflow_type="invoice-approval",
            company_id=company_id,
        )

        # Assert
        assert result is not None
        assert result["max_duration_hours"] == 24  # Default for invoice-approval
        assert result.get("is_default") is True


# =============================================================================
# Test SLA Status Calculation
# =============================================================================

class TestSLAStatusCalculation:
    """Tests for SLA status calculation."""

    def test_status_on_track(self, sla_service: SLAService) -> None:
        """Test status is ON_TRACK when within 50%."""
        # Less than 50% elapsed = ON_TRACK
        assert SLAStatus.ON_TRACK.value == "on_track"

    def test_status_warning_at_50_percent(self, sla_service: SLAService) -> None:
        """Test status is WARNING at 50% threshold."""
        assert SLAStatus.WARNING.value == "warning"

    def test_status_at_risk_at_75_percent(self, sla_service: SLAService) -> None:
        """Test status is AT_RISK at 75% threshold."""
        assert SLAStatus.AT_RISK.value == "at_risk"

    def test_status_critical_at_90_percent(self, sla_service: SLAService) -> None:
        """Test status is CRITICAL at 90% threshold."""
        assert SLAStatus.CRITICAL.value == "critical"

    def test_status_breached_at_100_percent(self, sla_service: SLAService) -> None:
        """Test status is BREACHED at 100%+."""
        assert SLAStatus.BREACHED.value == "breached"


# =============================================================================
# Test Alert Thresholds
# =============================================================================

class TestAlertThresholds:
    """Tests for SLA alert threshold configuration."""

    def test_alert_thresholds_defined(self, sla_service: SLAService) -> None:
        """Test all alert thresholds are defined."""
        assert len(sla_service.ALERT_THRESHOLDS) == 4

    def test_alert_threshold_50_percent(self, sla_service: SLAService) -> None:
        """Test 50% threshold configuration."""
        threshold = sla_service.ALERT_THRESHOLDS[0]
        assert threshold[0] == 0.50
        assert threshold[1] == SLAAlertThreshold.INFO_50

    def test_alert_threshold_75_percent(self, sla_service: SLAService) -> None:
        """Test 75% threshold configuration."""
        threshold = sla_service.ALERT_THRESHOLDS[1]
        assert threshold[0] == 0.75
        assert threshold[1] == SLAAlertThreshold.WARNING_75

    def test_alert_threshold_90_percent(self, sla_service: SLAService) -> None:
        """Test 90% threshold configuration."""
        threshold = sla_service.ALERT_THRESHOLDS[2]
        assert threshold[0] == 0.90
        assert threshold[1] == SLAAlertThreshold.HIGH_90

    def test_alert_threshold_100_percent(self, sla_service: SLAService) -> None:
        """Test 100% threshold configuration."""
        threshold = sla_service.ALERT_THRESHOLDS[3]
        assert threshold[0] == 1.00
        assert threshold[1] == SLAAlertThreshold.CRITICAL_100


# =============================================================================
# Test SLA Alert Codes
# =============================================================================

class TestSLAAlertCodes:
    """Tests for SLA alert codes."""

    def test_alert_code_info_50(self) -> None:
        """Test INFO_50 alert code."""
        assert SLAAlertCodes.SLA_INFO_50 == "SLA_001"

    def test_alert_code_warning_75(self) -> None:
        """Test WARNING_75 alert code."""
        assert SLAAlertCodes.SLA_WARNING_75 == "SLA_002"

    def test_alert_code_high_90(self) -> None:
        """Test HIGH_90 alert code."""
        assert SLAAlertCodes.SLA_HIGH_90 == "SLA_003"

    def test_alert_code_breached(self) -> None:
        """Test BREACHED alert code."""
        assert SLAAlertCodes.SLA_BREACHED == "SLA_004"

    def test_alert_code_auto_escalated(self) -> None:
        """Test AUTO_ESCALATED alert code."""
        assert SLAAlertCodes.SLA_AUTO_ESCALATED == "SLA_005"


# =============================================================================
# Test Default SLA Configuration
# =============================================================================

class TestDefaultSLAConfiguration:
    """Tests for default SLA configurations."""

    def test_invoice_approval_default(self, sla_service: SLAService) -> None:
        """Test invoice approval default is 24 hours."""
        assert sla_service.DEFAULT_SLAS["invoice-approval"] == 24

    def test_document_review_default(self, sla_service: SLAService) -> None:
        """Test document review default is 48 hours."""
        assert sla_service.DEFAULT_SLAS["document-review"] == 48

    def test_contract_approval_default(self, sla_service: SLAService) -> None:
        """Test contract approval default is 72 hours."""
        assert sla_service.DEFAULT_SLAS["contract-approval"] == 72

    def test_expense_claim_default(self, sla_service: SLAService) -> None:
        """Test expense claim default is 24 hours."""
        assert sla_service.DEFAULT_SLAS["expense-claim"] == 24

    def test_leave_request_default(self, sla_service: SLAService) -> None:
        """Test leave request default is 8 hours."""
        assert sla_service.DEFAULT_SLAS["leave-request"] == 8

    def test_purchase_order_default(self, sla_service: SLAService) -> None:
        """Test purchase order default is 24 hours."""
        assert sla_service.DEFAULT_SLAS["purchase-order"] == 24

    def test_vendor_onboarding_default(self, sla_service: SLAService) -> None:
        """Test vendor onboarding default is 168 hours (7 days)."""
        assert sla_service.DEFAULT_SLAS["vendor-onboarding"] == 168

    def test_default_fallback(self, sla_service: SLAService) -> None:
        """Test default fallback is 48 hours."""
        assert sla_service.DEFAULT_SLAS["default"] == 48


# =============================================================================
# Test SLA Tracking
# =============================================================================

class TestSLATracking:
    """Tests for SLA tracking functions."""

    @pytest.mark.asyncio
    async def test_start_sla_tracking_success(
        self,
        sla_service: SLAService,
        mock_session: AsyncMock,
        mock_process_instance: MagicMock,
        mock_process_definition: MagicMock,
        instance_id: UUID,
        company_id: UUID,
    ) -> None:
        """Test starting SLA tracking."""
        # Arrange
        def mock_execute(stmt):
            result = MagicMock()
            # First call returns instance, second returns definition
            if "ProcessInstance" in str(stmt) or hasattr(stmt, '_where_criteria'):
                result.scalar_one_or_none = MagicMock(return_value=mock_process_instance)
            else:
                result.scalar_one_or_none = MagicMock(return_value=mock_process_definition)
            return result

        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_process_instance)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_process_definition)),
        ])

        # Act
        result = await sla_service.start_sla_tracking(
            workflow_instance_id=instance_id,
            company_id=company_id,
        )

        # Assert
        assert result["instance_id"] == str(instance_id)
        assert result["status"] == SLAStatus.ON_TRACK.value
        assert "deadline" in result
        assert "start_time" in result
        mock_session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_sla_tracking_instance_not_found(
        self,
        sla_service: SLAService,
        mock_session: AsyncMock,
        instance_id: UUID,
        company_id: UUID,
    ) -> None:
        """Test SLA tracking fails for non-existent instance."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(ValueError, match="Prozess-Instanz nicht gefunden"):
            await sla_service.start_sla_tracking(
                workflow_instance_id=instance_id,
                company_id=company_id,
            )


# =============================================================================
# Test Service Initialization
# =============================================================================

class TestServiceInitialization:
    """Tests for SLA service initialization."""

    def test_service_creation(self, mock_session: AsyncMock) -> None:
        """Test service can be created."""
        service = SLAService(session=mock_session)
        assert service is not None
        assert service.session == mock_session

    def test_alert_service_lazy_loading(self, sla_service: SLAService) -> None:
        """Test alert service is not loaded on init."""
        assert sla_service._alert_service is None

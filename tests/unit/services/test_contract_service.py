"""
Unit Tests for Contract Service

Comprehensive tests for the ContractService including:
- CRUD operations
- Milestone tracking
- Amendment management
- Renewal options logic
- Status transitions
- Deadline calculations
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.contract_service import (
    ContractService,
    ContractSummary,
    DeadlineAlert,
    ContractTimelineEvent,
    get_contract_service,
)
from app.db.models import (
    BusinessContract,
    ContractMilestone,
    ContractRenewalOption,
    ContractAmendment,
    ContractType,
    ContractStatus,
    RenewalOptionStatus,
    MilestoneType,
    AmendmentStatus,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def contract_service() -> ContractService:
    """Create ContractService instance."""
    return ContractService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock async database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def sample_company_id() -> str:
    """Sample company UUID."""
    return uuid4()


@pytest.fixture
def sample_user_id() -> str:
    """Sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_contract_data(sample_company_id, sample_user_id):
    """Sample contract creation data."""
    return {
        "company_id": sample_company_id,
        "user_id": sample_user_id,
        "contract_number": "V-2026-001",
        "title": "Wartungsvertrag IT-Systeme",
        "contract_type": ContractType.MAINTENANCE,
        "start_date": date.today(),
        "end_date": date.today() + timedelta(days=365),
        "notice_period_days": 90,
        "auto_renewal": True,
        "renewal_period_months": 12,
        "total_value": Decimal("12000.00"),
        "monthly_value": Decimal("1000.00"),
        "party_a_name": "Unsere Firma GmbH",
        "party_b_name": "IT-Dienstleister AG",
    }


@pytest.fixture
def sample_contract(sample_company_id, sample_user_id) -> BusinessContract:
    """Create sample contract object."""
    contract = BusinessContract(
        id=uuid4(),
        company_id=sample_company_id,
        created_by_id=sample_user_id,
        contract_number="V-2026-001",
        title="Wartungsvertrag IT-Systeme",
        contract_type=ContractType.MAINTENANCE,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today() + timedelta(days=60),
        notice_period_days=30,
        notice_deadline=date.today() + timedelta(days=30),
        auto_renewal=True,
        renewal_period_months=12,
        status=ContractStatus.ACTIVE,
        total_value=Decimal("12000.00"),
        monthly_value=Decimal("1000.00"),
    )
    contract.milestones = []
    contract.renewal_options = []
    return contract


@pytest.fixture
def sample_renewal_option(sample_contract) -> ContractRenewalOption:
    """Create sample renewal option."""
    return ContractRenewalOption(
        id=uuid4(),
        contract_id=sample_contract.id,
        contract=sample_contract,
        option_number=1,
        renewal_duration_months=12,
        exercise_deadline=date.today() + timedelta(days=30),
        renewal_start_date=date.today() + timedelta(days=60),
        status=RenewalOptionStatus.AVAILABLE,
    )


# =============================================================================
# Singleton Tests
# =============================================================================

class TestContractServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_contract_service_returns_instance(self):
        """Test that get_contract_service returns a ContractService instance."""
        service = get_contract_service()
        assert isinstance(service, ContractService)

    def test_get_contract_service_returns_same_instance(self):
        """Test that get_contract_service returns the same instance."""
        service1 = get_contract_service()
        service2 = get_contract_service()
        assert service1 is service2


# =============================================================================
# CRUD Operations Tests
# =============================================================================

class TestContractCRUD:
    """Tests for CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_contract_success(
        self, contract_service, mock_db, sample_contract_data
    ):
        """Test successful contract creation."""
        # Setup
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Execute
        contract = await contract_service.create_contract(
            db=mock_db,
            **sample_contract_data
        )

        # Assert
        assert contract is not None
        assert contract.contract_number == sample_contract_data["contract_number"]
        assert contract.title == sample_contract_data["title"]
        assert contract.status == ContractStatus.DRAFT
        mock_db.add.assert_called()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_contract_calculates_end_date_from_duration(
        self, contract_service, mock_db, sample_contract_data
    ):
        """Test that end_date is calculated from duration_months."""
        # Modify data
        sample_contract_data.pop("end_date")
        sample_contract_data["duration_months"] = 6

        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Execute
        contract = await contract_service.create_contract(
            db=mock_db,
            **sample_contract_data
        )

        # Assert - end_date should be calculated
        expected_end = sample_contract_data["start_date"] + timedelta(days=6 * 30)
        assert contract.end_date == expected_end

    @pytest.mark.asyncio
    async def test_create_contract_with_auto_renewal_creates_options(
        self, contract_service, mock_db, sample_contract_data
    ):
        """Test that auto_renewal creates renewal options."""
        sample_contract_data["auto_renewal"] = True
        sample_contract_data["renewal_period_months"] = 12

        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Execute
        contract = await contract_service.create_contract(
            db=mock_db,
            **sample_contract_data
        )

        # Assert - renewal options should be created
        # Check that add was called multiple times (contract + milestones + options)
        assert mock_db.add.call_count > 1

    @pytest.mark.asyncio
    async def test_get_contract_found(
        self, contract_service, mock_db, sample_contract, sample_company_id
    ):
        """Test getting an existing contract."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_contract
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        contract = await contract_service.get_contract(
            db=mock_db,
            contract_id=sample_contract.id,
            company_id=sample_company_id,
        )

        # Assert
        assert contract is not None
        assert contract.id == sample_contract.id

    @pytest.mark.asyncio
    async def test_get_contract_not_found(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test getting a non-existent contract."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        contract = await contract_service.get_contract(
            db=mock_db,
            contract_id=uuid4(),
            company_id=sample_company_id,
        )

        # Assert
        assert contract is None

    @pytest.mark.asyncio
    async def test_update_contract_success(
        self, contract_service, mock_db, sample_contract, sample_company_id
    ):
        """Test updating a contract."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_contract
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Execute
        updated = await contract_service.update_contract(
            db=mock_db,
            contract_id=sample_contract.id,
            company_id=sample_company_id,
            title="Neuer Titel",
            total_value=Decimal("15000.00"),
        )

        # Assert
        assert updated is not None
        assert updated.title == "Neuer Titel"
        assert updated.total_value == Decimal("15000.00")
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_contract_not_found(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test updating a non-existent contract."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        result = await contract_service.update_contract(
            db=mock_db,
            contract_id=uuid4(),
            company_id=sample_company_id,
            title="Neuer Titel",
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_contract_soft_delete(
        self, contract_service, mock_db, sample_contract, sample_company_id
    ):
        """Test soft delete sets status to TERMINATED."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_contract
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        # Execute
        result = await contract_service.delete_contract(
            db=mock_db,
            contract_id=sample_contract.id,
            company_id=sample_company_id,
        )

        # Assert
        assert result is True
        assert sample_contract.status == ContractStatus.TERMINATED
        assert sample_contract.terminated_date == date.today()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_contract_not_found(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test deleting a non-existent contract."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        result = await contract_service.delete_contract(
            db=mock_db,
            contract_id=uuid4(),
            company_id=sample_company_id,
        )

        # Assert
        assert result is False


# =============================================================================
# List and Search Tests
# =============================================================================

class TestContractListSearch:
    """Tests for listing and searching contracts."""

    @pytest.mark.asyncio
    async def test_list_contracts_returns_results_and_count(
        self, contract_service, mock_db, sample_contract, sample_company_id
    ):
        """Test listing contracts returns both results and total count."""
        # Setup mocks
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = [sample_contract]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        # Execute
        contracts, total = await contract_service.list_contracts(
            db=mock_db,
            company_id=sample_company_id,
        )

        # Assert
        assert len(contracts) == 1
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_contracts_excludes_terminated_by_default(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test that terminated contracts are excluded by default."""
        # Setup mocks
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        # Execute
        contracts, total = await contract_service.list_contracts(
            db=mock_db,
            company_id=sample_company_id,
            status=None,  # No explicit status filter
        )

        # Assert - check that execute was called with correct query
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_list_contracts_with_status_filter(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test filtering contracts by status."""
        # Setup mocks
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        # Execute
        await contract_service.list_contracts(
            db=mock_db,
            company_id=sample_company_id,
            status=ContractStatus.ACTIVE,
        )

        # Assert
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_list_contracts_with_expiring_filter(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test filtering contracts expiring within X days."""
        # Setup mocks
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        # Execute
        await contract_service.list_contracts(
            db=mock_db,
            company_id=sample_company_id,
            expiring_within_days=30,
        )

        # Assert
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_list_contracts_with_search(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test searching contracts by text."""
        # Setup mocks
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        # Execute
        await contract_service.list_contracts(
            db=mock_db,
            company_id=sample_company_id,
            search="Wartung",
        )

        # Assert
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_list_contracts_pagination(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test pagination parameters."""
        # Setup mocks
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 100

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        # Execute
        contracts, total = await contract_service.list_contracts(
            db=mock_db,
            company_id=sample_company_id,
            offset=50,
            limit=10,
        )

        # Assert
        assert total == 100
        mock_db.execute.assert_called()


# =============================================================================
# Deadline Management Tests
# =============================================================================

class TestDeadlineManagement:
    """Tests for deadline management."""

    def test_get_urgency_critical(self, contract_service):
        """Test urgency is critical for <= 7 days."""
        assert contract_service._get_urgency(0) == "critical"
        assert contract_service._get_urgency(5) == "critical"
        assert contract_service._get_urgency(7) == "critical"

    def test_get_urgency_warning(self, contract_service):
        """Test urgency is warning for 8-30 days."""
        assert contract_service._get_urgency(8) == "warning"
        assert contract_service._get_urgency(15) == "warning"
        assert contract_service._get_urgency(30) == "warning"

    def test_get_urgency_upcoming(self, contract_service):
        """Test urgency is upcoming for > 30 days."""
        assert contract_service._get_urgency(31) == "upcoming"
        assert contract_service._get_urgency(60) == "upcoming"
        assert contract_service._get_urgency(90) == "upcoming"

    @pytest.mark.asyncio
    async def test_get_upcoming_deadlines_returns_sorted_alerts(
        self, contract_service, mock_db, sample_contract, sample_company_id
    ):
        """Test that deadlines are returned sorted by days remaining."""
        # Setup - contract with notice deadline in 15 days
        sample_contract.notice_deadline = date.today() + timedelta(days=15)
        sample_contract.end_date = date.today() + timedelta(days=45)
        sample_contract.status = ContractStatus.ACTIVE

        # Mock party_a for the response
        sample_contract.party_a = None

        # Setup mocks for contracts query
        mock_contract_result = MagicMock()
        mock_contract_result.scalars.return_value.all.return_value = [sample_contract]

        # Setup mocks for renewal options query
        mock_renewal_result = MagicMock()
        mock_renewal_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[mock_contract_result, mock_renewal_result]
        )

        # Execute
        alerts = await contract_service.get_upcoming_deadlines(
            db=mock_db,
            company_id=sample_company_id,
            days_ahead=90,
        )

        # Assert
        assert isinstance(alerts, list)
        # Should have alerts for notice and end deadlines
        assert len(alerts) == 2

        # Check alerts are sorted by days_remaining
        for i in range(len(alerts) - 1):
            assert alerts[i].days_remaining <= alerts[i + 1].days_remaining

    @pytest.mark.asyncio
    async def test_get_upcoming_deadlines_includes_renewal_options(
        self, contract_service, mock_db, sample_contract, sample_renewal_option,
        sample_company_id
    ):
        """Test that renewal option deadlines are included."""
        sample_contract.notice_deadline = None
        sample_contract.end_date = None

        # Setup mocks
        mock_contract_result = MagicMock()
        mock_contract_result.scalars.return_value.all.return_value = []

        mock_renewal_result = MagicMock()
        mock_renewal_result.scalars.return_value.all.return_value = [
            sample_renewal_option
        ]

        mock_db.execute = AsyncMock(
            side_effect=[mock_contract_result, mock_renewal_result]
        )

        # Execute
        alerts = await contract_service.get_upcoming_deadlines(
            db=mock_db,
            company_id=sample_company_id,
        )

        # Assert
        assert len(alerts) == 1
        assert alerts[0].deadline_type == "renewal"


# =============================================================================
# Renewal Management Tests
# =============================================================================

class TestRenewalManagement:
    """Tests for renewal option management."""

    @pytest.mark.asyncio
    async def test_exercise_renewal_option_success(
        self, contract_service, mock_db, sample_contract, sample_renewal_option,
        sample_company_id, sample_user_id
    ):
        """Test successfully exercising a renewal option."""
        # Setup
        sample_renewal_option.contract = sample_contract
        sample_contract.current_renewal_count = 0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_renewal_option
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        # Execute
        option, error = await contract_service.exercise_renewal_option(
            db=mock_db,
            option_id=sample_renewal_option.id,
            user_id=sample_user_id,
            company_id=sample_company_id,
            notes="Verlaengert wegen guter Leistung",
        )

        # Assert
        assert option is not None
        assert error is None
        assert option.status == RenewalOptionStatus.EXERCISED
        assert option.exercised_by_id == sample_user_id
        assert sample_contract.status == ContractStatus.RENEWED
        assert sample_contract.current_renewal_count == 1
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exercise_renewal_option_not_found(
        self, contract_service, mock_db, sample_company_id, sample_user_id
    ):
        """Test exercising a non-existent renewal option."""
        # Setup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        option, error = await contract_service.exercise_renewal_option(
            db=mock_db,
            option_id=uuid4(),
            user_id=sample_user_id,
            company_id=sample_company_id,
        )

        # Assert
        assert option is None
        assert error == "Verlängerungsoption nicht gefunden"

    @pytest.mark.asyncio
    async def test_exercise_renewal_option_not_available(
        self, contract_service, mock_db, sample_contract, sample_renewal_option,
        sample_company_id, sample_user_id
    ):
        """Test exercising an unavailable renewal option."""
        # Setup - option already exercised
        sample_renewal_option.status = RenewalOptionStatus.EXERCISED
        sample_renewal_option.contract = sample_contract

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_renewal_option
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        option, error = await contract_service.exercise_renewal_option(
            db=mock_db,
            option_id=sample_renewal_option.id,
            user_id=sample_user_id,
            company_id=sample_company_id,
        )

        # Assert
        assert option is None
        assert "nicht verfügbar" in error

    @pytest.mark.asyncio
    async def test_exercise_renewal_option_expired(
        self, contract_service, mock_db, sample_contract, sample_renewal_option,
        sample_company_id, sample_user_id
    ):
        """Test exercising an expired renewal option."""
        # Setup - deadline passed
        sample_renewal_option.exercise_deadline = date.today() - timedelta(days=1)
        sample_renewal_option.contract = sample_contract

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_renewal_option
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        # Execute
        option, error = await contract_service.exercise_renewal_option(
            db=mock_db,
            option_id=sample_renewal_option.id,
            user_id=sample_user_id,
            company_id=sample_company_id,
        )

        # Assert
        assert option is None
        assert "abgelaufen" in error
        assert sample_renewal_option.status == RenewalOptionStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_decline_renewal_option_success(
        self, contract_service, mock_db, sample_renewal_option,
        sample_company_id, sample_user_id
    ):
        """Test successfully declining a renewal option."""
        # Setup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_renewal_option
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        # Execute
        option, error = await contract_service.decline_renewal_option(
            db=mock_db,
            option_id=sample_renewal_option.id,
            user_id=sample_user_id,
            company_id=sample_company_id,
            notes="Wechsel zu anderem Anbieter",
        )

        # Assert
        assert option is not None
        assert error is None
        assert option.status == RenewalOptionStatus.DECLINED
        assert option.decision_notes == "Wechsel zu anderem Anbieter"
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_decline_renewal_option_not_found(
        self, contract_service, mock_db, sample_company_id, sample_user_id
    ):
        """Test declining a non-existent renewal option."""
        # Setup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        option, error = await contract_service.decline_renewal_option(
            db=mock_db,
            option_id=uuid4(),
            user_id=sample_user_id,
            company_id=sample_company_id,
        )

        # Assert
        assert option is None
        assert error == "Verlängerungsoption nicht gefunden"


# =============================================================================
# Analytics Tests
# =============================================================================

class TestContractAnalytics:
    """Tests for contract analytics."""

    @pytest.mark.asyncio
    async def test_get_portfolio_summary(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test getting portfolio summary statistics."""
        # Setup mocks for all count queries
        mock_total = MagicMock()
        mock_total.scalar.return_value = 25

        mock_active = MagicMock()
        mock_active.scalar.return_value = 20

        mock_expiring = MagicMock()
        mock_expiring.scalar.return_value = 5

        mock_critical = MagicMock()
        mock_critical.scalar.return_value = 2

        mock_values = MagicMock()
        mock_values.fetchone.return_value = (Decimal("500000.00"), Decimal("15000.00"))

        mock_db.execute = AsyncMock(
            side_effect=[mock_total, mock_active, mock_expiring, mock_critical, mock_values]
        )

        # Execute
        summary = await contract_service.get_portfolio_summary(
            db=mock_db,
            company_id=sample_company_id,
        )

        # Assert
        assert isinstance(summary, ContractSummary)
        assert summary.total_contracts == 25
        assert summary.active_contracts == 20
        assert summary.expiring_soon == 5
        assert summary.critical_deadlines == 2
        assert summary.total_value == Decimal("500000.00")
        assert summary.monthly_commitment == Decimal("15000.00")

    @pytest.mark.asyncio
    async def test_get_contract_timeline(
        self, contract_service, mock_db, sample_contract, sample_company_id
    ):
        """Test getting contract timeline events."""
        # Setup - add milestones and renewal options
        milestone = ContractMilestone(
            id=uuid4(),
            contract_id=sample_contract.id,
            milestone_type=MilestoneType.PAYMENT_DUE,
            title="Erste Rate",
            scheduled_date=date.today() + timedelta(days=30),
            is_completed=False,
        )
        sample_contract.milestones = [milestone]

        renewal_option = ContractRenewalOption(
            id=uuid4(),
            contract_id=sample_contract.id,
            option_number=1,
            renewal_duration_months=12,
            exercise_deadline=date.today() + timedelta(days=20),
            renewal_start_date=date.today() + timedelta(days=60),
            status=RenewalOptionStatus.AVAILABLE,
        )
        sample_contract.renewal_options = [renewal_option]

        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_contract
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        events = await contract_service.get_contract_timeline(
            db=mock_db,
            contract_id=sample_contract.id,
            company_id=sample_company_id,
        )

        # Assert
        assert isinstance(events, list)
        assert len(events) > 0

        # Check event types
        event_types = [e.event_type for e in events]
        assert "contract_start" in event_types

        # Check events are sorted by date
        for i in range(len(events) - 1):
            assert events[i].event_date <= events[i + 1].event_date

    @pytest.mark.asyncio
    async def test_get_contract_timeline_not_found(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test getting timeline for non-existent contract."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute
        events = await contract_service.get_contract_timeline(
            db=mock_db,
            contract_id=uuid4(),
            company_id=sample_company_id,
        )

        # Assert
        assert events == []


# =============================================================================
# Helper Method Tests
# =============================================================================

class TestHelperMethods:
    """Tests for helper methods."""

    @pytest.mark.asyncio
    async def test_create_default_milestones(
        self, contract_service, mock_db, sample_contract
    ):
        """Test creating default milestones for a contract."""
        # Setup
        sample_contract.notice_deadline = date.today() + timedelta(days=30)
        mock_db.add = MagicMock()

        # Execute
        await contract_service._create_default_milestones(
            db=mock_db,
            contract=sample_contract,
        )

        # Assert - should add start, notice_deadline, and end milestones
        assert mock_db.add.call_count >= 2

    @pytest.mark.asyncio
    async def test_create_default_milestones_with_price_adjustment(
        self, contract_service, mock_db, sample_contract
    ):
        """Test creating milestones includes price adjustment if configured."""
        # Setup
        sample_contract.price_adjustment_clause = True
        sample_contract.price_adjustment_date = date.today() + timedelta(days=180)
        sample_contract.price_adjustment_index = "VPI"
        sample_contract.notice_deadline = date.today() + timedelta(days=30)
        mock_db.add = MagicMock()

        # Execute
        await contract_service._create_default_milestones(
            db=mock_db,
            contract=sample_contract,
        )

        # Assert - should include price adjustment milestone
        assert mock_db.add.call_count >= 3

    @pytest.mark.asyncio
    async def test_create_renewal_options(
        self, contract_service, mock_db, sample_contract
    ):
        """Test creating renewal options for a contract."""
        # Setup
        sample_contract.renewal_period_months = 12
        sample_contract.notice_period_days = 30
        mock_db.add = MagicMock()

        # Execute
        await contract_service._create_renewal_options(
            db=mock_db,
            contract=sample_contract,
            num_options=3,
        )

        # Assert
        assert mock_db.add.call_count == 3

    @pytest.mark.asyncio
    async def test_create_renewal_options_respects_max_renewals(
        self, contract_service, mock_db, sample_contract
    ):
        """Test that max_renewals limit is respected."""
        # Setup
        sample_contract.renewal_period_months = 12
        sample_contract.max_renewals = 2
        mock_db.add = MagicMock()

        # Execute
        await contract_service._create_renewal_options(
            db=mock_db,
            contract=sample_contract,
            num_options=5,  # Request more than max
        )

        # Assert - should only create 2
        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_create_renewal_options_no_end_date(
        self, contract_service, mock_db, sample_contract
    ):
        """Test that no options are created if no end_date."""
        # Setup
        sample_contract.end_date = None
        sample_contract.renewal_period_months = 12
        mock_db.add = MagicMock()

        # Execute
        await contract_service._create_renewal_options(
            db=mock_db,
            contract=sample_contract,
        )

        # Assert
        mock_db.add.assert_not_called()


# =============================================================================
# Data Class Tests
# =============================================================================

class TestDataClasses:
    """Tests for data classes."""

    def test_contract_summary_creation(self):
        """Test ContractSummary dataclass."""
        summary = ContractSummary(
            total_contracts=25,
            active_contracts=20,
            expiring_soon=5,
            critical_deadlines=2,
            total_value=Decimal("500000.00"),
            monthly_commitment=Decimal("15000.00"),
        )

        assert summary.total_contracts == 25
        assert summary.active_contracts == 20
        assert summary.total_value == Decimal("500000.00")

    def test_deadline_alert_creation(self):
        """Test DeadlineAlert dataclass."""
        alert = DeadlineAlert(
            contract_id=uuid4(),
            contract_number="V-2026-001",
            contract_title="Wartungsvertrag",
            deadline_type="notice",
            deadline_date=date.today() + timedelta(days=15),
            days_remaining=15,
            urgency="warning",
            party_name="Firma GmbH",
        )

        assert alert.deadline_type == "notice"
        assert alert.urgency == "warning"
        assert alert.days_remaining == 15

    def test_contract_timeline_event_creation(self):
        """Test ContractTimelineEvent dataclass."""
        event = ContractTimelineEvent(
            event_date=date.today(),
            event_type="contract_start",
            title="Vertragsbeginn",
            description="Vertragsstart IT-Wartung",
            is_completed=True,
            contract_id=uuid4(),
        )

        assert event.event_type == "contract_start"
        assert event.is_completed is True


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_update_contract_ignores_none_values(
        self, contract_service, mock_db, sample_contract, sample_company_id
    ):
        """Test that None values in updates are ignored."""
        original_title = sample_contract.title

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_contract
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Execute with None value
        await contract_service.update_contract(
            db=mock_db,
            contract_id=sample_contract.id,
            company_id=sample_company_id,
            title=None,  # Should be ignored
            total_value=Decimal("20000.00"),
        )

        # Assert - title should remain unchanged
        assert sample_contract.title == original_title
        assert sample_contract.total_value == Decimal("20000.00")

    @pytest.mark.asyncio
    async def test_list_contracts_empty_result(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test listing contracts with no results."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        # Execute
        contracts, total = await contract_service.list_contracts(
            db=mock_db,
            company_id=sample_company_id,
        )

        # Assert
        assert contracts == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_portfolio_summary_with_null_values(
        self, contract_service, mock_db, sample_company_id
    ):
        """Test portfolio summary handles NULL values gracefully."""
        mock_total = MagicMock()
        mock_total.scalar.return_value = None

        mock_active = MagicMock()
        mock_active.scalar.return_value = None

        mock_expiring = MagicMock()
        mock_expiring.scalar.return_value = None

        mock_critical = MagicMock()
        mock_critical.scalar.return_value = None

        mock_values = MagicMock()
        mock_values.fetchone.return_value = (None, None)

        mock_db.execute = AsyncMock(
            side_effect=[mock_total, mock_active, mock_expiring, mock_critical, mock_values]
        )

        # Execute
        summary = await contract_service.get_portfolio_summary(
            db=mock_db,
            company_id=sample_company_id,
        )

        # Assert - should handle None gracefully
        assert summary.total_contracts == 0
        assert summary.total_value == Decimal("0")

    def test_get_urgency_negative_days(self, contract_service):
        """Test urgency for negative days (past deadline)."""
        # Past deadlines should still be critical
        assert contract_service._get_urgency(-1) == "critical"
        assert contract_service._get_urgency(-30) == "critical"

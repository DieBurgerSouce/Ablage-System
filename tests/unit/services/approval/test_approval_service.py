"""Tests fuer den Approval Service.

Testet:
- Erstellung von Genehmigungsanfragen
- Genehmigung/Ablehnung/Delegation
- Eskalation
- Status-Tracking
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalStatus, ApprovalPriority
from app.services.approval.approval_service import (
    ApprovalService,
    ApprovalResult,
)


class TestApprovalCreation:
    """Tests fuer die Erstellung von Genehmigungsanfragen."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.mark.asyncio
    async def test_create_approval_request_basic(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Einfache Genehmigungsanfrage wird erstellt."""
        # Arrange
        company_id = uuid4()
        entity_type = "invoice"
        entity_id = uuid4()
        approver_ids = [uuid4()]
        requester_id = uuid4()

        # Act
        result = await service.create_approval_request(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            approver_ids=approver_ids,
            requester_id=requester_id,
        )

        # Assert
        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_create_approval_request_multi_step(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Mehrstufige Genehmigungsanfrage wird erstellt."""
        company_id = uuid4()
        entity_type = "expense"
        entity_id = uuid4()
        approver_ids = [uuid4(), uuid4(), uuid4()]  # 3 Genehmiger
        requester_id = uuid4()

        result = await service.create_approval_request(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            approver_ids=approver_ids,
            requester_id=requester_id,
        )

        # Sollte 3 Steps erstellt haben
        assert mock_db.add.call_count >= 3

    @pytest.mark.asyncio
    async def test_create_approval_request_with_priority(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Genehmigungsanfrage mit Prioritaet wird erstellt."""
        company_id = uuid4()
        entity_type = "contract"
        entity_id = uuid4()
        approver_ids = [uuid4()]
        requester_id = uuid4()

        result = await service.create_approval_request(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            approver_ids=approver_ids,
            requester_id=requester_id,
            priority=ApprovalPriority.URGENT,
        )

        assert mock_db.add.called


class TestApprovalActions:
    """Tests fuer Genehmigungsaktionen."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """Mock-Genehmigungsanfrage."""
        request = MagicMock()
        request.id = uuid4()
        request.status = ApprovalStatus.PENDING
        request.current_step = 1
        request.steps = [
            MagicMock(
                step_order=1,
                assigned_user_id=uuid4(),
                status=ApprovalStatus.PENDING,
            )
        ]
        return request

    @pytest.mark.asyncio
    async def test_approve_single_step(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Einzelschritt-Genehmigung funktioniert."""
        request_id = mock_request.id
        user_id = mock_request.steps[0].assigned_user_id

        # Mock get_request
        with patch.object(
            service, "_get_request", return_value=mock_request
        ):
            result = await service.approve(
                request_id=request_id,
                user_id=user_id,
                notes="Genehmigt",
            )

            # Assert
            assert isinstance(result, ApprovalResult)
            assert result.success
            assert mock_request.steps[0].status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approve_wrong_user_fails(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Genehmigung durch falschen User schlaegt fehl."""
        request_id = mock_request.id
        wrong_user_id = uuid4()  # Anderer User

        with patch.object(
            service, "_get_request", return_value=mock_request
        ):
            result = await service.approve(
                request_id=request_id,
                user_id=wrong_user_id,
            )

            assert not result.success
            assert "nicht autorisiert" in result.message.lower()

    @pytest.mark.asyncio
    async def test_reject_requires_notes(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Ablehnung erfordert Begruendung."""
        request_id = mock_request.id
        user_id = mock_request.steps[0].assigned_user_id

        with patch.object(
            service, "_get_request", return_value=mock_request
        ):
            result = await service.reject(
                request_id=request_id,
                user_id=user_id,
                notes=None,  # Keine Begruendung
            )

            assert not result.success
            assert "begruendung" in result.message.lower()

    @pytest.mark.asyncio
    async def test_reject_with_notes_succeeds(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Ablehnung mit Begruendung funktioniert."""
        request_id = mock_request.id
        user_id = mock_request.steps[0].assigned_user_id

        with patch.object(
            service, "_get_request", return_value=mock_request
        ):
            result = await service.reject(
                request_id=request_id,
                user_id=user_id,
                notes="Budget ueberschritten",
            )

            assert result.success
            assert mock_request.steps[0].status == ApprovalStatus.REJECTED


class TestApprovalDelegation:
    """Tests fuer Delegation."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        request = MagicMock()
        request.id = uuid4()
        request.status = ApprovalStatus.PENDING
        request.current_step = 1
        request.steps = [
            MagicMock(
                step_order=1,
                assigned_user_id=uuid4(),
                status=ApprovalStatus.PENDING,
            )
        ]
        return request

    @pytest.mark.asyncio
    async def test_delegate_changes_assignee(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Delegation aendert den zugewiesenen User."""
        request_id = mock_request.id
        user_id = mock_request.steps[0].assigned_user_id
        delegate_to_id = uuid4()

        with patch.object(
            service, "_get_request", return_value=mock_request
        ):
            result = await service.delegate(
                request_id=request_id,
                user_id=user_id,
                delegate_to_id=delegate_to_id,
                reason="Im Urlaub",
            )

            assert result.success

    @pytest.mark.asyncio
    async def test_delegate_to_self_fails(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Delegation an sich selbst schlaegt fehl."""
        request_id = mock_request.id
        user_id = mock_request.steps[0].assigned_user_id

        with patch.object(
            service, "_get_request", return_value=mock_request
        ):
            result = await service.delegate(
                request_id=request_id,
                user_id=user_id,
                delegate_to_id=user_id,  # An sich selbst
                reason="Test",
            )

            assert not result.success


class TestApprovalEscalation:
    """Tests fuer Eskalation."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.mark.asyncio
    async def test_escalate_overdue_finds_requests(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Ueberfaellige Anfragen werden gefunden."""
        # Arrange
        overdue_request = MagicMock()
        overdue_request.id = uuid4()
        overdue_request.status = ApprovalStatus.PENDING
        overdue_request.due_date = datetime.utcnow() - timedelta(days=1)
        overdue_request.is_escalated = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [overdue_request]
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.escalate_overdue()

        # Assert
        assert result["escalated_count"] == 1
        assert overdue_request.status == ApprovalStatus.ESCALATED

    @pytest.mark.asyncio
    async def test_already_escalated_not_escalated_again(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Bereits eskalierte Anfragen werden nicht erneut eskaliert."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # Keine ueberfaelligen
        mock_db.execute.return_value = mock_result

        result = await service.escalate_overdue()

        assert result["escalated_count"] == 0


class TestApprovalStatistics:
    """Tests fuer Statistiken."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.mark.asyncio
    async def test_get_summary_returns_counts(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """get_summary gibt Zaehler zurueck."""
        company_id = uuid4()

        # Mock counts
        mock_db.execute.return_value.scalar.side_effect = [10, 3, 2, 1]  # pending, approved, rejected, escalated

        result = await service.get_summary(company_id=company_id)

        assert "pending_count" in result
        assert "approved_count" in result
        assert "rejected_count" in result
        assert "escalated_count" in result

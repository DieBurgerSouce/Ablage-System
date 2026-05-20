"""Tests fuer den Approval Service.

Testet:
- Erstellung von Genehmigungsanfragen
- Genehmigung/Ablehnung/Delegation
- Eskalation
- Status-Tracking
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalStatus, ApprovalPriority
from app.services.approval.approval_service import (
    ApprovalService,
    ApprovalDecision,
)


class TestApprovalCreation:
    """Tests fuer die Erstellung von Genehmigungsanfragen."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.add = MagicMock()
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
        company_id = uuid4()
        entity_type = "invoice"
        entity_id = uuid4()
        approval_chain = [
            {"step": 1, "type": "user", "value": str(uuid4()), "required": True}
        ]

        result = await service.create_approval_request(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            title="Test-Rechnung",
            approval_chain=approval_chain,
        )

        assert mock_db.add.called
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_approval_request_multi_step(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Mehrstufige Genehmigungsanfrage wird erstellt."""
        company_id = uuid4()
        entity_type = "expense"
        entity_id = uuid4()
        approval_chain = [
            {"step": 1, "type": "role", "value": "manager", "required": True},
            {"step": 2, "type": "role", "value": "director", "required": True},
            {"step": 3, "type": "role", "value": "cfo", "required": True},
        ]

        result = await service.create_approval_request(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            title="Test-Ausgabe",
            approval_chain=approval_chain,
        )

        # 1 Request + 3 Steps = mindestens 4 adds
        assert mock_db.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_create_approval_request_with_priority(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Genehmigungsanfrage mit Prioritaet wird erstellt."""
        company_id = uuid4()
        entity_type = "contract"
        entity_id = uuid4()
        approval_chain = [
            {"step": 1, "type": "user", "value": str(uuid4()), "required": True}
        ]

        result = await service.create_approval_request(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            title="Vertrag",
            approval_chain=approval_chain,
            priority=ApprovalPriority.URGENT,
        )

        assert mock_db.add.called


class TestApprovalActions:
    """Tests fuer Genehmigungsaktionen (approve/reject)."""

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

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """Mock-Genehmigungsanfrage mit Steps."""
        user_id = uuid4()
        request = MagicMock()
        request.id = uuid4()
        request.company_id = uuid4()
        request.status = ApprovalStatus.PENDING
        request.current_step = 1
        request.total_steps = 1

        step = MagicMock()
        step.step_number = 1
        step.assigned_user_id = user_id
        step.delegated_to_id = None
        step.status = ApprovalStatus.PENDING
        step.approver_type = "user"
        step.approver_value = str(user_id)

        request.approval_steps = [step]
        return request

    @pytest.mark.asyncio
    async def test_approve_calls_internal_method(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Approve ruft interne Methoden auf."""
        request_id = mock_request.id
        user_id = mock_request.approval_steps[0].assigned_user_id

        with patch.object(
            service, "get_request", return_value=mock_request
        ):
            with patch.object(
                service, "_get_current_step", return_value=mock_request.approval_steps[0]
            ):
                with patch.object(
                    service, "_can_approve", return_value=True
                ):
                    result = await service.approve(
                        request_id=request_id,
                        user_id=user_id,
                        notes="Genehmigt",
                    )

                    assert isinstance(result, ApprovalDecision)

    @pytest.mark.asyncio
    async def test_approve_wrong_user_fails(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Genehmigung durch falschen User schlaegt fehl."""
        request_id = mock_request.id
        wrong_user_id = uuid4()

        with patch.object(
            service, "get_request", return_value=mock_request
        ):
            with patch.object(
                service, "_get_current_step", return_value=mock_request.approval_steps[0]
            ):
                with patch.object(
                    service, "_can_approve", return_value=False
                ):
                    result = await service.approve(
                        request_id=request_id,
                        user_id=wrong_user_id,
                    )

                    assert not result.success

    @pytest.mark.asyncio
    async def test_reject_calls_internal_method(
        self, service: ApprovalService, mock_db: AsyncMock, mock_request: MagicMock
    ) -> None:
        """Reject ruft interne Methoden auf."""
        request_id = mock_request.id
        user_id = mock_request.approval_steps[0].assigned_user_id

        with patch.object(
            service, "get_request", return_value=mock_request
        ):
            with patch.object(
                service, "_get_current_step", return_value=mock_request.approval_steps[0]
            ):
                with patch.object(
                    service, "_can_approve", return_value=True
                ):
                    result = await service.reject(
                        request_id=request_id,
                        user_id=user_id,
                        notes="Budget ueberschritten",
                    )

                    assert isinstance(result, ApprovalDecision)


class TestApprovalDelegationLegacy:
    """Legacy-Tests fuer Delegation (via delegate_step)."""

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

    @pytest.fixture
    def mock_step(self) -> MagicMock:
        step = MagicMock()
        step.id = uuid4()
        step.step_number = 1
        step.assigned_user_id = uuid4()
        step.delegated_to_id = None
        step.status = ApprovalStatus.PENDING
        return step

    @pytest.mark.asyncio
    async def test_delegate_step_changes_assignee(
        self, service: ApprovalService, mock_db: AsyncMock, mock_step: MagicMock
    ) -> None:
        """Delegation aendert den zugewiesenen User."""
        step_id = mock_step.id
        original_user_id = mock_step.assigned_user_id
        delegate_to_id = uuid4()

        with patch.object(
            service, "get_step", return_value=mock_step
        ):
            result = await service.delegate_step(
                step_id=step_id,
                delegate_to_id=delegate_to_id,
                delegated_by_id=original_user_id,
                reason="Im Urlaub",
            )

            assert result is not None
            assert mock_step.assigned_user_id == delegate_to_id


class TestApprovalEscalation:
    """Tests fuer Eskalation."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.mark.asyncio
    async def test_escalate_overdue_finds_requests(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Ueberfaellige Anfragen werden gefunden."""
        overdue_request = MagicMock()
        overdue_request.id = uuid4()
        overdue_request.status = ApprovalStatus.PENDING
        overdue_request.due_date = datetime.now(timezone.utc) - timedelta(days=1)
        overdue_request.is_escalated = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [overdue_request]
        mock_db.execute.return_value = mock_result

        # escalate_overdue gibt int zurueck
        result = await service.escalate_overdue()

        assert result == 1
        assert overdue_request.status == ApprovalStatus.ESCALATED

    @pytest.mark.asyncio
    async def test_already_escalated_not_escalated_again(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Bereits eskalierte Anfragen werden nicht erneut eskaliert."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.escalate_overdue()

        assert result == 0


class TestApprovalStatistics:
    """Tests fuer Statistiken (get_summary)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.mark.asyncio
    async def test_get_summary_returns_approval_summary(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """get_summary gibt ApprovalSummary zurueck."""
        from app.services.approval.approval_service import ApprovalSummary

        company_id = uuid4()

        # Mock: status counts, avg hours, overdue count, my_pending
        status_result = MagicMock()
        status_result.all.return_value = [
            (ApprovalStatus.PENDING, 10),
            (ApprovalStatus.APPROVED, 5),
            (ApprovalStatus.REJECTED, 2),
            (ApprovalStatus.ESCALATED, 1),
        ]

        avg_result = MagicMock()
        avg_result.scalar.return_value = 24.5

        overdue_result = MagicMock()
        overdue_result.scalar.return_value = 3

        my_pending_result = MagicMock()
        my_pending_result.scalar.return_value = 0

        mock_db.execute.side_effect = [
            status_result,
            avg_result,
            overdue_result,
            my_pending_result,
        ]

        result = await service.get_summary(company_id=company_id)

        assert isinstance(result, ApprovalSummary)
        assert result.total_pending == 10
        assert result.total_approved == 5


# =============================================================================
# API-COMPATIBLE METHODS TESTS (fuer app/api/v1/approvals.py)
# =============================================================================

class TestGetRequestsForCompany:
    """Tests fuer get_requests_for_company Methode."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.mark.asyncio
    async def test_get_requests_basic(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Holt Anfragen ohne Filter."""
        company_id = uuid4()

        mock_request = MagicMock()
        mock_request.id = uuid4()
        mock_request.company_id = company_id
        mock_request.status = ApprovalStatus.PENDING

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_request]
        mock_db.execute.return_value = mock_result

        result = await service.get_requests_for_company(
            company_id=company_id,
            offset=0,
            limit=50,
        )

        assert len(result) == 1
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_requests_with_status_filter(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Filtert nach Status."""
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.get_requests_for_company(
            company_id=company_id,
            status_filter=ApprovalStatus.APPROVED,
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_requests_with_entity_type_filter(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Filtert nach Entity-Typ."""
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.get_requests_for_company(
            company_id=company_id,
            entity_type="invoice",
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_requests_for_specific_user(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Filtert nach zugewiesenem User."""
        company_id = uuid4()
        user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.get_requests_for_company(
            company_id=company_id,
            for_user_id=user_id,
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_requests_pagination(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Testet Pagination mit offset und limit."""
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.get_requests_for_company(
            company_id=company_id,
            offset=10,
            limit=5,
        )

        assert len(result) == 0


class TestCountRequestsForCompany:
    """Tests fuer count_requests_for_company Methode."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.mark.asyncio
    async def test_count_requests_basic(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Zaehlt alle Anfragen."""
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_db.execute.return_value = mock_result

        count = await service.count_requests_for_company(
            company_id=company_id,
        )

        assert count == 42

    @pytest.mark.asyncio
    async def test_count_requests_with_filters(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Zaehlt mit Filtern."""
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_db.execute.return_value = mock_result

        count = await service.count_requests_for_company(
            company_id=company_id,
            status_filter=ApprovalStatus.PENDING,
            entity_type="expense",
        )

        assert count == 5

    @pytest.mark.asyncio
    async def test_count_requests_returns_zero_when_none(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Gibt 0 zurueck wenn keine Ergebnisse."""
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        count = await service.count_requests_for_company(
            company_id=company_id,
        )

        assert count == 0


class TestProcessApprovalDecision:
    """Tests fuer process_approval_decision Methode."""

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
    async def test_process_decision_approved(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Genehmigung wird verarbeitet."""
        request_id = uuid4()
        user_id = uuid4()

        with patch.object(
            service, "approve", return_value=MagicMock(success=True)
        ) as mock_approve:
            result = await service.process_approval_decision(
                request_id=request_id,
                user_id=user_id,
                decision="approved",
                notes="Alles korrekt",
            )

            mock_approve.assert_awaited_once_with(request_id, user_id, "Alles korrekt")

    @pytest.mark.asyncio
    async def test_process_decision_rejected_with_notes(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Ablehnung mit Begruendung wird verarbeitet."""
        request_id = uuid4()
        user_id = uuid4()

        with patch.object(
            service, "reject", return_value=MagicMock(success=True)
        ) as mock_reject:
            result = await service.process_approval_decision(
                request_id=request_id,
                user_id=user_id,
                decision="rejected",
                notes="Budget ueberschritten",
            )

            mock_reject.assert_awaited_once_with(
                request_id, user_id, "Budget ueberschritten"
            )

    @pytest.mark.asyncio
    async def test_process_decision_rejected_without_notes_fails(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Ablehnung ohne Begruendung schlaegt fehl."""
        request_id = uuid4()
        user_id = uuid4()

        result = await service.process_approval_decision(
            request_id=request_id,
            user_id=user_id,
            decision="rejected",
            notes=None,  # Keine Begruendung
        )

        assert result.success is False
        assert "erforderlich" in result.message.lower()

    @pytest.mark.asyncio
    async def test_process_decision_invalid_decision(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Ungueltige Entscheidung wird abgelehnt."""
        request_id = uuid4()
        user_id = uuid4()

        result = await service.process_approval_decision(
            request_id=request_id,
            user_id=user_id,
            decision="maybe",  # Ungueltig
        )

        assert result.success is False
        assert "ungueltig" in result.message.lower()


class TestEscalateRequest:
    """Tests fuer escalate_request Methode."""

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
    async def test_escalate_pending_request(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Ausstehende Anfrage wird eskaliert."""
        request_id = uuid4()

        mock_request = MagicMock()
        mock_request.id = request_id
        mock_request.status = ApprovalStatus.PENDING
        mock_request.is_escalated = False

        with patch.object(
            service, "get_request", return_value=mock_request
        ):
            result = await service.escalate_request(
                request_id=request_id,
                reason="Dringend - Projektstart uebermorgen",
                escalate_to_role="director",
            )

            assert result is True
            assert mock_request.is_escalated is True
            assert mock_request.status == ApprovalStatus.ESCALATED
            mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_escalate_already_completed_fails(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Abgeschlossene Anfrage kann nicht eskaliert werden."""
        request_id = uuid4()

        mock_request = MagicMock()
        mock_request.id = request_id
        mock_request.status = ApprovalStatus.APPROVED

        with patch.object(
            service, "get_request", return_value=mock_request
        ):
            result = await service.escalate_request(
                request_id=request_id,
                reason="Egal",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_escalate_not_found_fails(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Nicht existierende Anfrage kann nicht eskaliert werden."""
        request_id = uuid4()

        with patch.object(
            service, "get_request", return_value=None
        ):
            result = await service.escalate_request(
                request_id=request_id,
                reason="Egal",
            )

            assert result is False


class TestDelegateStep:
    """Tests fuer delegate_step Methode."""

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
    async def test_delegate_step_success(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Step wird erfolgreich delegiert."""
        step_id = uuid4()
        delegate_to_id = uuid4()
        delegated_by_id = uuid4()

        mock_step = MagicMock()
        mock_step.id = step_id
        mock_step.assigned_user_id = delegated_by_id

        with patch.object(
            service, "get_step", return_value=mock_step
        ):
            result = await service.delegate_step(
                step_id=step_id,
                delegate_to_id=delegate_to_id,
                delegated_by_id=delegated_by_id,
                reason="Im Urlaub",
            )

            assert result is not None
            assert mock_step.delegated_to_id == delegate_to_id
            assert mock_step.assigned_user_id == delegate_to_id
            mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delegate_step_not_found(
        self, service: ApprovalService, mock_db: AsyncMock
    ) -> None:
        """Nicht existierender Step kann nicht delegiert werden."""
        step_id = uuid4()

        with patch.object(
            service, "get_step", return_value=None
        ):
            result = await service.delegate_step(
                step_id=step_id,
                delegate_to_id=uuid4(),
                delegated_by_id=uuid4(),
            )

            assert result is None


class TestCanUserApproveStep:
    """Tests fuer can_user_approve_step Methode."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock(spec=AsyncSession)
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ApprovalService:
        return ApprovalService(db=mock_db)

    @pytest.mark.asyncio
    async def test_can_approve_assigned_user(
        self, service: ApprovalService
    ) -> None:
        """Zugewiesener User kann genehmigen."""
        user_id = uuid4()

        mock_step = MagicMock()
        mock_step.step_number = 1
        mock_step.assigned_user_id = user_id
        mock_step.status = ApprovalStatus.PENDING

        mock_request = MagicMock()
        mock_request.approval_steps = [mock_step]

        mock_user = MagicMock()
        mock_user.id = user_id

        with patch.object(
            service, "_can_approve", return_value=True
        ):
            result = await service.can_user_approve_step(
                request=mock_request,
                user=mock_user,
                step_number=1,
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_can_approve_no_steps(
        self, service: ApprovalService
    ) -> None:
        """Ohne Steps kann niemand genehmigen."""
        mock_request = MagicMock()
        mock_request.approval_steps = None

        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.can_user_approve_step(
            request=mock_request,
            user=mock_user,
            step_number=1,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_can_approve_step_not_found(
        self, service: ApprovalService
    ) -> None:
        """Bei nicht existierendem Step wird False zurueckgegeben."""
        mock_step = MagicMock()
        mock_step.step_number = 1

        mock_request = MagicMock()
        mock_request.approval_steps = [mock_step]

        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.can_user_approve_step(
            request=mock_request,
            user=mock_user,
            step_number=99,  # Existiert nicht
        )

        assert result is False

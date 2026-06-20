"""Unit Tests fuer ApprovalMatrixService.

Tests fuer:
- Matrix Lookup (amount ranges, department matching)
- Vier-Augen-Prinzip
- Chain Template Building
- CRUD Operations
- Group Decision Modes
"""

import pytest
import pytest_asyncio
from decimal import Decimal
from uuid import uuid4
from datetime import datetime, timezone

from app.services.approval.approval_matrix_service import ApprovalMatrixService
from app.services.approval.approval_audit_service import ApprovalAuditService
from app.db.models_approval_matrix import (
    ApprovalMatrix,
    ApprovalChainTemplate,
    ApprovalGroup,
    ApprovalGroupMember,
)
from app.db.models import ApprovalStatus, ApprovalRequest, ApprovalStep, Company, User


@pytest_asyncio.fixture
async def async_db_session(test_db):
    """Liefert die kanonische PostgreSQL-Async-Session aus conftest (``test_db``).

    Diese Tests schreiben echte ORM-Objekte (Company, User, ApprovalMatrix ...)
    und brauchen daher eine echte DB-Session. ``test_db`` ueberspringt sauber,
    wenn keine Datenbank erreichbar ist (CI-only). Frueher referenzierte diese
    Datei einen nirgends definierten Fixture-Namen -> 13 Setup-Errors.
    """
    yield test_db


@pytest.mark.asyncio
class TestApprovalMatrixService:
    """Tests fuer ApprovalMatrixService."""

    async def test_create_matrix_entry(self, async_db_session):
        """Test: Matrix-Eintrag erstellen."""
        company_id = uuid4()
        user_id = uuid4()

        # Create company first
        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        # Create user
        user = User(id=user_id, email="test@test.de", hashed_password="xxx", company_id=company_id)
        async_db_session.add(user)
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)
        matrix = await service.create_matrix_entry(
            company_id=company_id,
            department="Einkauf",
            amount_min=Decimal("0.00"),
            amount_max=Decimal("5000.00"),
            chain_template_id=None,
            created_by_id=user_id,
            four_eyes_required=False,
            min_approvers=1,
            priority=0,
        )

        assert matrix.id is not None
        assert matrix.company_id == company_id
        assert matrix.department == "Einkauf"
        assert matrix.amount_min == Decimal("0.00")
        assert matrix.amount_max == Decimal("5000.00")
        assert matrix.is_active is True

    async def test_find_matching_matrix_exact_match(self, async_db_session):
        """Test: Matrix Lookup - Exakter Match."""
        company_id = uuid4()
        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        # Create chain template
        template = ApprovalChainTemplate(
            id=uuid4(),
            company_id=company_id,
            name="Standard Kette",
            steps_config=[
                {"step": 1, "approver_type": "role", "approver_id": "manager", "timeout_hours": 48}
            ],
        )
        async_db_session.add(template)

        # Create matrix entry
        matrix = ApprovalMatrix(
            id=uuid4(),
            company_id=company_id,
            department="Einkauf",
            document_type="invoice",
            amount_min=Decimal("0.00"),
            amount_max=Decimal("5000.00"),
            chain_template_id=template.id,
            priority=10,
        )
        async_db_session.add(matrix)
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)
        match = await service.find_matching_matrix(
            company_id=company_id,
            department="Einkauf",
            amount=Decimal("2500.00"),
            document_type="invoice",
        )

        assert match is not None
        assert match.matrix_id == matrix.id
        assert match.priority == 10
        assert len(match.steps_config) == 1

    async def test_find_matching_matrix_amount_range(self, async_db_session):
        """Test: Matrix Lookup - Amount Range Matching."""
        company_id = uuid4()
        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        # Create matrix entries with different ranges
        matrix_low = ApprovalMatrix(
            id=uuid4(),
            company_id=company_id,
            department="Finanzen",
            amount_min=Decimal("0.00"),
            amount_max=Decimal("1000.00"),
            priority=1,
        )
        matrix_high = ApprovalMatrix(
            id=uuid4(),
            company_id=company_id,
            department="Finanzen",
            amount_min=Decimal("1000.01"),
            amount_max=None,  # Unbegrenzt
            priority=2,
        )
        async_db_session.add_all([matrix_low, matrix_high])
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)

        # Test low amount
        match_low = await service.find_matching_matrix(
            company_id=company_id,
            department="Finanzen",
            amount=Decimal("500.00"),
        )
        assert match_low is not None
        assert match_low.matrix_id == matrix_low.id

        # Test high amount (unbegrenzt)
        match_high = await service.find_matching_matrix(
            company_id=company_id,
            department="Finanzen",
            amount=Decimal("50000.00"),
        )
        assert match_high is not None
        assert match_high.matrix_id == matrix_high.id

    async def test_find_matching_matrix_priority(self, async_db_session):
        """Test: Matrix Lookup - Prioritaet bei Ueberlappung."""
        company_id = uuid4()
        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        # Create overlapping matrix entries
        matrix_low_prio = ApprovalMatrix(
            id=uuid4(),
            company_id=company_id,
            department="IT",
            amount_min=Decimal("0.00"),
            amount_max=Decimal("10000.00"),
            priority=1,
        )
        matrix_high_prio = ApprovalMatrix(
            id=uuid4(),
            company_id=company_id,
            department="IT",
            amount_min=Decimal("0.00"),
            amount_max=Decimal("10000.00"),
            priority=10,  # Hoehere Prioritaet
        )
        async_db_session.add_all([matrix_low_prio, matrix_high_prio])
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)
        match = await service.find_matching_matrix(
            company_id=company_id,
            department="IT",
            amount=Decimal("5000.00"),
        )

        assert match is not None
        # Hoehere Prioritaet sollte gewinnen
        assert match.matrix_id == matrix_high_prio.id

    async def test_find_matching_matrix_fallback(self, async_db_session):
        """Test: Matrix Lookup - Fallback auf NULL document_type."""
        company_id = uuid4()
        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        # Create fallback matrix (NULL document_type)
        matrix_fallback = ApprovalMatrix(
            id=uuid4(),
            company_id=company_id,
            department="Marketing",
            document_type=None,  # General rule
            amount_min=Decimal("0.00"),
            amount_max=Decimal("5000.00"),
            priority=1,
        )
        async_db_session.add(matrix_fallback)
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)
        match = await service.find_matching_matrix(
            company_id=company_id,
            department="Marketing",
            amount=Decimal("2000.00"),
            document_type="contract",  # Kein exakter Match, sollte Fallback nutzen
        )

        assert match is not None
        assert match.matrix_id == matrix_fallback.id

    async def test_check_four_eyes_principle_fulfilled(self, async_db_session):
        """Test: Vier-Augen-Prinzip erfuellt."""
        company_id = uuid4()
        request_id = uuid4()
        user1_id = uuid4()
        user2_id = uuid4()

        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        # Create users
        user1 = User(id=user1_id, email="user1@test.de", hashed_password="xxx", company_id=company_id)
        user2 = User(id=user2_id, email="user2@test.de", hashed_password="xxx", company_id=company_id)
        async_db_session.add_all([user1, user2])

        # Create approval request
        request = ApprovalRequest(
            id=request_id,
            company_id=company_id,
            entity_type="invoice",
            entity_id=uuid4(),
            title="Test Genehmigung",
            current_step=2,
            total_steps=2,
            approval_chain=[],
        )
        async_db_session.add(request)

        # Create approved steps von verschiedenen Usern
        step1 = ApprovalStep(
            id=uuid4(),
            approval_request_id=request_id,
            step_number=1,
            approver_type="user",
            approver_value=str(user1_id),
            status=ApprovalStatus.APPROVED,
            decision_by_id=user1_id,
        )
        step2 = ApprovalStep(
            id=uuid4(),
            approval_request_id=request_id,
            step_number=2,
            approver_type="user",
            approver_value=str(user2_id),
            status=ApprovalStatus.PENDING,
        )
        async_db_session.add_all([step1, step2])
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)

        # Create matrix match with four_eyes_required
        from app.services.approval.approval_matrix_service import MatrixMatch
        matrix_match = MatrixMatch(
            matrix_id=uuid4(),
            chain_template_id=None,
            four_eyes_required=True,
            min_approvers=2,
            priority=1,
            steps_config=[],
        )

        # Check: User2 genehmigt jetzt
        is_fulfilled = await service.check_four_eyes_principle(
            request_id=request_id,
            approver_id=user2_id,
            matrix_match=matrix_match,
        )

        assert is_fulfilled is True  # 2 unique approvers

    async def test_check_four_eyes_principle_not_fulfilled(self, async_db_session):
        """Test: Vier-Augen-Prinzip nicht erfuellt."""
        company_id = uuid4()
        request_id = uuid4()
        user1_id = uuid4()

        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        user1 = User(id=user1_id, email="user1@test.de", hashed_password="xxx", company_id=company_id)
        async_db_session.add(user1)

        request = ApprovalRequest(
            id=request_id,
            company_id=company_id,
            entity_type="invoice",
            entity_id=uuid4(),
            title="Test Genehmigung",
            current_step=1,
            total_steps=1,
            approval_chain=[],
        )
        async_db_session.add(request)
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)

        from app.services.approval.approval_matrix_service import MatrixMatch
        matrix_match = MatrixMatch(
            matrix_id=uuid4(),
            chain_template_id=None,
            four_eyes_required=True,
            min_approvers=2,
            priority=1,
            steps_config=[],
        )

        # Check: Nur 1 approver
        is_fulfilled = await service.check_four_eyes_principle(
            request_id=request_id,
            approver_id=user1_id,
            matrix_match=matrix_match,
        )

        assert is_fulfilled is False  # Nur 1 unique approver

    async def test_build_approval_chain(self, async_db_session):
        """Test: Approval Chain aus Template bauen."""
        service = ApprovalMatrixService(async_db_session)

        from app.services.approval.approval_matrix_service import MatrixMatch
        matrix_match = MatrixMatch(
            matrix_id=uuid4(),
            chain_template_id=uuid4(),
            four_eyes_required=False,
            min_approvers=1,
            priority=1,
            steps_config=[
                {
                    "step": 1,
                    "approver_type": "role",
                    "approver_id": "manager",
                    "required": True,
                    "timeout_hours": 48,
                },
                {
                    "step": 2,
                    "approver_type": "user",
                    "approver_id": str(uuid4()),
                    "required": True,
                    "timeout_hours": 24,
                },
            ],
        )

        chain = await service.build_approval_chain(matrix_match)

        assert len(chain) == 2
        assert chain[0]["step"] == 1
        assert chain[0]["type"] == "role"
        assert chain[0]["value"] == "manager"
        assert chain[0]["timeout_hours"] == 48
        assert chain[1]["step"] == 2
        assert chain[1]["type"] == "user"

    async def test_update_matrix_entry(self, async_db_session):
        """Test: Matrix-Eintrag aktualisieren."""
        company_id = uuid4()
        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        matrix = ApprovalMatrix(
            id=uuid4(),
            company_id=company_id,
            department="HR",
            amount_min=Decimal("0.00"),
            amount_max=Decimal("1000.00"),
            priority=1,
        )
        async_db_session.add(matrix)
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)
        updated = await service.update_matrix_entry(
            matrix_id=matrix.id,
            amount_max=Decimal("2000.00"),
            priority=5,
        )

        assert updated is not None
        assert updated.amount_max == Decimal("2000.00")
        assert updated.priority == 5

    async def test_delete_matrix_entry_soft_delete(self, async_db_session):
        """Test: Matrix-Eintrag loeschen (Soft Delete)."""
        company_id = uuid4()
        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        matrix = ApprovalMatrix(
            id=uuid4(),
            company_id=company_id,
            department="Legal",
            amount_min=Decimal("0.00"),
            amount_max=None,
            is_active=True,
        )
        async_db_session.add(matrix)
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)
        success = await service.delete_matrix_entry(matrix.id)

        assert success is True

        # Verify soft delete
        await async_db_session.refresh(matrix)
        assert matrix.is_active is False

    async def test_create_chain_template(self, async_db_session):
        """Test: Chain Template erstellen."""
        company_id = uuid4()
        user_id = uuid4()

        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        user = User(id=user_id, email="test@test.de", hashed_password="xxx", company_id=company_id)
        async_db_session.add(user)
        await async_db_session.commit()

        service = ApprovalMatrixService(async_db_session)
        template = await service.create_chain_template(
            company_id=company_id,
            name="Standard Template",
            steps_config=[
                {
                    "step": 1,
                    "approver_type": "role",
                    "approver_id": "cfo",
                    "timeout_hours": 72,
                }
            ],
            created_by_id=user_id,
            description="Standard 3-stufige Genehmigung",
            is_default=True,
        )

        assert template.id is not None
        assert template.company_id == company_id
        assert template.name == "Standard Template"
        assert template.is_default is True
        assert len(template.steps_config) == 1


@pytest.mark.asyncio
class TestApprovalAuditService:
    """Tests fuer ApprovalAuditService."""

    async def test_log_action(self, async_db_session):
        """Test: Audit-Aktion loggen."""
        company_id = uuid4()
        request_id = uuid4()
        actor_id = uuid4()

        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        user = User(id=actor_id, email="actor@test.de", hashed_password="xxx", company_id=company_id)
        async_db_session.add(user)

        request = ApprovalRequest(
            id=request_id,
            company_id=company_id,
            entity_type="invoice",
            entity_id=uuid4(),
            title="Test Request",
            current_step=1,
            total_steps=1,
            approval_chain=[],
        )
        async_db_session.add(request)
        await async_db_session.commit()

        service = ApprovalAuditService(async_db_session)
        log_entry = await service.log_action(
            company_id=company_id,
            request_id=request_id,
            action_type="approved",
            new_status="approved",
            actor_id=actor_id,
            old_status="pending",
            notes="Test approval",
            ip_address="192.168.1.1",
        )

        assert log_entry.id is not None
        assert log_entry.request_id == request_id
        assert log_entry.action_type == "approved"
        assert log_entry.new_status == "approved"
        assert log_entry.old_status == "pending"
        assert log_entry.ip_address == "192.168.1.1"

    async def test_get_audit_trail(self, async_db_session):
        """Test: Audit Trail abrufen."""
        company_id = uuid4()
        request_id = uuid4()

        company = Company(id=company_id, name="Test GmbH")
        async_db_session.add(company)

        request = ApprovalRequest(
            id=request_id,
            company_id=company_id,
            entity_type="invoice",
            entity_id=uuid4(),
            title="Test Request",
            current_step=1,
            total_steps=1,
            approval_chain=[],
        )
        async_db_session.add(request)
        await async_db_session.commit()

        service = ApprovalAuditService(async_db_session)

        # Log multiple actions
        await service.log_action(
            company_id=company_id,
            request_id=request_id,
            action_type="created",
            new_status="pending",
        )
        await service.log_action(
            company_id=company_id,
            request_id=request_id,
            action_type="approved",
            old_status="pending",
            new_status="approved",
        )

        trail = await service.get_audit_trail(request_id)

        assert len(trail) == 2
        assert trail[0].action_type == "created"
        assert trail[1].action_type == "approved"
        # Should be chronological
        assert trail[0].created_at < trail[1].created_at

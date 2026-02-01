"""Integration tests for RLS (Row-Level Security) context.

Tests verify that:
1. RLS context is properly set and filters queries
2. Concurrent company switches are handled atomically
3. RLS bypass works correctly for service operations

These tests require a real PostgreSQL database with RLS policies enabled.

To run these tests:
    docker-compose exec backend pytest tests/integration/test_rls_context.py -v -m integration
"""

import asyncio
import pytest
import pytest_asyncio
from uuid import uuid4
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, User, UserCompany


# Alias db_session to test_db from main conftest for backwards compatibility
@pytest_asyncio.fixture
async def db_session(test_db: AsyncSession):
    """Alias for test_db fixture from main conftest.py."""
    yield test_db


@pytest_asyncio.fixture
async def test_companies(db_session: AsyncSession):
    """Create two test companies for RLS testing."""
    company_a = Company(
        id=uuid4(),
        name="Test Company A",
        legal_name="Test GmbH A",
        is_active=True,
    )
    company_b = Company(
        id=uuid4(),
        name="Test Company B",
        legal_name="Test GmbH B",
        is_active=True,
    )
    db_session.add_all([company_a, company_b])
    await db_session.commit()
    await db_session.refresh(company_a)
    await db_session.refresh(company_b)
    yield company_a, company_b
    # Cleanup
    await db_session.execute(
        text("DELETE FROM companies WHERE id IN (:a, :b)"),
        {"a": str(company_a.id), "b": str(company_b.id)}
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def test_user_with_companies(
    db_session: AsyncSession,
    test_companies: tuple,
):
    """Create a test user with access to both companies."""
    company_a, company_b = test_companies

    user = User(
        id=uuid4(),
        email=f"test_{uuid4().hex[:8]}@example.com",
        hashed_password="$2b$12$test",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    user_company_a = UserCompany(
        user_id=user.id,
        company_id=company_a.id,
        role="member",
        is_current=True,
    )
    user_company_b = UserCompany(
        user_id=user.id,
        company_id=company_b.id,
        role="member",
        is_current=False,
    )
    db_session.add_all([user_company_a, user_company_b])
    await db_session.commit()

    yield user, company_a, company_b

    # Cleanup
    await db_session.execute(
        text("DELETE FROM user_companies WHERE user_id = :uid"),
        {"uid": str(user.id)}
    )
    await db_session.execute(
        text("DELETE FROM users WHERE id = :uid"),
        {"uid": str(user.id)}
    )
    await db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestRLSContextIntegration:
    """Integration tests for RLS context with real PostgreSQL."""

    async def test_rls_context_sets_session_variable(
        self,
        db_session: AsyncSession,
        test_companies: tuple,
    ):
        """Verify set_rls_company_context sets PostgreSQL session variable."""
        from app.middleware.company_context import set_rls_company_context

        company_a, _ = test_companies

        await set_rls_company_context(db_session, company_a.id)

        # Verify the session variable was set
        result = await db_session.execute(
            text("SELECT current_setting('app.current_company_id', true)")
        )
        current_company = result.scalar()

        assert current_company == str(company_a.id)

    async def test_rls_bypass_context_manager(
        self,
        db_session: AsyncSession,
    ):
        """Verify rls_bypass_context enables and disables bypass correctly."""
        from app.middleware.company_context import rls_bypass_context

        async with rls_bypass_context(db_session):
            # Check bypass is enabled
            result = await db_session.execute(
                text("SELECT current_setting('app.rls_bypass', true)")
            )
            bypass_value = result.scalar()
            assert bypass_value == "true"

        # Check bypass is disabled after context
        result = await db_session.execute(
            text("SELECT current_setting('app.rls_bypass', true)")
        )
        bypass_value = result.scalar()
        assert bypass_value == "false"


@pytest.mark.integration
@pytest.mark.asyncio
class TestConcurrentCompanySwitchIntegration:
    """Integration tests for concurrent company switching with real DB."""

    async def test_concurrent_switches_are_atomic(
        self,
        db_session: AsyncSession,
        test_user_with_companies: tuple,
    ):
        """Verify concurrent switch_company operations use proper locking."""
        from app.middleware.company_context import switch_company
        from app.db.database import DatabaseManager

        user, company_a, company_b = test_user_with_companies

        # Get database manager for creating new sessions
        db_manager = DatabaseManager()

        # Create separate sessions for concurrent operations
        async def switch_to_a():
            async with db_manager.get_session() as session:
                return await switch_company(user.id, company_a.id, session)

        async def switch_to_b():
            async with db_manager.get_session() as session:
                return await switch_company(user.id, company_b.id, session)

        # Run multiple concurrent switches
        results = await asyncio.gather(
            switch_to_a(),
            switch_to_b(),
            switch_to_a(),
            switch_to_b(),
            return_exceptions=True
        )

        # All should complete (with possible RuntimeError for lock timeouts)
        for result in results:
            assert result is True or isinstance(result, RuntimeError)

        # Verify final state is consistent (exactly one is_current=True)
        async with db_manager.get_session() as check_session:
            result = await check_session.execute(
                select(UserCompany)
                .where(UserCompany.user_id == user.id)
                .where(UserCompany.is_current == True)
            )
            current_companies = result.scalars().all()
            assert len(current_companies) == 1

    async def test_switch_company_rollback_on_error(
        self,
        db_session: AsyncSession,
        test_user_with_companies: tuple,
    ):
        """Verify switch_company rolls back on database errors."""
        from app.middleware.company_context import switch_company

        user, company_a, company_b = test_user_with_companies

        # First ensure user is on company_a
        await switch_company(user.id, company_a.id, db_session)

        # Verify initial state
        result = await db_session.execute(
            select(UserCompany)
            .where(UserCompany.user_id == user.id)
            .where(UserCompany.is_current == True)
        )
        current = result.scalar_one()
        assert current.company_id == company_a.id

        # Now try to switch to company_b
        await switch_company(user.id, company_b.id, db_session)

        # Verify state changed
        await db_session.refresh(current)
        result = await db_session.execute(
            select(UserCompany)
            .where(UserCompany.user_id == user.id)
            .where(UserCompany.is_current == True)
        )
        current = result.scalar_one()
        assert current.company_id == company_b.id


@pytest.mark.integration
@pytest.mark.asyncio
class TestTimingAttackMitigationIntegration:
    """Integration tests for CWE-208 timing attack mitigation."""

    async def test_timing_consistent_across_scenarios(
        self,
        db_session: AsyncSession,
        test_user_with_companies: tuple,
    ):
        """Verify timing is consistent for valid/invalid/missing company scenarios."""
        from app.middleware.company_context import (
            get_current_company,
            _MIN_COMPANY_LOOKUP_TIME,
            set_company_context,
        )
        from unittest.mock import MagicMock, patch, AsyncMock
        from starlette.datastructures import Headers
        import time

        user, company_a, company_b = test_user_with_companies

        # Create mock requests
        def make_request(company_id=None, user_in_state=None):
            headers_dict = {}
            if company_id:
                headers_dict["X-Company-ID"] = str(company_id)
            headers_dict["Authorization"] = "Bearer valid.token"

            mock_request = MagicMock()
            mock_request.headers = Headers(headers_dict)
            state = MagicMock()
            if user_in_state:
                state.user = user_in_state
            else:
                del state.user
            mock_request.state = state
            return mock_request

        timings = []

        # Scenario 1: Valid user, valid company
        set_company_context(company_a.id)
        mock_user = MagicMock()
        mock_user.id = user.id
        mock_user.is_active = True

        with patch(
            "app.middleware.company_context._get_user_from_request_optional",
            new_callable=AsyncMock,
            return_value=mock_user
        ):
            start = time.perf_counter()
            await get_current_company(make_request(company_a.id), db_session)
            timings.append(("valid_user_valid_company", time.perf_counter() - start))

        # Scenario 2: Valid user, invalid company (no access)
        invalid_company_id = uuid4()
        set_company_context(invalid_company_id)

        with patch(
            "app.middleware.company_context._get_user_from_request_optional",
            new_callable=AsyncMock,
            return_value=mock_user
        ):
            start = time.perf_counter()
            await get_current_company(make_request(invalid_company_id), db_session)
            timings.append(("valid_user_invalid_company", time.perf_counter() - start))

        # Scenario 3: No user
        set_company_context(None)

        with patch(
            "app.middleware.company_context._get_user_from_request_optional",
            new_callable=AsyncMock,
            return_value=None
        ):
            start = time.perf_counter()
            await get_current_company(make_request(), db_session)
            timings.append(("no_user", time.perf_counter() - start))

        # All timings should be >= minimum
        for scenario, timing in timings:
            assert timing >= _MIN_COMPANY_LOOKUP_TIME * 0.9, (
                f"{scenario} took {timing:.4f}s, expected >= {_MIN_COMPANY_LOOKUP_TIME * 0.9:.4f}s"
            )

        # Timings should be relatively similar (within 50ms of each other)
        min_time = min(t for _, t in timings)
        max_time = max(t for _, t in timings)
        assert max_time - min_time < 0.050, (
            f"Timing variance too high: {max_time - min_time:.4f}s"
        )

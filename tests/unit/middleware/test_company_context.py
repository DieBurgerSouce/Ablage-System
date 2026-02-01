"""Unit tests for Company Context Middleware.

Tests for the inline user extraction functions and company context handling
added in commit 618e722a to fix circular imports.

Test Coverage:
- _get_user_from_request_optional(): 4 test cases
- _get_user_from_request_required(): 3 test cases
- get_current_company(): 2 test cases (security validation)
"""

import pytest
import jwt
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4, UUID
from datetime import datetime
import sys

from fastapi import HTTPException
from starlette.requests import Request
from starlette.datastructures import Headers


class MockUser:
    """Mock User object for testing."""

    def __init__(
        self,
        user_id: UUID = None,
        is_active: bool = True,
        email: str = "test@example.com"
    ):
        self.id = user_id or uuid4()
        self.is_active = is_active
        self.email = email


class MockCompany:
    """Mock Company object for testing."""

    def __init__(
        self,
        company_id: UUID = None,
        name: str = "Test GmbH",
        is_active: bool = True,
    ):
        self.id = company_id or uuid4()
        self.name = name
        self.is_active = is_active
        self.deleted_at = None


class MockUserCompany:
    """Mock UserCompany relationship for testing."""

    def __init__(
        self,
        user_id: UUID,
        company_id: UUID,
        is_current: bool = True,
        role: str = "member",
    ):
        self.user_id = user_id
        self.company_id = company_id
        self.is_current = is_current
        self.role = role
        self.created_at = datetime.utcnow()
        self.can_manage_cash = False
        self.can_approve_expenses = False


def create_mock_request(
    authorization: str = None,
    x_company_id: str = None,
    user_in_state: MockUser = None,
) -> MagicMock:
    """Create a mock Request object."""
    headers_dict = {}
    if authorization:
        headers_dict["Authorization"] = authorization
    if x_company_id:
        headers_dict["X-Company-ID"] = x_company_id

    mock_request = MagicMock(spec=Request)
    mock_request.headers = Headers(headers_dict)

    # Mock request.state
    state = MagicMock()
    if user_in_state:
        state.user = user_in_state
    else:
        # hasattr returns False for non-existent attributes
        del state.user

    mock_request.state = state

    return mock_request


class TestGetUserCompanyHelper:
    """Tests for _get_user_company() helper function (P1 DRY-FIX)."""

    @pytest.mark.asyncio
    async def test_returns_user_company_when_exists(self):
        """_get_user_company should return UserCompany when relationship exists."""
        from app.middleware.company_context import _get_user_company

        user_id = uuid4()
        company_id = uuid4()
        mock_user_company = MockUserCompany(user_id=user_id, company_id=company_id)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user_company))
        )

        result = await _get_user_company(user_id, company_id, mock_db)

        assert result is mock_user_company
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_exists(self):
        """_get_user_company should return None when no relationship exists."""
        from app.middleware.company_context import _get_user_company

        user_id = uuid4()
        company_id = uuid4()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        result = await _get_user_company(user_id, company_id, mock_db)

        assert result is None


class TestExtractUserFromToken:
    """Tests for _extract_user_from_token() helper function (P1 DRY-FIX)."""

    @pytest.mark.asyncio
    async def test_returns_user_from_request_state(self):
        """User in request.state should be returned directly."""
        from app.middleware.company_context import _extract_user_from_token

        existing_user = MockUser()
        mock_request = create_mock_request(user_in_state=existing_user)
        mock_db = AsyncMock()

        result = await _extract_user_from_token(mock_request, mock_db)

        assert result is existing_user

    @pytest.mark.asyncio
    async def test_returns_none_without_auth_header(self):
        """No Authorization header should return None."""
        from app.middleware.company_context import _extract_user_from_token

        mock_request = create_mock_request()
        mock_db = AsyncMock()

        result = await _extract_user_from_token(mock_request, mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_jwt_error(self):
        """JWT error should return None, not raise exception."""
        from app.middleware.company_context import _extract_user_from_token

        mock_request = create_mock_request(authorization="Bearer invalid.token")
        mock_db = AsyncMock()

        with patch(
            "app.middleware.company_context.decode_token",
            new_callable=AsyncMock,
            side_effect=jwt.PyJWTError("Invalid token")
        ):
            result = await _extract_user_from_token(mock_request, mock_db)

            assert result is None


class TestGetUserFromRequestOptional:
    """Tests for _get_user_from_request_optional()."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """Valid Bearer token should return active user."""
        from app.middleware.company_context import _get_user_from_request_optional

        user_id = uuid4()
        mock_user = MockUser(user_id=user_id)
        mock_request = create_mock_request(authorization="Bearer valid.jwt.token")
        mock_db = AsyncMock()

        # Patch at the source modules since inline imports are used
        with patch(
            "app.core.security.decode_token",
            new_callable=AsyncMock,
            return_value={"sub": str(user_id), "type": "access"}
        ) as mock_decode, patch(
            "app.core.security.verify_token_type"
        ) as mock_verify, patch(
            "app.services.user_service.UserService.get_user_by_id",
            new_callable=AsyncMock,
            return_value=mock_user
        ) as mock_get_user:

            result = await _get_user_from_request_optional(mock_request, mock_db)

            assert result is not None
            assert result.id == user_id
            mock_decode.assert_called_once_with("valid.jwt.token")
            mock_verify.assert_called_once()
            mock_get_user.assert_called_once_with(mock_db, user_id)

    @pytest.mark.asyncio
    async def test_no_auth_header_returns_none(self):
        """Missing Authorization header should return None."""
        from app.middleware.company_context import _get_user_from_request_optional

        mock_request = create_mock_request()  # No authorization header
        mock_db = AsyncMock()

        result = await _get_user_from_request_optional(mock_request, mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        """Invalid/expired token should return None, not raise exception."""
        from app.middleware.company_context import _get_user_from_request_optional

        mock_request = create_mock_request(authorization="Bearer invalid.token")
        mock_db = AsyncMock()

        # CWE-390 FIX: Now only catches specific exceptions (ValueError, jwt.PyJWTError)
        # Mock decode_token to raise a JWT error
        with patch(
            "app.core.security.decode_token",
            new_callable=AsyncMock,
            side_effect=jwt.PyJWTError("Token expired")
        ):

            # Should NOT raise, should return None (graceful degradation)
            result = await _get_user_from_request_optional(mock_request, mock_db)

            assert result is None

    @pytest.mark.asyncio
    async def test_user_from_request_state(self):
        """User already in request.state should be returned directly."""
        from app.middleware.company_context import _get_user_from_request_optional

        existing_user = MockUser()
        mock_request = create_mock_request(user_in_state=existing_user)
        mock_db = AsyncMock()

        result = await _get_user_from_request_optional(mock_request, mock_db)

        # Should return the same user object from state without decoding token
        assert result is existing_user

    @pytest.mark.asyncio
    async def test_inactive_user_returns_none(self):
        """Inactive user should return None."""
        from app.middleware.company_context import _get_user_from_request_optional

        user_id = uuid4()
        inactive_user = MockUser(user_id=user_id, is_active=False)
        mock_request = create_mock_request(authorization="Bearer valid.token")
        mock_db = AsyncMock()

        with patch(
            "app.core.security.decode_token",
            new_callable=AsyncMock,
            return_value={"sub": str(user_id), "type": "access"}
        ), patch(
            "app.core.security.verify_token_type"
        ), patch(
            "app.services.user_service.UserService.get_user_by_id",
            new_callable=AsyncMock,
            return_value=inactive_user
        ):

            result = await _get_user_from_request_optional(mock_request, mock_db)

            assert result is None


class TestGetUserFromRequestRequired:
    """Tests for _get_user_from_request_required()."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """Valid Bearer token should return active user."""
        from app.middleware.company_context import _get_user_from_request_required

        user_id = uuid4()
        mock_user = MockUser(user_id=user_id)
        mock_request = create_mock_request(authorization="Bearer valid.jwt.token")
        mock_db = AsyncMock()

        with patch(
            "app.core.security.decode_token",
            new_callable=AsyncMock,
            return_value={"sub": str(user_id), "type": "access"}
        ), patch(
            "app.core.security.verify_token_type"
        ), patch(
            "app.services.user_service.UserService.get_user_by_id",
            new_callable=AsyncMock,
            return_value=mock_user
        ):

            result = await _get_user_from_request_required(mock_request, mock_db)

            assert result is not None
            assert result.id == user_id

    @pytest.mark.asyncio
    async def test_no_auth_header_raises_401(self):
        """Missing Authorization header should raise 401."""
        from app.middleware.company_context import _get_user_from_request_required

        mock_request = create_mock_request()  # No authorization header
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_from_request_required(mock_request, mock_db)

        assert exc_info.value.status_code == 401
        assert "Nicht authentifiziert" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """Invalid token should raise 401."""
        from app.middleware.company_context import _get_user_from_request_required

        mock_request = create_mock_request(authorization="Bearer invalid.token")
        mock_db = AsyncMock()

        # CWE-390 FIX: Now only catches specific exceptions (ValueError, jwt.PyJWTError)
        with patch(
            "app.core.security.decode_token",
            new_callable=AsyncMock,
            side_effect=jwt.PyJWTError("Token invalid")
        ):

            with pytest.raises(HTTPException) as exc_info:
                await _get_user_from_request_required(mock_request, mock_db)

            assert exc_info.value.status_code == 401
            assert "fehlgeschlagen" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_user_from_request_state(self):
        """User already in request.state should be returned directly."""
        from app.middleware.company_context import _get_user_from_request_required

        existing_user = MockUser()
        mock_request = create_mock_request(user_in_state=existing_user)
        mock_db = AsyncMock()

        result = await _get_user_from_request_required(mock_request, mock_db)

        assert result is existing_user

    @pytest.mark.asyncio
    async def test_inactive_user_raises_401(self):
        """Inactive user should raise 401."""
        from app.middleware.company_context import _get_user_from_request_required

        user_id = uuid4()
        inactive_user = MockUser(user_id=user_id, is_active=False)
        mock_request = create_mock_request(authorization="Bearer valid.token")
        mock_db = AsyncMock()

        with patch(
            "app.core.security.decode_token",
            new_callable=AsyncMock,
            return_value={"sub": str(user_id), "type": "access"}
        ), patch(
            "app.core.security.verify_token_type"
        ), patch(
            "app.services.user_service.UserService.get_user_by_id",
            new_callable=AsyncMock,
            return_value=inactive_user
        ):

            with pytest.raises(HTTPException) as exc_info:
                await _get_user_from_request_required(mock_request, mock_db)

            assert exc_info.value.status_code == 401
            assert "inaktiv" in exc_info.value.detail


class TestGetCurrentCompany:
    """Tests for get_current_company() dependency."""

    @pytest.mark.asyncio
    async def test_company_from_header_with_ownership(self):
        """X-Company-ID header with valid ownership returns company."""
        from app.middleware.company_context import get_current_company

        user_id = uuid4()
        company_id = uuid4()

        mock_user = MockUser(user_id=user_id)
        mock_company = MockCompany(company_id=company_id)
        mock_user_company = MockUserCompany(user_id=user_id, company_id=company_id)

        mock_request = create_mock_request(
            authorization="Bearer valid.token",
            x_company_id=str(company_id)
        )
        mock_db = AsyncMock()

        # Mock the DB queries
        mock_execute_results = [
            # First query: UserCompany ownership check
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user_company)),
            # Second query: Company fetch
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_company)),
        ]
        mock_db.execute = AsyncMock(side_effect=mock_execute_results)

        with patch(
            "app.middleware.company_context._get_user_from_request_optional",
            new_callable=AsyncMock,
            return_value=mock_user
        ), patch(
            "app.middleware.company_context.get_current_company_id",
            return_value=company_id
        ):

            result = await get_current_company(mock_request, mock_db)

            assert result is not None
            assert result.id == company_id

    @pytest.mark.asyncio
    async def test_company_from_header_without_ownership_blocked(self):
        """X-Company-ID for non-owned company should fallback to user's company."""
        from app.middleware.company_context import get_current_company

        user_id = uuid4()
        attempted_company_id = uuid4()  # Company user doesn't own
        actual_company_id = uuid4()  # User's actual company

        mock_user = MockUser(user_id=user_id)
        mock_actual_company = MockCompany(company_id=actual_company_id)

        mock_request = create_mock_request(
            authorization="Bearer valid.token",
            x_company_id=str(attempted_company_id)
        )
        mock_db = AsyncMock()

        # First query returns None (no ownership), triggering security block
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        with patch(
            "app.middleware.company_context._get_user_from_request_optional",
            new_callable=AsyncMock,
            return_value=mock_user
        ), patch(
            "app.middleware.company_context.get_current_company_id",
            return_value=attempted_company_id
        ), patch(
            "app.middleware.company_context.set_company_context"
        ) as mock_set_context, patch(
            "app.middleware.company_context.get_user_current_company",
            new_callable=AsyncMock,
            return_value=mock_actual_company
        ) as mock_get_user_company:

            result = await get_current_company(mock_request, mock_db)

            # Security fix should reset context and return user's actual company
            mock_set_context.assert_called_with(None)
            mock_get_user_company.assert_called_once_with(user_id, mock_db)
            assert result is mock_actual_company


class TestCompanyContextMiddleware:
    """Tests for CompanyContextMiddleware."""

    @pytest.mark.asyncio
    async def test_valid_company_header_sets_context(self):
        """Valid X-Company-ID header should set context."""
        from app.middleware.company_context import (
            CompanyContextMiddleware,
            get_current_company_id,
        )

        company_id = uuid4()
        mock_request = create_mock_request(x_company_id=str(company_id))
        mock_response = MagicMock()
        mock_call_next = AsyncMock(return_value=mock_response)

        middleware = CompanyContextMiddleware(app=MagicMock())

        response = await middleware.dispatch(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)
        assert response is mock_response

    @pytest.mark.asyncio
    async def test_invalid_company_header_logged_and_ignored(self):
        """Invalid X-Company-ID header should be logged and ignored."""
        from app.middleware.company_context import CompanyContextMiddleware

        mock_request = create_mock_request(x_company_id="not-a-valid-uuid")
        mock_response = MagicMock()
        mock_call_next = AsyncMock(return_value=mock_response)

        middleware = CompanyContextMiddleware(app=MagicMock())

        with patch("app.middleware.company_context.logger") as mock_logger:
            response = await middleware.dispatch(mock_request, mock_call_next)

            # Should log warning but continue
            mock_logger.warning.assert_called()
            mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_reset_after_request(self):
        """Context should be reset to None after request completes."""
        from app.middleware.company_context import (
            CompanyContextMiddleware,
            set_company_context,
            get_current_company_id,
        )

        company_id = uuid4()
        mock_request = create_mock_request(x_company_id=str(company_id))
        mock_response = MagicMock()
        mock_call_next = AsyncMock(return_value=mock_response)

        middleware = CompanyContextMiddleware(app=MagicMock())

        await middleware.dispatch(mock_request, mock_call_next)

        # After middleware completes, context should be None
        assert get_current_company_id() is None


class TestSetRLSCompanyContext:
    """Tests for set_rls_company_context() SQL injection prevention."""

    @pytest.mark.asyncio
    async def test_valid_uuid_sets_context(self):
        """Valid UUID should set RLS context."""
        from app.middleware.company_context import set_rls_company_context

        company_id = uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        await set_rls_company_context(mock_db, company_id)

        mock_db.execute.assert_called_once()
        # Verify that the company_id was passed as parameter
        call_args = mock_db.execute.call_args
        # Check that the cid parameter contains our company_id
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert str(company_id) in str(params)

    @pytest.mark.asyncio
    async def test_invalid_uuid_prevented(self):
        """Invalid UUID-like string should be caught and logged."""
        from app.middleware.company_context import set_rls_company_context

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        # Create a mock object that converts to an invalid string
        class FakeUUID:
            def __str__(self):
                return "'; DROP TABLE users; --"

        # This should not raise, but should log warning
        with patch("app.middleware.company_context.logger") as mock_logger:
            # Pass an object that looks like a UUID but has malicious str() output
            await set_rls_company_context(mock_db, FakeUUID())

            # Should log warning about invalid UUID
            mock_logger.warning.assert_called()
            # Should NOT execute the SQL
            mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_error_propagates_exception(self):
        """CWE-391 FIX: Database errors should propagate to prevent silent RLS bypass."""
        from app.middleware.company_context import set_rls_company_context

        company_id = uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("Database connection failed"))
        mock_db.rollback = AsyncMock()

        # CWE-391: Exception should be raised, not silently ignored
        with patch("app.middleware.company_context.logger") as mock_logger:
            with pytest.raises(Exception) as exc_info:
                await set_rls_company_context(mock_db, company_id)

            assert "Database connection failed" in str(exc_info.value)
            # Should log error (not just debug)
            mock_logger.error.assert_called()


class TestSwitchCompanyAtomic:
    """Tests for switch_company() atomic operations (CWE-362 fix)."""

    @pytest.mark.asyncio
    async def test_switch_company_uses_row_level_locking(self):
        """CWE-362 FIX: switch_company should use SELECT FOR UPDATE for row-level locking."""
        from app.middleware.company_context import switch_company
        import sqlalchemy as sa

        user_id = uuid4()
        company_id = uuid4()

        mock_db = AsyncMock()
        mock_user_company = MockUserCompany(user_id=user_id, company_id=company_id)

        # Track all executed queries
        executed_queries = []

        async def mock_execute(query, *args, **kwargs):
            # Track the query type for verification
            query_str = str(query) if hasattr(query, '__str__') else repr(query)
            executed_queries.append(query_str)

            # First call (access check) returns user_company
            if len(executed_queries) == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user_company))
            # Other calls return empty mock
            return MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))

        mock_db.execute = mock_execute
        mock_db.commit = AsyncMock()

        result = await switch_company(user_id, company_id, mock_db)

        assert result is True
        # Should have 5 execute calls:
        # 1. SELECT access check
        # 2. SET LOCAL lock_timeout
        # 3. SELECT FOR UPDATE (row-level lock)
        # 4. UPDATE set all is_current=False
        # 5. UPDATE set target is_current=True
        assert len(executed_queries) == 5, f"Expected 5 queries, got {len(executed_queries)}"

        # Verify lock_timeout was set
        assert any("lock_timeout" in q for q in executed_queries), "lock_timeout should be set"

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_company_no_access_raises(self):
        """User without access should raise ValueError."""
        from app.middleware.company_context import switch_company

        user_id = uuid4()
        company_id = uuid4()

        mock_db = AsyncMock()
        # No access: scalar_one_or_none returns None
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        with pytest.raises(ValueError) as exc_info:
            await switch_company(user_id, company_id, mock_db)

        assert "keinen Zugriff" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_switch_company_db_error_raises_runtime_error(self):
        """CWE-362 FIX: Database errors should raise RuntimeError and rollback."""
        from app.middleware.company_context import switch_company
        import sqlalchemy as sa

        user_id = uuid4()
        company_id = uuid4()

        mock_db = AsyncMock()
        mock_user_company = MockUserCompany(user_id=user_id, company_id=company_id)

        call_count = 0

        async def mock_execute(query, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: access check succeeds
                return MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user_company))
            # Third call (SELECT FOR UPDATE): fails with lock timeout
            if call_count == 3:
                raise sa.exc.OperationalError("statement", {}, Exception("lock timeout"))
            return MagicMock()

        mock_db.execute = mock_execute
        mock_db.rollback = AsyncMock()

        with pytest.raises(RuntimeError) as exc_info:
            await switch_company(user_id, company_id, mock_db)

        assert "erneut versuchen" in str(exc_info.value)
        mock_db.rollback.assert_called_once()


class TestRLSBypassAuditLogging:
    """Tests for RLS bypass audit logging (CWE-390/391 fix)."""

    @pytest.mark.asyncio
    async def test_enable_rls_bypass_logs_warning(self):
        """CWE-390/391 FIX: RLS bypass enable should log audit warning."""
        from app.middleware.company_context import enable_rls_bypass

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        with patch("app.middleware.company_context.logger") as mock_logger:
            await enable_rls_bypass(mock_db)

            # Should log warning with audit_event
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args[1]
            assert call_kwargs.get("audit_event") == "RLS_BYPASS_START"

    @pytest.mark.asyncio
    async def test_disable_rls_bypass_logs_warning(self):
        """CWE-390/391 FIX: RLS bypass disable should log audit warning."""
        from app.middleware.company_context import disable_rls_bypass

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        with patch("app.middleware.company_context.logger") as mock_logger:
            await disable_rls_bypass(mock_db)

            # Should log warning with audit_event
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args[1]
            assert call_kwargs.get("audit_event") == "RLS_BYPASS_END"

    @pytest.mark.asyncio
    async def test_enable_rls_bypass_error_raises(self):
        """CWE-390 FIX: RLS bypass enable error should raise, not be silently ignored."""
        from app.middleware.company_context import enable_rls_bypass
        import sqlalchemy as sa

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=sa.exc.SQLAlchemyError("Connection lost")
        )

        with pytest.raises(sa.exc.SQLAlchemyError):
            await enable_rls_bypass(mock_db)

    @pytest.mark.asyncio
    async def test_disable_rls_bypass_error_raises(self):
        """CWE-390 FIX: RLS bypass disable error should raise, not be silently ignored."""
        from app.middleware.company_context import disable_rls_bypass
        import sqlalchemy as sa

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=sa.exc.SQLAlchemyError("Connection lost")
        )

        with pytest.raises(sa.exc.SQLAlchemyError):
            await disable_rls_bypass(mock_db)


class TestRLSContextRollbackHandling:
    """Tests for RLS context rollback error handling (CWE-391 fix)."""

    @pytest.mark.asyncio
    async def test_rls_context_rollback_failure_logs_critical(self):
        """CWE-391 FIX: Rollback failure should log critical, not be silently ignored."""
        from app.middleware.company_context import set_rls_company_context
        import sqlalchemy as sa

        company_id = uuid4()
        mock_db = AsyncMock()

        # First execute fails, then rollback also fails
        mock_db.execute = AsyncMock(
            side_effect=sa.exc.SQLAlchemyError("Connection lost")
        )
        mock_db.rollback = AsyncMock(
            side_effect=sa.exc.SQLAlchemyError("Rollback failed")
        )

        with patch("app.middleware.company_context.logger") as mock_logger:
            with pytest.raises(RuntimeError) as exc_info:
                await set_rls_company_context(mock_db, company_id)

            # Should log critical for rollback failure
            mock_logger.critical.assert_called_once()
            # Error message should mention both errors
            assert "RLS-Fehler" in str(exc_info.value)
            assert "Rollback-Fehler" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rls_context_error_propagates(self):
        """CWE-391 FIX: RLS context error should propagate after successful rollback."""
        from app.middleware.company_context import set_rls_company_context
        import sqlalchemy as sa

        company_id = uuid4()
        mock_db = AsyncMock()

        # Execute fails, rollback succeeds
        mock_db.execute = AsyncMock(
            side_effect=sa.exc.SQLAlchemyError("Connection lost")
        )
        mock_db.rollback = AsyncMock()  # Rollback succeeds

        with patch("app.middleware.company_context.logger") as mock_logger:
            with pytest.raises(sa.exc.SQLAlchemyError) as exc_info:
                await set_rls_company_context(mock_db, company_id)

            # Should log error
            mock_logger.error.assert_called_once()
            # Rollback should have been called
            mock_db.rollback.assert_called_once()

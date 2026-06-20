"""
Tests fuer Holding Dashboard API Endpoints.

Testet Multi-Company Holding-Sicht mit konsolidierten KPIs.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import status


class TestHoldingAPI:
    """Tests fuer Holding Dashboard API."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = uuid4()
        user.is_admin = False
        user.current_company_id = uuid4()
        return user

    @pytest.fixture
    def mock_admin(self):
        """Mock admin user."""
        user = MagicMock()
        user.id = uuid4()
        user.is_admin = True
        user.current_company_id = uuid4()
        return user

    @pytest.fixture
    def mock_holding_service(self):
        """Mock HoldingKPIService."""
        service = AsyncMock()
        service.get_consolidated_overview.return_value = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "company_count": 2,
            "companies": [
                {
                    "id": str(uuid4()),
                    "name": "Firma A",
                    "short_name": "A",
                    "subscription_tier": "professional",
                    "is_active": True,
                },
                {
                    "id": str(uuid4()),
                    "name": "Firma B",
                    "short_name": "B",
                    "subscription_tier": "basic",
                    "is_active": True,
                },
            ],
            "financials": {
                "total_receivables": 50000.0,
                "total_payables": 30000.0,
                "net_position": 20000.0,
                "overdue_receivables": 5000.0,
                "overdue_payables": 2000.0,
                "currency": "EUR",
            },
            "documents": {
                "total": 1500,
                "this_month": 120,
                "by_status": {"completed": 1400, "pending": 100},
            },
            "invoices": {
                "open_outgoing": 25,
                "open_incoming": 15,
                "avg_payment_days": 21,
            },
            "banking": {
                "total_balance": 150000.0,
                "account_count": 5,
                "transactions_last_30d": 250,
                "currency": "EUR",
            },
            "intercompany": {
                "total_intercompany_volume": 25000.0,
                "intercompany_receivables": 10000.0,
                "intercompany_payables": 15000.0,
                "transaction_count": 12,
            },
        }
        service.get_company_comparison.return_value = [
            {"company_id": str(uuid4()), "company_name": "Firma A", "metric": "receivables", "value": 30000.0},
            {"company_id": str(uuid4()), "company_name": "Firma B", "metric": "receivables", "value": 20000.0},
        ]
        return service

    # ==================== Overview Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_holding_overview_admin(
        self,
        mock_admin: MagicMock,
        mock_holding_service: AsyncMock,
    ) -> None:
        """Admin kann konsolidierte Uebersicht abrufen."""
        from app.api.v1.holding import get_holding_overview

        company_ids = [uuid4(), uuid4()]

        with patch(
            "app.api.v1.holding.get_user_company_ids",
            return_value=company_ids,
        ):
            with patch(
                "app.api.v1.holding.HoldingKPIService",
                return_value=mock_holding_service,
            ):
                result = await get_holding_overview(
                    company_ids=None,
                    current_user=mock_admin,
                    db=AsyncMock(),
                )

        assert result.company_count == 2
        assert result.financials.total_receivables == 50000.0
        assert result.banking.total_balance == 150000.0

    @pytest.mark.asyncio
    async def test_get_holding_overview_no_companies(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Fehler wenn User keine Companies hat."""
        from app.api.v1.holding import get_holding_overview
        from fastapi import HTTPException

        with patch(
            "app.api.v1.holding.get_user_company_ids",
            return_value=[],  # Keine Companies
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_holding_overview(
                    company_ids=None,
                    current_user=mock_user,
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 404
        assert "Keine Firmen" in exc_info.value.detail

    # ==================== Companies Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_holding_companies(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Firmenliste abrufen."""
        from app.api.v1.holding import get_holding_companies

        company_ids = [uuid4(), uuid4()]
        mock_db = AsyncMock()

        # Mock DB result - name muss explizit gesetzt werden (reserviertes MagicMock-Attribut)
        mock_company_a = MagicMock()
        mock_company_a.configure_mock(id=company_ids[0], short_name="A", subscription_tier="pro", is_active=True)
        mock_company_a.name = "Firma A"

        mock_company_b = MagicMock()
        mock_company_b.configure_mock(id=company_ids[1], short_name="B", subscription_tier="basic", is_active=True)
        mock_company_b.name = "Firma B"

        mock_companies = [mock_company_a, mock_company_b]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_companies
        mock_db.execute.return_value = mock_result

        with patch(
            "app.api.v1.holding.get_user_company_ids",
            return_value=company_ids,
        ):
            result = await get_holding_companies(
                current_user=mock_user,
                db=mock_db,
            )

        assert len(result) == 2
        assert result[0].name == "Firma A"

    @pytest.mark.asyncio
    async def test_get_holding_companies_empty(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Leere Liste wenn User keine Companies hat."""
        from app.api.v1.holding import get_holding_companies

        with patch(
            "app.api.v1.holding.get_user_company_ids",
            return_value=[],
        ):
            result = await get_holding_companies(
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result == []

    # ==================== Compare Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_compare_companies(
        self,
        mock_admin: MagicMock,
        mock_holding_service: AsyncMock,
    ) -> None:
        """Firmenvergleich."""
        from app.api.v1.holding import compare_companies

        company_ids = [uuid4(), uuid4()]

        with patch(
            "app.api.v1.holding.get_user_company_ids",
            return_value=company_ids,
        ):
            with patch(
                "app.api.v1.holding.HoldingKPIService",
                return_value=mock_holding_service,
            ):
                result = await compare_companies(
                    metric="receivables",
                    company_ids=None,
                    current_user=mock_admin,
                    db=AsyncMock(),
                )

        assert result.metric == "receivables"
        assert len(result.companies) == 2

    # ==================== Intercompany Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_intercompany_transactions(
        self,
        mock_admin: MagicMock,
        mock_holding_service: AsyncMock,
    ) -> None:
        """Intercompany-Transaktionen abrufen."""
        from app.api.v1.holding import get_intercompany_transactions

        company_ids = [uuid4(), uuid4()]

        with patch(
            "app.api.v1.holding.get_user_company_ids",
            return_value=company_ids,
        ):
            with patch(
                "app.api.v1.holding.HoldingKPIService",
                return_value=mock_holding_service,
            ):
                result = await get_intercompany_transactions(
                    company_ids=None,
                    current_user=mock_admin,
                    db=AsyncMock(),
                )

        assert result.total_intercompany_volume == 25000.0
        assert result.transaction_count == 12

    # ==================== Cashflow Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_holding_cashflow(
        self,
        mock_admin: MagicMock,
    ) -> None:
        """Konzern-Cashflow abrufen."""
        from app.api.v1.holding import get_holding_cashflow

        company_ids = [uuid4()]
        mock_db = AsyncMock()

        # Mock all queries - der Endpoint macht mehrere Queries pro Company
        # 1. Company-Name, 2. Inflows, 3. Outflows
        mock_company_result = MagicMock()
        mock_company_result.scalar.return_value = "Test Company"

        mock_inflows_result = MagicMock()
        mock_inflows_result.scalar.return_value = 10000.0

        mock_outflows_result = MagicMock()
        mock_outflows_result.scalar.return_value = 5000.0

        # Alle Queries mocken - einfacher approach
        mock_db.execute = AsyncMock(side_effect=[
            mock_company_result,
            mock_inflows_result,
            mock_outflows_result,
        ])

        with patch(
            "app.api.v1.holding.get_user_company_ids",
            return_value=company_ids,
        ):
            result = await get_holding_cashflow(
                period="monthly",
                company_ids=None,
                current_user=mock_admin,
                db=mock_db,
            )

        assert result.period_type == "monthly"
        assert result.total_inflows == 10000.0
        assert result.total_outflows == 5000.0
        assert result.total_net_flow == 5000.0


class TestGetUserCompanyIds:
    """Tests fuer get_user_company_ids Helper."""

    @pytest.mark.asyncio
    async def test_admin_sees_all_companies(self) -> None:
        """Admin sieht alle aktiven Companies."""
        from app.api.v1.holding import get_user_company_ids

        mock_db = AsyncMock()
        mock_admin = MagicMock()
        mock_admin.is_admin = True

        company_ids = [uuid4(), uuid4(), uuid4()]
        mock_result = MagicMock()
        mock_result.all.return_value = [(cid,) for cid in company_ids]
        mock_db.execute.return_value = mock_result

        result = await get_user_company_ids(mock_db, mock_admin)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_user_sees_own_companies(self) -> None:
        """User sieht nur eigene Companies."""
        from app.api.v1.holding import get_user_company_ids

        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.is_admin = False
        mock_user.id = uuid4()

        company_ids = [uuid4(), uuid4()]
        mock_result = MagicMock()
        mock_result.all.return_value = [(cid,) for cid in company_ids]
        mock_db.execute.return_value = mock_result

        result = await get_user_company_ids(mock_db, mock_user)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_by_requested_ids(self) -> None:
        """Filter nach angeforderten IDs."""
        from app.api.v1.holding import get_user_company_ids

        mock_db = AsyncMock()
        mock_admin = MagicMock()
        mock_admin.is_admin = True

        company_ids = [uuid4(), uuid4()]
        mock_result = MagicMock()
        mock_result.all.return_value = [(company_ids[0],)]  # Nur eine gefiltert
        mock_db.execute.return_value = mock_result

        result = await get_user_company_ids(
            mock_db,
            mock_admin,
            requested_ids=[company_ids[0]],
        )

        assert len(result) == 1
        assert result[0] == company_ids[0]

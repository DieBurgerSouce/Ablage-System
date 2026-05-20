# -*- coding: utf-8 -*-
"""
Unit Tests fuer Banking Interest Rates API (Feature 18).

Testet:
- GET /api/v1/banking/dunning/interest-rates
- GET /api/v1/banking/dunning/interest-rates/history
- GET /api/v1/banking/dunning/interest-rates/calculate
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import status

from app.services.bundesbank_rate_service import BasiszinsData, BasiszinsSource


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_basiszins_data():
    """Mock BasiszinsData fuer Tests."""
    return BasiszinsData(
        rate=Decimal("3.62"),
        valid_from="2024-07-01",
        valid_until=None,
        source=BasiszinsSource.CACHE,
        fetched_at="2024-07-15T10:00:00Z",
    )


@pytest.fixture
def mock_history():
    """Mock BasiszinsHistory fuer Tests."""
    from app.services.bundesbank_rate_service import BasiszinsHistory

    return BasiszinsHistory(
        rates=[
            BasiszinsData(rate=Decimal("3.62"), valid_from="2024-07-01"),
            BasiszinsData(rate=Decimal("3.12"), valid_from="2024-01-01"),
        ],
        last_updated="2024-07-15T10:00:00Z",
    )


# =============================================================================
# GET /interest-rates Tests
# =============================================================================


class TestGetCurrentInterestRates:
    """Tests fuer GET /banking/dunning/interest-rates."""

    @pytest.mark.asyncio
    async def test_returns_current_rates(
        self, client, auth_headers, mock_basiszins_data
    ):
        """Test: Aktuelle Zinssaetze werden zurueckgegeben."""
        with patch(
            "app.api.v1.banking.get_current_basiszins",
            new_callable=AsyncMock
        ) as mock_basiszins:
            with patch(
                "app.api.v1.banking.get_verzugszins",
                new_callable=AsyncMock
            ) as mock_verzug:
                mock_basiszins.return_value = mock_basiszins_data
                mock_verzug.side_effect = [
                    Decimal("12.62"),  # B2B
                    Decimal("8.62"),   # B2C
                ]

                response = await client.get(
                    "/api/v1/banking/dunning/interest-rates",
                    headers=auth_headers,
                )

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["base_rate"] == 3.62
                assert data["b2b_rate"] == 12.62
                assert data["b2c_rate"] == 8.62
                assert data["legal_basis"] == "BGB §288"

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client):
        """Test: Authentifizierung erforderlich."""
        response = await client.get("/api/v1/banking/dunning/interest-rates")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# GET /interest-rates/history Tests
# =============================================================================


class TestGetInterestRateHistory:
    """Tests fuer GET /banking/dunning/interest-rates/history."""

    @pytest.mark.asyncio
    async def test_returns_history(self, client, auth_headers, mock_history):
        """Test: Historische Zinssaetze werden zurueckgegeben."""
        from unittest.mock import MagicMock

        # get_bundesbank_rate_service ist SYNCHRON, gibt Service zurueck
        # Service.get_basiszins_history ist ASYNC
        with patch(
            "app.api.v1.banking.get_bundesbank_rate_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_basiszins_history = AsyncMock(
                return_value=mock_history
            )
            mock_get_service.return_value = mock_service

            response = await client.get(
                "/api/v1/banking/dunning/interest-rates/history",
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "rates" in data
            assert len(data["rates"]) == 2
            assert data["rates"][0]["rate"] == 3.62


# =============================================================================
# GET /interest-rates/calculate Tests
# =============================================================================


class TestCalculateInterest:
    """Tests fuer GET /banking/dunning/interest-rates/calculate."""

    @pytest.mark.asyncio
    async def test_calculates_b2b_interest(self, client, auth_headers):
        """Test: B2B Verzugszins wird korrekt berechnet."""
        with patch(
            "app.api.v1.banking.get_verzugszins",
            new_callable=AsyncMock
        ) as mock_verzug:
            mock_verzug.return_value = Decimal("12.62")

            response = await client.get(
                "/api/v1/banking/dunning/interest-rates/calculate",
                params={"amount": 1000, "days_overdue": 30, "is_b2b": True},
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["original_amount"] == 1000
            assert data["days_overdue"] == 30
            assert data["is_b2b"] is True
            assert data["verzugszins_rate"] == 12.62
            assert data["interest_amount"] > 0
            assert data["legal_basis"] == "BGB §288 Abs. 2"

    @pytest.mark.asyncio
    async def test_calculates_b2c_interest(self, client, auth_headers):
        """Test: B2C Verzugszins wird korrekt berechnet."""
        with patch(
            "app.api.v1.banking.get_verzugszins",
            new_callable=AsyncMock
        ) as mock_verzug:
            mock_verzug.return_value = Decimal("8.62")

            response = await client.get(
                "/api/v1/banking/dunning/interest-rates/calculate",
                params={"amount": 500, "days_overdue": 60, "is_b2b": False},
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_b2b"] is False
            assert data["legal_basis"] == "BGB §288 Abs. 1"

    @pytest.mark.asyncio
    async def test_validates_amount_positive(self, client, auth_headers):
        """Test: Amount muss positiv sein."""
        response = await client.get(
            "/api/v1/banking/dunning/interest-rates/calculate",
            params={"amount": -100, "days_overdue": 30, "is_b2b": True},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_validates_days_non_negative(self, client, auth_headers):
        """Test: Days_overdue darf nicht negativ sein."""
        response = await client.get(
            "/api/v1/banking/dunning/interest-rates/calculate",
            params={"amount": 100, "days_overdue": -5, "is_b2b": True},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

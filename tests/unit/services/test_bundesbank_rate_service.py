# -*- coding: utf-8 -*-
"""
Unit Tests fuer BundesbankRateService.

Testet:
- Basiszins-Abfrage mit Cache/API/Fallback
- Verzugszins-Berechnung nach §288 BGB
- Historische Daten
- Fehlerbehandlung

Feature 18: Bundesbank Basiszins-API
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.bundesbank_rate_service import (
    BundesbankRateService,
    BasiszinsData,
    BasiszinsHistory,
    BasiszinsSource,
    FALLBACK_BASISZINS,
    FALLBACK_DATE,
    get_bundesbank_rate_service,
    get_current_basiszins,
    get_verzugszins,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Erstelle Service-Instanz."""
    return BundesbankRateService()


@pytest.fixture
def mock_cache_hit():
    """Mock fuer Cache-Treffer."""
    return {
        "rate": 3.62,
        "valid_from": "2024-07-01",
        "valid_until": None,
        "fetched_at": "2024-07-15T10:00:00Z",
    }


@pytest.fixture
def mock_api_response():
    """Mock fuer Bundesbank API Response."""
    return {
        "dataSets": [
            {
                "series": {
                    "0:0:0:0": {
                        "observations": {
                            "0": [3.62],
                            "1": [3.12],
                        }
                    }
                }
            }
        ],
        "structure": {
            "dimensions": {
                "observation": [
                    {
                        "id": "TIME_PERIOD",
                        "values": [
                            {"id": "2024-H2"},
                            {"id": "2024-H1"},
                        ]
                    }
                ]
            }
        }
    }


# =============================================================================
# Basic Tests
# =============================================================================


class TestBundesbankRateService:
    """Tests fuer BundesbankRateService."""

    def test_init(self, service):
        """Test Service-Initialisierung."""
        assert service._client is None

    @pytest.mark.asyncio
    async def test_close(self, service):
        """Test Client-Schliessen."""
        # Erstelle Client
        await service._get_client()
        assert service._client is not None

        # Schliesse Client
        await service.close()
        assert service._client is None


# =============================================================================
# Basiszins Tests
# =============================================================================


class TestGetCurrentBasiszins:
    """Tests fuer get_current_basiszins."""

    @pytest.mark.asyncio
    async def test_returns_cached_value(self, service, mock_cache_hit):
        """Test: Cache-Treffer wird zurueckgegeben."""
        with patch("app.services.bundesbank_rate_service.cache_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache_hit

            result = await service.get_current_basiszins()

            assert result.rate == Decimal("3.62")
            assert result.source == BasiszinsSource.CACHE
            assert result.valid_from == "2024-07-01"
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetches_from_api_on_cache_miss(self, service, mock_api_response):
        """Test: API wird bei Cache-Miss abgefragt."""
        with patch("app.services.bundesbank_rate_service.cache_get", new_callable=AsyncMock) as mock_get, \
             patch("app.services.bundesbank_rate_service.cache_set", new_callable=AsyncMock) as mock_set, \
             patch.object(service, "_get_client") as mock_client:

            mock_get.return_value = None

            mock_response = MagicMock()
            mock_response.json.return_value = mock_api_response
            mock_response.raise_for_status = MagicMock()

            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_client.return_value = mock_http_client

            result = await service.get_current_basiszins()

            assert result.rate == Decimal("3.62")
            assert result.source == BasiszinsSource.API
            assert result.valid_from == "2024-07-01"
            mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_fallback_on_api_error(self, service):
        """Test: Fallback bei API-Fehler."""
        with patch("app.services.bundesbank_rate_service.cache_get", new_callable=AsyncMock) as mock_get, \
             patch.object(service, "_fetch_from_api", new_callable=AsyncMock) as mock_api:

            mock_get.return_value = None
            mock_api.side_effect = Exception("API nicht erreichbar")

            result = await service.get_current_basiszins()

            assert result.rate == FALLBACK_BASISZINS
            assert result.source == BasiszinsSource.FALLBACK
            assert result.valid_from == FALLBACK_DATE


# =============================================================================
# Verzugszins Tests
# =============================================================================


class TestVerzugszins:
    """Tests fuer Verzugszins-Berechnung nach §288 BGB."""

    def test_calculate_verzugszins_b2b(self, service):
        """Test: B2B Verzugszins = Basiszins + 9%."""
        result = service.calculate_verzugszins(Decimal("3.62"), is_b2b=True)
        assert result == Decimal("12.62")

    def test_calculate_verzugszins_b2c(self, service):
        """Test: B2C Verzugszins = Basiszins + 5%."""
        result = service.calculate_verzugszins(Decimal("3.62"), is_b2b=False)
        assert result == Decimal("8.62")

    def test_calculate_verzugszins_negative_base(self, service):
        """Test: Negativer Basiszins wird korrekt verarbeitet."""
        # Historisch gab es negative Basiszinssaetze
        result = service.calculate_verzugszins(Decimal("-0.88"), is_b2b=True)
        assert result == Decimal("8.12")  # -0.88 + 9 = 8.12

    @pytest.mark.asyncio
    async def test_get_verzugszins_integration(self, service, mock_cache_hit):
        """Test: get_verzugszins ruft get_current_basiszins auf."""
        with patch("app.services.bundesbank_rate_service.cache_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache_hit

            result = await service.get_verzugszins(is_b2b=True)

            assert result == Decimal("12.62")  # 3.62 + 9


# =============================================================================
# History Tests
# =============================================================================


class TestBasiszinsHistory:
    """Tests fuer historische Basiszinssaetze."""

    @pytest.mark.asyncio
    async def test_get_basiszins_history_from_cache(self, service):
        """Test: Historie aus Cache."""
        cached_history = {
            "rates": [
                {"rate": 3.62, "valid_from": "2024-07-01"},
                {"rate": 3.12, "valid_from": "2024-01-01"},
            ],
            "last_updated": "2024-07-15T10:00:00Z",
        }

        with patch("app.services.bundesbank_rate_service.cache_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = cached_history

            result = await service.get_basiszins_history()

            assert len(result.rates) == 2
            assert result.rates[0].rate == Decimal("3.62")
            assert result.rates[1].rate == Decimal("3.12")

    def test_history_get_rate_for_date(self):
        """Test: Korrekte Rate fuer ein bestimmtes Datum."""
        rates = [
            BasiszinsData(rate=Decimal("3.62"), valid_from="2024-07-01"),
            BasiszinsData(rate=Decimal("3.12"), valid_from="2024-01-01"),
            BasiszinsData(rate=Decimal("2.50"), valid_from="2023-07-01"),
        ]
        history = BasiszinsHistory(rates=rates, last_updated="2024-07-15T10:00:00Z")

        # Datum in H2/2024
        rate = history.get_rate_for_date(datetime(2024, 9, 15))
        assert rate == Decimal("3.62")

        # Datum in H1/2024
        rate = history.get_rate_for_date(datetime(2024, 3, 15))
        assert rate == Decimal("3.12")

        # Datum in H2/2023
        rate = history.get_rate_for_date(datetime(2023, 10, 1))
        assert rate == Decimal("2.50")


# =============================================================================
# Period Parsing Tests
# =============================================================================


class TestPeriodParsing:
    """Tests fuer Period-String Parsing."""

    def test_parse_period_h1(self, service):
        """Test: H1 Format."""
        result = service._parse_period("2024-H1")
        assert result == "2024-01-01"

    def test_parse_period_h2(self, service):
        """Test: H2 Format."""
        result = service._parse_period("2024-H2")
        assert result == "2024-07-01"

    def test_parse_period_month(self, service):
        """Test: YYYY-MM Format."""
        result = service._parse_period("2024-01")
        assert result == "2024-01-01"

    def test_parse_period_passthrough(self, service):
        """Test: Unbekanntes Format wird durchgereicht."""
        result = service._parse_period("2024-01-15")
        assert result == "2024-01-15"


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_bundesbank_rate_service_returns_singleton(self):
        """Test: Singleton wird korrekt zurueckgegeben."""
        # Reset Singleton
        import app.services.bundesbank_rate_service as module
        module._service = None

        service1 = get_bundesbank_rate_service()
        service2 = get_bundesbank_rate_service()

        assert service1 is service2

    @pytest.mark.asyncio
    async def test_convenience_functions(self, mock_cache_hit):
        """Test: Convenience-Funktionen funktionieren."""
        import app.services.bundesbank_rate_service as module
        module._service = None

        with patch("app.services.bundesbank_rate_service.cache_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cache_hit

            basiszins = await get_current_basiszins()
            assert basiszins.rate == Decimal("3.62")

            verzugszins = await get_verzugszins(is_b2b=True)
            assert verzugszins == Decimal("12.62")


# =============================================================================
# Data Class Tests
# =============================================================================


class TestDataClasses:
    """Tests fuer Dataclasses."""

    def test_basiszins_data_to_dict(self):
        """Test: BasiszinsData.to_dict()."""
        data = BasiszinsData(
            rate=Decimal("3.62"),
            valid_from="2024-07-01",
            valid_until="2024-12-31",
            source=BasiszinsSource.API,
            fetched_at="2024-07-15T10:00:00Z",
        )

        result = data.to_dict()

        assert result["rate"] == 3.62
        assert result["valid_from"] == "2024-07-01"
        assert result["valid_until"] == "2024-12-31"
        assert result["source"] == "api"
        assert result["fetched_at"] == "2024-07-15T10:00:00Z"

    def test_basiszins_source_enum(self):
        """Test: BasiszinsSource Enum-Werte."""
        assert BasiszinsSource.API.value == "api"
        assert BasiszinsSource.CACHE.value == "cache"
        assert BasiszinsSource.FALLBACK.value == "fallback"


# =============================================================================
# Refresh Basiszins Tests
# =============================================================================


class TestRefreshBasiszins:
    """Tests fuer refresh_basiszins Methode."""

    @pytest.mark.asyncio
    async def test_refresh_invalidates_cache_and_fetches_api(self):
        """Test: refresh_basiszins invalidiert Cache und holt von API."""
        service = BundesbankRateService()

        api_response = BasiszinsData(
            rate=Decimal("3.75"),
            valid_from="2025-01-01",
            source=BasiszinsSource.API,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

        with patch("app.services.bundesbank_rate_service.invalidate_cache", new_callable=AsyncMock) as mock_inv:
            with patch.object(service, "_fetch_from_api", new_callable=AsyncMock) as mock_api:
                with patch.object(service, "_set_cache", new_callable=AsyncMock) as mock_set:
                    mock_api.return_value = api_response

                    result = await service.refresh_basiszins()

                    # Cache wurde invalidiert
                    mock_inv.assert_called_once()
                    # API wurde aufgerufen
                    mock_api.assert_called_once()
                    # Neuer Wert wurde gecached
                    mock_set.assert_called_once_with(api_response)
                    # Ergebnis ist korrekt
                    assert result.rate == Decimal("3.75")

    @pytest.mark.asyncio
    async def test_refresh_raises_on_api_failure(self):
        """Test: refresh_basiszins wirft RuntimeError bei API-Fehler."""
        service = BundesbankRateService()

        with patch("app.services.bundesbank_rate_service.invalidate_cache", new_callable=AsyncMock):
            with patch.object(service, "_fetch_from_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = Exception("API nicht erreichbar")

                with pytest.raises(RuntimeError, match="Basiszins-Refresh fehlgeschlagen"):
                    await service.refresh_basiszins()

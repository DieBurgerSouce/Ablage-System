# -*- coding: utf-8 -*-
"""
Bundesbank Basiszins API Service.

Holt den aktuellen Basiszinssatz von der Bundesbank:
- Halbjährliche Abfrage (1. Januar und 1. Juli)
- Redis-Caching mit 6-Monats-TTL
- Fallback auf manuell gepflegten Wert
- Historische Daten für Zinsberechnungen

Feature 18: Bundesbank Basiszins-API

SECURITY: Keine sensiblen Daten. Öffentlich verfügbare Zinssätze.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import asyncio

import structlog
import httpx

from app.core.config import settings
from app.core.cache import cache_get, cache_set, invalidate_cache
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Bundesbank API endpoint für Zeitreihen
# BBK01.SU0112: Basiszinssatz nach § 247 BGB
BUNDESBANK_API_URL = "https://api.statistiken.bundesbank.de/rest/data"
BASISZINS_SERIES = "BBK01/SU0112"

# Cache key for Redis
BASISZINS_CACHE_KEY = "bundesbank:basiszins:current"
BASISZINS_HISTORY_CACHE_KEY = "bundesbank:basiszins:history"

# Cache TTL: 6 Monate in Sekunden
CACHE_TTL_SECONDS = 180 * 24 * 60 * 60  # ~180 Tage

# Fallback-Werte (Stand: Januar 2026)
# Diese werden verwendet, wenn die API nicht erreichbar ist
FALLBACK_BASISZINS = Decimal("3.62")
FALLBACK_DATE = "2024-07-01"


# =============================================================================
# Data Classes
# =============================================================================


class BasiszinsSource(str, Enum):
    """Quelle des Basiszinssatzes."""
    API = "api"
    CACHE = "cache"
    FALLBACK = "fallback"


@dataclass
class BasiszinsData:
    """Basiszinssatz-Daten."""
    rate: Decimal
    valid_from: str
    valid_until: Optional[str] = None
    source: BasiszinsSource = BasiszinsSource.API
    fetched_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "rate": float(self.rate),
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "source": self.source.value,
            "fetched_at": self.fetched_at,
        }


@dataclass
class BasiszinsHistory:
    """Historische Basiszinssätze."""
    rates: List[BasiszinsData]
    last_updated: str

    def get_rate_for_date(self, date: datetime) -> Optional[Decimal]:
        """Hole Zinssatz für ein bestimmtes Datum."""
        date_str = date.strftime("%Y-%m-%d")
        for rate_data in sorted(self.rates, key=lambda x: x.valid_from, reverse=True):
            if rate_data.valid_from <= date_str:
                return rate_data.rate
        return None


# =============================================================================
# Service Implementation
# =============================================================================


class BundesbankRateService:
    """Service für Bundesbank-Basiszinssatz."""

    def __init__(self) -> None:
        """Initialisiere Service."""
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Hole oder erstelle HTTP-Client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Ablage-System/1.0",
                },
            )
        return self._client

    async def close(self) -> None:
        """Schließe HTTP-Client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_current_basiszins(self) -> BasiszinsData:
        """
        Hole aktuellen Basiszinssatz.

        Prüft zuerst den Cache, dann die API, dann Fallback.

        Returns:
            BasiszinsData mit aktuellem Zinssatz
        """
        # 1. Check Cache
        cached = await self._get_from_cache()
        if cached:
            logger.debug("Basiszins aus Cache geladen", rate=float(cached.rate))
            return cached

        # 2. Try API
        try:
            api_data = await self._fetch_from_api()
            if api_data:
                # Cache the result
                await self._set_cache(api_data)
                logger.info(
                    "Basiszins von Bundesbank API geladen",
                    rate=float(api_data.rate),
                    valid_from=api_data.valid_from,
                )
                return api_data
        except Exception as e:
            logger.warning(
                "Bundesbank API nicht erreichbar, verwende Fallback",
                **safe_error_log(e),
            )

        # 3. Fallback
        fallback_data = BasiszinsData(
            rate=FALLBACK_BASISZINS,
            valid_from=FALLBACK_DATE,
            source=BasiszinsSource.FALLBACK,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info(
            "Verwende Fallback-Basiszins",
            rate=float(fallback_data.rate),
            valid_from=fallback_data.valid_from,
        )
        return fallback_data

    async def get_basiszins_history(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> BasiszinsHistory:
        """
        Hole historische Basiszinssätze.

        Args:
            start_date: Startdatum (YYYY-MM-DD), default: 2000-01-01
            end_date: Enddatum (YYYY-MM-DD), default: heute

        Returns:
            BasiszinsHistory mit allen Zinssätzen im Zeitraum
        """
        # Check history cache
        cached_history = await cache_get(BASISZINS_HISTORY_CACHE_KEY)
        if cached_history:
            rates = [
                BasiszinsData(
                    rate=Decimal(str(r["rate"])),
                    valid_from=r["valid_from"],
                    valid_until=r.get("valid_until"),
                    source=BasiszinsSource.CACHE,
                )
                for r in cached_history.get("rates", [])
            ]
            return BasiszinsHistory(
                rates=rates,
                last_updated=cached_history.get("last_updated", ""),
            )

        # Fetch from API
        try:
            history = await self._fetch_history_from_api(start_date, end_date)
            if history:
                # Cache the result
                await cache_set(
                    BASISZINS_HISTORY_CACHE_KEY,
                    {
                        "rates": [r.to_dict() for r in history.rates],
                        "last_updated": history.last_updated,
                    },
                    ttl=CACHE_TTL_SECONDS,
                )
                return history
        except Exception as e:
            logger.warning(
                "Bundesbank History API nicht erreichbar",
                **safe_error_log(e),
            )

        # Fallback: Return only current rate
        current = await self.get_current_basiszins()
        return BasiszinsHistory(
            rates=[current],
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

    def calculate_verzugszins(
        self,
        basiszins: Decimal,
        is_b2b: bool = True,
    ) -> Decimal:
        """
        Berechne Verzugszinssatz.

        Nach § 288 BGB:
        - B2C: Basiszins + 5 Prozentpunkte
        - B2B: Basiszins + 9 Prozentpunkte

        Args:
            basiszins: Aktueller Basiszinssatz
            is_b2b: True für Geschäftskunden

        Returns:
            Verzugszinssatz in Prozent
        """
        addition = Decimal("9.0") if is_b2b else Decimal("5.0")
        return basiszins + addition

    async def get_verzugszins(self, is_b2b: bool = True) -> Decimal:
        """
        Hole aktuellen Verzugszinssatz.

        Args:
            is_b2b: True für Geschäftskunden

        Returns:
            Aktueller Verzugszinssatz
        """
        basiszins = await self.get_current_basiszins()
        return self.calculate_verzugszins(basiszins.rate, is_b2b)

    async def refresh_basiszins(self) -> BasiszinsData:
        """
        Erzwinge Neuladung des Basiszinssatzes.

        Löscht den Cache und holt den Wert direkt von der API.
        Wird vom Celery Task am 1.1. und 1.7. aufgerufen.

        Returns:
            Aktueller BasiszinsData

        Raises:
            RuntimeError: Wenn API nicht erreichbar und kein Cache
        """
        # 1. Cache invalidieren
        await invalidate_cache(BASISZINS_CACHE_KEY)
        logger.info("Basiszins-Cache invalidiert für Refresh")

        # 2. Von API holen
        try:
            api_data = await self._fetch_from_api()
            if api_data:
                await self._set_cache(api_data)
                logger.info(
                    "Basiszins erfolgreich aktualisiert",
                    rate=float(api_data.rate),
                    valid_from=api_data.valid_from,
                )
                return api_data
        except Exception as e:
            logger.error(
                "Basiszins-Refresh von API fehlgeschlagen",
                **safe_error_log(e),
            )
            raise RuntimeError(f"Basiszins-Refresh fehlgeschlagen: {e}")

        # 3. Falls API kein Ergebnis liefert, Fallback
        return BasiszinsData(
            rate=FALLBACK_BASISZINS,
            valid_from=FALLBACK_DATE,
            source=BasiszinsSource.FALLBACK,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _get_from_cache(self) -> Optional[BasiszinsData]:
        """Hole Basiszins aus Cache."""
        cached = await cache_get(BASISZINS_CACHE_KEY)
        if not cached:
            return None

        return BasiszinsData(
            rate=Decimal(str(cached["rate"])),
            valid_from=cached["valid_from"],
            valid_until=cached.get("valid_until"),
            source=BasiszinsSource.CACHE,
            fetched_at=cached.get("fetched_at"),
        )

    async def _set_cache(self, data: BasiszinsData) -> None:
        """Setze Basiszins in Cache."""
        await cache_set(
            BASISZINS_CACHE_KEY,
            {
                "rate": float(data.rate),
                "valid_from": data.valid_from,
                "valid_until": data.valid_until,
                "fetched_at": data.fetched_at,
            },
            ttl=CACHE_TTL_SECONDS,
        )

    async def _fetch_from_api(self) -> Optional[BasiszinsData]:
        """
        Hole aktuellen Basiszins von Bundesbank API.

        Die Bundesbank SDMX-REST API liefert Zeitreihen im JSON-Format.
        """
        client = await self._get_client()

        # Construct API URL
        # Format: /data/{flowRef}/{key}?format=json
        url = f"{BUNDESBANK_API_URL}/{BASISZINS_SERIES}"
        params = {
            "format": "json",
            "detail": "dataonly",
            "lastNObservations": "2",  # Letzten 2 Werte (aktuell + vorher)
        }

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            # Parse SDMX-JSON response
            # Structure: dataSets[0].series.0:0:0:0.observations
            datasets = data.get("dataSets", [])
            if not datasets:
                return None

            observations = datasets[0].get("series", {}).get("0:0:0:0", {}).get("observations", {})
            if not observations:
                # Fallback: Try different series key
                observations = self._find_observations(datasets[0])

            if not observations:
                return None

            # Get time dimension values
            dimensions = data.get("structure", {}).get("dimensions", {}).get("observation", [])
            time_values = {}
            for dim in dimensions:
                if dim.get("id") == "TIME_PERIOD":
                    for i, val in enumerate(dim.get("values", [])):
                        time_values[str(i)] = val.get("id", "")

            # Get the most recent observation
            latest_key = max(observations.keys(), key=lambda k: time_values.get(k, ""))
            latest_value = observations[latest_key][0]
            latest_period = time_values.get(latest_key, "")

            # Parse period (e.g., "2024-H1" -> "2024-01-01" or "2024-H2" -> "2024-07-01")
            valid_from = self._parse_period(latest_period)

            return BasiszinsData(
                rate=Decimal(str(latest_value)),
                valid_from=valid_from,
                source=BasiszinsSource.API,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

        except httpx.HTTPStatusError as e:
            logger.warning(
                "Bundesbank API HTTP-Fehler",
                status_code=e.response.status_code,
                **safe_error_log(e),
            )
            return None
        except Exception as e:
            logger.warning(
                "Bundesbank API Fehler",
                **safe_error_log(e),
            )
            return None

    def _find_observations(self, dataset: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find observations in dataset with flexible key."""
        series = dataset.get("series", {})
        for key, value in series.items():
            if "observations" in value:
                return value["observations"]
        return None

    def _parse_period(self, period: str) -> str:
        """
        Parse Bundesbank period format to date.

        Examples:
            "2024-H1" -> "2024-01-01"
            "2024-H2" -> "2024-07-01"
            "2024-01" -> "2024-01-01"
        """
        if "-H1" in period:
            year = period.split("-H1")[0]
            return f"{year}-01-01"
        elif "-H2" in period:
            year = period.split("-H2")[0]
            return f"{year}-07-01"
        elif len(period) == 7:  # YYYY-MM format
            return f"{period}-01"
        else:
            return period

    async def _fetch_history_from_api(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[BasiszinsHistory]:
        """Hole historische Zinssätze von API."""
        client = await self._get_client()

        url = f"{BUNDESBANK_API_URL}/{BASISZINS_SERIES}"
        params = {
            "format": "json",
            "detail": "dataonly",
        }

        if start_date:
            params["startPeriod"] = start_date[:7]  # YYYY-MM
        if end_date:
            params["endPeriod"] = end_date[:7]

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            datasets = data.get("dataSets", [])
            if not datasets:
                return None

            # Parse all observations
            rates: List[BasiszinsData] = []
            series = datasets[0].get("series", {})

            # Get time dimension values
            dimensions = data.get("structure", {}).get("dimensions", {}).get("observation", [])
            time_values = {}
            for dim in dimensions:
                if dim.get("id") == "TIME_PERIOD":
                    for i, val in enumerate(dim.get("values", [])):
                        time_values[str(i)] = val.get("id", "")

            # Find observations
            observations = self._find_observations(datasets[0])
            if observations:
                for key, values in observations.items():
                    if values:
                        period = time_values.get(key, "")
                        valid_from = self._parse_period(period)
                        rates.append(BasiszinsData(
                            rate=Decimal(str(values[0])),
                            valid_from=valid_from,
                            source=BasiszinsSource.API,
                        ))

            return BasiszinsHistory(
                rates=sorted(rates, key=lambda r: r.valid_from, reverse=True),
                last_updated=datetime.now(timezone.utc).isoformat(),
            )

        except Exception as e:
            logger.warning(
                "Bundesbank History API Fehler",
                **safe_error_log(e),
            )
            return None


# =============================================================================
# Service Instance
# =============================================================================

_service: Optional[BundesbankRateService] = None


def get_bundesbank_rate_service() -> BundesbankRateService:
    """Hole Singleton-Instanz des Services."""
    global _service
    if _service is None:
        _service = BundesbankRateService()
    return _service


async def get_current_basiszins() -> BasiszinsData:
    """Convenience-Funktion: Hole aktuellen Basiszins."""
    service = get_bundesbank_rate_service()
    return await service.get_current_basiszins()


async def get_verzugszins(is_b2b: bool = True) -> Decimal:
    """Convenience-Funktion: Hole aktuellen Verzugszins."""
    service = get_bundesbank_rate_service()
    return await service.get_verzugszins(is_b2b)


# Singleton-Instanz für direkten Import (Celery Tasks, etc.)
bundesbank_rate_service = get_bundesbank_rate_service()

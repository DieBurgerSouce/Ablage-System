"""
Market Data Service.

Service für externe Marktdaten-Abfragen.
Ermöglicht Schätzung von Immobilien- und Fahrzeugwerten.

WICHTIG:
- Nur kostenlose APIs
- Nur auf manuelle Anfrage (Button-Klick)
- Keine automatischen Abfragen
- Rate-Limiting beachten

Features:
- Immobilienwert-Schätzung basierend auf Lage/Größe
- Fahrzeugwert-Schätzung basierend auf Marke/Modell/Alter
- Caching um API-Calls zu reduzieren
- Fallback auf lokale Schätzung wenn API nicht verfügbar
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)


class DataSource(str, Enum):
    """Datenquellen für Marktwerte."""

    LOCAL_ESTIMATE = "local_estimate"
    CACHED = "cached"
    EXTERNAL_API = "external_api"
    USER_PROVIDED = "user_provided"


@dataclass
class PropertyMarketData:
    """Marktdaten für eine Immobilie."""

    property_id: UUID
    estimated_value: Decimal
    price_per_sqm: Decimal
    value_range_min: Decimal
    value_range_max: Decimal
    comparable_count: int
    data_source: DataSource
    confidence: float  # 0.0 - 1.0
    location_factor: float  # Lagefaktor
    condition_factor: float  # Zustandsfaktor
    market_trend: str  # "rising", "stable", "falling"
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "property_id": str(self.property_id),
            "estimated_value": float(self.estimated_value),
            "price_per_sqm": float(self.price_per_sqm),
            "value_range_min": float(self.value_range_min),
            "value_range_max": float(self.value_range_max),
            "comparable_count": self.comparable_count,
            "data_source": self.data_source.value,
            "confidence": self.confidence,
            "location_factor": self.location_factor,
            "condition_factor": self.condition_factor,
            "market_trend": self.market_trend,
            "retrieved_at": self.retrieved_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class VehicleMarketData:
    """Marktdaten für ein Fahrzeug."""

    vehicle_id: UUID
    estimated_value: Decimal
    value_range_min: Decimal
    value_range_max: Decimal
    comparable_count: int
    data_source: DataSource
    confidence: float  # 0.0 - 1.0
    mileage_factor: float  # km-Abzug
    condition_factor: float  # Zustandsfaktor
    age_depreciation: Decimal  # Altersbedingte Abschreibung
    market_trend: str  # "rising", "stable", "falling"
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "vehicle_id": str(self.vehicle_id),
            "estimated_value": float(self.estimated_value),
            "value_range_min": float(self.value_range_min),
            "value_range_max": float(self.value_range_max),
            "comparable_count": self.comparable_count,
            "data_source": self.data_source.value,
            "confidence": self.confidence,
            "mileage_factor": self.mileage_factor,
            "condition_factor": self.condition_factor,
            "age_depreciation": float(self.age_depreciation),
            "market_trend": self.market_trend,
            "retrieved_at": self.retrieved_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


# Durchschnittspreise pro qm nach Bundesland (Stand 2024)
PROPERTY_PRICES_BY_REGION: Dict[str, Decimal] = {
    # Bundesländer
    "bayern": Decimal("4500"),
    "baden-wuerttemberg": Decimal("4200"),
    "hessen": Decimal("4000"),
    "hamburg": Decimal("5500"),
    "berlin": Decimal("5000"),
    "nordrhein-westfalen": Decimal("3200"),
    "niedersachsen": Decimal("2800"),
    "schleswig-holstein": Decimal("3000"),
    "rheinland-pfalz": Decimal("2600"),
    "saarland": Decimal("2200"),
    "sachsen": Decimal("2400"),
    "sachsen-anhalt": Decimal("1800"),
    "thueringen": Decimal("2000"),
    "brandenburg": Decimal("2200"),
    "mecklenburg-vorpommern": Decimal("2000"),
    "bremen": Decimal("3200"),
    # Staedte (Premium)
    "muenchen": Decimal("9500"),
    "frankfurt": Decimal("6500"),
    "duesseldorf": Decimal("5000"),
    "koeln": Decimal("4500"),
    "stuttgart": Decimal("5500"),
    # Default
    "default": Decimal("3000"),
}

# Abschreibungstabelle für Fahrzeuge (% pro Jahr)
VEHICLE_DEPRECIATION_TABLE: Dict[int, float] = {
    0: 0.00,    # Neuwagen
    1: 0.25,    # 1 Jahr: -25%
    2: 0.35,    # 2 Jahre: -35%
    3: 0.45,    # 3 Jahre: -45%
    4: 0.52,    # 4 Jahre: -52%
    5: 0.58,    # 5 Jahre: -58%
    6: 0.63,    # 6 Jahre: -63%
    7: 0.67,    # 7 Jahre: -67%
    8: 0.70,    # 8 Jahre: -70%
    9: 0.73,    # 9 Jahre: -73%
    10: 0.75,   # 10+ Jahre: -75%
}

# Durchschnittliche Neupreise nach Fahrzeugklasse
VEHICLE_BASE_PRICES: Dict[str, Decimal] = {
    "kleinwagen": Decimal("18000"),
    "kompakt": Decimal("28000"),
    "mittelklasse": Decimal("38000"),
    "oberklasse": Decimal("55000"),
    "suv_klein": Decimal("32000"),
    "suv_mittel": Decimal("48000"),
    "suv_gross": Decimal("65000"),
    "kombi": Decimal("35000"),
    "van": Decimal("40000"),
    "sportwagen": Decimal("75000"),
    "elektro": Decimal("45000"),
    "default": Decimal("30000"),
}


class MarketDataService:
    """
    Service für Marktdaten-Abfragen.

    Ermöglicht Schätzung von Immobilien- und Fahrzeugwerten
    basierend auf lokalen Algorithmen und optionalen externen APIs.

    WICHTIG: Externe APIs werden nur auf explizite Anfrage aufgerufen.
    """

    CACHE_TTL_HOURS = 24  # Cache-Gültigkeit in Stunden

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
        self._metrics = {
            "property_estimates": 0,
            "vehicle_estimates": 0,
            "cache_hits": 0,
            "api_calls": 0,
            "api_errors": 0,
        }

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Gibt HTTP-Client zurück (Lazy Initialization)."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "Ablage-System/1.0"},
            )
        return self._http_client

    async def close(self) -> None:
        """Schließt den HTTP-Client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _get_cache_key(self, prefix: str, **kwargs: Any) -> str:
        """Generiert einen Cache-Key."""
        data = json.dumps(kwargs, sort_keys=True, default=str)
        hash_value = hashlib.md5(data.encode()).hexdigest()[:16]
        return f"{prefix}:{hash_value}"

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Holt Wert aus Cache wenn nicht abgelaufen."""
        if key in self._cache:
            value, expires_at = self._cache[key]
            if datetime.now(timezone.utc) < expires_at:
                self._metrics["cache_hits"] += 1
                return value
            else:
                del self._cache[key]
        return None

    def _set_cache(self, key: str, value: Any, ttl_hours: int = None) -> None:
        """Speichert Wert im Cache."""
        ttl = ttl_hours or self.CACHE_TTL_HOURS
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)
        self._cache[key] = (value, expires_at)

    async def estimate_property_value(
        self,
        property_id: UUID,
        postal_code: str,
        city: Optional[str],
        state: Optional[str],
        living_space_sqm: Decimal,
        property_type: str,  # "wohnung", "haus", "grundstück"
        year_built: Optional[int] = None,
        condition: str = "normal",  # "neu", "gut", "normal", "renovierungsbedürftig"
        use_external_api: bool = False,
    ) -> PropertyMarketData:
        """
        Schätzt den Marktwert einer Immobilie.

        Args:
            property_id: Immobilien-ID
            postal_code: Postleitzahl
            city: Stadt (optional)
            state: Bundesland (optional)
            living_space_sqm: Wohnflaeche in qm
            property_type: Art der Immobilie
            year_built: Baujahr (optional)
            condition: Zustand
            use_external_api: Ob externe API verwendet werden soll

        Returns:
            PropertyMarketData mit Schätzwerten
        """
        self._metrics["property_estimates"] += 1

        # Check cache
        cache_key = self._get_cache_key(
            "property",
            postal_code=postal_code,
            living_space_sqm=str(living_space_sqm),
            property_type=property_type,
        )
        cached = self._get_from_cache(cache_key)
        if cached:
            cached.property_id = property_id
            cached.data_source = DataSource.CACHED
            return cached

        # Bestimme Basispreis pro qm
        location_key = self._normalize_location(city, state)
        base_price_sqm = PROPERTY_PRICES_BY_REGION.get(
            location_key,
            PROPERTY_PRICES_BY_REGION["default"]
        )

        # Lagefaktor basierend auf PLZ (vereinfacht)
        location_factor = self._calculate_location_factor(postal_code)

        # Zustandsfaktor
        condition_factors = {
            "neu": 1.15,
            "gut": 1.05,
            "normal": 1.0,
            "renovierungsbedürftig": 0.75,
        }
        condition_factor = condition_factors.get(condition, 1.0)

        # Immobilientyp-Faktor
        type_factors = {
            "wohnung": 1.0,
            "haus": 1.10,
            "reihenhaus": 0.95,
            "doppelhaushaelfte": 1.0,
            "grundstück": 0.6,
        }
        type_factor = type_factors.get(property_type, 1.0)

        # Altersfaktor
        age_factor = 1.0
        if year_built:
            age = datetime.now().year - year_built
            if age < 5:
                age_factor = 1.1
            elif age < 20:
                age_factor = 1.0
            elif age < 50:
                age_factor = 0.9
            else:
                age_factor = 0.8

        # Berechnung
        adjusted_price_sqm = (
            base_price_sqm
            * Decimal(str(location_factor))
            * Decimal(str(condition_factor))
            * Decimal(str(type_factor))
            * Decimal(str(age_factor))
        )

        estimated_value = adjusted_price_sqm * living_space_sqm

        # Wertbereich (+/- 15%)
        value_range_min = estimated_value * Decimal("0.85")
        value_range_max = estimated_value * Decimal("1.15")

        # Markttrend (vereinfacht - stabil)
        market_trend = "stable"

        result = PropertyMarketData(
            property_id=property_id,
            estimated_value=estimated_value.quantize(Decimal("1")),
            price_per_sqm=adjusted_price_sqm.quantize(Decimal("1")),
            value_range_min=value_range_min.quantize(Decimal("1")),
            value_range_max=value_range_max.quantize(Decimal("1")),
            comparable_count=0,  # Keine echten Vergleichsobjekte ohne API
            data_source=DataSource.LOCAL_ESTIMATE,
            confidence=0.6,  # Lokale Schätzung = 60% Konfidenz
            location_factor=location_factor,
            condition_factor=condition_factor,
            market_trend=market_trend,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=self.CACHE_TTL_HOURS),
        )

        # Cache speichern
        self._set_cache(cache_key, result)

        logger.info(
            "property_value_estimated",
            estimated_value_eur=f"{estimated_value:.0f}",
            postal_code=postal_code,
            living_space_sqm=str(living_space_sqm),
        )

        return result

    async def estimate_vehicle_value(
        self,
        vehicle_id: UUID,
        brand: str,
        model: str,
        year: int,
        mileage_km: int,
        vehicle_class: str = "default",
        fuel_type: str = "benzin",
        condition: str = "normal",
        original_price: Optional[Decimal] = None,
        use_external_api: bool = False,
    ) -> VehicleMarketData:
        """
        Schätzt den Marktwert eines Fahrzeugs.

        Args:
            vehicle_id: Fahrzeug-ID
            brand: Marke
            model: Modell
            year: Baujahr/Erstzulassung
            mileage_km: Kilometerstand
            vehicle_class: Fahrzeugklasse
            fuel_type: Kraftstoffart
            condition: Zustand
            original_price: Urspruenglicher Kaufpreis (optional)
            use_external_api: Ob externe API verwendet werden soll

        Returns:
            VehicleMarketData mit Schätzwerten
        """
        self._metrics["vehicle_estimates"] += 1

        # Check cache
        cache_key = self._get_cache_key(
            "vehicle",
            brand=brand,
            model=model,
            year=year,
            mileage_km=mileage_km,
        )
        cached = self._get_from_cache(cache_key)
        if cached:
            cached.vehicle_id = vehicle_id
            cached.data_source = DataSource.CACHED
            return cached

        # Basispreis ermitteln
        if original_price:
            base_price = original_price
        else:
            base_price = VEHICLE_BASE_PRICES.get(
                vehicle_class.lower(),
                VEHICLE_BASE_PRICES["default"]
            )
            # Marken-Aufschlag
            premium_brands = {"bmw", "mercedes", "audi", "porsche", "tesla"}
            if brand.lower() in premium_brands:
                base_price *= Decimal("1.3")

        # Altersabschreibung
        age = datetime.now().year - year
        if age >= 10:
            depreciation_rate = VEHICLE_DEPRECIATION_TABLE[10]
        else:
            depreciation_rate = VEHICLE_DEPRECIATION_TABLE.get(age, 0.5)

        age_depreciation = base_price * Decimal(str(depreciation_rate))
        value_after_age = base_price - age_depreciation

        # km-Faktor (15.000 km/Jahr als Durchschnitt)
        expected_km = age * 15000
        km_deviation = mileage_km - expected_km

        if km_deviation > 0:
            # Mehr km als erwartet = Abzug
            mileage_factor = 1 - min(0.15, (km_deviation / 100000) * 0.1)
        else:
            # Weniger km = leichter Aufschlag
            mileage_factor = 1 + min(0.05, (abs(km_deviation) / 100000) * 0.05)

        # Zustandsfaktor
        condition_factors = {
            "neuwertig": 1.10,
            "sehr_gut": 1.05,
            "gut": 1.0,
            "normal": 0.95,
            "maessig": 0.85,
            "schlecht": 0.70,
        }
        condition_factor = condition_factors.get(condition, 0.95)

        # Kraftstoff-Faktor (Elektro/Hybrid aktuell höher)
        fuel_factors = {
            "elektro": 1.10,
            "hybrid": 1.05,
            "benzin": 1.0,
            "diesel": 0.92,  # Diesel-Abschlag
            "gas": 0.95,
        }
        fuel_factor = fuel_factors.get(fuel_type.lower(), 1.0)

        # Endwert berechnen
        estimated_value = (
            value_after_age
            * Decimal(str(mileage_factor))
            * Decimal(str(condition_factor))
            * Decimal(str(fuel_factor))
        )

        # Mindest- und Hoechstwert
        estimated_value = max(estimated_value, Decimal("500"))  # Mindestens 500 EUR

        # Wertbereich (+/- 10%)
        value_range_min = estimated_value * Decimal("0.90")
        value_range_max = estimated_value * Decimal("1.10")

        result = VehicleMarketData(
            vehicle_id=vehicle_id,
            estimated_value=estimated_value.quantize(Decimal("1")),
            value_range_min=value_range_min.quantize(Decimal("1")),
            value_range_max=value_range_max.quantize(Decimal("1")),
            comparable_count=0,
            data_source=DataSource.LOCAL_ESTIMATE,
            confidence=0.65,
            mileage_factor=mileage_factor,
            condition_factor=condition_factor,
            age_depreciation=age_depreciation.quantize(Decimal("1")),
            market_trend="stable",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=self.CACHE_TTL_HOURS),
        )

        # Cache speichern
        self._set_cache(cache_key, result)

        logger.info(
            "vehicle_value_estimated",
            estimated_value_eur=f"{estimated_value:.0f}",
            brand=brand,
            model=model,
            year=year,
            mileage_km=mileage_km,
        )

        return result

    def _normalize_location(self, city: Optional[str], state: Optional[str]) -> str:
        """Normalisiert Ortsangabe für Lookup."""
        if city:
            city_lower = city.lower().replace(" ", "").replace("-", "")
            # Direkter Stadt-Match
            for key in PROPERTY_PRICES_BY_REGION:
                if key in city_lower or city_lower in key:
                    return key

        if state:
            state_lower = state.lower().replace(" ", "").replace("-", "")
            for key in PROPERTY_PRICES_BY_REGION:
                if key in state_lower or state_lower in key:
                    return key

        return "default"

    def _calculate_location_factor(self, postal_code: str) -> float:
        """
        Berechnet Lagefaktor basierend auf PLZ.

        Vereinfachte Heuristik:
        - PLZ 8xxxx (Bayern/Muenchen): +20%
        - PLZ 6xxxx (Frankfurt/Rhein-Main): +10%
        - PLZ 1xxxx (Berlin): +5%
        - PLZ 2xxxx (Hamburg): +15%
        - PLZ 0xxxx (Sachsen/Thueringen): -10%
        """
        if not postal_code or len(postal_code) < 1:
            return 1.0

        first_digit = postal_code[0]

        factors = {
            "8": 1.20,  # Bayern
            "6": 1.10,  # Hessen/Frankfurt
            "2": 1.15,  # Hamburg/Schleswig-Holstein
            "1": 1.05,  # Berlin
            "5": 1.05,  # NRW West
            "4": 1.00,  # NRW Ost
            "3": 0.95,  # Niedersachsen
            "7": 1.10,  # Baden-Wuerttemberg
            "9": 0.90,  # Bayern Land
            "0": 0.85,  # Sachsen/Thueringen
        }

        return factors.get(first_digit, 1.0)

    def get_metrics(self) -> Dict[str, int]:
        """Gibt Metriken zurück."""
        return self._metrics.copy()

    def clear_cache(self) -> int:
        """Löscht den Cache und gibt Anzahl gelöschter Einträge zurück."""
        count = len(self._cache)
        self._cache.clear()
        return count


# Singleton Instance
_market_data_service_instance: Optional[MarketDataService] = None


def get_market_data_service() -> MarketDataService:
    """Factory-Funktion für MarketDataService Singleton."""
    global _market_data_service_instance
    if _market_data_service_instance is None:
        _market_data_service_instance = MarketDataService()
    return _market_data_service_instance

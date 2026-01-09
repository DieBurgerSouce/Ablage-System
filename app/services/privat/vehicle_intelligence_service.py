# -*- coding: utf-8 -*-
"""
VehicleIntelligenceService - Intelligente Fahrzeug-Analyse und TCO.

Berechnet automatisch:
- Wertverlust/Restwert (markenspezifische Depreciation-Kurven)
- Total Cost of Ownership (TCO)
- Kraftstoffverbrauch-Analyse mit Trend
- Service-Prognosen
- Optimale Verkaufszeitpunkte

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

VEHICLE_INTEL_CALCULATIONS = Counter(
    "vehicle_intelligence_calculations_total",
    "Anzahl der Vehicle-Intelligence Berechnungen",
    ["calculation_type"]
)

VEHICLE_INTEL_DURATION = Histogram(
    "vehicle_intelligence_duration_seconds",
    "Dauer der Vehicle-Intelligence Berechnung",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)


# =============================================================================
# Referenzdaten - Depreciation Kurven nach Fahrzeugklasse
# =============================================================================

# Wertverlust-Faktoren nach Jahr (kumulativ vom Neuwert)
# Format: Jahr -> Restwert in % vom Neuwert
DEPRECIATION_CURVES: Dict[str, Dict[int, float]] = {
    # Premium-Marken (Mercedes, BMW, Audi, Porsche)
    "premium": {
        0: 1.0, 1: 0.78, 2: 0.65, 3: 0.55, 4: 0.48,
        5: 0.42, 6: 0.37, 7: 0.33, 8: 0.30, 9: 0.27, 10: 0.25,
        11: 0.23, 12: 0.21, 13: 0.19, 14: 0.17, 15: 0.15
    },
    # Volumenhersteller (VW, Ford, Opel, Skoda)
    "volume": {
        0: 1.0, 1: 0.72, 2: 0.58, 3: 0.48, 4: 0.42,
        5: 0.36, 6: 0.32, 7: 0.28, 8: 0.25, 9: 0.22, 10: 0.20,
        11: 0.18, 12: 0.16, 13: 0.14, 14: 0.12, 15: 0.10
    },
    # Budget-Marken (Dacia, Fiat, Hyundai, Kia)
    "budget": {
        0: 1.0, 1: 0.68, 2: 0.52, 3: 0.42, 4: 0.35,
        5: 0.30, 6: 0.26, 7: 0.23, 8: 0.20, 9: 0.18, 10: 0.16,
        11: 0.14, 12: 0.12, 13: 0.10, 14: 0.08, 15: 0.07
    },
    # Elektrofahrzeuge (schnellerer Wertverlust wegen Batterie)
    "electric": {
        0: 1.0, 1: 0.70, 2: 0.55, 3: 0.45, 4: 0.38,
        5: 0.32, 6: 0.27, 7: 0.23, 8: 0.20, 9: 0.17, 10: 0.15,
        11: 0.13, 12: 0.11, 13: 0.09, 14: 0.08, 15: 0.07
    },
    # Oldtimer/Klassiker (steigender Wert nach 25+ Jahren)
    "classic": {
        0: 1.0, 1: 0.90, 2: 0.85, 3: 0.82, 4: 0.80,
        5: 0.78, 10: 0.85, 15: 0.95, 20: 1.10, 25: 1.30,
        30: 1.50, 35: 1.80, 40: 2.20
    }
}

# Marken-Klassifizierung
MAKE_TO_CLASS: Dict[str, str] = {
    # Premium
    "mercedes": "premium", "mercedes-benz": "premium", "bmw": "premium",
    "audi": "premium", "porsche": "premium", "lexus": "premium",
    "volvo": "premium", "jaguar": "premium", "land rover": "premium",
    # Volume
    "volkswagen": "volume", "vw": "volume", "ford": "volume",
    "opel": "volume", "skoda": "volume", "seat": "volume",
    "toyota": "volume", "honda": "volume", "mazda": "volume",
    "peugeot": "volume", "renault": "volume", "citroen": "volume",
    # Budget
    "dacia": "budget", "fiat": "budget", "hyundai": "budget",
    "kia": "budget", "suzuki": "budget", "mitsubishi": "budget",
    # Electric
    "tesla": "electric",
}

# Kraftstoffkosten-Referenz (Euro pro Liter/kWh)
FUEL_COSTS: Dict[str, Decimal] = {
    "benzin": Decimal("1.75"),
    "diesel": Decimal("1.65"),
    "super": Decimal("1.80"),
    "e10": Decimal("1.70"),
    "elektro": Decimal("0.35"),  # pro kWh
    "gas": Decimal("1.20"),
    "lpg": Decimal("0.90"),
}

# Service-Intervalle nach Kraftstoff (km)
SERVICE_INTERVALS: Dict[str, int] = {
    "benzin": 15000,
    "diesel": 20000,
    "elektro": 30000,
    "hybrid": 15000,
    "gas": 15000,
    "default": 15000,
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class VehicleDepreciation:
    """Wertverlust-Berechnung."""
    vehicle_id: UUID
    purchase_price: Decimal
    current_estimated_value: Decimal
    depreciation_absolute: Decimal
    depreciation_percent: Decimal
    monthly_depreciation: Decimal
    vehicle_class: str
    age_years: Decimal
    mileage_factor: Decimal = Decimal("1.0")
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class VehicleTCO:
    """Total Cost of Ownership."""
    vehicle_id: UUID

    # Anschaffung
    purchase_price: Decimal = Decimal("0")
    current_value: Decimal = Decimal("0")
    depreciation_total: Decimal = Decimal("0")

    # Laufende Kosten (jaehrlich)
    fuel_costs_annual: Decimal = Decimal("0")
    insurance_annual: Decimal = Decimal("0")
    tax_annual: Decimal = Decimal("0")
    maintenance_annual: Decimal = Decimal("0")
    repairs_annual: Decimal = Decimal("0")

    # Zusammenfassung
    total_annual_costs: Decimal = Decimal("0")
    cost_per_km: Decimal = Decimal("0")
    cost_per_month: Decimal = Decimal("0")

    # Prognose
    projected_annual_costs_next_year: Decimal = Decimal("0")

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FuelAnalysis:
    """Kraftstoffverbrauch-Analyse."""
    vehicle_id: UUID

    # Durchschnitte
    average_consumption: Decimal  # l/100km oder kWh/100km
    average_cost_per_100km: Decimal
    average_cost_per_fill: Decimal

    # Trend
    consumption_trend: str  # "improving", "stable", "worsening"
    trend_percent: Decimal

    # Anomalien
    anomalies: List[Dict[str, Any]] = field(default_factory=list)

    # Statistik
    total_fuel_cost_ytd: Decimal = Decimal("0")
    total_km_ytd: int = 0
    fill_count_ytd: int = 0

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ServicePrediction:
    """Service-Prognose."""
    vehicle_id: UUID

    # Naechster Service
    next_service_km: int
    next_service_date: Optional[date] = None
    km_until_service: int = 0
    days_until_service: Optional[int] = None

    # TUeV/HU
    tuev_due: Optional[date] = None
    days_until_tuev: Optional[int] = None

    # Geschaetzte Kosten
    estimated_service_cost: Decimal = Decimal("0")
    estimated_tuev_cost: Decimal = Decimal("150")

    # Empfehlungen
    recommendations: List[str] = field(default_factory=list)

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class VehicleAnalytics:
    """Vollstaendige Fahrzeug-Analytics."""
    vehicle_id: UUID

    depreciation: Optional[VehicleDepreciation] = None
    tco: Optional[VehicleTCO] = None
    fuel_analysis: Optional[FuelAnalysis] = None
    service_prediction: Optional[ServicePrediction] = None

    # Gesundheits-Score
    health_score: Decimal = Decimal("0")
    recommendations: List[str] = field(default_factory=list)

    # Optimaler Verkaufszeitpunkt
    optimal_sell_date: Optional[date] = None
    optimal_sell_reason: str = ""

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Service
# =============================================================================

class VehicleIntelligenceService:
    """
    Intelligente Fahrzeug-Analyse ohne externe APIs.

    Features:
    - Wertverlust nach Markenklasse und Alter
    - Total Cost of Ownership
    - Kraftstoffverbrauch-Trends
    - Service-Prognosen
    - Verkaufsempfehlungen
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    # =========================================================================
    # Wertverlust/Depreciation
    # =========================================================================

    async def calculate_depreciation(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
    ) -> Optional[VehicleDepreciation]:
        """
        Berechnet den Wertverlust eines Fahrzeugs.

        Methodik:
        1. Fahrzeugklasse aus Marke bestimmen
        2. Alter in Jahren berechnen
        3. Depreciation-Kurve anwenden
        4. Kilometerstand-Faktor (optional)
        """
        from app.db.models import PrivatVehicle

        VEHICLE_INTEL_CALCULATIONS.labels(calculation_type="depreciation").inc()

        result = await db.execute(
            select(PrivatVehicle).where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            return None

        if not vehicle.purchase_price or vehicle.purchase_price <= 0:
            return None

        purchase_price = Decimal(str(vehicle.purchase_price))

        # Fahrzeugklasse bestimmen
        vehicle_class = self._get_vehicle_class(vehicle.make, vehicle.fuel_type)

        # Alter berechnen
        purchase_date = vehicle.purchase_date or date.today()
        age_days = (date.today() - purchase_date).days
        age_years = Decimal(str(age_days)) / Decimal("365.25")

        # Depreciation-Faktor aus Kurve
        depreciation_curve = DEPRECIATION_CURVES.get(vehicle_class, DEPRECIATION_CURVES["volume"])
        retention_factor = self._interpolate_depreciation(depreciation_curve, float(age_years))

        # Kilometerstand-Faktor (wenn verfuegbar)
        mileage_factor = Decimal("1.0")
        if vehicle.current_mileage and age_years > 0:
            expected_annual_km = 15000  # Durchschnitt
            expected_km = int(float(age_years) * expected_annual_km)
            actual_km = vehicle.current_mileage

            if expected_km > 0:
                km_ratio = actual_km / expected_km
                if km_ratio > 1.2:  # Mehr als 20% ueber Durchschnitt
                    mileage_factor = Decimal("0.95")
                elif km_ratio > 1.5:  # Mehr als 50% ueber Durchschnitt
                    mileage_factor = Decimal("0.90")
                elif km_ratio < 0.7:  # Weniger als 70% des Durchschnitts
                    mileage_factor = Decimal("1.05")

        # Aktueller Wert berechnen
        current_value = (
            purchase_price * Decimal(str(retention_factor)) * mileage_factor
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Mindestwert: 5% des Kaufpreises
        min_value = purchase_price * Decimal("0.05")
        if current_value < min_value:
            current_value = min_value

        # Depreciation
        depreciation_absolute = purchase_price - current_value
        depreciation_percent = (
            (depreciation_absolute / purchase_price) * 100
        ).quantize(Decimal("0.01"))

        # Monatliche Abschreibung
        months_held = max(1, int(age_days / 30))
        monthly_depreciation = (
            depreciation_absolute / Decimal(str(months_held))
        ).quantize(Decimal("0.01"))

        logger.info(
            "vehicle_depreciation_calculated",
            vehicle_id=str(vehicle_id),
            vehicle_class=vehicle_class,
            age_years=float(age_years),
            retention_factor=retention_factor,
            current_value=float(current_value),
        )

        return VehicleDepreciation(
            vehicle_id=vehicle_id,
            purchase_price=purchase_price,
            current_estimated_value=current_value,
            depreciation_absolute=depreciation_absolute,
            depreciation_percent=depreciation_percent,
            monthly_depreciation=monthly_depreciation,
            vehicle_class=vehicle_class,
            age_years=age_years.quantize(Decimal("0.1")),
            mileage_factor=mileage_factor,
        )

    def _get_vehicle_class(self, make: Optional[str], fuel_type: Optional[str]) -> str:
        """Bestimmt die Fahrzeugklasse."""
        if fuel_type and "elektro" in fuel_type.lower():
            return "electric"

        if make:
            make_lower = make.lower().strip()
            if make_lower in MAKE_TO_CLASS:
                return MAKE_TO_CLASS[make_lower]

        return "volume"  # Default

    def _interpolate_depreciation(self, curve: Dict[int, float], age_years: float) -> float:
        """Interpoliert den Depreciation-Faktor."""
        if age_years <= 0:
            return 1.0

        years = sorted(curve.keys())

        # Exakter Treffer
        year_int = int(age_years)
        if year_int in curve:
            return curve[year_int]

        # Interpolation
        lower_year = max(y for y in years if y <= age_years) if any(y <= age_years for y in years) else years[0]
        upper_year = min(y for y in years if y > age_years) if any(y > age_years for y in years) else years[-1]

        if lower_year == upper_year:
            return curve[lower_year]

        # Lineare Interpolation
        lower_factor = curve[lower_year]
        upper_factor = curve[upper_year]
        ratio = (age_years - lower_year) / (upper_year - lower_year)

        return lower_factor + (upper_factor - lower_factor) * ratio

    # =========================================================================
    # Total Cost of Ownership
    # =========================================================================

    async def calculate_tco(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
    ) -> Optional[VehicleTCO]:
        """
        Berechnet die Total Cost of Ownership.

        Komponenten:
        - Wertverlust
        - Kraftstoff
        - Versicherung
        - Steuern
        - Wartung + Reparaturen
        """
        from app.db.models import PrivatVehicle, PrivatFuelLog

        VEHICLE_INTEL_CALCULATIONS.labels(calculation_type="tco").inc()

        result = await db.execute(
            select(PrivatVehicle)
            .options(selectinload(PrivatVehicle.fuel_logs))
            .where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            return None

        tco = VehicleTCO(vehicle_id=vehicle_id)

        # 1. Depreciation
        depreciation = await self.calculate_depreciation(db, vehicle_id)
        if depreciation:
            tco.purchase_price = depreciation.purchase_price
            tco.current_value = depreciation.current_estimated_value
            tco.depreciation_total = depreciation.depreciation_absolute

        # 2. Kraftstoffkosten (aus Fuel Logs)
        one_year_ago = date.today() - timedelta(days=365)
        annual_fuel_cost = Decimal("0")

        for log in vehicle.fuel_logs:
            if log.date >= one_year_ago:
                annual_fuel_cost += Decimal(str(log.total_cost or 0))

        tco.fuel_costs_annual = annual_fuel_cost

        # 3. Versicherung
        if vehicle.insurance_premium:
            tco.insurance_annual = Decimal(str(vehicle.insurance_premium))

        # 4. KFZ-Steuer (Schaetzung basierend auf Hubraum/CO2)
        # Vereinfacht: 100-300 EUR fuer PKW
        tco.tax_annual = Decimal("180")  # Durchschnitt

        # 5. Wartung (Schaetzung)
        # Junge Autos: ~300 EUR, Alte: ~600 EUR
        age_years = 0
        if vehicle.purchase_date:
            age_years = (date.today() - vehicle.purchase_date).days / 365.25

        if age_years < 3:
            tco.maintenance_annual = Decimal("300")
        elif age_years < 6:
            tco.maintenance_annual = Decimal("450")
        else:
            tco.maintenance_annual = Decimal("600")

        # 6. Reparaturen (Schaetzung)
        if age_years < 3:
            tco.repairs_annual = Decimal("100")
        elif age_years < 6:
            tco.repairs_annual = Decimal("300")
        else:
            tco.repairs_annual = Decimal("500")

        # Gesamt
        tco.total_annual_costs = (
            tco.fuel_costs_annual +
            tco.insurance_annual +
            tco.tax_annual +
            tco.maintenance_annual +
            tco.repairs_annual
        )

        tco.cost_per_month = (
            tco.total_annual_costs / 12
        ).quantize(Decimal("0.01"))

        # Kosten pro km
        if vehicle.current_mileage and vehicle.purchase_date:
            annual_km = vehicle.current_mileage / max(1, age_years) if age_years > 0 else 15000
            if annual_km > 0:
                tco.cost_per_km = (
                    tco.total_annual_costs / Decimal(str(annual_km))
                ).quantize(Decimal("0.01"))

        # Prognose naechstes Jahr (leichte Steigerung)
        tco.projected_annual_costs_next_year = (
            tco.total_annual_costs * Decimal("1.05")
        ).quantize(Decimal("0.01"))

        return tco

    # =========================================================================
    # Kraftstoff-Analyse
    # =========================================================================

    async def analyze_fuel_consumption(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
    ) -> Optional[FuelAnalysis]:
        """
        Analysiert den Kraftstoffverbrauch.

        Features:
        - Durchschnittsverbrauch
        - Trend-Erkennung
        - Anomalie-Warnung
        """
        from app.db.models import PrivatVehicle, PrivatFuelLog

        VEHICLE_INTEL_CALCULATIONS.labels(calculation_type="fuel_analysis").inc()

        result = await db.execute(
            select(PrivatVehicle)
            .options(selectinload(PrivatVehicle.fuel_logs))
            .where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle or not vehicle.fuel_logs:
            return None

        # Sortiere nach Datum
        fuel_logs = sorted(vehicle.fuel_logs, key=lambda x: x.date)

        if len(fuel_logs) < 2:
            return None

        # Verbrauch berechnen (benoetigt 2 aufeinanderfolgende Tankungen)
        consumptions: List[Decimal] = []
        costs: List[Decimal] = []
        anomalies: List[Dict[str, Any]] = []

        for i in range(1, len(fuel_logs)):
            current = fuel_logs[i]
            previous = fuel_logs[i - 1]

            if current.mileage and previous.mileage and current.liters:
                km_driven = current.mileage - previous.mileage
                if km_driven > 0:
                    consumption = (Decimal(str(current.liters)) / Decimal(str(km_driven))) * 100
                    consumptions.append(consumption)
                    costs.append(Decimal(str(current.total_cost)))

        if not consumptions:
            return None

        # Durchschnitte
        avg_consumption = sum(consumptions) / len(consumptions)
        avg_cost = sum(costs) / len(costs) if costs else Decimal("0")

        # Kosten pro 100km
        fuel_type = (vehicle.fuel_type or "benzin").lower()
        fuel_price = FUEL_COSTS.get(fuel_type, Decimal("1.75"))
        avg_cost_per_100km = avg_consumption * fuel_price

        # Trend (erste Haelfte vs. zweite Haelfte)
        trend = "stable"
        trend_percent = Decimal("0")

        if len(consumptions) >= 4:
            mid = len(consumptions) // 2
            first_half_avg = sum(consumptions[:mid]) / mid
            second_half_avg = sum(consumptions[mid:]) / (len(consumptions) - mid)

            if second_half_avg > first_half_avg * Decimal("1.1"):
                trend = "worsening"
                trend_percent = ((second_half_avg - first_half_avg) / first_half_avg * 100).quantize(Decimal("0.1"))
            elif second_half_avg < first_half_avg * Decimal("0.9"):
                trend = "improving"
                trend_percent = ((first_half_avg - second_half_avg) / first_half_avg * 100).quantize(Decimal("0.1"))

        # Anomalien erkennen (>20% ueber Durchschnitt)
        for i, consumption in enumerate(consumptions):
            if consumption > avg_consumption * Decimal("1.2"):
                anomalies.append({
                    "date": str(fuel_logs[i + 1].date),
                    "consumption": float(consumption),
                    "expected": float(avg_consumption),
                    "deviation_percent": float((consumption - avg_consumption) / avg_consumption * 100),
                })

        # Year-to-Date Statistiken
        current_year = date.today().year
        ytd_cost = Decimal("0")
        ytd_km = 0
        ytd_fills = 0

        for log in fuel_logs:
            if log.date.year == current_year:
                ytd_cost += Decimal(str(log.total_cost or 0))
                ytd_fills += 1

        # YTD km (von erstem bis letztem Log des Jahres)
        ytd_logs = [l for l in fuel_logs if l.date.year == current_year and l.mileage]
        if len(ytd_logs) >= 2:
            ytd_km = ytd_logs[-1].mileage - ytd_logs[0].mileage

        return FuelAnalysis(
            vehicle_id=vehicle_id,
            average_consumption=avg_consumption.quantize(Decimal("0.1")),
            average_cost_per_100km=avg_cost_per_100km.quantize(Decimal("0.01")),
            average_cost_per_fill=avg_cost.quantize(Decimal("0.01")),
            consumption_trend=trend,
            trend_percent=trend_percent,
            anomalies=anomalies[:5],  # Max 5 Anomalien
            total_fuel_cost_ytd=ytd_cost,
            total_km_ytd=ytd_km,
            fill_count_ytd=ytd_fills,
        )

    # =========================================================================
    # Service-Prognose
    # =========================================================================

    async def predict_service(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
    ) -> Optional[ServicePrediction]:
        """
        Sagt den naechsten Service voraus.

        Basiert auf:
        - Aktuellem Kilometerstand
        - Service-Intervall nach Kraftstoff-Typ
        - TUeV-Datum
        """
        from app.db.models import PrivatVehicle

        VEHICLE_INTEL_CALCULATIONS.labels(calculation_type="service_prediction").inc()

        result = await db.execute(
            select(PrivatVehicle).where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            return None

        prediction = ServicePrediction(
            vehicle_id=vehicle_id,
            next_service_km=0,
        )

        # Service-Intervall
        fuel_type = (vehicle.fuel_type or "benzin").lower()
        interval = SERVICE_INTERVALS.get(fuel_type, SERVICE_INTERVALS["default"])

        # Naechster Service-km
        if vehicle.current_mileage:
            # Berechne naechstes Intervall
            current_interval = (vehicle.current_mileage // interval) + 1
            prediction.next_service_km = current_interval * interval
            prediction.km_until_service = prediction.next_service_km - vehicle.current_mileage

            # Geschaetzte Tage bis Service (basierend auf Fahrleistung)
            if vehicle.mileage_date and vehicle.purchase_date:
                days_since_mileage = (date.today() - vehicle.mileage_date).days
                if days_since_mileage > 0:
                    # Schaetze taegliche km
                    # Hier koennte man historische Daten nutzen
                    daily_km = 50  # Durchschnitt
                    days_until = prediction.km_until_service // daily_km
                    prediction.next_service_date = date.today() + timedelta(days=days_until)
                    prediction.days_until_service = days_until

        # TUeV
        if vehicle.tuev_due:
            prediction.tuev_due = vehicle.tuev_due
            days_until_tuev = (vehicle.tuev_due - date.today()).days
            prediction.days_until_tuev = days_until_tuev

        # Geschaetzte Kosten
        age_years = 0
        if vehicle.purchase_date:
            age_years = (date.today() - vehicle.purchase_date).days / 365.25

        if age_years < 3:
            prediction.estimated_service_cost = Decimal("250")
        elif age_years < 6:
            prediction.estimated_service_cost = Decimal("400")
        else:
            prediction.estimated_service_cost = Decimal("600")

        # Empfehlungen
        if prediction.days_until_service is not None and prediction.days_until_service < 30:
            prediction.recommendations.append(
                f"Service in {prediction.days_until_service} Tagen faellig - Termin vereinbaren"
            )

        if prediction.days_until_tuev is not None:
            if prediction.days_until_tuev < 0:
                prediction.recommendations.append(
                    f"TUeV ueberfaellig seit {abs(prediction.days_until_tuev)} Tagen - DRINGEND!"
                )
            elif prediction.days_until_tuev < 30:
                prediction.recommendations.append(
                    f"TUeV in {prediction.days_until_tuev} Tagen - Termin vereinbaren"
                )

        return prediction

    # =========================================================================
    # Vollstaendige Analytics
    # =========================================================================

    async def get_full_analytics(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
        persist: bool = True,
    ) -> VehicleAnalytics:
        """
        Berechnet alle Analytics fuer ein Fahrzeug.
        """
        from app.db.models import PrivatVehicle

        VEHICLE_INTEL_CALCULATIONS.labels(calculation_type="full_analytics").inc()

        with VEHICLE_INTEL_DURATION.time():
            analytics = VehicleAnalytics(vehicle_id=vehicle_id)

            # 1. Depreciation
            analytics.depreciation = await self.calculate_depreciation(db, vehicle_id)

            # 2. TCO
            analytics.tco = await self.calculate_tco(db, vehicle_id)

            # 3. Fuel Analysis
            analytics.fuel_analysis = await self.analyze_fuel_consumption(db, vehicle_id)

            # 4. Service Prediction
            analytics.service_prediction = await self.predict_service(db, vehicle_id)

            # 5. Empfehlungen sammeln
            if analytics.service_prediction:
                analytics.recommendations.extend(analytics.service_prediction.recommendations)

            if analytics.fuel_analysis and analytics.fuel_analysis.consumption_trend == "worsening":
                analytics.recommendations.append(
                    f"Kraftstoffverbrauch steigt (+{analytics.fuel_analysis.trend_percent}%) - "
                    "Wartung oder Fahrverhalten pruefen"
                )

            if analytics.fuel_analysis and analytics.fuel_analysis.anomalies:
                analytics.recommendations.append(
                    f"{len(analytics.fuel_analysis.anomalies)} Verbrauchs-Anomalien erkannt - "
                    "Moegliche Probleme pruefen"
                )

            # 6. Optimaler Verkaufszeitpunkt
            analytics.optimal_sell_date, analytics.optimal_sell_reason = self._calculate_optimal_sell(
                analytics.depreciation, analytics.tco
            )

            # 7. Health Score
            analytics.health_score = self._calculate_health_score(analytics)

            # Persistieren
            if persist:
                await self._persist_analytics(db, vehicle_id, analytics)

            return analytics

    def _calculate_optimal_sell(
        self,
        depreciation: Optional[VehicleDepreciation],
        tco: Optional[VehicleTCO],
    ) -> Tuple[Optional[date], str]:
        """Berechnet den optimalen Verkaufszeitpunkt."""
        if not depreciation or not tco:
            return None, ""

        age_years = float(depreciation.age_years)

        # Regel: Verkaufen wenn monatliche Kosten > monatlicher Wertverlust + Grenzwert
        if tco.cost_per_month > depreciation.monthly_depreciation + Decimal("200"):
            return date.today() + timedelta(days=90), "Betriebskosten uebersteigen Wertverlust"

        # Regel: Premium-Fahrzeuge nach 3-4 Jahren, Volume nach 5-6 Jahren
        if depreciation.vehicle_class == "premium" and age_years > 4:
            return date.today() + timedelta(days=180), "Premium-Fahrzeug nach 4 Jahren - hoehere Wartungskosten erwartet"

        if depreciation.vehicle_class == "volume" and age_years > 6:
            return date.today() + timedelta(days=365), "Fahrzeug ueber 6 Jahre - erhoehtes Reparaturrisiko"

        return None, ""

    def _calculate_health_score(self, analytics: VehicleAnalytics) -> Decimal:
        """Berechnet den Gesundheits-Score (0-100)."""
        score = Decimal("70")  # Basis

        # Wertverlust (-20 bis +10)
        if analytics.depreciation:
            if analytics.depreciation.depreciation_percent < Decimal("20"):
                score += Decimal("10")
            elif analytics.depreciation.depreciation_percent > Decimal("60"):
                score -= Decimal("20")

        # Kosten pro km (-15 bis +15)
        if analytics.tco and analytics.tco.cost_per_km:
            if analytics.tco.cost_per_km < Decimal("0.30"):
                score += Decimal("15")
            elif analytics.tco.cost_per_km > Decimal("0.50"):
                score -= Decimal("15")

        # Verbrauchs-Trend (-10 bis +10)
        if analytics.fuel_analysis:
            if analytics.fuel_analysis.consumption_trend == "improving":
                score += Decimal("10")
            elif analytics.fuel_analysis.consumption_trend == "worsening":
                score -= Decimal("10")

        # TUeV-Status (-20 bis 0)
        if analytics.service_prediction and analytics.service_prediction.days_until_tuev is not None:
            if analytics.service_prediction.days_until_tuev < 0:
                score -= Decimal("20")
            elif analytics.service_prediction.days_until_tuev < 30:
                score -= Decimal("5")

        return max(Decimal("0"), min(Decimal("100"), score)).quantize(Decimal("0.01"))

    async def _persist_analytics(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
        analytics: VehicleAnalytics,
    ) -> None:
        """Speichert Analytics in der Datenbank."""
        from app.db.models import PrivatVehicle

        result = await db.execute(
            select(PrivatVehicle).where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            return

        # Depreciation
        if analytics.depreciation:
            vehicle.current_estimated_value = analytics.depreciation.current_estimated_value
            vehicle.depreciation_monthly = analytics.depreciation.monthly_depreciation

        # TCO
        if analytics.tco:
            vehicle.tco_total = analytics.tco.total_annual_costs
            vehicle.tco_per_km = analytics.tco.cost_per_km

        # Fuel
        if analytics.fuel_analysis:
            vehicle.average_fuel_consumption = analytics.fuel_analysis.average_consumption

        # Service
        if analytics.service_prediction:
            vehicle.next_service_date = analytics.service_prediction.next_service_date
            vehicle.next_service_km = analytics.service_prediction.next_service_km

        # Timestamp
        vehicle.last_kpi_calculation = datetime.now(timezone.utc)

        await db.flush()

        logger.info(
            "vehicle_analytics_persisted",
            vehicle_id=str(vehicle_id),
            health_score=float(analytics.health_score),
        )

    # =========================================================================
    # Batch-Operationen
    # =========================================================================

    async def recalculate_all_vehicles(
        self,
        db: AsyncSession,
        space_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Berechnet Analytics fuer alle Fahrzeuge."""
        from app.db.models import PrivatVehicle

        VEHICLE_INTEL_CALCULATIONS.labels(calculation_type="batch_all").inc()

        query = select(PrivatVehicle).where(PrivatVehicle.deleted_at.is_(None))
        if space_id:
            query = query.where(PrivatVehicle.space_id == space_id)

        result = await db.execute(query)
        vehicles = result.scalars().all()

        stats = {
            "total": len(vehicles),
            "calculated": 0,
            "skipped": 0,
            "errors": [],
        }

        for vehicle in vehicles:
            try:
                await self.get_full_analytics(db, vehicle.id, persist=True)
                stats["calculated"] += 1
            except Exception as e:
                stats["skipped"] += 1
                stats["errors"].append(f"{vehicle.id}: {str(e)}")
                logger.warning(
                    "vehicle_analytics_failed",
                    vehicle_id=str(vehicle.id),
                    error=str(e),
                )

        await db.commit()

        logger.info(
            "batch_vehicle_analytics_completed",
            total=stats["total"],
            calculated=stats["calculated"],
            skipped=stats["skipped"],
        )

        return stats


# =============================================================================
# Singleton
# =============================================================================

_vehicle_intelligence_service: Optional[VehicleIntelligenceService] = None
_service_lock = threading.Lock()


def get_vehicle_intelligence_service() -> VehicleIntelligenceService:
    """Factory fuer VehicleIntelligenceService Singleton (Thread-safe)."""
    global _vehicle_intelligence_service
    if _vehicle_intelligence_service is None:
        with _service_lock:
            if _vehicle_intelligence_service is None:
                _vehicle_intelligence_service = VehicleIntelligenceService()
    return _vehicle_intelligence_service

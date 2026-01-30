"""Insurance KPI Service fuer Versicherungs-Berechnungen.

Berechnet alle Versicherungs-bezogenen KPIs:
- Deckungsluecken-Analyse
- Kuendigungsfristen
- Praemienentwicklung
- Risikobewertung

Enterprise Features:
- Multi-Tenant Security via space_id
- Echte DB-Integration mit SQLAlchemy
- KPI-Persistenz in DB
- Structured Logging
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PrivatInsurance
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# Type alias fuer Premium History (falls kein separates Model existiert)
# In Zukunft sollte ein dediziertes InsurancePremiumHistory Model erstellt werden
PremiumHistoryEntry = PrivatInsurance  # Workaround: Wir nutzen aeltere Versicherungsdaten


@dataclass
class InsuranceGapResult:
    """Ergebnis der Deckungsluecken-Analyse."""

    insurance_type: str
    current_coverage: Decimal
    recommended_coverage: Decimal
    gap_amount: Decimal
    gap_severity: str  # "none", "low", "medium", "high", "critical"
    estimated_additional_premium: Decimal
    risk_exposure: str


@dataclass
class CancellationInfo:
    """Informationen zur Kuendigungsfrist."""

    insurance_id: UUID
    cancellation_deadline: date
    days_remaining: int
    is_urgent: bool  # < 30 Tage
    auto_renewal_date: Optional[date]


@dataclass
class PremiumTrend:
    """Praemienentwicklung ueber Zeit."""

    insurance_type: str
    current_premium: Decimal
    previous_premium: Decimal
    change_amount: Decimal
    change_percent: Decimal
    trend_direction: str  # "rising", "falling", "stable"


class InsuranceKPIService:
    """Service fuer Versicherungs-KPI-Berechnungen.

    Analysiert Versicherungen auf:
    - Deckungsluecken nach Empfehlungen
    - Kuendigungsfristen
    - Praemienentwicklung
    - Risiko-Exposure
    """

    # Empfohlene Deckungssummen nach Versicherungstyp
    COVERAGE_RECOMMENDATIONS = {
        "haftpflicht_privat": Decimal("10000000"),  # 10 Mio Euro
        "haftpflicht_kfz": Decimal("100000000"),    # 100 Mio Euro (gesetzlich)
        "hausrat": None,  # Wird basierend auf Wohnflaeche berechnet
        "rechtsschutz": Decimal("500000"),
        "berufsunfaehigkeit": None,  # Basierend auf Einkommen
        "risikoleben": None,  # Basierend auf Verbindlichkeiten
        "wohngebaeude": None,  # Basierend auf Wert
    }

    # Empfohlene Deckung pro m2 fuer Hausrat
    HAUSRAT_PER_SQM = Decimal("650")  # 650 Euro pro m2

    # BU-Empfehlung: X% des Bruttoeinkommens
    BU_INCOME_PERCENT = Decimal("0.80")

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def calculate_coverage_gaps(
        self,
        insurance_id: UUID,
        space_id: UUID,
        persist: bool = True
    ) -> InsuranceGapResult:
        """Berechnet Deckungsluecken fuer eine Versicherung.

        Args:
            insurance_id: UUID der Versicherung
            space_id: UUID des Space (Multi-Tenant Security!)
            persist: Ob KPIs in DB persistiert werden sollen

        Returns:
            InsuranceGapResult mit Gap-Analyse

        Raises:
            ValueError: Wenn Versicherung nicht gefunden oder Zugriff verweigert
        """
        logger.info(
            "insurance_coverage_gap_calculation_started",
            insurance_id=str(insurance_id),
            space_id=str(space_id),
        )

        insurance = await self._get_insurance(insurance_id, space_id)

        recommended = self._get_recommended_coverage(insurance)
        current = insurance.coverage_amount or Decimal("0")
        gap = recommended - current

        result = InsuranceGapResult(
            insurance_type=insurance.insurance_type,
            current_coverage=current,
            recommended_coverage=recommended,
            gap_amount=max(gap, Decimal("0")),
            gap_severity=self._calc_severity(gap, recommended),
            estimated_additional_premium=self._estimate_premium_increase(insurance, gap),
            risk_exposure=self._calc_risk_exposure(insurance.insurance_type, gap),
        )

        if persist:
            await self._persist_coverage_gap(insurance, result)

        logger.info(
            "insurance_coverage_gap_calculation_completed",
            insurance_id=str(insurance_id),
            gap_severity=result.gap_severity,
            gap_amount=str(result.gap_amount),
        )

        return result

    async def calculate_cancellation_deadline(
        self,
        insurance_id: UUID,
        space_id: UUID,
        persist: bool = True
    ) -> CancellationInfo:
        """Berechnet die naechste Kuendigungsfrist.

        Args:
            insurance_id: UUID der Versicherung
            space_id: UUID des Space (Multi-Tenant Security!)
            persist: Ob KPIs in DB persistiert werden sollen

        Returns:
            CancellationInfo mit Fristen

        Raises:
            ValueError: Wenn Versicherung nicht gefunden oder Zugriff verweigert
        """
        logger.info(
            "insurance_cancellation_calculation_started",
            insurance_id=str(insurance_id),
            space_id=str(space_id),
        )

        insurance = await self._get_insurance(insurance_id, space_id)

        # Standard: 3 Monate vor Ablauf (cancellation_period_months im Model)
        notice_period_months = insurance.cancellation_period_months or 3

        # Naechstes Ablaufdatum finden
        if insurance.end_date:
            next_end = insurance.end_date
        elif insurance.start_date:
            # Jaehrliche Verlaengerung ab Startdatum
            next_end = self._calc_next_anniversary(insurance.start_date)
        else:
            # Fallback: 1 Jahr ab heute
            next_end = date.today() + timedelta(days=365)

        cancellation_deadline = next_end - timedelta(days=notice_period_months * 30)
        days_remaining = (cancellation_deadline - date.today()).days

        result = CancellationInfo(
            insurance_id=insurance_id,
            cancellation_deadline=cancellation_deadline,
            days_remaining=max(days_remaining, 0),
            is_urgent=0 < days_remaining <= 30,
            auto_renewal_date=next_end if insurance.is_auto_renew else None,
        )

        if persist:
            await self._persist_cancellation_deadline(insurance, result)

        logger.info(
            "insurance_cancellation_calculation_completed",
            insurance_id=str(insurance_id),
            days_remaining=result.days_remaining,
            is_urgent=result.is_urgent,
        )

        return result

    async def calculate_premium_trends(self, space_id: UUID) -> List[PremiumTrend]:
        """Berechnet Praemientrends fuer alle Versicherungen.

        Args:
            space_id: UUID des Privat-Space

        Returns:
            Liste von PremiumTrend pro Versicherungstyp
        """
        insurances = await self._get_all_insurances(space_id)
        premium_history = await self._get_premium_history(space_id)

        trends = []
        for ins_type in set(i.insurance_type for i in insurances):
            trend = self._calc_premium_trend(ins_type, insurances, premium_history)
            if trend:
                trends.append(trend)

        return trends

    def _get_recommended_coverage(self, insurance: PrivatInsurance) -> Decimal:
        """Ermittelt die empfohlene Deckungssumme.

        Args:
            insurance: Versicherungs-Objekt

        Returns:
            Empfohlene Deckungssumme basierend auf Versicherungstyp
        """
        ins_type = insurance.insurance_type

        if ins_type in self.COVERAGE_RECOMMENDATIONS:
            fixed = self.COVERAGE_RECOMMENDATIONS[ins_type]
            if fixed is not None:
                return fixed

        # Dynamische Berechnung aus coverage_details JSON falls vorhanden
        details = insurance.coverage_details or {}

        if ins_type == "hausrat":
            living_space = Decimal(str(details.get("living_space_sqm", 100)))
            return living_space * self.HAUSRAT_PER_SQM

        if ins_type == "berufsunfaehigkeit":
            annual_income = Decimal(str(details.get("annual_income", 50000)))
            monthly_need = (annual_income * self.BU_INCOME_PERCENT) / 12
            return monthly_need.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        if ins_type == "risikoleben":
            # Empfehlung: Summe aller Verbindlichkeiten + 3 Jahresgehaelter
            debts = Decimal(str(details.get("total_debts", 0)))
            annual_income = Decimal(str(details.get("annual_income", 50000)))
            return debts + (annual_income * 3)

        if ins_type == "wohngebaeude":
            property_value = Decimal(str(details.get("property_value", 300000)))
            return property_value

        # Fallback
        return insurance.coverage_amount or Decimal("100000")

    def _calc_severity(self, gap: Decimal, recommended: Decimal) -> str:
        """Berechnet den Schweregrad der Deckungsluecke."""
        if gap <= 0:
            return "none"

        if recommended <= 0:
            return "unknown"

        gap_percent = (gap / recommended) * 100

        if gap_percent < 10:
            return "low"
        elif gap_percent < 25:
            return "medium"
        elif gap_percent < 50:
            return "high"
        else:
            return "critical"

    def _estimate_premium_increase(self, insurance: PrivatInsurance, gap: Decimal) -> Decimal:
        """Schaetzt die zusaetzliche Praemie fuer Gap-Schliessung.

        Args:
            insurance: Versicherungs-Objekt
            gap: Deckungsluecke in EUR

        Returns:
            Geschaetzte zusaetzliche Jahrespraemie
        """
        if gap <= 0:
            return Decimal("0")

        # Berechne jaehrliche Praemie aus premium_amount und premium_frequency
        annual_premium = self._calc_annual_premium(insurance)
        current_coverage = insurance.coverage_amount or Decimal("100000")

        if current_coverage <= 0:
            return Decimal("0")

        # Lineare Schaetzung (vereinfacht)
        premium_per_coverage = annual_premium / current_coverage
        additional = gap * premium_per_coverage

        return additional.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_annual_premium(self, insurance: PrivatInsurance) -> Decimal:
        """Berechnet die jaehrliche Praemie aus Betrag und Frequenz.

        Args:
            insurance: Versicherungs-Objekt

        Returns:
            Jaehrliche Gesamtpraemie
        """
        premium = insurance.premium_amount or Decimal("0")
        frequency = insurance.premium_frequency or "yearly"

        frequency_multipliers = {
            "monthly": 12,
            "quarterly": 4,
            "semi_annual": 2,
            "yearly": 1,
        }

        multiplier = frequency_multipliers.get(frequency, 1)
        return premium * multiplier

    def _calc_risk_exposure(self, insurance_type: str, gap: Decimal) -> str:
        """Bewertet das Risiko-Exposure bei Deckungsluecke."""
        if gap <= 0:
            return "Vollstaendig abgedeckt"

        risk_descriptions = {
            "haftpflicht_privat": f"Bei Schaeden ueber der Deckungssumme haften Sie persoenlich mit {gap:,.0f} EUR",
            "hausrat": f"Hausrat im Wert von {gap:,.0f} EUR ist nicht versichert",
            "berufsunfaehigkeit": f"Monatliche Versorgungsluecke von {gap:,.0f} EUR bei Berufsunfaehigkeit",
            "risikoleben": f"Hinterbliebene waeren mit {gap:,.0f} EUR unterversorgt",
            "wohngebaeude": f"Gebaeudeteil im Wert von {gap:,.0f} EUR ist nicht versichert",
        }

        return risk_descriptions.get(
            insurance_type,
            f"Deckungsluecke von {gap:,.0f} EUR"
        )

    def _calc_next_anniversary(self, start_date: date) -> date:
        """Berechnet das naechste Vertragsjubilaeum."""
        today = date.today()
        anniversary = start_date.replace(year=today.year)

        if anniversary <= today:
            anniversary = anniversary.replace(year=today.year + 1)

        return anniversary

    def _calc_premium_trend(
        self,
        insurance_type: str,
        insurances: list[PrivatInsurance],
        history: list[PrivatInsurance]
    ) -> Optional[PremiumTrend]:
        """Berechnet den Praemientrend fuer einen Versicherungstyp.

        Args:
            insurance_type: Versicherungstyp
            insurances: Aktuelle Versicherungen
            history: Historische Versicherungsdaten (z.B. Vorjahr)

        Returns:
            PremiumTrend oder None falls keine Daten
        """
        type_insurances = [i for i in insurances if i.insurance_type == insurance_type]
        if not type_insurances:
            return None

        current_premium = sum(
            self._calc_annual_premium(i) for i in type_insurances
        )

        # Vorjahrespraemie aus Historie
        previous_premium = Decimal("0")
        type_history = [h for h in history if h.insurance_type == insurance_type]
        if type_history:
            previous_premium = sum(
                self._calc_annual_premium(h) for h in type_history
            )
        else:
            previous_premium = current_premium  # Kein Vergleich moeglich

        change = current_premium - previous_premium
        change_percent = Decimal("0")
        if previous_premium > 0:
            change_percent = (change / previous_premium) * 100

        if change > 0:
            trend = "rising"
        elif change < 0:
            trend = "falling"
        else:
            trend = "stable"

        return PremiumTrend(
            insurance_type=insurance_type,
            current_premium=current_premium,
            previous_premium=previous_premium,
            change_amount=change,
            change_percent=change_percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            trend_direction=trend,
        )

    # =========================================================================
    # Persistence Methods
    # =========================================================================

    async def _persist_coverage_gap(
        self,
        insurance: PrivatInsurance,
        result: InsuranceGapResult
    ) -> None:
        """Persistiert Deckungsluecken-Analyse in der Datenbank."""
        insurance.coverage_gap_analysis = {
            "gap_amount": str(result.gap_amount),
            "gap_severity": result.gap_severity,
            "recommended_coverage": str(result.recommended_coverage),
            "current_coverage": str(result.current_coverage),
            "risk_exposure": result.risk_exposure,
            "estimated_additional_premium": str(result.estimated_additional_premium),
        }
        insurance.coverage_adequacy_score = self._calc_adequacy_score(result)
        insurance.annual_premium_total = self._calc_annual_premium(insurance)
        insurance.last_kpi_calculation = datetime.now(timezone.utc)

        await self.db.commit()

        logger.debug(
            "insurance_coverage_gap_persisted",
            insurance_id=str(insurance.id),
            gap_severity=result.gap_severity,
        )

    async def _persist_cancellation_deadline(
        self,
        insurance: PrivatInsurance,
        result: CancellationInfo
    ) -> None:
        """Persistiert Kuendigungsfrist in der Datenbank."""
        insurance.cancellation_deadline = result.cancellation_deadline
        insurance.last_kpi_calculation = datetime.now(timezone.utc)

        await self.db.commit()

        logger.debug(
            "insurance_cancellation_deadline_persisted",
            insurance_id=str(insurance.id),
            deadline=str(result.cancellation_deadline),
        )

    def _calc_adequacy_score(self, result: InsuranceGapResult) -> Decimal:
        """Berechnet Deckungsadaequanz-Score (0-100)."""
        if result.recommended_coverage <= 0:
            return Decimal("100")

        coverage_ratio = result.current_coverage / result.recommended_coverage
        score = min(coverage_ratio * 100, Decimal("100"))
        return score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # =========================================================================
    # Database Access Methods (Multi-Tenant Security!)
    # =========================================================================

    async def _get_insurance(self, insurance_id: UUID, space_id: UUID) -> PrivatInsurance:
        """Laedt Versicherung aus der Datenbank mit Multi-Tenant Security.

        Args:
            insurance_id: UUID der Versicherung
            space_id: UUID des Space (Multi-Tenant Security!)

        Returns:
            PrivatInsurance Objekt

        Raises:
            ValueError: Wenn Versicherung nicht gefunden oder Zugriff verweigert
        """
        stmt = (
            select(PrivatInsurance)
            .where(
                PrivatInsurance.id == insurance_id,
                PrivatInsurance.space_id == space_id,  # Multi-Tenant Security!
                PrivatInsurance.deleted_at.is_(None),
            )
        )

        result = await self.db.execute(stmt)
        insurance = result.scalar_one_or_none()

        if not insurance:
            logger.warning(
                "insurance_not_found_or_access_denied",
                insurance_id=str(insurance_id),
                space_id=str(space_id),
            )
            raise ValueError(
                f"Versicherung {insurance_id} nicht gefunden oder Zugriff verweigert"
            )

        return insurance

    async def _get_all_insurances(self, space_id: UUID) -> list[PrivatInsurance]:
        """Laedt alle aktiven Versicherungen eines Space.

        Args:
            space_id: UUID des Space (Multi-Tenant Security!)

        Returns:
            Liste von PrivatInsurance Objekten
        """
        stmt = (
            select(PrivatInsurance)
            .where(
                PrivatInsurance.space_id == space_id,  # Multi-Tenant Security!
                PrivatInsurance.deleted_at.is_(None),
                PrivatInsurance.is_active.is_(True),
            )
            .order_by(PrivatInsurance.insurance_type)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_premium_history(self, space_id: UUID) -> list[PrivatInsurance]:
        """Laedt Praemienhistorie (aeltere Versicherungsdaten).

        Da wir kein dediziertes PremiumHistory Model haben, nutzen wir
        inaktive/geloeschte Versicherungen als historische Referenz.

        Args:
            space_id: UUID des Space (Multi-Tenant Security!)

        Returns:
            Liste von historischen PrivatInsurance Objekten
        """
        # Fuer echte Premium-Historie sollte ein dediziertes Model erstellt werden
        # Vorerst: Leere Liste zurueckgeben (kein historischer Vergleich)
        logger.debug(
            "premium_history_not_available",
            space_id=str(space_id),
            note="Dediziertes PremiumHistory Model erforderlich fuer echte Historie",
        )
        return []

    # =========================================================================
    # Batch Processing Methods (fuer Celery Tasks)
    # =========================================================================

    async def calculate_all_insurance_kpis_for_space(
        self,
        space_id: UUID,
        persist: bool = True
    ) -> dict[UUID, InsuranceGapResult]:
        """Berechnet Deckungsluecken fuer alle Versicherungen eines Space.

        Batch-Methode fuer Celery Tasks.

        Args:
            space_id: UUID des Space
            persist: Ob KPIs persistiert werden sollen

        Returns:
            Dict von insurance_id -> InsuranceGapResult
        """
        logger.info(
            "batch_insurance_kpi_calculation_started",
            space_id=str(space_id),
        )

        insurances = await self._get_all_insurances(space_id)

        results: dict[UUID, InsuranceGapResult] = {}
        success_count = 0
        error_count = 0

        for insurance in insurances:
            try:
                result = await self.calculate_coverage_gaps(
                    insurance_id=insurance.id,
                    space_id=space_id,
                    persist=persist,
                )
                results[insurance.id] = result
                success_count += 1

                # Auch Kuendigungsfrist berechnen
                await self.calculate_cancellation_deadline(
                    insurance_id=insurance.id,
                    space_id=space_id,
                    persist=persist,
                )
            except Exception as e:
                logger.error(
                    "insurance_kpi_calculation_failed",
                    insurance_id=str(insurance.id),
                    **safe_error_log(e),
                )
                error_count += 1

        logger.info(
            "batch_insurance_kpi_calculation_completed",
            space_id=str(space_id),
            total=len(insurances),
            success=success_count,
            errors=error_count,
        )

        return results

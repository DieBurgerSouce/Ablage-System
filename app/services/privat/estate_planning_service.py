# -*- coding: utf-8 -*-
"""
EstatePlanningService - Nachlassplanung für das Privat-Modul.

Bietet Funktionen für:
1. Vermoegensübertragungsplanung
2. Erbschaftsteuer-Szenarien (deutsches Erbschaftsteuerrecht)
3. Vollmacht-Verwaltung (Vorsorge-, General-, Bankvollmacht)
4. Zeitgesteuerten Dokumentenzugriff für Erben
5. Nachlass-Zusammenfassungen

Basierend auf deutschem Erbschaftsteuer- und Schenkungsteuergesetz (ErbStG).

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
SECURITY: NIEMALS persoenliche Daten oder Vermoegenshöhen loggen!
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple, Set
from uuid import UUID
from enum import Enum

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

ESTATE_PLANNING_CALCULATIONS = Counter(
    "estate_planning_calculations_total",
    "Anzahl der Nachlassplanungs-Berechnungen",
    ["calculation_type"]
)

ESTATE_PLANNING_DURATION = Histogram(
    "estate_planning_duration_seconds",
    "Dauer der Nachlassplanungs-Berechnung",
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)


# =============================================================================
# Deutsches Erbschaftsteuerrecht - Konstanten
# =============================================================================

class RelationshipType(str, Enum):
    """Verwandtschaftsverhältnis zum Erblasser/Schenker."""
    EHEPARTNER = "ehepartner"
    LEBENSPARTNER = "lebenspartner"  # Eingetragene Lebenspartnerschaft
    KIND = "kind"
    STIEFKIND = "stiefkind"
    ENKELKIND = "enkelkind"  # wenn Eltern verstorben
    ENKELKIND_ELTERN_LEBEN = "enkelkind_eltern_leben"
    ELTERNTEIL = "elternteil"  # Nur bei Erbschaft
    GESCHWISTER = "geschwister"
    NEFFE_NICHTE = "neffe_nichte"
    SONSTIGE_VERWANDTE = "sonstige_verwandte"
    NICHT_VERWANDT = "nicht_verwandt"


class TaxClass(str, Enum):
    """Erbschaftsteuer-Klasse nach ErbStG."""
    KLASSE_I = "klasse_i"
    KLASSE_II = "klasse_ii"
    KLASSE_III = "klasse_iii"


class PowerOfAttorneyType(str, Enum):
    """Typen von Vollmachten."""
    VORSORGEVOLLMACHT = "vorsorgevollmacht"
    GENERALVOLLMACHT = "generalvollmacht"
    BANKVOLLMACHT = "bankvollmacht"
    PATIENTENVERFUEGUNG = "patientenverfügung"
    BETREUUNGSVERFUEGUNG = "betreuungsverfügung"
    SORGERECHTSVERFUEGUNG = "sorgerechtsverfügung"


class DocumentAccessTrigger(str, Enum):
    """Ausloeser für Dokumentenzugriff."""
    DEATH = "death"  # Nach Tod
    INCAPACITY = "incapacity"  # Bei Geschäftsunfähigkeit
    DATE = "date"  # Ab bestimmtem Datum
    AGE = "age"  # Ab bestimmtem Alter des Erben
    MANUAL = "manual"  # Manuell durch Vollmachtgeber


# =============================================================================
# Freibetraege nach ErbStG (Stand 2026)
# =============================================================================

# Persoenliche Freibetraege (alle 10 Jahre erneuerbar)
FREIBETRAG_EHEPARTNER = Decimal("500000")
FREIBETRAG_KIND = Decimal("400000")
FREIBETRAG_ENKELKIND = Decimal("200000")  # Eltern verstorben
FREIBETRAG_ENKELKIND_ELTERN = Decimal("100000")  # Eltern leben
FREIBETRAG_ELTERN_ERBSCHAFT = Decimal("100000")
FREIBETRAG_SONSTIGE_STEUERKLASSE_II = Decimal("20000")
FREIBETRAG_STEUERKLASSE_III = Decimal("20000")

# Versorgungsfreibetrag (nur bei Tod, nicht Schenkung)
VERSORGUNGSFREIBETRAG_EHEPARTNER = Decimal("256000")
VERSORGUNGSFREIBETRAG_KIND_0_5 = Decimal("52000")
VERSORGUNGSFREIBETRAG_KIND_5_10 = Decimal("41000")
VERSORGUNGSFREIBETRAG_KIND_10_15 = Decimal("30700")
VERSORGUNGSFREIBETRAG_KIND_15_20 = Decimal("20500")
VERSORGUNGSFREIBETRAG_KIND_20_27 = Decimal("10300")

# Hausrat-Freibetrag
HAUSRAT_FREIBETRAG_KLASSE_I = Decimal("41000")
SONSTIGE_BEWEGLICHE_SACHEN_KLASSE_I = Decimal("12000")

# Steuersätze nach Steuerklasse und Wert (Tabelle 19 ErbStG)
# Format: {(von, bis): {klasse: satz}}
ERBSCHAFTSTEUER_SAETZE = {
    (Decimal("0"), Decimal("75000")): {
        TaxClass.KLASSE_I: Decimal("0.07"),
        TaxClass.KLASSE_II: Decimal("0.15"),
        TaxClass.KLASSE_III: Decimal("0.30"),
    },
    (Decimal("75000"), Decimal("300000")): {
        TaxClass.KLASSE_I: Decimal("0.11"),
        TaxClass.KLASSE_II: Decimal("0.20"),
        TaxClass.KLASSE_III: Decimal("0.30"),
    },
    (Decimal("300000"), Decimal("600000")): {
        TaxClass.KLASSE_I: Decimal("0.15"),
        TaxClass.KLASSE_II: Decimal("0.25"),
        TaxClass.KLASSE_III: Decimal("0.30"),
    },
    (Decimal("600000"), Decimal("6000000")): {
        TaxClass.KLASSE_I: Decimal("0.19"),
        TaxClass.KLASSE_II: Decimal("0.30"),
        TaxClass.KLASSE_III: Decimal("0.30"),
    },
    (Decimal("6000000"), Decimal("13000000")): {
        TaxClass.KLASSE_I: Decimal("0.23"),
        TaxClass.KLASSE_II: Decimal("0.35"),
        TaxClass.KLASSE_III: Decimal("0.50"),
    },
    (Decimal("13000000"), Decimal("26000000")): {
        TaxClass.KLASSE_I: Decimal("0.27"),
        TaxClass.KLASSE_II: Decimal("0.40"),
        TaxClass.KLASSE_III: Decimal("0.50"),
    },
    (Decimal("26000000"), Decimal("999999999999")): {
        TaxClass.KLASSE_I: Decimal("0.30"),
        TaxClass.KLASSE_II: Decimal("0.43"),
        TaxClass.KLASSE_III: Decimal("0.50"),
    },
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Heir:
    """Repraesentation eines Erben/Beschenkten."""
    name: str
    relationship: RelationshipType
    birth_date: Optional[date] = None
    share_percent: Decimal = Decimal("0")  # Erbanteil in Prozent
    specific_bequest: Optional[Decimal] = None  # Vermaechtnis (absoluter Betrag)
    tax_class: Optional[TaxClass] = None
    personal_allowance: Decimal = Decimal("0")
    care_allowance: Decimal = Decimal("0")  # Versorgungsfreibetrag
    notes: Optional[str] = None


@dataclass
class PowerOfAttorney:
    """Vollmacht-Dokument."""
    id: Optional[UUID]
    poa_type: PowerOfAttorneyType
    title: str
    granted_to: str  # Name des Bevollmaechtigten
    granted_date: Optional[date] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    document_id: Optional[UUID] = None  # Verknüpftes Dokument
    is_active: bool = True
    scope: Optional[str] = None  # Umfang der Vollmacht
    notarized: bool = False
    last_reviewed: Optional[date] = None


@dataclass
class InheritanceTaxScenario:
    """Erbschaftsteuer-Szenario für einen Erben."""
    heir: Heir
    gross_inheritance: Decimal
    taxable_inheritance: Decimal
    personal_allowance: Decimal
    care_allowance: Decimal
    household_allowance: Decimal
    other_deductions: Decimal
    tax_base: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    effective_tax_rate: Decimal


@dataclass
class GiftPlanningScenario:
    """Schenkungsplanung zur Steueroptimierung."""
    recipient: Heir
    annual_gift: Decimal  # Jährliche Schenkung
    years: int
    total_gift: Decimal
    tax_free_amount: Decimal
    taxable_amount: Decimal
    estimated_tax: Decimal
    strategy_description: str
    next_renewal_date: date  # Nächste Freibetrag-Erneuerung


@dataclass
class HeirDocumentAccess:
    """Zeitgesteuerter Dokumentenzugriff für Erben."""
    heir_name: str
    heir_email: Optional[str]
    documents: List[UUID]
    folders: List[UUID]
    trigger: DocumentAccessTrigger
    trigger_date: Optional[date] = None  # Für DATE/AGE Trigger
    trigger_age: Optional[int] = None  # Für AGE Trigger
    is_active: bool = True
    access_granted: bool = False
    access_granted_at: Optional[datetime] = None
    notes: Optional[str] = None


@dataclass
class EstateSummary:
    """Zusammenfassung des Nachlasses."""
    space_id: UUID
    total_assets: Decimal
    total_liabilities: Decimal
    net_estate: Decimal

    # Aufschluesselung
    real_estate_value: Decimal
    investment_value: Decimal
    vehicle_value: Decimal
    other_assets: Decimal
    mortgage_debt: Decimal
    other_debt: Decimal

    # Erben
    heirs: List[Heir]
    total_shares: Decimal  # Sollte 100% sein

    # Steuer-Szenarien
    tax_scenarios: List[InheritanceTaxScenario]
    total_estimated_tax: Decimal

    # Vollmachten
    active_powers_of_attorney: List[PowerOfAttorney]
    missing_essential_poas: List[str]

    # Dokumentenzugriff
    heir_document_access: List[HeirDocumentAccess]

    # Empfehlungen
    recommendations: List[str]
    warnings: List[str]

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TenYearGiftPlan:
    """10-Jahres-Schenkungsplan zur Freibetrag-Optimierung."""
    recipient: Heir
    allowance_per_10_years: Decimal
    current_gifts_in_period: Decimal
    remaining_allowance: Decimal
    period_start: date
    period_end: date
    recommended_gifts: List[GiftPlanningScenario]
    total_tax_savings: Decimal


# =============================================================================
# Singleton Service
# =============================================================================

class EstatePlanningService:
    """
    Singleton Service für Nachlassplanung.

    Berechnet Erbschaftsteuer-Szenarien, verwaltet Vollmachten
    und plant Vermoegensübertragungen.

    SECURITY: NIEMALS persoenliche Daten oder Betraege loggen!
    """

    _instance: Optional["EstatePlanningService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "EstatePlanningService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        logger.info("estate_planning_service_initialized")

    # =========================================================================
    # Steuerklasse und Freibetraege
    # =========================================================================

    def get_tax_class(self, relationship: RelationshipType) -> TaxClass:
        """Bestimmt die Steuerklasse basierend auf Verwandtschaftsverhältnis."""
        if relationship in (
            RelationshipType.EHEPARTNER,
            RelationshipType.LEBENSPARTNER,
            RelationshipType.KIND,
            RelationshipType.STIEFKIND,
            RelationshipType.ENKELKIND,
            RelationshipType.ENKELKIND_ELTERN_LEBEN,
            RelationshipType.ELTERNTEIL,
        ):
            return TaxClass.KLASSE_I

        if relationship in (
            RelationshipType.GESCHWISTER,
            RelationshipType.NEFFE_NICHTE,
            RelationshipType.SONSTIGE_VERWANDTE,
        ):
            return TaxClass.KLASSE_II

        return TaxClass.KLASSE_III

    def get_personal_allowance(
        self,
        relationship: RelationshipType,
        is_inheritance: bool = True,
    ) -> Decimal:
        """Ermittelt den persoenlichen Freibetrag."""
        if relationship in (RelationshipType.EHEPARTNER, RelationshipType.LEBENSPARTNER):
            return FREIBETRAG_EHEPARTNER

        if relationship in (RelationshipType.KIND, RelationshipType.STIEFKIND):
            return FREIBETRAG_KIND

        if relationship == RelationshipType.ENKELKIND:
            return FREIBETRAG_ENKELKIND  # Eltern verstorben

        if relationship == RelationshipType.ENKELKIND_ELTERN_LEBEN:
            return FREIBETRAG_ENKELKIND_ELTERN

        if relationship == RelationshipType.ELTERNTEIL and is_inheritance:
            return FREIBETRAG_ELTERN_ERBSCHAFT

        if relationship in (
            RelationshipType.GESCHWISTER,
            RelationshipType.NEFFE_NICHTE,
            RelationshipType.SONSTIGE_VERWANDTE,
        ):
            return FREIBETRAG_SONSTIGE_STEUERKLASSE_II

        return FREIBETRAG_STEUERKLASSE_III

    def get_care_allowance(
        self,
        relationship: RelationshipType,
        age_at_death: Optional[int] = None,
        is_inheritance: bool = True,
    ) -> Decimal:
        """
        Ermittelt den Versorgungsfreibetrag.

        Nur bei Erbschaft, nicht bei Schenkung!
        Wird um Kapitalwert von Versorgungsbezuegen gekürzt.
        """
        if not is_inheritance:
            return Decimal("0")

        if relationship in (RelationshipType.EHEPARTNER, RelationshipType.LEBENSPARTNER):
            return VERSORGUNGSFREIBETRAG_EHEPARTNER

        if relationship in (RelationshipType.KIND, RelationshipType.STIEFKIND):
            if age_at_death is None:
                return Decimal("0")

            if age_at_death < 5:
                return VERSORGUNGSFREIBETRAG_KIND_0_5
            elif age_at_death < 10:
                return VERSORGUNGSFREIBETRAG_KIND_5_10
            elif age_at_death < 15:
                return VERSORGUNGSFREIBETRAG_KIND_10_15
            elif age_at_death < 20:
                return VERSORGUNGSFREIBETRAG_KIND_15_20
            elif age_at_death < 27:
                return VERSORGUNGSFREIBETRAG_KIND_20_27

        return Decimal("0")

    # =========================================================================
    # Steuerberechnung
    # =========================================================================

    def calculate_inheritance_tax(
        self,
        taxable_amount: Decimal,
        tax_class: TaxClass,
    ) -> Tuple[Decimal, Decimal]:
        """
        Berechnet die Erbschaftsteuer.

        Args:
            taxable_amount: Steuerpflichtiger Erwerb (nach Abzug aller Freibetraege)
            tax_class: Steuerklasse

        Returns:
            Tuple aus (Steuerbetrag, Steuersatz)
        """
        if taxable_amount <= 0:
            return Decimal("0"), Decimal("0")

        # Passenden Steuersatz finden
        for (von, bis), saetze in ERBSCHAFTSTEUER_SAETZE.items():
            if von < taxable_amount <= bis:
                rate = saetze[tax_class]
                tax = (taxable_amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
                return tax, rate

        # Fallback: Hoechster Satz
        highest_rates = list(ERBSCHAFTSTEUER_SAETZE.values())[-1]
        rate = highest_rates[tax_class]
        tax = (taxable_amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        return tax, rate

    def calculate_heir_scenario(
        self,
        heir: Heir,
        total_estate: Decimal,
        is_inheritance: bool = True,
    ) -> InheritanceTaxScenario:
        """Berechnet das Steuer-Szenario für einen einzelnen Erben."""
        # Anteil am Nachlass berechnen
        if heir.specific_bequest:
            gross_inheritance = heir.specific_bequest
        else:
            gross_inheritance = (total_estate * heir.share_percent / 100).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )

        # Steuerklasse bestimmen
        tax_class = heir.tax_class or self.get_tax_class(heir.relationship)

        # Freibetraege ermitteln
        personal_allowance = self.get_personal_allowance(
            heir.relationship, is_inheritance
        )

        # Alter bei Tod berechnen für Versorgungsfreibetrag
        age_at_event: Optional[int] = None
        if heir.birth_date:
            age_at_event = (date.today() - heir.birth_date).days // 365

        care_allowance = self.get_care_allowance(
            heir.relationship, age_at_event, is_inheritance
        )

        # Hausrat-Freibetrag (nur Klasse I)
        household_allowance = Decimal("0")
        if tax_class == TaxClass.KLASSE_I:
            household_allowance = HAUSRAT_FREIBETRAG_KLASSE_I + SONSTIGE_BEWEGLICHE_SACHEN_KLASSE_I

        # Steuerpflichtiger Erwerb
        total_deductions = personal_allowance + care_allowance + household_allowance
        other_deductions = Decimal("0")  # Erweiterbar für Beerdigungskosten etc.

        taxable_inheritance = gross_inheritance
        tax_base = max(Decimal("0"), taxable_inheritance - total_deductions - other_deductions)

        # Steuer berechnen
        tax_amount, tax_rate = self.calculate_inheritance_tax(tax_base, tax_class)

        # Effektiver Steuersatz bezogen auf Brutto-Erbe
        effective_rate = Decimal("0")
        if gross_inheritance > 0:
            effective_rate = (tax_amount / gross_inheritance * 100).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )

        return InheritanceTaxScenario(
            heir=heir,
            gross_inheritance=gross_inheritance,
            taxable_inheritance=taxable_inheritance,
            personal_allowance=personal_allowance,
            care_allowance=care_allowance,
            household_allowance=household_allowance,
            other_deductions=other_deductions,
            tax_base=tax_base,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            effective_tax_rate=effective_rate,
        )

    # =========================================================================
    # Schenkungsplanung
    # =========================================================================

    def create_ten_year_gift_plan(
        self,
        recipient: Heir,
        total_intended_gift: Decimal,
        gifts_already_made: List[Tuple[date, Decimal]] = None,
    ) -> TenYearGiftPlan:
        """
        Erstellt einen 10-Jahres-Schenkungsplan zur Steueroptimierung.

        Der Freibetrag erneuert sich alle 10 Jahre vollständig.
        """
        if gifts_already_made is None:
            gifts_already_made = []

        allowance = self.get_personal_allowance(recipient.relationship, is_inheritance=False)

        # Aktuelle 10-Jahres-Periode berechnen
        today = date.today()

        # Geschenke der letzten 10 Jahre summieren
        period_start = today - timedelta(days=3650)  # 10 Jahre
        current_gifts = Decimal("0")

        earliest_gift_date: Optional[date] = None
        for gift_date, gift_amount in gifts_already_made:
            if gift_date >= period_start:
                current_gifts += gift_amount
                if earliest_gift_date is None or gift_date < earliest_gift_date:
                    earliest_gift_date = gift_date

        remaining_allowance = max(Decimal("0"), allowance - current_gifts)

        # Nächstes Freibetrag-Reset berechnen
        if earliest_gift_date:
            period_end = earliest_gift_date + timedelta(days=3650)
        else:
            period_end = today + timedelta(days=3650)

        # Schenkungsszenarien erstellen
        recommended_gifts: List[GiftPlanningScenario] = []
        remaining_to_gift = total_intended_gift

        # Szenario 1: Sofort den Restfreibetrag nutzen
        if remaining_allowance > 0 and remaining_to_gift > 0:
            immediate_gift = min(remaining_allowance, remaining_to_gift)
            recommended_gifts.append(GiftPlanningScenario(
                recipient=recipient,
                annual_gift=immediate_gift,
                years=1,
                total_gift=immediate_gift,
                tax_free_amount=immediate_gift,
                taxable_amount=Decimal("0"),
                estimated_tax=Decimal("0"),
                strategy_description=(
                    f"Sofortige Schenkung bis zum Freibetrag: {immediate_gift:.2f} EUR steuerfrei"
                ),
                next_renewal_date=period_end,
            ))
            remaining_to_gift -= immediate_gift

        # Szenario 2: Nach Freibetrag-Erneuerung
        if remaining_to_gift > 0:
            next_period_gift = min(allowance, remaining_to_gift)
            recommended_gifts.append(GiftPlanningScenario(
                recipient=recipient,
                annual_gift=next_period_gift,
                years=1,
                total_gift=next_period_gift,
                tax_free_amount=next_period_gift,
                taxable_amount=Decimal("0"),
                estimated_tax=Decimal("0"),
                strategy_description=(
                    f"Nach Freibetrag-Erneuerung ({period_end}): "
                    f"{next_period_gift:.2f} EUR steuerfrei möglich"
                ),
                next_renewal_date=period_end + timedelta(days=3650),
            ))

        # Steuerersparnis berechnen
        tax_without_planning, _ = self.calculate_inheritance_tax(
            total_intended_gift - self.get_personal_allowance(recipient.relationship),
            self.get_tax_class(recipient.relationship),
        )
        tax_with_planning = sum(s.estimated_tax for s in recommended_gifts)
        total_savings = tax_without_planning - tax_with_planning

        return TenYearGiftPlan(
            recipient=recipient,
            allowance_per_10_years=allowance,
            current_gifts_in_period=current_gifts,
            remaining_allowance=remaining_allowance,
            period_start=period_start,
            period_end=period_end,
            recommended_gifts=recommended_gifts,
            total_tax_savings=total_savings,
        )

    # =========================================================================
    # Vollmacht-Verwaltung
    # =========================================================================

    async def get_powers_of_attorney(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[PowerOfAttorney]:
        """Holt alle Vollmachten eines Spaces."""
        # Vollmachten aus Dokumenten mit entsprechender Kategorie laden
        from app.db.models import PrivatDocument

        result = await db.execute(
            select(PrivatDocument)
            .where(
                PrivatDocument.space_id == space_id,
                PrivatDocument.deleted_at.is_(None),
                or_(
                    PrivatDocument.document_type == "vollmacht",
                    PrivatDocument.document_type == "power_of_attorney",
                    func.lower(PrivatDocument.name).contains("vollmacht"),
                    func.lower(PrivatDocument.name).contains("verfügung"),
                ),
            )
        )
        documents = result.scalars().all()

        poas: List[PowerOfAttorney] = []

        for doc in documents:
            # Typ aus Dokumentnamen/Metadaten ableiten
            poa_type = self._classify_poa_type(doc)

            poas.append(PowerOfAttorney(
                id=doc.id,
                poa_type=poa_type,
                title=doc.name or "Vollmacht",
                granted_to="",  # Müsste aus OCR extrahiert werden
                granted_date=doc.document_date,
                document_id=doc.id,
                is_active=True,
                notarized=self._check_if_notarized(doc),
            ))

        return poas

    def _classify_poa_type(self, doc: Any) -> PowerOfAttorneyType:
        """Klassifiziert den Typ einer Vollmacht."""
        text = ""
        if hasattr(doc, 'name') and doc.name:
            text += doc.name.lower()
        if hasattr(doc, 'title') and doc.title:
            text += " " + doc.title.lower()

        if "vorsorgevollmacht" in text:
            return PowerOfAttorneyType.VORSORGEVOLLMACHT
        if "generalvollmacht" in text:
            return PowerOfAttorneyType.GENERALVOLLMACHT
        if "bankvollmacht" in text or "kontovollmacht" in text:
            return PowerOfAttorneyType.BANKVOLLMACHT
        if "patientenverfügung" in text:
            return PowerOfAttorneyType.PATIENTENVERFUEGUNG
        if "betreuungsverfügung" in text:
            return PowerOfAttorneyType.BETREUUNGSVERFUEGUNG
        if "sorgerecht" in text:
            return PowerOfAttorneyType.SORGERECHTSVERFUEGUNG

        return PowerOfAttorneyType.VORSORGEVOLLMACHT  # Default

    def _check_if_notarized(self, doc: Any) -> bool:
        """Prüft ob ein Dokument notariell beglaubigt ist."""
        text = ""
        if hasattr(doc, 'name') and doc.name:
            text += doc.name.lower()
        if hasattr(doc, 'ocr_text') and doc.ocr_text:
            text += " " + doc.ocr_text.lower()[:500]

        notary_indicators = ["notar", "beurkundung", "beglaubig", "öffentlich"]
        return any(ind in text for ind in notary_indicators)

    def check_essential_poas(
        self,
        existing_poas: List[PowerOfAttorney],
    ) -> List[str]:
        """Prüft auf fehlende wichtige Vollmachten."""
        existing_types = {poa.poa_type for poa in existing_poas if poa.is_active}

        essential = [
            (PowerOfAttorneyType.VORSORGEVOLLMACHT, "Vorsorgevollmacht"),
            (PowerOfAttorneyType.PATIENTENVERFUEGUNG, "Patientenverfügung"),
            (PowerOfAttorneyType.BANKVOLLMACHT, "Bankvollmacht"),
        ]

        missing: List[str] = []
        for poa_type, name in essential:
            if poa_type not in existing_types:
                missing.append(name)

        return missing

    # =========================================================================
    # Dokumentenzugriff für Erben
    # =========================================================================

    async def setup_heir_document_access(
        self,
        db: AsyncSession,
        space_id: UUID,
        heir_name: str,
        heir_email: Optional[str],
        document_ids: List[UUID],
        folder_ids: List[UUID],
        trigger: DocumentAccessTrigger,
        trigger_date: Optional[date] = None,
        trigger_age: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> HeirDocumentAccess:
        """
        Richtet zeitgesteuerten Dokumentenzugriff für einen Erben ein.

        SECURITY: Keine Details über Dokumente loggen!
        """
        ESTATE_PLANNING_CALCULATIONS.labels(calculation_type="heir_access_setup").inc()

        access = HeirDocumentAccess(
            heir_name=heir_name,
            heir_email=heir_email,
            documents=document_ids,
            folders=folder_ids,
            trigger=trigger,
            trigger_date=trigger_date,
            trigger_age=trigger_age,
            is_active=True,
            access_granted=False,
            notes=notes,
        )

        # In der Praxis: In DB speichern
        # Hier nur Rückgabe des Objekts

        logger.info(
            "heir_document_access_setup",
            space_id=str(space_id),
            trigger=trigger.value,
            document_count=len(document_ids),
            folder_count=len(folder_ids),
        )

        return access

    # =========================================================================
    # Nachlass-Zusammenfassung
    # =========================================================================

    async def generate_estate_summary(
        self,
        db: AsyncSession,
        space_id: UUID,
        heirs: List[Heir],
    ) -> EstateSummary:
        """
        Generiert eine vollständige Nachlass-Zusammenfassung.

        SECURITY: Keine Betraege oder persoenliche Daten loggen!
        """
        import time
        start_time = time.time()

        ESTATE_PLANNING_CALCULATIONS.labels(calculation_type="estate_summary").inc()

        # 1. Vermoegen ermitteln
        from app.services.privat.financial_health_service import get_financial_health_service

        health_service = get_financial_health_service()
        net_worth = await health_service.calculate_net_worth(db, space_id)

        total_assets = net_worth.total_assets
        total_liabilities = net_worth.total_liabilities
        net_estate = net_worth.net_worth

        # 2. Erbteile validieren
        total_shares = sum(h.share_percent for h in heirs if not h.specific_bequest)

        warnings: List[str] = []
        if total_shares != Decimal("100") and total_shares > 0:
            warnings.append(
                f"Erbteile summieren sich auf {total_shares}% statt 100%"
            )

        # 3. Steuer-Szenarien berechnen
        tax_scenarios: List[InheritanceTaxScenario] = []
        total_tax = Decimal("0")

        for heir in heirs:
            scenario = self.calculate_heir_scenario(
                heir, net_estate, is_inheritance=True
            )
            tax_scenarios.append(scenario)
            total_tax += scenario.tax_amount

        # 4. Vollmachten prüfen
        poas = await self.get_powers_of_attorney(db, space_id)
        missing_poas = self.check_essential_poas(poas)

        # 5. Empfehlungen generieren
        recommendations = self._generate_estate_recommendations(
            net_estate, heirs, tax_scenarios, missing_poas
        )

        # 6. Warnungen hinzufuegen
        if missing_poas:
            warnings.append(f"Fehlende wichtige Vollmachten: {', '.join(missing_poas)}")

        if total_tax > net_estate * Decimal("0.1"):
            warnings.append(
                "Erbschaftsteuer betraegt mehr als 10% des Nachlasses. "
                "Schenkungsplanung empfohlen."
            )

        duration = time.time() - start_time
        ESTATE_PLANNING_DURATION.observe(duration)

        logger.info(
            "estate_summary_generated",
            space_id=str(space_id),
            heir_count=len(heirs),
            poa_count=len(poas),
            duration_seconds=round(duration, 3),
        )

        return EstateSummary(
            space_id=space_id,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            net_estate=net_estate,
            real_estate_value=net_worth.property_value,
            investment_value=net_worth.investment_value,
            vehicle_value=net_worth.vehicle_value,
            other_assets=net_worth.cash_and_savings,
            mortgage_debt=net_worth.mortgage_debt,
            other_debt=net_worth.loan_debt,
            heirs=heirs,
            total_shares=total_shares,
            tax_scenarios=tax_scenarios,
            total_estimated_tax=total_tax,
            active_powers_of_attorney=poas,
            missing_essential_poas=missing_poas,
            heir_document_access=[],  # Wuerde aus DB geladen
            recommendations=recommendations,
            warnings=warnings,
        )

    def _generate_estate_recommendations(
        self,
        net_estate: Decimal,
        heirs: List[Heir],
        scenarios: List[InheritanceTaxScenario],
        missing_poas: List[str],
    ) -> List[str]:
        """Generiert Empfehlungen zur Nachlassplanung."""
        recommendations: List[str] = []

        # Vollmachten
        for poa in missing_poas:
            recommendations.append(f"Empfehlung: {poa} erstellen lassen")

        # Schenkungsplanung
        high_tax_heirs = [s for s in scenarios if s.effective_tax_rate > Decimal("10")]
        if high_tax_heirs:
            recommendations.append(
                "Schenkungsplanung: Durch gestaffelte Schenkungen könnten "
                "Freibetraege mehrfach genutzt werden (alle 10 Jahre)."
            )

        # Testament-Empfehlung
        if len(heirs) > 2:
            recommendations.append(
                "Bei mehreren Erben: Notarielles Testament empfohlen "
                "zur Vermeidung von Erbstreitigkeiten."
            )

        # Immobilien-Spezifisch
        if any(
            h.relationship == RelationshipType.EHEPARTNER
            for h in heirs
        ):
            recommendations.append(
                "Familienheim-Befreiung: Selbstgenutzte Immobilie kann "
                "steuerfrei an Ehepartner vererbt werden (bei Selbstnutzung für 10 Jahre)."
            )

        # Lebensversicherungen
        recommendations.append(
            "Tipp: Lebensversicherungen mit Bezugsrecht umgehen den Nachlass "
            "und können Erbschaftsteuer sparen."
        )

        return recommendations[:5]  # Max 5 Empfehlungen

    # =========================================================================
    # Niesbrauch-Berechnung
    # =========================================================================

    def calculate_usufruct_value(
        self,
        asset_value: Decimal,
        annual_yield_rate: Decimal,  # z.B. 0.04 für 4% Mietrendite
        beneficiary_age: int,
        gender: str = "m",  # "m" oder "f"
    ) -> Decimal:
        """
        Berechnet den Kapitalwert eines Niessbrauchs.

        Wichtig für Schenkung unter Niessbrauchsvorbehalt
        (Steueroptimierung bei Immobilien).
        """
        # Jahrlicher Ertrag
        annual_benefit = asset_value * annual_yield_rate

        # Kapitalisierungsfaktor nach Sterbetafel
        # Vereinfachte Tabelle (Anlage 9a BewG)
        # In der Praxis: Aktuelle BMF-Tabellen verwenden
        multipliers = {
            # Alter: Faktor (Durchschnitt m/f)
            30: Decimal("17.7"),
            40: Decimal("15.5"),
            50: Decimal("13.2"),
            60: Decimal("10.8"),
            65: Decimal("9.3"),
            70: Decimal("7.8"),
            75: Decimal("6.3"),
            80: Decimal("4.8"),
            85: Decimal("3.5"),
            90: Decimal("2.4"),
        }

        # Nächsten Faktor finden
        ages = sorted(multipliers.keys())
        factor = Decimal("5")  # Default

        for age in ages:
            if beneficiary_age <= age:
                factor = multipliers[age]
                break

        usufruct_value = (annual_benefit * factor).quantize(Decimal("0.01"))
        return usufruct_value

    def calculate_gift_with_usufruct(
        self,
        asset_value: Decimal,
        usufruct_value: Decimal,
        recipient: Heir,
    ) -> Dict[str, Any]:
        """
        Berechnet Schenkungsteuer bei Übertragung unter Niessbrauchsvorbehalt.

        Der Niessbrauch mindert den steuerpflichtigen Erwerb.
        """
        net_gift_value = asset_value - usufruct_value
        allowance = self.get_personal_allowance(recipient.relationship, is_inheritance=False)
        tax_class = self.get_tax_class(recipient.relationship)

        taxable_amount = max(Decimal("0"), net_gift_value - allowance)
        tax, rate = self.calculate_inheritance_tax(taxable_amount, tax_class)

        # Vergleich ohne Niessbrauch
        tax_without_usufruct, _ = self.calculate_inheritance_tax(
            max(Decimal("0"), asset_value - allowance),
            tax_class,
        )
        savings = tax_without_usufruct - tax

        return {
            "asset_value": str(asset_value),
            "usufruct_value": str(usufruct_value),
            "net_gift_value": str(net_gift_value),
            "personal_allowance": str(allowance),
            "taxable_amount": str(taxable_amount),
            "tax_amount": str(tax),
            "tax_rate": str(rate * 100) + "%",
            "savings_vs_direct_gift": str(savings),
            "recommendation": (
                "Niessbrauchsvorbehalt empfohlen" if savings > 1000
                else "Direktübertragung ggf. vorteilhafter"
            ),
        }


# =============================================================================
# Singleton-Instanz
# =============================================================================

def get_estate_planning_service() -> EstatePlanningService:
    """Gibt die Singleton-Instanz des Estate Planning Service zurück."""
    return EstatePlanningService()

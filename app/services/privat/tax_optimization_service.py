# -*- coding: utf-8 -*-
"""
TaxOptimizationService - Intelligente Steueroptimierung fuer das Privat-Modul.

Enterprise-Feature fuer umfassende Steueroptimierung mit:
1. Automatische Dokumenten-Klassifizierung nach Steuer-Kategorien
2. Deutsche Einkommensteuer-Berechnung (2024-2026)
3. ELSTER XML Export-Vorbereitung (Anlage N, V, EUER)
4. Steuer-Prognose und "Was-waere-wenn" Szenarien
5. Intelligente Optimierungsvorschlaege
6. AfA-Berechnung fuer Abschreibungen
7. Vorauszahlungs-Tracking

Unterstuetzte Steuer-Kategorien:
- Werbungskosten (berufsbedingte Aufwendungen)
- Sonderausgaben (Versicherungen, Vorsorge, Spenden)
- Aussergewoehnliche Belastungen (Krankheit, Behinderung)
- Haushaltsnahe Dienstleistungen (20% bis max. 4.000 EUR)
- Handwerkerleistungen (20% bis max. 1.200 EUR)
- AfA (Abschreibungen fuer Vermietung/Verpachtung)

SECURITY: NIEMALS persoenliche Finanzdaten loggen!
Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from enum import Enum

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func, and_, or_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# ELSTER Anlage-Typen
# =============================================================================

class ElsterAnlage(str, Enum):
    """ELSTER Formular-Anlagen fuer Steuererklaerung."""
    MANTELBOGEN = "mantelbogen"  # Hauptformular
    ANLAGE_N = "anlage_n"  # Einkuenfte aus nichtselbstaendiger Arbeit
    ANLAGE_V = "anlage_v"  # Einkuenfte aus Vermietung und Verpachtung
    ANLAGE_EUER = "anlage_euer"  # Einnahmen-Ueberschuss-Rechnung
    ANLAGE_KAP = "anlage_kap"  # Einkuenfte aus Kapitalvermoegen
    ANLAGE_R = "anlage_r"  # Renten
    ANLAGE_SO = "anlage_so"  # Sonstige Einkuenfte
    ANLAGE_VORSORGE = "anlage_vorsorge"  # Vorsorgeaufwendungen
    ANLAGE_HAUSHALTSNAHE = "anlage_haushaltsnahe"  # Haushaltsnahe Dienstleistungen
    ANLAGE_KIND = "anlage_kind"  # Kinder
    ANLAGE_UNTERHALT = "anlage_unterhalt"  # Unterhaltsleistungen
    ANLAGE_AV = "anlage_av"  # Abschreibungsverzeichnis


class ElsterFieldMapping(str, Enum):
    """ELSTER Kennzahlen fuer die wichtigsten Felder."""
    # Anlage N (Arbeitnehmereinkuenfte)
    BRUTTOARBEITSLOHN = "210"
    WERBUNGSKOSTEN_GESAMT = "220"
    WERBUNGSKOSTEN_PAUSCHALE = "221"
    FAHRTKOSTEN = "222"
    ARBEITSMITTEL = "223"
    FORTBILDUNGSKOSTEN = "224"
    HOMEOFFICE_PAUSCHALE = "225"

    # Anlage V (Vermietung)
    MIETEINNAHMEN = "310"
    WERBUNGSKOSTEN_VERMIETUNG = "320"
    AFA_GEBAEUDE = "321"
    ZINSEN_DARLEHEN = "322"
    NEBENKOSTEN_NICHT_UMLAGEFAEHIG = "323"

    # Anlage Vorsorge
    KRANKENVERSICHERUNG_BASIS = "410"
    PFLEGEVERSICHERUNG = "411"
    ALTERSVORSORGE_RIESTER = "412"
    ALTERSVORSORGE_RUERUP = "413"

    # Haushaltsnahe Dienstleistungen
    HAUSHALTSNAHE_SUMME = "510"
    HANDWERKERLEISTUNGEN_SUMME = "520"

    # Sonderausgaben
    SPENDEN_INLAND = "610"
    KIRCHENSTEUER = "611"
    KINDERBETREUUNG = "612"


# =============================================================================
# Prometheus Metriken
# =============================================================================

TAX_OPTIMIZATION_CALCULATIONS = Counter(
    "tax_optimization_calculations_total",
    "Anzahl der Steueroptimierungs-Berechnungen",
    ["calculation_type"]
)

TAX_OPTIMIZATION_DURATION = Histogram(
    "tax_optimization_duration_seconds",
    "Dauer der Steueroptimierungs-Berechnung",
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)


# =============================================================================
# Deutsche Steuer-Konstanten (Stand 2026)
# =============================================================================

class TaxCategory(str, Enum):
    """Deutsche Steuer-Kategorien fuer Abzuege."""
    WERBUNGSKOSTEN = "werbungskosten"
    SONDERAUSGABEN = "sonderausgaben"
    AUSSERGEWOEHNLICHE_BELASTUNGEN = "aussergewoehnliche_belastungen"
    HAUSHALTSNAHE_DIENSTLEISTUNGEN = "haushaltsnahe_dienstleistungen"
    HANDWERKERLEISTUNGEN = "handwerkerleistungen"
    DOPPELTE_HAUSHALTSFUEHRUNG = "doppelte_haushaltsfuehrung"
    HOMEOFFICE = "homeoffice"
    KINDERBETREUUNG = "kinderbetreuung"
    SPENDEN = "spenden"
    KIRCHENSTEUER = "kirchensteuer"


class TaxDeadlineType(str, Enum):
    """Typen von Steuerfristen."""
    EINKOMMENSTEUER = "einkommensteuer"
    GEWERBESTEUER = "gewerbesteuer"
    UMSATZSTEUER_VORANMELDUNG = "umsatzsteuer_voranmeldung"
    UMSATZSTEUER_ERKLAERUNG = "umsatzsteuer_erklaerung"
    GRUNDSTEUER = "grundsteuer"
    KOERPERSCHAFTSTEUER = "koerperschaftsteuer"
    LOHNSTEUER = "lohnsteuer"
    FRISTVERLÄNGERUNG = "fristverlaengerung"


class TaxRating(str, Enum):
    """Bewertung der Steueroptimierung."""
    OPTIMAL = "optimal"
    GUT = "gut"
    VERBESSERBAR = "verbesserbar"
    OPTIMIERUNGSBEDARF = "optimierungsbedarf"


# =============================================================================
# Steuerliche Grenzwerte (2024-2026)
# Jahr-spezifische Werte fuer praezise Berechnungen
# =============================================================================

# Grundfreibetraege nach Jahr (Single)
GRUNDFREIBETRAG_BY_YEAR = {
    2024: Decimal("11604"),
    2025: Decimal("12084"),
    2026: Decimal("12096"),  # geschaetzt
}

# Grundfreibetraege verheiratet (Splittingtarif = 2x Single)
GRUNDFREIBETRAG_VERHEIRATET_BY_YEAR = {
    2024: Decimal("23208"),
    2025: Decimal("24168"),
    2026: Decimal("24192"),
}

# Werbungskosten-Pauschale (Arbeitnehmer)
WERBUNGSKOSTEN_PAUSCHALE = Decimal("1230")

# Sonderausgaben-Pauschale
SONDERAUSGABEN_PAUSCHALE_SINGLE = Decimal("36")
SONDERAUSGABEN_PAUSCHALE_VERHEIRATET = Decimal("72")

# Sparerfreibetrag (Kapitalertraege)
SPARERFREIBETRAG_SINGLE = Decimal("1000")
SPARERFREIBETRAG_VERHEIRATET = Decimal("2000")

# Haushaltsnahe Dienstleistungen
HAUSHALTSNAHE_MAX_ANSATZ = Decimal("20000")  # Basis
HAUSHALTSNAHE_ABZUG_PROZENT = Decimal("0.20")  # 20%
HAUSHALTSNAHE_MAX_ABZUG = Decimal("4000")  # Max Steuerermassigung

# Handwerkerleistungen
HANDWERKER_MAX_ANSATZ = Decimal("6000")  # Basis
HANDWERKER_ABZUG_PROZENT = Decimal("0.20")  # 20%
HANDWERKER_MAX_ABZUG = Decimal("1200")  # Max Steuerermassigung

# Homeoffice-Pauschale
HOMEOFFICE_TAGESSATZ = Decimal("6")  # EUR pro Tag
HOMEOFFICE_MAX_TAGE = 210
HOMEOFFICE_MAX_ABZUG = Decimal("1260")  # 210 x 6 EUR

# Pendlerpauschale (Entfernungspauschale)
PENDLER_PAUSCHALE_PRO_KM_BIS_20 = Decimal("0.30")  # Erste 20 km
PENDLER_PAUSCHALE_PRO_KM_AB_21 = Decimal("0.38")  # Ab 21 km (erhoehte Pauschale)
PENDLER_MAX_ARBEITSTAGE = 230  # Standardwert

# Kinderbetreuungskosten
KINDERBETREUUNG_MAX = Decimal("6000")  # Pro Kind
KINDERBETREUUNG_ABZUG_PROZENT = Decimal("0.6667")  # 2/3 absetzbar
KINDERBETREUUNG_MAX_ABSETZBAR = Decimal("4000")  # Pro Kind

# Spenden-Hoechstgrenzen
SPENDEN_MAX_PROZENT_EINKOMMEN = Decimal("0.20")  # 20% des Gesamtbetrags

# Aussergewoehnliche Belastungen - Zumutbare Belastung
# Prozentsaetze basierend auf Einkommen und Familienstand
ZUMUTBARE_BELASTUNG_PROZENT = {
    # (bis_einkommen, ohne_kinder, mit_1_2_kindern, ab_3_kindern)
    "stufe1": (Decimal("15340"), Decimal("0.05"), Decimal("0.02"), Decimal("0.01")),
    "stufe2": (Decimal("51130"), Decimal("0.06"), Decimal("0.03"), Decimal("0.01")),
    "stufe3": (None, Decimal("0.07"), Decimal("0.04"), Decimal("0.02")),  # unbegrenzt
}

# AfA-Saetze fuer Gebaeude (Abschreibung fuer Abnutzung)
AFA_SAETZE_GEBAEUDE = {
    "neubau_ab_2023": Decimal("0.03"),  # 3% (33 1/3 Jahre)
    "neubau_1925_2022": Decimal("0.02"),  # 2% (50 Jahre)
    "altbau_vor_1925": Decimal("0.025"),  # 2.5% (40 Jahre)
    "denkmal": Decimal("0.09"),  # 9% erste 8 Jahre, dann 7%
}

# Vorauszahlungstermine Einkommensteuer
VORAUSZAHLUNGSTERMINE = [
    (3, 10),   # 10. Maerz
    (6, 10),   # 10. Juni
    (9, 10),   # 10. September
    (12, 10),  # 10. Dezember
]

# Einkommensteuer-Tarif 2026 (Zone 2-4)
# Zone 1: Bis Grundfreibetrag = 0%
# Zone 2: Progressionszone I (14% bis ca. 24%)
# Zone 3: Progressionszone II (24% bis 42%)
# Zone 4: Proportionalzone (42%)
# Zone 5: Reichensteuer (45%)
ESt_ZONE2_BIS = Decimal("17442")
ESt_ZONE3_BIS = Decimal("68479")
ESt_ZONE4_BIS = Decimal("277825")
ESt_EINGANGSSTEUERSATZ = Decimal("0.14")
ESt_SPITZENSTEUERSATZ = Decimal("0.42")
ESt_REICHENSTEUERSATZ = Decimal("0.45")

# Solidaritaetszuschlag (nur bei hohen Einkommen)
SOLI_FREIGRENZE_SINGLE = Decimal("18130")  # Steuerbetrag
SOLI_FREIGRENZE_VERHEIRATET = Decimal("36260")
SOLI_SATZ = Decimal("0.055")  # 5.5%

# Kirchensteuer (je nach Bundesland 8% oder 9%)
KIRCHENSTEUER_SAETZE = {
    "BW": Decimal("0.08"),  # Baden-Wuerttemberg
    "BY": Decimal("0.08"),  # Bayern
    "default": Decimal("0.09"),  # Alle anderen Bundeslaender
}

# Dokument-Kategorien fuer automatische Erkennung
TAX_DOCUMENT_KEYWORDS = {
    TaxCategory.WERBUNGSKOSTEN: [
        "fahrtkosten", "arbeitsweg", "fortbildung", "fachliteratur",
        "arbeitsmittel", "berufskleidung", "bewerbung", "umzug",
        "arbeitszimmer", "doppelte haushaltsfuehrung", "reisekosten",
    ],
    TaxCategory.SONDERAUSGABEN: [
        "versicherung", "altersvorsorge", "riester", "ruerup",
        "krankenversicherung", "pflegeversicherung", "basisrente",
        "haftpflicht", "unfallversicherung",
    ],
    TaxCategory.AUSSERGEWOEHNLICHE_BELASTUNGEN: [
        "arzt", "zahnarzt", "krankenhaus", "medikamente",
        "brille", "zahnersatz", "behinderung", "pflege",
        "kur", "rehabilitation", "scheidung", "bestattung",
    ],
    TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN: [
        "haushaltshilfe", "gaertner", "reinigung", "pflege",
        "betreuung", "hausmeister", "winterdienst", "putzhilfe",
    ],
    TaxCategory.HANDWERKERLEISTUNGEN: [
        "handwerker", "renovierung", "reparatur", "installation",
        "malerarbeiten", "elektro", "sanitaer", "heizung",
        "dach", "fassade", "schornsteinfeger",
    ],
    TaxCategory.KINDERBETREUUNG: [
        "kindergarten", "kita", "tagesmutter", "hort",
        "kinderbetreuung", "babysitter", "au-pair",
    ],
    TaxCategory.SPENDEN: [
        "spende", "zuwendung", "gemeinnuetzig", "stiftung",
        "kirche", "partei", "spendenquittung",
    ],
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TaxDeductionItem:
    """Einzelner Steuerabzugs-Posten."""
    category: TaxCategory
    description: str
    gross_amount: Decimal
    deductible_amount: Decimal
    document_id: Optional[UUID] = None
    document_date: Optional[date] = None
    confidence: Decimal = Decimal("0.0")
    is_verified: bool = False
    notes: Optional[str] = None


@dataclass
class TaxDeductionSummary:
    """Zusammenfassung aller Abzuege einer Kategorie."""
    category: TaxCategory
    category_name: str  # Deutsche Bezeichnung
    total_gross: Decimal
    total_deductible: Decimal
    max_deductible: Optional[Decimal]  # Hoechstbetrag falls vorhanden
    utilization_percent: Optional[Decimal]  # Auslastung in %
    items: List[TaxDeductionItem]
    recommendations: List[str]


@dataclass
class TaxDeadline:
    """Steuerliche Frist."""
    deadline_type: TaxDeadlineType
    title: str
    due_date: date
    description: str
    is_recurring: bool = True
    recurrence_pattern: Optional[str] = None  # "monthly", "quarterly", "yearly"
    days_until_due: int = 0
    is_overdue: bool = False
    reminder_sent: bool = False


@dataclass
class TaxOptimizationResult:
    """Vollstaendiges Ergebnis der Steueroptimierung."""
    space_id: UUID
    tax_year: int

    # Gesamtuebersicht
    total_deductible: Decimal
    estimated_tax_savings: Decimal
    optimization_rating: TaxRating

    # Kategorie-Details
    deduction_summaries: List[TaxDeductionSummary]

    # Fristen
    upcoming_deadlines: List[TaxDeadline]
    overdue_deadlines: List[TaxDeadline]

    # Optimierungsvorschlaege
    optimization_suggestions: List[str]
    missing_deductions: List[str]

    # DATEV-Export Info
    datev_export_ready: bool
    datev_export_notes: Optional[str] = None

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TaxSavingsEstimate:
    """Schaetzung der Steuerersparnis."""
    estimated_gross_income: Decimal
    total_deductions: Decimal
    taxable_income: Decimal
    estimated_tax_without_deductions: Decimal
    estimated_tax_with_deductions: Decimal
    estimated_savings: Decimal
    effective_tax_rate: Decimal  # In Prozent
    marginal_tax_rate: Decimal  # Grenzsteuersatz


@dataclass
class TaxProjection:
    """Vollstaendige Steuer-Prognose fuer ein Jahr."""
    tax_year: int

    # Einkuenfte
    total_income: Decimal
    income_from_employment: Decimal  # Arbeitseinkuenfte
    income_from_rental: Decimal  # Vermietung
    income_from_capital: Decimal  # Kapitalertraege
    other_income: Decimal  # Sonstige

    # Abzuege
    total_deductions: Decimal
    werbungskosten: Decimal
    sonderausgaben: Decimal
    aussergewoehnliche_belastungen: Decimal
    haushaltsnahe_abzug: Decimal
    handwerker_abzug: Decimal

    # Steuern
    taxable_income: Decimal
    estimated_income_tax: Decimal
    solidarity_surcharge: Decimal
    church_tax: Decimal
    total_tax: Decimal

    # Vorauszahlungen
    already_paid: Decimal  # Vorauszahlungen und Lohnsteuer
    expected_refund: Decimal  # Positiv = Erstattung, Negativ = Nachzahlung

    # Optimierung
    optimization_potential: Decimal  # Geschaetztes Sparpotenzial
    unused_allowances: List[str]  # Nicht genutzte Freibetraege

    # Metadata
    is_married: bool
    number_of_children: int
    federal_state: str  # Bundesland fuer Kirchensteuer
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WhatIfScenario:
    """Was-waere-wenn Szenario fuer Steuer-Simulation."""
    scenario_name: str
    description: str

    # Eingabe-Parameter
    additional_income: Decimal = Decimal("0")
    additional_deductions: Decimal = Decimal("0")
    change_marital_status: Optional[bool] = None
    additional_children: int = 0

    # Ergebnis im Vergleich
    tax_before: Decimal = Decimal("0")
    tax_after: Decimal = Decimal("0")
    tax_difference: Decimal = Decimal("0")  # Positiv = Ersparnis
    recommendation: str = ""


@dataclass
class AfACalculation:
    """Abschreibungsberechnung fuer ein Wirtschaftsgut."""
    asset_id: Optional[UUID]
    asset_name: str
    asset_type: str  # gebaeude, beweglich, etc.

    purchase_date: date
    purchase_price: Decimal
    useful_life_years: int
    afa_rate: Decimal

    annual_depreciation: Decimal
    accumulated_depreciation: Decimal
    remaining_book_value: Decimal
    years_remaining: int

    # ELSTER-Felder
    elster_anlage: ElsterAnlage
    elster_field: str


@dataclass
class ElsterExportData:
    """Struktur fuer ELSTER-Export eines Steuerjahres."""
    tax_year: int
    steuernummer: Optional[str]  # Wird nicht gespeichert, nur fuer Export

    # Anlagen-Status
    anlagen: Dict[ElsterAnlage, bool]  # Welche Anlagen relevant sind

    # Feldwerte nach Anlage gruppiert
    anlage_n_fields: Dict[str, Any]  # Arbeitseinkuenfte
    anlage_v_fields: Dict[str, Any]  # Vermietung
    anlage_vorsorge_fields: Dict[str, Any]  # Vorsorgeaufwendungen
    anlage_haushaltsnahe_fields: Dict[str, Any]  # Haushaltsnahe DL

    # Validierung
    is_complete: bool
    missing_fields: List[str]
    validation_warnings: List[str]

    # Export-Metadaten
    export_format: str = "xml"  # xml oder json
    export_version: str = "2026.1"
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DocumentTaxAnalysis:
    """Steuerliche Analyse eines einzelnen Dokuments."""
    document_id: UUID
    document_name: str

    # Kategorisierung
    category: TaxCategory
    category_name: str
    confidence: Decimal

    # Betraege
    gross_amount: Decimal
    deductible_amount: Decimal
    potential_savings: Decimal  # Bei Grenzsteuersatz

    # ELSTER-Zuordnung
    elster_anlage: ElsterAnlage
    elster_field: str

    # Empfehlungen
    suggestions: List[str]
    missing_info: List[str]  # Fehlende Informationen fuer optimale Absetzung


@dataclass
class TaxAdvancedPayment:
    """Steuer-Vorauszahlung Tracking."""
    payment_id: Optional[UUID]
    tax_year: int
    quarter: int  # 1-4
    due_date: date

    amount_due: Decimal
    amount_paid: Decimal
    payment_date: Optional[date]

    is_paid: bool
    is_overdue: bool
    days_until_due: int


# =============================================================================
# Singleton Service
# =============================================================================

class TaxOptimizationService:
    """
    Singleton Service fuer Steueroptimierung.

    Erkennt automatisch steuerlich relevante Dokumente,
    berechnet Abzuege und gibt Optimierungsvorschlaege.

    SECURITY: Alle finanziellen Daten werden NIE geloggt!
    """

    _instance: Optional["TaxOptimizationService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TaxOptimizationService":
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

        # Kategorie-Namen (deutsch)
        self._category_names = {
            TaxCategory.WERBUNGSKOSTEN: "Werbungskosten",
            TaxCategory.SONDERAUSGABEN: "Sonderausgaben",
            TaxCategory.AUSSERGEWOEHNLICHE_BELASTUNGEN: "Aussergewoehnliche Belastungen",
            TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN: "Haushaltsnahe Dienstleistungen",
            TaxCategory.HANDWERKERLEISTUNGEN: "Handwerkerleistungen",
            TaxCategory.DOPPELTE_HAUSHALTSFUEHRUNG: "Doppelte Haushaltsfuehrung",
            TaxCategory.HOMEOFFICE: "Homeoffice-Pauschale",
            TaxCategory.KINDERBETREUUNG: "Kinderbetreuungskosten",
            TaxCategory.SPENDEN: "Spenden und Mitgliedsbeitraege",
            TaxCategory.KIRCHENSTEUER: "Kirchensteuer",
        }

        logger.info("tax_optimization_service_initialized")

    # =========================================================================
    # Hauptberechnung
    # =========================================================================

    async def analyze_tax_optimization(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: Optional[int] = None,
        estimated_gross_income: Optional[Decimal] = None,
        is_married: bool = False,
    ) -> TaxOptimizationResult:
        """
        Analysiert alle steuerlich relevanten Dokumente und berechnet Optimierungen.

        Args:
            db: Datenbank-Session
            space_id: ID des Privat-Space
            tax_year: Steuerjahr (Default: aktuelles Jahr)
            estimated_gross_income: Geschaetztes Bruttoeinkommen (fuer Ersparnis-Berechnung)
            is_married: Verheiratet (fuer Splitting-Tarif)

        Returns:
            TaxOptimizationResult mit allen Abzuegen und Empfehlungen

        SECURITY: Niemals Betraege oder persoenliche Daten loggen!
        """
        import time
        start_time = time.time()

        TAX_OPTIMIZATION_CALCULATIONS.labels(calculation_type="full_analysis").inc()

        if tax_year is None:
            tax_year = datetime.now(timezone.utc).year

        # 1. Alle relevanten Dokumente sammeln
        deduction_items = await self._collect_deductible_documents(
            db, space_id, tax_year
        )

        # 2. Versicherungen als Sonderausgaben einbeziehen
        insurance_items = await self._collect_insurance_deductions(
            db, space_id, tax_year
        )
        deduction_items.extend(insurance_items)

        # 3. Immobilien-bezogene Abzuege
        property_items = await self._collect_property_deductions(
            db, space_id, tax_year
        )
        deduction_items.extend(property_items)

        # 4. Nach Kategorien gruppieren und zusammenfassen
        summaries = self._summarize_deductions(deduction_items)

        # 5. Gesamtabzug berechnen
        total_deductible = sum(s.total_deductible for s in summaries)

        # 6. Steuerersparnis schaetzen
        estimated_savings = Decimal("0")
        if estimated_gross_income and estimated_gross_income > 0:
            savings_estimate = self._estimate_tax_savings(
                estimated_gross_income,
                total_deductible,
                is_married,
            )
            estimated_savings = savings_estimate.estimated_savings

        # 7. Fristen ermitteln
        upcoming_deadlines, overdue_deadlines = self._get_tax_deadlines(tax_year)

        # 8. Optimierungsvorschlaege generieren
        optimization_suggestions = self._generate_optimization_suggestions(
            summaries, estimated_gross_income
        )

        # 9. Fehlende Abzuege identifizieren
        missing_deductions = self._identify_missing_deductions(summaries)

        # 10. Rating berechnen
        rating = self._calculate_optimization_rating(summaries, missing_deductions)

        # 11. DATEV-Export-Status pruefen
        datev_ready, datev_notes = self._check_datev_export_readiness(summaries)

        duration = time.time() - start_time
        TAX_OPTIMIZATION_DURATION.observe(duration)

        logger.info(
            "tax_optimization_analysis_completed",
            space_id=str(space_id),
            tax_year=tax_year,
            categories_found=len(summaries),
            duration_seconds=round(duration, 3),
        )

        return TaxOptimizationResult(
            space_id=space_id,
            tax_year=tax_year,
            total_deductible=total_deductible,
            estimated_tax_savings=estimated_savings,
            optimization_rating=rating,
            deduction_summaries=summaries,
            upcoming_deadlines=upcoming_deadlines,
            overdue_deadlines=overdue_deadlines,
            optimization_suggestions=optimization_suggestions,
            missing_deductions=missing_deductions,
            datev_export_ready=datev_ready,
            datev_export_notes=datev_notes,
        )

    # =========================================================================
    # Dokumenten-Sammlung
    # =========================================================================

    async def _collect_deductible_documents(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: int,
    ) -> List[TaxDeductionItem]:
        """Sammelt alle steuerlich relevanten Dokumente."""
        from app.db.models import PrivatDocument

        items: List[TaxDeductionItem] = []

        year_start = date(tax_year, 1, 1)
        year_end = date(tax_year, 12, 31)

        # Dokumente des Steuerjahres laden
        result = await db.execute(
            select(PrivatDocument)
            .where(
                PrivatDocument.space_id == space_id,
                PrivatDocument.deleted_at.is_(None),
                or_(
                    and_(
                        PrivatDocument.document_date >= year_start,
                        PrivatDocument.document_date <= year_end,
                    ),
                    and_(
                        PrivatDocument.created_at >= datetime(tax_year, 1, 1, tzinfo=timezone.utc),
                        PrivatDocument.created_at < datetime(tax_year + 1, 1, 1, tzinfo=timezone.utc),
                    ),
                ),
            )
        )
        documents = result.scalars().all()

        for doc in documents:
            # Kategorie aus Dokument-Inhalt erkennen
            category, confidence = self._classify_document_tax_category(doc)

            if category and confidence > Decimal("0.5"):
                # Betrag aus extracted_data oder Metadaten extrahieren
                amount = self._extract_amount_from_document(doc)

                if amount and amount > 0:
                    deductible = self._calculate_deductible_amount(category, amount)

                    items.append(TaxDeductionItem(
                        category=category,
                        description=doc.name or doc.title or "Dokument",
                        gross_amount=amount,
                        deductible_amount=deductible,
                        document_id=doc.id,
                        document_date=doc.document_date,
                        confidence=confidence,
                        is_verified=False,
                    ))

        return items

    def _classify_document_tax_category(
        self,
        doc: Any,  # PrivatDocument
    ) -> Tuple[Optional[TaxCategory], Decimal]:
        """
        Klassifiziert ein Dokument nach Steuer-Kategorie.

        Returns:
            Tuple aus (Kategorie, Confidence 0-1)
        """
        # Text-Inhalt zusammenstellen
        text_content = ""
        if hasattr(doc, 'name') and doc.name:
            text_content += doc.name.lower() + " "
        if hasattr(doc, 'title') and doc.title:
            text_content += doc.title.lower() + " "
        if hasattr(doc, 'description') and doc.description:
            text_content += doc.description.lower() + " "
        if hasattr(doc, 'ocr_text') and doc.ocr_text:
            text_content += doc.ocr_text.lower()[:1000]  # Nur erste 1000 Zeichen

        if not text_content.strip():
            return None, Decimal("0")

        best_category: Optional[TaxCategory] = None
        best_score = 0

        for category, keywords in TAX_DOCUMENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_content)
            if score > best_score:
                best_score = score
                best_category = category

        if best_category and best_score > 0:
            # Confidence basierend auf Treffer-Anzahl
            confidence = min(Decimal("1.0"), Decimal(str(best_score)) * Decimal("0.25"))
            return best_category, confidence

        return None, Decimal("0")

    def _extract_amount_from_document(self, doc: Any) -> Optional[Decimal]:
        """Extrahiert den Betrag aus einem Dokument."""
        # Versuche aus extracted_data
        if hasattr(doc, 'extracted_data') and doc.extracted_data:
            data = doc.extracted_data
            for key in ['amount', 'total', 'betrag', 'summe', 'brutto', 'netto']:
                if key in data:
                    try:
                        return Decimal(str(data[key]))
                    except Exception:
                        continue

        # Versuche aus document_metadata
        if hasattr(doc, 'document_metadata') and doc.document_metadata:
            meta = doc.document_metadata
            for key in ['amount', 'total', 'betrag']:
                if key in meta:
                    try:
                        return Decimal(str(meta[key]))
                    except Exception:
                        continue

        return None

    def _calculate_deductible_amount(
        self,
        category: TaxCategory,
        gross_amount: Decimal,
    ) -> Decimal:
        """Berechnet den abzugsfaehigen Betrag je nach Kategorie."""
        if category == TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN:
            # 20% bis max 4.000 EUR
            return min(
                gross_amount * HAUSHALTSNAHE_ABZUG_PROZENT,
                HAUSHALTSNAHE_MAX_ABZUG,
            )

        elif category == TaxCategory.HANDWERKERLEISTUNGEN:
            # 20% bis max 1.200 EUR (nur Arbeitskosten!)
            # Annahme: 60% des Betrags sind Arbeitskosten
            labor_costs = gross_amount * Decimal("0.6")
            return min(
                labor_costs * HANDWERKER_ABZUG_PROZENT,
                HANDWERKER_MAX_ABZUG,
            )

        elif category == TaxCategory.KINDERBETREUUNG:
            # 2/3, max 4.000 EUR pro Kind
            return min(
                gross_amount * KINDERBETREUUNG_ABZUG_PROZENT,
                Decimal("4000"),
            )

        elif category in (
            TaxCategory.WERBUNGSKOSTEN,
            TaxCategory.SONDERAUSGABEN,
            TaxCategory.AUSSERGEWOEHNLICHE_BELASTUNGEN,
            TaxCategory.SPENDEN,
        ):
            # Voller Betrag abzugsfaehig (Hoechstgrenzen werden bei Summierung geprueft)
            return gross_amount

        else:
            return gross_amount

    # =========================================================================
    # Versicherungen und Immobilien
    # =========================================================================

    async def _collect_insurance_deductions(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: int,
    ) -> List[TaxDeductionItem]:
        """Sammelt Versicherungsbeitraege als Sonderausgaben."""
        from app.db.models import PrivatInsurance

        items: List[TaxDeductionItem] = []

        result = await db.execute(
            select(PrivatInsurance)
            .where(
                PrivatInsurance.space_id == space_id,
                PrivatInsurance.is_active == True,
            )
        )
        insurances = result.scalars().all()

        for insurance in insurances:
            # Jaehrlichen Beitrag berechnen
            if not insurance.premium_amount:
                continue

            annual_premium = insurance.premium_amount
            if hasattr(insurance, 'payment_frequency'):
                freq = insurance.payment_frequency
                if freq == "monthly":
                    annual_premium = insurance.premium_amount * 12
                elif freq == "quarterly":
                    annual_premium = insurance.premium_amount * 4
                elif freq == "semi_annual":
                    annual_premium = insurance.premium_amount * 2

            # Kategorie bestimmen
            ins_type = (insurance.insurance_type or "").lower()

            if any(t in ins_type for t in ["kranken", "pflege", "health", "care"]):
                category = TaxCategory.SONDERAUSGABEN
                description = f"Kranken-/Pflegeversicherung: {insurance.name}"
            elif any(t in ins_type for t in ["haftpflicht", "liability"]):
                category = TaxCategory.SONDERAUSGABEN
                description = f"Haftpflichtversicherung: {insurance.name}"
            elif any(t in ins_type for t in ["berufsunfaehigkeit", "disability"]):
                category = TaxCategory.SONDERAUSGABEN
                description = f"Berufsunfaehigkeitsversicherung: {insurance.name}"
            elif any(t in ins_type for t in ["unfall", "accident"]):
                category = TaxCategory.SONDERAUSGABEN
                description = f"Unfallversicherung: {insurance.name}"
            else:
                # Andere Versicherungen nur teilweise abzugsfaehig
                continue

            items.append(TaxDeductionItem(
                category=category,
                description=description,
                gross_amount=annual_premium,
                deductible_amount=annual_premium,  # Versicherungen voll abzugsfaehig
                confidence=Decimal("0.95"),
                is_verified=True,  # Aus strukturierten Daten
            ))

        return items

    async def _collect_property_deductions(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: int,
    ) -> List[TaxDeductionItem]:
        """Sammelt Immobilien-bezogene Abzuege (Werbungskosten bei Vermietung)."""
        from app.db.models import PrivatProperty, PrivatUtilityStatement

        items: List[TaxDeductionItem] = []

        # Vermietete Immobilien
        result = await db.execute(
            select(PrivatProperty)
            .where(
                PrivatProperty.space_id == space_id,
                PrivatProperty.is_rented == True,
                PrivatProperty.deleted_at.is_(None),
            )
        )
        properties = result.scalars().all()

        for prop in properties:
            # AfA (Abschreibung) - 2% bei Neubau ab 1925
            if prop.purchase_price and prop.purchase_date:
                # Vereinfacht: 2% AfA linear
                afa = prop.purchase_price * Decimal("0.02")

                items.append(TaxDeductionItem(
                    category=TaxCategory.WERBUNGSKOSTEN,
                    description=f"AfA Immobilie: {prop.name}",
                    gross_amount=afa,
                    deductible_amount=afa,
                    confidence=Decimal("0.9"),
                    is_verified=True,
                    notes="Abschreibung bei Vermietung (2% linear)",
                ))

            # Nebenkosten aus Utility Statements
            # (Nur Vermieter-Anteil, nicht umlagefaehig)
            # Dies ist komplex und erfordert detailliertere Daten

        return items

    # =========================================================================
    # Zusammenfassung und Berechnungen
    # =========================================================================

    def _summarize_deductions(
        self,
        items: List[TaxDeductionItem],
    ) -> List[TaxDeductionSummary]:
        """Gruppiert und summiert Abzuege nach Kategorie."""
        from collections import defaultdict

        grouped: Dict[TaxCategory, List[TaxDeductionItem]] = defaultdict(list)
        for item in items:
            grouped[item.category].append(item)

        summaries: List[TaxDeductionSummary] = []

        for category, cat_items in grouped.items():
            total_gross = sum(item.gross_amount for item in cat_items)
            total_deductible = sum(item.deductible_amount for item in cat_items)

            # Hoechstgrenzen anwenden
            max_deductible: Optional[Decimal] = None
            utilization: Optional[Decimal] = None
            recommendations: List[str] = []

            if category == TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN:
                max_deductible = HAUSHALTSNAHE_MAX_ABZUG
                if total_deductible > max_deductible:
                    total_deductible = max_deductible
                    recommendations.append(
                        "Hoechstbetrag fuer haushaltsnahe Dienstleistungen erreicht (4.000 EUR)."
                    )
                utilization = (total_deductible / max_deductible * 100).quantize(Decimal("0.1"))

            elif category == TaxCategory.HANDWERKERLEISTUNGEN:
                max_deductible = HANDWERKER_MAX_ABZUG
                if total_deductible > max_deductible:
                    total_deductible = max_deductible
                    recommendations.append(
                        "Hoechstbetrag fuer Handwerkerleistungen erreicht (1.200 EUR)."
                    )
                utilization = (total_deductible / max_deductible * 100).quantize(Decimal("0.1"))

            elif category == TaxCategory.WERBUNGSKOSTEN:
                # Nur ueber Pauschale absetzbar
                if total_deductible < WERBUNGSKOSTEN_PAUSCHALE:
                    recommendations.append(
                        f"Werbungskosten unter Pauschale ({WERBUNGSKOSTEN_PAUSCHALE} EUR). "
                        "Einzelnachweis lohnt sich nicht."
                    )
                else:
                    recommendations.append(
                        f"Werbungskosten ueber Pauschale! "
                        f"Ersparnis durch Einzelnachweis: {total_deductible - WERBUNGSKOSTEN_PAUSCHALE:.2f} EUR"
                    )

            summaries.append(TaxDeductionSummary(
                category=category,
                category_name=self._category_names.get(category, str(category)),
                total_gross=total_gross,
                total_deductible=total_deductible,
                max_deductible=max_deductible,
                utilization_percent=utilization,
                items=cat_items,
                recommendations=recommendations,
            ))

        return summaries

    def _estimate_tax_savings(
        self,
        gross_income: Decimal,
        total_deductions: Decimal,
        is_married: bool = False,
    ) -> TaxSavingsEstimate:
        """Schaetzt die Steuerersparnis durch Abzuege."""
        # Grundfreibetrag
        grundfreibetrag = (
            GRUNDFREIBETRAG_VERHEIRATET_2026 if is_married
            else GRUNDFREIBETRAG_2026
        )

        # Zu versteuerndes Einkommen
        taxable_without = max(Decimal("0"), gross_income - grundfreibetrag)
        taxable_with = max(Decimal("0"), gross_income - total_deductions - grundfreibetrag)

        # Steuer berechnen (vereinfachte Formel)
        tax_without = self._calculate_income_tax(taxable_without, is_married)
        tax_with = self._calculate_income_tax(taxable_with, is_married)

        savings = tax_without - tax_with

        # Effektiver Steuersatz
        effective_rate = Decimal("0")
        if gross_income > 0:
            effective_rate = (tax_with / gross_income * 100).quantize(Decimal("0.1"))

        # Grenzsteuersatz
        marginal_rate = self._get_marginal_tax_rate(taxable_with)

        return TaxSavingsEstimate(
            estimated_gross_income=gross_income,
            total_deductions=total_deductions,
            taxable_income=taxable_with + grundfreibetrag,  # Vor Grundfreibetrag
            estimated_tax_without_deductions=tax_without,
            estimated_tax_with_deductions=tax_with,
            estimated_savings=savings,
            effective_tax_rate=effective_rate,
            marginal_tax_rate=marginal_rate * 100,
        )

    def _calculate_income_tax(
        self,
        taxable_income: Decimal,
        is_married: bool = False,
    ) -> Decimal:
        """
        Berechnet die Einkommensteuer nach deutschem Tarif (vereinfacht).

        Splitting-Verfahren bei Verheirateten.
        """
        if is_married:
            # Splitting: Haelfte versteuern, Ergebnis verdoppeln
            half_income = taxable_income / 2
            return self._calculate_single_tax(half_income) * 2

        return self._calculate_single_tax(taxable_income)

    def _calculate_single_tax(self, income: Decimal) -> Decimal:
        """Berechnet ESt fuer Einzelveranlagung (Tarif 2026 geschaetzt)."""
        if income <= 0:
            return Decimal("0")

        # Zone 1: Bis Grundfreibetrag - steuerfrei (schon abgezogen)

        # Zone 2: Progressionszone I
        if income <= ESt_ZONE2_BIS:
            y = (income - Decimal("11604")) / Decimal("10000")
            return ((Decimal("922.98") * y + Decimal("1400")) * y).quantize(Decimal("0.01"))

        # Zone 3: Progressionszone II
        if income <= ESt_ZONE3_BIS:
            z = (income - Decimal("17005")) / Decimal("10000")
            return ((Decimal("181.19") * z + Decimal("2397")) * z + Decimal("991.21")).quantize(Decimal("0.01"))

        # Zone 4: Proportionalzone I (42%)
        if income <= ESt_ZONE4_BIS:
            return (Decimal("0.42") * income - Decimal("10602.13")).quantize(Decimal("0.01"))

        # Zone 5: Reichensteuer (45%)
        return (Decimal("0.45") * income - Decimal("18936.88")).quantize(Decimal("0.01"))

    def _get_marginal_tax_rate(self, taxable_income: Decimal) -> Decimal:
        """Ermittelt den Grenzsteuersatz."""
        if taxable_income <= 0:
            return Decimal("0")
        if taxable_income <= ESt_ZONE2_BIS:
            return Decimal("0.14")  # Eingangssteuersatz
        if taxable_income <= ESt_ZONE3_BIS:
            return Decimal("0.24")  # Mittelzone
        if taxable_income <= ESt_ZONE4_BIS:
            return Decimal("0.42")
        return Decimal("0.45")

    # =========================================================================
    # Fristen und Deadlines
    # =========================================================================

    def _get_tax_deadlines(
        self,
        tax_year: int,
    ) -> Tuple[List[TaxDeadline], List[TaxDeadline]]:
        """Ermittelt kommende und ueberfaellige Steuerfristen."""
        today = date.today()

        all_deadlines = [
            TaxDeadline(
                deadline_type=TaxDeadlineType.EINKOMMENSTEUER,
                title=f"Einkommensteuererklaerung {tax_year}",
                due_date=date(tax_year + 1, 7, 31),  # 31. Juli des Folgejahres
                description="Abgabe der Einkommensteuererklaerung",
                is_recurring=True,
                recurrence_pattern="yearly",
            ),
            TaxDeadline(
                deadline_type=TaxDeadlineType.FRISTVERLÄNGERUNG,
                title=f"Fristverlaengerung ESt {tax_year} (mit Steuerberater)",
                due_date=date(tax_year + 2, 2, 28),  # Ende Februar uebernachstes Jahr
                description="Verlaengerte Frist bei Steuerberater-Vertretung",
                is_recurring=True,
                recurrence_pattern="yearly",
            ),
        ]

        # Umsatzsteuer-Voranmeldungen (monatlich/quartalweise)
        for month in range(1, 13):
            vat_date = date(tax_year, month, 1) + timedelta(days=40)  # ~10. des Folgemonats
            if vat_date.day > 10:
                vat_date = vat_date.replace(day=10)

            all_deadlines.append(TaxDeadline(
                deadline_type=TaxDeadlineType.UMSATZSTEUER_VORANMELDUNG,
                title=f"USt-Voranmeldung {month:02d}/{tax_year}",
                due_date=vat_date,
                description=f"Umsatzsteuer-Voranmeldung fuer {month:02d}/{tax_year}",
                is_recurring=True,
                recurrence_pattern="monthly",
            ))

        # Grundsteuer (4 Raten)
        for quarter, due_day in [(1, 15), (2, 15), (3, 15), (4, 15)]:
            q_month = quarter * 3 - 1  # Feb, Mai, Aug, Nov
            all_deadlines.append(TaxDeadline(
                deadline_type=TaxDeadlineType.GRUNDSTEUER,
                title=f"Grundsteuer Q{quarter}/{tax_year}",
                due_date=date(tax_year, q_month, due_day),
                description=f"Grundsteuer-Rate {quarter}. Quartal",
                is_recurring=True,
                recurrence_pattern="quarterly",
            ))

        # Fristen kategorisieren
        upcoming: List[TaxDeadline] = []
        overdue: List[TaxDeadline] = []

        for deadline in all_deadlines:
            deadline.days_until_due = (deadline.due_date - today).days
            deadline.is_overdue = deadline.due_date < today

            if deadline.is_overdue:
                overdue.append(deadline)
            elif deadline.days_until_due <= 90:  # Naechste 90 Tage
                upcoming.append(deadline)

        # Sortieren nach Datum
        upcoming.sort(key=lambda d: d.due_date)
        overdue.sort(key=lambda d: d.due_date, reverse=True)

        return upcoming, overdue

    # =========================================================================
    # Optimierungsvorschlaege
    # =========================================================================

    def _generate_optimization_suggestions(
        self,
        summaries: List[TaxDeductionSummary],
        estimated_income: Optional[Decimal],
    ) -> List[str]:
        """Generiert Optimierungsvorschlaege."""
        suggestions: List[str] = []

        # Auslastung von Hoechstbetraegen pruefen
        for summary in summaries:
            if summary.max_deductible and summary.utilization_percent:
                if summary.utilization_percent < Decimal("50"):
                    suggestions.append(
                        f"{summary.category_name}: Nur {summary.utilization_percent}% des "
                        f"Hoechstbetrags genutzt. Potenzial: "
                        f"{summary.max_deductible - summary.total_deductible:.2f} EUR"
                    )

        # Werbungskosten vs. Pauschale
        wk_summary = next(
            (s for s in summaries if s.category == TaxCategory.WERBUNGSKOSTEN),
            None
        )
        if wk_summary:
            if wk_summary.total_deductible < WERBUNGSKOSTEN_PAUSCHALE * Decimal("0.8"):
                suggestions.append(
                    "Tipp: Sammeln Sie mehr Werbungskosten-Belege "
                    f"(aktuell unter 80% der Pauschale von {WERBUNGSKOSTEN_PAUSCHALE} EUR)."
                )
        else:
            suggestions.append(
                f"Keine Werbungskosten erfasst. "
                f"Sie koennen mindestens die Pauschale von {WERBUNGSKOSTEN_PAUSCHALE} EUR nutzen."
            )

        # Homeoffice-Pauschale hinweisen
        homeoffice = next(
            (s for s in summaries if s.category == TaxCategory.HOMEOFFICE),
            None
        )
        if not homeoffice:
            suggestions.append(
                f"Homeoffice-Pauschale: Bis zu {HOMEOFFICE_MAX_ABZUG} EUR/Jahr "
                "fuer Arbeiten von zu Hause absetzbar."
            )

        # Handwerkerleistungen
        handwerker = next(
            (s for s in summaries if s.category == TaxCategory.HANDWERKERLEISTUNGEN),
            None
        )
        if not handwerker:
            suggestions.append(
                "Handwerkerleistungen: Bis zu 1.200 EUR Steuerermassigung "
                "fuer Reparaturen und Renovierungen im Haushalt."
            )

        return suggestions[:5]  # Max 5 Vorschlaege

    def _identify_missing_deductions(
        self,
        summaries: List[TaxDeductionSummary],
    ) -> List[str]:
        """Identifiziert potenziell fehlende Abzugskategorien."""
        found_categories = {s.category for s in summaries}

        missing: List[str] = []

        common_categories = [
            (TaxCategory.WERBUNGSKOSTEN, "Werbungskosten (Fahrtkosten, Arbeitsmittel, Fortbildung)"),
            (TaxCategory.SONDERAUSGABEN, "Sonderausgaben (Versicherungen, Vorsorge)"),
            (TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN, "Haushaltsnahe Dienstleistungen"),
            (TaxCategory.HANDWERKERLEISTUNGEN, "Handwerkerleistungen"),
            (TaxCategory.SPENDEN, "Spenden und Mitgliedsbeitraege"),
        ]

        for category, description in common_categories:
            if category not in found_categories:
                missing.append(description)

        return missing

    def _calculate_optimization_rating(
        self,
        summaries: List[TaxDeductionSummary],
        missing_deductions: List[str],
    ) -> TaxRating:
        """Berechnet eine Gesamtbewertung der Steueroptimierung."""
        # Punkte vergeben
        points = 0
        max_points = 100

        # Anzahl genutzter Kategorien (max 30 Punkte)
        category_points = min(30, len(summaries) * 6)
        points += category_points

        # Auslastung von Hoechstbetraegen (max 40 Punkte)
        utilization_sum = Decimal("0")
        util_count = 0
        for summary in summaries:
            if summary.utilization_percent:
                utilization_sum += summary.utilization_percent
                util_count += 1

        if util_count > 0:
            avg_utilization = utilization_sum / util_count
            points += int(min(40, float(avg_utilization) * 0.4))

        # Weniger fehlende Kategorien = besser (max 30 Punkte)
        missing_penalty = len(missing_deductions) * 6
        points += max(0, 30 - missing_penalty)

        # Rating bestimmen
        if points >= 80:
            return TaxRating.OPTIMAL
        elif points >= 60:
            return TaxRating.GUT
        elif points >= 40:
            return TaxRating.VERBESSERBAR
        else:
            return TaxRating.OPTIMIERUNGSBEDARF

    # =========================================================================
    # DATEV-Export
    # =========================================================================

    def _check_datev_export_readiness(
        self,
        summaries: List[TaxDeductionSummary],
    ) -> Tuple[bool, Optional[str]]:
        """Prueft ob die Daten fuer DATEV-Export bereit sind."""
        if not summaries:
            return False, "Keine Abzuege erfasst"

        # Pruefen ob alle Items verifiziert sind
        unverified_count = 0
        for summary in summaries:
            for item in summary.items:
                if not item.is_verified:
                    unverified_count += 1

        if unverified_count > 0:
            return False, f"{unverified_count} Belege noch nicht verifiziert"

        return True, None

    async def generate_datev_export(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: int,
    ) -> Dict[str, Any]:
        """
        Generiert einen DATEV-kompatiblen Export.

        Format: DATEV-Buchungsstapel mit Kontierung nach SKR03/04.

        SECURITY: Keine persoenlichen Daten in der Export-Struktur!
        """
        TAX_OPTIMIZATION_CALCULATIONS.labels(calculation_type="datev_export").inc()

        result = await self.analyze_tax_optimization(db, space_id, tax_year)

        export_data = {
            "format_version": "DATEV-Export v1.0",
            "tax_year": tax_year,
            "export_date": utc_now().isoformat(),
            "total_deductible": str(result.total_deductible),
            "categories": [],
        }

        for summary in result.deduction_summaries:
            cat_export = {
                "category": summary.category.value,
                "category_name": summary.category_name,
                "total_gross": str(summary.total_gross),
                "total_deductible": str(summary.total_deductible),
                "item_count": len(summary.items),
                # SKR03 Konten-Empfehlung (vereinfacht)
                "suggested_accounts": self._get_skr03_accounts(summary.category),
            }
            export_data["categories"].append(cat_export)

        logger.info(
            "datev_export_generated",
            space_id=str(space_id),
            tax_year=tax_year,
            category_count=len(result.deduction_summaries),
        )

        return export_data

    def _get_skr03_accounts(self, category: TaxCategory) -> List[Dict[str, str]]:
        """Gibt SKR03-Kontenempfehlungen fuer eine Kategorie zurueck."""
        skr03_mapping = {
            TaxCategory.WERBUNGSKOSTEN: [
                {"konto": "4900", "bezeichnung": "Sonstige betriebliche Aufwendungen"},
            ],
            TaxCategory.SONDERAUSGABEN: [
                {"konto": "4130", "bezeichnung": "Gesetzl. Sozialversicherung AN-Anteil"},
            ],
            TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN: [
                {"konto": "4950", "bezeichnung": "Rechts- und Beratungskosten"},
            ],
            TaxCategory.HANDWERKERLEISTUNGEN: [
                {"konto": "4810", "bezeichnung": "Reparaturen und Instandhaltung"},
            ],
            TaxCategory.SPENDEN: [
                {"konto": "6810", "bezeichnung": "Spenden und Zuwendungen"},
            ],
        }
        return skr03_mapping.get(category, [])

    # =========================================================================
    # Abzugsfaehigkeits-Check
    # =========================================================================

    async def check_deductibility(
        self,
        document_text: str,
        document_type: Optional[str] = None,
        amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Prueft ob ein Dokument steuerlich absetzbar ist.

        Args:
            document_text: OCR-Text des Dokuments
            document_type: Dokumenttyp falls bekannt
            amount: Betrag falls bekannt

        Returns:
            Dict mit Abzugsfaehigkeits-Informationen
        """
        TAX_OPTIMIZATION_CALCULATIONS.labels(calculation_type="deductibility_check").inc()

        text_lower = document_text.lower()

        # Kategorie erkennen
        best_category: Optional[TaxCategory] = None
        best_score = 0
        matched_keywords: List[str] = []

        for category, keywords in TAX_DOCUMENT_KEYWORDS.items():
            matches = [kw for kw in keywords if kw in text_lower]
            if len(matches) > best_score:
                best_score = len(matches)
                best_category = category
                matched_keywords = matches

        if not best_category:
            return {
                "is_deductible": False,
                "confidence": 0.0,
                "reason": "Keine steuerlich relevanten Merkmale erkannt",
                "category": None,
                "recommendations": [
                    "Dokument scheint nicht steuerlich relevant zu sein.",
                    "Falls es sich um einen Beleg handelt, pruefen Sie die Kategorie manuell.",
                ],
            }

        # Abzugsfaehigkeit berechnen
        deductible_amount = Decimal("0")
        max_amount: Optional[Decimal] = None
        deduction_rules: List[str] = []

        if amount and amount > 0:
            if best_category == TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN:
                deductible_amount = min(amount * Decimal("0.2"), HAUSHALTSNAHE_MAX_ABZUG)
                max_amount = HAUSHALTSNAHE_MAX_ABZUG
                deduction_rules.append("20% der Aufwendungen, max. 4.000 EUR/Jahr")

            elif best_category == TaxCategory.HANDWERKERLEISTUNGEN:
                labor = amount * Decimal("0.6")  # Annahme: 60% Arbeitskosten
                deductible_amount = min(labor * Decimal("0.2"), HANDWERKER_MAX_ABZUG)
                max_amount = HANDWERKER_MAX_ABZUG
                deduction_rules.append("20% der Arbeitskosten, max. 1.200 EUR/Jahr")
                deduction_rules.append("Nur Lohnkosten absetzbar, keine Materialkosten")

            elif best_category == TaxCategory.WERBUNGSKOSTEN:
                deductible_amount = amount
                deduction_rules.append(f"Vollstaendig absetzbar ueber Pauschale ({WERBUNGSKOSTEN_PAUSCHALE} EUR)")

            elif best_category == TaxCategory.SONDERAUSGABEN:
                deductible_amount = amount
                deduction_rules.append("Im Rahmen der Sonderausgaben absetzbar")

            else:
                deductible_amount = amount

        confidence = min(1.0, best_score * 0.25)

        return {
            "is_deductible": True,
            "confidence": confidence,
            "category": best_category.value,
            "category_name": self._category_names.get(best_category, str(best_category)),
            "matched_keywords": matched_keywords,
            "amount": str(amount) if amount else None,
            "deductible_amount": str(deductible_amount) if amount else None,
            "max_deductible": str(max_amount) if max_amount else None,
            "deduction_rules": deduction_rules,
            "recommendations": [
                "Beleg aufbewahren fuer die Steuererklaerung",
                f"Kategorie: {self._category_names.get(best_category, '')}",
            ],
        }

    # =========================================================================
    # Steuer-Prognose (Tax Projection)
    # =========================================================================

    async def calculate_tax_projection(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: Optional[int] = None,
        gross_income: Optional[Decimal] = None,
        is_married: bool = False,
        number_of_children: int = 0,
        federal_state: str = "default",
        already_paid: Decimal = Decimal("0"),
    ) -> TaxProjection:
        """
        Berechnet eine vollstaendige Steuer-Prognose fuer ein Jahr.

        Args:
            db: Datenbank-Session
            space_id: ID des Privat-Space
            tax_year: Steuerjahr (Default: aktuelles Jahr)
            gross_income: Bruttoeinkommen (falls nicht aus Dokumenten bekannt)
            is_married: Verheiratet (Splittingtarif)
            number_of_children: Anzahl Kinder (fuer Freibetraege)
            federal_state: Bundesland (fuer Kirchensteuer)
            already_paid: Bereits gezahlte Vorauszahlungen

        Returns:
            TaxProjection mit vollstaendiger Prognose

        SECURITY: Niemals Betraege oder persoenliche Daten loggen!
        """
        import time
        start_time = time.time()

        TAX_OPTIMIZATION_CALCULATIONS.labels(calculation_type="tax_projection").inc()

        if tax_year is None:
            tax_year = datetime.now(timezone.utc).year

        # 1. Steueroptimierung analysieren
        optimization = await self.analyze_tax_optimization(
            db, space_id, tax_year, gross_income, is_married
        )

        # 2. Einkuenfte nach Art aufschluesseln
        income_from_employment = gross_income or Decimal("0")
        income_from_rental = await self._calculate_rental_income(db, space_id, tax_year)
        income_from_capital = await self._calculate_capital_income(db, space_id, tax_year)
        other_income = Decimal("0")

        total_income = (
            income_from_employment +
            income_from_rental +
            income_from_capital +
            other_income
        )

        # 3. Abzuege nach Kategorie extrahieren
        werbungskosten = Decimal("0")
        sonderausgaben = Decimal("0")
        aussergewoehnlich = Decimal("0")
        haushaltsnahe = Decimal("0")
        handwerker = Decimal("0")

        for summary in optimization.deduction_summaries:
            if summary.category == TaxCategory.WERBUNGSKOSTEN:
                werbungskosten = summary.total_deductible
            elif summary.category == TaxCategory.SONDERAUSGABEN:
                sonderausgaben = summary.total_deductible
            elif summary.category == TaxCategory.AUSSERGEWOEHNLICHE_BELASTUNGEN:
                aussergewoehnlich = summary.total_deductible
            elif summary.category == TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN:
                haushaltsnahe = summary.total_deductible
            elif summary.category == TaxCategory.HANDWERKERLEISTUNGEN:
                handwerker = summary.total_deductible

        # 4. Grundfreibetrag ermitteln
        grundfreibetrag = GRUNDFREIBETRAG_BY_YEAR.get(
            tax_year,
            GRUNDFREIBETRAG_BY_YEAR.get(2026, Decimal("12096"))
        )
        if is_married:
            grundfreibetrag = GRUNDFREIBETRAG_VERHEIRATET_BY_YEAR.get(
                tax_year,
                GRUNDFREIBETRAG_VERHEIRATET_BY_YEAR.get(2026, Decimal("24192"))
            )

        # 5. Kinderfreibetrag (9.540 EUR pro Kind in 2026)
        kinderfreibetrag = number_of_children * Decimal("9540")

        # 6. Zu versteuerndes Einkommen berechnen
        taxable_income = max(
            Decimal("0"),
            total_income
            - werbungskosten
            - sonderausgaben
            - grundfreibetrag
            - kinderfreibetrag
        )

        # 7. Einkommensteuer berechnen
        estimated_income_tax = self._calculate_income_tax(taxable_income, is_married)

        # 8. Solidaritaetszuschlag (nur bei hohem Einkommen)
        soli_freigrenze = (
            SOLI_FREIGRENZE_VERHEIRATET if is_married else SOLI_FREIGRENZE_SINGLE
        )
        solidarity_surcharge = Decimal("0")
        if estimated_income_tax > soli_freigrenze:
            # Milderungszone beachten
            soli_basis = estimated_income_tax - soli_freigrenze
            solidarity_surcharge = min(
                soli_basis * Decimal("0.119"),  # Milderung
                estimated_income_tax * SOLI_SATZ
            )

        # 9. Kirchensteuer
        kirchen_satz = KIRCHENSTEUER_SAETZE.get(
            federal_state.upper(),
            KIRCHENSTEUER_SAETZE["default"]
        )
        church_tax = estimated_income_tax * kirchen_satz

        # 10. Gesamtsteuer (vor haushaltsnahen Abzuegen)
        total_tax_before_reduction = estimated_income_tax + solidarity_surcharge + church_tax

        # 11. Steuerermassigungen abziehen (direkt von Steuer)
        total_tax = max(
            Decimal("0"),
            total_tax_before_reduction - haushaltsnahe - handwerker
        )

        # 12. Erstattung/Nachzahlung berechnen
        expected_refund = already_paid - total_tax

        # 13. Optimierungspotenzial ermitteln
        unused_allowances = optimization.missing_deductions
        optimization_potential = Decimal("0")

        # Ungenutztes Potenzial berechnen
        if haushaltsnahe < HAUSHALTSNAHE_MAX_ABZUG:
            optimization_potential += (HAUSHALTSNAHE_MAX_ABZUG - haushaltsnahe)
        if handwerker < HANDWERKER_MAX_ABZUG:
            optimization_potential += (HANDWERKER_MAX_ABZUG - handwerker)

        duration = time.time() - start_time
        TAX_OPTIMIZATION_DURATION.observe(duration)

        logger.info(
            "tax_projection_calculated",
            space_id=str(space_id),
            tax_year=tax_year,
            duration_seconds=round(duration, 3),
        )

        return TaxProjection(
            tax_year=tax_year,
            total_income=total_income,
            income_from_employment=income_from_employment,
            income_from_rental=income_from_rental,
            income_from_capital=income_from_capital,
            other_income=other_income,
            total_deductions=optimization.total_deductible,
            werbungskosten=werbungskosten,
            sonderausgaben=sonderausgaben,
            aussergewoehnliche_belastungen=aussergewoehnlich,
            haushaltsnahe_abzug=haushaltsnahe,
            handwerker_abzug=handwerker,
            taxable_income=taxable_income,
            estimated_income_tax=estimated_income_tax,
            solidarity_surcharge=solidarity_surcharge,
            church_tax=church_tax,
            total_tax=total_tax,
            already_paid=already_paid,
            expected_refund=expected_refund,
            optimization_potential=optimization_potential,
            unused_allowances=unused_allowances,
            is_married=is_married,
            number_of_children=number_of_children,
            federal_state=federal_state,
        )

    async def _calculate_rental_income(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: int,
    ) -> Decimal:
        """Berechnet Mieteinnahmen aus Immobilien."""
        from app.db.models import PrivatProperty, PrivatRentalIncome

        try:
            # Summe aller Mieteinnahmen im Steuerjahr
            year_start = date(tax_year, 1, 1)
            year_end = date(tax_year, 12, 31)

            result = await db.execute(
                select(func.coalesce(func.sum(PrivatRentalIncome.amount), 0))
                .join(PrivatProperty)
                .where(
                    PrivatProperty.space_id == space_id,
                    PrivatRentalIncome.payment_date >= year_start,
                    PrivatRentalIncome.payment_date <= year_end,
                )
            )
            return Decimal(str(result.scalar() or 0))
        except Exception:
            return Decimal("0")

    async def _calculate_capital_income(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: int,
    ) -> Decimal:
        """Berechnet Kapitalertraege (vereinfacht)."""
        # Hier koennten Dividenden, Zinsen etc. aus Investments summiert werden
        # Fuer MVP: Placeholder
        return Decimal("0")

    # =========================================================================
    # Was-waere-wenn Szenarien
    # =========================================================================

    async def calculate_what_if_scenario(
        self,
        db: AsyncSession,
        space_id: UUID,
        scenario: WhatIfScenario,
        base_projection: Optional[TaxProjection] = None,
    ) -> WhatIfScenario:
        """
        Berechnet ein Was-waere-wenn Szenario.

        Args:
            db: Datenbank-Session
            space_id: ID des Privat-Space
            scenario: Szenario-Parameter
            base_projection: Basis-Prognose (falls schon berechnet)

        Returns:
            WhatIfScenario mit Ergebnissen
        """
        TAX_OPTIMIZATION_CALCULATIONS.labels(calculation_type="what_if_scenario").inc()

        # Basis-Prognose holen falls nicht vorhanden
        if base_projection is None:
            base_projection = await self.calculate_tax_projection(db, space_id)

        # Modifizierte Werte berechnen
        modified_income = base_projection.total_income + scenario.additional_income
        modified_deductions = base_projection.total_deductions + scenario.additional_deductions

        # Familienstand aendern?
        is_married = base_projection.is_married
        if scenario.change_marital_status is not None:
            is_married = scenario.change_marital_status

        # Kinder hinzufuegen?
        children = base_projection.number_of_children + scenario.additional_children

        # Neue Steuer berechnen
        modified_projection = await self.calculate_tax_projection(
            db,
            space_id,
            tax_year=base_projection.tax_year,
            gross_income=modified_income,
            is_married=is_married,
            number_of_children=children,
            federal_state=base_projection.federal_state,
            already_paid=base_projection.already_paid,
        )

        # Ergebnis setzen
        scenario.tax_before = base_projection.total_tax
        scenario.tax_after = modified_projection.total_tax
        scenario.tax_difference = base_projection.total_tax - modified_projection.total_tax

        # Empfehlung generieren
        if scenario.tax_difference > 0:
            scenario.recommendation = (
                f"Dieses Szenario wuerde eine Ersparnis von "
                f"{scenario.tax_difference:.2f} EUR bringen."
            )
        elif scenario.tax_difference < 0:
            scenario.recommendation = (
                f"Dieses Szenario wuerde eine Mehrbelastung von "
                f"{abs(scenario.tax_difference):.2f} EUR bedeuten."
            )
        else:
            scenario.recommendation = "Keine Aenderung der Steuerbelastung."

        logger.info(
            "what_if_scenario_calculated",
            space_id=str(space_id),
            scenario_name=scenario.scenario_name,
        )

        return scenario

    async def calculate_common_scenarios(
        self,
        db: AsyncSession,
        space_id: UUID,
        base_projection: Optional[TaxProjection] = None,
    ) -> List[WhatIfScenario]:
        """
        Berechnet gaengige Was-waere-wenn Szenarien.

        Liefert Empfehlungen wie:
        - "Wenn Sie heiraten wuerden..."
        - "Mit einem Kind mehr..."
        - "Bei 5.000 EUR mehr Werbungskosten..."
        """
        if base_projection is None:
            base_projection = await self.calculate_tax_projection(db, space_id)

        scenarios = []

        # Szenario 1: Heirat (falls ledig)
        if not base_projection.is_married:
            marriage_scenario = WhatIfScenario(
                scenario_name="Heirat",
                description="Steuerliche Auswirkung bei Eheschliessung (Splittingtarif)",
                change_marital_status=True,
            )
            scenarios.append(
                await self.calculate_what_if_scenario(db, space_id, marriage_scenario, base_projection)
            )

        # Szenario 2: Zusaetzliche Werbungskosten
        werbungskosten_scenario = WhatIfScenario(
            scenario_name="Mehr Werbungskosten",
            description="Bei 2.000 EUR zusaetzlichen Werbungskosten",
            additional_deductions=Decimal("2000"),
        )
        scenarios.append(
            await self.calculate_what_if_scenario(db, space_id, werbungskosten_scenario, base_projection)
        )

        # Szenario 3: Haushaltsnahe Dienstleistungen maximal nutzen
        if base_projection.haushaltsnahe_abzug < HAUSHALTSNAHE_MAX_ABZUG:
            potential = HAUSHALTSNAHE_MAX_ABZUG - base_projection.haushaltsnahe_abzug
            haushaltsnahe_scenario = WhatIfScenario(
                scenario_name="Haushaltsnahe DL maximieren",
                description=f"Bei voller Ausschoepfung der haushaltsnahen Dienstleistungen (+{potential:.2f} EUR)",
                additional_deductions=potential,
            )
            scenarios.append(
                await self.calculate_what_if_scenario(db, space_id, haushaltsnahe_scenario, base_projection)
            )

        # Szenario 4: Handwerkerleistungen maximal nutzen
        if base_projection.handwerker_abzug < HANDWERKER_MAX_ABZUG:
            potential = HANDWERKER_MAX_ABZUG - base_projection.handwerker_abzug
            handwerker_scenario = WhatIfScenario(
                scenario_name="Handwerkerleistungen maximieren",
                description=f"Bei voller Ausschoepfung der Handwerkerleistungen (+{potential:.2f} EUR)",
                additional_deductions=potential,
            )
            scenarios.append(
                await self.calculate_what_if_scenario(db, space_id, handwerker_scenario, base_projection)
            )

        # Szenario 5: Gehaltserhoehung
        raise_scenario = WhatIfScenario(
            scenario_name="Gehaltserhoehung 10%",
            description="Auswirkung einer 10% Gehaltserhoehung",
            additional_income=base_projection.income_from_employment * Decimal("0.10"),
        )
        scenarios.append(
            await self.calculate_what_if_scenario(db, space_id, raise_scenario, base_projection)
        )

        return scenarios

    # =========================================================================
    # ELSTER Export
    # =========================================================================

    async def prepare_elster_export(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: int,
        taxpayer_info: Optional[Dict[str, Any]] = None,
    ) -> ElsterExportData:
        """
        Bereitet Daten fuer ELSTER-Export vor.

        Erzeugt strukturierte Daten die fuer:
        - Anlage N (Arbeitnehmereinkuenfte)
        - Anlage V (Vermietung und Verpachtung)
        - Anlage Vorsorge (Vorsorgeaufwendungen)
        - Haushaltsnahe Dienstleistungen

        validiert und exportiert werden koennen.

        SECURITY: Steuernummer wird NICHT gespeichert!

        Args:
            db: Datenbank-Session
            space_id: ID des Privat-Space
            tax_year: Steuerjahr
            taxpayer_info: Optionale Steuerzahler-Infos (Name, Adresse)

        Returns:
            ElsterExportData mit allen Feldwerten
        """
        TAX_OPTIMIZATION_CALCULATIONS.labels(calculation_type="elster_export").inc()

        # 1. Steueroptimierung analysieren
        optimization = await self.analyze_tax_optimization(db, space_id, tax_year)

        # 2. Relevante Anlagen ermitteln
        anlagen: Dict[ElsterAnlage, bool] = {
            ElsterAnlage.MANTELBOGEN: True,  # Immer erforderlich
            ElsterAnlage.ANLAGE_N: False,
            ElsterAnlage.ANLAGE_V: False,
            ElsterAnlage.ANLAGE_VORSORGE: False,
            ElsterAnlage.ANLAGE_HAUSHALTSNAHE: False,
        }

        # 3. Anlage N Felder (Arbeitnehmer)
        anlage_n: Dict[str, Any] = {}
        wk_summary = next(
            (s for s in optimization.deduction_summaries if s.category == TaxCategory.WERBUNGSKOSTEN),
            None
        )
        if wk_summary:
            anlagen[ElsterAnlage.ANLAGE_N] = True
            anlage_n["werbungskosten_gesamt"] = str(wk_summary.total_deductible)

            # Einzelne Positionen aufschluesseln
            for item in wk_summary.items:
                if "fahrt" in item.description.lower() or "pendler" in item.description.lower():
                    anlage_n.setdefault("fahrtkosten", Decimal("0"))
                    anlage_n["fahrtkosten"] += item.deductible_amount
                elif "arbeitsmittel" in item.description.lower():
                    anlage_n.setdefault("arbeitsmittel", Decimal("0"))
                    anlage_n["arbeitsmittel"] += item.deductible_amount
                elif "fortbildung" in item.description.lower():
                    anlage_n.setdefault("fortbildungskosten", Decimal("0"))
                    anlage_n["fortbildungskosten"] += item.deductible_amount
                elif "homeoffice" in item.description.lower():
                    anlage_n.setdefault("homeoffice_pauschale", Decimal("0"))
                    anlage_n["homeoffice_pauschale"] += item.deductible_amount

        # 4. Anlage V Felder (Vermietung)
        anlage_v: Dict[str, Any] = {}
        rental_income = await self._calculate_rental_income(db, space_id, tax_year)
        if rental_income > 0:
            anlagen[ElsterAnlage.ANLAGE_V] = True
            anlage_v["mieteinnahmen"] = str(rental_income)

            # AfA fuer vermietete Immobilien
            afa_items = await self._collect_property_deductions(db, space_id, tax_year)
            total_afa = sum(item.deductible_amount for item in afa_items)
            if total_afa > 0:
                anlage_v["afa_gebaeude"] = str(total_afa)

        # 5. Anlage Vorsorge Felder
        anlage_vorsorge: Dict[str, Any] = {}
        sonderausgaben_summary = next(
            (s for s in optimization.deduction_summaries if s.category == TaxCategory.SONDERAUSGABEN),
            None
        )
        if sonderausgaben_summary and sonderausgaben_summary.total_deductible > 0:
            anlagen[ElsterAnlage.ANLAGE_VORSORGE] = True
            anlage_vorsorge["vorsorgeaufwendungen_gesamt"] = str(sonderausgaben_summary.total_deductible)

            # Nach Versicherungstyp aufschluesseln
            for item in sonderausgaben_summary.items:
                desc_lower = item.description.lower()
                if "kranken" in desc_lower or "pflege" in desc_lower:
                    anlage_vorsorge.setdefault("kranken_pflege", Decimal("0"))
                    anlage_vorsorge["kranken_pflege"] += item.deductible_amount
                elif "riester" in desc_lower:
                    anlage_vorsorge.setdefault("riester", Decimal("0"))
                    anlage_vorsorge["riester"] += item.deductible_amount
                elif "ruerup" in desc_lower or "basis" in desc_lower:
                    anlage_vorsorge.setdefault("ruerup", Decimal("0"))
                    anlage_vorsorge["ruerup"] += item.deductible_amount

        # 6. Haushaltsnahe Dienstleistungen
        anlage_haushaltsnahe: Dict[str, Any] = {}
        haushaltsnahe_summary = next(
            (s for s in optimization.deduction_summaries if s.category == TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN),
            None
        )
        handwerker_summary = next(
            (s for s in optimization.deduction_summaries if s.category == TaxCategory.HANDWERKERLEISTUNGEN),
            None
        )

        if haushaltsnahe_summary or handwerker_summary:
            anlagen[ElsterAnlage.ANLAGE_HAUSHALTSNAHE] = True
            if haushaltsnahe_summary:
                anlage_haushaltsnahe["haushaltsnahe_summe"] = str(haushaltsnahe_summary.total_deductible)
            if handwerker_summary:
                anlage_haushaltsnahe["handwerker_summe"] = str(handwerker_summary.total_deductible)

        # 7. Validierung
        missing_fields: List[str] = []
        validation_warnings: List[str] = []

        # Pflichtfelder pruefen
        if anlagen[ElsterAnlage.ANLAGE_N] and "werbungskosten_gesamt" not in anlage_n:
            missing_fields.append("Anlage N: Werbungskosten-Summe fehlt")

        if anlagen[ElsterAnlage.ANLAGE_V] and "mieteinnahmen" not in anlage_v:
            missing_fields.append("Anlage V: Mieteinnahmen fehlen")

        # Warnungen generieren
        if optimization.optimization_rating in (TaxRating.VERBESSERBAR, TaxRating.OPTIMIERUNGSBEDARF):
            validation_warnings.append(
                "Ihre Steuerabzuege sind moeglicherweise nicht optimal. "
                "Pruefen Sie die Optimierungsvorschlaege."
            )

        unverified_count = sum(
            1 for s in optimization.deduction_summaries
            for item in s.items if not item.is_verified
        )
        if unverified_count > 0:
            validation_warnings.append(
                f"{unverified_count} Belege sind noch nicht verifiziert. "
                "Bitte pruefen und bestaetigen Sie diese."
            )

        is_complete = len(missing_fields) == 0

        logger.info(
            "elster_export_prepared",
            space_id=str(space_id),
            tax_year=tax_year,
            anlagen_count=sum(1 for v in anlagen.values() if v),
            is_complete=is_complete,
        )

        return ElsterExportData(
            tax_year=tax_year,
            steuernummer=None,  # SECURITY: Nicht speichern
            anlagen=anlagen,
            anlage_n_fields=anlage_n,
            anlage_v_fields=anlage_v,
            anlage_vorsorge_fields=anlage_vorsorge,
            anlage_haushaltsnahe_fields=anlage_haushaltsnahe,
            is_complete=is_complete,
            missing_fields=missing_fields,
            validation_warnings=validation_warnings,
        )

    def generate_elster_xml(
        self,
        export_data: ElsterExportData,
        taxpayer_info: Dict[str, Any],
    ) -> str:
        """
        Generiert ELSTER-kompatibles XML.

        HINWEIS: Dies ist ein vereinfachtes Format.
        Fuer echte ELSTER-Uebertragung ist die offizielle
        ERiC-Bibliothek erforderlich.

        Args:
            export_data: Vorbereitete Export-Daten
            taxpayer_info: Steuerzahler-Infos (Name, Steuernummer)

        Returns:
            XML-String fuer ELSTER-Upload
        """
        TAX_OPTIMIZATION_CALCULATIONS.labels(calculation_type="elster_xml").inc()

        # XML-Header
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<Elster xmlns="http://www.elster.de/elsterxml/schema/v11">',
            f'  <TransferHeader>',
            f'    <Verfahren>ElsterEinkommensteuer</Verfahren>',
            f'    <DatenArt>ESt</DatenArt>',
            f'    <Vorgang>send-Auth</Vorgang>',
            f'    <ErstellungsDatum>{export_data.generated_at.strftime("%Y-%m-%dT%H:%M:%S")}</ErstellungsDatum>',
            f'  </TransferHeader>',
            f'  <DatenTeil>',
            f'    <Nutzdatenblock>',
            f'      <Nutzdaten>',
            f'        <Steuererklarung>',
            f'          <Jahr>{export_data.tax_year}</Jahr>',
        ]

        # Mantelbogen (Basis-Daten)
        if taxpayer_info:
            xml_parts.extend([
                f'          <Mantelbogen>',
                f'            <Name>{taxpayer_info.get("name", "")}</Name>',
                f'            <Steuernummer>{taxpayer_info.get("steuernummer", "")}</Steuernummer>',
                f'          </Mantelbogen>',
            ])

        # Anlage N
        if export_data.anlagen.get(ElsterAnlage.ANLAGE_N) and export_data.anlage_n_fields:
            xml_parts.append('          <AnlageN>')
            for key, value in export_data.anlage_n_fields.items():
                xml_parts.append(f'            <{key}>{value}</{key}>')
            xml_parts.append('          </AnlageN>')

        # Anlage V
        if export_data.anlagen.get(ElsterAnlage.ANLAGE_V) and export_data.anlage_v_fields:
            xml_parts.append('          <AnlageV>')
            for key, value in export_data.anlage_v_fields.items():
                xml_parts.append(f'            <{key}>{value}</{key}>')
            xml_parts.append('          </AnlageV>')

        # Anlage Vorsorge
        if export_data.anlagen.get(ElsterAnlage.ANLAGE_VORSORGE) and export_data.anlage_vorsorge_fields:
            xml_parts.append('          <AnlageVorsorge>')
            for key, value in export_data.anlage_vorsorge_fields.items():
                xml_parts.append(f'            <{key}>{value}</{key}>')
            xml_parts.append('          </AnlageVorsorge>')

        # Haushaltsnahe Dienstleistungen
        if export_data.anlagen.get(ElsterAnlage.ANLAGE_HAUSHALTSNAHE) and export_data.anlage_haushaltsnahe_fields:
            xml_parts.append('          <HaushaltsnaheDienstleistungen>')
            for key, value in export_data.anlage_haushaltsnahe_fields.items():
                xml_parts.append(f'            <{key}>{value}</{key}>')
            xml_parts.append('          </HaushaltsnaheDienstleistungen>')

        # XML-Footer
        xml_parts.extend([
            f'        </Steuererklarung>',
            f'      </Nutzdaten>',
            f'    </Nutzdatenblock>',
            f'  </DatenTeil>',
            f'</Elster>',
        ])

        return '\n'.join(xml_parts)

    # =========================================================================
    # Dokument-Analyse
    # =========================================================================

    async def analyze_document_for_tax(
        self,
        db: AsyncSession,
        document_id: UUID,
        space_id: UUID,
        tax_year: Optional[int] = None,
    ) -> DocumentTaxAnalysis:
        """
        Analysiert ein einzelnes Dokument auf steuerliche Relevanz.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            space_id: Space-ID
            tax_year: Optionales Steuerjahr

        Returns:
            DocumentTaxAnalysis mit Kategorisierung und Empfehlungen
        """
        from app.db.models import PrivatDocument

        TAX_OPTIMIZATION_CALCULATIONS.labels(calculation_type="document_analysis").inc()

        if tax_year is None:
            tax_year = datetime.now(timezone.utc).year

        # Dokument laden
        result = await db.execute(
            select(PrivatDocument)
            .where(
                PrivatDocument.id == document_id,
                PrivatDocument.space_id == space_id,
                PrivatDocument.deleted_at.is_(None),
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise ValueError(f"Dokument nicht gefunden: {document_id}")

        # Klassifizieren
        category, confidence = self._classify_document_tax_category(doc)

        if not category:
            category = TaxCategory.WERBUNGSKOSTEN  # Default
            confidence = Decimal("0.1")

        # Betrag extrahieren
        amount = self._extract_amount_from_document(doc) or Decimal("0")
        deductible = self._calculate_deductible_amount(category, amount)

        # Grenzsteuersatz schaetzen (vereinfacht 35%)
        marginal_rate = Decimal("0.35")
        potential_savings = deductible * marginal_rate

        # ELSTER-Zuordnung ermitteln
        elster_anlage, elster_field = self._get_elster_mapping(category)

        # Empfehlungen generieren
        suggestions: List[str] = []
        missing_info: List[str] = []

        if amount == 0:
            missing_info.append("Betrag konnte nicht erkannt werden - bitte manuell eingeben")

        if confidence < Decimal("0.7"):
            suggestions.append(
                f"Die Kategorie '{self._category_names.get(category, '')}' wurde mit "
                f"niedriger Konfidenz ({confidence:.0%}) erkannt. Bitte pruefen."
            )

        if category == TaxCategory.HANDWERKERLEISTUNGEN:
            suggestions.append(
                "Bei Handwerkerleistungen sind nur Lohnkosten absetzbar, "
                "keine Materialkosten. Fordern Sie eine aufgeschluesselte Rechnung an."
            )

        if category == TaxCategory.WERBUNGSKOSTEN and deductible < WERBUNGSKOSTEN_PAUSCHALE:
            suggestions.append(
                f"Sammeln Sie mehr Belege! Aktuell ({deductible:.2f} EUR) unter "
                f"der Pauschale von {WERBUNGSKOSTEN_PAUSCHALE} EUR."
            )

        return DocumentTaxAnalysis(
            document_id=document_id,
            document_name=doc.name or doc.title or "Dokument",
            category=category,
            category_name=self._category_names.get(category, str(category)),
            confidence=confidence,
            gross_amount=amount,
            deductible_amount=deductible,
            potential_savings=potential_savings,
            elster_anlage=elster_anlage,
            elster_field=elster_field,
            suggestions=suggestions,
            missing_info=missing_info,
        )

    def _get_elster_mapping(
        self,
        category: TaxCategory,
    ) -> Tuple[ElsterAnlage, str]:
        """Ermittelt die ELSTER-Anlage und Kennzahl fuer eine Kategorie."""
        mapping = {
            TaxCategory.WERBUNGSKOSTEN: (ElsterAnlage.ANLAGE_N, ElsterFieldMapping.WERBUNGSKOSTEN_GESAMT.value),
            TaxCategory.SONDERAUSGABEN: (ElsterAnlage.ANLAGE_VORSORGE, "vorsorgeaufwendungen"),
            TaxCategory.AUSSERGEWOEHNLICHE_BELASTUNGEN: (ElsterAnlage.MANTELBOGEN, "aussergewoehnliche_belastungen"),
            TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN: (ElsterAnlage.ANLAGE_HAUSHALTSNAHE, ElsterFieldMapping.HAUSHALTSNAHE_SUMME.value),
            TaxCategory.HANDWERKERLEISTUNGEN: (ElsterAnlage.ANLAGE_HAUSHALTSNAHE, ElsterFieldMapping.HANDWERKERLEISTUNGEN_SUMME.value),
            TaxCategory.HOMEOFFICE: (ElsterAnlage.ANLAGE_N, ElsterFieldMapping.HOMEOFFICE_PAUSCHALE.value),
            TaxCategory.KINDERBETREUUNG: (ElsterAnlage.ANLAGE_KIND, ElsterFieldMapping.KINDERBETREUUNG.value),
            TaxCategory.SPENDEN: (ElsterAnlage.MANTELBOGEN, ElsterFieldMapping.SPENDEN_INLAND.value),
            TaxCategory.KIRCHENSTEUER: (ElsterAnlage.MANTELBOGEN, ElsterFieldMapping.KIRCHENSTEUER.value),
            TaxCategory.DOPPELTE_HAUSHALTSFUEHRUNG: (ElsterAnlage.ANLAGE_N, "doppelte_haushaltsfuehrung"),
        }
        return mapping.get(category, (ElsterAnlage.MANTELBOGEN, "sonstige"))

    # =========================================================================
    # Vorauszahlungs-Tracking
    # =========================================================================

    def get_advance_payment_schedule(
        self,
        tax_year: int,
        quarterly_amount: Decimal,
    ) -> List[TaxAdvancedPayment]:
        """
        Erstellt einen Vorauszahlungs-Plan fuer ein Steuerjahr.

        Args:
            tax_year: Steuerjahr
            quarterly_amount: Vierteljahresbetrag

        Returns:
            Liste der Vorauszahlungstermine
        """
        today = date.today()
        payments: List[TaxAdvancedPayment] = []

        for quarter, (month, day) in enumerate(VORAUSZAHLUNGSTERMINE, 1):
            due_date = date(tax_year, month, day)
            days_until = (due_date - today).days

            payments.append(TaxAdvancedPayment(
                payment_id=None,
                tax_year=tax_year,
                quarter=quarter,
                due_date=due_date,
                amount_due=quarterly_amount,
                amount_paid=Decimal("0"),
                payment_date=None,
                is_paid=False,
                is_overdue=due_date < today,
                days_until_due=days_until,
            ))

        return payments

    # =========================================================================
    # AfA-Berechnung (Abschreibungen)
    # =========================================================================

    async def calculate_afa_for_properties(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: int,
    ) -> List[AfACalculation]:
        """
        Berechnet AfA fuer alle vermieteten Immobilien.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            tax_year: Steuerjahr

        Returns:
            Liste der AfA-Berechnungen
        """
        from app.db.models import PrivatProperty

        result = await db.execute(
            select(PrivatProperty)
            .where(
                PrivatProperty.space_id == space_id,
                PrivatProperty.is_rented == True,
                PrivatProperty.deleted_at.is_(None),
            )
        )
        properties = result.scalars().all()

        calculations: List[AfACalculation] = []

        for prop in properties:
            if not prop.purchase_price or not prop.purchase_date:
                continue

            # AfA-Satz ermitteln
            purchase_year = prop.purchase_date.year if isinstance(prop.purchase_date, date) else prop.purchase_date

            if purchase_year >= 2023:
                afa_rate = AFA_SAETZE_GEBAEUDE["neubau_ab_2023"]
                useful_life = 34  # 33 1/3 Jahre
            elif purchase_year >= 1925:
                afa_rate = AFA_SAETZE_GEBAEUDE["neubau_1925_2022"]
                useful_life = 50
            else:
                afa_rate = AFA_SAETZE_GEBAEUDE["altbau_vor_1925"]
                useful_life = 40

            # Jaehrliche AfA
            annual_depreciation = prop.purchase_price * afa_rate

            # Bisherige Abschreibung berechnen
            years_owned = tax_year - purchase_year
            accumulated = annual_depreciation * min(years_owned, useful_life)
            remaining = max(Decimal("0"), prop.purchase_price - accumulated)
            years_remaining = max(0, useful_life - years_owned)

            calculations.append(AfACalculation(
                asset_id=prop.id,
                asset_name=prop.name or f"Immobilie {prop.street} {prop.street_number}",
                asset_type="gebaeude",
                purchase_date=prop.purchase_date if isinstance(prop.purchase_date, date) else date(purchase_year, 1, 1),
                purchase_price=prop.purchase_price,
                useful_life_years=useful_life,
                afa_rate=afa_rate,
                annual_depreciation=annual_depreciation,
                accumulated_depreciation=accumulated,
                remaining_book_value=remaining,
                years_remaining=years_remaining,
                elster_anlage=ElsterAnlage.ANLAGE_V,
                elster_field=ElsterFieldMapping.AFA_GEBAEUDE.value,
            ))

        return calculations

    # =========================================================================
    # Optimierungsvorschlaege (erweitert)
    # =========================================================================

    async def get_personalized_suggestions(
        self,
        db: AsyncSession,
        space_id: UUID,
        tax_year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generiert personalisierte Steuer-Optimierungsvorschlaege.

        Analysiert die vorhandenen Daten und generiert spezifische
        Empfehlungen mit geschaetztem Sparpotenzial.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            tax_year: Optionales Steuerjahr

        Returns:
            Liste von Optimierungsvorschlaegen mit Sparpotenzial
        """
        if tax_year is None:
            tax_year = datetime.now(timezone.utc).year

        optimization = await self.analyze_tax_optimization(db, space_id, tax_year)
        projection = await self.calculate_tax_projection(db, space_id, tax_year)

        suggestions: List[Dict[str, Any]] = []

        # 1. Werbungskosten unter Pauschale?
        wk_summary = next(
            (s for s in optimization.deduction_summaries if s.category == TaxCategory.WERBUNGSKOSTEN),
            None
        )
        if wk_summary:
            if wk_summary.total_deductible < WERBUNGSKOSTEN_PAUSCHALE:
                gap = WERBUNGSKOSTEN_PAUSCHALE - wk_summary.total_deductible
                suggestions.append({
                    "title": "Werbungskosten optimieren",
                    "description": (
                        f"Ihre Werbungskosten ({wk_summary.total_deductible:.2f} EUR) "
                        f"liegen unter der Pauschale ({WERBUNGSKOSTEN_PAUSCHALE} EUR). "
                        "Sammeln Sie mehr Belege!"
                    ),
                    "potential_savings": gap * projection.estimated_income_tax / projection.taxable_income if projection.taxable_income > 0 else Decimal("0"),
                    "priority": "hoch",
                    "category": "werbungskosten",
                    "actions": [
                        "Homeoffice-Tage erfassen",
                        "Fahrtkosten zur Arbeit dokumentieren",
                        "Arbeitsmittel (Laptop, Buero) absetzen",
                        "Fortbildungskosten sammeln",
                    ],
                })

        # 2. Haushaltsnahe Dienstleistungen nicht ausgeschoepft?
        if projection.haushaltsnahe_abzug < HAUSHALTSNAHE_MAX_ABZUG:
            unused = HAUSHALTSNAHE_MAX_ABZUG - projection.haushaltsnahe_abzug
            suggestions.append({
                "title": "Haushaltsnahe Dienstleistungen nutzen",
                "description": (
                    f"Sie koennten noch {unused:.2f} EUR Steuerermassigung erhalten. "
                    "20% der Aufwendungen (max. 4.000 EUR) sind direkt absetzbar!"
                ),
                "potential_savings": unused,
                "priority": "mittel",
                "category": "haushaltsnahe",
                "actions": [
                    "Putzhilfe/Haushaltshilfe beauftragen",
                    "Gaertner-Rechnungen sammeln",
                    "Pflegedienstleistungen abrechnen",
                ],
            })

        # 3. Handwerkerleistungen nicht ausgeschoepft?
        if projection.handwerker_abzug < HANDWERKER_MAX_ABZUG:
            unused = HANDWERKER_MAX_ABZUG - projection.handwerker_abzug
            suggestions.append({
                "title": "Handwerkerleistungen nutzen",
                "description": (
                    f"Sie koennten noch {unused:.2f} EUR Steuerermassigung erhalten. "
                    "20% der Lohnkosten (max. 1.200 EUR) sind direkt absetzbar!"
                ),
                "potential_savings": unused,
                "priority": "mittel",
                "category": "handwerker",
                "actions": [
                    "Renovierungsarbeiten planen",
                    "Wartung von Heizung/Sanitaer durchfuehren lassen",
                    "Rechnungen mit Lohnkostenausweis anfordern",
                ],
            })

        # 4. Spenden-Potenzial
        spenden_summary = next(
            (s for s in optimization.deduction_summaries if s.category == TaxCategory.SPENDEN),
            None
        )
        if not spenden_summary or spenden_summary.total_deductible < Decimal("50"):
            suggestions.append({
                "title": "Spenden als Sonderausgaben",
                "description": (
                    "Spenden an gemeinnuetzige Organisationen sind als "
                    "Sonderausgaben absetzbar (bis 20% des Einkommens)."
                ),
                "potential_savings": None,  # Variabel
                "priority": "niedrig",
                "category": "spenden",
                "actions": [
                    "Spendenquittungen sammeln",
                    "Mitgliedsbeitraege dokumentieren",
                ],
            })

        # Sortieren nach Prioritaet
        priority_order = {"hoch": 0, "mittel": 1, "niedrig": 2}
        suggestions.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return suggestions


# =============================================================================
# Singleton-Instanz
# =============================================================================

def get_tax_optimization_service() -> TaxOptimizationService:
    """Gibt die Singleton-Instanz des Tax Optimization Service zurueck."""
    return TaxOptimizationService()

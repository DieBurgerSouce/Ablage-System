# -*- coding: utf-8 -*-
"""
TaxOptimizationService - Steueroptimierung fuer das Privat-Modul.

Berechnet automatisch Steuerabzuege und Optimierungsmoeglichkeiten basierend auf:
1. Werbungskosten (berufsbedingte Aufwendungen)
2. Sonderausgaben (Versicherungen, Vorsorge, Spenden)
3. Aussergewoehnliche Belastungen (Krankheit, Behinderung)
4. Haushaltsnahe Dienstleistungen (20% bis max. 4.000 EUR)
5. Handwerkerleistungen (20% bis max. 1.200 EUR)

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
SECURITY: NIEMALS persoenliche Finanzdaten loggen!
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
# Steuerliche Grenzwerte (2026)
# =============================================================================

# Werbungskosten-Pauschale (Arbeitnehmer)
WERBUNGSKOSTEN_PAUSCHALE = Decimal("1230")

# Sonderausgaben-Pauschale
SONDERAUSGABEN_PAUSCHALE_SINGLE = Decimal("36")
SONDERAUSGABEN_PAUSCHALE_VERHEIRATET = Decimal("72")

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

# Pendlerpauschale
PENDLER_PAUSCHALE_PRO_KM_BIS_20 = Decimal("0.30")  # Erste 20 km
PENDLER_PAUSCHALE_PRO_KM_AB_21 = Decimal("0.38")  # Ab 21 km

# Kinderbetreuungskosten
KINDERBETREUUNG_MAX = Decimal("6000")  # Pro Kind
KINDERBETREUUNG_ABZUG_PROZENT = Decimal("0.6667")  # 2/3

# Spenden-Hoechstgrenzen
SPENDEN_MAX_PROZENT_EINKOMMEN = Decimal("0.20")  # 20% des Gesamtbetrags

# Grundfreibetrag (2026 geschaetzt)
GRUNDFREIBETRAG_2026 = Decimal("12096")  # Single
GRUNDFREIBETRAG_VERHEIRATET_2026 = Decimal("24192")

# Einkommensteuer-Tarif 2026 (Zone 2-4)
ESt_ZONE2_BIS = Decimal("17442")
ESt_ZONE3_BIS = Decimal("68479")
ESt_ZONE4_BIS = Decimal("277825")
ESt_SPITZENSTEUERSATZ = Decimal("0.45")

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


# =============================================================================
# Singleton-Instanz
# =============================================================================

def get_tax_optimization_service() -> TaxOptimizationService:
    """Gibt die Singleton-Instanz des Tax Optimization Service zurueck."""
    return TaxOptimizationService()

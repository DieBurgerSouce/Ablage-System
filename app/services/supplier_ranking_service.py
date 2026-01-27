# -*- coding: utf-8 -*-
"""
Supplier Ranking Service.

Bewertet Lieferanten basierend auf:
- Puenktlichkeit (Liefertreue)
- Preis-Leistungs-Verhaeltnis
- Zuverlaessigkeit (Reklamationsquote, Qualitaet)
- Kommunikation
- Zahlungsbedingungen

Die Bewertung erfolgt automatisch aus historischen Daten
und kann manuell ergaenzt werden.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_, desc, asc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
    EntityType,
)
from app.core.datetime_utils import utc_now


logger = structlog.get_logger(__name__)


class SupplierRankingCategory(str, Enum):
    """Ranking-Kategorien fuer Lieferanten."""
    PUNCTUALITY = "punctuality"        # Puenktlichkeit
    PRICE = "price"                    # Preis-Leistung
    RELIABILITY = "reliability"        # Zuverlaessigkeit
    COMMUNICATION = "communication"    # Kommunikation
    PAYMENT_TERMS = "payment_terms"    # Zahlungsbedingungen


class SupplierTier(str, Enum):
    """Tier-Einstufung basierend auf Gesamtscore."""
    PLATINUM = "platinum"  # 90-100: Top-Lieferant
    GOLD = "gold"          # 75-89: Bevorzugter Lieferant
    SILVER = "silver"      # 60-74: Standard-Lieferant
    BRONZE = "bronze"      # 40-59: Beobachtung
    CRITICAL = "critical"  # 0-39: Kritisch


@dataclass
class SupplierScore:
    """Einzelbewertung einer Kategorie."""
    category: SupplierRankingCategory
    score: float  # 0-100
    weight: float  # Gewichtung in Gesamtscore
    data_points: int  # Anzahl der Datenpunkte
    trend: str  # "up", "down", "stable"
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SupplierRanking:
    """Gesamtbewertung eines Lieferanten."""
    entity_id: UUID
    entity_name: str

    # Gesamtscore
    overall_score: float  # 0-100
    tier: SupplierTier

    # Einzelkategorien
    category_scores: List[SupplierScore]

    # Statistiken
    total_orders: int
    total_volume: Decimal
    first_order_date: Optional[date]
    last_order_date: Optional[date]
    avg_order_value: Decimal

    # Trend
    score_trend: str  # "improving", "declining", "stable"
    previous_score: Optional[float]

    # Empfehlungen
    recommendations: List[str] = field(default_factory=list)

    # Zeitstempel
    calculated_at: datetime = field(default_factory=utc_now)


@dataclass
class SupplierRankingReport:
    """Report ueber alle Lieferanten-Rankings."""
    company_id: UUID

    # Uebersicht
    total_suppliers: int
    ranked_suppliers: int

    # Tier-Verteilung
    tier_distribution: Dict[str, int]

    # Top/Bottom Lieferanten
    top_suppliers: List[SupplierRanking]
    critical_suppliers: List[SupplierRanking]
    improving_suppliers: List[SupplierRanking]
    declining_suppliers: List[SupplierRanking]

    # Durchschnittswerte
    avg_overall_score: float
    avg_punctuality: float
    avg_reliability: float

    # Zeitraum
    analysis_period_start: date
    analysis_period_end: date

    generated_at: datetime = field(default_factory=utc_now)


class SupplierRankingService:
    """
    Service zur Bewertung von Lieferanten.

    Bewertet Lieferanten automatisch basierend auf:
    - Liefertreue (Dokumente mit Liefertermin)
    - Rechnungsgenauigkeit (Abweichungen Bestellung vs Rechnung)
    - Zahlungsbedingungen (Skonto, Zahlungsfristen)
    - Historische Performance
    """

    # Gewichtung der Kategorien
    CATEGORY_WEIGHTS = {
        SupplierRankingCategory.PUNCTUALITY: 0.30,     # 30%
        SupplierRankingCategory.PRICE: 0.25,          # 25%
        SupplierRankingCategory.RELIABILITY: 0.25,    # 25%
        SupplierRankingCategory.COMMUNICATION: 0.10,  # 10%
        SupplierRankingCategory.PAYMENT_TERMS: 0.10,  # 10%
    }

    # Tier-Schwellenwerte
    TIER_THRESHOLDS = {
        SupplierTier.PLATINUM: 90,
        SupplierTier.GOLD: 75,
        SupplierTier.SILVER: 60,
        SupplierTier.BRONZE: 40,
        SupplierTier.CRITICAL: 0,
    }

    async def calculate_supplier_ranking(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        period_days: int = 365,
    ) -> Optional[SupplierRanking]:
        """Berechnet Ranking fuer einen Lieferanten.

        Args:
            db: Datenbank-Session
            entity_id: ID des Lieferanten
            company_id: Firmen-ID
            period_days: Auswertungszeitraum in Tagen

        Returns:
            SupplierRanking oder None wenn Lieferant nicht gefunden
        """
        # Lieferant laden
        entity = await db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.entity_type == EntityType.SUPPLIER.value,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        )
        supplier = entity.scalar_one_or_none()

        if not supplier:
            return None

        # Zeitraum
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        # Dokumente des Lieferanten laden
        docs_result = await db.execute(
            select(Document).where(
                and_(
                    Document.business_entity_id == entity_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.created_at >= datetime.combine(start_date, datetime.min.time()),
                )
            )
        )
        documents = docs_result.scalars().all()

        # Rechnungen des Lieferanten laden
        invoices_result = await db.execute(
            select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= start_date,
                )
            )
        )
        invoices = list(invoices_result.scalars().all())

        # Kategorien berechnen
        category_scores = []

        # 1. Puenktlichkeit
        punctuality_score = await self._calculate_punctuality_score(
            documents, invoices
        )
        category_scores.append(punctuality_score)

        # 2. Preis-Leistung
        price_score = await self._calculate_price_score(
            db, entity_id, company_id, invoices
        )
        category_scores.append(price_score)

        # 3. Zuverlaessigkeit
        reliability_score = await self._calculate_reliability_score(
            documents, invoices
        )
        category_scores.append(reliability_score)

        # 4. Kommunikation
        communication_score = await self._calculate_communication_score(
            documents
        )
        category_scores.append(communication_score)

        # 5. Zahlungsbedingungen
        payment_terms_score = await self._calculate_payment_terms_score(
            invoices
        )
        category_scores.append(payment_terms_score)

        # Gesamtscore berechnen
        overall_score = sum(
            s.score * s.weight for s in category_scores
        )

        # Tier bestimmen
        tier = self._determine_tier(overall_score)

        # Statistiken berechnen
        total_volume = sum(
            inv.total_amount or Decimal("0") for inv in invoices
        )
        avg_order = (
            total_volume / len(invoices) if invoices else Decimal("0")
        )

        first_order = min(
            (inv.invoice_date for inv in invoices), default=None
        )
        last_order = max(
            (inv.invoice_date for inv in invoices), default=None
        )

        # Trend berechnen (Vergleich mit vorherigem Zeitraum)
        previous_score = supplier.risk_score  # Vorheriger Score (falls vorhanden)
        if previous_score is not None:
            # Risk score ist invers (hoeher = schlechter)
            # Konvertieren zu Supplier Score (hoeher = besser)
            prev_supplier_score = 100 - previous_score
            if overall_score > prev_supplier_score + 5:
                score_trend = "improving"
            elif overall_score < prev_supplier_score - 5:
                score_trend = "declining"
            else:
                score_trend = "stable"
        else:
            score_trend = "stable"
            prev_supplier_score = None

        # Empfehlungen generieren
        recommendations = self._generate_recommendations(
            category_scores, tier, invoices
        )

        ranking = SupplierRanking(
            entity_id=entity_id,
            entity_name=supplier.name,
            overall_score=round(overall_score, 1),
            tier=tier,
            category_scores=category_scores,
            total_orders=len(invoices),
            total_volume=total_volume,
            first_order_date=first_order,
            last_order_date=last_order,
            avg_order_value=avg_order,
            score_trend=score_trend,
            previous_score=prev_supplier_score,
            recommendations=recommendations,
        )

        logger.info(
            "supplier_ranking_calculated",
            entity_id=str(entity_id),
            overall_score=overall_score,
            tier=tier.value,
        )

        return ranking

    async def _calculate_punctuality_score(
        self,
        documents: List[Document],
        invoices: List[InvoiceTracking],
    ) -> SupplierScore:
        """Berechnet Puenktlichkeits-Score.

        Basiert auf:
        - Liefertermin-Einhaltung
        - Rechnungsstellungs-Geschwindigkeit
        """
        data_points = 0
        total_score = 0.0

        # Dokumente mit Lieferdatum auswerten
        delivery_scores = []
        for doc in documents:
            if doc.extracted_data:
                delivery_date = doc.extracted_data.get("delivery_date")
                expected_date = doc.extracted_data.get("expected_delivery_date")

                if delivery_date and expected_date:
                    try:
                        actual = datetime.fromisoformat(str(delivery_date)).date()
                        expected = datetime.fromisoformat(str(expected_date)).date()

                        delay_days = (actual - expected).days

                        if delay_days <= 0:
                            # Puenktlich oder frueh: 100
                            delivery_scores.append(100)
                        elif delay_days <= 2:
                            # 1-2 Tage spaet: 80
                            delivery_scores.append(80)
                        elif delay_days <= 5:
                            # 3-5 Tage spaet: 60
                            delivery_scores.append(60)
                        elif delay_days <= 10:
                            # 6-10 Tage spaet: 40
                            delivery_scores.append(40)
                        else:
                            # Mehr als 10 Tage: 20
                            delivery_scores.append(20)

                        data_points += 1
                    except (ValueError, TypeError) as e:
                        logger.debug("parse_delivery_date", error_type=type(e).__name__)

        # Rechnungs-Timing auswerten
        invoice_timing_scores = []
        for inv in invoices:
            if inv.invoice_date and inv.received_date:
                # Wie schnell wurde Rechnung nach Lieferung gestellt?
                delay = (inv.received_date - inv.invoice_date).days

                if delay <= 3:
                    invoice_timing_scores.append(100)
                elif delay <= 7:
                    invoice_timing_scores.append(80)
                elif delay <= 14:
                    invoice_timing_scores.append(60)
                else:
                    invoice_timing_scores.append(40)

                data_points += 1

        # Kombinierter Score
        all_scores = delivery_scores + invoice_timing_scores
        if all_scores:
            total_score = sum(all_scores) / len(all_scores)
        else:
            # Default bei fehlenden Daten
            total_score = 70.0

        # Trend (vereinfacht)
        trend = "stable"
        if len(all_scores) >= 4:
            recent = all_scores[-2:]
            older = all_scores[:2]
            if sum(recent) / 2 > sum(older) / 2 + 5:
                trend = "up"
            elif sum(recent) / 2 < sum(older) / 2 - 5:
                trend = "down"

        return SupplierScore(
            category=SupplierRankingCategory.PUNCTUALITY,
            score=round(total_score, 1),
            weight=self.CATEGORY_WEIGHTS[SupplierRankingCategory.PUNCTUALITY],
            data_points=data_points,
            trend=trend,
            details={
                "delivery_scores": len(delivery_scores),
                "invoice_timing_scores": len(invoice_timing_scores),
                "avg_delivery_score": (
                    sum(delivery_scores) / len(delivery_scores)
                    if delivery_scores else None
                ),
            },
        )

    async def _calculate_price_score(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        invoices: List[InvoiceTracking],
    ) -> SupplierScore:
        """Berechnet Preis-Leistungs-Score.

        Basiert auf:
        - Preiskonsistenz (Abweichungen von Angeboten)
        - Skonto-Angebote
        - Preisaenderungen ueber Zeit
        """
        data_points = 0
        scores = []

        # Preiskonsistenz aus Dokumenten
        for inv in invoices:
            # Pruefen ob Rechnung zu Bestellung passt
            if inv.total_amount and inv.total_amount > 0:
                # Vereinfachte Bewertung: Konsistente Rechnungen = gut
                scores.append(75)  # Baseline
                data_points += 1

        # Skonto-Bewertung
        skonto_offered = sum(
            1 for inv in invoices
            if inv.discount_percent and inv.discount_percent > 0
        )
        if invoices:
            skonto_ratio = skonto_offered / len(invoices)
            skonto_score = 50 + (skonto_ratio * 50)  # 50-100 basierend auf Skonto-Haeufigkeit
            scores.append(skonto_score)
            data_points += 1

        # Durchschnitt
        total_score = sum(scores) / len(scores) if scores else 70.0

        return SupplierScore(
            category=SupplierRankingCategory.PRICE,
            score=round(total_score, 1),
            weight=self.CATEGORY_WEIGHTS[SupplierRankingCategory.PRICE],
            data_points=data_points,
            trend="stable",
            details={
                "skonto_ratio": skonto_offered / len(invoices) if invoices else 0,
                "invoices_analyzed": len(invoices),
            },
        )

    async def _calculate_reliability_score(
        self,
        documents: List[Document],
        invoices: List[InvoiceTracking],
    ) -> SupplierScore:
        """Berechnet Zuverlaessigkeits-Score.

        Basiert auf:
        - Reklamationsquote
        - Vollstaendigkeit der Lieferungen
        - Qualitaetsprobleme
        """
        data_points = len(invoices)

        # Vereinfachte Bewertung basierend auf Dokumentstatus
        # In Realitaet wuerden hier Reklamationen, Ruecksendungen etc. ausgewertet

        # Pruefen ob Rechnungen bezahlt wurden (indikator fuer keine Probleme)
        paid_invoices = sum(1 for inv in invoices if inv.status == "paid")
        disputed_invoices = sum(1 for inv in invoices if inv.status == "disputed")

        if invoices:
            reliability_ratio = (paid_invoices - disputed_invoices) / len(invoices)
            score = max(0, min(100, 50 + (reliability_ratio * 50)))
        else:
            score = 70.0  # Default

        return SupplierScore(
            category=SupplierRankingCategory.RELIABILITY,
            score=round(score, 1),
            weight=self.CATEGORY_WEIGHTS[SupplierRankingCategory.RELIABILITY],
            data_points=data_points,
            trend="stable",
            details={
                "paid_invoices": paid_invoices,
                "disputed_invoices": disputed_invoices,
            },
        )

    async def _calculate_communication_score(
        self,
        documents: List[Document],
    ) -> SupplierScore:
        """Berechnet Kommunikations-Score.

        Basiert auf:
        - Dokumentqualitaet (OCR-Confidence)
        - Vollstaendigkeit der Informationen
        """
        data_points = len(documents)

        # OCR Confidence als Indikator fuer Dokumentqualitaet
        confidences = []
        for doc in documents:
            if doc.ocr_confidence:
                confidences.append(doc.ocr_confidence * 100)

        if confidences:
            # Hohe OCR Confidence = gut lesbare, professionelle Dokumente
            avg_confidence = sum(confidences) / len(confidences)
            score = min(100, avg_confidence + 10)  # Bonus fuer gute Dokumente
        else:
            score = 70.0  # Default

        return SupplierScore(
            category=SupplierRankingCategory.COMMUNICATION,
            score=round(score, 1),
            weight=self.CATEGORY_WEIGHTS[SupplierRankingCategory.COMMUNICATION],
            data_points=data_points,
            trend="stable",
            details={
                "avg_ocr_confidence": sum(confidences) / len(confidences) if confidences else None,
                "documents_analyzed": len(documents),
            },
        )

    async def _calculate_payment_terms_score(
        self,
        invoices: List[InvoiceTracking],
    ) -> SupplierScore:
        """Berechnet Zahlungsbedingungen-Score.

        Basiert auf:
        - Zahlungsziel-Laenge
        - Skonto-Konditionen
        - Flexibilitaet
        """
        data_points = len(invoices)
        scores = []

        for inv in invoices:
            inv_score = 70  # Baseline

            # Laengeres Zahlungsziel = besser fuer uns
            if inv.payment_terms_days:
                if inv.payment_terms_days >= 30:
                    inv_score += 15
                elif inv.payment_terms_days >= 14:
                    inv_score += 10
                elif inv.payment_terms_days >= 7:
                    inv_score += 5

            # Skonto-Angebot = Bonus
            if inv.discount_percent and inv.discount_percent > 0:
                inv_score += 10
                if inv.discount_percent >= 3:
                    inv_score += 5

            scores.append(min(100, inv_score))

        total_score = sum(scores) / len(scores) if scores else 70.0

        return SupplierScore(
            category=SupplierRankingCategory.PAYMENT_TERMS,
            score=round(total_score, 1),
            weight=self.CATEGORY_WEIGHTS[SupplierRankingCategory.PAYMENT_TERMS],
            data_points=data_points,
            trend="stable",
            details={
                "avg_payment_days": (
                    sum(inv.payment_terms_days or 0 for inv in invoices) / len(invoices)
                    if invoices else None
                ),
                "skonto_offers": sum(
                    1 for inv in invoices
                    if inv.discount_percent and inv.discount_percent > 0
                ),
            },
        )

    def _calculate_overall_score(self, category_scores: List[SupplierScore]) -> float:
        """Berechnet Gesamt-Score aus gewichteten Kategorie-Scores.

        Args:
            category_scores: Liste der Kategorie-Scores

        Returns:
            Gewichteter Gesamt-Score (0-100)
        """
        if not category_scores:
            return 0.0

        total_score = 0.0
        for score in category_scores:
            total_score += score.score * score.weight

        return round(total_score, 2)

    def _calculate_score_trend(
        self, previous_score: Optional[float], current_score: float
    ) -> str:
        """Berechnet Trend zwischen vorherigem und aktuellem Score.

        Args:
            previous_score: Vorheriger Score (optional)
            current_score: Aktueller Score

        Returns:
            Trend: "improving", "declining", oder "stable"
        """
        if previous_score is None:
            return "stable"

        diff = current_score - previous_score

        # Signifikante Aenderung: mehr als 5 Punkte
        if diff >= 5.0:
            return "improving"
        elif diff <= -5.0:
            return "declining"
        else:
            return "stable"

    def _detect_category_trend(self, scores: List[float]) -> str:
        """Erkennt Trend in einer Reihe von Scores.

        Args:
            scores: Liste von Scores (aelteste zuerst)

        Returns:
            Trend: "up", "down", oder "stable"
        """
        if len(scores) < 2:
            return "stable"

        # Vergleiche erste und letzte Haelfte
        mid = len(scores) // 2
        first_half_avg = sum(scores[:mid]) / mid if mid > 0 else 0
        second_half_avg = sum(scores[mid:]) / (len(scores) - mid)

        diff = second_half_avg - first_half_avg

        if diff >= 5.0:
            return "up"
        elif diff <= -5.0:
            return "down"
        else:
            return "stable"

    def _determine_tier(self, score: float) -> SupplierTier:
        """Bestimmt Tier basierend auf Score."""
        if score >= self.TIER_THRESHOLDS[SupplierTier.PLATINUM]:
            return SupplierTier.PLATINUM
        elif score >= self.TIER_THRESHOLDS[SupplierTier.GOLD]:
            return SupplierTier.GOLD
        elif score >= self.TIER_THRESHOLDS[SupplierTier.SILVER]:
            return SupplierTier.SILVER
        elif score >= self.TIER_THRESHOLDS[SupplierTier.BRONZE]:
            return SupplierTier.BRONZE
        else:
            return SupplierTier.CRITICAL

    def _generate_recommendations(
        self,
        scores: List[SupplierScore],
        tier: SupplierTier,
        invoices: List[InvoiceTracking],
    ) -> List[str]:
        """Generiert Empfehlungen basierend auf Bewertung."""
        recommendations = []

        # Schwache Kategorien identifizieren
        for score in scores:
            if score.score < 60:
                if score.category == SupplierRankingCategory.PUNCTUALITY:
                    recommendations.append(
                        "Liefertermine ueberpruefen - haeufige Verspaetungen"
                    )
                elif score.category == SupplierRankingCategory.PRICE:
                    recommendations.append(
                        "Preisverhandlungen fuehren - Konditionen verbessern"
                    )
                elif score.category == SupplierRankingCategory.RELIABILITY:
                    recommendations.append(
                        "Qualitaetsprobleme ansprechen - Alternative suchen"
                    )
                elif score.category == SupplierRankingCategory.COMMUNICATION:
                    recommendations.append(
                        "Kommunikation verbessern - Dokumentenqualitaet niedrig"
                    )
                elif score.category == SupplierRankingCategory.PAYMENT_TERMS:
                    recommendations.append(
                        "Zahlungsbedingungen neu verhandeln"
                    )

        # Tier-spezifische Empfehlungen
        if tier == SupplierTier.PLATINUM:
            recommendations.append("Top-Lieferant - Partnerschaft ausbauen")
        elif tier == SupplierTier.GOLD:
            recommendations.append("Guter Lieferant - bevorzugt behandeln")
        elif tier == SupplierTier.CRITICAL:
            recommendations.append("KRITISCH: Alternative Lieferanten suchen!")
            recommendations.append("Bestellvolumen reduzieren")

        # Volumen-basierte Empfehlung
        if len(invoices) < 3:
            recommendations.append("Wenig Daten - weitere Bestellungen abwarten")

        return recommendations

    # -------------------------------------------------------------------------
    # Report-Funktionen
    # -------------------------------------------------------------------------

    async def get_supplier_ranking_report(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_days: int = 365,
        top_n: int = 10,
    ) -> SupplierRankingReport:
        """Erstellt Report ueber alle Lieferanten-Rankings.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            period_days: Auswertungszeitraum
            top_n: Anzahl Top/Bottom Lieferanten

        Returns:
            SupplierRankingReport mit Uebersicht
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        # Alle Lieferanten laden
        suppliers_result = await db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.entity_type == EntityType.SUPPLIER.value,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        )
        suppliers = suppliers_result.scalars().all()

        total_suppliers = len(suppliers)

        # Rankings berechnen
        rankings: List[SupplierRanking] = []
        for supplier in suppliers:
            ranking = await self.calculate_supplier_ranking(
                db, supplier.id, company_id, period_days
            )
            if ranking and ranking.total_orders > 0:
                rankings.append(ranking)

        # Sortieren nach Score
        rankings.sort(key=lambda r: r.overall_score, reverse=True)

        # Tier-Verteilung
        tier_distribution = {tier.value: 0 for tier in SupplierTier}
        for r in rankings:
            tier_distribution[r.tier.value] += 1

        # Top/Bottom/Trends
        top_suppliers = rankings[:top_n]
        critical_suppliers = [r for r in rankings if r.tier == SupplierTier.CRITICAL]
        improving_suppliers = [
            r for r in rankings if r.score_trend == "improving"
        ][:top_n]
        declining_suppliers = [
            r for r in rankings if r.score_trend == "declining"
        ][:top_n]

        # Durchschnittswerte
        if rankings:
            avg_overall = sum(r.overall_score for r in rankings) / len(rankings)

            punctuality_scores = [
                next(
                    (s.score for s in r.category_scores
                     if s.category == SupplierRankingCategory.PUNCTUALITY),
                    0
                )
                for r in rankings
            ]
            avg_punctuality = sum(punctuality_scores) / len(punctuality_scores)

            reliability_scores = [
                next(
                    (s.score for s in r.category_scores
                     if s.category == SupplierRankingCategory.RELIABILITY),
                    0
                )
                for r in rankings
            ]
            avg_reliability = sum(reliability_scores) / len(reliability_scores)
        else:
            avg_overall = 0.0
            avg_punctuality = 0.0
            avg_reliability = 0.0

        report = SupplierRankingReport(
            company_id=company_id,
            total_suppliers=total_suppliers,
            ranked_suppliers=len(rankings),
            tier_distribution=tier_distribution,
            top_suppliers=top_suppliers,
            critical_suppliers=critical_suppliers,
            improving_suppliers=improving_suppliers,
            declining_suppliers=declining_suppliers,
            avg_overall_score=round(avg_overall, 1),
            avg_punctuality=round(avg_punctuality, 1),
            avg_reliability=round(avg_reliability, 1),
            analysis_period_start=start_date,
            analysis_period_end=end_date,
        )

        logger.info(
            "supplier_ranking_report_generated",
            company_id=str(company_id),
            total_suppliers=total_suppliers,
            ranked_suppliers=len(rankings),
        )

        return report

    async def get_supplier_comparison(
        self,
        db: AsyncSession,
        company_id: UUID,
        entity_ids: List[UUID],
        period_days: int = 365,
    ) -> List[SupplierRanking]:
        """Vergleicht mehrere Lieferanten.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            entity_ids: Liste der zu vergleichenden Lieferanten-IDs
            period_days: Auswertungszeitraum

        Returns:
            Liste der SupplierRankings sortiert nach Score
        """
        rankings = []

        for entity_id in entity_ids:
            ranking = await self.calculate_supplier_ranking(
                db, entity_id, company_id, period_days
            )
            if ranking:
                rankings.append(ranking)

        # Sortieren nach Gesamtscore
        rankings.sort(key=lambda r: r.overall_score, reverse=True)

        return rankings


# =============================================================================
# Singleton
# =============================================================================

_supplier_ranking_service: Optional[SupplierRankingService] = None


def get_supplier_ranking_service() -> SupplierRankingService:
    """Gibt Supplier-Ranking-Service-Instanz zurueck."""
    global _supplier_ranking_service
    if _supplier_ranking_service is None:
        _supplier_ranking_service = SupplierRankingService()
    return _supplier_ranking_service

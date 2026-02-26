# -*- coding: utf-8 -*-
"""
DeviationLearner - ML-basiertes Lernen von Lieferanten-Abweichungstoleranz.

Lernt pro Lieferant welche Betragsabweichungen im historischen Durchschnitt
als "normal" einzustufen sind (z.B. Versandkosten-Varianz, Skontoabzug).

Phase 1: Regelbasiert (0-2% Fallback-Toleranz)
Phase 2: Lernen aus bestätigten Matches pro Vendor

Architektur:
    - VendorDeviationProfile: Immutable Daten-Transfer-Objekt
    - DeviationLearner: Async-Service, liest/schreibt DB
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.sensitive_data_filter import get_pii_safe_logger
from app.core.safe_errors import safe_error_log
from app.db.models_po_matching import (
    PurchaseOrderMatch,
    MatchDiscrepancy,
    MatchStatus,
    DiscrepancyCategory,
)

logger = get_pii_safe_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

VENDOR_PROFILE_LOOKUPS = Counter(
    "deviation_learner_profile_lookups_total",
    "Vendor-Profil-Abfragen",
    ["source"],  # "cache", "computed", "default"
)

VENDOR_TOLERANCE_HISTOGRAM = Histogram(
    "deviation_learner_vendor_tolerance_percent",
    "Gelernte Betrags-Toleranz pro Vendor",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0],
)

LEARNING_EVENTS = Counter(
    "deviation_learner_learning_events_total",
    "Lern-Events aus manuellen Match-Bestaetigungen",
    ["outcome"],  # "learned", "skipped", "error"
)


# =============================================================================
# Konstanten
# =============================================================================

# Minimale Anzahl historischer bestätigter Matches, bevor gelernte Toleranz
# verwendet wird (darunter: Regelbasierter Fallback).
MIN_SAMPLES_FOR_LEARNING: int = 3

# Fallback-Toleranz (Regelbasiert, Phase 1)
DEFAULT_AMOUNT_TOLERANCE_PERCENT: float = 2.0

# Maximale Toleranz, die gelernt werden kann (Sicherheits-Cap)
MAX_LEARNED_TOLERANCE_PERCENT: float = 15.0

# Lookback-Fenster für historische Matches (in Tagen)
LEARNING_WINDOW_DAYS: int = 180

# Gewichtung: neuere Matches erhalten höheres Gewicht (exponentieller Decay)
DECAY_HALF_LIFE_DAYS: int = 60


# =============================================================================
# Data Transfer Objects
# =============================================================================


@dataclass(frozen=True)
class VendorDeviationProfile:
    """Immutable Profil der gelernten Abweichungstoleranz eines Lieferanten.

    Attributes:
        vendor_id: Lieferanten-Entity-ID.
        company_id: Mandanten-ID.
        amount_tolerance_percent: Gelernte Betragstoleranz (0-15%).
        sample_count: Anzahl der Lern-Samples.
        learned: True wenn gelernte Werte verwendet werden, False = Regelbasiert.
        avg_deviation_percent: Durchschnittliche historische Abweichung.
        max_deviation_percent: Maximale historische Abweichung.
        last_updated: Zeitpunkt der letzten Aktualisierung.
        explanation: Deutsche Erklärung der Toleranz.
    """
    vendor_id: UUID
    company_id: UUID
    amount_tolerance_percent: float
    sample_count: int
    learned: bool
    avg_deviation_percent: float
    max_deviation_percent: float
    last_updated: datetime
    explanation: str


@dataclass
class _DeviationSample:
    """Internes DTO: Ein historischer Abweichungs-Datenpunkt."""
    match_id: UUID
    deviation_percent: float
    confirmed_at: datetime
    weight: float = field(default=1.0)


# =============================================================================
# DeviationLearner
# =============================================================================


class DeviationLearner:
    """Lernt pro Lieferant welche Betragsabweichungen normal sind.

    Implementierung:
        Phase 1 (Fallback): Regelbasiert mit DEFAULT_AMOUNT_TOLERANCE_PERCENT.
        Phase 2 (Gelernt):  Gewichtetes Mittel der historischen Abweichungen
                            aus manuell bestätigten Matches.

    Threading:
        Stateless: Jede Methode bekommt eine eigene AsyncSession.
        In-Memory-Cache: Kein externer Cache erforderlich.

    Verwendung:
        learner = DeviationLearner()
        profile = await learner.get_vendor_profile(db, company_id, vendor_id)
        tolerance = profile.amount_tolerance_percent
    """

    def __init__(self) -> None:
        # Einfacher In-Memory-Cache: {(company_id, vendor_id): VendorDeviationProfile}
        # TTL wird beim Lesen geprüft (cache_ttl_minutes).
        self._cache: Dict[str, VendorDeviationProfile] = {}
        self._cache_ttl_minutes: int = 30

    # -------------------------------------------------------------------------
    # Öffentliche API
    # -------------------------------------------------------------------------

    async def get_vendor_profile(
        self,
        db: AsyncSession,
        company_id: UUID,
        vendor_id: UUID,
    ) -> VendorDeviationProfile:
        """Laedt oder berechnet das Vendor-Profil.

        Liefert zuerst gecachte Profile zurück (TTL 30 Minuten).
        Falls Cache abgelaufen oder nicht vorhanden, wird aus historischen
        Matches berechnet.

        Args:
            db: Async-Datenbanksession.
            company_id: Mandanten-ID.
            vendor_id: Lieferanten-Entity-ID.

        Returns:
            VendorDeviationProfile mit Toleranzwert und Metadaten.
        """
        cache_key = f"{company_id}:{vendor_id}"

        # Cache-Prüfung
        cached = self._cache.get(cache_key)
        if cached is not None:
            age_minutes = (
                datetime.now(timezone.utc) - cached.last_updated
            ).total_seconds() / 60.0
            if age_minutes < self._cache_ttl_minutes:
                VENDOR_PROFILE_LOOKUPS.labels(source="cache").inc()
                return cached

        # Aus DB berechnen
        try:
            profile = await self._compute_profile(db, company_id, vendor_id)
            self._cache[cache_key] = profile
            VENDOR_PROFILE_LOOKUPS.labels(source="computed").inc()
            return profile

        except Exception as exc:
            logger.warning(
                "vendor_profile_berechnung_fehlgeschlagen",
                vendor_id=str(vendor_id),
                company_id=str(company_id),
                **safe_error_log(exc, context="DeviationLearner"),
            )
            # Fallback auf Regelbasiert
            VENDOR_PROFILE_LOOKUPS.labels(source="default").inc()
            return self._default_profile(vendor_id, company_id)

    async def learn_from_confirmation(
        self,
        db: AsyncSession,
        company_id: UUID,
        match_id: UUID,
    ) -> None:
        """Lernt aus einer manuellen Match-Bestaetigung.

        Wird aufgerufen nachdem ein Benutzer einen Match trotz Abweichungen
        bestätigt hat. Aktualisiert das Vendor-Profil für die Zukunft.

        Args:
            db: Async-Datenbanksession.
            company_id: Mandanten-ID.
            match_id: ID des bestätigten PurchaseOrderMatch.
        """
        try:
            # Match laden
            stmt = select(PurchaseOrderMatch).where(
                and_(
                    PurchaseOrderMatch.id == match_id,
                    PurchaseOrderMatch.company_id == company_id,
                    PurchaseOrderMatch.match_status == MatchStatus.APPROVED,
                )
            )
            result = await db.execute(stmt)
            match = result.scalar_one_or_none()

            if match is None:
                logger.debug(
                    "lern_event_uebersprungen_kein_match",
                    match_id=str(match_id),
                )
                LEARNING_EVENTS.labels(outcome="skipped").inc()
                return

            if match.vendor_entity_id is None:
                logger.debug(
                    "lern_event_uebersprungen_kein_vendor",
                    match_id=str(match_id),
                )
                LEARNING_EVENTS.labels(outcome="skipped").inc()
                return

            # Cache invalidieren damit nächste Anfrage neu berechnet
            cache_key = f"{company_id}:{match.vendor_entity_id}"
            self._cache.pop(cache_key, None)

            logger.info(
                "lern_event_verarbeitet",
                match_id=str(match_id),
                vendor_id=str(match.vendor_entity_id),
                company_id=str(company_id),
            )
            LEARNING_EVENTS.labels(outcome="learned").inc()

        except Exception as exc:
            logger.error(
                "lern_event_fehlgeschlagen",
                match_id=str(match_id),
                **safe_error_log(exc, context="DeviationLearner.learn_from_confirmation"),
            )
            LEARNING_EVENTS.labels(outcome="error").inc()

    async def get_amount_tolerance(
        self,
        db: AsyncSession,
        company_id: UUID,
        vendor_id: UUID,
    ) -> float:
        """Gibt die gelernte Betrags-Toleranz fuer einen Vendor zurueck.

        Bequemlichkeitsmethode die direkt den Prozentwert liefert.

        Args:
            db: Async-Datenbanksession.
            company_id: Mandanten-ID.
            vendor_id: Lieferanten-Entity-ID.

        Returns:
            Toleranz in Prozent (z.B. 2.0 = ±2%).
        """
        profile = await self.get_vendor_profile(db, company_id, vendor_id)
        return profile.amount_tolerance_percent

    # -------------------------------------------------------------------------
    # Interne Berechnung
    # -------------------------------------------------------------------------

    async def _compute_profile(
        self,
        db: AsyncSession,
        company_id: UUID,
        vendor_id: UUID,
    ) -> VendorDeviationProfile:
        """Berechnet das Vendor-Profil aus historischen Matches.

        Aggregiert alle AMOUNT-Abweichungen aus bestätigten Matches
        des Vendors in den letzten LEARNING_WINDOW_DAYS Tagen.
        Wendet exponentiellen Decay an (neuere Matches werden stärker gewichtet).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=LEARNING_WINDOW_DAYS)

        # Alle bestätigten Matches mit diesem Vendor laden
        stmt = (
            select(PurchaseOrderMatch)
            .where(
                and_(
                    PurchaseOrderMatch.company_id == company_id,
                    PurchaseOrderMatch.vendor_entity_id == vendor_id,
                    PurchaseOrderMatch.match_status == MatchStatus.APPROVED,
                    PurchaseOrderMatch.approved_at >= cutoff,
                )
            )
            .order_by(PurchaseOrderMatch.approved_at.desc())
            .limit(100)
        )
        result = await db.execute(stmt)
        matches = result.scalars().all()

        if not matches:
            return self._default_profile(vendor_id, company_id)

        # Abweichungssamples sammeln
        samples: List[_DeviationSample] = []
        now = datetime.now(timezone.utc)

        for match in matches:
            if match.approved_at is None:
                continue

            # Maximale prozentuale Abweichung dieser Matches aus Discrepancies
            deviation = await self._get_max_amount_deviation(db, match.id)

            # Alternativer Ansatz: Direkte Betragsabweichung aus Match-Feldern
            if deviation is None and match.po_amount and match.invoice_amount:
                po = float(match.po_amount)
                inv = float(match.invoice_amount)
                if po > 0:
                    deviation = abs((inv - po) / po) * 100.0

            if deviation is None:
                continue

            # Zeitlicher Decay: neuere Matches erhalten höheres Gewicht
            approved_at = match.approved_at
            if approved_at.tzinfo is None:
                approved_at = approved_at.replace(tzinfo=timezone.utc)
            age_days = (now - approved_at).total_seconds() / 86400.0
            weight = math.exp(-age_days * math.log(2) / DECAY_HALF_LIFE_DAYS)

            samples.append(
                _DeviationSample(
                    match_id=match.id,
                    deviation_percent=deviation,
                    confirmed_at=approved_at,
                    weight=weight,
                )
            )

        if len(samples) < MIN_SAMPLES_FOR_LEARNING:
            return self._default_profile(vendor_id, company_id)

        # Gewichtetes Mittel berechnen
        total_weight = sum(s.weight for s in samples)
        weighted_avg = sum(s.deviation_percent * s.weight for s in samples) / total_weight
        max_deviation = max(s.deviation_percent for s in samples)

        # Toleranz = gewichtetes Mittel * Sicherheitspuffer (1.5x), gecapped
        learned_tolerance = min(weighted_avg * 1.5, MAX_LEARNED_TOLERANCE_PERCENT)
        # Mindest-Toleranz = Regelbasierter Wert
        learned_tolerance = max(learned_tolerance, DEFAULT_AMOUNT_TOLERANCE_PERCENT)

        VENDOR_TOLERANCE_HISTOGRAM.observe(learned_tolerance)

        explanation = (
            f"Gelernte Toleranz aus {len(samples)} bestätigten Matches "
            f"der letzten {LEARNING_WINDOW_DAYS} Tage. "
            f"Durchschn. Abweichung: {weighted_avg:.2f}%, "
            f"Toleranz: ±{learned_tolerance:.2f}%."
        )

        logger.info(
            "vendor_profil_berechnet",
            vendor_id=str(vendor_id),
            company_id=str(company_id),
            sample_count=len(samples),
            avg_deviation=round(weighted_avg, 3),
            learned_tolerance=round(learned_tolerance, 3),
        )

        return VendorDeviationProfile(
            vendor_id=vendor_id,
            company_id=company_id,
            amount_tolerance_percent=learned_tolerance,
            sample_count=len(samples),
            learned=True,
            avg_deviation_percent=weighted_avg,
            max_deviation_percent=max_deviation,
            last_updated=datetime.now(timezone.utc),
            explanation=explanation,
        )

    async def _get_max_amount_deviation(
        self,
        db: AsyncSession,
        match_id: UUID,
    ) -> Optional[float]:
        """Liest die maximale Betrags-Abweichung aus MatchDiscrepancy fuer einen Match."""
        stmt = (
            select(func.max(MatchDiscrepancy.deviation_percent))
            .where(
                and_(
                    MatchDiscrepancy.match_id == match_id,
                    MatchDiscrepancy.category == DiscrepancyCategory.AMOUNT,
                    MatchDiscrepancy.deviation_percent.isnot(None),
                )
            )
        )
        result = await db.execute(stmt)
        value = result.scalar_one_or_none()
        if value is None:
            return None
        return abs(float(value))

    @staticmethod
    def _default_profile(
        vendor_id: UUID,
        company_id: UUID,
    ) -> VendorDeviationProfile:
        """Erstellt ein regelbasiertes Standard-Profil (Phase 1 Fallback)."""
        return VendorDeviationProfile(
            vendor_id=vendor_id,
            company_id=company_id,
            amount_tolerance_percent=DEFAULT_AMOUNT_TOLERANCE_PERCENT,
            sample_count=0,
            learned=False,
            avg_deviation_percent=0.0,
            max_deviation_percent=0.0,
            last_updated=datetime.now(timezone.utc),
            explanation=(
                f"Regelbasierte Standard-Toleranz (±{DEFAULT_AMOUNT_TOLERANCE_PERCENT}%). "
                f"Mindestens {MIN_SAMPLES_FOR_LEARNING} bestätigte Matches erforderlich "
                f"für Lern-Modus."
            ),
        )


# =============================================================================
# Singleton-Instanz (Dependency Injection)
# =============================================================================

_deviation_learner: Optional[DeviationLearner] = None


def get_deviation_learner() -> DeviationLearner:
    """Gibt die Singleton-Instanz des DeviationLearner zurück."""
    global _deviation_learner
    if _deviation_learner is None:
        _deviation_learner = DeviationLearner()
    return _deviation_learner

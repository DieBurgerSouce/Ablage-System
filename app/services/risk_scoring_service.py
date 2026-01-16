"""
Risk Scoring Service

Berechnet Risiko-Scores fuer Geschaeftspartner basierend auf:
- Zahlungsverhalten (Zahlungsverzoegerungen, Ausfallraten)
- Dokumentenhistorie (Anzahl, Frequenz, Typen)
- Rechnungsvolumen und -muster
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, Document, InvoiceTracking, DocumentCategory
from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Risk Factor Weights
# ============================================================================

RISK_WEIGHTS = {
    "payment_delay": 0.35,      # Zahlungsverzoegerung
    "default_rate": 0.25,       # Ausfallrate
    "invoice_volume": 0.15,     # Rechnungsvolumen (niedriger = riskanter)
    "document_frequency": 0.10, # Dokumentenfrequenz (unregelmaessig = riskanter)
    "relationship_age": 0.15,   # Beziehungsdauer (kuerzer = riskanter)
}


class RiskFactors:
    """Einzelne Risikofaktoren mit Bewertung."""

    def __init__(self) -> None:
        self.payment_delay_days: float = 0.0  # Durchschnittliche Verzoegerung in Tagen
        self.default_rate: float = 0.0  # Prozent ausgefallener Zahlungen
        self.invoice_volume: float = 0.0  # Gesamtvolumen in EUR
        self.document_frequency: float = 0.0  # Dokumente pro Monat
        self.relationship_months: float = 0.0  # Beziehungsdauer in Monaten
        self.total_invoices: int = 0
        self.paid_invoices: int = 0
        self.overdue_invoices: int = 0
        self.open_invoices: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer JSON-Speicherung."""
        return {
            "payment_delay_days": round(self.payment_delay_days, 1),
            "default_rate": round(self.default_rate * 100, 1),  # Als Prozent
            "invoice_volume": round(self.invoice_volume, 2),
            "document_frequency": round(self.document_frequency, 2),
            "relationship_months": round(self.relationship_months, 1),
            "total_invoices": self.total_invoices,
            "paid_invoices": self.paid_invoices,
            "overdue_invoices": self.overdue_invoices,
            "open_invoices": self.open_invoices,
        }


class RiskScoringService:
    """Service fuer Risiko-Score-Berechnung."""

    def __init__(self) -> None:
        self._weights = RISK_WEIGHTS

    async def calculate_risk_score(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> Tuple[float, float, RiskFactors]:
        """
        Berechnet Risiko-Score fuer einen Geschaeftspartner.

        Returns:
            Tuple[risk_score, payment_behavior_score, factors]
            - risk_score: 0-100 (100 = hoechstes Risiko)
            - payment_behavior_score: 0-100 (100 = bester Zahler)
            - factors: Detaillierte Risikofaktoren
        """
        factors = await self._collect_factors(db, entity_id)

        # Einzelne Scores berechnen (jeweils 0-100, hoeher = riskanter)
        payment_delay_score = self._score_payment_delay(factors.payment_delay_days)
        default_rate_score = self._score_default_rate(factors.default_rate)
        invoice_volume_score = self._score_invoice_volume(factors.invoice_volume)
        document_frequency_score = self._score_document_frequency(factors.document_frequency)
        relationship_age_score = self._score_relationship_age(factors.relationship_months)

        # Gewichteter Gesamt-Risiko-Score
        risk_score = (
            payment_delay_score * self._weights["payment_delay"]
            + default_rate_score * self._weights["default_rate"]
            + invoice_volume_score * self._weights["invoice_volume"]
            + document_frequency_score * self._weights["document_frequency"]
            + relationship_age_score * self._weights["relationship_age"]
        )

        # Payment Behavior Score (umgekehrte Skala: hoeher = besser)
        # Hauptsaechlich basierend auf Zahlungsverzoegerung und Ausfallrate
        payment_behavior_score = 100 - (
            payment_delay_score * 0.6 + default_rate_score * 0.4
        )

        return (
            min(100, max(0, risk_score)),
            min(100, max(0, payment_behavior_score)),
            factors,
        )

    async def _collect_factors(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> RiskFactors:
        """Sammelt alle Risikofaktoren fuer einen Geschaeftspartner."""
        factors = RiskFactors()

        # Entity abrufen
        entity_result = await db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()

        if not entity:
            return factors

        # Basis-Statistiken aus Entity
        factors.invoice_volume = entity.total_invoice_amount or 0.0

        # Beziehungsdauer berechnen
        if entity.first_document_date:
            age_delta = datetime.now(entity.first_document_date.tzinfo) - entity.first_document_date
            factors.relationship_months = age_delta.days / 30.0
        else:
            factors.relationship_months = 0.0

        # Dokumentenfrequenz berechnen
        if entity.document_count and entity.first_document_date and entity.last_document_date:
            span_days = (entity.last_document_date - entity.first_document_date).days
            if span_days > 0:
                factors.document_frequency = (entity.document_count / span_days) * 30  # Pro Monat
            else:
                factors.document_frequency = float(entity.document_count)
        else:
            factors.document_frequency = 0.0

        # Invoice Tracking Daten abrufen
        await self._collect_invoice_factors(db, entity_id, factors)

        return factors

    async def _collect_invoice_factors(
        self,
        db: AsyncSession,
        entity_id: UUID,
        factors: RiskFactors,
    ) -> None:
        """Sammelt Rechnungs-bezogene Faktoren."""
        # Alle Rechnungen des Geschaeftspartners finden
        # Ueber Document -> InvoiceTracking
        invoice_query = (
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    Document.deleted_at.is_(None),
                )
            )
        )

        invoice_result = await db.execute(invoice_query)
        invoices = invoice_result.scalars().all()

        if not invoices:
            return

        factors.total_invoices = len(invoices)

        # Zahlungsstatus analysieren
        paid_invoices = []
        overdue_count = 0
        open_count = 0

        now = datetime.now()

        for inv in invoices:
            if inv.status == "paid":
                paid_invoices.append(inv)
                factors.paid_invoices += 1
            elif inv.status in ("overdue", "dunning"):
                overdue_count += 1
                factors.overdue_invoices += 1
            elif inv.status in ("open", "sent"):
                # Pruefen ob ueberfaellig
                if inv.due_date and inv.due_date.replace(tzinfo=None) < now:
                    overdue_count += 1
                    factors.overdue_invoices += 1
                else:
                    open_count += 1
                    factors.open_invoices += 1

        # Zahlungsverzoegerung berechnen
        if paid_invoices:
            delay_days = []
            for inv in paid_invoices:
                if inv.paid_at and inv.due_date:
                    paid_date = inv.paid_at.replace(tzinfo=None) if inv.paid_at.tzinfo else inv.paid_at
                    due_date = inv.due_date.replace(tzinfo=None) if inv.due_date.tzinfo else inv.due_date
                    delay = (paid_date - due_date).days
                    if delay > 0:  # Nur Verzoegerungen zaehlen
                        delay_days.append(delay)

            if delay_days:
                factors.payment_delay_days = sum(delay_days) / len(delay_days)

        # Ausfallrate berechnen (ueberfaellige / total)
        if factors.total_invoices > 0:
            factors.default_rate = overdue_count / factors.total_invoices

    def _score_payment_delay(self, delay_days: float) -> float:
        """Bewertet Zahlungsverzoegerung. 0 Tage = 0 Score, 30+ Tage = 100."""
        if delay_days <= 0:
            return 0.0
        if delay_days >= 30:
            return 100.0
        return (delay_days / 30) * 100

    def _score_default_rate(self, rate: float) -> float:
        """Bewertet Ausfallrate. 0% = 0 Score, 20%+ = 100."""
        if rate <= 0:
            return 0.0
        if rate >= 0.20:
            return 100.0
        return (rate / 0.20) * 100

    def _score_invoice_volume(self, volume: float) -> float:
        """Bewertet Rechnungsvolumen. Niedriger = riskanter (weniger Engagement)."""
        # 0 EUR = 80 Score (keine Historie), 100k+ EUR = 0 Score (etabliert)
        if volume <= 0:
            return 80.0
        if volume >= 100000:
            return 0.0
        # Lineare Abnahme
        return 80 - (volume / 100000) * 80

    def _score_document_frequency(self, freq_per_month: float) -> float:
        """Bewertet Dokumentenfrequenz. Unregelmaessig = riskanter."""
        # 0 Dokumente/Monat = 60 Score, 10+ = 0 Score
        if freq_per_month <= 0:
            return 60.0
        if freq_per_month >= 10:
            return 0.0
        return 60 - (freq_per_month / 10) * 60

    def _score_relationship_age(self, months: float) -> float:
        """Bewertet Beziehungsdauer. Kuerzer = riskanter."""
        # 0 Monate = 70 Score, 24+ Monate = 0 Score
        if months <= 0:
            return 70.0
        if months >= 24:
            return 0.0
        return 70 - (months / 24) * 70

    async def update_entity_risk_score(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> Optional[BusinessEntity]:
        """
        Aktualisiert den Risiko-Score eines Geschaeftspartners.

        Returns:
            Updated BusinessEntity or None if not found
        """
        risk_score, payment_score, factors = await self.calculate_risk_score(db, entity_id)

        # Entity aktualisieren
        result = await db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()

        if not entity:
            logger.warning(f"Entity {entity_id} nicht gefunden fuer Risk-Score-Update")
            return None

        entity.risk_score = risk_score
        entity.payment_behavior_score = payment_score
        entity.risk_factors = factors.to_dict()
        entity.risk_calculated_at = datetime.now()

        await db.commit()
        await db.refresh(entity)

        logger.info(
            f"Risk-Score aktualisiert fuer Entity {entity.name}: "
            f"risk={risk_score:.1f}, payment_behavior={payment_score:.1f}"
        )

        return entity

    async def update_all_risk_scores(
        self,
        db: AsyncSession,
        entity_type: Optional[str] = None,
        limit: int = 1000,
    ) -> int:
        """
        Aktualisiert Risiko-Scores fuer alle (oder gefilterte) Geschaeftspartner.

        Returns:
            Number of updated entities
        """
        query = select(BusinessEntity.id).where(
            and_(
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
            )
        )

        if entity_type:
            query = query.where(BusinessEntity.entity_type == entity_type)

        query = query.limit(limit)

        result = await db.execute(query)
        entity_ids = [row[0] for row in result.fetchall()]

        updated_count = 0
        for entity_id in entity_ids:
            try:
                await self.update_entity_risk_score(db, entity_id)
                updated_count += 1
            except Exception as e:
                logger.error(f"Fehler bei Risk-Score-Update fuer Entity {entity_id}: {e}")

        logger.info(f"Risk-Scores aktualisiert fuer {updated_count} Entities")
        return updated_count


# Singleton instance
_risk_scoring_service: Optional[RiskScoringService] = None


def get_risk_scoring_service() -> RiskScoringService:
    """Returns singleton instance of RiskScoringService."""
    global _risk_scoring_service
    if _risk_scoring_service is None:
        _risk_scoring_service = RiskScoringService()
    return _risk_scoring_service

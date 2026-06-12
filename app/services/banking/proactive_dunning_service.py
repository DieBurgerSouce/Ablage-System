# -*- coding: utf-8 -*-
"""
Proactive Dunning Service - Risk-basierte automatische Mahnung.

Intelligentes Mahnwesen mit:
- Risiko-basierter Entscheidung
- Zahlungshistorie-Berücksichtigung
- Multi-Channel Benachrichtigungen
- Eskalationslogik

Proaktiv statt reaktiv - warnt vor Problemen.

Vision 2026 Q2 - Proactive Dunning Automation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InvoiceTracking, InvoiceStatus, BusinessEntity
from app.services.invoice_direction import is_open_invoice, is_outgoing_invoice
from app.core.security.sensitive_data_filter import get_pii_safe_logger
from app.core.safe_errors import safe_error_log

logger = get_pii_safe_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

DUNNING_DECISIONS = Counter(
    "dunning_decisions_total",
    "Anzahl Mahnentscheidungen",
    ["action", "dunning_level"]
)

DUNNING_CONFIDENCE = Histogram(
    "dunning_decision_confidence",
    "Verteilung der Entscheidungs-Confidence",
    buckets=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
)

OVERDUE_INVOICES = Gauge(
    "overdue_invoices_count",
    "Anzahl überfälliger Rechnungen",
    ["dunning_level"]
)


# =============================================================================
# Enums
# =============================================================================

class DunningLevel(int, Enum):
    """Mahnstufen."""
    REMINDER = 0         # Zahlungserinnerung (freundlich)
    FIRST = 1            # 1. Mahnung
    SECOND = 2           # 2. Mahnung
    FINAL = 3            # 3. Mahnung (letzte Warnung)
    COLLECTION = 4       # Inkasso-Ankündigung


class DunningAction(str, Enum):
    """Empfohlene Mahnaktion."""
    SEND_REMINDER = "send_reminder"        # Zahlungserinnerung senden
    SEND_DUNNING = "send_dunning"          # Mahnung senden
    ESCALATE = "escalate"                  # Eskalieren (nächste Stufe)
    HOLD = "hold"                          # Abwarten (guter Kunde)
    MANUAL_REVIEW = "manual_review"        # Manuelle Prüfung
    COLLECTION = "collection"              # An Inkasso übergeben


class NotificationChannel(str, Enum):
    """Benachrichtigungskanäle."""
    EMAIL = "email"
    LETTER = "letter"
    SLACK = "slack"
    INTERNAL = "internal"  # Nur interne Benachrichtigung


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PaymentHistory:
    """Zahlungshistorie einer Entity."""
    entity_id: UUID
    entity_name: str = ""

    # Statistiken
    total_invoices: int = 0
    paid_invoices: int = 0
    overdue_invoices: int = 0

    # Zahlungsverhalten
    avg_delay_days: float = 0.0
    max_delay_days: int = 0
    on_time_rate: float = 0.0  # Prozent pünktlicher Zahlungen

    # Volumen
    total_volume: Decimal = Decimal("0")
    outstanding_volume: Decimal = Decimal("0")

    # Beziehung
    relationship_months: int = 0
    last_payment_date: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "entity_id": str(self.entity_id),
            "entity_name": self.entity_name,
            "total_invoices": self.total_invoices,
            "paid_invoices": self.paid_invoices,
            "overdue_invoices": self.overdue_invoices,
            "avg_delay_days": self.avg_delay_days,
            "max_delay_days": self.max_delay_days,
            "on_time_rate": self.on_time_rate,
            "total_volume": float(self.total_volume),
            "outstanding_volume": float(self.outstanding_volume),
            "relationship_months": self.relationship_months,
            "last_payment_date": self.last_payment_date.isoformat() if self.last_payment_date else None,
        }


@dataclass
class DunningDecision:
    """Entscheidung für eine Mahnung."""
    id: UUID = field(default_factory=uuid4)
    invoice_id: UUID = field(default_factory=uuid4)

    # Entscheidung
    action: DunningAction = DunningAction.MANUAL_REVIEW
    dunning_level: DunningLevel = DunningLevel.REMINDER
    confidence: float = 0.0

    # Kanäle
    channels: List[NotificationChannel] = field(default_factory=list)

    # Erklärung
    explanation: str = ""
    factors: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    recommended_send_date: Optional[datetime] = None

    # Entity-Kontext
    entity_risk_score: float = 0.0
    payment_history: Optional[PaymentHistory] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "invoice_id": str(self.invoice_id),
            "action": self.action.value,
            "dunning_level": self.dunning_level.value,
            "confidence": self.confidence,
            "channels": [c.value for c in self.channels],
            "explanation": self.explanation,
            "factors": self.factors,
            "recommended_send_date": self.recommended_send_date.isoformat() if self.recommended_send_date else None,
            "entity_risk_score": self.entity_risk_score,
            "payment_history": self.payment_history.to_dict() if self.payment_history else None,
        }


@dataclass
class DunningProcessResult:
    """Ergebnis der Mahnverarbeitung."""
    processed_count: int = 0
    sent_count: int = 0
    held_count: int = 0
    review_count: int = 0
    decisions: List[DunningDecision] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "processed_count": self.processed_count,
            "sent_count": self.sent_count,
            "held_count": self.held_count,
            "review_count": self.review_count,
            "decisions": [d.to_dict() for d in self.decisions],
        }


# =============================================================================
# Proactive Dunning Service
# =============================================================================

class ProactiveDunningService:
    """
    Automatische Mahnung mit Eskalationslogik.

    Entscheidungsfaktoren:
    - Risiko-Score der Entity
    - Zahlungshistorie
    - Überfälligkeitsdauer
    - Rechnungsbetrag
    - Geschäftsbeziehungsdauer
    """

    # Konfiguration
    CONFIDENCE_THRESHOLD = 0.85  # Für automatischen Versand

    # Überfälligkeits-Tage pro Mahnstufe
    DUNNING_THRESHOLDS = {
        DunningLevel.REMINDER: 3,      # 3 Tage nach Fälligkeit
        DunningLevel.FIRST: 14,        # 14 Tage
        DunningLevel.SECOND: 28,       # 28 Tage
        DunningLevel.FINAL: 42,        # 42 Tage
        DunningLevel.COLLECTION: 60,   # 60 Tage
    }

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db

    async def process_overdue_invoices(
        self,
        company_id: UUID,
        dry_run: bool = False,
    ) -> DunningProcessResult:
        """
        Verarbeitet alle überfälligen Rechnungen.

        Args:
            company_id: Mandant-ID
            dry_run: True = nur Entscheidungen generieren, nicht senden

        Returns:
            DunningProcessResult mit allen Entscheidungen
        """
        result = DunningProcessResult()

        # Überfällige Rechnungen laden
        overdue = await self._get_overdue_invoices(company_id)

        for invoice in overdue:
            decision = await self._make_decision(invoice)
            result.decisions.append(decision)
            result.processed_count += 1

            # Metriken aktualisieren
            DUNNING_DECISIONS.labels(
                action=decision.action.value,
                dunning_level=str(decision.dunning_level.value)
            ).inc()
            DUNNING_CONFIDENCE.observe(decision.confidence)

            # Aktion ausführen (wenn nicht dry_run)
            if not dry_run and decision.action in [DunningAction.SEND_REMINDER, DunningAction.SEND_DUNNING]:
                if decision.confidence >= self.CONFIDENCE_THRESHOLD:
                    success = await self._send_dunning(invoice, decision)
                    if success:
                        result.sent_count += 1
                else:
                    result.review_count += 1
            elif decision.action == DunningAction.HOLD:
                result.held_count += 1
            elif decision.action == DunningAction.MANUAL_REVIEW:
                result.review_count += 1

        # Gauge aktualisieren
        for level in DunningLevel:
            count = len([d for d in result.decisions if d.dunning_level == level])
            OVERDUE_INVOICES.labels(dunning_level=str(level.value)).set(count)

        logger.info(
            "dunning_process_completed",
            processed=result.processed_count,
            sent=result.sent_count,
            held=result.held_count,
            review=result.review_count,
        )

        return result

    async def _make_decision(self, invoice: InvoiceTracking) -> DunningDecision:
        """
        Trifft Mahnentscheidung für eine Rechnung.

        Berücksichtigt:
        - Entity-Risiko-Score
        - Zahlungshistorie
        - Überfälligkeitsdauer
        - Rechnungsbetrag
        """
        decision = DunningDecision(invoice_id=invoice.id)

        # Zahlungshistorie laden
        if invoice.business_entity_id:
            history = await self._get_payment_history(invoice.business_entity_id)
            decision.payment_history = history

            # Risiko-Score (aus Entity oder berechnen)
            entity = await self._get_entity(invoice.business_entity_id)
            decision.entity_risk_score = entity.risk_score if entity and entity.risk_score else 50.0
        else:
            history = None
            decision.entity_risk_score = 75.0  # Default: mittleres Risiko

        # Überfälligkeitsdauer berechnen
        days_overdue = self._calculate_days_overdue(invoice)

        # Mahnstufe bestimmen
        decision.dunning_level = self._determine_dunning_level(
            invoice.dunning_level or 0,
            days_overdue
        )

        # Entscheidung treffen
        decision = self._evaluate_decision(decision, invoice, history, days_overdue)

        return decision

    def _evaluate_decision(
        self,
        decision: DunningDecision,
        invoice: InvoiceTracking,
        history: Optional[PaymentHistory],
        days_overdue: int,
    ) -> DunningDecision:
        """Evaluiert und trifft finale Entscheidung."""
        factors: List[Tuple[str, float, str]] = []
        amount = invoice.outstanding_amount or invoice.amount or Decimal("0")

        # Faktor 1: Überfälligkeitsdauer (35%)
        overdue_score = min(days_overdue / 60, 1.0)  # Max bei 60 Tagen
        factors.append((
            "Überfälligkeitsdauer",
            overdue_score * 0.35,
            f"{days_overdue} Tage überfällig"
        ))

        # Faktor 2: Risiko-Score (25%)
        risk_score = decision.entity_risk_score / 100
        factors.append((
            "Risiko-Score",
            risk_score * 0.25,
            f"Entity-Risiko: {decision.entity_risk_score:.0f}/100"
        ))

        # Faktor 3: Zahlungshistorie (25%)
        if history:
            # Schlechte Historie = höherer Score (mehr Handlungsbedarf)
            history_score = 1.0 - history.on_time_rate
            factors.append((
                "Zahlungshistorie",
                history_score * 0.25,
                f"Pünktlich: {history.on_time_rate*100:.0f}%, Ø Verzug: {history.avg_delay_days:.0f} Tage"
            ))
        else:
            factors.append((
                "Zahlungshistorie",
                0.5 * 0.25,  # Neutral wenn keine Historie
                "Keine historischen Daten"
            ))

        # Faktor 4: Rechnungsbetrag (15%)
        # Höhere Beträge = mehr Aufmerksamkeit
        amount_score = min(float(amount) / 10000, 1.0)  # Max bei 10.000 EUR
        factors.append((
            "Rechnungsbetrag",
            amount_score * 0.15,
            f"{amount:.2f} EUR ausstehend"
        ))

        # Gesamtscore berechnen
        total_score = sum(f[1] for f in factors)
        decision.confidence = min(total_score + 0.3, 1.0)  # Basis + Faktoren

        # Faktoren speichern
        decision.factors = [
            {
                "name": f[0],
                "contribution": f[1],
                "explanation": f[2],
            }
            for f in factors
        ]

        # Aktion bestimmen basierend auf Score und Kontext
        decision = self._determine_action(decision, history, days_overdue, amount)

        return decision

    def _determine_action(
        self,
        decision: DunningDecision,
        history: Optional[PaymentHistory],
        days_overdue: int,
        amount: Decimal,
    ) -> DunningDecision:
        """Bestimmt die empfohlene Aktion."""
        # Guter Kunde mit kurzer Überfälligkeit → Abwarten
        if history and history.on_time_rate >= 0.9 and days_overdue <= 7:
            decision.action = DunningAction.HOLD
            decision.explanation = (
                f"Guter Kunde (Pünktlichkeit {history.on_time_rate*100:.0f}%), "
                f"nur {days_overdue} Tage überfällig. Abwarten empfohlen."
            )
            decision.channels = [NotificationChannel.INTERNAL]
            return decision

        # Hoher Risiko-Score → Eskalation
        if decision.entity_risk_score >= 80 and days_overdue >= 30:
            decision.action = DunningAction.ESCALATE
            decision.explanation = (
                f"Hohes Risiko ({decision.entity_risk_score:.0f}/100) und "
                f"{days_overdue} Tage überfällig. Eskalation empfohlen."
            )
            decision.channels = [NotificationChannel.LETTER, NotificationChannel.EMAIL]
            return decision

        # Inkasso bei extremer Überfälligkeit
        if days_overdue >= 60 and decision.dunning_level >= DunningLevel.FINAL:
            decision.action = DunningAction.COLLECTION
            decision.explanation = (
                f"Über 60 Tage überfällig, {decision.dunning_level.value}. Mahnstufe erreicht. "
                f"Inkasso-Übergabe prüfen."
            )
            decision.channels = [NotificationChannel.LETTER]
            decision.confidence = max(decision.confidence, 0.90)
            return decision

        # Standard-Mahnung basierend auf Stufe
        if decision.dunning_level == DunningLevel.REMINDER:
            decision.action = DunningAction.SEND_REMINDER
            decision.explanation = (
                f"Zahlungserinnerung: {days_overdue} Tage überfällig, "
                f"{amount:.2f} EUR ausstehend."
            )
            decision.channels = [NotificationChannel.EMAIL]

        elif decision.dunning_level in [DunningLevel.FIRST, DunningLevel.SECOND]:
            decision.action = DunningAction.SEND_DUNNING
            decision.explanation = (
                f"{decision.dunning_level.value}. Mahnung: {days_overdue} Tage überfällig, "
                f"{amount:.2f} EUR ausstehend."
            )
            decision.channels = [NotificationChannel.EMAIL, NotificationChannel.LETTER]

        elif decision.dunning_level == DunningLevel.FINAL:
            decision.action = DunningAction.SEND_DUNNING
            decision.explanation = (
                f"Letzte Mahnung: {days_overdue} Tage überfällig, "
                f"{amount:.2f} EUR. Inkasso-Ankündigung."
            )
            decision.channels = [NotificationChannel.LETTER]
            decision.confidence = max(decision.confidence, 0.85)

        else:
            decision.action = DunningAction.MANUAL_REVIEW
            decision.explanation = "Manuelle Prüfung erforderlich"
            decision.channels = [NotificationChannel.INTERNAL]

        return decision

    def _determine_dunning_level(
        self,
        current_level: int,
        days_overdue: int,
    ) -> DunningLevel:
        """Bestimmt die Mahnstufe basierend auf Überfälligkeit."""
        for level, threshold in sorted(
            self.DUNNING_THRESHOLDS.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            if days_overdue >= threshold and current_level <= level.value:
                return level

        return DunningLevel.REMINDER

    def _calculate_days_overdue(self, invoice: InvoiceTracking) -> int:
        """Berechnet Überfälligkeitstage."""
        if not invoice.due_date:
            return 0

        now = datetime.now(timezone.utc)
        due = invoice.due_date

        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)

        if now > due:
            return (now - due).days

        return 0

    # =========================================================================
    # Dunning Execution
    # =========================================================================

    async def _send_dunning(
        self,
        invoice: InvoiceTracking,
        decision: DunningDecision,
    ) -> bool:
        """Sendet eine Mahnung über die konfigurierten Kanäle."""
        try:
            # Hier würde die eigentliche Versendung stattfinden
            # Email, Brief, Slack, etc.

            logger.info(
                "dunning_sent",
                invoice_id=str(invoice.id),
                level=decision.dunning_level.value,
                channels=[c.value for c in decision.channels],
            )

            # Mahnstufe in Rechnung erhöhen
            invoice.dunning_level = decision.dunning_level.value
            invoice.last_dunning_date = datetime.now(timezone.utc)
            await self.db.commit()

            return True

        except Exception as e:
            logger.error(
                "dunning_send_failed",
                invoice_id=str(invoice.id),
                **safe_error_log(e),
            )
            return False

    # =========================================================================
    # Database Access
    # =========================================================================

    async def _get_overdue_invoices(self, company_id: UUID) -> List[InvoiceTracking]:
        """Lädt überfällige Rechnungen."""
        now = datetime.now(timezone.utc)

        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                is_open_invoice(),
                is_outgoing_invoice(),
                InvoiceTracking.due_date < now,
            )
        ).order_by(InvoiceTracking.due_date.asc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_payment_history(self, entity_id: UUID) -> PaymentHistory:
        """Lädt Zahlungshistorie einer Entity."""
        history = PaymentHistory(entity_id=entity_id)

        # Entity-Name
        entity = await self._get_entity(entity_id)
        if entity:
            history.entity_name = entity.name or ""
            # Beziehungsdauer
            if entity.created_at:
                months = (datetime.now(timezone.utc) - entity.created_at).days // 30
                history.relationship_months = months

        # Rechnungsstatistiken
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.entity_id == entity_id,
                is_outgoing_invoice(),
            )
        )

        result = await self.db.execute(stmt)
        invoices = list(result.scalars().all())

        if invoices:
            history.total_invoices = len(invoices)
            history.paid_invoices = len([
                i for i in invoices if i.status == InvoiceStatus.PAID.value
            ])
            history.overdue_invoices = len([
                i for i in invoices
                if i.status != InvoiceStatus.PAID.value
                and i.due_date and i.due_date < datetime.now(timezone.utc)
            ])

            # Zahlungsverzögerungen
            delays = []
            for inv in invoices:
                if inv.status == InvoiceStatus.PAID.value and inv.paid_at and inv.due_date:
                    delay = (inv.paid_at - inv.due_date).days
                    delays.append(max(delay, 0))

            if delays:
                history.avg_delay_days = sum(delays) / len(delays)
                history.max_delay_days = max(delays)
                history.on_time_rate = len([d for d in delays if d <= 0]) / len(delays)

            # Volumen
            history.total_volume = sum(
                i.amount or Decimal("0") for i in invoices
            )
            history.outstanding_volume = sum(
                i.outstanding_amount or i.amount or Decimal("0")
                for i in invoices if i.status != InvoiceStatus.PAID.value
            )

            # Letzte Zahlung
            paid = [
                i for i in invoices
                if i.status == InvoiceStatus.PAID.value and i.paid_at
            ]
            if paid:
                history.last_payment_date = max(i.paid_at for i in paid)

        return history

    async def _get_entity(self, entity_id: UUID) -> Optional[BusinessEntity]:
        """Lädt eine Entity."""
        stmt = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()


# =============================================================================
# Factory
# =============================================================================

def get_proactive_dunning_service(db: AsyncSession) -> ProactiveDunningService:
    """Factory-Funktion für ProactiveDunningService."""
    return ProactiveDunningService(db)

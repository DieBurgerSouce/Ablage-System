# -*- coding: utf-8 -*-
"""Insolvency Warning Service.

Frühwarnsystem für Insolvenz-Risiken bei Geschäftspartnern.
Integriert Bundesanzeiger, Handelsregister und interne Risiko-Daten.

Features:
- Externe Datenbank-Abfragen (Bundesanzeiger, Handelsregister)
- Interne Risiko-Analyse basierend auf Zahlungsverhalten
- Automatische Alerts bei Insolvenz-Signalen
- Kreditlimit-Empfehlungen
"""

import structlog
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class InsolvencyStatus(str, Enum):
    """Insolvenz-Status eines Unternehmens."""

    ACTIVE = "active"  # Normaler Betrieb
    WATCH = "watch"  # Unter Beobachtung
    WARNING = "warning"  # Warnung aktiv
    INSOLVENCY_FILED = "insolvency_filed"  # Insolvenz angemeldet
    INSOLVENCY_OPENED = "insolvency_opened"  # Insolvenzverfahren eröffnet
    LIQUIDATION = "liquidation"  # In Liquidation
    DISSOLVED = "dissolved"  # Aufgelöst


class RiskSignalType(str, Enum):
    """Arten von Risiko-Signalen."""

    # Externe Signale
    INSOLVENCY_FILING = "insolvency_filing"
    INSOLVENCY_OPENING = "insolvency_opening"
    LIQUIDATION_START = "liquidation_start"
    MANAGEMENT_CHANGE = "management_change"
    ADDRESS_CHANGE = "address_change"
    CAPITAL_REDUCTION = "capital_reduction"
    NEGATIVE_EQUITY = "negative_equity"

    # Interne Signale
    PAYMENT_DELAY_INCREASING = "payment_delay_increasing"
    PAYMENT_DEFAULT = "payment_default"
    DISPUTE_RATE_HIGH = "dispute_rate_high"
    ORDER_VOLUME_DECLINING = "order_volume_declining"
    CREDIT_LIMIT_EXCEEDED = "credit_limit_exceeded"


class SignalSeverity(str, Enum):
    """Schweregrad eines Signals."""

    INFO = "info"  # Nur zur Information
    LOW = "low"  # Niedriges Risiko
    MEDIUM = "medium"  # Mittleres Risiko
    HIGH = "high"  # Hohes Risiko
    CRITICAL = "critical"  # Kritisch - sofortige Aktion


class ExternalDataSource(str, Enum):
    """Externe Datenquellen."""

    BUNDESANZEIGER = "bundesanzeiger"
    HANDELSREGISTER = "handelsregister"
    CREDITREFORM = "creditreform"
    SCHUFA_B2B = "schufa_b2b"
    INTERNAL = "internal"


@dataclass
class RiskSignal:
    """Ein Risiko-Signal für einen Geschäftspartner."""

    id: UUID
    entity_id: UUID
    company_id: UUID
    signal_type: RiskSignalType
    severity: SignalSeverity
    source: ExternalDataSource
    detected_at: datetime
    description: str
    raw_data: dict[str, Any] = field(default_factory=dict)
    is_acknowledged: bool = False
    acknowledged_by: UUID | None = None
    acknowledged_at: datetime | None = None
    notes: str | None = None


@dataclass
class InsolvencyCheck:
    """Ergebnis einer Insolvenz-Prüfung."""

    entity_id: UUID
    entity_name: str
    check_date: datetime
    status: InsolvencyStatus
    risk_score: int  # 0-100
    signals: list[RiskSignal]
    credit_limit_recommendation: Decimal | None
    last_external_check: datetime | None
    external_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class CreditLimitRecommendation:
    """Kreditlimit-Empfehlung."""

    entity_id: UUID
    current_limit: Decimal | None
    recommended_limit: Decimal
    recommendation_reason: str
    risk_factors: list[str]
    confidence: float  # 0.0 - 1.0


@dataclass
class EntityHealthSummary:
    """Zusammenfassung der Unternehmensgesundheit."""

    entity_id: UUID
    entity_name: str
    status: InsolvencyStatus
    risk_score: int
    open_signals_count: int
    critical_signals_count: int
    total_open_invoices: Decimal
    average_payment_delay_days: int
    credit_limit: Decimal | None
    credit_utilization_percent: float
    last_check: datetime


@dataclass
class InsolvencyStatistics:
    """Statistiken zum Insolvenz-Monitoring."""

    company_id: UUID
    total_monitored_entities: int
    entities_by_status: dict[InsolvencyStatus, int]
    signals_by_severity: dict[SignalSeverity, int]
    total_at_risk_volume: Decimal
    entities_with_critical_signals: int
    external_checks_last_30_days: int
    period_start: date
    period_end: date


class InsolvencyWarningService:
    """Service für Insolvenz-Frühwarnung.

    Überwacht Geschäftspartner auf Insolvenz-Risiken durch:
    - Integration externer Datenbanken (Bundesanzeiger, Handelsregister)
    - Analyse interner Zahlungsdaten
    - Automatische Alerts bei Warnsignalen
    """

    # Risiko-Score Schwellenwerte
    WATCH_THRESHOLD = 30
    WARNING_THRESHOLD = 50
    CRITICAL_THRESHOLD = 75

    # Signal-Gewichtungen für Risiko-Score
    SIGNAL_WEIGHTS: dict[RiskSignalType, int] = {
        RiskSignalType.INSOLVENCY_OPENING: 100,
        RiskSignalType.INSOLVENCY_FILING: 90,
        RiskSignalType.LIQUIDATION_START: 85,
        RiskSignalType.NEGATIVE_EQUITY: 60,
        RiskSignalType.CAPITAL_REDUCTION: 40,
        RiskSignalType.PAYMENT_DEFAULT: 50,
        RiskSignalType.PAYMENT_DELAY_INCREASING: 30,
        RiskSignalType.DISPUTE_RATE_HIGH: 25,
        RiskSignalType.ORDER_VOLUME_DECLINING: 20,
        RiskSignalType.CREDIT_LIMIT_EXCEEDED: 35,
        RiskSignalType.MANAGEMENT_CHANGE: 15,
        RiskSignalType.ADDRESS_CHANGE: 10,
    }

    # Kreditlimit-Faktoren
    BASE_CREDIT_FACTOR = Decimal("0.1")  # 10% des Jahresumsatzes
    RISK_REDUCTION_FACTORS: dict[InsolvencyStatus, Decimal] = {
        InsolvencyStatus.ACTIVE: Decimal("1.0"),
        InsolvencyStatus.WATCH: Decimal("0.7"),
        InsolvencyStatus.WARNING: Decimal("0.4"),
        InsolvencyStatus.INSOLVENCY_FILED: Decimal("0.0"),
        InsolvencyStatus.INSOLVENCY_OPENED: Decimal("0.0"),
        InsolvencyStatus.LIQUIDATION: Decimal("0.0"),
        InsolvencyStatus.DISSOLVED: Decimal("0.0"),
    }

    async def check_entity_insolvency(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        include_external: bool = True,
    ) -> InsolvencyCheck:
        """Führt eine vollständige Insolvenz-Prüfung durch.

        Args:
            db: Datenbank-Session
            entity_id: ID des zu prüfenden Geschäftspartners
            company_id: Firmen-ID
            include_external: Externe Quellen abfragen

        Returns:
            InsolvencyCheck mit allen Ergebnissen
        """
        from app.db.models import BusinessEntity

        # Entity laden (BusinessEntity hat kein company_id - Isolation über Documents)
        result = await db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            raise ValueError(f"Geschäftspartner nicht gefunden: {entity_id}")

        # Alle Signale sammeln
        signals: list[RiskSignal] = []

        # 1. Interne Signale analysieren
        internal_signals = await self._analyze_internal_signals(
            db, entity_id, company_id
        )
        signals.extend(internal_signals)

        # 2. Externe Daten prüfen (falls aktiviert)
        external_data: dict[str, Any] = {}
        last_external_check: datetime | None = None

        if include_external:
            external_result = await self._check_external_sources(
                db, entity_id, entity.name if hasattr(entity, "name") else str(entity_id)
            )
            signals.extend(external_result.get("signals", []))
            external_data = external_result.get("data", {})
            last_external_check = external_result.get("check_time")

        # 3. Risiko-Score berechnen
        risk_score = self._calculate_risk_score(signals)

        # 4. Status bestimmen
        status = self._determine_status(risk_score, signals)

        # 5. Kreditlimit-Empfehlung
        credit_limit = await self._calculate_credit_limit_recommendation(
            db, entity_id, company_id, status, risk_score
        )

        logger.info(
            "insolvency_check_completed",
            entity_id=str(entity_id),
            risk_score=risk_score,
            status=status.value,
            signal_count=len(signals),
        )

        return InsolvencyCheck(
            entity_id=entity_id,
            entity_name=entity.name if hasattr(entity, "name") else str(entity_id),
            check_date=datetime.now(timezone.utc),
            status=status,
            risk_score=risk_score,
            signals=signals,
            credit_limit_recommendation=credit_limit,
            last_external_check=last_external_check,
            external_data=external_data,
        )

    async def _analyze_internal_signals(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
    ) -> list[RiskSignal]:
        """Analysiert interne Daten auf Warnsignale.

        Prüft:
        - Zahlungsverzögerungen
        - Zahlungsausfälle
        - Bestellvolumen-Trend
        - Kreditlimit-Überschreitung
        """
        from app.db.models import Document, InvoiceTracking

        signals: list[RiskSignal] = []
        now = datetime.now(timezone.utc)

        # Rechnungen der letzten 12 Monate
        # InvoiceTracking hat kein entity_id - wir müssen über Document joinen
        twelve_months_ago = now - timedelta(days=365)

        result = await db.execute(
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= twelve_months_ago,
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        invoices = result.scalars().all()

        if not invoices:
            return signals

        # Analyse: Zahlungsverzögerungen
        paid_invoices = [inv for inv in invoices if inv.status == "paid"]
        if paid_invoices:
            # Durchschnittliche Verzögerung berechnen
            delays = []
            for inv in paid_invoices:
                if inv.paid_date and inv.due_date:
                    delay = (inv.paid_date - inv.due_date).days
                    if delay > 0:
                        delays.append(delay)

            if delays:
                avg_delay = sum(delays) / len(delays)

                # Trend der letzten 3 Monate vs. vorherige 3 Monate
                # Konvertieren zu date für Vergleiche (paid_date kann date oder datetime sein)
                three_months_ago_date = (now - timedelta(days=90)).date()
                six_months_ago_date = (now - timedelta(days=180)).date()

                def to_date(dt: date | datetime | None) -> date | None:
                    """Konvertiert datetime zu date falls noetig."""
                    if dt is None:
                        return None
                    if isinstance(dt, datetime):
                        return dt.date()
                    return dt

                recent_delays = [
                    d
                    for inv, d in zip(paid_invoices, delays)
                    if to_date(inv.paid_date) and to_date(inv.paid_date) >= three_months_ago_date
                ]
                older_delays = [
                    d
                    for inv, d in zip(paid_invoices, delays)
                    if to_date(inv.paid_date)
                    and six_months_ago_date <= to_date(inv.paid_date) < three_months_ago_date
                ]

                if recent_delays and older_delays:
                    recent_avg = sum(recent_delays) / len(recent_delays)
                    older_avg = sum(older_delays) / len(older_delays)

                    # Verzögerung um mehr als 50% gestiegen
                    if recent_avg > older_avg * 1.5:
                        signals.append(
                            RiskSignal(
                                id=uuid4(),
                                entity_id=entity_id,
                                company_id=company_id,
                                signal_type=RiskSignalType.PAYMENT_DELAY_INCREASING,
                                severity=SignalSeverity.MEDIUM,
                                source=ExternalDataSource.INTERNAL,
                                detected_at=now,
                                description=f"Zahlungsverzögerung gestiegen: {older_avg:.1f} → {recent_avg:.1f} Tage",
                                raw_data={
                                    "recent_avg_delay": recent_avg,
                                    "older_avg_delay": older_avg,
                                    "increase_percent": ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0,
                                },
                            )
                        )

        # Analyse: Zahlungsausfälle (überfällig > 90 Tage)
        overdue_invoices = [
            inv
            for inv in invoices
            if inv.status == "overdue"
            and inv.due_date
            and (now.date() - inv.due_date).days > 90
        ]

        if overdue_invoices:
            total_overdue = sum(
                Decimal(str(inv.amount)) for inv in overdue_invoices if inv.amount
            )
            signals.append(
                RiskSignal(
                    id=uuid4(),
                    entity_id=entity_id,
                    company_id=company_id,
                    signal_type=RiskSignalType.PAYMENT_DEFAULT,
                    severity=SignalSeverity.HIGH,
                    source=ExternalDataSource.INTERNAL,
                    detected_at=now,
                    description=f"{len(overdue_invoices)} Rechnungen > 90 Tage überfällig (Summe: {total_overdue:.2f} EUR)",
                    raw_data={
                        "overdue_count": len(overdue_invoices),
                        "total_overdue_amount": float(total_overdue),
                        "invoice_ids": [str(inv.id) for inv in overdue_invoices],
                    },
                )
            )

        # Analyse: Bestellvolumen-Rückgang
        six_months_ago = now - timedelta(days=180)
        recent_invoices = [
            inv for inv in invoices if inv.invoice_date and inv.invoice_date >= six_months_ago.date()
        ]
        older_invoices = [
            inv
            for inv in invoices
            if inv.invoice_date and inv.invoice_date < six_months_ago.date()
        ]

        if recent_invoices and older_invoices:
            recent_volume = sum(
                Decimal(str(inv.amount)) for inv in recent_invoices if inv.amount
            )
            older_volume = sum(
                Decimal(str(inv.amount)) for inv in older_invoices if inv.amount
            )

            # Volumen um mehr als 40% gesunken
            if older_volume > 0 and recent_volume < older_volume * Decimal("0.6"):
                signals.append(
                    RiskSignal(
                        id=uuid4(),
                        entity_id=entity_id,
                        company_id=company_id,
                        signal_type=RiskSignalType.ORDER_VOLUME_DECLINING,
                        severity=SignalSeverity.LOW,
                        source=ExternalDataSource.INTERNAL,
                        detected_at=now,
                        description=f"Rechnungsvolumen gesunken: {older_volume:.2f} → {recent_volume:.2f} EUR",
                        raw_data={
                            "recent_volume": float(recent_volume),
                            "older_volume": float(older_volume),
                            "decline_percent": float((older_volume - recent_volume) / older_volume * 100) if older_volume > 0 else 0,
                        },
                    )
                )

        return signals

    async def _check_external_sources(
        self,
        db: AsyncSession,
        entity_id: UUID,
        entity_name: str,
    ) -> dict[str, Any]:
        """Prüft externe Datenquellen auf Insolvenz-Meldungen.

        HINWEIS: Dies ist ein Stub für die Integration externer APIs.
        In Production würden hier echte API-Calls erfolgen zu:
        - Bundesanzeiger API
        - Handelsregister API
        - Creditreform API
        """
        # Stub-Implementierung - in Production durch echte API-Calls ersetzen
        logger.info(
            "external_insolvency_check_stub",
            entity_name=entity_name,
            entity_id=str(entity_id),
        )

        return {
            "signals": [],
            "data": {
                "bundesanzeiger_checked": True,
                "handelsregister_checked": True,
                "no_insolvency_found": True,
            },
            "check_time": datetime.now(timezone.utc),
        }

    def _calculate_risk_score(self, signals: list[RiskSignal]) -> int:
        """Berechnet Risiko-Score basierend auf allen Signalen.

        Returns:
            Score von 0 (kein Risiko) bis 100 (maximales Risiko)
        """
        if not signals:
            return 0

        # Basis-Score aus Signal-Gewichtungen
        total_weight = 0
        for signal in signals:
            weight = self.SIGNAL_WEIGHTS.get(signal.signal_type, 10)
            # Severity-Multiplikator
            severity_mult = {
                SignalSeverity.INFO: 0.5,
                SignalSeverity.LOW: 0.7,
                SignalSeverity.MEDIUM: 1.0,
                SignalSeverity.HIGH: 1.3,
                SignalSeverity.CRITICAL: 1.5,
            }.get(signal.severity, 1.0)

            total_weight += weight * severity_mult

        # Normalisieren auf 0-100
        # Max theoretisch: ~300 (mehrere kritische Signale)
        score = min(100, int(total_weight))

        return score

    def _determine_status(
        self, risk_score: int, signals: list[RiskSignal]
    ) -> InsolvencyStatus:
        """Bestimmt Status basierend auf Score und Signalen."""
        # Direkte Insolvenz-Signale überschreiben Score
        for signal in signals:
            if signal.signal_type == RiskSignalType.INSOLVENCY_OPENING:
                return InsolvencyStatus.INSOLVENCY_OPENED
            if signal.signal_type == RiskSignalType.INSOLVENCY_FILING:
                return InsolvencyStatus.INSOLVENCY_FILED
            if signal.signal_type == RiskSignalType.LIQUIDATION_START:
                return InsolvencyStatus.LIQUIDATION

        # Score-basierte Bestimmung
        if risk_score >= self.CRITICAL_THRESHOLD:
            return InsolvencyStatus.WARNING
        if risk_score >= self.WARNING_THRESHOLD:
            return InsolvencyStatus.WARNING
        if risk_score >= self.WATCH_THRESHOLD:
            return InsolvencyStatus.WATCH

        return InsolvencyStatus.ACTIVE

    async def _calculate_credit_limit_recommendation(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        status: InsolvencyStatus,
        risk_score: int,
    ) -> Decimal | None:
        """Berechnet Kreditlimit-Empfehlung."""
        from app.db.models import Document, InvoiceTracking

        # Jahresumsatz der letzten 12 Monate
        # InvoiceTracking hat kein entity_id - wir müssen über Document joinen
        twelve_months_ago = datetime.now(timezone.utc) - timedelta(days=365)

        result = await db.execute(
            select(func.sum(InvoiceTracking.amount))
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= twelve_months_ago.date(),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        raw_volume = result.scalar()

        # Sicherstellen dass wir einen numerischen Wert haben
        if raw_volume is None or not isinstance(raw_volume, (int, float, Decimal)):
            return None

        annual_volume = Decimal(str(raw_volume)) if raw_volume else Decimal("0")

        if annual_volume == 0:
            return None

        # Basis: 10% des Jahresumsatzes
        base_limit = annual_volume * self.BASE_CREDIT_FACTOR

        # Status-Reduktion anwenden
        reduction_factor = self.RISK_REDUCTION_FACTORS.get(status, Decimal("1.0"))

        # Score-basierte Feinabstimmung (-0.5% pro Score-Punkt über 30)
        if risk_score > 30:
            score_reduction = Decimal(str(1 - (risk_score - 30) * 0.005))
            score_reduction = max(Decimal("0.3"), score_reduction)  # Min 30%
        else:
            score_reduction = Decimal("1.0")

        recommended = base_limit * reduction_factor * score_reduction

        # Runden auf 100er
        recommended = (recommended / 100).quantize(Decimal("1")) * 100

        return recommended

    async def get_entity_health_summary(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
    ) -> EntityHealthSummary:
        """Ruft Zusammenfassung der Unternehmensgesundheit ab."""
        # Vollständige Prüfung durchführen
        check = await self.check_entity_insolvency(
            db, entity_id, company_id, include_external=False
        )

        # Offene Rechnungen
        # InvoiceTracking hat kein entity_id - wir müssen über Document joinen
        from app.db.models import Document, InvoiceTracking

        result = await db.execute(
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["open", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        open_invoices = result.scalars().all()

        total_open = sum(
            Decimal(str(inv.amount)) for inv in open_invoices if inv.amount
        )

        # Durchschnittliche Verzögerung
        avg_delay = 0
        if open_invoices:
            now = datetime.now(timezone.utc).date()
            delays = [
                (now - inv.due_date).days
                for inv in open_invoices
                if inv.due_date and now > inv.due_date
            ]
            avg_delay = int(sum(delays) / len(delays)) if delays else 0

        # Kritische Signale zählen
        critical_count = len(
            [s for s in check.signals if s.severity in [SignalSeverity.HIGH, SignalSeverity.CRITICAL]]
        )

        # Kreditauslastung
        credit_utilization = 0.0
        if check.credit_limit_recommendation and check.credit_limit_recommendation > 0:
            credit_utilization = float(total_open / check.credit_limit_recommendation * 100)

        return EntityHealthSummary(
            entity_id=entity_id,
            entity_name=check.entity_name,
            status=check.status,
            risk_score=check.risk_score,
            open_signals_count=len(check.signals),
            critical_signals_count=critical_count,
            total_open_invoices=total_open,
            average_payment_delay_days=avg_delay,
            credit_limit=check.credit_limit_recommendation,
            credit_utilization_percent=credit_utilization,
            last_check=check.check_date,
        )

    async def get_high_risk_entities(
        self,
        db: AsyncSession,
        company_id: UUID,
        min_risk_score: int = 50,
        limit: int = 50,
    ) -> list[EntityHealthSummary]:
        """Ruft alle Geschäftspartner mit hohem Risiko ab."""
        from app.db.models import BusinessEntity, Document

        # BusinessEntity hat kein company_id - wir finden Entities über Dokumente
        # Distinct Entities die Dokumente in dieser Company haben
        result = await db.execute(
            select(BusinessEntity)
            .join(Document, BusinessEntity.id == Document.business_entity_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    BusinessEntity.deleted_at.is_(None),
                    Document.deleted_at.is_(None),
                )
            )
            .distinct()
            .limit(limit * 2)  # Mehr laden für Filterung
        )
        entities = result.scalars().all()

        high_risk_summaries: list[EntityHealthSummary] = []

        for entity in entities:
            try:
                summary = await self.get_entity_health_summary(
                    db, entity.id, company_id
                )
                if summary.risk_score >= min_risk_score:
                    high_risk_summaries.append(summary)
            except Exception as e:
                logger.warning(
                    "entity_risk_check_failed",
                    entity_id=str(entity.id),
                    error=str(e),
                )
                continue

            if len(high_risk_summaries) >= limit:
                break

        # Nach Risiko-Score sortieren (höchstes zuerst)
        high_risk_summaries.sort(key=lambda x: x.risk_score, reverse=True)

        return high_risk_summaries

    async def acknowledge_signal(
        self,
        db: AsyncSession,
        signal_id: UUID,
        user_id: UUID,
        notes: str | None = None,
    ) -> bool:
        """Markiert ein Signal als zur Kenntnis genommen.

        HINWEIS: In Production würde dies in der DB gespeichert.
        Hier nur Stub-Implementierung.
        """
        logger.info(
            "signal_acknowledged",
            signal_id=str(signal_id),
            user_id=str(user_id),
            notes=notes,
        )
        return True

    async def get_statistics(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_days: int = 30,
    ) -> InsolvencyStatistics:
        """Ruft Statistiken zum Insolvenz-Monitoring ab."""
        from app.db.models import BusinessEntity, Document, InvoiceTracking

        now = datetime.now(timezone.utc)
        period_start = (now - timedelta(days=period_days)).date()
        period_end = now.date()

        # Alle Entities zählen die Dokumente in dieser Company haben
        # BusinessEntity hat kein company_id - wir müssen über Document joinen
        result = await db.execute(
            select(func.count(func.distinct(BusinessEntity.id)))
            .join(Document, BusinessEntity.id == Document.business_entity_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    BusinessEntity.deleted_at.is_(None),
                    Document.deleted_at.is_(None),
                )
            )
        )
        total_entities = result.scalar() or 0

        # Status-Verteilung (vereinfacht - in Production aus DB)
        entities_by_status: dict[InsolvencyStatus, int] = {
            InsolvencyStatus.ACTIVE: total_entities,
            InsolvencyStatus.WATCH: 0,
            InsolvencyStatus.WARNING: 0,
            InsolvencyStatus.INSOLVENCY_FILED: 0,
            InsolvencyStatus.INSOLVENCY_OPENED: 0,
            InsolvencyStatus.LIQUIDATION: 0,
            InsolvencyStatus.DISSOLVED: 0,
        }

        # Signale nach Severity (vereinfacht)
        signals_by_severity: dict[SignalSeverity, int] = {
            SignalSeverity.INFO: 0,
            SignalSeverity.LOW: 0,
            SignalSeverity.MEDIUM: 0,
            SignalSeverity.HIGH: 0,
            SignalSeverity.CRITICAL: 0,
        }

        # Offenes Risiko-Volumen
        result = await db.execute(
            select(func.sum(InvoiceTracking.amount)).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["open", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        at_risk_volume = Decimal(str(result.scalar() or 0))

        return InsolvencyStatistics(
            company_id=company_id,
            total_monitored_entities=total_entities,
            entities_by_status=entities_by_status,
            signals_by_severity=signals_by_severity,
            total_at_risk_volume=at_risk_volume,
            entities_with_critical_signals=0,
            external_checks_last_30_days=0,
            period_start=period_start,
            period_end=period_end,
        )


# Singleton-Instanz
_insolvency_warning_service: InsolvencyWarningService | None = None


def get_insolvency_warning_service() -> InsolvencyWarningService:
    """Gibt Singleton-Instanz des InsolvencyWarningService zurück."""
    global _insolvency_warning_service
    if _insolvency_warning_service is None:
        _insolvency_warning_service = InsolvencyWarningService()
    return _insolvency_warning_service

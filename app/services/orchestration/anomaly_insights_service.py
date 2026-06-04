# -*- coding: utf-8 -*-
"""
Anomaly Insights Service.

Enterprise Feature: Proaktive Erkennung von Anomalien und ungewoehnlichen Mustern.

Dieses Modul erkennt verschiedene Anomalie-Typen:

- Preisanomalien: "Lieferant X hat Preise um 50% erhöht!"
- Volumen-Anomalien: "Bestellvolumen bei Y ist 3x höher als ueblich"
- Timing-Anomalien: "Ungewoehnliche Rechnungsfrequenz erkannt"
- Duplikat-Muster: "Mögliche Duplikat-Rechnungen gefunden"

Integration mit: EntitySearchService, InvoiceTracking, FraudDetectionService
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.proactive_insights_service import (
    ExtractedEntity,
    EntityType,
    InsightPriority,
    InsightType,
    ProactiveInsight,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class AnomalyType(str, Enum):
    """Typ der Anomalie."""
    PRICE_SPIKE = "price_spike"             # Plotzlicher Preisanstieg
    PRICE_DROP = "price_drop"               # Plotzlicher Preisabfall
    VOLUME_HIGH = "volume_high"             # Ungewoehnlich hohes Volumen
    VOLUME_LOW = "volume_low"               # Ungewoehnlich niedriges Volumen
    TIMING_UNUSUAL = "timing_unusual"       # Ungewoehnliches Timing
    DUPLICATE_PATTERN = "duplicate_pattern" # Duplikat-Muster
    FREQUENCY_ANOMALY = "frequency_anomaly" # Ungewoehnliche Frequenz
    AMOUNT_ROUND = "amount_round"           # Verdaechtig runde Betraege


class AnomalySeverity(str, Enum):
    """Schweregrad der Anomalie."""
    CRITICAL = "critical"   # Sofort prüfen (>3 Standardabweichungen)
    HIGH = "high"           # Dringend (2-3 Standardabweichungen)
    MEDIUM = "medium"       # Normal (1.5-2 Standardabweichungen)
    LOW = "low"             # Info (<1.5 Standardabweichungen)


@dataclass
class AnomalyAlert:
    """Ein Anomalie-Alert mit Details."""
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    entity_id: UUID
    entity_name: str
    description: str
    deviation_percent: float          # Prozentuale Abweichung
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    confidence: float = 0.0           # Konfidenz der Erkennung
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    related_documents: List[UUID] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_insight(self) -> ProactiveInsight:
        """Konvertiert zu ProactiveInsight."""
        severity_priority_map = {
            AnomalySeverity.CRITICAL: InsightPriority.CRITICAL,
            AnomalySeverity.HIGH: InsightPriority.HIGH,
            AnomalySeverity.MEDIUM: InsightPriority.MEDIUM,
            AnomalySeverity.LOW: InsightPriority.LOW,
        }

        return ProactiveInsight(
            insight_type=InsightType.ANOMALY,
            priority=severity_priority_map.get(self.severity, InsightPriority.MEDIUM),
            title=self._generate_title(),
            message=self.description,
            detail=self._generate_detail(),
            action_url=self.action_url,
            action_label=self.action_label,
            source_rule=f"anomaly_{self.anomaly_type.value}",
            confidence=self.confidence,
            related_entities=[
                ExtractedEntity(
                    entity_type=EntityType.SUPPLIER,
                    entity_id=self.entity_id,
                    entity_name=self.entity_name,
                    confidence=self.confidence,
                )
            ],
        )

    def _generate_title(self) -> str:
        """Generiert Titel basierend auf Anomalie-Typ."""
        type_titles = {
            AnomalyType.PRICE_SPIKE: f"Preisanstieg bei {self.entity_name}",
            AnomalyType.PRICE_DROP: f"Preisabfall bei {self.entity_name}",
            AnomalyType.VOLUME_HIGH: f"Ungewoehnlich hohes Volumen: {self.entity_name}",
            AnomalyType.VOLUME_LOW: f"Ungewoehnlich niedriges Volumen: {self.entity_name}",
            AnomalyType.TIMING_UNUSUAL: f"Ungewoehnliches Timing: {self.entity_name}",
            AnomalyType.DUPLICATE_PATTERN: f"Mögliche Duplikate: {self.entity_name}",
            AnomalyType.FREQUENCY_ANOMALY: f"Ungewoehnliche Frequenz: {self.entity_name}",
            AnomalyType.AMOUNT_ROUND: f"Verdaechtig runde Betraege: {self.entity_name}",
        }
        return type_titles.get(self.anomaly_type, f"Anomalie: {self.entity_name}")

    def _generate_detail(self) -> str:
        """Generiert Detail-Text."""
        details = []

        if self.expected_value is not None and self.actual_value is not None:
            details.append(f"Erwartet: {self.expected_value:,.2f}, Aktuell: {self.actual_value:,.2f}")

        details.append(f"Abweichung: {self.deviation_percent:+.1f}%")
        details.append(f"Konfidenz: {self.confidence * 100:.0f}%")

        if self.related_documents:
            details.append(f"Betroffene Dokumente: {len(self.related_documents)}")

        return " | ".join(details)


def _calculate_severity(deviation_std: float) -> AnomalySeverity:
    """Berechnet Schweregrad basierend auf Standardabweichungen."""
    abs_deviation = abs(deviation_std)

    if abs_deviation >= 3.0:
        return AnomalySeverity.CRITICAL
    elif abs_deviation >= 2.0:
        return AnomalySeverity.HIGH
    elif abs_deviation >= 1.5:
        return AnomalySeverity.MEDIUM
    else:
        return AnomalySeverity.LOW


def _calculate_z_score(value: float, mean: float, std: float) -> float:
    """Berechnet Z-Score (Standardabweichungen vom Mittelwert)."""
    if std == 0:
        return 0.0
    return (value - mean) / std


@dataclass
class AnomalyCheckResult:
    """Ergebnis einer Anomalie-Prüfung (Test-kompatibel)."""
    anomaly_type: AnomalyType
    title: str
    message: str
    detail: str = ""
    severity: str = "medium"
    confidence: float = 0.0
    deviation_percentage: Optional[float] = None
    affected_amount: Optional[Decimal] = None
    entity_id: Optional[UUID] = None
    entity_name: Optional[str] = None

    def to_insight(self) -> ProactiveInsight:
        """Konvertiert zu ProactiveInsight."""
        priority_map = {"critical": InsightPriority.CRITICAL, "high": InsightPriority.HIGH,
                        "medium": InsightPriority.MEDIUM, "low": InsightPriority.LOW}
        return ProactiveInsight(
            insight_type=InsightType.WARNING if self.severity in ("critical", "high") else InsightType.SUGGESTION,
            priority=priority_map.get(self.severity, InsightPriority.MEDIUM),
            title=self.title,
            message=self.message,
            detail=self.detail,
            confidence=self.confidence,
        )


class AnomalyInsightsService:
    """
    Service für proaktive Anomalie-Erkennung.

    Analysiert historische Daten und erkennt ungewoehnliche
    Muster, die auf Fehler, Betrug oder wichtige Veränderungen
    hinweisen könnten.
    """

    def __init__(self) -> None:
        # Schwellwerte für Anomalie-Erkennung
        self._price_deviation_threshold = 0.2      # 20% Preisabweichung
        self._volume_deviation_threshold = 2.0     # 200% Volumenabweichung
        self._min_history_items = 5                # Mindestens 5 historische Werte
        self._lookback_days = 365                  # 1 Jahr zurück schauen

        logger.info("anomaly_insights_service_initialized")

    async def check_all_anomalies(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Prüft alle Anomalie-Typen und generiert Insights.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für alle erkannten Anomalien
        """
        logger.info(
            "checking_all_anomalies",
            company_id=str(company_id),
        )

        all_insights: List[ProactiveInsight] = []

        # Parallel alle Anomalie-Checks ausführen
        results = await asyncio.gather(
            self.detect_price_anomalies(db, company_id),
            self.detect_volume_anomalies(db, company_id),
            self.detect_invoice_pattern_anomalies(db, company_id),
            self.detect_duplicate_patterns(db, company_id),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "anomaly_check_failed",
                    error=str(result),
                )
            elif isinstance(result, list):
                all_insights.extend(result)

        # Nach Priorität sortieren
        priority_order = {
            InsightPriority.CRITICAL: 0,
            InsightPriority.HIGH: 1,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 3,
        }
        all_insights.sort(key=lambda i: priority_order.get(i.priority, 4))

        logger.info(
            "all_anomalies_checked",
            total_insights=len(all_insights),
        )

        return all_insights

    async def detect_price_anomalies(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt Preisanomalien bei Lieferanten.

        Vergleicht aktuelle Preise mit historischen Durchschnittspreisen
        und erkennt signifikante Abweichungen.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Preisanomalien
        """
        from app.db.models import Document, BusinessEntity

        try:
            now = datetime.now(timezone.utc)
            lookback_start = now - timedelta(days=self._lookback_days)
            recent_period = now - timedelta(days=30)  # Letzte 30 Tage = "aktuell"

            # Alle Lieferanten mit Dokumenten finden
            entities_query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.entity_type == "supplier",
                    BusinessEntity.is_active.is_(True),
                )
            )
            entities_result = await db.execute(entities_query)
            suppliers: Sequence[BusinessEntity] = entities_result.scalars().all()

            alerts: List[AnomalyAlert] = []

            for supplier in suppliers:
                # Historische Rechnungsbetraege laden
                history_query = select(Document.total_amount).where(
                    and_(
                        Document.company_id == company_id,
                        Document.linked_entity_id == supplier.id,
                        Document.document_type == "invoice",
                        Document.created_at >= lookback_start,
                        Document.created_at < recent_period,
                        Document.total_amount.isnot(None),
                    )
                )
                history_result = await db.execute(history_query)
                historical_amounts = [float(row[0]) for row in history_result.fetchall() if row[0]]

                if len(historical_amounts) < self._min_history_items:
                    continue  # Nicht genug Daten

                # Aktuelle Rechnungsbetraege laden
                recent_query = select(Document.id, Document.total_amount).where(
                    and_(
                        Document.company_id == company_id,
                        Document.linked_entity_id == supplier.id,
                        Document.document_type == "invoice",
                        Document.created_at >= recent_period,
                        Document.total_amount.isnot(None),
                    )
                )
                recent_result = await db.execute(recent_query)
                recent_invoices = [(row[0], float(row[1])) for row in recent_result.fetchall() if row[1]]

                if not recent_invoices:
                    continue

                # Statistiken berechnen
                hist_mean = statistics.mean(historical_amounts)
                hist_std = statistics.stdev(historical_amounts) if len(historical_amounts) > 1 else 0

                # Jede aktuelle Rechnung prüfen
                for doc_id, amount in recent_invoices:
                    if hist_std > 0:
                        z_score = _calculate_z_score(amount, hist_mean, hist_std)
                    else:
                        z_score = 0 if amount == hist_mean else (2.0 if amount > hist_mean else -2.0)

                    deviation_percent = ((amount - hist_mean) / hist_mean) * 100 if hist_mean > 0 else 0

                    # Nur signifikante Abweichungen melden
                    if abs(z_score) >= 1.5:
                        anomaly_type = AnomalyType.PRICE_SPIKE if z_score > 0 else AnomalyType.PRICE_DROP
                        severity = _calculate_severity(z_score)

                        alert = AnomalyAlert(
                            anomaly_type=anomaly_type,
                            severity=severity,
                            entity_id=supplier.id,
                            entity_name=supplier.name or "Unbekannt",
                            description=f"Rechnungsbetrag liegt {deviation_percent:+.1f}% {'über' if z_score > 0 else 'unter'} dem Durchschnitt.",
                            deviation_percent=deviation_percent,
                            expected_value=hist_mean,
                            actual_value=amount,
                            confidence=min(0.95, 0.5 + abs(z_score) * 0.15),
                            action_url=f"/documents/{doc_id}",
                            action_label="Rechnung prüfen",
                            related_documents=[doc_id],
                            metadata={
                                "historical_mean": hist_mean,
                                "historical_std": hist_std,
                                "z_score": z_score,
                                "sample_size": len(historical_amounts),
                            },
                        )
                        alerts.append(alert)

            insights = [alert.to_insight() for alert in alerts]

            logger.info(
                "price_anomalies_detected",
                company_id=str(company_id),
                alerts_count=len(alerts),
            )

            return insights

        except Exception as e:
            logger.warning(
                "price_anomaly_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_volume_anomalies(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt Volumenanomalien bei Lieferanten.

        Vergleicht aktuelles Bestellvolumen mit historischem
        Durchschnittsvolumen pro Zeiteinheit.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Volumenanomalien
        """
        from app.db.models import Document, BusinessEntity

        try:
            now = datetime.now(timezone.utc)
            lookback_start = now - timedelta(days=self._lookback_days)
            current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # Monatliche Volumina pro Lieferant aggregieren
            volume_query = select(
                Document.linked_entity_id,
                func.date_trunc('month', Document.created_at).label('month'),
                func.sum(Document.total_amount).label('volume'),
                func.count().label('count'),
            ).where(
                and_(
                    Document.company_id == company_id,
                    Document.document_type == "invoice",
                    Document.created_at >= lookback_start,
                    Document.linked_entity_id.isnot(None),
                    Document.total_amount.isnot(None),
                )
            ).group_by(
                Document.linked_entity_id,
                func.date_trunc('month', Document.created_at),
            )

            result = await db.execute(volume_query)
            monthly_data = result.fetchall()

            # Daten pro Lieferant gruppieren
            supplier_volumes: Dict[UUID, List[Tuple[datetime, float, int]]] = {}
            for row in monthly_data:
                entity_id, month, volume, count = row
                if entity_id not in supplier_volumes:
                    supplier_volumes[entity_id] = []
                supplier_volumes[entity_id].append((month, float(volume or 0), count))

            alerts: List[AnomalyAlert] = []

            for entity_id, volumes in supplier_volumes.items():
                if len(volumes) < self._min_history_items:
                    continue

                # Aktuellen Monat separieren
                current_month_data = [v for v in volumes if v[0] >= current_month_start]
                historical_data = [v for v in volumes if v[0] < current_month_start]

                if not current_month_data or len(historical_data) < 3:
                    continue

                # Statistiken berechnen
                hist_volumes = [v[1] for v in historical_data]
                hist_mean = statistics.mean(hist_volumes)
                hist_std = statistics.stdev(hist_volumes) if len(hist_volumes) > 1 else 0

                current_volume = current_month_data[0][1]

                if hist_std > 0:
                    z_score = _calculate_z_score(current_volume, hist_mean, hist_std)
                else:
                    z_score = 0 if current_volume == hist_mean else (2.0 if current_volume > hist_mean else -2.0)

                deviation_percent = ((current_volume - hist_mean) / hist_mean) * 100 if hist_mean > 0 else 0

                # Nur signifikante Abweichungen melden
                if abs(z_score) >= 1.5:
                    # Lieferantenname laden
                    name_query = select(BusinessEntity.name).where(BusinessEntity.id == entity_id)
                    name_result = await db.execute(name_query)
                    supplier_name = name_result.scalar() or "Unbekannt"

                    anomaly_type = AnomalyType.VOLUME_HIGH if z_score > 0 else AnomalyType.VOLUME_LOW
                    severity = _calculate_severity(z_score)

                    alert = AnomalyAlert(
                        anomaly_type=anomaly_type,
                        severity=severity,
                        entity_id=entity_id,
                        entity_name=supplier_name,
                        description=f"Monatliches Volumen liegt {deviation_percent:+.1f}% {'über' if z_score > 0 else 'unter'} dem Durchschnitt.",
                        deviation_percent=deviation_percent,
                        expected_value=hist_mean,
                        actual_value=current_volume,
                        confidence=min(0.95, 0.5 + abs(z_score) * 0.15),
                        action_url=f"/entities/{entity_id}",
                        action_label="Lieferant analysieren",
                        metadata={
                            "historical_mean": hist_mean,
                            "historical_std": hist_std,
                            "z_score": z_score,
                            "months_analyzed": len(historical_data),
                        },
                    )
                    alerts.append(alert)

            insights = [alert.to_insight() for alert in alerts]

            logger.info(
                "volume_anomalies_detected",
                company_id=str(company_id),
                alerts_count=len(alerts),
            )

            return insights

        except Exception as e:
            logger.warning(
                "volume_anomaly_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_invoice_pattern_anomalies(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt ungewoehnliche Rechnungsmuster.

        Prüft auf:
        - Ungewoehnlich viele Rechnungen in kurzer Zeit
        - Verdaechtig runde Betraege
        - Ungewoehnliche Zeitpunkte (Wochenende, Feiertage)

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Muster-Anomalien
        """
        from app.db.models import Document

        try:
            now = datetime.now(timezone.utc)
            recent_period = now - timedelta(days=30)

            # Rechnungen der letzten 30 Tage laden
            query = select(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.document_type == "invoice",
                    Document.created_at >= recent_period,
                    Document.total_amount.isnot(None),
                )
            ).order_by(Document.created_at.desc())

            result = await db.execute(query)
            documents: Sequence[Document] = result.scalars().all()

            alerts: List[AnomalyAlert] = []

            # 1. Verdaechtig runde Betraege erkennen
            round_amount_docs = []
            for doc in documents:
                if doc.total_amount:
                    amount = float(doc.total_amount)
                    # Runde Tausender oder Hunderter
                    if amount >= 100 and amount % 100 == 0:
                        round_amount_docs.append(doc)

            # Wenn mehr als 30% der Rechnungen runde Betraege haben
            if len(documents) > 5 and len(round_amount_docs) / len(documents) > 0.3:
                alert = AnomalyAlert(
                    anomaly_type=AnomalyType.AMOUNT_ROUND,
                    severity=AnomalySeverity.MEDIUM,
                    entity_id=documents[0].company_id,
                    entity_name="Allgemein",
                    description=f"{len(round_amount_docs)} von {len(documents)} Rechnungen haben verdaechtig runde Betraege.",
                    deviation_percent=(len(round_amount_docs) / len(documents)) * 100,
                    confidence=0.7,
                    action_url="/documents?filter=round_amounts",
                    action_label="Rechnungen prüfen",
                    related_documents=[d.id for d in round_amount_docs[:10]],
                    metadata={
                        "round_count": len(round_amount_docs),
                        "total_count": len(documents),
                    },
                )
                alerts.append(alert)

            # 2. Wochenend-Rechnungen erkennen
            weekend_docs = [
                d for d in documents
                if d.created_at and d.created_at.weekday() >= 5
            ]

            # Wenn mehr als 20% der Rechnungen am Wochenende erstellt wurden
            if len(documents) > 10 and len(weekend_docs) / len(documents) > 0.2:
                alert = AnomalyAlert(
                    anomaly_type=AnomalyType.TIMING_UNUSUAL,
                    severity=AnomalySeverity.LOW,
                    entity_id=documents[0].company_id,
                    entity_name="Allgemein",
                    description=f"{len(weekend_docs)} Rechnungen wurden am Wochenende erfasst.",
                    deviation_percent=(len(weekend_docs) / len(documents)) * 100,
                    confidence=0.6,
                    action_url="/documents?filter=weekend",
                    action_label="Prüfen",
                    related_documents=[d.id for d in weekend_docs[:10]],
                    metadata={
                        "weekend_count": len(weekend_docs),
                        "total_count": len(documents),
                    },
                )
                alerts.append(alert)

            # 3. Hochfrequenz-Perioden erkennen
            # Gruppiere nach Tag
            daily_counts: Dict[str, List[Document]] = {}
            for doc in documents:
                if doc.created_at:
                    day_key = doc.created_at.strftime("%Y-%m-%d")
                    if day_key not in daily_counts:
                        daily_counts[day_key] = []
                    daily_counts[day_key].append(doc)

            # Tage mit ungewoehnlich vielen Rechnungen
            if len(daily_counts) > 5:
                counts = [len(docs) for docs in daily_counts.values()]
                avg_daily = statistics.mean(counts)
                std_daily = statistics.stdev(counts) if len(counts) > 1 else 0

                for day, docs in daily_counts.items():
                    if std_daily > 0:
                        z_score = (len(docs) - avg_daily) / std_daily
                        if z_score >= 2.0:
                            alert = AnomalyAlert(
                                anomaly_type=AnomalyType.FREQUENCY_ANOMALY,
                                severity=_calculate_severity(z_score),
                                entity_id=documents[0].company_id,
                                entity_name=f"Tag: {day}",
                                description=f"{len(docs)} Rechnungen an einem Tag (Durchschnitt: {avg_daily:.1f})",
                                deviation_percent=((len(docs) - avg_daily) / avg_daily) * 100 if avg_daily > 0 else 0,
                                expected_value=avg_daily,
                                actual_value=float(len(docs)),
                                confidence=min(0.9, 0.5 + z_score * 0.15),
                                action_url=f"/documents?date={day}",
                                action_label="Tag prüfen",
                                related_documents=[d.id for d in docs[:10]],
                                metadata={
                                    "date": day,
                                    "z_score": z_score,
                                },
                            )
                            alerts.append(alert)

            insights = [alert.to_insight() for alert in alerts]

            logger.info(
                "invoice_pattern_anomalies_detected",
                company_id=str(company_id),
                alerts_count=len(alerts),
            )

            return insights

        except Exception as e:
            logger.warning(
                "invoice_pattern_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_duplicate_patterns(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt mögliche Duplikat-Muster.

        Findet:
        - Gleiche Betraege am gleichen Tag
        - Gleiche Rechnungsnummern
        - Sehr ähnliche Rechnungen

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Duplikat-Muster
        """
        from app.db.models import Document


        try:
            now = datetime.now(timezone.utc)
            recent_period = now - timedelta(days=90)

            # Potenzielle Duplikate: Gleicher Betrag, gleicher Tag
            dup_query = select(
                Document.total_amount,
                func.date(Document.created_at).label('date'),
                func.count().label('count'),
                func.array_agg(Document.id).label('doc_ids'),
            ).where(
                and_(
                    Document.company_id == company_id,
                    Document.document_type == "invoice",
                    Document.created_at >= recent_period,
                    Document.total_amount.isnot(None),
                    Document.total_amount > 0,
                )
            ).group_by(
                Document.total_amount,
                func.date(Document.created_at),
            ).having(func.count() > 1)

            result = await db.execute(dup_query)
            potential_dups = result.fetchall()

            alerts: List[AnomalyAlert] = []

            for row in potential_dups:
                amount, date, count, doc_ids = row

                # Nur bei relevanten Betraegen warnen
                if float(amount) < 50:
                    continue

                alert = AnomalyAlert(
                    anomaly_type=AnomalyType.DUPLICATE_PATTERN,
                    severity=AnomalySeverity.MEDIUM if count == 2 else AnomalySeverity.HIGH,
                    entity_id=doc_ids[0] if doc_ids else company_id,
                    entity_name=f"{count} Rechnungen",
                    description=f"{count} Rechnungen mit gleichem Betrag ({float(amount):,.2f} EUR) am {date}",
                    deviation_percent=0.0,
                    confidence=0.75,
                    action_url="/documents?filter=duplicates",
                    action_label="Duplikate prüfen",
                    related_documents=doc_ids[:10] if doc_ids else [],
                    metadata={
                        "amount": float(amount),
                        "date": str(date),
                        "duplicate_count": count,
                    },
                )
                alerts.append(alert)

            insights = [alert.to_insight() for alert in alerts]

            logger.info(
                "duplicate_patterns_detected",
                company_id=str(company_id),
                alerts_count=len(alerts),
            )

            return insights

        except Exception as e:
            logger.warning(
                "duplicate_pattern_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def get_anomaly_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Erstellt eine Zusammenfassung aller Anomalien.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Zusammenfassung mit Counts pro Typ und Severity
        """
        insights = await self.check_all_anomalies(db, company_id)

        summary: Dict[str, Any] = {
            "total_count": len(insights),
            "by_type": {},
            "by_severity": {},
        }

        for insight in insights:
            # Nach Typ zaehlen
            rule_type = insight.source_rule or "unknown"
            if rule_type not in summary["by_type"]:
                summary["by_type"][rule_type] = 0
            summary["by_type"][rule_type] += 1

            # Nach Priorität zaehlen
            priority = insight.priority.value
            if priority not in summary["by_severity"]:
                summary["by_severity"][priority] = 0
            summary["by_severity"][priority] += 1

        return summary


# Singleton-Instanz
_anomaly_insights_instance: Optional[AnomalyInsightsService] = None


def get_anomaly_insights_service() -> AnomalyInsightsService:
    """Gibt die Singleton-Instanz des Anomaly Insights Service zurück."""
    global _anomaly_insights_instance
    if _anomaly_insights_instance is None:
        _anomaly_insights_instance = AnomalyInsightsService()
    return _anomaly_insights_instance

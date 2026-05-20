# -*- coding: utf-8 -*-
"""
Bottleneck Detector Service.

Erkennt Engpaesse im Dokumenten-Verarbeitungsprozess:
- Lange Wartezeiten identifizieren
- Stau-Punkte erkennen
- Kapazitätsengpaesse analysieren
- Empfehlungen generieren

Feinpoliert und durchdacht.
"""

import structlog
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
from decimal import Decimal

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_process_mining import (
    ProcessEvent,
    ProcessMetric,
    EventType,
    ActorType,
)

logger = structlog.get_logger(__name__)


class BottleneckDetector:
    """
    Service zur Erkennung von Prozess-Engpaessen.

    Analysiert Wartezeiten, Durchsatz und Kapazität.
    """

    # Schwellwerte für Bottleneck-Erkennung
    DURATION_THRESHOLD_FACTOR = 2.0  # X-fache des Durchschnitts
    QUEUE_THRESHOLD = 10  # Dokumente in Warteschlange
    FAILURE_RATE_THRESHOLD = 0.1  # 10% Fehlerrate

    # Bottleneck-Schweregrade
    SEVERITY_LEVELS = {
        "critical": {"min_score": 0.8, "color": "#dc2626"},
        "high": {"min_score": 0.6, "color": "#ea580c"},
        "medium": {"min_score": 0.4, "color": "#ca8a04"},
        "low": {"min_score": 0.2, "color": "#16a34a"},
    }

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Detector.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db

    async def detect_bottlenecks(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Erkenne Engpaesse im Prozess.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum

        Returns:
            Liste erkannter Bottlenecks mit Scores
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Analysiere verschiedene Bottleneck-Typen
        duration_bottlenecks = await self._analyze_duration_bottlenecks(company_id, since)
        queue_bottlenecks = await self._analyze_queue_bottlenecks(company_id, since)
        failure_bottlenecks = await self._analyze_failure_bottlenecks(company_id, since)
        resource_bottlenecks = await self._analyze_resource_bottlenecks(company_id, since)

        # Kombiniere alle Bottlenecks
        all_bottlenecks = (
            duration_bottlenecks +
            queue_bottlenecks +
            failure_bottlenecks +
            resource_bottlenecks
        )

        # Sortiere nach Score
        all_bottlenecks.sort(key=lambda x: x["score"], reverse=True)

        # Berechne Gesamt-Score
        overall_score = 0
        if all_bottlenecks:
            overall_score = sum(b["score"] for b in all_bottlenecks) / len(all_bottlenecks)

        return {
            "bottlenecks": all_bottlenecks,
            "overall_score": round(overall_score, 4),
            "overall_severity": self._score_to_severity(overall_score),
            "bottleneck_count": len(all_bottlenecks),
            "period_days": days,
        }

    async def _analyze_duration_bottlenecks(
        self,
        company_id: UUID,
        since: datetime,
    ) -> List[Dict[str, Any]]:
        """Analysiere Engpaesse durch lange Dauern."""
        bottlenecks = []

        # Hole durchschnittliche Dauern pro Event-Typ
        result = await self.db.execute(
            select(
                ProcessEvent.event_type,
                func.avg(ProcessEvent.duration_ms).label("avg_duration"),
                func.max(ProcessEvent.duration_ms).label("max_duration"),
                func.count(ProcessEvent.id).label("count"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.duration_ms.isnot(None),
                )
            )
            .group_by(ProcessEvent.event_type)
        )

        durations = {row.event_type: row for row in result.all()}

        # Berechne globalen Durchschnitt
        if durations:
            global_avg = sum(d.avg_duration for d in durations.values()) / len(durations)
        else:
            return []

        # Identifiziere Bottlenecks
        for event_type, data in durations.items():
            if data.avg_duration > global_avg * self.DURATION_THRESHOLD_FACTOR:
                # Berechne Score (0-1)
                ratio = data.avg_duration / (global_avg * self.DURATION_THRESHOLD_FACTOR)
                score = min(1.0, ratio / 2)  # Normalisiere

                bottlenecks.append({
                    "type": "duration",
                    "location": event_type,
                    "score": round(score, 4),
                    "severity": self._score_to_severity(score),
                    "details": {
                        "avg_duration_ms": int(data.avg_duration),
                        "max_duration_ms": data.max_duration,
                        "global_avg_ms": int(global_avg),
                        "ratio": round(ratio, 2),
                        "affected_documents": data.count,
                    },
                    "recommendation": self._get_duration_recommendation(event_type, ratio),
                })

        return bottlenecks

    async def _analyze_queue_bottlenecks(
        self,
        company_id: UUID,
        since: datetime,
    ) -> List[Dict[str, Any]]:
        """Analysiere Engpaesse durch Warteschlangen."""
        bottlenecks = []

        # Analysiere Zeit zwischen Events (Wartezeit)
        result = await self.db.execute(
            select(
                ProcessEvent.event_type,
                func.avg(ProcessEvent.time_since_previous_ms).label("avg_wait"),
                func.max(ProcessEvent.time_since_previous_ms).label("max_wait"),
                func.count(ProcessEvent.id).label("count"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.time_since_previous_ms.isnot(None),
                )
            )
            .group_by(ProcessEvent.event_type)
        )

        wait_times = {row.event_type: row for row in result.all()}

        # Berechne globalen Durchschnitt der Wartezeiten
        if wait_times:
            global_avg_wait = sum(d.avg_wait for d in wait_times.values()) / len(wait_times)
        else:
            return []

        # Identifiziere Warteschlangen-Bottlenecks
        for event_type, data in wait_times.items():
            if data.avg_wait > global_avg_wait * 3:  # 3x länger als Durchschnitt
                ratio = data.avg_wait / global_avg_wait
                score = min(1.0, ratio / 10)

                bottlenecks.append({
                    "type": "queue",
                    "location": event_type,
                    "score": round(score, 4),
                    "severity": self._score_to_severity(score),
                    "details": {
                        "avg_wait_ms": int(data.avg_wait),
                        "max_wait_ms": data.max_wait,
                        "global_avg_wait_ms": int(global_avg_wait),
                        "ratio": round(ratio, 2),
                        "affected_documents": data.count,
                    },
                    "recommendation": f"Vor '{event_type}' stauen sich Dokumente. "
                                      f"Erhöhen Sie die Verarbeitungskapazität.",
                })

        return bottlenecks

    async def _analyze_failure_bottlenecks(
        self,
        company_id: UUID,
        since: datetime,
    ) -> List[Dict[str, Any]]:
        """Analysiere Engpaesse durch Fehler."""
        bottlenecks = []

        result = await self.db.execute(
            select(
                ProcessEvent.event_type,
                func.count(ProcessEvent.id).label("total"),
                func.count(ProcessEvent.id).filter(ProcessEvent.success == False).label("failures"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
            .group_by(ProcessEvent.event_type)
        )

        for row in result.all():
            if row.total > 0:
                failure_rate = row.failures / row.total
                if failure_rate >= self.FAILURE_RATE_THRESHOLD:
                    score = min(1.0, failure_rate * 2)

                    bottlenecks.append({
                        "type": "failure",
                        "location": row.event_type,
                        "score": round(score, 4),
                        "severity": self._score_to_severity(score),
                        "details": {
                            "total_events": row.total,
                            "failures": row.failures,
                            "failure_rate": round(failure_rate, 4),
                        },
                        "recommendation": f"Hohe Fehlerrate bei '{row.event_type}'. "
                                          f"Prüfen Sie die Konfiguration und Eingabedaten.",
                    })

        return bottlenecks

    async def _analyze_resource_bottlenecks(
        self,
        company_id: UUID,
        since: datetime,
    ) -> List[Dict[str, Any]]:
        """Analysiere Ressourcen-Engpaesse (manuelle Aktionen)."""
        bottlenecks = []

        # Analysiere manuelle Aktionen
        result = await self.db.execute(
            select(
                ProcessEvent.event_type,
                ProcessEvent.actor_type,
                func.count(ProcessEvent.id).label("count"),
                func.avg(ProcessEvent.duration_ms).label("avg_duration"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.actor_type == ActorType.USER.value,
                )
            )
            .group_by(ProcessEvent.event_type, ProcessEvent.actor_type)
        )

        manual_actions = list(result.all())

        # Identifiziere Schritte mit vielen manuellen Aktionen
        for row in manual_actions:
            if row.count > 10:  # Mindestens 10 manuelle Aktionen
                # Score basierend auf Anzahl und Dauer
                score = min(1.0, (row.count / 100) + ((row.avg_duration or 0) / 60000))

                bottlenecks.append({
                    "type": "resource",
                    "location": row.event_type,
                    "score": round(score, 4),
                    "severity": self._score_to_severity(score),
                    "details": {
                        "manual_actions": row.count,
                        "avg_duration_ms": int(row.avg_duration) if row.avg_duration else 0,
                    },
                    "recommendation": f"'{row.event_type}' erfordert viele manuelle Eingriffe. "
                                      f"Automatisierung empfohlen.",
                })

        return bottlenecks

    def _score_to_severity(self, score: float) -> str:
        """Konvertiere Score zu Schweregrad."""
        for severity, config in self.SEVERITY_LEVELS.items():
            if score >= config["min_score"]:
                return severity
        return "low"

    def _get_duration_recommendation(self, event_type: str, ratio: float) -> str:
        """Generiere Empfehlung basierend auf Event-Typ."""
        recommendations = {
            EventType.OCR_STARTED.value: "OCR-Verarbeitung ist langsam. GPU-Ressourcen prüfen.",
            EventType.OCR_COMPLETED.value: "OCR dauert länger als erwartet. Backend wechseln?",
            EventType.CLASSIFICATION_COMPLETED.value: "Klassifikation ist langsam. Modell optimieren.",
            EventType.VALIDATION_COMPLETED.value: "Validierung dauert lange. Regeln vereinfachen.",
            EventType.APPROVAL_GRANTED.value: "Freigaben dauern lange. Workflow optimieren.",
            EventType.APPROVAL_REJECTED.value: "Ablehnungen verzögern den Prozess.",
        }

        return recommendations.get(
            event_type,
            f"'{event_type}' ist {ratio:.1f}x langsamer als der Durchschnitt."
        )

    async def get_bottleneck_heatmap(
        self,
        company_id: UUID,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        Erstelle Heatmap-Daten für Bottleneck-Visualisierung.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum (granular)

        Returns:
            Heatmap-Daten nach Tag und Stunde
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Hole Events mit Timestamp-Details
        result = await self.db.execute(
            select(
                func.extract('dow', ProcessEvent.timestamp).label('day_of_week'),
                func.extract('hour', ProcessEvent.timestamp).label('hour'),
                ProcessEvent.event_type,
                func.count(ProcessEvent.id).label('count'),
                func.avg(ProcessEvent.duration_ms).label('avg_duration'),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
            .group_by('day_of_week', 'hour', ProcessEvent.event_type)
        )

        heatmap_data = defaultdict(lambda: defaultdict(lambda: {"count": 0, "avg_duration": 0}))

        for row in result.all():
            day = int(row.day_of_week)
            hour = int(row.hour)
            heatmap_data[day][hour]["count"] += row.count
            heatmap_data[day][hour]["avg_duration"] = max(
                heatmap_data[day][hour]["avg_duration"],
                int(row.avg_duration) if row.avg_duration else 0
            )

        # Formatiere für Frontend
        formatted_data = []
        day_names = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"]

        for day in range(7):
            for hour in range(24):
                data = heatmap_data[day].get(hour, {"count": 0, "avg_duration": 0})
                formatted_data.append({
                    "day": day,
                    "day_name": day_names[day],
                    "hour": hour,
                    "count": data["count"],
                    "avg_duration_ms": data["avg_duration"],
                })

        return {
            "data": formatted_data,
            "period_days": days,
        }

    async def calculate_process_health(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Berechne Gesamt-Prozessgesundheit.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum

        Returns:
            Prozessgesundheits-Score und Details
        """
        bottlenecks = await self.detect_bottlenecks(company_id, days)

        # Berechne Teilscores
        bottleneck_score = 1.0 - bottlenecks["overall_score"]

        # Erfolgsrate
        since = datetime.utcnow() - timedelta(days=days)
        success_result = await self.db.execute(
            select(
                func.count(ProcessEvent.id).label("total"),
                func.count(ProcessEvent.id).filter(ProcessEvent.success == True).label("success"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
        )
        success_row = success_result.one()
        success_rate = success_row.success / success_row.total if success_row.total > 0 else 0

        # Automatisierungsgrad
        automation_result = await self.db.execute(
            select(
                func.count(ProcessEvent.id).label("total"),
                func.count(ProcessEvent.id).filter(
                    ProcessEvent.actor_type != ActorType.USER.value
                ).label("automated"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
        )
        automation_row = automation_result.one()
        automation_rate = (
            automation_row.automated / automation_row.total
            if automation_row.total > 0 else 0
        )

        # Gesamt-Health-Score (gewichtet)
        health_score = (
            bottleneck_score * 0.4 +
            success_rate * 0.4 +
            automation_rate * 0.2
        )

        return {
            "health_score": round(health_score, 4),
            "health_grade": self._score_to_grade(health_score),
            "components": {
                "bottleneck_score": round(bottleneck_score, 4),
                "success_rate": round(success_rate, 4),
                "automation_rate": round(automation_rate, 4),
            },
            "bottleneck_count": bottlenecks["bottleneck_count"],
            "top_bottleneck": bottlenecks["bottlenecks"][0] if bottlenecks["bottlenecks"] else None,
            "period_days": days,
        }

    def _score_to_grade(self, score: float) -> str:
        """Konvertiere Score zu Note."""
        if score >= 0.9:
            return "A"
        elif score >= 0.8:
            return "B"
        elif score >= 0.7:
            return "C"
        elif score >= 0.6:
            return "D"
        else:
            return "F"

    async def save_daily_metrics(
        self,
        company_id: UUID,
    ) -> None:
        """
        Speichere tägliche Bottleneck-Metriken.

        Wird von Celery-Task aufgerufen.

        Args:
            company_id: Mandanten-ID
        """
        today = datetime.utcnow().date()

        # Berechne Metriken
        health = await self.calculate_process_health(company_id, days=1)
        bottlenecks = await self.detect_bottlenecks(company_id, days=1)

        # Speichere pro kritischem Bottleneck
        for bottleneck in bottlenecks["bottlenecks"]:
            if bottleneck["severity"] in ["critical", "high"]:
                metric = ProcessMetric(
                    company_id=company_id,
                    metric_date=today,
                    metric_type="bottleneck",
                    process_name="document_lifecycle",
                    activity_name=bottleneck["location"],
                    bottleneck_score=Decimal(str(bottleneck["score"])),
                    metadata={
                        "type": bottleneck["type"],
                        "severity": bottleneck["severity"],
                        "details": bottleneck["details"],
                    },
                )
                self.db.add(metric)

        await self.db.flush()
        logger.info(f"Saved daily bottleneck metrics for company {company_id}")

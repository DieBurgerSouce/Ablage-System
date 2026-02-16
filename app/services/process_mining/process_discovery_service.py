# -*- coding: utf-8 -*-
"""
Process Discovery Service.

Erkennt Prozessflüsse aus Event-Logs:
- Prozessvarianten analysieren
- Häufige Pfade identifizieren
- Durchlaufzeiten berechnen
- Prozessmodell generieren

Feinpoliert und durchdacht.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, and_, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_process_mining import ProcessEvent, EventType, ActorType

logger = logging.getLogger(__name__)


class ProcessDiscoveryService:
    """
    Service für Process Discovery aus Event-Logs.

    Analysiert historische Events um Prozessmuster zu erkennen.
    """

    # Standard-Prozessschritte in erwarteter Reihenfolge
    STANDARD_PROCESS_FLOW = [
        EventType.DOCUMENT_UPLOADED,
        EventType.OCR_STARTED,
        EventType.OCR_COMPLETED,
        EventType.CLASSIFICATION_COMPLETED,
        EventType.VALIDATION_COMPLETED,
        EventType.APPROVAL_GRANTED,
        EventType.ARCHIVE_COMPLETED,
    ]

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Service.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db

    async def discover_process_variants(
        self,
        company_id: UUID,
        days: int = 30,
        min_occurrences: int = 5,
    ) -> Dict[str, Any]:
        """
        Entdecke Prozessvarianten aus Event-Logs.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum
            min_occurrences: Mindestanzahl für Variante

        Returns:
            Prozessvarianten mit Häufigkeiten
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Hole alle Process Instances
        result = await self.db.execute(
            select(ProcessEvent.process_instance_id)
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.process_instance_id.isnot(None),
                )
            )
            .distinct()
        )
        instance_ids = [row[0] for row in result.all()]

        if not instance_ids:
            return {
                "variants": [],
                "total_instances": 0,
                "unique_variants": 0,
            }

        # Sammle Varianten (Event-Sequenzen)
        variants: Dict[str, List[str]] = defaultdict(list)

        for instance_id in instance_ids:
            events_result = await self.db.execute(
                select(ProcessEvent.event_type)
                .where(
                    and_(
                        ProcessEvent.process_instance_id == instance_id,
                        ProcessEvent.company_id == company_id,
                    )
                )
                .order_by(ProcessEvent.timestamp)
            )
            event_sequence = [row[0] for row in events_result.all()]

            if event_sequence:
                # Erstelle Varianten-Key aus Sequenz
                variant_key = " → ".join(event_sequence)
                variants[variant_key].append(instance_id)

        # Filtere nach Mindestanzahl und sortiere
        filtered_variants = [
            {
                "sequence": key,
                "steps": key.split(" → "),
                "count": len(instances),
                "percentage": round(len(instances) / len(instance_ids) * 100, 2),
                "sample_instances": instances[:3],  # Beispiele
            }
            for key, instances in variants.items()
            if len(instances) >= min_occurrences
        ]
        filtered_variants.sort(key=lambda x: x["count"], reverse=True)

        # Identifiziere Standard-Variante
        standard_sequence = " → ".join([e.value for e in self.STANDARD_PROCESS_FLOW])
        has_standard = any(v["sequence"] == standard_sequence for v in filtered_variants)

        return {
            "variants": filtered_variants,
            "total_instances": len(instance_ids),
            "unique_variants": len(variants),
            "filtered_variants": len(filtered_variants),
            "has_standard_process": has_standard,
            "period_days": days,
        }

    async def calculate_throughput_times(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Berechne Durchlaufzeiten pro Prozessschritt.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum

        Returns:
            Durchlaufzeiten mit Statistiken
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Hole Dauern pro Event-Typ
        result = await self.db.execute(
            select(
                ProcessEvent.event_type,
                func.count(ProcessEvent.id).label("count"),
                func.avg(ProcessEvent.duration_ms).label("avg_duration"),
                func.min(ProcessEvent.duration_ms).label("min_duration"),
                func.max(ProcessEvent.duration_ms).label("max_duration"),
                func.percentile_cont(0.5).within_group(ProcessEvent.duration_ms).label("p50"),
                func.percentile_cont(0.95).within_group(ProcessEvent.duration_ms).label("p95"),
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

        throughput_by_step = []
        total_avg_ms = 0

        for row in result.all():
            step_data = {
                "event_type": row.event_type,
                "count": row.count,
                "avg_duration_ms": int(row.avg_duration) if row.avg_duration else 0,
                "min_duration_ms": row.min_duration,
                "max_duration_ms": row.max_duration,
                "p50_duration_ms": int(row.p50) if row.p50 else 0,
                "p95_duration_ms": int(row.p95) if row.p95 else 0,
            }
            throughput_by_step.append(step_data)
            total_avg_ms += step_data["avg_duration_ms"]

        # Sortiere nach Standard-Reihenfolge
        event_order = {e.value: i for i, e in enumerate(self.STANDARD_PROCESS_FLOW)}
        throughput_by_step.sort(
            key=lambda x: event_order.get(x["event_type"], 999)
        )

        # Berechne Gesamt-Durchlaufzeit (Upload bis Archiv)
        total_throughput = await self._calculate_total_throughput(company_id, since)

        return {
            "steps": throughput_by_step,
            "total_avg_duration_ms": total_avg_ms,
            "end_to_end_avg_ms": total_throughput.get("avg_ms", 0),
            "end_to_end_p50_ms": total_throughput.get("p50_ms", 0),
            "end_to_end_p95_ms": total_throughput.get("p95_ms", 0),
            "period_days": days,
        }

    async def _calculate_total_throughput(
        self,
        company_id: UUID,
        since: datetime,
    ) -> Dict[str, int]:
        """Berechne End-to-End Durchlaufzeit."""
        # Finde abgeschlossene Prozesse (Upload bis Archiv)
        result = await self.db.execute(
            select(ProcessEvent.process_instance_id)
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.event_type == EventType.ARCHIVE_COMPLETED.value,
                )
            )
            .distinct()
        )
        completed_instances = [row[0] for row in result.all()]

        if not completed_instances:
            return {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0}

        durations = []
        for instance_id in completed_instances[:100]:  # Limitiere auf 100
            # Hole erstes und letztes Event
            first_result = await self.db.execute(
                select(ProcessEvent.timestamp)
                .where(
                    and_(
                        ProcessEvent.process_instance_id == instance_id,
                        ProcessEvent.company_id == company_id,
                    )
                )
                .order_by(ProcessEvent.timestamp)
                .limit(1)
            )
            first_ts = first_result.scalar_one_or_none()

            last_result = await self.db.execute(
                select(ProcessEvent.timestamp)
                .where(
                    and_(
                        ProcessEvent.process_instance_id == instance_id,
                        ProcessEvent.company_id == company_id,
                    )
                )
                .order_by(ProcessEvent.timestamp.desc())
                .limit(1)
            )
            last_ts = last_result.scalar_one_or_none()

            if first_ts and last_ts:
                duration_ms = int(
                    (last_ts.replace(tzinfo=None) - first_ts.replace(tzinfo=None))
                    .total_seconds() * 1000
                )
                durations.append(duration_ms)

        if not durations:
            return {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0}

        durations.sort()
        p50_idx = int(len(durations) * 0.5)
        p95_idx = int(len(durations) * 0.95)

        return {
            "avg_ms": int(sum(durations) / len(durations)),
            "p50_ms": durations[p50_idx] if p50_idx < len(durations) else 0,
            "p95_ms": durations[p95_idx] if p95_idx < len(durations) else 0,
        }

    async def analyze_actor_distribution(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Analysiere Verteilung von Aktionen nach Akteur-Typ.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum

        Returns:
            Verteilung manuell vs automatisch
        """
        since = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            select(
                ProcessEvent.actor_type,
                ProcessEvent.event_type,
                func.count(ProcessEvent.id).label("count"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
            .group_by(ProcessEvent.actor_type, ProcessEvent.event_type)
        )

        distribution: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        totals: Dict[str, int] = defaultdict(int)

        for row in result.all():
            distribution[row.actor_type][row.event_type] = row.count
            totals[row.actor_type] += row.count

        total_actions = sum(totals.values())
        manual_actions = totals.get(ActorType.USER.value, 0)
        automated_actions = total_actions - manual_actions

        automation_rate = automated_actions / total_actions if total_actions > 0 else 0

        return {
            "distribution": dict(distribution),
            "totals_by_actor": dict(totals),
            "total_actions": total_actions,
            "manual_actions": manual_actions,
            "automated_actions": automated_actions,
            "automation_rate": round(automation_rate, 4),
            "period_days": days,
        }

    async def find_process_deviations(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Finde Abweichungen vom Standard-Prozess.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum

        Returns:
            Liste von Abweichungen
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Hole alle Process Instances
        result = await self.db.execute(
            select(ProcessEvent.process_instance_id)
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.process_instance_id.isnot(None),
                )
            )
            .distinct()
        )
        instance_ids = [row[0] for row in result.all()]

        deviations = {
            "skipped_steps": [],      # Übersprungene Schritte
            "repeated_steps": [],     # Wiederholte Schritte
            "failed_steps": [],       # Fehlgeschlagene Schritte
            "manual_corrections": [], # Manuelle Korrekturen
            "unusual_order": [],      # Ungewoehnliche Reihenfolge
        }

        standard_flow = [e.value for e in self.STANDARD_PROCESS_FLOW]

        for instance_id in instance_ids[:100]:  # Limitiere
            events_result = await self.db.execute(
                select(ProcessEvent)
                .where(
                    and_(
                        ProcessEvent.process_instance_id == instance_id,
                        ProcessEvent.company_id == company_id,
                    )
                )
                .order_by(ProcessEvent.timestamp)
            )
            events = list(events_result.scalars().all())

            event_types = [e.event_type for e in events]

            # Prüfe auf übersprungene Schritte
            for i, expected in enumerate(standard_flow):
                if expected not in event_types:
                    # Prüfe ob nachfolgende Schritte vorhanden
                    if any(e in event_types for e in standard_flow[i + 1:]):
                        deviations["skipped_steps"].append({
                            "instance_id": instance_id,
                            "skipped_step": expected,
                        })

            # Prüfe auf wiederholte Schritte
            for event_type in set(event_types):
                count = event_types.count(event_type)
                if count > 1:
                    deviations["repeated_steps"].append({
                        "instance_id": instance_id,
                        "repeated_step": event_type,
                        "count": count,
                    })

            # Prüfe auf Fehler
            for event in events:
                if not event.success:
                    deviations["failed_steps"].append({
                        "instance_id": instance_id,
                        "failed_step": event.event_type,
                        "error": event.error_message,
                    })

            # Prüfe auf manuelle Korrekturen
            if EventType.CLASSIFICATION_CORRECTED.value in event_types:
                deviations["manual_corrections"].append({
                    "instance_id": instance_id,
                    "correction_type": "classification",
                })
            if EventType.MANUAL_CORRECTION.value in event_types:
                deviations["manual_corrections"].append({
                    "instance_id": instance_id,
                    "correction_type": "validation",
                })

        return {
            "deviations": deviations,
            "summary": {
                "skipped_count": len(deviations["skipped_steps"]),
                "repeated_count": len(deviations["repeated_steps"]),
                "failed_count": len(deviations["failed_steps"]),
                "correction_count": len(deviations["manual_corrections"]),
            },
            "analyzed_instances": len(instance_ids),
            "period_days": days,
        }

    async def generate_process_model(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Generiere Prozessmodell für Visualisierung.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum

        Returns:
            Prozessmodell mit Knoten und Kanten
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Sammle Übergaenge zwischen Events
        transitions: Dict[Tuple[str, str], int] = defaultdict(int)
        event_counts: Dict[str, int] = defaultdict(int)

        # Hole alle Process Instances
        result = await self.db.execute(
            select(ProcessEvent.process_instance_id)
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.process_instance_id.isnot(None),
                )
            )
            .distinct()
        )
        instance_ids = [row[0] for row in result.all()]

        for instance_id in instance_ids:
            events_result = await self.db.execute(
                select(ProcessEvent.event_type)
                .where(
                    and_(
                        ProcessEvent.process_instance_id == instance_id,
                        ProcessEvent.company_id == company_id,
                    )
                )
                .order_by(ProcessEvent.timestamp)
            )
            event_types = [row[0] for row in events_result.all()]

            # Zaehle Events
            for event_type in event_types:
                event_counts[event_type] += 1

            # Zaehle Übergaenge
            for i in range(len(event_types) - 1):
                transition = (event_types[i], event_types[i + 1])
                transitions[transition] += 1

        # Erstelle Knoten
        nodes = [
            {
                "id": event_type,
                "label": event_type.replace("_", " ").title(),
                "count": count,
            }
            for event_type, count in event_counts.items()
        ]

        # Erstelle Kanten
        edges = [
            {
                "source": source,
                "target": target,
                "count": count,
            }
            for (source, target), count in transitions.items()
        ]

        # Sortiere nach Häufigkeit
        edges.sort(key=lambda x: x["count"], reverse=True)

        return {
            "nodes": nodes,
            "edges": edges,
            "total_instances": len(instance_ids),
            "unique_events": len(nodes),
            "unique_transitions": len(edges),
            "period_days": days,
        }

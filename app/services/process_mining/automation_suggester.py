# -*- coding: utf-8 -*-
"""
Automation Suggester Service.

Generiert Automatisierungsvorschläge basierend auf Process Mining:
- Manuelle Aktionen erkennen
- Wiederholte Muster identifizieren
- ROI berechnen
- Vorschläge mit Confidence erstellen

Feinpoliert und durchdacht.
"""

import structlog
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_process_mining import (
    ProcessEvent,
    AutomationSuggestion,
    EventType,
    ActorType,
    SuggestionStatus,
    SuggestionType,
)

logger = structlog.get_logger(__name__)


class AutomationSuggester:
    """
    Service für die Generierung von Automatisierungsvorschlägen.

    Analysiert manuelle Aktionen und schlaegt Automatisierung vor.
    """

    # Stundenlohn für ROI-Berechnung (EUR)
    DEFAULT_HOURLY_RATE = 50.0

    # Mindest-Confidence für Vorschläge
    MIN_CONFIDENCE = 0.7

    # Mindest-Frequenz pro Woche
    MIN_FREQUENCY = 5

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Suggester.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db

    async def generate_suggestions(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Generiere Automatisierungsvorschläge.

        Args:
            company_id: Mandanten-ID
            days: Analysezeitraum

        Returns:
            Liste von Vorschlägen
        """
        suggestions = []

        # Analysiere verschiedene Automatisierungstypen
        classification_suggestions = await self._analyze_classification_patterns(company_id, days)
        routing_suggestions = await self._analyze_routing_patterns(company_id, days)
        approval_suggestions = await self._analyze_approval_patterns(company_id, days)
        entity_suggestions = await self._analyze_entity_linking_patterns(company_id, days)
        workflow_suggestions = await self._analyze_workflow_optimizations(company_id, days)

        suggestions.extend(classification_suggestions)
        suggestions.extend(routing_suggestions)
        suggestions.extend(approval_suggestions)
        suggestions.extend(entity_suggestions)
        suggestions.extend(workflow_suggestions)

        # Sortiere nach Potential (Einsparungen)
        suggestions.sort(key=lambda x: x.get("potential_savings_hours", 0), reverse=True)

        return suggestions

    async def _analyze_classification_patterns(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Analysiere Klassifikations-Korrekturen für Auto-Klassifikation."""
        suggestions = []
        since = datetime.utcnow() - timedelta(days=days)

        # Finde häufige manuelle Klassifikations-Korrekturen
        result = await self.db.execute(
            select(
                ProcessEvent.event_metadata['document_type'].astext.label('doc_type'),
                func.count(ProcessEvent.id).label('count'),
                func.avg(ProcessEvent.duration_ms).label('avg_duration'),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.event_type == EventType.CLASSIFICATION_CORRECTED.value,
                    ProcessEvent.actor_type == ActorType.USER.value,
                )
            )
            .group_by('doc_type')
            .having(func.count(ProcessEvent.id) >= self.MIN_FREQUENCY)
        )

        for row in result.all():
            if row.doc_type:
                frequency_per_week = row.count / (days / 7)
                avg_duration_hours = (row.avg_duration or 0) / 3600000

                # Berechne Einsparungen
                savings_hours = frequency_per_week * 52 * avg_duration_hours
                savings_cost = savings_hours * self.DEFAULT_HOURLY_RATE

                # Berechne Confidence basierend auf Konsistenz
                confidence = min(0.95, 0.7 + (row.count / 100) * 0.25)

                suggestions.append({
                    "suggestion_type": SuggestionType.AUTO_CLASSIFICATION.value,
                    "title": f"Auto-Klassifikation für '{row.doc_type}'",
                    "description": (
                        f"Dokumente vom Typ '{row.doc_type}' werden häufig manuell korrigiert. "
                        f"Eine automatische Klassifikationsregel könnte {frequency_per_week:.1f} "
                        f"manuelle Korrekturen pro Woche einsparen."
                    ),
                    "pattern_description": (
                        f"In den letzten {days} Tagen wurden {row.count} Dokumente "
                        f"manuell als '{row.doc_type}' klassifiziert."
                    ),
                    "confidence": round(confidence, 4),
                    "potential_savings_hours": round(savings_hours, 2),
                    "potential_savings_cost": round(savings_cost, 2),
                    "affected_steps": [EventType.CLASSIFICATION_COMPLETED.value],
                    "trigger_conditions": {
                        "document_type_pattern": row.doc_type,
                    },
                    "suggested_actions": [
                        {
                            "action": "auto_classify",
                            "target_type": row.doc_type,
                        }
                    ],
                    "frequency_per_week": int(frequency_per_week),
                })

        return suggestions

    async def _analyze_routing_patterns(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Analysiere Routing-Muster für Auto-Routing."""
        suggestions = []
        since = datetime.utcnow() - timedelta(days=days)

        # Finde Entity-Linking Muster
        result = await self.db.execute(
            select(
                ProcessEvent.entity_id,
                ProcessEvent.event_metadata['strategy'].astext.label('strategy'),
                func.count(ProcessEvent.id).label('count'),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.event_type == EventType.ENTITY_LINKED.value,
                )
            )
            .group_by(ProcessEvent.entity_id, 'strategy')
            .having(func.count(ProcessEvent.id) >= self.MIN_FREQUENCY)
        )

        entity_patterns = defaultdict(list)
        for row in result.all():
            if row.entity_id:
                entity_patterns[str(row.entity_id)].append({
                    "strategy": row.strategy,
                    "count": row.count,
                })

        # Generiere Vorschläge für konsistente Patterns
        for entity_id, patterns in entity_patterns.items():
            total_count = sum(p["count"] for p in patterns)
            frequency_per_week = total_count / (days / 7)

            if frequency_per_week >= self.MIN_FREQUENCY:
                # Finde dominante Strategie
                dominant = max(patterns, key=lambda x: x["count"])
                consistency = dominant["count"] / total_count

                if consistency >= 0.8:  # 80%+ konsistent
                    suggestions.append({
                        "suggestion_type": SuggestionType.AUTO_ROUTING.value,
                        "title": f"Auto-Routing für Entity {entity_id[:8]}...",
                        "description": (
                            f"Dokumente werden konsistent zu dieser Entity geroutet. "
                            f"Auto-Routing könnte den Prozess beschleunigen."
                        ),
                        "confidence": round(consistency * 0.9, 4),
                        "potential_savings_hours": round(frequency_per_week * 52 * 0.05, 2),
                        "potential_savings_cost": round(frequency_per_week * 52 * 0.05 * self.DEFAULT_HOURLY_RATE, 2),
                        "affected_steps": [EventType.ENTITY_LINKED.value],
                        "trigger_conditions": {
                            "entity_id": entity_id,
                            "strategy": dominant["strategy"],
                        },
                        "frequency_per_week": int(frequency_per_week),
                    })

        return suggestions

    async def _analyze_approval_patterns(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Analysiere Freigabe-Muster für Auto-Approval."""
        suggestions = []
        since = datetime.utcnow() - timedelta(days=days)

        # Finde Freigabe-Muster nach Betrag
        result = await self.db.execute(
            select(
                ProcessEvent.actor_id,
                func.count(ProcessEvent.id).label('total'),
                func.count(ProcessEvent.id).filter(
                    ProcessEvent.event_type == EventType.APPROVAL_GRANTED.value
                ).label('approved'),
                func.avg(ProcessEvent.duration_ms).label('avg_duration'),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.event_type.in_([
                        EventType.APPROVAL_GRANTED.value,
                        EventType.APPROVAL_REJECTED.value,
                    ]),
                    ProcessEvent.actor_type == ActorType.USER.value,
                )
            )
            .group_by(ProcessEvent.actor_id)
            .having(func.count(ProcessEvent.id) >= self.MIN_FREQUENCY)
        )

        for row in result.all():
            if row.total > 0:
                approval_rate = row.approved / row.total
                frequency_per_week = row.total / (days / 7)

                # Nur wenn fast immer genehmigt wird
                if approval_rate >= 0.95:
                    avg_duration_hours = (row.avg_duration or 0) / 3600000
                    savings_hours = frequency_per_week * 52 * avg_duration_hours

                    suggestions.append({
                        "suggestion_type": SuggestionType.AUTO_APPROVAL.value,
                        "title": "Auto-Freigabe für Routinedokumente",
                        "description": (
                            f"Bei einer Genehmigungsrate von {approval_rate * 100:.1f}% "
                            f"könnten bestimmte Dokumente automatisch freigegeben werden."
                        ),
                        "pattern_description": (
                            f"{row.approved} von {row.total} Dokumenten wurden genehmigt."
                        ),
                        "confidence": round(approval_rate * 0.9, 4),
                        "potential_savings_hours": round(savings_hours, 2),
                        "potential_savings_cost": round(savings_hours * self.DEFAULT_HOURLY_RATE, 2),
                        "affected_steps": [EventType.APPROVAL_GRANTED.value],
                        "trigger_conditions": {
                            "approval_rate_threshold": 0.95,
                        },
                        "suggested_actions": [
                            {
                                "action": "auto_approve",
                                "condition": "amount_below_threshold",
                            }
                        ],
                        "frequency_per_week": int(frequency_per_week),
                    })

        return suggestions

    async def _analyze_entity_linking_patterns(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Analysiere Entity-Linking für Verbesserungen."""
        suggestions = []
        since = datetime.utcnow() - timedelta(days=days)

        # Finde manuelle Entity-Verknüpfungen
        result = await self.db.execute(
            select(
                func.count(ProcessEvent.id).label('total'),
                func.count(ProcessEvent.id).filter(
                    ProcessEvent.actor_type == ActorType.USER.value
                ).label('manual'),
                func.avg(ProcessEvent.duration_ms).label('avg_duration'),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.event_type == EventType.ENTITY_LINKED.value,
                )
            )
        )

        row = result.one()
        if row.total > 0:
            manual_rate = row.manual / row.total
            frequency_per_week = row.total / (days / 7)

            if manual_rate > 0.3:  # Mehr als 30% manuell
                avg_duration_hours = (row.avg_duration or 0) / 3600000
                potential_auto = row.manual * 0.7  # 70% könnten automatisiert werden
                savings_hours = (potential_auto / (days / 7)) * 52 * avg_duration_hours

                suggestions.append({
                    "suggestion_type": SuggestionType.AUTO_ENTITY_LINK.value,
                    "title": "Verbesserte Entity-Erkennung",
                    "description": (
                        f"{manual_rate * 100:.1f}% der Entity-Verknüpfungen erfolgen manuell. "
                        f"Erweitertes Training könnte die Erkennungsrate verbessern."
                    ),
                    "pattern_description": (
                        f"{row.manual} von {row.total} Verknüpfungen waren manuell."
                    ),
                    "confidence": round(0.75, 4),
                    "potential_savings_hours": round(savings_hours, 2),
                    "potential_savings_cost": round(savings_hours * self.DEFAULT_HOURLY_RATE, 2),
                    "affected_steps": [EventType.ENTITY_LINKED.value],
                    "trigger_conditions": {
                        "manual_rate_threshold": 0.3,
                    },
                    "suggested_actions": [
                        {
                            "action": "retrain_entity_matcher",
                            "with_corrections": True,
                        }
                    ],
                    "frequency_per_week": int(frequency_per_week),
                })

        return suggestions

    async def _analyze_workflow_optimizations(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Analysiere Workflow-Optimierungen."""
        suggestions = []
        since = datetime.utcnow() - timedelta(days=days)

        # Finde wiederkehrende manuelle Korrekturen
        result = await self.db.execute(
            select(
                ProcessEvent.event_type,
                func.count(ProcessEvent.id).label('count'),
                func.avg(ProcessEvent.duration_ms).label('avg_duration'),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.actor_type == ActorType.USER.value,
                    ProcessEvent.event_type.in_([
                        EventType.MANUAL_CORRECTION.value,
                        EventType.CLASSIFICATION_CORRECTED.value,
                    ]),
                )
            )
            .group_by(ProcessEvent.event_type)
            .having(func.count(ProcessEvent.id) >= self.MIN_FREQUENCY)
        )

        total_corrections = 0
        total_duration = 0

        for row in result.all():
            total_corrections += row.count
            total_duration += (row.avg_duration or 0) * row.count

        if total_corrections > 0:
            frequency_per_week = total_corrections / (days / 7)
            avg_duration_hours = (total_duration / total_corrections) / 3600000
            savings_hours = frequency_per_week * 52 * avg_duration_hours * 0.5

            suggestions.append({
                "suggestion_type": SuggestionType.WORKFLOW_OPTIMIZATION.value,
                "title": "Workflow-Optimierung durch Musterlernen",
                "description": (
                    f"Es gibt {int(frequency_per_week)} manuelle Korrekturen pro Woche. "
                    f"Ein lernender Workflow könnte diese reduzieren."
                ),
                "pattern_description": (
                    f"Insgesamt {total_corrections} manuelle Korrekturen in {days} Tagen."
                ),
                "confidence": round(0.7, 4),
                "potential_savings_hours": round(savings_hours, 2),
                "potential_savings_cost": round(savings_hours * self.DEFAULT_HOURLY_RATE, 2),
                "affected_steps": [
                    EventType.MANUAL_CORRECTION.value,
                    EventType.CLASSIFICATION_CORRECTED.value,
                ],
                "trigger_conditions": {
                    "correction_frequency": frequency_per_week,
                },
                "suggested_actions": [
                    {
                        "action": "enable_learning_mode",
                        "target": "all_corrections",
                    }
                ],
                "frequency_per_week": int(frequency_per_week),
            })

        return suggestions

    async def save_suggestions(
        self,
        company_id: UUID,
        suggestions: List[Dict[str, Any]],
    ) -> List[AutomationSuggestion]:
        """
        Speichere generierte Vorschläge in der Datenbank.

        Args:
            company_id: Mandanten-ID
            suggestions: Liste von Vorschlägen

        Returns:
            Gespeicherte AutomationSuggestion-Objekte
        """
        saved = []

        for sugg in suggestions:
            # Prüfe ob ähnlicher Vorschlag existiert
            existing = await self.db.execute(
                select(AutomationSuggestion)
                .where(
                    and_(
                        AutomationSuggestion.company_id == company_id,
                        AutomationSuggestion.suggestion_type == sugg["suggestion_type"],
                        AutomationSuggestion.status == SuggestionStatus.PENDING.value,
                    )
                )
                .limit(1)
            )

            if existing.scalar_one_or_none():
                continue  # Überspringe Duplikate

            suggestion = AutomationSuggestion(
                company_id=company_id,
                suggestion_type=sugg["suggestion_type"],
                title=sugg["title"],
                description=sugg.get("description"),
                pattern_description=sugg.get("pattern_description"),
                confidence=Decimal(str(sugg["confidence"])),
                potential_savings_hours=Decimal(str(sugg.get("potential_savings_hours", 0))),
                potential_savings_cost=Decimal(str(sugg.get("potential_savings_cost", 0))),
                affected_steps=sugg.get("affected_steps", []),
                trigger_conditions=sugg.get("trigger_conditions", {}),
                suggested_actions=sugg.get("suggested_actions", []),
                frequency_per_week=sugg.get("frequency_per_week"),
                status=SuggestionStatus.PENDING.value,
            )

            self.db.add(suggestion)
            saved.append(suggestion)

        await self.db.flush()
        logger.info(f"Saved {len(saved)} automation suggestions for company {company_id}")

        return saved

    async def get_pending_suggestions(
        self,
        company_id: UUID,
        limit: int = 10,
    ) -> List[AutomationSuggestion]:
        """
        Hole offene Vorschläge.

        Args:
            company_id: Mandanten-ID
            limit: Maximale Anzahl

        Returns:
            Liste offener Vorschläge
        """
        result = await self.db.execute(
            select(AutomationSuggestion)
            .where(
                and_(
                    AutomationSuggestion.company_id == company_id,
                    AutomationSuggestion.status == SuggestionStatus.PENDING.value,
                )
            )
            .order_by(desc(AutomationSuggestion.potential_savings_hours))
            .limit(limit)
        )

        return list(result.scalars().all())

    async def activate_suggestion(
        self,
        suggestion_id: UUID,
        user_id: UUID,
    ) -> Optional[AutomationSuggestion]:
        """
        Aktiviere einen Vorschlag.

        Args:
            suggestion_id: Vorschlags-ID
            user_id: Aktivierender Benutzer

        Returns:
            Aktualisierter Vorschlag
        """
        result = await self.db.execute(
            select(AutomationSuggestion)
            .where(AutomationSuggestion.id == suggestion_id)
        )
        suggestion = result.scalar_one_or_none()

        if suggestion:
            suggestion.status = SuggestionStatus.ACTIVATED.value
            suggestion.activated_at = datetime.utcnow()
            suggestion.activated_by_id = user_id
            await self.db.flush()

            logger.info(f"Activated automation suggestion {suggestion_id}")

        return suggestion

    async def reject_suggestion(
        self,
        suggestion_id: UUID,
        user_id: UUID,
        reason: Optional[str] = None,
    ) -> Optional[AutomationSuggestion]:
        """
        Lehne einen Vorschlag ab.

        Args:
            suggestion_id: Vorschlags-ID
            user_id: Ablehnender Benutzer
            reason: Ablehnungsgrund

        Returns:
            Aktualisierter Vorschlag
        """
        result = await self.db.execute(
            select(AutomationSuggestion)
            .where(AutomationSuggestion.id == suggestion_id)
        )
        suggestion = result.scalar_one_or_none()

        if suggestion:
            suggestion.status = SuggestionStatus.REJECTED.value
            suggestion.rejected_at = datetime.utcnow()
            suggestion.rejected_by_id = user_id
            suggestion.rejection_reason = reason
            await self.db.flush()

            logger.info(f"Rejected automation suggestion {suggestion_id}: {reason}")

        return suggestion

    async def get_suggestion_statistics(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Hole Statistiken über Vorschläge.

        Args:
            company_id: Mandanten-ID

        Returns:
            Statistiken
        """
        result = await self.db.execute(
            select(
                AutomationSuggestion.status,
                func.count(AutomationSuggestion.id).label('count'),
                func.sum(AutomationSuggestion.potential_savings_hours).label('total_savings'),
            )
            .where(AutomationSuggestion.company_id == company_id)
            .group_by(AutomationSuggestion.status)
        )

        stats_by_status = {row.status: {"count": row.count, "savings": float(row.total_savings or 0)} for row in result.all()}

        # Berechne realisierte Einsparungen (aktivierte Vorschläge)
        activated_savings = stats_by_status.get(SuggestionStatus.ACTIVATED.value, {}).get("savings", 0)

        return {
            "by_status": stats_by_status,
            "total_pending": stats_by_status.get(SuggestionStatus.PENDING.value, {}).get("count", 0),
            "total_activated": stats_by_status.get(SuggestionStatus.ACTIVATED.value, {}).get("count", 0),
            "realized_savings_hours": activated_savings,
            "realized_savings_cost": activated_savings * self.DEFAULT_HOURLY_RATE,
        }

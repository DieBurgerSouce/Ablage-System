# -*- coding: utf-8 -*-
"""
Document Lifecycle Service - Lebenszyklus-Verwaltung mit SLA-Ueberwachung.

Verwaltet den Lebenszyklus von Dokumenten durch definierte Stufen:
Eingang -> OCR -> Klassifizierung -> Pruefung -> Freigabe -> Buchung -> Archivierung

Features:
- Stufen-Uebergaenge mit Benutzer-Zuordnung
- SLA-Konfiguration pro Dokumenttyp und Stufe
- SLA-Verletzungserkennung
- Kanban-Uebersicht (Stufen-Zaehler)
- Stufen-Metriken (Durchschnittszeiten)

Feinpoliert und durchdacht - Enterprise-grade Document Lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, desc, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.db.models_document_lifecycle import (
    DocumentLifecycleConfig,
    DocumentLifecycleEvent,
    DocumentLifecycleStage,
    STAGE_ORDER,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class SLAViolation:
    """Repraesentiert eine SLA-Verletzung."""

    document_id: UUID
    document_filename: str
    document_type: str
    current_stage: str
    entered_stage_at: datetime
    max_duration_hours: int
    actual_duration_hours: float
    overdue_hours: float
    escalation_to_role: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert die SLA-Verletzung als Dictionary."""
        return {
            "document_id": str(self.document_id),
            "document_filename": self.document_filename,
            "document_type": self.document_type,
            "current_stage": self.current_stage,
            "entered_stage_at": self.entered_stage_at.isoformat(),
            "max_duration_hours": self.max_duration_hours,
            "actual_duration_hours": round(self.actual_duration_hours, 1),
            "overdue_hours": round(self.overdue_hours, 1),
            "escalation_to_role": self.escalation_to_role,
        }


@dataclass
class StageMetric:
    """Metriken fuer eine einzelne Lebenszyklus-Stufe."""

    stage: str
    avg_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    total_transitions: int
    sla_compliance_rate: float  # 0.0 - 1.0

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert die Stufen-Metrik als Dictionary."""
        return {
            "stage": self.stage,
            "avg_duration_seconds": round(self.avg_duration_seconds, 1),
            "min_duration_seconds": round(self.min_duration_seconds, 1),
            "max_duration_seconds": round(self.max_duration_seconds, 1),
            "total_transitions": self.total_transitions,
            "sla_compliance_rate": round(self.sla_compliance_rate, 3),
        }


# ============================================================================
# Service
# ============================================================================


class DocumentLifecycleService:
    """
    Verwaltet den Dokument-Lebenszyklus mit SLA-Ueberwachung.

    Bietet Methoden fuer Stufen-Uebergaenge, SLA-Pruefung,
    Kanban-Uebersicht und Stufen-Metriken.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service mit einer Datenbank-Session."""
        self.db = db

    async def transition_stage(
        self,
        document_id: UUID,
        company_id: UUID,
        to_stage: DocumentLifecycleStage,
        user_id: Optional[UUID] = None,
        note: Optional[str] = None,
    ) -> DocumentLifecycleEvent:
        """
        Fuehrt einen Stufen-Uebergang fuer ein Dokument durch.

        Args:
            document_id: ID des Dokuments
            company_id: ID des Mandanten
            to_stage: Ziel-Stufe
            user_id: ID des ausfuehrenden Benutzers
            note: Optionale Notiz zum Uebergang

        Returns:
            DocumentLifecycleEvent fuer den Uebergang

        Raises:
            ValueError: Bei ungueltiger Stufen-Kombination
        """
        # Aktuelle Stufe ermitteln
        current_stage = await self.get_current_stage(document_id)
        from_stage_value = current_stage.value if current_stage else None

        # Validierung: Stufe darf nicht zurueckgehen
        if current_stage is not None:
            current_idx = STAGE_ORDER.index(current_stage)
            target_idx = STAGE_ORDER.index(to_stage)
            if target_idx <= current_idx:
                raise ValueError(
                    f"Ungueltiger Uebergang: '{current_stage.value}' -> "
                    f"'{to_stage.value}'. Stufe kann nicht zurueckgesetzt werden."
                )

        # Dauer in der vorherigen Stufe berechnen
        duration_seconds: Optional[int] = None
        sla_met: Optional[bool] = None

        if current_stage is not None:
            last_event = await self._get_last_event(document_id)
            if last_event is not None and last_event.transitioned_at:
                now = datetime.now(timezone.utc)
                delta = now - last_event.transitioned_at
                duration_seconds = int(delta.total_seconds())

                # SLA pruefen
                sla_met = await self._check_stage_sla(
                    company_id=company_id,
                    document_id=document_id,
                    stage=current_stage,
                    duration_seconds=duration_seconds,
                )

        # Event erstellen
        event = DocumentLifecycleEvent(
            document_id=document_id,
            company_id=company_id,
            from_stage=from_stage_value,
            to_stage=to_stage.value,
            transitioned_by_id=user_id,
            duration_seconds=duration_seconds,
            sla_met=sla_met,
            note=note,
        )

        self.db.add(event)
        await self.db.flush()

        logger.info(
            "lifecycle_stage_transition",
            document_id=str(document_id),
            from_stage=from_stage_value,
            to_stage=to_stage.value,
            duration_seconds=duration_seconds,
            sla_met=sla_met,
        )

        return event

    async def get_current_stage(
        self, document_id: UUID
    ) -> Optional[DocumentLifecycleStage]:
        """
        Ermittelt die aktuelle Lebenszyklus-Stufe eines Dokuments.

        Args:
            document_id: ID des Dokuments

        Returns:
            Aktuelle Stufe oder None, wenn noch kein Event existiert
        """
        last_event = await self._get_last_event(document_id)
        if last_event is None:
            return None

        try:
            return DocumentLifecycleStage(last_event.to_stage)
        except ValueError:
            logger.warning(
                "unknown_lifecycle_stage",
                document_id=str(document_id),
                stage=last_event.to_stage,
            )
            return None

    async def check_sla_violations(
        self,
        company_id: UUID,
    ) -> List[SLAViolation]:
        """
        Prueft alle Dokumente eines Mandanten auf SLA-Verletzungen.

        Vergleicht die aktuelle Verweildauer in einer Stufe mit
        der konfigurierten maximalen Dauer.

        Args:
            company_id: ID des Mandanten

        Returns:
            Liste von SLA-Verletzungen
        """
        violations: List[SLAViolation] = []
        now = datetime.now(timezone.utc)

        try:
            # Alle SLA-Konfigurationen fuer diesen Mandanten laden
            config_stmt = select(DocumentLifecycleConfig).where(
                and_(
                    DocumentLifecycleConfig.company_id == company_id,
                    DocumentLifecycleConfig.is_active == True,  # noqa: E712
                )
            )
            config_result = await self.db.execute(config_stmt)
            configs = config_result.scalars().all()

            if not configs:
                return violations

            # Konfigurationen nach (document_type, stage) indexieren
            config_map: Dict[Tuple[str, str], DocumentLifecycleConfig] = {}
            for config in configs:
                config_map[(config.document_type, config.stage)] = config

            # Letzte Events pro Dokument finden (Subquery)
            # Wir nutzen eine korrelierte Subquery fuer das letzte Event
            latest_event_subq = (
                select(
                    DocumentLifecycleEvent.document_id,
                    func.max(DocumentLifecycleEvent.transitioned_at).label(
                        "latest_at"
                    ),
                )
                .where(DocumentLifecycleEvent.company_id == company_id)
                .group_by(DocumentLifecycleEvent.document_id)
                .subquery()
            )

            # Events mit den neuesten Zeitstempeln joinen
            stmt = (
                select(DocumentLifecycleEvent, Document)
                .join(
                    latest_event_subq,
                    and_(
                        DocumentLifecycleEvent.document_id
                        == latest_event_subq.c.document_id,
                        DocumentLifecycleEvent.transitioned_at
                        == latest_event_subq.c.latest_at,
                    ),
                )
                .join(
                    Document,
                    DocumentLifecycleEvent.document_id == Document.id,
                )
                .where(
                    and_(
                        DocumentLifecycleEvent.company_id == company_id,
                        # Archivierte Dokumente ausschliessen
                        DocumentLifecycleEvent.to_stage
                        != DocumentLifecycleStage.ARCHIVIERUNG.value,
                    )
                )
            )

            result = await self.db.execute(stmt)
            rows = result.all()

            for event, document in rows:
                doc_type = document.document_type or "other"
                stage = event.to_stage

                config = config_map.get((doc_type, stage))
                if config is None:
                    # Fallback: allgemeine Konfiguration ohne Dokumenttyp-Filter
                    config = config_map.get(("*", stage))
                if config is None:
                    continue

                # Verweildauer berechnen
                entered_at = event.transitioned_at
                if entered_at is None:
                    continue

                duration = now - entered_at
                duration_hours = duration.total_seconds() / 3600.0

                if duration_hours > config.max_duration_hours:
                    violations.append(
                        SLAViolation(
                            document_id=document.id,
                            document_filename=document.filename or "",
                            document_type=doc_type,
                            current_stage=stage,
                            entered_stage_at=entered_at,
                            max_duration_hours=config.max_duration_hours,
                            actual_duration_hours=duration_hours,
                            overdue_hours=duration_hours
                            - config.max_duration_hours,
                            escalation_to_role=config.escalation_to_role,
                        )
                    )

            logger.info(
                "sla_violations_checked",
                company_id=str(company_id),
                violations_found=len(violations),
            )

        except Exception as e:
            logger.error(
                "sla_violation_check_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )

        return violations

    async def get_lifecycle_overview(
        self,
        company_id: UUID,
    ) -> Dict[str, int]:
        """
        Gibt eine Kanban-Uebersicht zurueck: Anzahl Dokumente pro Stufe.

        Args:
            company_id: ID des Mandanten

        Returns:
            Dictionary mit Stufe -> Anzahl Dokumente
        """
        overview: Dict[str, int] = {
            stage.value: 0 for stage in DocumentLifecycleStage
        }

        try:
            # Neueste Stufe pro Dokument ermitteln
            latest_event_subq = (
                select(
                    DocumentLifecycleEvent.document_id,
                    func.max(DocumentLifecycleEvent.transitioned_at).label(
                        "latest_at"
                    ),
                )
                .where(DocumentLifecycleEvent.company_id == company_id)
                .group_by(DocumentLifecycleEvent.document_id)
                .subquery()
            )

            stmt = (
                select(
                    DocumentLifecycleEvent.to_stage,
                    func.count().label("count"),
                )
                .join(
                    latest_event_subq,
                    and_(
                        DocumentLifecycleEvent.document_id
                        == latest_event_subq.c.document_id,
                        DocumentLifecycleEvent.transitioned_at
                        == latest_event_subq.c.latest_at,
                    ),
                )
                .where(DocumentLifecycleEvent.company_id == company_id)
                .group_by(DocumentLifecycleEvent.to_stage)
            )

            result = await self.db.execute(stmt)
            for row in result.all():
                stage_name = row[0]
                count = row[1]
                if stage_name in overview:
                    overview[stage_name] = count

        except Exception as e:
            logger.error(
                "lifecycle_overview_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )

        return overview

    async def get_stage_metrics(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> List[StageMetric]:
        """
        Berechnet Metriken pro Lebenszyklus-Stufe.

        Args:
            company_id: ID des Mandanten
            days: Zeitraum in Tagen (Standard: 30)

        Returns:
            Liste von StageMetric-Objekten
        """
        metrics: List[StageMetric] = []
        since = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            stmt = (
                select(
                    DocumentLifecycleEvent.to_stage,
                    func.avg(DocumentLifecycleEvent.duration_seconds).label(
                        "avg_duration"
                    ),
                    func.min(DocumentLifecycleEvent.duration_seconds).label(
                        "min_duration"
                    ),
                    func.max(DocumentLifecycleEvent.duration_seconds).label(
                        "max_duration"
                    ),
                    func.count().label("total"),
                    func.avg(
                        case(
                            (DocumentLifecycleEvent.sla_met == True, 1.0),  # noqa: E712
                            else_=0.0,
                        )
                    ).label("sla_rate"),
                )
                .where(
                    and_(
                        DocumentLifecycleEvent.company_id == company_id,
                        DocumentLifecycleEvent.transitioned_at >= since,
                        DocumentLifecycleEvent.duration_seconds.isnot(None),
                    )
                )
                .group_by(DocumentLifecycleEvent.to_stage)
            )

            result = await self.db.execute(stmt)
            for row in result.all():
                metrics.append(
                    StageMetric(
                        stage=row[0],
                        avg_duration_seconds=float(row[1] or 0),
                        min_duration_seconds=float(row[2] or 0),
                        max_duration_seconds=float(row[3] or 0),
                        total_transitions=int(row[4] or 0),
                        sla_compliance_rate=float(row[5] or 0),
                    )
                )

        except Exception as e:
            logger.error(
                "stage_metrics_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )

        return metrics

    async def get_document_history(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> List[DocumentLifecycleEvent]:
        """
        Gibt die vollstaendige Lebenszyklus-Historie eines Dokuments zurueck.

        Args:
            document_id: ID des Dokuments
            company_id: ID des Mandanten

        Returns:
            Liste von DocumentLifecycleEvent-Objekten, chronologisch sortiert
        """
        stmt = (
            select(DocumentLifecycleEvent)
            .where(
                and_(
                    DocumentLifecycleEvent.document_id == document_id,
                    DocumentLifecycleEvent.company_id == company_id,
                )
            )
            .order_by(DocumentLifecycleEvent.transitioned_at)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ========================================================================
    # Private Helpers
    # ========================================================================

    async def _get_last_event(
        self, document_id: UUID
    ) -> Optional[DocumentLifecycleEvent]:
        """Letztes Lifecycle-Event fuer ein Dokument abrufen."""
        stmt = (
            select(DocumentLifecycleEvent)
            .where(DocumentLifecycleEvent.document_id == document_id)
            .order_by(desc(DocumentLifecycleEvent.transitioned_at))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _check_stage_sla(
        self,
        company_id: UUID,
        document_id: UUID,
        stage: DocumentLifecycleStage,
        duration_seconds: int,
    ) -> bool:
        """Prueft ob die SLA fuer eine Stufe eingehalten wurde."""
        # Dokumenttyp ermitteln
        doc_stmt = select(Document.document_type).where(
            Document.id == document_id
        )
        doc_result = await self.db.execute(doc_stmt)
        doc_type = doc_result.scalar_one_or_none() or "other"

        # SLA-Konfiguration suchen
        stmt = select(DocumentLifecycleConfig).where(
            and_(
                DocumentLifecycleConfig.company_id == company_id,
                DocumentLifecycleConfig.document_type.in_([doc_type, "*"]),
                DocumentLifecycleConfig.stage == stage.value,
                DocumentLifecycleConfig.is_active == True,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None:
            # Keine SLA konfiguriert = immer eingehalten
            return True

        duration_hours = duration_seconds / 3600.0
        return duration_hours <= config.max_duration_hours


def get_document_lifecycle_service(
    db: AsyncSession,
) -> DocumentLifecycleService:
    """Factory-Funktion fuer den DocumentLifecycleService."""
    return DocumentLifecycleService(db)

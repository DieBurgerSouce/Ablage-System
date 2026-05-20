# -*- coding: utf-8 -*-
"""
Workflow Insights Service.

Enterprise Feature: Proaktive Workflow-Optimierungsvorschläge.

Dieses Modul analysiert Workflows und generiert Optimierungsvorschläge:

- Batch-Genehmigungen: "5 Rechnungen vom gleichen Lieferanten warten auf Genehmigung"
- Bottleneck-Erkennung: "Genehmigungsstau bei User X (15 Dokumente)"
- Automatisierungsvorschläge: "Diese 8 Rechnungen könnten automatisch genehmigt werden"
- Delegationsvorschläge: "User X ist überlastet, Delegation empfohlen"

Integration mit: ApprovalService, WorkflowService, DelegationService
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.proactive_insights_service import (
    ExtractedEntity,
    EntityType,
    InsightPriority,
    InsightType,
    ProactiveInsight,
)

logger = structlog.get_logger(__name__)


class WorkflowInsightType(str, Enum):
    """Typ des Workflow-Insights."""
    BATCH_APPROVAL = "batch_approval"           # Batch-Genehmigung möglich
    BOTTLENECK = "bottleneck"                   # Engpass erkannt
    AUTOMATION_POSSIBLE = "automation_possible" # Automatisierung möglich
    DELEGATION_SUGGESTED = "delegation_suggested"  # Delegation empfohlen
    STALE_ITEMS = "stale_items"                 # Veraltete Elemente
    WORKLOAD_IMBALANCE = "workload_imbalance"   # Ungleiche Arbeitslast


class BottleneckSeverity(str, Enum):
    """Schweregrad des Bottlenecks."""
    CRITICAL = "critical"   # >20 Elemente oder >7 Tage alt
    HIGH = "high"           # >10 Elemente oder >3 Tage alt
    MEDIUM = "medium"       # >5 Elemente oder >1 Tag alt
    LOW = "low"             # >3 Elemente


@dataclass
class WorkflowInsight:
    """Ein Workflow-Insight mit Details."""
    insight_type: WorkflowInsightType
    title: str
    description: str
    affected_users: List[UUID] = field(default_factory=list)
    affected_documents: List[UUID] = field(default_factory=list)
    pending_count: int = 0
    avg_wait_time_hours: float = 0.0
    potential_time_savings_hours: float = 0.0
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_proactive_insight(self) -> ProactiveInsight:
        """Konvertiert zu ProactiveInsight."""
        priority_map = {
            WorkflowInsightType.BOTTLENECK: InsightPriority.HIGH,
            WorkflowInsightType.BATCH_APPROVAL: InsightPriority.MEDIUM,
            WorkflowInsightType.STALE_ITEMS: InsightPriority.HIGH,
            WorkflowInsightType.AUTOMATION_POSSIBLE: InsightPriority.MEDIUM,
            WorkflowInsightType.DELEGATION_SUGGESTED: InsightPriority.MEDIUM,
            WorkflowInsightType.WORKLOAD_IMBALANCE: InsightPriority.LOW,
        }

        insight_type_map = {
            WorkflowInsightType.BOTTLENECK: InsightType.WARNING,
            WorkflowInsightType.BATCH_APPROVAL: InsightType.OPTIMIZATION,
            WorkflowInsightType.STALE_ITEMS: InsightType.WARNING,
            WorkflowInsightType.AUTOMATION_POSSIBLE: InsightType.RECOMMENDATION,
            WorkflowInsightType.DELEGATION_SUGGESTED: InsightType.RECOMMENDATION,
            WorkflowInsightType.WORKLOAD_IMBALANCE: InsightType.INFORMATION,
        }

        return ProactiveInsight(
            insight_type=insight_type_map.get(self.insight_type, InsightType.INFORMATION),
            priority=priority_map.get(self.insight_type, InsightPriority.MEDIUM),
            title=self.title,
            message=self.description,
            detail=self._generate_detail(),
            action_url=self.action_url,
            action_label=self.action_label,
            source_rule=f"workflow_{self.insight_type.value}",
            related_entities=[
                ExtractedEntity(
                    entity_type=EntityType.GENERAL,
                    entity_name=f"Workflow ({self.pending_count} Items)",
                    confidence=1.0,
                )
            ],
        )

    def _generate_detail(self) -> str:
        """Generiert Detail-Text."""
        details = []

        if self.pending_count > 0:
            details.append(f"Wartende Elemente: {self.pending_count}")

        if self.avg_wait_time_hours > 0:
            if self.avg_wait_time_hours >= 24:
                days = self.avg_wait_time_hours / 24
                details.append(f"Durchschnittliche Wartezeit: {days:.1f} Tage")
            else:
                details.append(f"Durchschnittliche Wartezeit: {self.avg_wait_time_hours:.1f} Stunden")

        if self.potential_time_savings_hours > 0:
            details.append(f"Potenzielle Zeiteinsparung: {self.potential_time_savings_hours:.1f} Stunden")

        return " | ".join(details) if details else ""


@dataclass
class WorkflowCheckResult:
    """Ergebnis einer Workflow-Prüfung."""
    insight_type: WorkflowInsightType
    title: str
    message: str
    detail: str = ""
    priority: str = "medium"
    affected_items: List[UUID] = field(default_factory=list)
    suggested_action: Optional[str] = None
    potential_time_savings_minutes: Optional[int] = None

    def to_insight(self) -> ProactiveInsight:
        """Konvertiert zu ProactiveInsight."""
        priority_map = {"critical": InsightPriority.CRITICAL, "high": InsightPriority.HIGH,
                        "medium": InsightPriority.MEDIUM, "low": InsightPriority.LOW}
        return ProactiveInsight(
            insight_type=InsightType.SUGGESTION,
            priority=priority_map.get(self.priority, InsightPriority.MEDIUM),
            title=self.title,
            message=self.message,
            detail=self.detail,
        )


class WorkflowInsightsService:
    """
    Service für proaktive Workflow-Optimierung.

    Analysiert Genehmigungs-Workflows, erkennt Engpaesse und
    schlaegt Optimierungen vor.
    """

    def __init__(self) -> None:
        # Schwellwerte
        self._batch_threshold = 3          # Mind. 3 Elemente für Batch
        self._bottleneck_threshold = 5     # Mind. 5 Elemente für Bottleneck
        self._stale_threshold_hours = 48   # 48h ohne Bearbeitung = stale
        self._overload_threshold = 10      # >10 Elemente = überlastet

        logger.info("workflow_insights_service_initialized")

    async def check_all_workflow_insights(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> List[ProactiveInsight]:
        """
        Prüft alle Workflow-Insights.

        Args:
            db: Datenbank-Session
            company_id: ID der Company
            user_id: Optional User-ID für benutzerspezifische Insights

        Returns:
            Liste von ProactiveInsights
        """
        logger.info(
            "checking_workflow_insights",
            company_id=str(company_id),
            user_id=str(user_id) if user_id else None,
        )

        all_insights: List[ProactiveInsight] = []

        # Parallel alle Workflow-Checks ausführen
        results = await asyncio.gather(
            self.suggest_batch_approvals(db, company_id, user_id),
            self.detect_bottlenecks(db, company_id),
            self.suggest_automation(db, company_id),
            self.detect_stale_items(db, company_id),
            self.analyze_workload_distribution(db, company_id),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "workflow_check_failed",
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
            "workflow_insights_checked",
            total_insights=len(all_insights),
        )

        return all_insights

    async def suggest_batch_approvals(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> List[ProactiveInsight]:
        """
        Schlaegt Batch-Genehmigungen vor.

        Findet Gruppen von ähnlichen Dokumenten, die gemeinsam
        genehmigt werden könnten.

        Args:
            db: Datenbank-Session
            company_id: ID der Company
            user_id: Optional User-ID (Genehmiger)

        Returns:
            Liste von ProactiveInsights für Batch-Genehmigungen
        """
        from app.db.models import ApprovalRequest, Document, BusinessEntity

        try:
            # Offene Genehmigungsanfragen finden
            query = select(
                ApprovalRequest,
                Document,
                BusinessEntity.name.label("supplier_name"),
            ).join(
                Document, ApprovalRequest.document_id == Document.id
            ).outerjoin(
                BusinessEntity, Document.linked_entity_id == BusinessEntity.id
            ).where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == "pending",
                )
            )

            if user_id:
                query = query.where(
                    or_(
                        ApprovalRequest.assignee_id == user_id,
                        ApprovalRequest.assignee_id.is_(None),
                    )
                )

            result = await db.execute(query)
            rows = result.fetchall()

            if not rows:
                return []

            # Gruppiere nach Lieferant
            supplier_groups: Dict[str, List[Tuple[ApprovalRequest, Document]]] = defaultdict(list)
            for row in rows:
                approval, doc, supplier_name = row
                supplier_key = supplier_name or "Unbekannt"
                supplier_groups[supplier_key].append((approval, doc))

            insights: List[WorkflowInsight] = []

            for supplier_name, items in supplier_groups.items():
                if len(items) >= self._batch_threshold:
                    total_amount = sum(
                        float(doc.total_amount or 0)
                        for _, doc in items
                    )

                    insight = WorkflowInsight(
                        insight_type=WorkflowInsightType.BATCH_APPROVAL,
                        title=f"Batch-Genehmigung: {supplier_name}",
                        description=f"{len(items)} Rechnungen von {supplier_name} warten auf Genehmigung.",
                        affected_documents=[doc.id for _, doc in items],
                        pending_count=len(items),
                        potential_time_savings_hours=len(items) * 0.25,  # 15 Min pro Dokument
                        action_url=f"/approvals?supplier={supplier_name}&batch=true",
                        action_label="Batch genehmigen",
                        metadata={
                            "supplier_name": supplier_name,
                            "total_amount": total_amount,
                        },
                    )
                    insights.append(insight)

            # Gruppiere nach Dokumenttyp
            type_groups: Dict[str, List[Tuple[ApprovalRequest, Document]]] = defaultdict(list)
            for row in rows:
                approval, doc, _ = row
                doc_type = doc.document_type or "unknown"
                type_groups[doc_type].append((approval, doc))

            for doc_type, items in type_groups.items():
                if len(items) >= self._batch_threshold * 2:  # Höherer Schwellwert für Typ-Batches
                    insight = WorkflowInsight(
                        insight_type=WorkflowInsightType.BATCH_APPROVAL,
                        title=f"Batch-Genehmigung: {doc_type}",
                        description=f"{len(items)} {doc_type} Dokumente warten auf Genehmigung.",
                        affected_documents=[doc.id for _, doc in items],
                        pending_count=len(items),
                        potential_time_savings_hours=len(items) * 0.2,
                        action_url=f"/approvals?type={doc_type}&batch=true",
                        action_label="Alle prüfen",
                        metadata={
                            "document_type": doc_type,
                        },
                    )
                    insights.append(insight)

            proactive_insights = [i.to_proactive_insight() for i in insights]

            logger.info(
                "batch_approvals_suggested",
                company_id=str(company_id),
                suggestions_count=len(proactive_insights),
            )

            return proactive_insights

        except Exception as e:
            logger.warning(
                "batch_approval_suggestion_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_bottlenecks(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt Workflow-Engpaesse.

        Findet Benutzer mit vielen wartenden Genehmigungen oder
        lange wartende Dokumente.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Bottlenecks
        """
        from app.db.models import ApprovalRequest, User

        try:
            now = datetime.now(timezone.utc)

            # Zaehle wartende Genehmigungen pro Benutzer
            query = select(
                ApprovalRequest.assignee_id,
                func.count().label("pending_count"),
                func.min(ApprovalRequest.created_at).label("oldest"),
                func.avg(
                    func.extract('epoch', now - ApprovalRequest.created_at) / 3600
                ).label("avg_wait_hours"),
            ).where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.assignee_id.isnot(None),
                )
            ).group_by(ApprovalRequest.assignee_id)

            result = await db.execute(query)
            user_stats = result.fetchall()

            insights: List[WorkflowInsight] = []

            for row in user_stats:
                assignee_id, pending_count, oldest, avg_wait_hours = row

                if pending_count >= self._bottleneck_threshold:
                    # Benutzernamen laden
                    user_query = select(User.email, User.full_name).where(User.id == assignee_id)
                    user_result = await db.execute(user_query)
                    user_row = user_result.fetchone()
                    user_name = user_row[1] or user_row[0] if user_row else "Unbekannt"

                    # Schweregrad berechnen
                    if pending_count > 20 or (avg_wait_hours or 0) > 168:  # >1 Woche
                        severity = BottleneckSeverity.CRITICAL
                    elif pending_count > 10 or (avg_wait_hours or 0) > 72:  # >3 Tage
                        severity = BottleneckSeverity.HIGH
                    elif pending_count > 5 or (avg_wait_hours or 0) > 24:
                        severity = BottleneckSeverity.MEDIUM
                    else:
                        severity = BottleneckSeverity.LOW

                    insight = WorkflowInsight(
                        insight_type=WorkflowInsightType.BOTTLENECK,
                        title=f"Genehmigungsstau bei {user_name}",
                        description=f"{pending_count} Dokumente warten auf Genehmigung durch {user_name}.",
                        affected_users=[assignee_id] if assignee_id else [],
                        pending_count=pending_count,
                        avg_wait_time_hours=float(avg_wait_hours or 0),
                        action_url=f"/admin/approvals?assignee={assignee_id}",
                        action_label="Übersicht öffnen",
                        metadata={
                            "severity": severity.value,
                            "assignee_id": str(assignee_id),
                            "assignee_name": user_name,
                            "oldest_request": oldest.isoformat() if oldest else None,
                        },
                    )
                    insights.append(insight)

            proactive_insights = [i.to_proactive_insight() for i in insights]

            logger.info(
                "bottlenecks_detected",
                company_id=str(company_id),
                bottlenecks_count=len(proactive_insights),
            )

            return proactive_insights

        except Exception as e:
            logger.warning(
                "bottleneck_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def suggest_automation(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Schlaegt Automatisierungsmöglichkeiten vor.

        Findet wiederkehrende Muster, die automatisiert werden könnten.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Automatisierung
        """
        from app.db.models import ApprovalRequest, Document, BusinessEntity

        try:
            # Analysiere historisch genehmigte Dokumente
            # Finde Muster: Gleicher Lieferant + Betrag unter X -> immer genehmigt
            approved_query = select(
                BusinessEntity.id.label("entity_id"),
                BusinessEntity.name.label("entity_name"),
                func.count().label("approved_count"),
                func.avg(Document.total_amount).label("avg_amount"),
                func.max(Document.total_amount).label("max_amount"),
            ).select_from(ApprovalRequest).join(
                Document, ApprovalRequest.document_id == Document.id
            ).join(
                BusinessEntity, Document.linked_entity_id == BusinessEntity.id
            ).where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == "approved",
                    ApprovalRequest.created_at >= datetime.now(timezone.utc) - timedelta(days=180),
                )
            ).group_by(
                BusinessEntity.id, BusinessEntity.name
            ).having(func.count() >= 10)  # Mind. 10 genehmigte Dokumente

            result = await db.execute(approved_query)
            high_approval_entities = result.fetchall()

            insights: List[WorkflowInsight] = []

            for row in high_approval_entities:
                entity_id, entity_name, approved_count, avg_amount, max_amount = row

                # Prüfe ob es wartende Dokumente von diesem Lieferanten gibt
                pending_query = select(func.count()).select_from(
                    ApprovalRequest
                ).join(
                    Document, ApprovalRequest.document_id == Document.id
                ).where(
                    and_(
                        ApprovalRequest.company_id == company_id,
                        ApprovalRequest.status == "pending",
                        Document.linked_entity_id == entity_id,
                        Document.total_amount <= max_amount,
                    )
                )
                pending_result = await db.execute(pending_query)
                pending_count = pending_result.scalar() or 0

                if pending_count >= 3:
                    insight = WorkflowInsight(
                        insight_type=WorkflowInsightType.AUTOMATION_POSSIBLE,
                        title=f"Auto-Genehmigung für {entity_name}",
                        description=f"{pending_count} Dokumente von {entity_name} könnten automatisch genehmigt werden.",
                        pending_count=pending_count,
                        potential_time_savings_hours=pending_count * 0.5,  # 30 Min pro Dokument
                        action_url=f"/admin/rules/create?entity={entity_id}&type=auto_approve",
                        action_label="Regel erstellen",
                        metadata={
                            "entity_id": str(entity_id),
                            "entity_name": entity_name,
                            "historical_approvals": approved_count,
                            "avg_amount": float(avg_amount or 0),
                            "max_amount": float(max_amount or 0),
                        },
                    )
                    insights.append(insight)

            proactive_insights = [i.to_proactive_insight() for i in insights]

            logger.info(
                "automation_suggested",
                company_id=str(company_id),
                suggestions_count=len(proactive_insights),
            )

            return proactive_insights

        except Exception as e:
            logger.warning(
                "automation_suggestion_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_stale_items(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt veraltete/unbearbeitete Elemente.

        Findet Dokumente, die zu lange auf Bearbeitung warten.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für veraltete Elemente
        """
        from app.db.models import ApprovalRequest, Document

        try:
            now = datetime.now(timezone.utc)
            stale_cutoff = now - timedelta(hours=self._stale_threshold_hours)

            # Finde veraltete Genehmigungsanfragen
            stale_query = select(
                ApprovalRequest,
                Document.original_filename,
            ).join(
                Document, ApprovalRequest.document_id == Document.id
            ).where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.created_at < stale_cutoff,
                )
            ).order_by(ApprovalRequest.created_at.asc())

            result = await db.execute(stale_query)
            stale_items = result.fetchall()

            if not stale_items:
                return []

            # Gruppiere nach Alter
            very_old = []  # >7 Tage
            old = []       # >3 Tage
            stale = []     # >48h

            for approval, doc_title in stale_items:
                age_hours = (now - approval.created_at).total_seconds() / 3600
                if age_hours > 168:  # >7 Tage
                    very_old.append((approval, doc_title, age_hours))
                elif age_hours > 72:  # >3 Tage
                    old.append((approval, doc_title, age_hours))
                else:
                    stale.append((approval, doc_title, age_hours))

            insights: List[WorkflowInsight] = []

            if very_old:
                insight = WorkflowInsight(
                    insight_type=WorkflowInsightType.STALE_ITEMS,
                    title=f"{len(very_old)} Dokumente seit über 7 Tagen unbearbeitet",
                    description="Diese Dokumente warten dringend auf Bearbeitung.",
                    affected_documents=[a.document_id for a, _, _ in very_old],
                    pending_count=len(very_old),
                    avg_wait_time_hours=sum(h for _, _, h in very_old) / len(very_old),
                    action_url="/approvals?filter=very_old",
                    action_label="Jetzt bearbeiten",
                    metadata={
                        "age_category": "very_old",
                        "min_age_days": 7,
                    },
                )
                insights.append(insight)

            if old:
                insight = WorkflowInsight(
                    insight_type=WorkflowInsightType.STALE_ITEMS,
                    title=f"{len(old)} Dokumente seit über 3 Tagen unbearbeitet",
                    description="Diese Dokumente sollten bald bearbeitet werden.",
                    affected_documents=[a.document_id for a, _, _ in old],
                    pending_count=len(old),
                    avg_wait_time_hours=sum(h for _, _, h in old) / len(old),
                    action_url="/approvals?filter=old",
                    action_label="Prüfen",
                    metadata={
                        "age_category": "old",
                        "min_age_days": 3,
                    },
                )
                insights.append(insight)

            proactive_insights = [i.to_proactive_insight() for i in insights]

            logger.info(
                "stale_items_detected",
                company_id=str(company_id),
                very_old_count=len(very_old),
                old_count=len(old),
                stale_count=len(stale),
            )

            return proactive_insights

        except Exception as e:
            logger.warning(
                "stale_items_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def analyze_workload_distribution(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Analysiert die Arbeitslastverteilung.

        Erkennt Ungleichgewichte in der Zuweisung von Aufgaben.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Arbeitslast-Ungleichgewichte
        """
        from app.db.models import ApprovalRequest, User


        try:
            # Lade Arbeitslast pro Benutzer
            query = select(
                ApprovalRequest.assignee_id,
                func.count().label("pending_count"),
            ).where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.assignee_id.isnot(None),
                )
            ).group_by(ApprovalRequest.assignee_id)

            result = await db.execute(query)
            workloads = result.fetchall()

            if len(workloads) < 2:
                return []

            # Statistiken berechnen
            counts = [w[1] for w in workloads]
            avg_workload = sum(counts) / len(counts)
            max_workload = max(counts)
            min_workload = min(counts)

            insights: List[WorkflowInsight] = []

            # Ungleichgewicht erkennen
            if max_workload > avg_workload * 2 and min_workload < avg_workload * 0.5:
                overloaded_users = []
                underloaded_users = []

                for assignee_id, count in workloads:
                    if count > avg_workload * 1.5:
                        overloaded_users.append((assignee_id, count))
                    elif count < avg_workload * 0.5:
                        underloaded_users.append((assignee_id, count))

                if overloaded_users and underloaded_users:
                    # Namen laden
                    all_ids = [u[0] for u in overloaded_users + underloaded_users]
                    names_query = select(User.id, User.full_name, User.email).where(User.id.in_(all_ids))
                    names_result = await db.execute(names_query)
                    names_map = {row[0]: row[1] or row[2] for row in names_result.fetchall()}

                    overloaded_names = [names_map.get(u[0], "Unbekannt") for u in overloaded_users[:3]]
                    underloaded_names = [names_map.get(u[0], "Unbekannt") for u in underloaded_users[:3]]

                    insight = WorkflowInsight(
                        insight_type=WorkflowInsightType.WORKLOAD_IMBALANCE,
                        title="Ungleiche Arbeitslastverteilung",
                        description=f"Überlastet: {', '.join(overloaded_names)}. Kapazität frei: {', '.join(underloaded_names)}.",
                        affected_users=[u[0] for u in overloaded_users + underloaded_users],
                        pending_count=sum(counts),
                        action_url="/admin/workload",
                        action_label="Arbeitslast verteilen",
                        metadata={
                            "avg_workload": avg_workload,
                            "max_workload": max_workload,
                            "min_workload": min_workload,
                            "overloaded_count": len(overloaded_users),
                            "underloaded_count": len(underloaded_users),
                        },
                    )
                    insights.append(insight)

            proactive_insights = [i.to_proactive_insight() for i in insights]

            logger.info(
                "workload_analyzed",
                company_id=str(company_id),
                imbalances_found=len(proactive_insights),
            )

            return proactive_insights

        except Exception as e:
            logger.warning(
                "workload_analysis_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def get_workflow_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Erstellt eine Zusammenfassung aller Workflow-Insights.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Zusammenfassung mit Counts und Metriken
        """
        insights = await self.check_all_workflow_insights(db, company_id)

        summary: Dict[str, Any] = {
            "total_count": len(insights),
            "by_type": {},
            "by_priority": {},
        }

        for insight in insights:
            # Nach Typ zaehlen
            rule_type = insight.source_rule or "unknown"
            if rule_type not in summary["by_type"]:
                summary["by_type"][rule_type] = 0
            summary["by_type"][rule_type] += 1

            # Nach Priorität zaehlen
            priority = insight.priority.value
            if priority not in summary["by_priority"]:
                summary["by_priority"][priority] = 0
            summary["by_priority"][priority] += 1

        return summary


# Singleton-Instanz
_workflow_insights_instance: Optional[WorkflowInsightsService] = None


def get_workflow_insights_service() -> WorkflowInsightsService:
    """Gibt die Singleton-Instanz des Workflow Insights Service zurück."""
    global _workflow_insights_instance
    if _workflow_insights_instance is None:
        _workflow_insights_instance = WorkflowInsightsService()
    return _workflow_insights_instance

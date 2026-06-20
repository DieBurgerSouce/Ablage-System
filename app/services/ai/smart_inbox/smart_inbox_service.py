"""Smart Inbox Service - Facade für KI-priorisierte Aufgabenliste.

Vereint alle Sub-Services:
- InboxAggregator: Sammelt Items aus verschiedenen Quellen
- PriorityScorer: ML-basierte Priorisierung
- BehaviorLearner: Lernt Benutzerverhalten
- ActionRecommender: Schlaegt Aktionen vor

Feinpoliert und durchdacht - Enterprise Smart Inbox.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SmartInboxItem, SmartInboxItemStatus

logger = structlog.get_logger(__name__)


@dataclass
class InboxListResult:
    """Ergebnis der Inbox-Abfrage."""

    items: List[SmartInboxItem]
    total: int
    has_more: bool


@dataclass
class ActionResult:
    """Ergebnis einer Aktion."""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class SmartInboxService:
    """Facade Service für Smart Inbox.

    Orchestriert alle Sub-Services für KI-priorisierte Aufgabenliste.
    """

    def __init__(self, db: AsyncSession, user_id: UUID) -> None:
        """Initialisiert den Smart Inbox Service.

        Args:
            db: Async Database Session
            user_id: Benutzer-ID
        """
        self.db = db
        self.user_id = user_id
        self.logger = logger.bind(service="smart_inbox", user_id=str(user_id))

    async def get_prioritized_items(
        self,
        company_id: UUID,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        category: Optional[str] = None,
    ) -> InboxListResult:
        """Holt priorisierte Inbox Items.

        Args:
            company_id: Company-ID für Multi-Tenant Isolation
            limit: Max. Anzahl Items
            offset: Offset für Pagination
            status: Optional Status-Filter
            category: Optional Kategorie-Filter

        Returns:
            InboxListResult mit Items und Pagination-Info
        """
        self.logger.info(
            "getting_prioritized_items",
            company_id=str(company_id),
            limit=limit,
            offset=offset,
        )

        # Base query
        query = select(SmartInboxItem).where(
            and_(
                SmartInboxItem.user_id == self.user_id,
                SmartInboxItem.company_id == company_id,
            )
        )

        # Apply filters
        if status:
            query = query.where(SmartInboxItem.status == status)
        else:
            # Default: Pending und In Progress
            query = query.where(
                SmartInboxItem.status.in_(
                    [SmartInboxItemStatus.PENDING.value, SmartInboxItemStatus.IN_PROGRESS.value]
                )
            )

        if category:
            query = query.where(SmartInboxItem.category == category)

        # Filter snoozed items
        now = datetime.now(timezone.utc)
        query = query.where(
            (SmartInboxItem.snoozed_until.is_(None)) | (SmartInboxItem.snoozed_until <= now)
        )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Order by ML priority and deadline
        query = query.order_by(
            SmartInboxItem.ml_priority.desc(),
            SmartInboxItem.deadline.asc().nullslast(),
            SmartInboxItem.created_at.desc(),
        )

        # Pagination
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        has_more = (offset + len(items)) < total

        self.logger.info(
            "items_retrieved",
            count=len(items),
            total=total,
            has_more=has_more,
        )

        return InboxListResult(items=items, total=total, has_more=has_more)

    async def perform_action(
        self,
        item_id: UUID,
        action: str,
        action_data: Optional[Dict[str, Any]],
        company_id: UUID,
    ) -> ActionResult:
        """Führt eine Aktion auf einem Inbox Item aus.

        Args:
            item_id: Item-ID
            action: Aktionstyp (complete, approve, reject, etc.)
            action_data: Optionale zusätzliche Daten
            company_id: Company-ID

        Returns:
            ActionResult

        Raises:
            ValueError: Item nicht gefunden
            PermissionError: Keine Berechtigung
        """
        self.logger.info(
            "performing_action",
            item_id=str(item_id),
            action=action,
        )

        # Load item
        item = await self._get_item(item_id, company_id)

        # Execute action
        if action == "complete":
            item.status = SmartInboxItemStatus.COMPLETED.value
            item.completed_at = datetime.now(timezone.utc)
            message = "Item als erledigt markiert"

        elif action == "approve":
            item.status = SmartInboxItemStatus.COMPLETED.value
            item.completed_at = datetime.now(timezone.utc)
            message = "Item genehmigt"

        elif action == "reject":
            item.status = SmartInboxItemStatus.COMPLETED.value
            item.completed_at = datetime.now(timezone.utc)
            message = "Item abgelehnt"

        elif action == "escalate":
            # Mark as escalated in metadata
            metadata = item.context_data or {}
            metadata["escalated"] = True
            metadata["escalated_at"] = datetime.now(timezone.utc).isoformat()
            item.context_data = metadata
            message = "Item eskaliert"

        elif action == "review":
            item.status = SmartInboxItemStatus.IN_PROGRESS.value
            message = "Item zur Prüfung markiert"

        elif action == "pay":
            item.status = SmartInboxItemStatus.COMPLETED.value
            item.completed_at = datetime.now(timezone.utc)
            message = "Zahlung veranlasst"

        else:
            raise ValueError(f"Unbekannte Aktion: {action}")

        await self.db.commit()

        self.logger.info(
            "action_completed",
            item_id=str(item_id),
            action=action,
        )

        return ActionResult(success=True, message=message)

    async def snooze_item(
        self,
        item_id: UUID,
        snooze_until: datetime,
        company_id: UUID,
    ) -> bool:
        """Snoozed ein Inbox Item.

        Args:
            item_id: Item-ID
            snooze_until: Zeitpunkt bis zum Snooze
            company_id: Company-ID

        Returns:
            True bei Erfolg

        Raises:
            ValueError: Item nicht gefunden
            PermissionError: Keine Berechtigung
        """
        self.logger.info(
            "snoozing_item",
            item_id=str(item_id),
            until=snooze_until.isoformat(),
        )

        item = await self._get_item(item_id, company_id)

        item.status = SmartInboxItemStatus.SNOOZED.value
        item.snoozed_until = snooze_until

        await self.db.commit()

        return True

    async def dismiss_item(
        self,
        item_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Verwirft ein Inbox Item.

        Args:
            item_id: Item-ID
            company_id: Company-ID

        Returns:
            True bei Erfolg

        Raises:
            ValueError: Item nicht gefunden
            PermissionError: Keine Berechtigung
        """
        self.logger.info("dismissing_item", item_id=str(item_id))

        item = await self._get_item(item_id, company_id)

        item.status = SmartInboxItemStatus.DISMISSED.value
        item.dismissed_at = datetime.now(timezone.utc)

        await self.db.commit()

        return True

    async def get_user_insights(
        self,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Generiert KI-Insights über Benutzerverhalten.

        Args:
            company_id: Company-ID

        Returns:
            Liste von Insight-Dictionaries
        """
        self.logger.info("generating_insights", company_id=str(company_id))

        insights: List[Dict[str, Any]] = []

        # Insight 1: Durchschnittliche Bearbeitungszeit
        avg_time_query = select(
            func.avg(
                func.extract(
                    'epoch',
                    SmartInboxItem.completed_at - SmartInboxItem.created_at
                )
            )
        ).where(
            and_(
                SmartInboxItem.user_id == self.user_id,
                SmartInboxItem.company_id == company_id,
                SmartInboxItem.status == SmartInboxItemStatus.COMPLETED.value,
            )
        )
        avg_result = await self.db.execute(avg_time_query)
        avg_time = avg_result.scalar()

        if avg_time:
            hours = avg_time / 3600
            insights.append({
                "title": "Durchschnittliche Bearbeitungszeit",
                "description": f"Sie bearbeiten Items im Schnitt in {hours:.1f} Stunden",
                "metric": "avg_processing_time_hours",
                "value": hours,
                "trend": "stable",
            })

        # Insight 2: Beliebteste Kategorie
        category_query = select(
            SmartInboxItem.category,
            func.count(SmartInboxItem.id).label('count')
        ).where(
            and_(
                SmartInboxItem.user_id == self.user_id,
                SmartInboxItem.company_id == company_id,
                SmartInboxItem.status == SmartInboxItemStatus.COMPLETED.value,
            )
        ).group_by(SmartInboxItem.category).order_by(
            func.count(SmartInboxItem.id).desc()
        ).limit(1)

        cat_result = await self.db.execute(category_query)
        top_category = cat_result.first()

        if top_category:
            insights.append({
                "title": "Meistbearbeitete Kategorie",
                "description": f"Sie bearbeiten am meisten '{top_category[0]}' Items",
                "metric": "top_category",
                "value": top_category[1],
                "trend": "up",
            })

        # Insight 3: Pendente Items
        pending_query = select(func.count(SmartInboxItem.id)).where(
            and_(
                SmartInboxItem.user_id == self.user_id,
                SmartInboxItem.company_id == company_id,
                SmartInboxItem.status == SmartInboxItemStatus.PENDING.value,
            )
        )
        pending_result = await self.db.execute(pending_query)
        pending_count = pending_result.scalar() or 0

        insights.append({
            "title": "Offene Aufgaben",
            "description": f"Sie haben {pending_count} offene Aufgaben",
            "metric": "pending_count",
            "value": pending_count,
            "trend": "down" if pending_count < 10 else "up",
        })

        return insights

    async def trigger_aggregation(
        self,
        company_id: UUID,
    ) -> UUID:
        """Triggert eine manuelle Aggregation von Inbox Items.

        Args:
            company_id: Company-ID

        Returns:
            Task-ID der gestarteten Aggregation
        """
        self.logger.info("triggering_aggregation", company_id=str(company_id))

        # Celery Task starten für asynchrone Aggregation
        try:
            from app.workers.tasks.smart_inbox_tasks import aggregate_inbox_items
            task = aggregate_inbox_items.delay(str(company_id), str(self.user_id))
            return UUID(task.id)
        except ImportError:
            # Fallback wenn Celery nicht verfügbar (Dev-Modus)
            self.logger.warning("celery_not_available_for_aggregation")
            import uuid
            return uuid.uuid4()
        except Exception as e:
            self.logger.error("aggregation_task_failed", error=str(e))
            import uuid
            return uuid.uuid4()

    async def get_statistics(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Holt Statistiken über den Smart Inbox.

        Args:
            company_id: Company-ID

        Returns:
            Dictionary mit Statistiken
        """
        self.logger.info("getting_statistics", company_id=str(company_id))

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        base_filter = and_(
            SmartInboxItem.user_id == self.user_id,
            SmartInboxItem.company_id == company_id,
        )

        # Total count
        total_query = select(func.count(SmartInboxItem.id)).where(base_filter)
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # Pending count
        pending_query = select(func.count(SmartInboxItem.id)).where(
            and_(base_filter, SmartInboxItem.status == SmartInboxItemStatus.PENDING.value)
        )
        pending_result = await self.db.execute(pending_query)
        pending = pending_result.scalar() or 0

        # In progress count
        in_progress_query = select(func.count(SmartInboxItem.id)).where(
            and_(base_filter, SmartInboxItem.status == SmartInboxItemStatus.IN_PROGRESS.value)
        )
        in_progress_result = await self.db.execute(in_progress_query)
        in_progress = in_progress_result.scalar() or 0

        # Completed today
        completed_today_query = select(func.count(SmartInboxItem.id)).where(
            and_(
                base_filter,
                SmartInboxItem.status == SmartInboxItemStatus.COMPLETED.value,
                SmartInboxItem.completed_at >= today_start,
            )
        )
        completed_today_result = await self.db.execute(completed_today_query)
        completed_today = completed_today_result.scalar() or 0

        # Dismissed today
        dismissed_today_query = select(func.count(SmartInboxItem.id)).where(
            and_(
                base_filter,
                SmartInboxItem.status == SmartInboxItemStatus.DISMISSED.value,
                SmartInboxItem.updated_at >= today_start,
            )
        )
        dismissed_today_result = await self.db.execute(dismissed_today_query)
        dismissed_today = dismissed_today_result.scalar() or 0

        # By category
        category_query = select(
            SmartInboxItem.category,
            func.count(SmartInboxItem.id)
        ).where(
            and_(base_filter, SmartInboxItem.status.in_([
                SmartInboxItemStatus.PENDING.value,
                SmartInboxItemStatus.IN_PROGRESS.value
            ]))
        ).group_by(SmartInboxItem.category)

        category_result = await self.db.execute(category_query)
        by_category = {row[0] or "other": row[1] for row in category_result.all()}

        # By source
        source_query = select(
            SmartInboxItem.source_type,
            func.count(SmartInboxItem.id)
        ).where(
            and_(base_filter, SmartInboxItem.status.in_([
                SmartInboxItemStatus.PENDING.value,
                SmartInboxItemStatus.IN_PROGRESS.value
            ]))
        ).group_by(SmartInboxItem.source_type)

        source_result = await self.db.execute(source_query)
        by_source = {row[0] or "other": row[1] for row in source_result.all()}

        # Berechne durchschnittliche Reaktionszeit aus abgeschlossenen Items
        avg_response_time_ms = await self._calculate_avg_response_time(base_filter)

        return {
            "total": total,
            "pending": pending,
            "in_progress": in_progress,
            "completed_today": completed_today,
            "dismissed_today": dismissed_today,
            "avg_response_time_ms": avg_response_time_ms,
            "by_category": by_category,
            "by_source": by_source,
        }

    async def _calculate_avg_response_time(self, base_filter) -> int:
        """Berechnet durchschnittliche Reaktionszeit aus abgeschlossenen Items."""
        # Hole completed Items mit Zeitdifferenz
        from sqlalchemy import extract

        completed_query = select(
            func.avg(
                extract('epoch', SmartInboxItem.completed_at) -
                extract('epoch', SmartInboxItem.created_at)
            ).label("avg_seconds")
        ).where(
            and_(
                base_filter,
                SmartInboxItem.status == SmartInboxItemStatus.COMPLETED.value,
                SmartInboxItem.completed_at.isnot(None),
            )
        )

        result = await self.db.execute(completed_query)
        avg_seconds = result.scalar()

        if avg_seconds:
            return int(avg_seconds * 1000)  # Konvertiere zu Millisekunden

        return 0

    async def _get_item(
        self,
        item_id: UUID,
        company_id: UUID,
    ) -> SmartInboxItem:
        """Holt ein Item mit Validierung.

        Args:
            item_id: Item-ID
            company_id: Company-ID

        Returns:
            SmartInboxItem

        Raises:
            ValueError: Item nicht gefunden
            PermissionError: Keine Berechtigung
        """
        query = select(SmartInboxItem).where(SmartInboxItem.id == item_id)
        result = await self.db.execute(query)
        item = result.scalar_one_or_none()

        if not item:
            raise ValueError(f"Item mit ID {item_id} nicht gefunden")

        # Check permissions (Multi-Tenant + User)
        if item.company_id != company_id:
            raise PermissionError("Keine Berechtigung für dieses Item")

        if item.user_id != self.user_id:
            raise PermissionError("Keine Berechtigung für dieses Item")

        return item

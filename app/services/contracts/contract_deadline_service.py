# -*- coding: utf-8 -*-
"""
Contract Deadline Service.

Verwaltet Vertragsfristen und wichtige Termine:
- Kuendigungsfristen
- Vertragsablauf
- Verlaengerungsentscheidungen
- Preisanpassungen
- Gewaehrleistungsende
- Automatische Erinnerungen

Feinpoliert und durchdacht.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_contract import (
    Contract,
    ContractDeadline,
    ContractStatus,
)

logger = logging.getLogger(__name__)


class ContractDeadlineService:
    """
    Service fuer das Management von Vertragsfristen.

    Verwaltet alle wichtigen Termine und Fristen aus Vertraegen
    mit automatischen Erinnerungen und Eskalation.
    """

    # Standard-Erinnerungsintervalle (Tage vor Frist)
    DEFAULT_REMINDERS = [90, 30, 14, 7, 1]

    # Prioritaet basierend auf Deadline-Typ
    TYPE_PRIORITIES = {
        "termination_notice": "critical",
        "contract_expiry": "high",
        "renewal_decision": "high",
        "price_adjustment": "medium",
        "warranty_expiry": "medium",
        "audit_due": "medium",
        "payment_due": "high",
        "report_due": "medium",
        "review_due": "low",
    }

    def __init__(self, db: AsyncSession):
        """Initialisiere Service mit Datenbank-Session."""
        self.db = db

    async def create_deadline(
        self,
        contract_id: UUID,
        company_id: UUID,
        deadline_type: str,
        title: str,
        deadline_date: date,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        reminder_days_before: Optional[List[int]] = None,
        assignee_id: Optional[UUID] = None,
    ) -> ContractDeadline:
        """
        Erstelle eine neue Vertragsfrist.

        Args:
            contract_id: ID des zugehoerigen Vertrags
            company_id: ID der Firma
            deadline_type: Art der Frist
            title: Titel der Frist
            deadline_date: Faelligkeitsdatum
            description: Detaillierte Beschreibung
            priority: Prioritaet (low, medium, high, critical)
            reminder_days_before: Erinnerungstage
            assignee_id: Zustaendiger Benutzer

        Returns:
            Erstellte ContractDeadline
        """
        # Validiere Contract existiert
        contract = await self.db.get(Contract, contract_id)
        if not contract:
            raise ValueError(f"Vertrag {contract_id} nicht gefunden")

        # Bestimme Prioritaet
        if not priority:
            priority = self.TYPE_PRIORITIES.get(deadline_type, "medium")

        # Bestimme Erinnerungen
        if reminder_days_before is None:
            reminder_days_before = self._get_reminders_for_priority(priority)

        deadline = ContractDeadline(
            contract_id=contract_id,
            deadline_type=deadline_type,
            title=title,
            description=description,
            deadline_date=deadline_date,
            priority=priority,
            is_completed=False,
            reminder_days_before=reminder_days_before,
            assignee_id=assignee_id,
            company_id=company_id,
        )

        self.db.add(deadline)
        await self.db.commit()
        await self.db.refresh(deadline)

        logger.info(f"Deadline erstellt: {deadline.id}, Typ: {deadline_type}")
        return deadline

    async def get_deadline(self, deadline_id: UUID) -> Optional[ContractDeadline]:
        """Hole Deadline by ID."""
        return await self.db.get(ContractDeadline, deadline_id)

    async def get_deadlines_for_contract(
        self,
        contract_id: UUID,
        include_completed: bool = False,
    ) -> List[ContractDeadline]:
        """
        Hole alle Deadlines fuer einen Vertrag.

        Args:
            contract_id: ID des Vertrags
            include_completed: Ob erledigte Deadlines einbezogen werden

        Returns:
            Liste von ContractDeadlines
        """
        query = select(ContractDeadline).where(
            ContractDeadline.contract_id == contract_id
        )

        if not include_completed:
            query = query.where(ContractDeadline.is_completed == False)

        query = query.order_by(ContractDeadline.deadline_date.asc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_upcoming_deadlines(
        self,
        company_id: UUID,
        days_ahead: int = 90,
        priority: Optional[str] = None,
        assignee_id: Optional[UUID] = None,
    ) -> List[ContractDeadline]:
        """
        Hole bevorstehende Deadlines.

        Args:
            company_id: ID der Firma
            days_ahead: Tage in die Zukunft
            priority: Optional Filter auf Prioritaet
            assignee_id: Optional Filter auf Benutzer

        Returns:
            Liste von bevorstehenden ContractDeadlines
        """
        today = date.today()
        cutoff_date = today + timedelta(days=days_ahead)

        query = select(ContractDeadline).where(
            and_(
                ContractDeadline.company_id == company_id,
                ContractDeadline.is_completed == False,
                ContractDeadline.deadline_date >= today,
                ContractDeadline.deadline_date <= cutoff_date,
            )
        )

        if priority:
            query = query.where(ContractDeadline.priority == priority)

        if assignee_id:
            query = query.where(ContractDeadline.assignee_id == assignee_id)

        # Sortiere nach Prioritaet und Datum
        priority_order = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
        }
        query = query.order_by(
            ContractDeadline.deadline_date.asc()
        )

        result = await self.db.execute(query)
        deadlines = list(result.scalars().all())

        # Python-seitige Sortierung nach Prioritaet
        deadlines.sort(key=lambda d: (priority_order.get(d.priority, 4), d.deadline_date))

        return deadlines

    async def get_expiring_contracts(
        self,
        company_id: UUID,
        days_ahead: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        Hole ablaufende Vertraege.

        Args:
            company_id: ID der Firma
            days_ahead: Tage in die Zukunft

        Returns:
            Liste von Vertraegen mit Ablauf-Infos
        """
        today = date.today()
        cutoff_date = today + timedelta(days=days_ahead)

        query = select(Contract).where(
            and_(
                Contract.company_id == company_id,
                Contract.status == ContractStatus.ACTIVE.value,
                Contract.expiration_date.isnot(None),
                Contract.expiration_date >= today,
                Contract.expiration_date <= cutoff_date,
            )
        )

        query = query.order_by(Contract.expiration_date.asc())

        result = await self.db.execute(query)
        contracts = list(result.scalars().all())

        expiring = []
        for contract in contracts:
            days_remaining = (contract.expiration_date - today).days
            expiring.append({
                "contract_id": str(contract.id),
                "title": contract.title,
                "contract_type": contract.contract_type,
                "expiration_date": contract.expiration_date.isoformat(),
                "days_remaining": days_remaining,
                "auto_renewal": contract.auto_renewal,
                "notice_period_days": contract.notice_period_days,
                "total_value": float(contract.total_value) if contract.total_value else None,
            })

        return expiring

    async def mark_as_completed(
        self,
        deadline_id: UUID,
        completed_by_id: UUID,
        action_taken: Optional[str] = None,
    ) -> ContractDeadline:
        """
        Markiere Deadline als erledigt.

        Args:
            deadline_id: ID der Deadline
            completed_by_id: ID des Benutzers
            action_taken: Beschreibung der durchgefuehrten Aktion

        Returns:
            Aktualisierte ContractDeadline
        """
        deadline = await self.db.get(ContractDeadline, deadline_id)
        if not deadline:
            raise ValueError(f"Deadline {deadline_id} nicht gefunden")

        deadline.is_completed = True
        deadline.completed_at = datetime.now()
        deadline.completed_by_id = completed_by_id
        deadline.action_taken = action_taken

        await self.db.commit()
        await self.db.refresh(deadline)

        logger.info(f"Deadline erledigt: {deadline_id}")
        return deadline

    async def update_deadline(
        self,
        deadline_id: UUID,
        **updates,
    ) -> ContractDeadline:
        """
        Aktualisiere Deadline.

        Args:
            deadline_id: ID der Deadline
            **updates: Felder zum Aktualisieren

        Returns:
            Aktualisierte ContractDeadline
        """
        deadline = await self.db.get(ContractDeadline, deadline_id)
        if not deadline:
            raise ValueError(f"Deadline {deadline_id} nicht gefunden")

        allowed_fields = {
            "title", "description", "deadline_date", "priority",
            "reminder_days_before", "assignee_id",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(deadline, field, value)

        await self.db.commit()
        await self.db.refresh(deadline)

        logger.info(f"Deadline aktualisiert: {deadline_id}")
        return deadline

    async def delete_deadline(self, deadline_id: UUID) -> bool:
        """
        Loesche Deadline.

        Args:
            deadline_id: ID der Deadline

        Returns:
            True wenn erfolgreich
        """
        deadline = await self.db.get(ContractDeadline, deadline_id)
        if not deadline:
            return False

        await self.db.delete(deadline)
        await self.db.commit()

        logger.info(f"Deadline geloescht: {deadline_id}")
        return True

    async def get_deadlines_needing_reminder(
        self,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Hole Deadlines die eine Erinnerung benoetigen.

        Prueft fuer jede Deadline ob heute ein Erinnerungstag ist.

        Args:
            company_id: ID der Firma

        Returns:
            Liste von Deadlines mit Reminder-Info
        """
        today = date.today()

        # Hole alle unerledigten Deadlines in den naechsten 90 Tagen
        cutoff_date = today + timedelta(days=90)

        query = select(ContractDeadline).where(
            and_(
                ContractDeadline.company_id == company_id,
                ContractDeadline.is_completed == False,
                ContractDeadline.deadline_date >= today,
                ContractDeadline.deadline_date <= cutoff_date,
            )
        )

        result = await self.db.execute(query)
        deadlines = list(result.scalars().all())

        needs_reminder = []
        for deadline in deadlines:
            days_until = (deadline.deadline_date - today).days
            reminder_days = deadline.reminder_days_before or self.DEFAULT_REMINDERS

            if days_until in reminder_days:
                # Pruefe ob Erinnerung heute schon gesendet wurde
                if deadline.last_reminder_sent:
                    if deadline.last_reminder_sent.date() == today:
                        continue

                needs_reminder.append({
                    "deadline": deadline,
                    "days_until": days_until,
                    "reminder_type": self._get_reminder_type(days_until),
                })

        return needs_reminder

    async def mark_reminder_sent(
        self,
        deadline_id: UUID,
    ) -> ContractDeadline:
        """
        Markiere Erinnerung als gesendet.

        Args:
            deadline_id: ID der Deadline

        Returns:
            Aktualisierte ContractDeadline
        """
        deadline = await self.db.get(ContractDeadline, deadline_id)
        if not deadline:
            raise ValueError(f"Deadline {deadline_id} nicht gefunden")

        deadline.last_reminder_sent = datetime.now()

        await self.db.commit()
        await self.db.refresh(deadline)

        return deadline

    async def create_deadlines_from_contract(
        self,
        contract: Contract,
    ) -> List[ContractDeadline]:
        """
        Erstelle automatisch Deadlines fuer einen Vertrag.

        Analysiert den Vertrag und erstellt relevante Fristen:
        - Vertragsablauf
        - Kuendigungsfrist
        - Verlaengerungsentscheidung (bei auto_renewal)
        - Gewaehrleistung (wenn in clauses)

        Args:
            contract: Der Vertrag

        Returns:
            Liste erstellter Deadlines
        """
        deadlines = []
        today = date.today()

        # 1. Vertragsablauf
        if contract.expiration_date and contract.expiration_date > today:
            deadline = await self.create_deadline(
                contract_id=contract.id,
                company_id=contract.company_id,
                deadline_type="contract_expiry",
                title=f"Vertragsablauf: {contract.title}",
                deadline_date=contract.expiration_date,
                description=f"Der Vertrag '{contract.title}' laeuft ab.",
                priority="high",
            )
            deadlines.append(deadline)

        # 2. Kuendigungsfrist
        if contract.expiration_date and contract.notice_period_days:
            notice_date = contract.expiration_date - timedelta(days=contract.notice_period_days)
            if notice_date > today:
                deadline = await self.create_deadline(
                    contract_id=contract.id,
                    company_id=contract.company_id,
                    deadline_type="termination_notice",
                    title=f"Kuendigungsfrist: {contract.title}",
                    deadline_date=notice_date,
                    description=f"Letzte Moeglichkeit zur Kuendigung. "
                                f"Kuendigungsfrist: {contract.notice_period_days} Tage.",
                    priority="critical",
                    reminder_days_before=[60, 30, 14, 7, 3, 1],
                )
                deadlines.append(deadline)

        # 3. Verlaengerungsentscheidung bei auto_renewal
        if contract.auto_renewal and contract.expiration_date and contract.renewal_notice_days:
            renewal_decision_date = contract.expiration_date - timedelta(days=contract.renewal_notice_days)
            if renewal_decision_date > today:
                deadline = await self.create_deadline(
                    contract_id=contract.id,
                    company_id=contract.company_id,
                    deadline_type="renewal_decision",
                    title=f"Verlaengerungsentscheidung: {contract.title}",
                    deadline_date=renewal_decision_date,
                    description="Entscheidung ueber automatische Verlaengerung erforderlich.",
                    priority="high",
                )
                deadlines.append(deadline)

        # 4. Gewaehrleistung aus Klauseln
        clauses = contract.clauses or {}
        warranty = clauses.get("warranty", {})
        if warranty.get("period_months") and contract.effective_date:
            warranty_end = contract.effective_date + timedelta(days=warranty["period_months"] * 30)
            if warranty_end > today:
                deadline = await self.create_deadline(
                    contract_id=contract.id,
                    company_id=contract.company_id,
                    deadline_type="warranty_expiry",
                    title=f"Gewaehrleistungsende: {contract.title}",
                    deadline_date=warranty_end,
                    description=f"Gewaehrleistung endet nach {warranty['period_months']} Monaten.",
                    priority="medium",
                )
                deadlines.append(deadline)

        # 5. Preisanpassung
        price_adjustment = clauses.get("price_adjustment", {})
        if price_adjustment.get("interval") == "annual" and contract.effective_date:
            # Naechste jaehrliche Anpassung
            next_adjustment = contract.effective_date.replace(year=today.year + 1)
            if next_adjustment <= today:
                next_adjustment = next_adjustment.replace(year=today.year + 1)

            deadline = await self.create_deadline(
                contract_id=contract.id,
                company_id=contract.company_id,
                deadline_type="price_adjustment",
                title=f"Preisanpassung: {contract.title}",
                deadline_date=next_adjustment,
                description="Jaehrliche Preisanpassung steht an.",
                priority="medium",
            )
            deadlines.append(deadline)

        logger.info(f"{len(deadlines)} Deadlines fuer Vertrag {contract.id} erstellt")
        return deadlines

    async def get_statistics(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Berechne Deadline-Statistiken.

        Args:
            company_id: ID der Firma

        Returns:
            Dictionary mit Statistiken
        """
        today = date.today()

        # Gesamtzahl
        total_query = select(func.count(ContractDeadline.id)).where(
            and_(
                ContractDeadline.company_id == company_id,
                ContractDeadline.is_completed == False,
            )
        )
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # Nach Prioritaet
        priority_counts = {}
        for priority in ["critical", "high", "medium", "low"]:
            query = select(func.count(ContractDeadline.id)).where(
                and_(
                    ContractDeadline.company_id == company_id,
                    ContractDeadline.is_completed == False,
                    ContractDeadline.priority == priority,
                )
            )
            result = await self.db.execute(query)
            priority_counts[priority] = result.scalar() or 0

        # Ueberfaellig
        overdue_query = select(func.count(ContractDeadline.id)).where(
            and_(
                ContractDeadline.company_id == company_id,
                ContractDeadline.is_completed == False,
                ContractDeadline.deadline_date < today,
            )
        )
        overdue_result = await self.db.execute(overdue_query)
        overdue = overdue_result.scalar() or 0

        # Diese Woche
        week_end = today + timedelta(days=7)
        this_week_query = select(func.count(ContractDeadline.id)).where(
            and_(
                ContractDeadline.company_id == company_id,
                ContractDeadline.is_completed == False,
                ContractDeadline.deadline_date >= today,
                ContractDeadline.deadline_date <= week_end,
            )
        )
        this_week_result = await self.db.execute(this_week_query)
        this_week = this_week_result.scalar() or 0

        # Diesen Monat
        month_end = today + timedelta(days=30)
        this_month_query = select(func.count(ContractDeadline.id)).where(
            and_(
                ContractDeadline.company_id == company_id,
                ContractDeadline.is_completed == False,
                ContractDeadline.deadline_date >= today,
                ContractDeadline.deadline_date <= month_end,
            )
        )
        this_month_result = await self.db.execute(this_month_query)
        this_month = this_month_result.scalar() or 0

        return {
            "total_pending": total,
            "by_priority": priority_counts,
            "overdue": overdue,
            "this_week": this_week,
            "this_month": this_month,
            "critical_count": priority_counts.get("critical", 0),
        }

    def _get_reminders_for_priority(self, priority: str) -> List[int]:
        """Bestimme Erinnerungstage basierend auf Prioritaet."""
        if priority == "critical":
            return [90, 60, 30, 14, 7, 3, 1]
        elif priority == "high":
            return [60, 30, 14, 7, 1]
        elif priority == "medium":
            return [30, 14, 7, 1]
        else:
            return [14, 7, 1]

    def _get_reminder_type(self, days_until: int) -> str:
        """Bestimme Erinnerungstyp basierend auf Tagen."""
        if days_until <= 1:
            return "urgent"
        elif days_until <= 7:
            return "warning"
        elif days_until <= 30:
            return "reminder"
        else:
            return "notice"

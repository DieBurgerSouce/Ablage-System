# -*- coding: utf-8 -*-
"""
Contract Obligation Tracker Service.

Verwaltet Vertragspflichten und -verpflichtungen:
- Erstellen und Aktualisieren von Obligations
- Status-Tracking (pending, fulfilled, overdue)
- Wiederkehrende Obligations
- Automatische Erinnerungen
- Zustaendigkeits-Management

Feinpoliert und durchdacht.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models_contract import (
    Contract,
    ContractObligation,
    ObligationType,
    ObligationStatus,
    RecurrencePattern,
)

logger = logging.getLogger(__name__)


class ContractObligationTracker:
    """
    Service fuer das Tracking von Vertragspflichten.

    Verwaltet den Lebenszyklus von Obligations von der
    Erstellung bis zur Erfuellung oder Eskalation.
    """

    # Umrechnung Recurrence zu Tagen
    RECURRENCE_DAYS = {
        RecurrencePattern.DAILY: 1,
        RecurrencePattern.WEEKLY: 7,
        RecurrencePattern.BIWEEKLY: 14,
        RecurrencePattern.MONTHLY: 30,
        RecurrencePattern.QUARTERLY: 91,
        RecurrencePattern.SEMIANNUAL: 182,
        RecurrencePattern.ANNUAL: 365,
    }

    def __init__(self, db: AsyncSession):
        """Initialisiere Service mit Datenbank-Session."""
        self.db = db

    async def create_obligation(
        self,
        contract_id: UUID,
        company_id: UUID,
        obligation_type: ObligationType,
        title: str,
        description: Optional[str] = None,
        responsible_party: Optional[str] = None,
        assignee_id: Optional[UUID] = None,
        due_date: Optional[date] = None,
        recurring: bool = False,
        recurrence_pattern: Optional[RecurrencePattern] = None,
        recurrence_end_date: Optional[date] = None,
        reminder_days: int = 7,
        amount: Optional[float] = None,
        currency: str = "EUR",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContractObligation:
        """
        Erstelle eine neue Vertragspflicht.

        Args:
            contract_id: ID des zugehoerigen Vertrags
            company_id: ID der Firma
            obligation_type: Art der Pflicht
            title: Titel der Pflicht
            description: Detaillierte Beschreibung
            responsible_party: Zustaendige Partei (us, them, both)
            assignee_id: ID des zugewiesenen Benutzers
            due_date: Faelligkeitsdatum
            recurring: Ob die Pflicht wiederkehrend ist
            recurrence_pattern: Wiederholungsmuster
            recurrence_end_date: Ende der Wiederholung
            reminder_days: Tage vor Faelligkeit fuer Erinnerung
            amount: Optionaler Betrag
            currency: Waehrung
            metadata: Zusaetzliche Metadaten

        Returns:
            Erstellte ContractObligation
        """
        # Validiere Contract existiert
        contract = await self.db.get(Contract, contract_id)
        if not contract:
            raise ValueError(f"Vertrag {contract_id} nicht gefunden")

        obligation = ContractObligation(
            contract_id=contract_id,
            obligation_type=obligation_type.value if isinstance(obligation_type, ObligationType) else obligation_type,
            title=title,
            description=description,
            responsible_party=responsible_party,
            assignee_id=assignee_id,
            due_date=due_date,
            recurring=recurring,
            recurrence_pattern=recurrence_pattern.value if recurrence_pattern else None,
            recurrence_end_date=recurrence_end_date,
            next_occurrence_date=due_date if recurring else None,
            status=ObligationStatus.PENDING.value,
            reminder_days=reminder_days,
            amount=amount,
            currency=currency,
            metadata=metadata or {},
            company_id=company_id,
        )

        self.db.add(obligation)
        await self.db.commit()
        await self.db.refresh(obligation)

        logger.info(f"Obligation erstellt: {obligation.id}, Vertrag: {contract_id}")
        return obligation

    async def get_obligation(self, obligation_id: UUID) -> Optional[ContractObligation]:
        """Hole Obligation by ID."""
        return await self.db.get(ContractObligation, obligation_id)

    async def get_obligations_for_contract(
        self,
        contract_id: UUID,
        status: Optional[ObligationStatus] = None,
        include_completed: bool = True,
    ) -> List[ContractObligation]:
        """
        Hole alle Obligations fuer einen Vertrag.

        Args:
            contract_id: ID des Vertrags
            status: Optional Status-Filter
            include_completed: Ob erfuellte Obligations einbezogen werden

        Returns:
            Liste von ContractObligations
        """
        query = select(ContractObligation).where(
            ContractObligation.contract_id == contract_id
        )

        if status:
            query = query.where(ContractObligation.status == status.value)
        elif not include_completed:
            query = query.where(
                ContractObligation.status != ObligationStatus.FULFILLED.value
            )

        query = query.order_by(ContractObligation.due_date.asc().nullslast())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_upcoming_obligations(
        self,
        company_id: UUID,
        days_ahead: int = 30,
        assignee_id: Optional[UUID] = None,
    ) -> List[ContractObligation]:
        """
        Hole bevorstehende Obligations.

        Args:
            company_id: ID der Firma
            days_ahead: Tage in die Zukunft
            assignee_id: Optional Filter auf Benutzer

        Returns:
            Liste von bevorstehenden ContractObligations
        """
        cutoff_date = date.today() + timedelta(days=days_ahead)

        query = select(ContractObligation).where(
            and_(
                ContractObligation.company_id == company_id,
                ContractObligation.status.in_([
                    ObligationStatus.PENDING.value,
                    ObligationStatus.IN_PROGRESS.value,
                ]),
                or_(
                    and_(
                        ContractObligation.due_date.isnot(None),
                        ContractObligation.due_date <= cutoff_date,
                    ),
                    and_(
                        ContractObligation.next_occurrence_date.isnot(None),
                        ContractObligation.next_occurrence_date <= cutoff_date,
                    ),
                ),
            )
        )

        if assignee_id:
            query = query.where(ContractObligation.assignee_id == assignee_id)

        query = query.order_by(
            func.coalesce(
                ContractObligation.due_date,
                ContractObligation.next_occurrence_date
            ).asc()
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_overdue_obligations(
        self,
        company_id: UUID,
    ) -> List[ContractObligation]:
        """
        Hole ueberfaellige Obligations.

        Args:
            company_id: ID der Firma

        Returns:
            Liste von ueberfaelligen ContractObligations
        """
        today = date.today()

        query = select(ContractObligation).where(
            and_(
                ContractObligation.company_id == company_id,
                ContractObligation.status.in_([
                    ObligationStatus.PENDING.value,
                    ObligationStatus.IN_PROGRESS.value,
                    ObligationStatus.OVERDUE.value,
                ]),
                or_(
                    and_(
                        ContractObligation.due_date.isnot(None),
                        ContractObligation.due_date < today,
                    ),
                    and_(
                        ContractObligation.next_occurrence_date.isnot(None),
                        ContractObligation.next_occurrence_date < today,
                    ),
                ),
            )
        )

        query = query.order_by(ContractObligation.due_date.asc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_as_fulfilled(
        self,
        obligation_id: UUID,
        completed_by_id: UUID,
        notes: Optional[str] = None,
    ) -> ContractObligation:
        """
        Markiere Obligation als erfuellt.

        Bei wiederkehrenden Obligations wird die naechste
        Occurrence erstellt.

        Args:
            obligation_id: ID der Obligation
            completed_by_id: ID des Benutzers der abschliesst
            notes: Optionale Notizen

        Returns:
            Aktualisierte ContractObligation
        """
        obligation = await self.db.get(ContractObligation, obligation_id)
        if not obligation:
            raise ValueError(f"Obligation {obligation_id} nicht gefunden")

        obligation.status = ObligationStatus.FULFILLED.value
        obligation.completed_at = datetime.now()
        obligation.completed_by_id = completed_by_id

        if notes:
            current_metadata = obligation.obligation_metadata or {}
            current_metadata["completion_notes"] = notes
            obligation.obligation_metadata = current_metadata

        # Bei wiederkehrenden: Naechste Occurrence berechnen
        if obligation.recurring and obligation.recurrence_pattern:
            next_date = self._calculate_next_occurrence(
                current_date=obligation.next_occurrence_date or obligation.due_date,
                pattern=obligation.recurrence_pattern,
                end_date=obligation.recurrence_end_date,
            )

            if next_date:
                # Erstelle neue Occurrence
                new_obligation = ContractObligation(
                    contract_id=obligation.contract_id,
                    obligation_type=obligation.obligation_type,
                    title=obligation.title,
                    description=obligation.description,
                    responsible_party=obligation.responsible_party,
                    assignee_id=obligation.assignee_id,
                    due_date=next_date,
                    recurring=True,
                    recurrence_pattern=obligation.recurrence_pattern,
                    recurrence_end_date=obligation.recurrence_end_date,
                    next_occurrence_date=next_date,
                    status=ObligationStatus.PENDING.value,
                    reminder_days=obligation.reminder_days,
                    amount=obligation.amount,
                    currency=obligation.currency,
                    metadata={"parent_obligation_id": str(obligation.id)},
                    company_id=obligation.company_id,
                )
                self.db.add(new_obligation)
                logger.info(f"Naechste Occurrence erstellt fuer: {next_date}")

        await self.db.commit()
        await self.db.refresh(obligation)

        logger.info(f"Obligation erfuellt: {obligation_id}")
        return obligation

    async def mark_as_overdue(self, obligation_id: UUID) -> ContractObligation:
        """
        Markiere Obligation als ueberfaellig.

        Args:
            obligation_id: ID der Obligation

        Returns:
            Aktualisierte ContractObligation
        """
        obligation = await self.db.get(ContractObligation, obligation_id)
        if not obligation:
            raise ValueError(f"Obligation {obligation_id} nicht gefunden")

        obligation.status = ObligationStatus.OVERDUE.value

        await self.db.commit()
        await self.db.refresh(obligation)

        logger.info(f"Obligation als ueberfaellig markiert: {obligation_id}")
        return obligation

    async def assign_to_user(
        self,
        obligation_id: UUID,
        assignee_id: UUID,
    ) -> ContractObligation:
        """
        Weise Obligation einem Benutzer zu.

        Args:
            obligation_id: ID der Obligation
            assignee_id: ID des Benutzers

        Returns:
            Aktualisierte ContractObligation
        """
        obligation = await self.db.get(ContractObligation, obligation_id)
        if not obligation:
            raise ValueError(f"Obligation {obligation_id} nicht gefunden")

        obligation.assignee_id = assignee_id

        await self.db.commit()
        await self.db.refresh(obligation)

        logger.info(f"Obligation {obligation_id} zugewiesen an: {assignee_id}")
        return obligation

    async def update_obligation(
        self,
        obligation_id: UUID,
        **updates,
    ) -> ContractObligation:
        """
        Aktualisiere Obligation.

        Args:
            obligation_id: ID der Obligation
            **updates: Felder zum Aktualisieren

        Returns:
            Aktualisierte ContractObligation
        """
        obligation = await self.db.get(ContractObligation, obligation_id)
        if not obligation:
            raise ValueError(f"Obligation {obligation_id} nicht gefunden")

        allowed_fields = {
            "title", "description", "responsible_party", "assignee_id",
            "due_date", "recurring", "recurrence_pattern", "recurrence_end_date",
            "reminder_days", "amount", "currency", "metadata", "status",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(obligation, field, value)

        await self.db.commit()
        await self.db.refresh(obligation)

        logger.info(f"Obligation aktualisiert: {obligation_id}")
        return obligation

    async def delete_obligation(self, obligation_id: UUID) -> bool:
        """
        Loesche Obligation.

        Args:
            obligation_id: ID der Obligation

        Returns:
            True wenn erfolgreich
        """
        obligation = await self.db.get(ContractObligation, obligation_id)
        if not obligation:
            return False

        await self.db.delete(obligation)
        await self.db.commit()

        logger.info(f"Obligation geloescht: {obligation_id}")
        return True

    async def get_obligations_needing_reminder(
        self,
        company_id: UUID,
    ) -> List[ContractObligation]:
        """
        Hole Obligations die eine Erinnerung benoetigen.

        Args:
            company_id: ID der Firma

        Returns:
            Liste von Obligations fuer Erinnerung
        """
        today = date.today()

        # Alle pending Obligations mit due_date
        query = select(ContractObligation).where(
            and_(
                ContractObligation.company_id == company_id,
                ContractObligation.status.in_([
                    ObligationStatus.PENDING.value,
                    ObligationStatus.IN_PROGRESS.value,
                ]),
                ContractObligation.reminder_sent == False,
                ContractObligation.due_date.isnot(None),
            )
        )

        result = await self.db.execute(query)
        obligations = list(result.scalars().all())

        # Filter nach reminder_days
        needs_reminder = []
        for obl in obligations:
            days_until = (obl.due_date - today).days
            if 0 <= days_until <= obl.reminder_days:
                needs_reminder.append(obl)

        return needs_reminder

    async def mark_reminder_sent(
        self,
        obligation_id: UUID,
    ) -> ContractObligation:
        """
        Markiere Erinnerung als gesendet.

        Args:
            obligation_id: ID der Obligation

        Returns:
            Aktualisierte ContractObligation
        """
        obligation = await self.db.get(ContractObligation, obligation_id)
        if not obligation:
            raise ValueError(f"Obligation {obligation_id} nicht gefunden")

        obligation.reminder_sent = True
        obligation.reminder_sent_at = datetime.now()

        await self.db.commit()
        await self.db.refresh(obligation)

        return obligation

    async def check_and_mark_overdue(
        self,
        company_id: UUID,
    ) -> List[ContractObligation]:
        """
        Pruefe und markiere ueberfaellige Obligations.

        Sollte taeglich als Celery-Task laufen.

        Args:
            company_id: ID der Firma

        Returns:
            Liste der als ueberfaellig markierten Obligations
        """
        today = date.today()

        query = select(ContractObligation).where(
            and_(
                ContractObligation.company_id == company_id,
                ContractObligation.status.in_([
                    ObligationStatus.PENDING.value,
                    ObligationStatus.IN_PROGRESS.value,
                ]),
                ContractObligation.due_date < today,
            )
        )

        result = await self.db.execute(query)
        obligations = list(result.scalars().all())

        marked = []
        for obl in obligations:
            obl.status = ObligationStatus.OVERDUE.value
            marked.append(obl)

        if marked:
            await self.db.commit()
            logger.info(f"{len(marked)} Obligations als ueberfaellig markiert")

        return marked

    async def get_statistics(
        self,
        company_id: UUID,
        contract_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Berechne Statistiken zu Obligations.

        Args:
            company_id: ID der Firma
            contract_id: Optional Filter auf Vertrag

        Returns:
            Dictionary mit Statistiken
        """
        base_filter = [ContractObligation.company_id == company_id]
        if contract_id:
            base_filter.append(ContractObligation.contract_id == contract_id)

        # Zaehle nach Status
        status_counts = {}
        for status in ObligationStatus:
            query = select(func.count(ContractObligation.id)).where(
                and_(
                    *base_filter,
                    ContractObligation.status == status.value,
                )
            )
            result = await self.db.execute(query)
            status_counts[status.value] = result.scalar() or 0

        # Zaehle nach Typ
        type_counts = {}
        for obl_type in ObligationType:
            query = select(func.count(ContractObligation.id)).where(
                and_(
                    *base_filter,
                    ContractObligation.obligation_type == obl_type.value,
                )
            )
            result = await self.db.execute(query)
            type_counts[obl_type.value] = result.scalar() or 0

        # Summe Betraege
        query = select(func.sum(ContractObligation.amount)).where(
            and_(
                *base_filter,
                ContractObligation.status.in_([
                    ObligationStatus.PENDING.value,
                    ObligationStatus.IN_PROGRESS.value,
                ]),
            )
        )
        result = await self.db.execute(query)
        pending_amount = result.scalar() or 0

        return {
            "by_status": status_counts,
            "by_type": type_counts,
            "total": sum(status_counts.values()),
            "pending_count": status_counts.get(ObligationStatus.PENDING.value, 0),
            "overdue_count": status_counts.get(ObligationStatus.OVERDUE.value, 0),
            "fulfilled_count": status_counts.get(ObligationStatus.FULFILLED.value, 0),
            "pending_amount": float(pending_amount),
        }

    def _calculate_next_occurrence(
        self,
        current_date: Optional[date],
        pattern: str,
        end_date: Optional[date],
    ) -> Optional[date]:
        """
        Berechne naechstes Vorkommen einer wiederkehrenden Obligation.

        Args:
            current_date: Aktuelles Datum
            pattern: Wiederholungsmuster
            end_date: Ende der Wiederholung

        Returns:
            Naechstes Datum oder None wenn beendet
        """
        if not current_date:
            return None

        try:
            pattern_enum = RecurrencePattern(pattern)
        except ValueError:
            return None

        days = self.RECURRENCE_DAYS.get(pattern_enum, 0)
        if days == 0:
            return None

        next_date = current_date + timedelta(days=days)

        # Pruefe Enddatum
        if end_date and next_date > end_date:
            return None

        return next_date

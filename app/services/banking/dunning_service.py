# -*- coding: utf-8 -*-
"""Dunning (Mahnwesen) Service.

Verwaltet das automatische Mahnwesen:
- Ueberfaellige Rechnungen erkennen
- Mahnstufen verwalten
- Mahngebuehren und Verzugszinsen berechnen
- Mahnschreiben generieren

Mahnstufen:
0 - Nicht begonnen
1 - 1. Mahnung (Zahlungserinnerung)
2 - 2. Mahnung (+ Mahngebuehr)
3 - Letzte Mahnung (+ Verzugszinsen, Inkasso-Androhung)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID, uuid4
import structlog

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.banking.models import (
    DunningLevel,
    DunningStatus,
    DunningRecordResponse,
)

from app.db.models import DunningRecord, Document

logger = structlog.get_logger(__name__)


class DunningAction(str, Enum):
    """Mahnaktionen."""
    REMINDER = "reminder"           # Zahlungserinnerung
    FIRST_DUNNING = "first"         # 1. Mahnung
    SECOND_DUNNING = "second"       # 2. Mahnung
    FINAL_DUNNING = "final"         # Letzte Mahnung
    COLLECTION = "collection"       # Inkasso
    WRITE_OFF = "write_off"         # Abschreibung


@dataclass
class DunningConfig:
    """Mahnkonfiguration."""
    # Fristen nach Faelligkeit (Tage)
    reminder_after_days: int = 7      # Zahlungserinnerung
    first_dunning_after_days: int = 14  # 1. Mahnung
    second_dunning_after_days: int = 28  # 2. Mahnung
    final_dunning_after_days: int = 42  # Letzte Mahnung

    # Gebuehren
    first_dunning_fee: Decimal = Decimal("5.00")
    second_dunning_fee: Decimal = Decimal("10.00")
    final_dunning_fee: Decimal = Decimal("15.00")

    # Verzugszinsen (p.a.)
    late_interest_rate: Decimal = Decimal("5.00")  # 5% ueber Basiszins
    base_interest_rate: Decimal = Decimal("3.62")  # Aktueller Basiszins

    # Mindestbetrag fuer Mahnung
    min_dunning_amount: Decimal = Decimal("5.00")


@dataclass
class DunningCandidate:
    """Kandidat fuer Mahnung."""
    document_id: UUID
    invoice_number: Optional[str]
    creditor_name: Optional[str]
    amount: Decimal
    due_date: date
    days_overdue: int
    current_level: DunningLevel
    recommended_action: DunningAction
    accumulated_fees: Decimal = Decimal("0.00")
    late_interest: Decimal = Decimal("0.00")
    total_due: Decimal = Decimal("0.00")


class DunningService:
    """Service fuer Mahnwesen."""

    def __init__(self, config: Optional[DunningConfig] = None):
        """Initialisiere Dunning Service.

        Args:
            config: Optionale Mahnkonfiguration
        """
        self.config = config or DunningConfig()

    async def get_overdue_invoices(
        self,
        db: AsyncSession,
        user_id: UUID,
        min_days_overdue: int = 1,
        max_days_overdue: Optional[int] = None,
        include_in_progress: bool = False,
    ) -> List[DunningCandidate]:
        """Hole ueberfaellige Rechnungen.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            min_days_overdue: Mindestens so viele Tage ueberfaellig
            max_days_overdue: Maximal so viele Tage ueberfaellig
            include_in_progress: Auch laufende Mahnverfahren?

        Returns:
            Liste von Mahnkandidaten
        """
        today = date.today()
        candidates = []

        # Offene Rechnungen mit Faelligkeitsdatum
        query = select(Document).where(
            and_(
                Document.owner_id == user_id,
                Document.document_type == "invoice",
                Document.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        for doc in documents:
            extracted = doc.extracted_data or {}

            # Pruefen ob bezahlt
            if extracted.get("payment_status") == "paid":
                continue

            # Betrag pruefen
            amount = extracted.get("total_amount") or extracted.get("amount")
            if not amount:
                continue

            try:
                amount = Decimal(str(amount))
            except (ValueError, TypeError, InvalidOperation):
                continue

            if amount < self.config.min_dunning_amount:
                continue

            # Faelligkeitsdatum
            due_date_str = extracted.get("due_date")
            if not due_date_str:
                continue

            try:
                if isinstance(due_date_str, str):
                    due_date = datetime.fromisoformat(due_date_str).date()
                else:
                    due_date = due_date_str
            except (ValueError, TypeError):
                continue

            # Ueberfaellig?
            days_overdue = (today - due_date).days
            if days_overdue < min_days_overdue:
                continue
            if max_days_overdue and days_overdue > max_days_overdue:
                continue

            # Existierendes Mahnverfahren pruefen
            dunning_record = await self._get_dunning_record(db, doc.id)
            current_level = DunningLevel.NOT_STARTED
            accumulated_fees = Decimal("0.00")

            if dunning_record:
                if not include_in_progress and dunning_record.status == DunningStatus.PENDING.value:
                    continue
                current_level = DunningLevel(dunning_record.dunning_level)
                accumulated_fees = dunning_record.total_fees or Decimal("0.00")

            # Empfohlene Aktion berechnen
            recommended_action = self._get_recommended_action(
                days_overdue, current_level
            )

            # Verzugszinsen berechnen
            late_interest = self._calculate_late_interest(
                amount, due_date, today
            )

            # Gesamtbetrag
            new_fees = self._get_fee_for_action(recommended_action)
            total_due = amount + accumulated_fees + new_fees + late_interest

            candidates.append(DunningCandidate(
                document_id=doc.id,
                invoice_number=extracted.get("invoice_number"),
                creditor_name=extracted.get("creditor_name"),
                amount=amount,
                due_date=due_date,
                days_overdue=days_overdue,
                current_level=current_level,
                recommended_action=recommended_action,
                accumulated_fees=accumulated_fees,
                late_interest=late_interest,
                total_due=total_due,
            ))

        # Nach Ueberfaelligkeit sortieren
        candidates.sort(key=lambda c: c.days_overdue, reverse=True)

        logger.info(
            "overdue_invoices_found",
            user_id=str(user_id),
            count=len(candidates),
            total_amount=float(sum(c.total_due for c in candidates)),
        )

        return candidates

    async def create_dunning(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_id: UUID,
        level: DunningLevel,
        notes: Optional[str] = None,
    ) -> DunningRecordResponse:
        """Erstelle neuen Mahnvorgang.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_id: Dokument-ID (Rechnung)
            level: Mahnstufe
            notes: Optionale Notizen

        Returns:
            DunningRecordResponse
        """
        # Dokument laden
        doc_result = await db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.owner_id == user_id,
                )
            )
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            raise ValueError("Dokument nicht gefunden")

        extracted = document.extracted_data or {}

        # Existierendes Mahnverfahren pruefen
        existing = await self._get_dunning_record(db, document_id)
        if existing:
            raise ValueError(
                f"Mahnverfahren existiert bereits (Stufe {existing.dunning_level})"
            )

        # Betrag und Faelligkeit
        amount = Decimal(str(extracted.get("total_amount") or extracted.get("amount", 0)))
        due_date_str = extracted.get("due_date")
        due_date = None
        if due_date_str:
            if isinstance(due_date_str, str):
                due_date = datetime.fromisoformat(due_date_str).date()
            else:
                due_date = due_date_str

        # Gebuehr berechnen
        fee = self._get_fee_for_level(level)
        late_interest = Decimal("0.00")
        if due_date:
            late_interest = self._calculate_late_interest(
                amount, due_date, date.today()
            )

        # Mahnvorgang erstellen
        dunning = DunningRecord(
            id=uuid4(),
            user_id=user_id,
            document_id=document_id,
            dunning_level=level.value,
            status=DunningStatus.PENDING.value,
            gross_amount=amount,
            reminder_fee=fee,
            accrued_interest=late_interest,
            due_date=due_date,
            resolution_notes=notes,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(dunning)
        await db.commit()
        await db.refresh(dunning)

        logger.info(
            "dunning_created",
            dunning_id=str(dunning.id),
            document_id=str(document_id),
            level=level.value,
            amount=float(amount),
            fee=float(fee),
        )

        return self._to_response(dunning)

    async def escalate_dunning(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_id: UUID,
        notes: Optional[str] = None,
    ) -> DunningRecordResponse:
        """Eskaliere Mahnvorgang zur naechsten Stufe.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            dunning_id: Mahnvorgang-ID
            notes: Optionale Notizen

        Returns:
            Aktualisierter DunningRecordResponse
        """
        dunning = await self._get_dunning_by_id(db, user_id, dunning_id)
        if not dunning:
            raise ValueError("Mahnvorgang nicht gefunden")

        if dunning.status != DunningStatus.PENDING.value:
            raise ValueError(
                f"Mahnvorgang kann nicht eskaliert werden (Status: {dunning.status})"
            )

        current_level = DunningLevel(dunning.dunning_level)

        # Naechste Stufe bestimmen
        level_order = [DunningLevel.NOT_STARTED, DunningLevel.FIRST_REMINDER, DunningLevel.SECOND_REMINDER, DunningLevel.FINAL_REMINDER]
        try:
            current_idx = level_order.index(current_level)
            if current_idx >= len(level_order) - 1:
                raise ValueError("Maximale Mahnstufe bereits erreicht")
            new_level = level_order[current_idx + 1]
        except ValueError:
            new_level = DunningLevel.FIRST_REMINDER

        # Neue Gebuehr hinzufuegen
        new_fee = self._get_fee_for_level(new_level)
        total_fees = (dunning.reminder_fee or Decimal("0.00")) + new_fee

        # Verzugszinsen aktualisieren
        late_interest = self._calculate_late_interest(
            dunning.gross_amount,
            dunning.due_date,
            date.today()
        )

        # Aktualisieren
        dunning.dunning_level = new_level.value
        dunning.reminder_fee = total_fees
        dunning.accrued_interest = late_interest
        dunning.updated_at = datetime.utcnow()
        if notes:
            dunning.resolution_notes = (dunning.resolution_notes or "") + f"\n[{datetime.now().isoformat()}] {notes}"

        await db.commit()
        await db.refresh(dunning)

        logger.info(
            "dunning_escalated",
            dunning_id=str(dunning_id),
            from_level=current_level.value,
            to_level=new_level.value,
            total_fees=float(total_fees),
        )

        return self._to_response(dunning)

    async def close_dunning(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_id: UUID,
        status: DunningStatus,
        notes: Optional[str] = None,
    ) -> DunningRecordResponse:
        """Schliesse Mahnvorgang ab.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            dunning_id: Mahnvorgang-ID
            status: Neuer Status (PAID, CANCELLED, WRITTEN_OFF)
            notes: Optionale Notizen

        Returns:
            Aktualisierter DunningRecordResponse
        """
        if status == DunningStatus.PENDING:
            raise ValueError("Mahnvorgang kann nicht auf 'in_progress' gesetzt werden")

        dunning = await self._get_dunning_by_id(db, user_id, dunning_id)
        if not dunning:
            raise ValueError("Mahnvorgang nicht gefunden")

        dunning.status = status.value
        dunning.resolved_at = datetime.utcnow()
        dunning.updated_at = datetime.utcnow()
        if notes:
            dunning.resolution_notes = (dunning.resolution_notes or "") + f"\n[{datetime.now().isoformat()}] {notes}"

        await db.commit()
        await db.refresh(dunning)

        logger.info(
            "dunning_closed",
            dunning_id=str(dunning_id),
            status=status.value,
        )

        return self._to_response(dunning)

    async def list_dunnings(
        self,
        db: AsyncSession,
        user_id: UUID,
        status: Optional[DunningStatus] = None,
        level: Optional[DunningLevel] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[DunningRecordResponse], int]:
        """Liste Mahnvorgaenge auf.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            status: Optionaler Status-Filter
            level: Optionaler Level-Filter
            limit: Max. Ergebnisse
            offset: Offset fuer Pagination

        Returns:
            Tuple (Liste, Gesamtanzahl)
        """
        query = select(DunningRecord).where(DunningRecord.user_id == user_id)

        if status:
            query = query.where(DunningRecord.status == status.value)
        if level:
            query = query.where(DunningRecord.dunning_level == level.value)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Fetch with pagination
        query = query.order_by(DunningRecord.updated_at.desc())
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        dunnings = result.scalars().all()

        return [self._to_response(d) for d in dunnings], total

    async def get_dunning_stats(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Hole Mahnstatistiken.

        Returns:
            Dictionary mit Statistiken
        """
        # Ueberfaellige Rechnungen
        overdue = await self.get_overdue_invoices(db, user_id)

        # Aktive Mahnverfahren
        active_result = await db.execute(
            select(func.count(), func.sum(DunningRecord.gross_amount)).where(
                and_(
                    DunningRecord.user_id == user_id,
                    DunningRecord.status == DunningStatus.PENDING.value,
                )
            )
        )
        active_row = active_result.one()
        active_count = active_row[0] or 0
        active_amount = active_row[1] or Decimal("0.00")

        # Nach Stufen gruppiert
        level_query = select(
            DunningRecord.dunning_level,
            func.count(),
            func.sum(DunningRecord.gross_amount),
        ).where(
            and_(
                DunningRecord.user_id == user_id,
                DunningRecord.status == DunningStatus.PENDING.value,
            )
        ).group_by(DunningRecord.dunning_level)

        level_result = await db.execute(level_query)
        by_level = {
            DunningLevel(row[0]).name.lower(): {
                "count": row[1],
                "amount": float(row[2] or 0),
            }
            for row in level_result
        }

        # Abgeschlossene (letzte 30 Tage)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        closed_result = await db.execute(
            select(DunningRecord.status, func.count()).where(
                and_(
                    DunningRecord.user_id == user_id,
                    DunningRecord.resolved_at >= thirty_days_ago,
                )
            ).group_by(DunningRecord.status)
        )
        closed_stats = {row[0]: row[1] for row in closed_result}

        return {
            "overdue": {
                "count": len(overdue),
                "total_amount": float(sum(c.amount for c in overdue)),
                "total_with_fees": float(sum(c.total_due for c in overdue)),
            },
            "active_dunnings": {
                "count": active_count,
                "amount": float(active_amount),
            },
            "by_level": by_level,
            "closed_last_30_days": {
                "paid": closed_stats.get(DunningStatus.PAID.value, 0),
                "partially_paid": closed_stats.get(DunningStatus.PARTIALLY_PAID.value, 0),
                "written_off": closed_stats.get(DunningStatus.WRITTEN_OFF.value, 0),
            },
            "fees_collected": await self._get_collected_fees(db, user_id),
        }

    async def process_automatic_dunning(
        self,
        db: AsyncSession,
        user_id: UUID,
        dry_run: bool = True,
    ) -> List[Dict[str, Any]]:
        """Fuehre automatisches Mahnverfahren durch.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            dry_run: Nur simulieren, nicht ausfuehren

        Returns:
            Liste der durchgefuehrten/geplanten Aktionen
        """
        actions = []
        overdue = await self.get_overdue_invoices(
            db, user_id, include_in_progress=True
        )

        for candidate in overdue:
            action_info = {
                "document_id": str(candidate.document_id),
                "invoice_number": candidate.invoice_number,
                "amount": float(candidate.amount),
                "days_overdue": candidate.days_overdue,
                "current_level": candidate.current_level.name,
                "recommended_action": candidate.recommended_action.value,
                "executed": False,
            }

            if not dry_run:
                try:
                    if candidate.recommended_action == DunningAction.FIRST_DUNNING:
                        await self.create_dunning(
                            db, user_id, candidate.document_id,
                            DunningLevel.FIRST_REMINDER
                        )
                        action_info["executed"] = True
                    elif candidate.recommended_action in [
                        DunningAction.SECOND_DUNNING,
                        DunningAction.FINAL_DUNNING,
                    ]:
                        # Bestehenden Mahnvorgang eskalieren
                        dunning = await self._get_dunning_record(
                            db, candidate.document_id
                        )
                        if dunning:
                            await self.escalate_dunning(
                                db, user_id, dunning.id
                            )
                            action_info["executed"] = True
                except Exception as e:
                    action_info["error"] = str(e)

            actions.append(action_info)

        logger.info(
            "automatic_dunning_processed",
            user_id=str(user_id),
            dry_run=dry_run,
            actions_count=len(actions),
            executed_count=sum(1 for a in actions if a.get("executed")),
        )

        return actions

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _get_dunning_record(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> Optional[DunningRecord]:
        """Hole Mahnvorgang fuer Dokument."""
        result = await db.execute(
            select(DunningRecord).where(
                DunningRecord.document_id == document_id
            )
        )
        return result.scalar_one_or_none()

    async def _get_dunning_by_id(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_id: UUID,
    ) -> Optional[DunningRecord]:
        """Hole Mahnvorgang nach ID."""
        result = await db.execute(
            select(DunningRecord).where(
                and_(
                    DunningRecord.id == dunning_id,
                    DunningRecord.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_collected_fees(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> float:
        """Hole eingesammelte Mahngebuehren (letzte 30 Tage)."""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        result = await db.execute(
            select(func.sum(DunningRecord.reminder_fee)).where(
                and_(
                    DunningRecord.user_id == user_id,
                    DunningRecord.status == DunningStatus.PAID.value,
                    DunningRecord.resolved_at >= thirty_days_ago,
                )
            )
        )
        return float(result.scalar() or 0)

    def _get_recommended_action(
        self,
        days_overdue: int,
        current_level: DunningLevel,
    ) -> DunningAction:
        """Bestimme empfohlene Mahnaktion."""
        if days_overdue < self.config.reminder_after_days:
            return DunningAction.REMINDER

        if current_level == DunningLevel.NOT_STARTED:
            if days_overdue >= self.config.first_dunning_after_days:
                return DunningAction.FIRST_DUNNING
            return DunningAction.REMINDER

        if current_level == DunningLevel.FIRST_REMINDER:
            if days_overdue >= self.config.second_dunning_after_days:
                return DunningAction.SECOND_DUNNING
            return DunningAction.FIRST_DUNNING

        if current_level == DunningLevel.SECOND_REMINDER:
            if days_overdue >= self.config.final_dunning_after_days:
                return DunningAction.FINAL_DUNNING
            return DunningAction.SECOND_DUNNING

        if current_level == DunningLevel.FINAL_REMINDER:
            return DunningAction.COLLECTION

        return DunningAction.REMINDER

    def _get_fee_for_level(self, level: DunningLevel) -> Decimal:
        """Hole Gebuehr fuer Mahnstufe."""
        fees = {
            DunningLevel.NOT_STARTED: Decimal("0.00"),
            DunningLevel.FIRST_REMINDER: self.config.first_dunning_fee,
            DunningLevel.SECOND_REMINDER: self.config.second_dunning_fee,
            DunningLevel.FINAL_REMINDER: self.config.final_dunning_fee,
        }
        return fees.get(level, Decimal("0.00"))

    def _get_fee_for_action(self, action: DunningAction) -> Decimal:
        """Hole Gebuehr fuer Mahnaktion."""
        fees = {
            DunningAction.REMINDER: Decimal("0.00"),
            DunningAction.FIRST_DUNNING: self.config.first_dunning_fee,
            DunningAction.SECOND_DUNNING: self.config.second_dunning_fee,
            DunningAction.FINAL_DUNNING: self.config.final_dunning_fee,
            DunningAction.COLLECTION: Decimal("0.00"),
            DunningAction.WRITE_OFF: Decimal("0.00"),
        }
        return fees.get(action, Decimal("0.00"))

    def _calculate_late_interest(
        self,
        principal: Decimal,
        due_date: date,
        as_of_date: date,
    ) -> Decimal:
        """Berechne Verzugszinsen.

        Verzugszinsen = Basiszins + 5% (fuer Verbraucher)
        oder Basiszins + 9% (fuer Geschaeftskunden)

        Hier: Basiszins + 5%
        """
        if due_date >= as_of_date:
            return Decimal("0.00")

        days_late = (as_of_date - due_date).days
        if days_late <= 0:
            return Decimal("0.00")

        # Jahresszins = Basiszins + Aufschlag
        annual_rate = (
            self.config.base_interest_rate + self.config.late_interest_rate
        ) / Decimal("100")

        # Tageszins
        daily_rate = annual_rate / Decimal("365")

        # Zinsberechnung
        interest = principal * daily_rate * Decimal(str(days_late))

        # Auf 2 Dezimalstellen runden
        return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _to_response(self, dunning: DunningRecord) -> DunningRecordResponse:
        """Konvertiere zu Response-Schema."""
        return DunningRecordResponse(
            id=dunning.id,
            document_id=dunning.document_id,
            invoice_number=dunning.invoice_number,
            invoice_date=dunning.invoice_date.date() if dunning.invoice_date else None,
            due_date=dunning.due_date.date() if dunning.due_date else None,
            gross_amount=dunning.gross_amount,
            outstanding_amount=dunning.outstanding_amount,
            currency=dunning.currency or "EUR",
            debtor_name=dunning.debtor_name,
            debtor_email=dunning.debtor_email,
            dunning_level=DunningLevel(dunning.dunning_level),
            status=DunningStatus(dunning.status),
            reminder_fee=dunning.reminder_fee or Decimal("0.00"),
            late_interest_rate=dunning.late_interest_rate,
            accrued_interest=dunning.accrued_interest or Decimal("0.00"),
            total_outstanding=dunning.total_outstanding,
            first_reminder_at=dunning.first_reminder_at,
            second_reminder_at=dunning.second_reminder_at,
            final_reminder_at=dunning.final_reminder_at,
            next_action_at=dunning.next_action_at,
            created_at=dunning.created_at,
            updated_at=dunning.updated_at,
        )


# Singleton
dunning_service = DunningService()

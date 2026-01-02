# -*- coding: utf-8 -*-
"""Dunning (Mahnwesen) Service.

Verwaltet das automatische Mahnwesen:
- Ueberfaellige Rechnungen erkennen
- Mahnstufen verwalten
- Mahngebuehren und Verzugszinsen berechnen
- Mahnschreiben generieren
- Mahnstopp fuer Reklamationen
- Audit-Log (mahnung_history)

Mahnstufen:
0 - Nicht begonnen
1 - 1. Mahnung (Zahlungserinnerung)
2 - 2. Mahnung (+ Mahngebuehr)
3 - Letzte Mahnung (+ Verzugszinsen, Inkasso-Androhung)

BGB §286 Compliance:
- B2B: Basiszins + 9% = 11.27% p.a.
- B2C: Basiszins + 5% = 7.27% p.a.
- EUR 40 Pauschale nach §288 Abs. 5 BGB
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
from sqlalchemy.orm import selectinload

from app.services.banking.models import (
    DunningLevel,
    DunningStatus,
    DunningRecordResponse,
)

from app.db.models import DunningRecord, Document, MahnungHistory, User

logger = structlog.get_logger(__name__)

# BGB §286 Zinssaetze (Stand: Januar 2025)
BASE_INTEREST_RATE = Decimal("2.27")  # Basiszinssatz
B2B_INTEREST_ADDON = Decimal("9.00")  # B2B: +9%
B2C_INTEREST_ADDON = Decimal("5.00")  # B2C: +5%
B2B_PAUSCHALE = Decimal("40.00")  # §288 Abs. 5 BGB


class MahnungHistoryAction(str, Enum):
    """Aktionstypen fuer Mahnung-History."""
    REMINDER_SENT = "reminder_sent"
    ESCALATED = "escalated"
    PHONE_CALL = "phone_call"
    PAYMENT_RECEIVED = "payment_received"
    PARTIAL_PAYMENT = "partial_payment"
    MAHNSTOPP_SET = "mahnstopp_set"
    MAHNSTOPP_LIFTED = "mahnstopp_lifted"
    B2B_PAUSCHALE_CLAIMED = "b2b_pauschale_claimed"
    WRITTEN_OFF = "written_off"
    SENT_TO_COLLECTION = "sent_to_collection"


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
        mahnstopp: Optional[bool] = None,
        is_b2b: Optional[bool] = None,
        business_entity_id: Optional[UUID] = None,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[DunningRecordResponse], int]:
        """Liste Mahnvorgaenge auf.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            status: Optionaler Status-Filter
            level: Optionaler Level-Filter
            mahnstopp: Filter fuer Mahnstopp-Vorgaenge
            is_b2b: Filter fuer B2B/B2C
            business_entity_id: Filter fuer Geschaeftspartner
            active_only: Nur aktive (nicht abgeschlossene) Mahnungen
            limit: Max. Ergebnisse
            offset: Offset fuer Pagination

        Returns:
            Tuple (Liste, Gesamtanzahl)
        """
        query = select(DunningRecord).where(DunningRecord.user_id == user_id)

        if status:
            query = query.where(DunningRecord.status == status.value)
        elif active_only:
            # Aktive Mahnungen = alle ausser bezahlt, abgeschrieben, rechtlich
            closed_statuses = [
                DunningStatus.PAID.value,
                DunningStatus.WRITTEN_OFF.value,
            ]
            query = query.where(DunningRecord.status.notin_(closed_statuses))
        if level:
            query = query.where(DunningRecord.dunning_level == level.value)
        if mahnstopp is not None:
            query = query.where(DunningRecord.mahnstopp == mahnstopp)
        if is_b2b is not None:
            query = query.where(DunningRecord.is_b2b == is_b2b)
        if business_entity_id is not None:
            query = query.where(DunningRecord.business_entity_id == business_entity_id)

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
            Dictionary mit Statistiken im Frontend-kompatiblen Format:
            - total_active: Anzahl aktiver Mahnungen
            - total_amount_overdue: Gesamtbetrag ueberfaelliger Forderungen
            - total_fees: Gesamte Mahngebuehren
            - avg_days_overdue: Durchschnittliche Ueberfaelligkeit in Tagen
            - by_level: Anzahl pro Mahnstufe
            - b2b_count: Anzahl B2B-Mahnungen
            - b2c_count: Anzahl B2C-Mahnungen
            - mahnstopp_count: Anzahl Mahnungen mit Mahnstopp
        """
        # Aktive Mahnungen (alle nicht abgeschlossenen)
        closed_statuses = [DunningStatus.PAID.value, DunningStatus.WRITTEN_OFF.value]

        # Gesamtzahl und Betraege aktiver Mahnungen
        active_result = await db.execute(
            select(
                func.count(),
                func.sum(DunningRecord.gross_amount),
                func.sum(DunningRecord.reminder_fee),
            ).where(
                and_(
                    DunningRecord.user_id == user_id,
                    DunningRecord.status.notin_(closed_statuses),
                )
            )
        )
        active_row = active_result.one()
        total_active = active_row[0] or 0
        total_amount_overdue = float(active_row[1] or 0)
        total_fees = float(active_row[2] or 0)

        # Durchschnittliche Ueberfaelligkeit in Tagen
        avg_days_result = await db.execute(
            select(
                func.avg(
                    func.extract('epoch', func.now() - DunningRecord.due_date) / 86400
                )
            ).where(
                and_(
                    DunningRecord.user_id == user_id,
                    DunningRecord.status.notin_(closed_statuses),
                    DunningRecord.due_date.isnot(None),
                )
            )
        )
        avg_days_overdue = float(avg_days_result.scalar() or 0)

        # Nach Stufen gruppiert (als Record<number, number>)
        level_query = select(
            DunningRecord.dunning_level,
            func.count(),
        ).where(
            and_(
                DunningRecord.user_id == user_id,
                DunningRecord.status.notin_(closed_statuses),
            )
        ).group_by(DunningRecord.dunning_level)

        level_result = await db.execute(level_query)
        by_level = {row[0]: row[1] for row in level_result}

        # B2B vs B2C Zaehlung
        b2b_result = await db.execute(
            select(func.count()).where(
                and_(
                    DunningRecord.user_id == user_id,
                    DunningRecord.status.notin_(closed_statuses),
                    DunningRecord.is_b2b == True,
                )
            )
        )
        b2b_count = b2b_result.scalar() or 0

        b2c_result = await db.execute(
            select(func.count()).where(
                and_(
                    DunningRecord.user_id == user_id,
                    DunningRecord.status.notin_(closed_statuses),
                    DunningRecord.is_b2b == False,
                )
            )
        )
        b2c_count = b2c_result.scalar() or 0

        # Mahnstopp-Zaehlung
        mahnstopp_result = await db.execute(
            select(func.count()).where(
                and_(
                    DunningRecord.user_id == user_id,
                    DunningRecord.status.notin_(closed_statuses),
                    DunningRecord.mahnstopp == True,
                )
            )
        )
        mahnstopp_count = mahnstopp_result.scalar() or 0

        return {
            "total_active": total_active,
            "total_amount_overdue": total_amount_overdue,
            "total_fees": total_fees,
            "avg_days_overdue": avg_days_overdue,
            "by_level": by_level,
            "b2b_count": b2b_count,
            "b2c_count": b2c_count,
            "mahnstopp_count": mahnstopp_count,
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

    # =========================================================================
    # Neue Methoden fuer erweitertes Mahnungswesen (BGB §286)
    # =========================================================================

    async def log_history_event(
        self,
        db: AsyncSession,
        dunning_record_id: UUID,
        action_type: MahnungHistoryAction,
        performed_by_id: Optional[UUID] = None,
        notes: Optional[str] = None,
        outcome: Optional[str] = None,
        document_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Schreibe Audit-Log-Eintrag (immutable).

        Args:
            db: Datenbank-Session
            dunning_record_id: Mahnvorgang-ID
            action_type: Art der Aktion
            performed_by_id: Benutzer-ID
            notes: Notizen
            outcome: Ergebnis (success, failed, pending)
            document_id: Optionales verknuepftes Dokument
            metadata: Zusaetzliche Metadaten (JSON)

        Returns:
            Erstellter History-Eintrag
        """
        # Aktuelle Mahnstufe ermitteln
        dunning = await db.get(DunningRecord, dunning_record_id)
        if not dunning:
            raise ValueError("Mahnvorgang nicht gefunden")

        history = MahnungHistory(
            id=uuid4(),
            dunning_record_id=dunning_record_id,
            action_type=action_type.value,
            mahn_stufe=dunning.dunning_level,
            action_timestamp=datetime.utcnow(),
            performed_by_id=performed_by_id,
            notes=notes,
            outcome=outcome,
            document_id=document_id,
            metadata=metadata or {},
        )

        db.add(history)
        await db.commit()
        await db.refresh(history)

        logger.info(
            "mahnung_history_logged",
            history_id=str(history.id),
            dunning_record_id=str(dunning_record_id),
            action_type=action_type.value,
        )

        return {
            "id": str(history.id),
            "dunning_record_id": str(history.dunning_record_id),
            "action_type": history.action_type,
            "mahn_stufe": history.mahn_stufe,
            "action_timestamp": history.action_timestamp.isoformat(),
            "performed_by_id": str(history.performed_by_id) if history.performed_by_id else None,
            "notes": history.notes,
            "outcome": history.outcome,
        }

    async def get_history(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_record_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Hole Mahnung-History fuer Mahnvorgang.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID (fuer Zugriffspruefung)
            dunning_record_id: Mahnvorgang-ID
            limit: Max. Eintraege
            offset: Offset fuer Pagination

        Returns:
            Tuple (Liste von History-Eintraegen, Gesamtanzahl)
        """
        # Zugriffspruefung
        dunning = await self._get_dunning_by_id(db, user_id, dunning_record_id)
        if not dunning:
            raise ValueError("Mahnvorgang nicht gefunden")

        # Gesamtanzahl
        count_query = (
            select(func.count())
            .select_from(MahnungHistory)
            .where(MahnungHistory.dunning_record_id == dunning_record_id)
        )
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginierte Daten mit Eager Loading (verhindert N+1)
        query = (
            select(MahnungHistory)
            .options(selectinload(MahnungHistory.performed_by))
            .where(MahnungHistory.dunning_record_id == dunning_record_id)
            .order_by(MahnungHistory.action_timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        entries = result.scalars().all()

        items = [
            {
                "id": str(e.id),
                "action_type": e.action_type,
                "mahn_stufe": e.mahn_stufe,
                "action_timestamp": e.action_timestamp.isoformat(),
                "performed_by_id": str(e.performed_by_id) if e.performed_by_id else None,
                "performed_by_name": e.performed_by.name if e.performed_by else None,
                "notes": e.notes,
                "outcome": e.outcome,
                "document_id": str(e.document_id) if e.document_id else None,
                "metadata": e.action_metadata,
            }
            for e in entries
        ]
        return items, total

    async def set_mahnstopp(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_id: UUID,
        reason: str,
        until_date: Optional[date] = None,
    ) -> DunningRecordResponse:
        """Setze Mahnstopp (z.B. bei Reklamation).

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            dunning_id: Mahnvorgang-ID
            reason: Grund für Mahnstopp
            until_date: Optionales Enddatum

        Returns:
            Aktualisierter Mahnvorgang
        """
        dunning = await self._get_dunning_by_id(db, user_id, dunning_id)
        if not dunning:
            raise ValueError("Mahnvorgang nicht gefunden")

        dunning.mahnstopp = True
        dunning.mahnstopp_reason = reason
        dunning.mahnstopp_until = datetime.combine(until_date, datetime.min.time()) if until_date else None
        dunning.updated_at = datetime.utcnow()

        # Audit-Log
        await self.log_history_event(
            db=db,
            dunning_record_id=dunning.id,
            action_type=MahnungHistoryAction.MAHNSTOPP_SET,
            performed_by_id=user_id,
            notes=f"Mahnstopp: {reason}",
            outcome="success",
            metadata={"until_date": until_date.isoformat() if until_date else None},
        )

        await db.commit()
        await db.refresh(dunning)

        logger.info(
            "mahnstopp_set",
            dunning_id=str(dunning_id),
            reason=reason,
        )

        return self._to_response(dunning)

    async def lift_mahnstopp(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_id: UUID,
        notes: Optional[str] = None,
    ) -> DunningRecordResponse:
        """Hebe Mahnstopp auf.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            dunning_id: Mahnvorgang-ID
            notes: Optionale Notizen

        Returns:
            Aktualisierter Mahnvorgang
        """
        dunning = await self._get_dunning_by_id(db, user_id, dunning_id)
        if not dunning:
            raise ValueError("Mahnvorgang nicht gefunden")

        if not dunning.mahnstopp:
            raise ValueError("Kein aktiver Mahnstopp vorhanden")

        old_reason = dunning.mahnstopp_reason
        dunning.mahnstopp = False
        dunning.mahnstopp_reason = None
        dunning.mahnstopp_until = None
        dunning.updated_at = datetime.utcnow()

        # Audit-Log
        await self.log_history_event(
            db=db,
            dunning_record_id=dunning.id,
            action_type=MahnungHistoryAction.MAHNSTOPP_LIFTED,
            performed_by_id=user_id,
            notes=notes or f"Mahnstopp aufgehoben (vorher: {old_reason})",
            outcome="success",
        )

        await db.commit()
        await db.refresh(dunning)

        logger.info(
            "mahnstopp_lifted",
            dunning_id=str(dunning_id),
        )

        return self._to_response(dunning)

    async def claim_b2b_pauschale(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_id: UUID,
    ) -> DunningRecordResponse:
        """Fordere B2B-Pauschale nach §288 Abs. 5 BGB.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            dunning_id: Mahnvorgang-ID

        Returns:
            Aktualisierter Mahnvorgang

        Raises:
            ValueError: Wenn nicht B2B oder bereits gefordert
        """
        dunning = await self._get_dunning_by_id(db, user_id, dunning_id)
        if not dunning:
            raise ValueError("Mahnvorgang nicht gefunden")

        if not dunning.is_b2b:
            raise ValueError("B2B-Pauschale nur fuer Geschaeftskunden moeglich")

        if dunning.b2b_pauschale_claimed:
            raise ValueError("B2B-Pauschale bereits gefordert")

        dunning.b2b_pauschale_claimed = True
        dunning.reminder_fee = (dunning.reminder_fee or Decimal("0.00")) + B2B_PAUSCHALE
        dunning.updated_at = datetime.utcnow()

        # Audit-Log
        await self.log_history_event(
            db=db,
            dunning_record_id=dunning.id,
            action_type=MahnungHistoryAction.B2B_PAUSCHALE_CLAIMED,
            performed_by_id=user_id,
            notes=f"B2B-Pauschale EUR {B2B_PAUSCHALE} nach §288 Abs. 5 BGB",
            outcome="success",
            metadata={"pauschale_amount": float(B2B_PAUSCHALE)},
        )

        await db.commit()
        await db.refresh(dunning)

        logger.info(
            "b2b_pauschale_claimed",
            dunning_id=str(dunning_id),
            amount=float(B2B_PAUSCHALE),
        )

        return self._to_response(dunning)

    def get_verzugszinsen_rate(self, is_b2b: bool = True) -> Decimal:
        """Hole aktuellen Verzugszinssatz nach BGB §288.

        Args:
            is_b2b: True fuer B2B, False fuer B2C

        Returns:
            Jaehrlicher Zinssatz in Prozent
        """
        addon = B2B_INTEREST_ADDON if is_b2b else B2C_INTEREST_ADDON
        return BASE_INTEREST_RATE + addon

    def calculate_verzugszinsen(
        self,
        principal: Decimal,
        due_date: date,
        as_of_date: date,
        is_b2b: bool = True,
    ) -> Decimal:
        """Berechne Verzugszinsen nach BGB §288.

        Args:
            principal: Hauptforderung
            due_date: Faelligkeitsdatum
            as_of_date: Berechnungsdatum
            is_b2b: B2B oder B2C

        Returns:
            Verzugszinsen in EUR
        """
        if due_date >= as_of_date:
            return Decimal("0.00")

        days_late = (as_of_date - due_date).days
        if days_late <= 0:
            return Decimal("0.00")

        # Jaehrlicher Zinssatz
        annual_rate = self.get_verzugszinsen_rate(is_b2b) / Decimal("100")

        # Tageszins
        daily_rate = annual_rate / Decimal("365")

        # Berechnung
        interest = principal * daily_rate * Decimal(str(days_late))

        return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def set_b2b_status(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_id: UUID,
        is_b2b: bool,
    ) -> DunningRecordResponse:
        """Setze B2B/B2C-Status fuer Mahnvorgang.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            dunning_id: Mahnvorgang-ID
            is_b2b: True fuer B2B, False fuer B2C

        Returns:
            Aktualisierter Mahnvorgang
        """
        dunning = await self._get_dunning_by_id(db, user_id, dunning_id)
        if not dunning:
            raise ValueError("Mahnvorgang nicht gefunden")

        old_status = "B2B" if dunning.is_b2b else "B2C"
        new_status = "B2B" if is_b2b else "B2C"

        dunning.is_b2b = is_b2b
        dunning.updated_at = datetime.utcnow()

        # Verzugszinsen neu berechnen
        if dunning.due_date:
            dunning.accrued_interest = self.calculate_verzugszinsen(
                principal=dunning.gross_amount or Decimal("0.00"),
                due_date=dunning.due_date.date() if hasattr(dunning.due_date, 'date') else dunning.due_date,
                as_of_date=date.today(),
                is_b2b=is_b2b,
            )

        await db.commit()
        await db.refresh(dunning)

        logger.info(
            "b2b_status_changed",
            dunning_id=str(dunning_id),
            old_status=old_status,
            new_status=new_status,
        )

        return self._to_response(dunning)

    async def bulk_escalate(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_ids: List[UUID],
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Eskaliere mehrere Mahnvorgaenge.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            dunning_ids: Liste von Mahnvorgang-IDs
            notes: Optionale Notizen

        Returns:
            Ergebnis mit Erfolgs- und Fehlerliste
        """
        successful = []
        failed = []

        for dunning_id in dunning_ids:
            try:
                result = await self.escalate_dunning(db, user_id, dunning_id, notes)
                successful.append(str(dunning_id))

                # Audit-Log
                await self.log_history_event(
                    db=db,
                    dunning_record_id=dunning_id,
                    action_type=MahnungHistoryAction.ESCALATED,
                    performed_by_id=user_id,
                    notes=notes,
                    outcome="success",
                )
            except Exception as e:
                failed.append({"id": str(dunning_id), "error": str(e)})

        logger.info(
            "bulk_escalation_completed",
            successful_count=len(successful),
            failed_count=len(failed),
        )

        return {
            "successful": successful,
            "failed": failed,
            "total_processed": len(dunning_ids),
        }

    async def get_dunnings_with_mahnstopp(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> List[DunningRecordResponse]:
        """Hole alle Mahnvorgaenge mit aktivem Mahnstopp.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Liste von Mahnvorgaengen mit Mahnstopp
        """
        query = select(DunningRecord).where(
            and_(
                DunningRecord.user_id == user_id,
                DunningRecord.mahnstopp == True,
            )
        ).order_by(DunningRecord.updated_at.desc())

        result = await db.execute(query)
        dunnings = result.scalars().all()

        return [self._to_response(d) for d in dunnings]

    async def check_expired_mahnstopp(
        self,
        db: AsyncSession,
    ) -> int:
        """Pruefe und hebe abgelaufene Mahnstopps auf.

        Wird vom Celery Beat Task taeglich aufgerufen.

        Returns:
            Anzahl aufgehobener Mahnstopps
        """
        today = datetime.utcnow()

        query = select(DunningRecord).where(
            and_(
                DunningRecord.mahnstopp == True,
                DunningRecord.mahnstopp_until.isnot(None),
                DunningRecord.mahnstopp_until <= today,
            )
        )

        result = await db.execute(query)
        dunnings = result.scalars().all()

        count = 0
        for dunning in dunnings:
            dunning.mahnstopp = False
            dunning.mahnstopp_reason = None
            dunning.mahnstopp_until = None
            dunning.updated_at = datetime.utcnow()

            # Audit-Log (ohne User-ID, da automatisch)
            history = MahnungHistory(
                id=uuid4(),
                dunning_record_id=dunning.id,
                action_type=MahnungHistoryAction.MAHNSTOPP_LIFTED.value,
                mahn_stufe=dunning.dunning_level,
                action_timestamp=datetime.utcnow(),
                notes="Automatisch aufgehoben (Ablaufdatum erreicht)",
                outcome="success",
            )
            db.add(history)
            count += 1

        if count > 0:
            await db.commit()
            logger.info(
                "expired_mahnstopp_lifted",
                count=count,
            )

        return count


# Singleton
dunning_service = DunningService()

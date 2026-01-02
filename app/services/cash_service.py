"""Cash Service - Kassenbuchführung (GoBD-konform).

Dieses Modul implementiert die gesamte Kassenbuch-Logik:
- Kassenbuchungen erstellen (APPEND-ONLY!)
- Stornierungen durch Gegenbuchung
- Kassensturz mit Zählprotokoll
- Zusammenfassungen und Reports

WICHTIG: GoBD-Compliance!
- CashEntry wird NIEMALS geändert oder gelöscht
- Stornierungen erfolgen durch Gegenbuchung mit Verweis
- entry_date darf nicht in der Zukunft liegen
- entry_number ist fortlaufend ohne Lücken
- balance_after muss bei jeder Buchung korrekt sein
"""

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    CashRegister,
    CashEntry,
    CashCategory,
    CashCount,
    CashEntryType,
    Company,
)
from app.db.schemas import (
    CashEntryCreate,
    CashEntryCancelRequest,
    CashCountCreate,
    CashCategoryCreate,
    CashRegisterCreate,
    CashRegisterUpdate,
    CashBookSummary,
    DailySummary,
    EntertainmentData,
)

logger = structlog.get_logger(__name__)


class CashService:
    """Service fuer Kassenbuchführung.

    Stellt alle Operationen fuer das Kassenbuch bereit:
    - Kassen verwalten
    - Buchungen erstellen (APPEND-ONLY!)
    - Stornierungen (Gegenbuchung)
    - Kassensturz
    - Reports
    """

    # Steuerliche Abzugsfähigkeit nach Buchungstyp
    DEDUCTIBLE_PERCENTAGES = {
        CashEntryType.ENTERTAINMENT.value: 70,  # Bewirtungskosten
        CashEntryType.GIFTS.value: 100,  # Kann je nach Betrag variieren
    }

    # Standard-MwSt-Sätze
    DEFAULT_TAX_RATES = {
        "standard": Decimal("19"),
        "reduced": Decimal("7"),
        "zero": Decimal("0"),
    }

    # =========================================================================
    # KASSEN-VERWALTUNG
    # =========================================================================

    async def create_register(
        self,
        db: AsyncSession,
        company_id: UUID,
        data: CashRegisterCreate,
        user_id: UUID
    ) -> CashRegister:
        """Erstellt eine neue Kasse.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            data: Kassen-Daten
            user_id: Benutzer-ID

        Returns:
            Erstellte Kasse
        """
        register = CashRegister(
            company_id=company_id,
            name=data.name,
            description=data.description,
            register_number=data.register_number,
            currency=data.currency,
            max_balance=data.max_balance,
            warning_threshold=data.warning_threshold,
            linked_bank_account_id=data.linked_bank_account_id,
            current_balance=Decimal(str(data.opening_balance)),
            balance_date=datetime.now(timezone.utc),
            created_by_id=user_id,
        )
        db.add(register)
        await db.flush()

        # Eröffnungsbuchung erstellen (falls Anfangsbestand > 0)
        if data.opening_balance != 0:
            await self._create_opening_entry(
                db=db,
                register=register,
                amount=Decimal(str(data.opening_balance)),
                user_id=user_id
            )

        await db.commit()
        await db.refresh(register)

        logger.info(
            "cash_register_created",
            register_id=str(register.id),
            company_id=str(company_id),
            name=register.name
        )

        return register

    async def get_register(
        self,
        db: AsyncSession,
        register_id: UUID,
        company_id: UUID
    ) -> Optional[CashRegister]:
        """Holt eine Kasse.

        Args:
            db: Datenbank-Session
            register_id: Kassen-ID
            company_id: Firmen-ID (zur Validierung)

        Returns:
            Kasse oder None
        """
        result = await db.execute(
            select(CashRegister)
            .where(CashRegister.id == register_id)
            .where(CashRegister.company_id == company_id)
            .where(CashRegister.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_registers(
        self,
        db: AsyncSession,
        company_id: UUID,
        skip: int = 0,
        limit: int = 50,
        include_inactive: bool = False
    ) -> Tuple[List[CashRegister], int]:
        """Holt alle Kassen einer Firma.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            skip: Anzahl zu ueberspringender Eintraege
            limit: Maximale Anzahl Eintraege
            include_inactive: Auch inaktive Kassen

        Returns:
            Tuple (Liste von Kassen, Gesamtanzahl)
        """
        base_query = select(CashRegister).where(
            CashRegister.company_id == company_id,
            CashRegister.deleted_at.is_(None)
        )

        if not include_inactive:
            base_query = base_query.where(CashRegister.is_active == True)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginierte Ergebnisse
        query = base_query.order_by(CashRegister.name).offset(skip).limit(limit)
        result = await db.execute(query)

        return list(result.scalars().all()), total

    async def update_register(
        self,
        db: AsyncSession,
        register_id: UUID,
        company_id: UUID,
        data: CashRegisterUpdate
    ) -> Optional[CashRegister]:
        """Aktualisiert eine Kasse.

        Args:
            db: Datenbank-Session
            register_id: Kassen-ID
            company_id: Firmen-ID
            data: Update-Daten

        Returns:
            Aktualisierte Kasse oder None
        """
        register = await self.get_register(db, register_id, company_id)
        if not register:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(register, field, value)

        await db.commit()
        await db.refresh(register)

        logger.info(
            "cash_register_updated",
            register_id=str(register_id),
            updated_fields=list(update_data.keys())
        )

        return register

    # =========================================================================
    # KASSENBUCHUNGEN (APPEND-ONLY!)
    # =========================================================================

    async def create_entry(
        self,
        db: AsyncSession,
        company_id: UUID,
        data: CashEntryCreate,
        user_id: UUID
    ) -> CashEntry:
        """Erstellt eine neue Kassenbuchung.

        WICHTIG: GoBD-konform, APPEND-ONLY!

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            data: Buchungsdaten
            user_id: Benutzer-ID

        Returns:
            Erstellte Buchung

        Raises:
            ValueError: Bei Validierungsfehlern
        """
        # Validierungen
        if data.entry_date.date() > date.today():
            raise ValueError("Buchungsdatum darf nicht in der Zukunft liegen (GoBD)")

        if data.amount == 0:
            raise ValueError("Betrag darf nicht 0 sein")

        # Kasse laden und sperren (FOR UPDATE)
        register = await self._get_register_for_update(
            db, data.cash_register_id, company_id
        )
        if not register:
            raise ValueError(f"Kasse nicht gefunden: {data.cash_register_id}")

        # Kategorie validieren (falls angegeben)
        if data.category_id:
            category_result = await db.execute(
                select(CashCategory).where(CashCategory.id == data.category_id)
            )
            category = category_result.scalar_one_or_none()
            if not category:
                raise ValueError(f"Kategorie nicht gefunden: {data.category_id}")
            if not category.is_active:
                raise ValueError(
                    f"Kategorie '{category.name}' ist deaktiviert und kann nicht verwendet werden"
                )

        # Nächste Entry-Nummer ermitteln
        fiscal_year = data.entry_date.year
        entry_number = await self._get_next_entry_number(
            db, data.cash_register_id, fiscal_year
        )

        # Steuer berechnen
        tax_rate, tax_amount, net_amount = self._calculate_tax(
            amount=Decimal(str(data.amount)),
            tax_rate=Decimal(str(data.tax_rate)) if data.tax_rate else None
        )

        # Abzugsfähigkeit ermitteln
        deductible_percentage = self._get_deductible_percentage(data.entry_type)

        # Neuen Saldo berechnen
        new_balance = Decimal(str(register.current_balance)) + Decimal(str(data.amount))

        # Buchungskonten ermitteln (SKR03/SKR04 dynamisch)
        debit_account, credit_account = await self._get_accounts(
            db, data.entry_type, data.category_id, company_id
        )

        # Buchung erstellen
        entry = CashEntry(
            company_id=company_id,
            cash_register_id=data.cash_register_id,
            entry_number=entry_number,
            fiscal_year=fiscal_year,
            entry_date=data.entry_date.date(),
            value_date=data.entry_date.date(),
            amount=Decimal(str(data.amount)),
            currency=register.currency,
            balance_after=new_balance,
            entry_type=data.entry_type.value,
            category_id=data.category_id,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            net_amount=net_amount,
            is_tax_deductible=deductible_percentage > 0,
            deductible_percentage=deductible_percentage,
            description=data.description,
            reference_number=data.reference_number,
            counterparty_name=data.counterparty_name,
            counterparty_id=data.counterparty_id,
            document_id=data.document_id,
            bank_transaction_id=data.bank_transaction_id,
            entertainment_data=data.entertainment_data.model_dump() if data.entertainment_data else None,
            debit_account=debit_account,
            credit_account=credit_account,
            cost_center=data.cost_center,
            created_by_id=user_id,
        )
        db.add(entry)

        # Kassenbestand aktualisieren
        register.current_balance = new_balance
        register.balance_date = datetime.now(timezone.utc)

        await db.commit()

        # Entry mit Kategorie-Relationship laden (N+1 Fix!)
        result = await db.execute(
            select(CashEntry)
            .options(selectinload(CashEntry.category))
            .where(CashEntry.id == entry.id)
        )
        entry = result.scalar_one()

        logger.info(
            "cash_entry_created",
            entry_id=str(entry.id),
            entry_number=entry_number,
            fiscal_year=fiscal_year,
            amount=float(data.amount),
            entry_type=data.entry_type.value,
            new_balance=float(new_balance)
        )

        return entry

    async def cancel_entry(
        self,
        db: AsyncSession,
        entry_id: UUID,
        company_id: UUID,
        data: CashEntryCancelRequest,
        user_id: UUID
    ) -> CashEntry:
        """Storniert eine Buchung durch Gegenbuchung.

        WICHTIG: Die Original-Buchung wird NICHT geändert oder gelöscht!
        Stattdessen wird eine Gegenbuchung mit umgekehrtem Vorzeichen erstellt.

        Args:
            db: Datenbank-Session
            entry_id: ID der zu stornierenden Buchung
            company_id: Firmen-ID
            data: Stornierungsgrund
            user_id: Benutzer-ID

        Returns:
            Stornobuchung (Gegenbuchung)

        Raises:
            ValueError: Bei Fehlern
        """
        # Original-Buchung laden mit FOR UPDATE Lock (Race-Condition verhindern!)
        # WICHTIG: Lock verhindert, dass zwei gleichzeitige Requests beide stornieren
        result = await db.execute(
            select(CashEntry)
            .options(selectinload(CashEntry.category))
            .where(CashEntry.id == entry_id)
            .where(CashEntry.company_id == company_id)
            .with_for_update()
        )
        original = result.scalar_one_or_none()

        if not original:
            raise ValueError(f"Buchung nicht gefunden: {entry_id}")

        if original.is_cancelled:
            raise ValueError("Buchung wurde bereits storniert")

        if original.entry_type == CashEntryType.CANCELLATION.value:
            raise ValueError("Stornobuchungen koennen nicht storniert werden")

        # Kasse sperren
        register = await self._get_register_for_update(
            db, original.cash_register_id, company_id
        )
        if not register:
            raise ValueError("Kasse nicht gefunden")

        # Nächste Entry-Nummer
        fiscal_year = date.today().year
        entry_number = await self._get_next_entry_number(
            db, original.cash_register_id, fiscal_year
        )

        # Gegenbuchung: Betrag mit umgekehrtem Vorzeichen
        cancel_amount = -original.amount
        new_balance = Decimal(str(register.current_balance)) + cancel_amount

        # Stornobuchung erstellen
        cancel_entry = CashEntry(
            company_id=company_id,
            cash_register_id=original.cash_register_id,
            entry_number=entry_number,
            fiscal_year=fiscal_year,
            entry_date=date.today(),
            value_date=date.today(),
            amount=cancel_amount,
            currency=original.currency,
            balance_after=new_balance,
            entry_type=CashEntryType.CANCELLATION.value,
            category_id=original.category_id,
            tax_rate=original.tax_rate,
            tax_amount=-original.tax_amount if original.tax_amount else None,
            net_amount=-original.net_amount if original.net_amount else None,
            is_tax_deductible=original.is_tax_deductible,
            deductible_percentage=original.deductible_percentage,
            description=f"STORNO #{original.entry_number}/{original.fiscal_year}: {data.reason}",
            reference_number=f"STORNO-{original.entry_number}",
            counterparty_name=original.counterparty_name,
            counterparty_id=original.counterparty_id,
            cancelled_by_entry_id=original.id,  # Diese Stornobuchung bezieht sich auf das Original
            cancellation_reason=data.reason,
            debit_account=original.credit_account,  # Umgekehrt!
            credit_account=original.debit_account,  # Umgekehrt!
            cost_center=original.cost_center,
            created_by_id=user_id,
        )
        db.add(cancel_entry)
        await db.flush()

        # Original markieren als storniert (mit Verweis auf Stornobuchung)
        original.is_cancelled = True
        original.cancelled_by_entry_id = cancel_entry.id
        original.cancellation_reason = data.reason
        # GoBD Audit Trail: Wer hat wann storniert?
        original.cancelled_by_user_id = user_id
        original.cancelled_at = datetime.now(timezone.utc)

        # Kassenbestand aktualisieren
        register.current_balance = new_balance
        register.balance_date = datetime.now(timezone.utc)

        await db.commit()

        # Stornobuchung mit Kategorie-Relationship laden (N+1 Fix!)
        result = await db.execute(
            select(CashEntry)
            .options(selectinload(CashEntry.category))
            .where(CashEntry.id == cancel_entry.id)
        )
        cancel_entry = result.scalar_one()

        logger.info(
            "cash_entry_cancelled",
            original_entry_id=str(entry_id),
            cancel_entry_id=str(cancel_entry.id),
            reason=data.reason,
            new_balance=float(new_balance)
        )

        return cancel_entry

    async def get_entries(
        self,
        db: AsyncSession,
        company_id: UUID,
        register_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        entry_type: Optional[str] = None,
        include_cancelled: bool = False,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[CashEntry], int]:
        """Holt Kassenbuchungen mit Filterung.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            register_id: Kassen-ID (optional)
            start_date: Von-Datum
            end_date: Bis-Datum
            entry_type: Buchungstyp
            include_cancelled: Auch stornierte Buchungen
            page: Seite
            page_size: Seitengröße

        Returns:
            Tuple (Buchungen, Gesamtanzahl)
        """
        # N+1 Fix: Eager Loading fuer Kategorie
        query = (
            select(CashEntry)
            .options(selectinload(CashEntry.category))
            .where(CashEntry.company_id == company_id)
        )

        if register_id:
            query = query.where(CashEntry.cash_register_id == register_id)

        if start_date:
            query = query.where(CashEntry.entry_date >= start_date)

        if end_date:
            query = query.where(CashEntry.entry_date <= end_date)

        if entry_type:
            query = query.where(CashEntry.entry_type == entry_type)

        if not include_cancelled:
            query = query.where(CashEntry.is_cancelled == False)

        # Count
        count_result = await db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0

        # Pagination
        query = query.order_by(
            CashEntry.entry_date.desc(),
            CashEntry.entry_number.desc()
        )
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        entries = list(result.scalars().all())

        return entries, total

    async def get_entry(
        self,
        db: AsyncSession,
        entry_id: UUID,
        company_id: UUID
    ) -> Optional[CashEntry]:
        """Holt einen einzelnen Kassenbucheintrag.

        Args:
            db: Datenbank-Session
            entry_id: Buchungs-ID
            company_id: Firmen-ID (zur Validierung)

        Returns:
            Buchung oder None
        """
        result = await db.execute(
            select(CashEntry)
            .options(selectinload(CashEntry.category))
            .where(CashEntry.id == entry_id)
            .where(CashEntry.company_id == company_id)
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # KASSENSTURZ
    # =========================================================================

    async def perform_cash_count(
        self,
        db: AsyncSession,
        company_id: UUID,
        data: CashCountCreate,
        user_id: UUID
    ) -> CashCount:
        """Führt einen Kassensturz durch.

        Vergleicht Ist-Bestand (gezählt) mit Soll-Bestand (Kassenbuch).
        Bei Differenz wird automatisch eine Ausgleichsbuchung erstellt.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            data: Zähldaten
            user_id: Benutzer-ID

        Returns:
            Zählprotokoll
        """
        # Kasse laden und sperren
        register = await self._get_register_for_update(
            db, data.cash_register_id, company_id
        )
        if not register:
            raise ValueError(f"Kasse nicht gefunden: {data.cash_register_id}")

        # Ist-Bestand berechnen
        counted_total = self._calculate_count_total(data)

        # Soll-Bestand
        expected_total = Decimal(str(register.current_balance))

        # Differenz
        difference = counted_total - expected_total

        # Zählprotokoll erstellen
        cash_count = CashCount(
            company_id=company_id,
            cash_register_id=data.cash_register_id,
            count_date=date.today(),
            count_time=datetime.now(timezone.utc).time(),
            coins_1_cent=data.coins_1_cent,
            coins_2_cent=data.coins_2_cent,
            coins_5_cent=data.coins_5_cent,
            coins_10_cent=data.coins_10_cent,
            coins_20_cent=data.coins_20_cent,
            coins_50_cent=data.coins_50_cent,
            coins_1_euro=data.coins_1_euro,
            coins_2_euro=data.coins_2_euro,
            notes_5_euro=data.notes_5_euro,
            notes_10_euro=data.notes_10_euro,
            notes_20_euro=data.notes_20_euro,
            notes_50_euro=data.notes_50_euro,
            notes_100_euro=data.notes_100_euro,
            notes_200_euro=data.notes_200_euro,
            notes_500_euro=data.notes_500_euro,
            expected_total=expected_total,
            counted_by_id=user_id,
            notes=data.notes,
        )
        db.add(cash_count)
        await db.flush()

        # Bei Differenz: Ausgleichsbuchung erstellen
        difference_entry = None
        if difference != 0:
            entry_type = CashEntryType.DIFFERENCE_PLUS if difference > 0 else CashEntryType.DIFFERENCE_MINUS
            description = (
                f"Kassendifferenz aus Kassensturz: "
                f"Ist {float(counted_total):.2f} EUR, Soll {float(expected_total):.2f} EUR"
            )

            # Nächste Entry-Nummer
            fiscal_year = date.today().year
            entry_number = await self._get_next_entry_number(
                db, data.cash_register_id, fiscal_year
            )

            # Neuer Saldo
            new_balance = counted_total  # Nach Ausgleich = Ist-Bestand

            difference_entry = CashEntry(
                company_id=company_id,
                cash_register_id=data.cash_register_id,
                entry_number=entry_number,
                fiscal_year=fiscal_year,
                entry_date=date.today(),
                value_date=date.today(),
                amount=difference,
                currency=register.currency,
                balance_after=new_balance,
                entry_type=entry_type.value,
                description=description,
                is_tax_deductible=False,
                deductible_percentage=0,
                created_by_id=user_id,
            )
            db.add(difference_entry)
            await db.flush()

            # Referenz in Zählprotokoll
            cash_count.difference_entry_id = difference_entry.id

            # Kassenbestand korrigieren
            register.current_balance = new_balance
            register.balance_date = datetime.now(timezone.utc)

        # Letztes Abstimmdatum aktualisieren
        register.last_reconciliation_date = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(cash_count)

        logger.info(
            "cash_count_performed",
            count_id=str(cash_count.id),
            register_id=str(data.cash_register_id),
            counted_total=float(counted_total),
            expected_total=float(expected_total),
            difference=float(difference),
            has_difference_entry=difference_entry is not None
        )

        return cash_count

    async def get_counts(
        self,
        db: AsyncSession,
        company_id: UUID,
        register_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[CashCount], int]:
        """Holt Zählprotokolle.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            register_id: Kassen-ID (optional)
            start_date: Von-Datum
            end_date: Bis-Datum
            skip: Anzahl zu ueberspringender Eintraege
            limit: Maximale Anzahl Eintraege

        Returns:
            Tuple (Liste von Zählprotokollen, Gesamtanzahl)
        """
        base_query = select(CashCount).where(CashCount.company_id == company_id)

        if register_id:
            base_query = base_query.where(CashCount.cash_register_id == register_id)

        if start_date:
            base_query = base_query.where(CashCount.count_date >= start_date)

        if end_date:
            base_query = base_query.where(CashCount.count_date <= end_date)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginierte Ergebnisse
        query = base_query.order_by(
            CashCount.count_date.desc(),
            CashCount.count_time.desc()
        ).offset(skip).limit(limit)
        result = await db.execute(query)

        return list(result.scalars().all()), total

    # =========================================================================
    # REPORTS
    # =========================================================================

    async def get_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
        register_id: UUID,
        start_date: Optional[date],
        end_date: Optional[date]
    ) -> CashBookSummary:
        """Erstellt eine Kassenbuch-Zusammenfassung.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            register_id: Kassen-ID
            start_date: Von-Datum (default: Anfang des Monats)
            end_date: Bis-Datum (default: heute)

        Returns:
            Zusammenfassung
        """
        register = await self.get_register(db, register_id, company_id)
        if not register:
            raise ValueError("Kasse nicht gefunden")

        # Standardwerte fuer Datumsbereich
        today = date.today()
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = date(today.year, today.month, 1)

        # Eröffnungssaldo (Saldo vor start_date)
        opening_result = await db.execute(
            select(CashEntry.balance_after)
            .where(CashEntry.cash_register_id == register_id)
            .where(CashEntry.entry_date < start_date)
            .order_by(CashEntry.entry_date.desc(), CashEntry.entry_number.desc())
            .limit(1)
        )
        opening_balance = opening_result.scalar() or Decimal("0")

        # Buchungen im Zeitraum
        entries_result = await db.execute(
            select(
                func.sum(case(
                    (CashEntry.amount > 0, CashEntry.amount),
                    else_=Decimal("0")
                )).label("income"),
                func.sum(case(
                    (CashEntry.amount < 0, CashEntry.amount),
                    else_=Decimal("0")
                )).label("expense"),
                func.count().label("entry_count"),
                func.sum(case(
                    (CashEntry.is_cancelled == True, 1),
                    else_=0
                )).label("cancelled_count")
            )
            .where(CashEntry.cash_register_id == register_id)
            .where(CashEntry.entry_date >= start_date)
            .where(CashEntry.entry_date <= end_date)
        )
        stats = entries_result.one()

        total_income = stats.income or Decimal("0")
        total_expense = abs(stats.expense or Decimal("0"))
        net_change = total_income - total_expense
        closing_balance = Decimal(str(opening_balance)) + net_change

        return CashBookSummary(
            register_id=register_id,
            register_name=register.name,
            period_start=datetime.combine(start_date, time.min),
            period_end=datetime.combine(end_date, time.max),
            opening_balance=float(opening_balance),
            closing_balance=float(closing_balance),
            total_income=float(total_income),
            total_expense=float(total_expense),
            net_change=float(net_change),
            entry_count=stats.entry_count or 0,
            cancelled_count=stats.cancelled_count or 0
        )

    async def get_daily_summaries(
        self,
        db: AsyncSession,
        company_id: UUID,
        register_id: UUID,
        start_date: date,
        end_date: date
    ) -> List[DailySummary]:
        """Erstellt tägliche Zusammenfassungen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            register_id: Kassen-ID
            start_date: Von-Datum
            end_date: Bis-Datum

        Returns:
            Liste von Tageszusammenfassungen
        """
        # Buchungen gruppiert nach Tag
        result = await db.execute(
            select(
                CashEntry.entry_date,
                func.sum(case(
                    (CashEntry.amount > 0, CashEntry.amount),
                    else_=Decimal("0")
                )).label("income"),
                func.sum(case(
                    (CashEntry.amount < 0, CashEntry.amount),
                    else_=Decimal("0")
                )).label("expense"),
                func.count().label("entry_count")
            )
            .where(CashEntry.cash_register_id == register_id)
            .where(CashEntry.entry_date >= start_date)
            .where(CashEntry.entry_date <= end_date)
            .where(CashEntry.is_cancelled == False)
            .group_by(CashEntry.entry_date)
            .order_by(CashEntry.entry_date)
        )

        summaries = []
        running_balance = Decimal("0")

        # Eröffnungssaldo
        opening_result = await db.execute(
            select(CashEntry.balance_after)
            .where(CashEntry.cash_register_id == register_id)
            .where(CashEntry.entry_date < start_date)
            .order_by(CashEntry.entry_date.desc(), CashEntry.entry_number.desc())
            .limit(1)
        )
        running_balance = opening_result.scalar() or Decimal("0")

        for row in result:
            income = row.income or Decimal("0")
            expense = abs(row.expense or Decimal("0"))
            net_change = income - expense
            opening = running_balance
            closing = opening + net_change
            running_balance = closing

            summaries.append(DailySummary(
                date=datetime.combine(row.entry_date, time.min),
                opening_balance=float(opening),
                closing_balance=float(closing),
                income=float(income),
                expense=float(expense),
                net_change=float(net_change),
                entry_count=row.entry_count
            ))

        return summaries

    # =========================================================================
    # KATEGORIEN
    # =========================================================================

    async def get_categories(
        self,
        db: AsyncSession,
        company_id: Optional[UUID] = None,
        include_system: bool = True,
        active_only: bool = True
    ) -> List[CashCategory]:
        """Holt Kategorien.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (für firmenspezifische Kategorien)
            include_system: Auch System-Kategorien
            active_only: Nur aktive Kategorien

        Returns:
            Liste von Kategorien
        """
        query = select(CashCategory)

        if company_id:
            # Firmenspezifische + System-Kategorien
            if include_system:
                query = query.where(
                    (CashCategory.company_id == company_id) |
                    (CashCategory.company_id.is_(None))
                )
            else:
                query = query.where(CashCategory.company_id == company_id)
        else:
            # Nur System-Kategorien
            query = query.where(CashCategory.company_id.is_(None))

        if active_only:
            query = query.where(CashCategory.is_active == True)

        query = query.order_by(CashCategory.sort_order, CashCategory.name)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create_category(
        self,
        db: AsyncSession,
        company_id: UUID,
        data: CashCategoryCreate,
    ) -> CashCategory:
        """Erstellt eine neue Kategorie.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            data: Kategorie-Daten

        Returns:
            Erstellte Kategorie
        """
        category = CashCategory(
            company_id=company_id,
            name=data.name,
            description=data.description,
            skr03_account=data.skr03_account,
            skr04_account=data.skr04_account,
            default_tax_rate=data.default_tax_rate,
            is_active=True,
        )
        db.add(category)
        await db.commit()
        await db.refresh(category)

        logger.info(
            "cash_category_created",
            category_id=str(category.id),
            company_id=str(company_id),
            name=category.name
        )

        return category

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _get_register_for_update(
        self,
        db: AsyncSession,
        register_id: UUID,
        company_id: UUID
    ) -> Optional[CashRegister]:
        """Holt eine Kasse mit Sperre (FOR UPDATE).

        Args:
            db: Datenbank-Session
            register_id: Kassen-ID
            company_id: Firmen-ID

        Returns:
            Kasse oder None
        """
        result = await db.execute(
            select(CashRegister)
            .where(CashRegister.id == register_id)
            .where(CashRegister.company_id == company_id)
            .where(CashRegister.deleted_at.is_(None))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _get_next_entry_number(
        self,
        db: AsyncSession,
        register_id: UUID,
        fiscal_year: int
    ) -> int:
        """Ermittelt die nächste fortlaufende Nummer (thread-safe).

        WICHTIG: Diese Methode muss innerhalb einer Transaktion aufgerufen werden,
        bei der das Register bereits mit FOR UPDATE gesperrt ist!

        Die Kombination aus Register-Lock + Entry-Lock garantiert:
        - Keine doppelten Belegnummern (GoBD-Compliance)
        - Keine Lücken in der Nummernfolge
        - Serialisierte Zugriffe bei parallelen Buchungen

        Args:
            db: Datenbank-Session
            register_id: Kassen-ID
            fiscal_year: Geschäftsjahr

        Returns:
            Nächste Nummer (1-basiert)
        """
        # HINWEIS: Die Thread-Sicherheit wird durch das Register-Lock garantiert.
        # Das Register muss VOR diesem Aufruf mit _get_register_for_update() gesperrt sein!
        # PostgreSQL erlaubt FOR UPDATE nicht mit Aggregatfunktionen (max, count, etc.).
        # Das Register-Lock serialisiert alle Zugriffe auf dieses Register.
        result = await db.execute(
            select(func.max(CashEntry.entry_number))
            .where(CashEntry.cash_register_id == register_id)
            .where(CashEntry.fiscal_year == fiscal_year)
        )
        max_number = result.scalar() or 0
        return max_number + 1

    def _calculate_tax(
        self,
        amount: Decimal,
        tax_rate: Optional[Decimal]
    ) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Berechnet Steuerbeträge.

        Args:
            amount: Bruttobetrag
            tax_rate: MwSt-Satz (None = keine Steuer)

        Returns:
            Tuple (Steuersatz, Steuerbetrag, Nettobetrag)
        """
        if tax_rate is None:
            return None, None, None

        # Betrag ist Brutto, Steuer rausrechnen
        net_amount = amount / (1 + tax_rate / 100)
        tax_amount = amount - net_amount

        return tax_rate, tax_amount.quantize(Decimal("0.01")), net_amount.quantize(Decimal("0.01"))

    def _get_deductible_percentage(self, entry_type: CashEntryType) -> int:
        """Ermittelt Abzugsfähigkeit nach Buchungstyp.

        Args:
            entry_type: Buchungstyp

        Returns:
            Prozentsatz (0-100)
        """
        return self.DEDUCTIBLE_PERCENTAGES.get(entry_type.value, 100)

    async def check_duplicate(
        self,
        db: AsyncSession,
        register_id: UUID,
        company_id: UUID,
        amount: Decimal,
        entry_date: date,
        description: str,
        reference_number: Optional[str] = None
    ) -> Optional[CashEntry]:
        """Prüft auf mögliche Duplikate (UX-Verbesserung).

        Sucht nach Buchungen mit:
        - Gleicher Firma (SICHERHEIT: RLS-Bypass verhindern!)
        - Gleichem Register
        - Gleichem Betrag
        - Gleichem Datum
        - Und: gleiche Belegnummer ODER aehnliche Beschreibung

        Args:
            db: Datenbank-Session
            register_id: Kassen-ID
            company_id: Firmen-ID (PFLICHT fuer Multi-Tenant-Sicherheit!)
            amount: Betrag
            entry_date: Buchungsdatum
            description: Beschreibung
            reference_number: Belegnummer (optional)

        Returns:
            Potentielles Duplikat oder None
        """
        # Basis-Query mit company_id fuer Multi-Tenant-Sicherheit!
        query = (
            select(CashEntry)
            .where(CashEntry.company_id == company_id)
            .where(CashEntry.cash_register_id == register_id)
            .where(CashEntry.amount == amount)
            .where(CashEntry.entry_date == entry_date)
            .where(CashEntry.is_cancelled == False)
            .order_by(CashEntry.created_at.desc())
            .limit(5)
        )

        result = await db.execute(query)
        candidates = result.scalars().all()

        if not candidates:
            return None

        # Exakte Belegnummer-Match
        if reference_number:
            for entry in candidates:
                if entry.reference_number == reference_number:
                    return entry

        # Fuzzy Beschreibungs-Match (einfache Implementierung)
        description_lower = description.lower().strip()
        for entry in candidates:
            existing_desc = (entry.description or "").lower().strip()
            # Exakte Übereinstimmung oder Teilstring
            if description_lower == existing_desc:
                return entry
            # Mindestens 80% der Woerter muessen uebereinstimmen
            words_new = set(description_lower.split())
            words_existing = set(existing_desc.split())
            if len(words_new) > 0 and len(words_existing) > 0:
                overlap = len(words_new & words_existing)
                max_words = max(len(words_new), len(words_existing))
                if overlap / max_words > 0.8:
                    return entry

        return None

    async def _get_accounts(
        self,
        db: AsyncSession,
        entry_type: CashEntryType,
        category_id: Optional[UUID],
        company_id: Optional[UUID] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Ermittelt Buchungskonten basierend auf Kontenrahmen.

        Args:
            db: Datenbank-Session
            entry_type: Buchungstyp
            category_id: Kategorie-ID
            company_id: Firmen-ID (fuer SKR-Ermittlung)

        Returns:
            Tuple (Soll-Konto, Haben-Konto)
        """
        # Kontenrahmen ermitteln (SKR03 oder SKR04)
        kontenrahmen = "SKR03"  # Default
        if company_id:
            result = await db.execute(
                select(Company.kontenrahmen)
                .where(Company.id == company_id)
            )
            company_kontenrahmen = result.scalar_one_or_none()
            if company_kontenrahmen:
                kontenrahmen = company_kontenrahmen

        # Kasse-Konto dynamisch: 1000 (SKR03) / 1600 (SKR04)
        cash_account = "1600" if kontenrahmen == "SKR04" else "1000"

        if category_id:
            result = await db.execute(
                select(CashCategory)
                .where(CashCategory.id == category_id)
            )
            category = result.scalar_one_or_none()
            if category:
                # SKR04-Konto bevorzugen wenn SKR04 aktiv und vorhanden
                if kontenrahmen == "SKR04" and category.skr04_account:
                    expense_account = category.skr04_account
                else:
                    expense_account = category.skr03_account

                if entry_type.value in ["income", "deposit", "refund_received", "difference_plus"]:
                    return cash_account, expense_account
                else:
                    return expense_account, cash_account

        return None, None

    def _calculate_count_total(self, data: CashCountCreate) -> Decimal:
        """Berechnet Ist-Bestand aus Zählung.

        Args:
            data: Zähldaten

        Returns:
            Gesamtbetrag
        """
        coins = (
            data.coins_1_cent * Decimal("0.01") +
            data.coins_2_cent * Decimal("0.02") +
            data.coins_5_cent * Decimal("0.05") +
            data.coins_10_cent * Decimal("0.10") +
            data.coins_20_cent * Decimal("0.20") +
            data.coins_50_cent * Decimal("0.50") +
            data.coins_1_euro * Decimal("1.00") +
            data.coins_2_euro * Decimal("2.00")
        )
        notes = (
            data.notes_5_euro * 5 +
            data.notes_10_euro * 10 +
            data.notes_20_euro * 20 +
            data.notes_50_euro * 50 +
            data.notes_100_euro * 100 +
            data.notes_200_euro * 200 +
            data.notes_500_euro * 500
        )
        return coins + Decimal(str(notes))

    async def _create_opening_entry(
        self,
        db: AsyncSession,
        register: CashRegister,
        amount: Decimal,
        user_id: UUID
    ) -> CashEntry:
        """Erstellt Eröffnungsbuchung.

        Args:
            db: Datenbank-Session
            register: Kasse
            amount: Anfangsbestand
            user_id: Benutzer-ID

        Returns:
            Eröffnungsbuchung
        """
        fiscal_year = date.today().year
        entry = CashEntry(
            company_id=register.company_id,
            cash_register_id=register.id,
            entry_number=1,
            fiscal_year=fiscal_year,
            entry_date=date.today(),
            value_date=date.today(),
            amount=amount,
            currency=register.currency,
            balance_after=amount,
            entry_type=CashEntryType.OPENING.value,
            description=f"Eröffnungsbuchung Kasse '{register.name}'",
            is_tax_deductible=False,
            deductible_percentage=0,
            created_by_id=user_id,
        )
        db.add(entry)
        await db.flush()
        return entry


# Singleton-Instanz
cash_service = CashService()

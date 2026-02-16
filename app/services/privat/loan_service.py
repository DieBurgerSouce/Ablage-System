"""Service für die Verwaltung von Krediten im Privat-Modul."""

import uuid
from datetime import datetime, date
from app.core.datetime_utils import utc_now
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import PrivatLoan
from app.db.schemas import (
    PrivatLoanCreate,
    PrivatLoanUpdate,
    PrivatLoanResponse,
    PrivatLoanWithStats,
    PrivatLoanListResponse,
    LoanType,
)

logger = structlog.get_logger(__name__)


class PrivatLoanService:
    """Service für Kreditverwaltung."""

    async def create(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatLoanCreate,
    ) -> PrivatLoan:
        """Erstellt einen neuen Kredit.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Kredit-Daten

        Returns:
            Erstellter Kredit
        """
        loan = PrivatLoan(
            id=uuid.uuid4(),
            space_id=space_id,
            name=data.name,
            loan_type=data.loan_type.value if isinstance(data.loan_type, LoanType) else data.loan_type,
            lender=data.lender,
            principal_amount=data.principal_amount,
            current_balance=data.current_balance,
            interest_rate=data.interest_rate,
            monthly_payment=data.monthly_payment,
            start_date=data.start_date,
            end_date=data.end_date,
            next_payment_date=data.next_payment_date,
            account_number=data.account_number,
            notes=data.notes,
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(loan)
        await db.commit()
        await db.refresh(loan)

        logger.info(
            "privat_loan_created",
            loan_id=str(loan.id),
            space_id=str(space_id),
            loan_type=loan.loan_type,
        )

        return loan

    async def get_by_id(
        self,
        db: AsyncSession,
        loan_id: uuid.UUID,
    ) -> Optional[PrivatLoan]:
        """Holt einen Kredit nach ID.

        WARNUNG: Diese Methode führt KEINEN Access-Check durch!
        Für API-Aufrufe IMMER get_by_id_with_access_check() verwenden!
        """
        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_access_check(
        self,
        db: AsyncSession,
        loan_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatLoan]:
        """Holt einen Kredit nach ID MIT Access-Check.

        SECURITY: Diese Methode ist IDOR-sicher:
        - Access-Check erfolgt VOR Rückgabe des Kredits
        - Gibt None zurück wenn nicht existiert ODER kein Zugriff
        - Keine Information Disclosure über Existenz fremder Ressourcen
        """
        from app.db.models import PrivatSpace, PrivatSpaceAccess

        # SECURITY: Hole Kredit MIT Space in EINER Query
        result = await db.execute(
            select(PrivatLoan, PrivatSpace)
            .join(PrivatSpace, PrivatLoan.space_id == PrivatSpace.id)
            .where(PrivatLoan.id == loan_id)
        )
        row = result.first()

        if not row:
            return None

        loan, space = row

        # Owner hat immer vollen Zugriff
        if space.owner_id == requesting_user_id:
            return loan

        # Prüfe explizite Berechtigung - SECURITY: mit expires_at Validierung!
        from datetime import timezone
        now = datetime.now(timezone.utc)
        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space.id,
                PrivatSpaceAccess.user_id == requesting_user_id,
                # SECURITY: expires_at check - abgelaufene Zugriffe ignorieren
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            logger.warning(
                "idor_loan_attempt_blocked",
                loan_id=str(loan_id),
                user_id=str(requesting_user_id),
                space_id=str(space.id)
            )
            return None

        return loan

    async def list_loans(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        loan_type: Optional[LoanType] = None,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> PrivatLoanListResponse:
        """Listet alle Kredite eines Spaces."""
        conditions = [PrivatLoan.space_id == space_id]

        if active_only:
            conditions.append(PrivatLoan.is_active == True)

        if loan_type:
            conditions.append(PrivatLoan.loan_type == loan_type.value)

        # Count
        count_result = await db.execute(
            select(func.count(PrivatLoan.id)).where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatLoan)
            .where(and_(*conditions))
            .order_by(PrivatLoan.name)
            .offset(offset)
            .limit(page_size)
        )
        loans = result.scalars().all()

        # Mit Statistiken anreichern
        items = []
        for loan in loans:
            stats = self._calculate_loan_stats(loan)
            items.append(PrivatLoanWithStats(
                id=loan.id,
                space_id=loan.space_id,
                name=loan.name,
                loan_type=LoanType(loan.loan_type),
                lender=loan.lender,
                principal_amount=loan.principal_amount,
                current_balance=loan.current_balance,
                interest_rate=loan.interest_rate,
                monthly_payment=loan.monthly_payment,
                start_date=loan.start_date,
                end_date=loan.end_date,
                next_payment_date=loan.next_payment_date,
                account_number=loan.account_number,
                notes=loan.notes,
                is_active=loan.is_active,
                created_at=loan.created_at,
                updated_at=loan.updated_at,
                **stats,
            ))

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return PrivatLoanListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def _calculate_loan_stats(
        self,
        loan: PrivatLoan,
    ) -> dict:
        """Berechnet Statistiken für einen Kredit."""
        today = date.today()

        # Bereits bezahlt (geschätzt)
        total_paid = loan.principal_amount - loan.current_balance
        if total_paid < 0:
            total_paid = Decimal("0.00")

        # Geschätzte Zinsen (vereinfacht)
        # Tatsaechliche Berechnung waere komplexer (Annuitaet)
        months_since_start = 0
        if loan.start_date:
            months_since_start = (
                (today.year - loan.start_date.year) * 12 +
                (today.month - loan.start_date.month)
            )

        total_payments = loan.monthly_payment * months_since_start if months_since_start > 0 else Decimal("0")
        total_interest_paid = total_payments - total_paid if total_payments > total_paid else Decimal("0")

        # Verbleibende Monate
        remaining_months = None
        payoff_date = None

        if loan.monthly_payment > 0 and loan.current_balance > 0:
            # Vereinfachte Berechnung ohne Zinseszins
            remaining_months = int(loan.current_balance / loan.monthly_payment) + 1

            from datetime import timedelta
            payoff_date = date(
                today.year + (today.month + remaining_months - 1) // 12,
                ((today.month + remaining_months - 1) % 12) + 1,
                min(today.day, 28)
            )

        return {
            "total_paid": total_paid,
            "total_interest_paid": total_interest_paid,
            "remaining_months": remaining_months,
            "payoff_date": payoff_date,
        }

    async def update(
        self,
        db: AsyncSession,
        loan_id: uuid.UUID,
        data: PrivatLoanUpdate,
    ) -> Optional[PrivatLoan]:
        """Aktualisiert einen Kredit.

        SECURITY FIX 22-9: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock könnte:
        - Lost Updates bei gleichzeitigen Änderungen auftreten
        - Inkonsistente Kreditdaten entstehen
        """
        # SECURITY FIX 22-9: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatLoan)
            .where(PrivatLoan.id == loan_id)
            .with_for_update()  # ROW LOCK - kritisch für Finanzdaten!
        )
        loan = result.scalar_one_or_none()
        if not loan:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "loan_type" and value:
                value = value.value if isinstance(value, LoanType) else value
            setattr(loan, key, value)

        loan.updated_at = utc_now()

        await db.commit()
        await db.refresh(loan)

        logger.info(
            "privat_loan_updated",
            loan_id=str(loan_id),
        )

        return loan

    async def record_payment(
        self,
        db: AsyncSession,
        loan_id: uuid.UUID,
        amount: Decimal,
        payment_date: Optional[date] = None,
    ) -> Optional[PrivatLoan]:
        """Erfasst eine Kreditrate.

        SECURITY FIX 21-1: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Zahlungen zu verhindern. Ohne Row Lock könnte:
        - Double-Spending auftreten
        - Zahlungen verloren gehen
        - current_balance korrupt werden

        Args:
            db: Datenbank-Session
            loan_id: Kredit-ID
            amount: Zahlungsbetrag
            payment_date: Optional Zahlungsdatum

        Returns:
            Aktualisierter Kredit
        """
        # SECURITY FIX 21-1: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatLoan)
            .where(PrivatLoan.id == loan_id)
            .with_for_update()  # ROW LOCK - kritisch für Finanzdaten!
        )
        loan = result.scalar_one_or_none()
        if not loan:
            return None

        # Reduziere Restschuld
        loan.current_balance = max(Decimal("0"), loan.current_balance - amount)

        # Setze nächstes Zahlungsdatum
        if payment_date is None:
            payment_date = date.today()

        from datetime import timedelta
        next_month = payment_date.replace(day=1) + timedelta(days=32)
        loan.next_payment_date = next_month.replace(day=payment_date.day if payment_date.day <= 28 else 28)

        # Deaktiviere wenn abbezahlt
        if loan.current_balance == 0:
            loan.is_active = False

        loan.updated_at = utc_now()

        await db.commit()
        await db.refresh(loan)

        logger.info(
            "privat_loan_payment_recorded",
            loan_id=str(loan_id),
            amount=str(amount),
            new_balance=str(loan.current_balance),
        )

        return loan

    async def delete(
        self,
        db: AsyncSession,
        loan_id: uuid.UUID,
        soft_delete: bool = True,
    ) -> bool:
        """Löscht einen Kredit.

        SECURITY FIX 22-10: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern. Ohne Row Lock könnte:
        - Double-Delete auftreten
        - Inkonsistente Zustaende entstehen
        """
        # SECURITY FIX 22-10: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatLoan)
            .where(PrivatLoan.id == loan_id)
            .with_for_update()  # ROW LOCK - kritisch für Datenintegrität!
        )
        loan = result.scalar_one_or_none()
        if not loan:
            return False

        if soft_delete:
            loan.is_active = False
            loan.updated_at = utc_now()
            await db.commit()
        else:
            await db.delete(loan)
            await db.commit()

        logger.info(
            "privat_loan_deleted",
            loan_id=str(loan_id),
            soft_delete=soft_delete,
        )

        return True

    async def get_total_balance(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> Decimal:
        """Berechnet die gesamte Restschuld aller Kredite."""
        result = await db.execute(
            select(func.coalesce(func.sum(PrivatLoan.current_balance), 0))
            .where(
                PrivatLoan.space_id == space_id,
                PrivatLoan.is_active == True,
            )
        )
        return Decimal(str(result.scalar() or 0))

    async def get_monthly_payments(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> Decimal:
        """Berechnet die gesamten monatlichen Kreditraten."""
        result = await db.execute(
            select(func.coalesce(func.sum(PrivatLoan.monthly_payment), 0))
            .where(
                PrivatLoan.space_id == space_id,
                PrivatLoan.is_active == True,
            )
        )
        return Decimal(str(result.scalar() or 0))

    async def get_upcoming_payments(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        days_ahead: int = 7,
    ) -> List[PrivatLoanWithStats]:
        """Holt Kredite mit bevorstehenden Zahlungen."""
        from datetime import timedelta
        target_date = date.today() + timedelta(days=days_ahead)

        result = await db.execute(
            select(PrivatLoan)
            .where(
                PrivatLoan.space_id == space_id,
                PrivatLoan.is_active == True,
                PrivatLoan.next_payment_date.isnot(None),
                PrivatLoan.next_payment_date <= target_date,
            )
            .order_by(PrivatLoan.next_payment_date)
        )

        loans = result.scalars().all()
        return [
            PrivatLoanWithStats(
                id=loan.id,
                space_id=loan.space_id,
                name=loan.name,
                loan_type=LoanType(loan.loan_type),
                lender=loan.lender,
                principal_amount=loan.principal_amount,
                current_balance=loan.current_balance,
                interest_rate=loan.interest_rate,
                monthly_payment=loan.monthly_payment,
                start_date=loan.start_date,
                end_date=loan.end_date,
                next_payment_date=loan.next_payment_date,
                account_number=loan.account_number,
                notes=loan.notes,
                is_active=loan.is_active,
                created_at=loan.created_at,
                updated_at=loan.updated_at,
                **self._calculate_loan_stats(loan),
            )
            for loan in loans
        ]

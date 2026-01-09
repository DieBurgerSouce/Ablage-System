"""Service fuer die Verwaltung von Geldanlagen im Privat-Modul."""

import uuid
from datetime import datetime, date
from app.core.datetime_utils import utc_now
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import PrivatInvestment
from app.db.schemas import (
    PrivatInvestmentCreate,
    PrivatInvestmentUpdate,
    PrivatInvestmentResponse,
    PrivatInvestmentWithStats,
    PrivatInvestmentListResponse,
    InvestmentType,
)

logger = structlog.get_logger(__name__)


class PrivatInvestmentService:
    """Service fuer Geldanlagen-Verwaltung."""

    async def create(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatInvestmentCreate,
    ) -> PrivatInvestment:
        """Erstellt eine neue Geldanlage.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Anlage-Daten

        Returns:
            Erstellte Anlage
        """
        investment = PrivatInvestment(
            id=uuid.uuid4(),
            space_id=space_id,
            name=data.name,
            investment_type=data.investment_type.value if isinstance(data.investment_type, InvestmentType) else data.investment_type,
            institution=data.institution,
            account_number=data.account_number,
            initial_amount=data.initial_amount,
            current_value=data.current_value,
            interest_rate=data.interest_rate,
            start_date=data.start_date,
            maturity_date=data.maturity_date,
            is_taxable=data.is_taxable,
            notes=data.notes,
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(investment)
        await db.commit()
        await db.refresh(investment)

        logger.info(
            "privat_investment_created",
            investment_id=str(investment.id),
            space_id=str(space_id),
            investment_type=investment.investment_type,
        )

        return investment

    async def get_by_id(
        self,
        db: AsyncSession,
        investment_id: uuid.UUID,
    ) -> Optional[PrivatInvestment]:
        """Holt eine Anlage nach ID.

        WARNUNG: Diese Methode fuehrt KEINEN Access-Check durch!
        Fuer API-Aufrufe IMMER get_by_id_with_access_check() verwenden!
        """
        result = await db.execute(
            select(PrivatInvestment).where(PrivatInvestment.id == investment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_access_check(
        self,
        db: AsyncSession,
        investment_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatInvestment]:
        """Holt eine Anlage nach ID MIT Access-Check.

        SECURITY: Diese Methode ist IDOR-sicher:
        - Access-Check erfolgt VOR Rueckgabe der Anlage
        - Gibt None zurueck wenn nicht existiert ODER kein Zugriff
        - Keine Information Disclosure ueber Existenz fremder Ressourcen
        """
        from app.db.models import PrivatSpace, PrivatSpaceAccess

        # SECURITY: Hole Anlage MIT Space in EINER Query
        result = await db.execute(
            select(PrivatInvestment, PrivatSpace)
            .join(PrivatSpace, PrivatInvestment.space_id == PrivatSpace.id)
            .where(PrivatInvestment.id == investment_id)
        )
        row = result.first()

        if not row:
            return None

        investment, space = row

        # Owner hat immer vollen Zugriff
        if space.owner_id == requesting_user_id:
            return investment

        # Pruefe explizite Berechtigung - SECURITY: mit expires_at Validierung!
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
                "idor_investment_attempt_blocked",
                investment_id=str(investment_id),
                user_id=str(requesting_user_id),
                space_id=str(space.id)
            )
            return None

        return investment

    async def list_investments(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        investment_type: Optional[InvestmentType] = None,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> PrivatInvestmentListResponse:
        """Listet alle Anlagen eines Spaces."""
        conditions = [PrivatInvestment.space_id == space_id]

        if active_only:
            conditions.append(PrivatInvestment.is_active == True)

        if investment_type:
            conditions.append(
                PrivatInvestment.investment_type == investment_type.value
            )

        # Count
        count_result = await db.execute(
            select(func.count(PrivatInvestment.id)).where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatInvestment)
            .where(and_(*conditions))
            .order_by(PrivatInvestment.name)
            .offset(offset)
            .limit(page_size)
        )
        investments = result.scalars().all()

        # Mit Statistiken anreichern
        items = []
        for inv in investments:
            stats = self._calculate_investment_stats(inv)
            items.append(PrivatInvestmentWithStats(
                id=inv.id,
                space_id=inv.space_id,
                name=inv.name,
                investment_type=InvestmentType(inv.investment_type),
                institution=inv.institution,
                account_number=inv.account_number,
                initial_amount=inv.initial_amount,
                current_value=inv.current_value,
                interest_rate=inv.interest_rate,
                start_date=inv.start_date,
                maturity_date=inv.maturity_date,
                is_taxable=inv.is_taxable,
                notes=inv.notes,
                is_active=inv.is_active,
                created_at=inv.created_at,
                updated_at=inv.updated_at,
                **stats,
            ))

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return PrivatInvestmentListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def _calculate_investment_stats(
        self,
        investment: PrivatInvestment,
    ) -> dict:
        """Berechnet Statistiken fuer eine Anlage."""
        # Gesamtrendite
        total_return = investment.current_value - investment.initial_amount

        # Rendite in Prozent
        return_percentage = Decimal("0.00")
        if investment.initial_amount > 0:
            return_percentage = (total_return / investment.initial_amount) * 100

        # Jaehrliche Rendite (vereinfacht)
        annual_return = None
        if investment.start_date:
            today = date.today()
            days_held = (today - investment.start_date).days
            if days_held > 0:
                # Annualisierte Rendite
                years_held = Decimal(str(days_held)) / Decimal("365")
                if years_held > 0:
                    annual_return = return_percentage / years_held

        return {
            "total_return": total_return,
            "return_percentage": return_percentage.quantize(Decimal("0.01")),
            "annual_return": annual_return.quantize(Decimal("0.01")) if annual_return else None,
        }

    async def update(
        self,
        db: AsyncSession,
        investment_id: uuid.UUID,
        data: PrivatInvestmentUpdate,
    ) -> Optional[PrivatInvestment]:
        """Aktualisiert eine Anlage.

        SECURITY FIX 22-11: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock koennte:
        - Lost Updates bei gleichzeitigen Aenderungen auftreten
        - Inkonsistente Anlagedaten entstehen
        """
        # SECURITY FIX 22-11: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatInvestment)
            .where(PrivatInvestment.id == investment_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Finanzdaten!
        )
        investment = result.scalar_one_or_none()
        if not investment:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "investment_type" and value:
                value = value.value if isinstance(value, InvestmentType) else value
            setattr(investment, key, value)

        investment.updated_at = utc_now()

        await db.commit()
        await db.refresh(investment)

        logger.info(
            "privat_investment_updated",
            investment_id=str(investment_id),
        )

        return investment

    async def update_value(
        self,
        db: AsyncSession,
        investment_id: uuid.UUID,
        new_value: Decimal,
    ) -> Optional[PrivatInvestment]:
        """Aktualisiert den aktuellen Wert einer Anlage.

        SECURITY FIX 21-2: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Wertaktualisierungen zu verhindern. Ohne Row Lock koennte:
        - Lost Updates auftreten
        - Inkonsistente Werte entstehen
        - Performance-Berechnungen falsch werden

        Args:
            db: Datenbank-Session
            investment_id: Anlage-ID
            new_value: Neuer aktueller Wert

        Returns:
            Aktualisierte Anlage
        """
        # SECURITY FIX 21-2: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatInvestment)
            .where(PrivatInvestment.id == investment_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Finanzdaten!
        )
        investment = result.scalar_one_or_none()
        if not investment:
            return None

        investment.current_value = new_value
        investment.updated_at = utc_now()

        await db.commit()
        await db.refresh(investment)

        logger.info(
            "privat_investment_value_updated",
            investment_id=str(investment_id),
            new_value=str(new_value),
        )

        return investment

    async def delete(
        self,
        db: AsyncSession,
        investment_id: uuid.UUID,
        soft_delete: bool = True,
    ) -> bool:
        """Loescht eine Anlage.

        SECURITY FIX 22-12: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern. Ohne Row Lock koennte:
        - Double-Delete auftreten
        - Inkonsistente Zustaende entstehen
        """
        # SECURITY FIX 22-12: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatInvestment)
            .where(PrivatInvestment.id == investment_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Datenintegritaet!
        )
        investment = result.scalar_one_or_none()
        if not investment:
            return False

        if soft_delete:
            investment.is_active = False
            investment.updated_at = utc_now()
            await db.commit()
        else:
            await db.delete(investment)
            await db.commit()

        return True

    async def get_total_value(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> Decimal:
        """Berechnet den Gesamtwert aller Anlagen."""
        result = await db.execute(
            select(func.coalesce(func.sum(PrivatInvestment.current_value), 0))
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.is_active == True,
            )
        )
        return Decimal(str(result.scalar() or 0))

    async def get_total_return(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> dict:
        """Berechnet die Gesamtrendite aller Anlagen."""
        result = await db.execute(
            select(
                func.coalesce(func.sum(PrivatInvestment.purchase_value), 0).label("total_invested"),
                func.coalesce(func.sum(PrivatInvestment.current_value), 0).label("total_value"),
            )
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.is_active == True,
            )
        )

        row = result.one()
        total_invested = Decimal(str(row.total_invested))
        total_value = Decimal(str(row.total_value))
        total_return = total_value - total_invested

        return_percentage = Decimal("0.00")
        if total_invested > 0:
            return_percentage = (total_return / total_invested) * 100

        return {
            "total_invested": total_invested,
            "total_value": total_value,
            "total_return": total_return,
            "return_percentage": return_percentage.quantize(Decimal("0.01")),
        }

    async def get_maturing_investments(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        days_ahead: int = 30,
    ) -> List[PrivatInvestmentWithStats]:
        """Holt Anlagen die bald faellig werden."""
        from datetime import timedelta
        target_date = date.today() + timedelta(days=days_ahead)

        result = await db.execute(
            select(PrivatInvestment)
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.is_active == True,
                PrivatInvestment.maturity_date.isnot(None),
                PrivatInvestment.maturity_date <= target_date,
                PrivatInvestment.maturity_date >= date.today(),
            )
            .order_by(PrivatInvestment.maturity_date)
        )

        investments = result.scalars().all()
        return [
            PrivatInvestmentWithStats(
                id=inv.id,
                space_id=inv.space_id,
                name=inv.name,
                investment_type=InvestmentType(inv.investment_type),
                institution=inv.institution,
                account_number=inv.account_number,
                initial_amount=inv.initial_amount,
                current_value=inv.current_value,
                interest_rate=inv.interest_rate,
                start_date=inv.start_date,
                maturity_date=inv.maturity_date,
                is_taxable=inv.is_taxable,
                notes=inv.notes,
                is_active=inv.is_active,
                created_at=inv.created_at,
                updated_at=inv.updated_at,
                **self._calculate_investment_stats(inv),
            )
            for inv in investments
        ]

    async def get_portfolio_breakdown(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> dict:
        """Berechnet die Portfolio-Verteilung nach Anlagetyp."""
        result = await db.execute(
            select(
                PrivatInvestment.investment_type,
                func.coalesce(func.sum(PrivatInvestment.current_value), 0).label("value"),
            )
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.is_active == True,
            )
            .group_by(PrivatInvestment.investment_type)
        )

        breakdown = {}
        total = Decimal("0")

        for row in result:
            value = Decimal(str(row.value))
            breakdown[row.investment_type] = value
            total += value

        # Prozentuale Verteilung hinzufuegen
        percentages = {}
        for inv_type, value in breakdown.items():
            percentage = (value / total * 100) if total > 0 else Decimal("0")
            percentages[inv_type] = {
                "value": value,
                "percentage": percentage.quantize(Decimal("0.1")),
            }

        return {
            "breakdown": percentages,
            "total": total,
        }

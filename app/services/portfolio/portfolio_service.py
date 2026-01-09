"""Portfolio Service fuer Vermoegensuebersicht.

DEPRECATED: Nutze stattdessen app.services.privat.portfolio_service.PortfolioService

Dieser Service wurde zugunsten des Privat-Modul PortfolioService deprecated.
Er bleibt fuer Rueckwaertskompatibilitaet erhalten, aber alle neuen Features
sollten den Privat-Service verwenden.

Enterprise Feature: Erstellt und verwaltet Portfolio-Snapshots mit:
- Vermoegenswerte aggregieren
- Verbindlichkeiten berechnen
- Nettovermoegen tracken
- Asset Allocation analysieren
- Historisches Tracking

Multi-Tenant Security: Alle Queries filtern nach space_id!
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PortfolioSnapshot as PortfolioSnapshotModel,
    PrivatProperty,
    PrivatVehicle,
    PrivatLoan,
    PrivatInvestment,
    PrivatBankAccount,
)

logger = structlog.get_logger(__name__)


@dataclass
class PortfolioSummary:
    """Zusammenfassung der Portfolio-Daten."""

    snapshot_date: date

    # Vermoegenswerte
    total_real_estate: Decimal
    total_vehicles: Decimal
    total_investments: Decimal
    total_cash: Decimal
    total_other_assets: Decimal

    # Aggregierte Werte
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal

    # Veraenderungen
    net_worth_change_absolute: Optional[Decimal]
    net_worth_change_percent: Optional[Decimal]

    # Kennzahlen
    debt_to_assets_ratio: Decimal
    liquidity_ratio: Decimal

    # Allocation
    asset_allocation: dict[str, Decimal]


class PortfolioService:
    """Service fuer Portfolio-Management und Snapshots.

    Aggregiert alle Vermoegenswerte und Verbindlichkeiten
    zu einer Gesamtuebersicht mit historischem Tracking.

    WICHTIG: Multi-Tenant Security - Alle Queries filtern nach space_id!
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def create_snapshot(self, space_id: UUID) -> PortfolioSummary:
        """Erstellt einen neuen Portfolio-Snapshot.

        Args:
            space_id: UUID des Privat-Space (Multi-Tenant Security!)

        Returns:
            PortfolioSummary mit allen aggregierten Werten
        """
        logger.info(
            "portfolio_snapshot_creation_started",
            space_id=str(space_id),
        )

        # Daten laden (mit Multi-Tenant Security!)
        properties = await self._get_properties(space_id)
        vehicles = await self._get_vehicles(space_id)
        investments = await self._get_investments(space_id)
        cash_accounts = await self._get_cash_accounts(space_id)
        loans = await self._get_loans(space_id)

        # Summen berechnen
        total_real_estate = self._calc_total_real_estate(properties)
        total_vehicles = self._calc_total_vehicles(vehicles)
        total_investments = self._calc_total_investments(investments)
        total_cash = self._calc_total_cash(cash_accounts)

        total_assets = total_real_estate + total_vehicles + total_investments + total_cash
        total_mortgages = self._calc_total_mortgages(loans)
        total_other_loans = self._calc_total_other_loans(loans)
        total_liabilities = total_mortgages + total_other_loans
        net_worth = total_assets - total_liabilities

        # Vorheriger Snapshot fuer Vergleich
        previous = await self.get_latest_snapshot(space_id)
        abs_change, pct_change = self._calc_net_worth_change(
            net_worth,
            previous.net_worth if previous else None
        )

        # Asset Allocation
        totals = {
            "real_estate": total_real_estate,
            "vehicles": total_vehicles,
            "investments": total_investments,
            "cash": total_cash,
        }
        allocation = self._calc_asset_allocation(totals, total_assets)

        # In DB speichern
        db_snapshot = PortfolioSnapshotModel(
            space_id=space_id,
            snapshot_date=date.today(),
            total_real_estate=total_real_estate,
            total_vehicles=total_vehicles,
            total_investments=total_investments,
            total_cash=total_cash,
            total_other_assets=Decimal("0"),
            total_mortgages=total_mortgages,
            total_loans=total_other_loans,
            total_other_liabilities=Decimal("0"),
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            net_worth=net_worth,
            net_worth_change_absolute=abs_change,
            net_worth_change_percent=pct_change,
            debt_to_assets_ratio=self._calc_debt_to_assets_ratio(total_liabilities, total_assets),
            liquidity_ratio=self._calc_liquidity_ratio(total_cash, total_liabilities),
            asset_allocation=allocation,
        )

        self.db.add(db_snapshot)
        await self.db.commit()
        await self.db.refresh(db_snapshot)

        logger.info(
            "portfolio_snapshot_created",
            space_id=str(space_id),
            snapshot_id=str(db_snapshot.id),
            net_worth=str(net_worth),
        )

        return PortfolioSummary(
            snapshot_date=date.today(),
            total_real_estate=total_real_estate,
            total_vehicles=total_vehicles,
            total_investments=total_investments,
            total_cash=total_cash,
            total_other_assets=Decimal("0"),
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            net_worth=net_worth,
            net_worth_change_absolute=abs_change,
            net_worth_change_percent=pct_change,
            debt_to_assets_ratio=self._calc_debt_to_assets_ratio(total_liabilities, total_assets),
            liquidity_ratio=self._calc_liquidity_ratio(total_cash, total_liabilities),
            asset_allocation=allocation,
        )

    async def get_latest_snapshot(self, space_id: UUID) -> Optional[PortfolioSnapshotModel]:
        """Laedt den neuesten Snapshot.

        Args:
            space_id: UUID des Privat-Space (Multi-Tenant Security!)

        Returns:
            Der neueste PortfolioSnapshot oder None
        """
        stmt = (
            select(PortfolioSnapshotModel)
            .where(PortfolioSnapshotModel.space_id == space_id)
            .order_by(desc(PortfolioSnapshotModel.snapshot_date))
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_historical_snapshots(
        self,
        space_id: UUID,
        months: int = 12
    ) -> list[PortfolioSnapshotModel]:
        """Laedt historische Snapshots.

        Args:
            space_id: UUID des Privat-Space (Multi-Tenant Security!)
            months: Anzahl Monate zurueck

        Returns:
            Liste von PortfolioSnapshots, neueste zuerst
        """
        cutoff_date = date.today() - timedelta(days=months * 30)

        stmt = (
            select(PortfolioSnapshotModel)
            .where(
                PortfolioSnapshotModel.space_id == space_id,
                PortfolioSnapshotModel.snapshot_date >= cutoff_date,
            )
            .order_by(desc(PortfolioSnapshotModel.snapshot_date))
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_net_worth_trend(
        self,
        space_id: UUID,
        months: int = 12
    ) -> list[tuple[date, Decimal]]:
        """Holt den Nettovermoegen-Trend.

        Args:
            space_id: UUID des Privat-Space
            months: Anzahl Monate

        Returns:
            Liste von (Datum, Nettovermoegen) Tupeln
        """
        snapshots = await self.get_historical_snapshots(space_id, months)
        return [(s.snapshot_date, s.net_worth) for s in reversed(snapshots)]

    # ===== Berechnungsmethoden =====

    def _calc_total_real_estate(self, properties: list[PrivatProperty]) -> Decimal:
        """Summiert alle Immobilienwerte."""
        if not properties:
            return Decimal("0")
        return sum(
            (Decimal(str(p.current_value)) if p.current_value else Decimal("0"))
            for p in properties
        )

    def _calc_total_vehicles(self, vehicles: list[PrivatVehicle]) -> Decimal:
        """Summiert alle Fahrzeugwerte."""
        if not vehicles:
            return Decimal("0")
        return sum(
            (Decimal(str(v.current_estimated_value)) if v.current_estimated_value else Decimal("0"))
            for v in vehicles
        )

    def _calc_total_investments(self, investments: list[PrivatInvestment]) -> Decimal:
        """Summiert alle Anlagewerte."""
        if not investments:
            return Decimal("0")
        return sum(
            (Decimal(str(i.current_value)) if i.current_value else Decimal("0"))
            for i in investments
        )

    def _calc_total_cash(self, accounts: list[PrivatBankAccount]) -> Decimal:
        """Summiert alle Kontoguthaben."""
        if not accounts:
            return Decimal("0")
        return sum(
            (Decimal(str(a.current_balance)) if a.current_balance else Decimal("0"))
            for a in accounts
        )

    def _calc_total_mortgages(self, loans: list[PrivatLoan]) -> Decimal:
        """Summiert alle Hypotheken."""
        if not loans:
            return Decimal("0")
        mortgages = [l for l in loans if l.loan_type and l.loan_type.lower() == 'mortgage']
        return sum(
            (Decimal(str(m.remaining_balance)) if m.remaining_balance else Decimal("0"))
            for m in mortgages
        )

    def _calc_total_other_loans(self, loans: list[PrivatLoan]) -> Decimal:
        """Summiert alle sonstigen Kredite."""
        if not loans:
            return Decimal("0")
        other = [l for l in loans if not l.loan_type or l.loan_type.lower() != 'mortgage']
        return sum(
            (Decimal(str(l.remaining_balance)) if l.remaining_balance else Decimal("0"))
            for l in other
        )

    def _calc_net_worth_change(
        self,
        current: Decimal,
        previous: Optional[Decimal]
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Berechnet die Nettovermoegen-Veraenderung."""
        if previous is None:
            return None, None

        abs_change = current - previous

        if previous == 0:
            pct_change = Decimal("0")
        else:
            pct_change = (abs_change / previous) * 100
            pct_change = pct_change.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return abs_change, pct_change

    def _calc_asset_allocation(
        self,
        totals: dict[str, Decimal],
        total_assets: Decimal
    ) -> dict[str, Decimal]:
        """Berechnet die Asset Allocation in Prozent."""
        if total_assets == 0:
            return {k: Decimal("0") for k in totals}

        allocation = {}
        for asset_type, value in totals.items():
            pct = (value / total_assets) * 100
            allocation[asset_type] = pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return allocation

    def _calc_debt_to_assets_ratio(
        self,
        total_liabilities: Decimal,
        total_assets: Decimal
    ) -> Decimal:
        """Berechnet das Schulden-zu-Vermoegen-Verhaeltnis."""
        if total_assets == 0:
            return Decimal("1.00")  # 100% Risiko

        result = total_liabilities / total_assets
        return result.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def _calc_liquidity_ratio(self, cash: Decimal, total_liabilities: Decimal) -> Decimal:
        """Berechnet die Liquiditaetsquote (Cash / Verbindlichkeiten)."""
        if total_liabilities == 0:
            return Decimal("999.9999")  # Keine Schulden = perfekt

        result = cash / total_liabilities
        return result.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # ===== Daten-Abruf mit Multi-Tenant Security =====

    async def _get_properties(self, space_id: UUID) -> list[PrivatProperty]:
        """Laedt alle Immobilien fuer einen Space.

        Args:
            space_id: UUID des Privat-Space (Multi-Tenant Security!)

        Returns:
            Liste von PrivatProperty Objekten
        """
        stmt = (
            select(PrivatProperty)
            .where(
                PrivatProperty.space_id == space_id,
                PrivatProperty.deleted_at.is_(None),
            )
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_vehicles(self, space_id: UUID) -> list[PrivatVehicle]:
        """Laedt alle Fahrzeuge fuer einen Space.

        Args:
            space_id: UUID des Privat-Space (Multi-Tenant Security!)

        Returns:
            Liste von PrivatVehicle Objekten
        """
        stmt = (
            select(PrivatVehicle)
            .where(
                PrivatVehicle.space_id == space_id,
                PrivatVehicle.deleted_at.is_(None),
                PrivatVehicle.is_active.is_(True),
            )
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_investments(self, space_id: UUID) -> list[PrivatInvestment]:
        """Laedt alle Investments fuer einen Space.

        Args:
            space_id: UUID des Privat-Space (Multi-Tenant Security!)

        Returns:
            Liste von PrivatInvestment Objekten
        """
        stmt = (
            select(PrivatInvestment)
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.deleted_at.is_(None),
            )
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_cash_accounts(self, space_id: UUID) -> list[PrivatBankAccount]:
        """Laedt alle Bankkonten fuer einen Space.

        Args:
            space_id: UUID des Privat-Space (Multi-Tenant Security!)

        Returns:
            Liste von PrivatBankAccount Objekten
        """
        stmt = (
            select(PrivatBankAccount)
            .where(
                PrivatBankAccount.space_id == space_id,
                PrivatBankAccount.deleted_at.is_(None),
                PrivatBankAccount.is_active.is_(True),
            )
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_loans(self, space_id: UUID) -> list[PrivatLoan]:
        """Laedt alle Kredite fuer einen Space.

        Args:
            space_id: UUID des Privat-Space (Multi-Tenant Security!)

        Returns:
            Liste von PrivatLoan Objekten
        """
        stmt = (
            select(PrivatLoan)
            .where(
                PrivatLoan.space_id == space_id,
                PrivatLoan.deleted_at.is_(None),
                PrivatLoan.is_active.is_(True),
            )
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())


async def calculate_all_portfolios_for_space(
    db: AsyncSession,
    space_id: UUID,
) -> PortfolioSummary:
    """Convenience-Funktion zum Erstellen eines Portfolio-Snapshots.

    Args:
        db: Database Session
        space_id: UUID des Privat-Space

    Returns:
        PortfolioSummary
    """
    service = PortfolioService(db)
    return await service.create_snapshot(space_id)

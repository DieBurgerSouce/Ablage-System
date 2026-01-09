"""Portfolio Service fuer Vermoegensueberblick und Snapshots.

Enterprise Feature: Automatisierte Vermoegensverwaltung mit:
- Monatliche Portfolio-Snapshots
- Asset Allocation Tracking
- Vermoegensentwicklung ueber Zeit
- Net Worth Berechnung
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Sequence, TypedDict
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PortfolioSnapshot,
    PrivatInvestment,
    PrivatLoan,
    PrivatProperty,
    PrivatSpace,
    PrivatVehicle,
)

logger = logging.getLogger(__name__)


class NetWorthTrendItem(TypedDict):
    """Typedefinition fuer Net Worth Trend Datenpunkt."""
    date: str
    net_worth: float
    total_assets: float
    total_liabilities: float


@dataclass
class AssetSummary:
    """Zusammenfassung aller Vermoegenswerte."""

    total_real_estate: Decimal = Decimal("0")
    total_vehicles: Decimal = Decimal("0")
    total_investments: Decimal = Decimal("0")
    total_cash: Decimal = Decimal("0")
    total_other_assets: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        """Gesamtwert aller Vermoegenswerte."""
        return (
            self.total_real_estate
            + self.total_vehicles
            + self.total_investments
            + self.total_cash
            + self.total_other_assets
        )


@dataclass
class LiabilitySummary:
    """Zusammenfassung aller Verbindlichkeiten."""

    total_mortgages: Decimal = Decimal("0")
    total_loans: Decimal = Decimal("0")
    total_other_liabilities: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        """Gesamtsumme aller Verbindlichkeiten."""
        return self.total_mortgages + self.total_loans + self.total_other_liabilities


@dataclass
class PortfolioAnalysis:
    """Vollstaendige Portfolio-Analyse."""

    assets: AssetSummary
    liabilities: LiabilitySummary
    net_worth: Decimal = Decimal("0")
    debt_to_assets_ratio: Decimal = Decimal("0")
    liquidity_ratio: Decimal = Decimal("0")
    asset_allocation: dict[str, float] = field(default_factory=dict)

    # Veraenderungen
    net_worth_change_absolute: Optional[Decimal] = None
    net_worth_change_percent: Optional[Decimal] = None


class PortfolioService:
    """Service fuer Portfolio-Management und Snapshots.

    Berechnet aggregierte Vermoegensueberblicke und erstellt
    monatliche Snapshots fuer historische Analyse.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Portfolio Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def calculate_current_portfolio(
        self, space_id: UUID
    ) -> PortfolioAnalysis:
        """Berechnet die aktuelle Vermoegensaufteilung fuer einen Space.

        Args:
            space_id: ID des Privat-Space

        Returns:
            PortfolioAnalysis mit allen Vermoegenswerten und Kennzahlen
        """
        # Assets berechnen
        assets = await self._calculate_assets(space_id)

        # Verbindlichkeiten berechnen
        liabilities = await self._calculate_liabilities(space_id)

        # Net Worth
        net_worth = assets.total - liabilities.total

        # Kennzahlen
        debt_to_assets = Decimal("0")
        if assets.total > 0:
            debt_to_assets = liabilities.total / assets.total

        liquidity_ratio = Decimal("0")
        if liabilities.total > 0:
            liquidity_ratio = assets.total_cash / liabilities.total

        # Asset Allocation (Prozent)
        allocation = {}
        if assets.total > 0:
            allocation = {
                "real_estate": float(assets.total_real_estate / assets.total * 100),
                "vehicles": float(assets.total_vehicles / assets.total * 100),
                "investments": float(assets.total_investments / assets.total * 100),
                "cash": float(assets.total_cash / assets.total * 100),
                "other": float(assets.total_other_assets / assets.total * 100),
            }

        # Vormonatsvergleich
        previous_snapshot = await self._get_previous_snapshot(space_id)
        change_absolute = None
        change_percent = None

        if previous_snapshot:
            change_absolute = net_worth - previous_snapshot.net_worth
            if previous_snapshot.net_worth and previous_snapshot.net_worth != 0:
                change_percent = (
                    change_absolute / previous_snapshot.net_worth * 100
                )

        return PortfolioAnalysis(
            assets=assets,
            liabilities=liabilities,
            net_worth=net_worth,
            debt_to_assets_ratio=debt_to_assets,
            liquidity_ratio=liquidity_ratio,
            asset_allocation=allocation,
            net_worth_change_absolute=change_absolute,
            net_worth_change_percent=change_percent,
        )

    async def _calculate_assets(self, space_id: UUID) -> AssetSummary:
        """Berechnet alle Vermoegenswerte eines Spaces.

        Args:
            space_id: ID des Privat-Space

        Returns:
            AssetSummary mit allen Kategorien
        """
        summary = AssetSummary()

        # Immobilien
        result = await self.db.execute(
            select(func.coalesce(func.sum(PrivatProperty.current_value), 0)).where(
                and_(
                    PrivatProperty.space_id == space_id,
                    PrivatProperty.deleted_at.is_(None),
                )
            )
        )
        summary.total_real_estate = Decimal(str(result.scalar() or 0))

        # Fahrzeuge
        result = await self.db.execute(
            select(func.coalesce(func.sum(PrivatVehicle.current_value), 0)).where(
                and_(
                    PrivatVehicle.space_id == space_id,
                    PrivatVehicle.deleted_at.is_(None),
                )
            )
        )
        summary.total_vehicles = Decimal(str(result.scalar() or 0))

        # Investments
        result = await self.db.execute(
            select(func.coalesce(func.sum(PrivatInvestment.current_value), 0)).where(
                and_(
                    PrivatInvestment.space_id == space_id,
                    PrivatInvestment.deleted_at.is_(None),
                )
            )
        )
        summary.total_investments = Decimal(str(result.scalar() or 0))

        # Cash-Konten: Investments vom Typ "cash", "savings", "checking", etc.
        # Diese werden als Bargeld/Bankguthaben gezaehlt
        cash_types = ["cash", "savings", "savings_account", "checking",
                      "checking_account", "money_market", "term_deposit",
                      "festgeld", "tagesgeld", "girokonto"]

        result = await self.db.execute(
            select(func.coalesce(func.sum(PrivatInvestment.current_value), 0)).where(
                and_(
                    PrivatInvestment.space_id == space_id,
                    PrivatInvestment.deleted_at.is_(None),
                    PrivatInvestment.is_active.is_(True),
                    func.lower(PrivatInvestment.investment_type).in_(cash_types),
                )
            )
        )
        summary.total_cash = Decimal(str(result.scalar() or 0))

        # Cash-Summe von Investments abziehen um Doppelzaehlung zu vermeiden
        summary.total_investments = summary.total_investments - summary.total_cash

        return summary

    async def _calculate_liabilities(self, space_id: UUID) -> LiabilitySummary:
        """Berechnet alle Verbindlichkeiten eines Spaces.

        Args:
            space_id: ID des Privat-Space

        Returns:
            LiabilitySummary mit allen Kategorien
        """
        summary = LiabilitySummary()

        # Alle Kredite nach Typ gruppieren
        result = await self.db.execute(
            select(
                PrivatLoan.loan_type,
                func.coalesce(func.sum(PrivatLoan.current_balance), 0),
            )
            .where(
                and_(
                    PrivatLoan.space_id == space_id,
                    PrivatLoan.deleted_at.is_(None),
                    PrivatLoan.status != "completed",
                )
            )
            .group_by(PrivatLoan.loan_type)
        )

        for loan_type, total in result.all():
            amount = Decimal(str(total or 0))
            if loan_type in ("mortgage", "hypothek"):
                summary.total_mortgages += amount
            else:
                summary.total_loans += amount

        return summary

    async def _get_previous_snapshot(
        self, space_id: UUID
    ) -> Optional[PortfolioSnapshot]:
        """Holt den letzten Snapshot fuer Vergleichszwecke.

        Args:
            space_id: ID des Privat-Space

        Returns:
            Letzter PortfolioSnapshot oder None
        """
        result = await self.db.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.space_id == space_id)
            .order_by(PortfolioSnapshot.snapshot_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_monthly_snapshot(
        self, space_id: UUID, snapshot_date: Optional[date] = None
    ) -> PortfolioSnapshot:
        """Erstellt einen monatlichen Portfolio-Snapshot.

        Args:
            space_id: ID des Privat-Space
            snapshot_date: Datum des Snapshots (Standard: heute)

        Returns:
            Erstellter PortfolioSnapshot
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        # Pruefen ob bereits ein Snapshot existiert
        existing = await self.db.execute(
            select(PortfolioSnapshot).where(
                and_(
                    PortfolioSnapshot.space_id == space_id,
                    PortfolioSnapshot.snapshot_date == snapshot_date,
                )
            )
        )
        if existing.scalar_one_or_none():
            logger.info(
                f"Snapshot fuer Space {space_id} am {snapshot_date} existiert bereits"
            )
            # Aktualisiere bestehenden Snapshot
            return await self.update_snapshot(space_id, snapshot_date)

        # Portfolio analysieren
        analysis = await self.calculate_current_portfolio(space_id)

        # Snapshot erstellen
        snapshot = PortfolioSnapshot(
            space_id=space_id,
            snapshot_date=snapshot_date,
            # Assets
            total_real_estate=analysis.assets.total_real_estate,
            total_vehicles=analysis.assets.total_vehicles,
            total_investments=analysis.assets.total_investments,
            total_cash=analysis.assets.total_cash,
            total_other_assets=analysis.assets.total_other_assets,
            # Liabilities
            total_mortgages=analysis.liabilities.total_mortgages,
            total_loans=analysis.liabilities.total_loans,
            total_other_liabilities=analysis.liabilities.total_other_liabilities,
            # Aggregates
            total_assets=analysis.assets.total,
            total_liabilities=analysis.liabilities.total,
            net_worth=analysis.net_worth,
            # Changes
            net_worth_change_absolute=analysis.net_worth_change_absolute,
            net_worth_change_percent=analysis.net_worth_change_percent,
            # Ratios
            debt_to_assets_ratio=analysis.debt_to_assets_ratio,
            liquidity_ratio=analysis.liquidity_ratio,
            # Allocation
            asset_allocation=analysis.asset_allocation,
        )

        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)

        logger.info(
            f"Portfolio-Snapshot erstellt fuer Space {space_id}: "
            f"Net Worth = {analysis.net_worth} EUR"
        )

        return snapshot

    async def update_snapshot(
        self, space_id: UUID, snapshot_date: date
    ) -> PortfolioSnapshot:
        """Aktualisiert einen bestehenden Snapshot.

        Args:
            space_id: ID des Privat-Space
            snapshot_date: Datum des Snapshots

        Returns:
            Aktualisierter PortfolioSnapshot
        """
        # Snapshot laden
        result = await self.db.execute(
            select(PortfolioSnapshot).where(
                and_(
                    PortfolioSnapshot.space_id == space_id,
                    PortfolioSnapshot.snapshot_date == snapshot_date,
                )
            )
        )
        snapshot = result.scalar_one_or_none()

        if not snapshot:
            return await self.create_monthly_snapshot(space_id, snapshot_date)

        # Portfolio neu analysieren
        analysis = await self.calculate_current_portfolio(space_id)

        # Snapshot aktualisieren
        snapshot.total_real_estate = analysis.assets.total_real_estate
        snapshot.total_vehicles = analysis.assets.total_vehicles
        snapshot.total_investments = analysis.assets.total_investments
        snapshot.total_cash = analysis.assets.total_cash
        snapshot.total_other_assets = analysis.assets.total_other_assets
        snapshot.total_mortgages = analysis.liabilities.total_mortgages
        snapshot.total_loans = analysis.liabilities.total_loans
        snapshot.total_other_liabilities = analysis.liabilities.total_other_liabilities
        snapshot.total_assets = analysis.assets.total
        snapshot.total_liabilities = analysis.liabilities.total
        snapshot.net_worth = analysis.net_worth
        snapshot.net_worth_change_absolute = analysis.net_worth_change_absolute
        snapshot.net_worth_change_percent = analysis.net_worth_change_percent
        snapshot.debt_to_assets_ratio = analysis.debt_to_assets_ratio
        snapshot.liquidity_ratio = analysis.liquidity_ratio
        snapshot.asset_allocation = analysis.asset_allocation

        await self.db.commit()
        await self.db.refresh(snapshot)

        logger.info(f"Portfolio-Snapshot aktualisiert fuer Space {space_id}")

        return snapshot

    async def get_latest_snapshot(
        self, space_id: UUID
    ) -> Optional[PortfolioSnapshot]:
        """Holt den neuesten Snapshot fuer einen Space.

        Args:
            space_id: ID des Privat-Space

        Returns:
            Neuester PortfolioSnapshot oder None
        """
        return await self._get_previous_snapshot(space_id)

    async def get_portfolio_history(
        self,
        space_id: UUID,
        months: int = 12,
    ) -> Sequence[PortfolioSnapshot]:
        """Holt die Portfolio-Historie der letzten Monate.

        Args:
            space_id: ID des Privat-Space
            months: Anzahl der Monate (Standard: 12)

        Returns:
            Liste von PortfolioSnapshots
        """
        cutoff_date = date.today() - timedelta(days=months * 30)

        result = await self.db.execute(
            select(PortfolioSnapshot)
            .where(
                and_(
                    PortfolioSnapshot.space_id == space_id,
                    PortfolioSnapshot.snapshot_date >= cutoff_date,
                )
            )
            .order_by(PortfolioSnapshot.snapshot_date.asc())
        )

        return result.scalars().all()

    async def get_net_worth_trend(
        self, space_id: UUID, months: int = 12
    ) -> list[NetWorthTrendItem]:
        """Holt den Net Worth Trend fuer Chart-Darstellung.

        Args:
            space_id: ID des Privat-Space
            months: Anzahl der Monate

        Returns:
            Liste mit Datum und Net Worth fuer jeden Monat
        """
        history = await self.get_portfolio_history(space_id, months)

        return [
            {
                "date": snapshot.snapshot_date.isoformat(),
                "net_worth": float(snapshot.net_worth),
                "total_assets": float(snapshot.total_assets),
                "total_liabilities": float(snapshot.total_liabilities),
            }
            for snapshot in history
        ]

    async def create_snapshots_for_all_spaces(self) -> int:
        """Erstellt Snapshots fuer alle aktiven Spaces.

        Wird typischerweise monatlich via Celery Beat ausgefuehrt.

        Returns:
            Anzahl der erstellten Snapshots
        """
        # Alle aktiven Spaces laden
        result = await self.db.execute(
            select(PrivatSpace.id).where(PrivatSpace.deleted_at.is_(None))
        )
        space_ids = result.scalars().all()

        count = 0
        today = date.today()

        for space_id in space_ids:
            try:
                await self.create_monthly_snapshot(space_id, today)
                count += 1
            except Exception as e:
                logger.error(
                    f"Fehler beim Erstellen des Snapshots fuer Space {space_id}: {e}"
                )
                continue

        logger.info(f"Portfolio-Snapshots erstellt fuer {count} Spaces")
        return count

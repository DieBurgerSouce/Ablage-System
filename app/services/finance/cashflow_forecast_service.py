# -*- coding: utf-8 -*-
"""
Cashflow Forecast Service - Intelligente Cashflow-Prognose.

Basiert auf: offene Rechnungen + Zahlungsverhalten + saisonale Muster.
Warnung bei drohendem Liquiditaetsengpass.
Was-waere-wenn-Szenarien.

Feinpoliert und durchdacht - Enterprise-grade Liquiditaetsplanung.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import uuid as uuid_mod

import structlog
from sqlalchemy import select, and_, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models_german_finance import CashflowForecast

logger = structlog.get_logger(__name__)


class CashflowForecastService:
    """Intelligente Cashflow-Prognose.

    Basiert auf offene Rechnungen + Zahlungsverhalten + saisonale Muster.
    Warnung bei drohendem Liquiditaetsengpass.
    """

    async def generate_forecast(
        self,
        db: AsyncSession,
        company_id: UUID,
        horizon_days: int = 90,
        scenario_type: str = "basis",
        scenario_config: Optional[Dict[str, object]] = None,
    ) -> CashflowForecast:
        """Cashflow-Prognose generieren.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            horizon_days: Prognosezeitraum in Tagen
            scenario_type: basis, optimistisch, pessimistisch, wenn_kunde_nicht_zahlt
            scenario_config: Szenario-Parameter

        Returns:
            CashflowForecast
        """
        today = date.today()

        # 1. Offene Posten ermitteln
        offene_forderungen = await self._get_offene_forderungen(db, company_id)
        offene_verbindlichkeiten = await self._get_offene_verbindlichkeiten(db, company_id)

        # 2. Saisonaler Faktor
        saisonaler_faktor = await self._calculate_seasonal_factor(
            db, company_id, today.month
        )

        # 3. Szenario-Anpassung
        inflow_factor, outflow_factor, delay_days = self._get_scenario_factors(
            scenario_type, scenario_config
        )

        # 4. Prognose berechnen
        einnahmen = float(offene_forderungen) * inflow_factor * saisonaler_faktor
        ausgaben = float(offene_verbindlichkeiten) * outflow_factor

        # Aktueller Kontostand
        current_balance = await self._get_current_balance(db, company_id)
        predicted_balance = current_balance + einnahmen - ausgaben

        # Konfidenzintervall (vereinfacht: +/- 20%)
        confidence_lower = predicted_balance * 0.8
        confidence_upper = predicted_balance * 1.2

        # 5. Engpass-Pruefung
        warnung = predicted_balance < 0
        engpass_datum = None
        if warnung:
            # Vereinfacht: wenn Balance negativ wird
            days_until_negative = max(
                1, int(current_balance / max(1, (ausgaben - einnahmen) / horizon_days))
            ) if ausgaben > einnahmen else None
            if days_until_negative:
                engpass_datum = today + timedelta(days=min(days_until_negative, horizon_days))

        # 6. Speichern
        forecast = CashflowForecast(
            id=uuid_mod.uuid4(),
            company_id=company_id,
            forecast_date=today,
            horizon_days=horizon_days,
            predicted_balance=round(predicted_balance, 2),
            confidence_lower=round(confidence_lower, 2),
            confidence_upper=round(confidence_upper, 2),
            einnahmen_prognose=round(einnahmen, 2),
            ausgaben_prognose=round(ausgaben, 2),
            offene_forderungen=float(offene_forderungen),
            offene_verbindlichkeiten=float(offene_verbindlichkeiten),
            saisonaler_faktor=round(saisonaler_faktor, 3),
            warnung_liquiditaetsengpass=warnung,
            engpass_datum=engpass_datum,
            scenario_type=scenario_type,
            scenario_config=scenario_config,
        )

        db.add(forecast)
        await db.flush()

        logger.info(
            "cashflow_prognose_generiert",
            company_id=str(company_id),
            horizon_days=horizon_days,
            scenario=scenario_type,
            predicted_balance=round(predicted_balance, 2),
            warnung=warnung,
        )

        return forecast

    async def check_liquidity_warnings(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Optional[Dict[str, object]]:
        """Prueft auf drohende Liquiditaetsengpaesse.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Dict mit Warnung oder None
        """
        forecast = await self.generate_forecast(db, company_id, horizon_days=90)

        if not forecast.warnung_liquiditaetsengpass:
            return None

        return {
            "company_id": str(company_id),
            "engpass_datum": (
                forecast.engpass_datum.isoformat() if forecast.engpass_datum else None
            ),
            "predicted_balance": forecast.predicted_balance,
            "forecast_id": str(forecast.id),
            "severity": "critical" if forecast.predicted_balance < -5000 else "warning",
            "message": (
                f"Liquiditaetsengpass erwartet am "
                f"{forecast.engpass_datum.strftime('%d.%m.%Y')}"
                if forecast.engpass_datum else
                "Liquiditaetsrisiko erkannt"
            ),
        }

    async def what_if_scenario(
        self,
        db: AsyncSession,
        company_id: UUID,
        base_forecast_id: UUID,
        modifications: Dict[str, object],
    ) -> CashflowForecast:
        """Was-waere-wenn-Szenario.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            base_forecast_id: Basis-Prognose
            modifications: Aenderungen

        Returns:
            Neue CashflowForecast
        """
        return await self.generate_forecast(
            db,
            company_id,
            scenario_type="wenn_kunde_nicht_zahlt",
            scenario_config=modifications,
        )

    async def get_seasonal_factors(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, float]:
        """Saisonale Faktoren fuer alle Monate."""
        factors: Dict[str, float] = {}
        for month in range(1, 13):
            factors[str(month)] = await self._calculate_seasonal_factor(
                db, company_id, month
            )
        return factors

    async def generate_scenario(
        self,
        db: AsyncSession,
        company_id: UUID,
        scenario_type: str,
        scenario_config: Optional[Dict[str, object]] = None,
        horizon_days: int = 90,
    ) -> CashflowForecast:
        """Spezifisches Szenario generieren.

        Unterstuetzte Szenarien:
            - basis: Standardprognose
            - optimistisch: +10% Einnahmen, -10% Ausgaben
            - pessimistisch: -25% Einnahmen, +10% Ausgaben
            - wenn_kunde_nicht_zahlt: Benutzerdefiniert via scenario_config

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            scenario_type: Szenario-Typ
            scenario_config: Optionale Parameter
            horizon_days: Prognosezeitraum

        Returns:
            CashflowForecast fuer das Szenario
        """
        return await self.generate_forecast(
            db,
            company_id,
            horizon_days=horizon_days,
            scenario_type=scenario_type,
            scenario_config=scenario_config,
        )

    async def get_forecast(
        self,
        db: AsyncSession,
        company_id: UUID,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[CashflowForecast]:
        """Cashflow-Prognosen fuer einen Zeitraum abrufen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            from_date: Startdatum (default: heute - 30 Tage)
            to_date: Enddatum (default: heute)

        Returns:
            Liste von CashflowForecast
        """
        if from_date is None:
            from_date = date.today() - timedelta(days=30)
        if to_date is None:
            to_date = date.today()

        stmt = (
            select(CashflowForecast)
            .where(
                and_(
                    CashflowForecast.company_id == company_id,
                    CashflowForecast.forecast_date >= from_date,
                    CashflowForecast.forecast_date <= to_date,
                )
            )
            .order_by(CashflowForecast.forecast_date.desc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_liquidity_warnings(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[CashflowForecast]:
        """Alle Prognosen mit Liquiditaetsengpass-Warnung.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Liste von CashflowForecast mit warnung_liquiditaetsengpass=True
        """
        stmt = (
            select(CashflowForecast)
            .where(
                and_(
                    CashflowForecast.company_id == company_id,
                    CashflowForecast.warnung_liquiditaetsengpass == True,
                    CashflowForecast.forecast_date >= date.today() - timedelta(days=90),
                )
            )
            .order_by(CashflowForecast.forecast_date.desc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_payment_behavior_analysis(
        self,
        db: AsyncSession,
        company_id: UUID,
        entity_id: Optional[UUID] = None,
    ) -> Dict[str, object]:
        """Zahlungsverhalten-Analyse.

        Analysiert historisches Zahlungsverhalten von Kunden/Lieferanten
        fuer bessere Cashflow-Prognosen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            entity_id: Optional - spezifische Entity analysieren

        Returns:
            Dict mit Zahlungsverhalten-Metriken
        """
        from app.db.models import InvoiceTracking

        # Bezahlte Rechnungen der letzten 365 Tage analysieren
        lookback = date.today() - timedelta(days=365)

        conditions = [
            InvoiceTracking.company_id == company_id,
            InvoiceTracking.status == "paid",
            InvoiceTracking.deleted_at.is_(None),
            InvoiceTracking.invoice_date >= datetime(
                lookback.year, lookback.month, lookback.day
            ),
        ]

        if entity_id is not None:
            conditions.append(InvoiceTracking.entity_id == entity_id)

        stmt = select(InvoiceTracking).where(and_(*conditions))
        result = await db.execute(stmt)
        invoices = result.scalars().all()

        if not invoices:
            return {
                "company_id": str(company_id),
                "entity_id": str(entity_id) if entity_id else None,
                "analyse_zeitraum_tage": 365,
                "anzahl_rechnungen": 0,
                "durchschnittliche_zahlungsdauer_tage": 0,
                "median_zahlungsdauer_tage": 0,
                "puenktlich_bezahlt_prozent": 0.0,
                "ueberfaellig_bezahlt_prozent": 0.0,
                "message": "Keine bezahlten Rechnungen im Analysezeitraum",
            }

        # Zahlungsdauern berechnen
        zahlungsdauern: List[int] = []
        puenktlich = 0

        for inv in invoices:
            inv_date = getattr(inv, "invoice_date", None)
            paid_date = getattr(inv, "paid_at", None) or getattr(inv, "updated_at", None)
            due_date = getattr(inv, "due_date", None)

            if inv_date and paid_date:
                if hasattr(inv_date, "date"):
                    inv_date = inv_date.date()
                if hasattr(paid_date, "date"):
                    paid_date = paid_date.date()
                delta = (paid_date - inv_date).days
                zahlungsdauern.append(max(0, delta))

                if due_date:
                    if hasattr(due_date, "date"):
                        due_date = due_date.date()
                    if paid_date <= due_date:
                        puenktlich += 1

        total_count = len(invoices)
        avg_days = sum(zahlungsdauern) / max(len(zahlungsdauern), 1)

        # Median berechnen
        sorted_days = sorted(zahlungsdauern)
        n = len(sorted_days)
        if n > 0:
            median_days = sorted_days[n // 2] if n % 2 == 1 else (
                (sorted_days[n // 2 - 1] + sorted_days[n // 2]) / 2
            )
        else:
            median_days = 0

        puenktlich_pct = (puenktlich / total_count * 100) if total_count > 0 else 0.0

        return {
            "company_id": str(company_id),
            "entity_id": str(entity_id) if entity_id else None,
            "analyse_zeitraum_tage": 365,
            "anzahl_rechnungen": total_count,
            "durchschnittliche_zahlungsdauer_tage": round(avg_days, 1),
            "median_zahlungsdauer_tage": round(median_days, 1),
            "puenktlich_bezahlt_prozent": round(puenktlich_pct, 1),
            "ueberfaellig_bezahlt_prozent": round(100.0 - puenktlich_pct, 1),
        }

    async def compare_forecast_accuracy(
        self,
        db: AsyncSession,
        company_id: UUID,
        forecast_id: UUID,
    ) -> Dict[str, object]:
        """Vergleicht Prognose mit tatsaechlichen Werten."""
        stmt = select(CashflowForecast).where(
            and_(
                CashflowForecast.id == forecast_id,
                CashflowForecast.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        forecast = result.scalar_one_or_none()

        if forecast is None:
            raise ValueError(f"Prognose {forecast_id} nicht gefunden")

        forecast_date = forecast.forecast_date
        end_date = forecast_date + timedelta(days=forecast.horizon_days)

        if end_date > date.today():
            return {
                "status": "zu_frueh",
                "message": f"Zeitraum endet am {end_date.isoformat()}",
            }

        return {
            "forecast_id": str(forecast_id),
            "status": "verfuegbar",
            "predicted_balance": forecast.predicted_balance,
            "einnahmen_prognose": forecast.einnahmen_prognose,
            "ausgaben_prognose": forecast.ausgaben_prognose,
        }

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _get_current_balance(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> float:
        """Ermittelt den aktuellen Kontostand."""
        from app.db.models import BankAccount, BankTransaction

        stmt = select(BankAccount).where(
            and_(
                BankAccount.company_id == company_id,
                BankAccount.is_active == True,
            )
        )
        result = await db.execute(stmt)
        accounts = result.scalars().all()

        total = 0.0
        for acct in accounts:
            tx_stmt = (
                select(BankTransaction.running_balance)
                .where(BankTransaction.bank_account_id == acct.id)
                .order_by(BankTransaction.booking_date.desc())
                .limit(1)
            )
            tx_result = await db.execute(tx_stmt)
            balance = tx_result.scalar()
            if balance is not None:
                total += float(balance)

        return total

    async def _get_offene_forderungen(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Decimal:
        """Offene Forderungen (Debitoren) aggregieren."""
        from app.db.models import InvoiceTracking

        stmt = (
            select(func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0))
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["open", "sent", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )

        result = await db.execute(stmt)
        total = result.scalar() or 0
        return Decimal(str(total))

    async def _get_offene_verbindlichkeiten(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Decimal:
        """Offene Verbindlichkeiten (Kreditoren) aggregieren."""
        from app.db.models import InvoiceTracking

        stmt = (
            select(func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0))
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["open", "sent", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )

        result = await db.execute(stmt)
        total = result.scalar() or 0
        return Decimal(str(total))

    async def _calculate_seasonal_factor(
        self,
        db: AsyncSession,
        company_id: UUID,
        target_month: int,
    ) -> float:
        """Berechnet saisonalen Faktor fuer einen Monat."""
        from app.db.models import InvoiceTracking

        lookback_start = date.today() - timedelta(days=730)

        stmt = (
            select(
                extract("month", InvoiceTracking.invoice_date).label("month"),
                func.sum(InvoiceTracking.amount).label("total"),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= datetime(
                        lookback_start.year, lookback_start.month, lookback_start.day
                    ),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            .group_by(extract("month", InvoiceTracking.invoice_date))
        )

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return 1.0

        monthly_totals = {int(row.month): float(row.total or 0) for row in rows}
        overall_avg = sum(monthly_totals.values()) / max(len(monthly_totals), 1)

        if overall_avg <= 0:
            return 1.0

        target_total = monthly_totals.get(target_month, overall_avg)
        return round(target_total / overall_avg, 3)

    def _get_scenario_factors(
        self,
        scenario_type: str,
        scenario_config: Optional[Dict[str, object]],
    ) -> Tuple[float, float, int]:
        """Szenario-Anpassungsfaktoren."""
        defaults = {
            "basis": (1.0, 1.0, 0),
            "optimistisch": (1.1, 0.9, -3),
            "pessimistisch": (0.75, 1.1, 15),
        }

        if scenario_type in defaults:
            return defaults[scenario_type]

        if scenario_config:
            return (
                float(scenario_config.get("inflow_factor", 1.0)),
                float(scenario_config.get("outflow_factor", 1.0)),
                int(scenario_config.get("delay_days", 0)),
            )

        return (1.0, 1.0, 0)


def get_cashflow_forecast_service() -> CashflowForecastService:
    """FastAPI Dependency."""
    return CashflowForecastService()

# -*- coding: utf-8 -*-
"""
FX Rate Service - Wechselkurse von der EZB.

Holt taegliche Referenzkurse der Europaeischen Zentralbank (ECB)
und bietet Waehrungsumrechnung mit Caching.

ECB Datenquelle: https://data-api.ecb.europa.eu
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import InvoiceTracking, InvoiceStatus, Document, Company
from app.db.models_fx import ExchangeRate, RateSource

logger = structlog.get_logger(__name__)


@dataclass
class RevaluationEntry:
    """Einzelposition einer Stichtagsbewertung."""
    invoice_tracking_id: UUID
    currency: str
    original_amount: Decimal
    outstanding_amount: Decimal
    booking_rate: Decimal
    current_rate: Decimal
    gain_loss_eur: Decimal
    is_gain: bool


@dataclass
class RevaluationSummary:
    """Ergebnis einer Monatsabschluss-Bewertung."""
    entries_processed: int
    total_gain: Decimal
    total_loss: Decimal
    currency_breakdown: Dict[str, Dict[str, str]]
    entries: List[RevaluationEntry]

# ECB daily reference rates endpoint (XML)
ECB_DAILY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
# For historical rates:
ECB_HISTORY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"

# Common currencies for German businesses
SUPPORTED_CURRENCIES = [
    "USD", "GBP", "CHF", "JPY", "SEK", "NOK", "DKK", "PLN", "CZK",
    "HUF", "RON", "BGN", "HRK", "TRY", "CNY", "CAD", "AUD", "NZD",
]


@dataclass
class ConversionResult:
    """Ergebnis einer Waehrungsumrechnung."""
    original_amount: Decimal
    original_currency: str
    converted_amount: Decimal
    target_currency: str
    rate_used: Decimal
    rate_date: date
    rate_source: str


class FXRateService:
    """Service fuer Wechselkurse und Waehrungsumrechnung."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_ecb_rates(self, historical: bool = False) -> int:
        """
        Holt aktuelle (oder 90-Tage-Historie) ECB Referenzkurse.
        Returns: Anzahl gespeicherter Kurse.

        Parses the ECB XML response format:
        <Cube time="2024-01-15">
            <Cube currency="USD" rate="1.0876"/>
            ...
        </Cube>
        """
        url = ECB_HISTORY_RATES_URL if historical else ECB_DAILY_RATES_URL

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.text)
        ns = {"gesmes": "http://www.gesmes.org/xml/2002-08-01",
              "eurofxref": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}

        count = 0
        for cube_time in root.findall(".//eurofxref:Cube[@time]", ns):
            rate_date_str = cube_time.attrib["time"]
            rate_date = date.fromisoformat(rate_date_str)

            for cube_rate in cube_time.findall("eurofxref:Cube", ns):
                currency = cube_rate.attrib["currency"]
                rate_value = Decimal(cube_rate.attrib["rate"])

                # Upsert rate
                existing = await self.db.execute(
                    select(ExchangeRate).where(
                        and_(
                            ExchangeRate.base_currency == "EUR",
                            ExchangeRate.target_currency == currency,
                            ExchangeRate.rate_date == rate_date,
                            ExchangeRate.source == "ecb",
                        )
                    )
                )
                if not existing.scalar_one_or_none():
                    self.db.add(ExchangeRate(
                        base_currency="EUR",
                        target_currency=currency,
                        rate=rate_value,
                        rate_date=rate_date,
                        source="ecb",
                    ))
                    count += 1

        await self.db.commit()
        logger.info("ecb_rates_imported", count=count, historical=historical)
        return count

    async def get_rate(
        self, currency: str, target_date: Optional[date] = None
    ) -> Optional[Decimal]:
        """
        Cached lookup: EUR -> currency rate for date.
        Falls back to most recent available rate if exact date not found.
        """
        if currency == "EUR":
            return Decimal("1.0")

        lookup_date = target_date or date.today()

        # Try exact date first
        result = await self.db.execute(
            select(ExchangeRate.rate).where(
                and_(
                    ExchangeRate.base_currency == "EUR",
                    ExchangeRate.target_currency == currency,
                    ExchangeRate.rate_date == lookup_date,
                )
            )
        )
        rate = result.scalar_one_or_none()
        if rate:
            return rate

        # Fallback: most recent rate within 7 days
        result = await self.db.execute(
            select(ExchangeRate.rate).where(
                and_(
                    ExchangeRate.base_currency == "EUR",
                    ExchangeRate.target_currency == currency,
                    ExchangeRate.rate_date >= lookup_date - timedelta(days=7),
                    ExchangeRate.rate_date <= lookup_date,
                )
            ).order_by(desc(ExchangeRate.rate_date)).limit(1)
        )
        return result.scalar_one_or_none()

    async def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str = "EUR",
        rate_date: Optional[date] = None,
    ) -> ConversionResult:
        """
        Waehrungsumrechnung mit aktuellem oder historischem Kurs.

        EUR -> Fremdwaehrung: amount * rate
        Fremdwaehrung -> EUR: amount / rate
        """
        if from_currency == to_currency:
            return ConversionResult(
                original_amount=amount,
                original_currency=from_currency,
                converted_amount=amount,
                target_currency=to_currency,
                rate_used=Decimal("1.0"),
                rate_date=rate_date or date.today(),
                rate_source="identity",
            )

        lookup_date = rate_date or date.today()

        if from_currency == "EUR":
            rate = await self.get_rate(to_currency, lookup_date)
            if rate is None:
                raise ValueError(f"Kein Wechselkurs verfuegbar fuer {to_currency} am {lookup_date}")
            converted = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif to_currency == "EUR":
            rate = await self.get_rate(from_currency, lookup_date)
            if rate is None:
                raise ValueError(f"Kein Wechselkurs verfuegbar fuer {from_currency} am {lookup_date}")
            converted = (amount / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            # Cross-rate via EUR
            rate_from = await self.get_rate(from_currency, lookup_date)
            rate_to = await self.get_rate(to_currency, lookup_date)
            if rate_from is None or rate_to is None:
                raise ValueError(f"Kein Wechselkurs verfuegbar fuer {from_currency}/{to_currency}")
            eur_amount = (amount / rate_from)
            converted = (eur_amount * rate_to).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            rate = rate_to / rate_from

        return ConversionResult(
            original_amount=amount,
            original_currency=from_currency,
            converted_amount=converted,
            target_currency=to_currency,
            rate_used=rate,
            rate_date=lookup_date,
            rate_source="ecb",
        )

    async def get_available_currencies(self, for_date: Optional[date] = None) -> List[str]:
        """Returns list of currencies with available rates."""
        lookup_date = for_date or date.today()
        result = await self.db.execute(
            select(ExchangeRate.target_currency).where(
                and_(
                    ExchangeRate.base_currency == "EUR",
                    ExchangeRate.rate_date >= lookup_date - timedelta(days=7),
                )
            ).distinct()
        )
        return [row[0] for row in result.all()]

    async def month_end_revaluation(
        self,
        company_id: UUID,
        revaluation_date: date,
        db: AsyncSession,
    ) -> RevaluationSummary:
        """
        Monatsabschluss-Stichtagsbewertung aller offenen Fremdwaehrungspositionen.

        Bewertet offene Forderungen und Verbindlichkeiten in Nicht-EUR-Waehrungen
        zum Stichtagskurs und bucht unrealisierte Kursgewinne/-verluste.

        Args:
            company_id: Firmen-ID
            revaluation_date: Bewertungsstichtag (z.B. 2026-01-31)
            db: Datenbank-Session

        Returns:
            RevaluationSummary mit Ergebnis der Bewertung
        """
        from app.services.accounting.fx_gain_loss_service import FXGainLossService

        logger.info(
            "month_end_revaluation_started",
            company_id=str(company_id),
            revaluation_date=str(revaluation_date),
        )

        # 1. Offene Fremdwaehrungspositionen abfragen
        open_positions = await self._get_open_fx_positions(company_id, db)

        if not open_positions:
            logger.info(
                "month_end_revaluation_no_positions",
                company_id=str(company_id),
            )
            return RevaluationSummary(
                entries_processed=0,
                total_gain=Decimal("0.00"),
                total_loss=Decimal("0.00"),
                currency_breakdown={},
                entries=[],
            )

        fx_gl_service = FXGainLossService(db)
        entries: List[RevaluationEntry] = []
        total_gain = Decimal("0.00")
        total_loss = Decimal("0.00")
        currency_breakdown: Dict[str, Dict[str, Decimal]] = {}

        # 2. Fuer jede Position: Stichtagskurs holen und Differenz berechnen
        for inv in open_positions:
            currency = inv.currency
            if not currency or currency == "EUR":
                continue

            outstanding = Decimal(str(inv.outstanding_amount or inv.amount or 0))
            paid = Decimal(str(inv.paid_amount or 0))
            if inv.outstanding_amount is None:
                outstanding = Decimal(str(inv.amount or 0)) - paid
            if outstanding <= Decimal("0"):
                continue

            # Buchungskurs: EUR-Betrag zum Zeitpunkt der Rechnungsstellung
            # Da InvoiceTracking keinen booking_rate hat, berechnen wir ihn
            # aus dem historischen Kurs am Rechnungsdatum
            invoice_date_val = inv.invoice_date
            if invoice_date_val and hasattr(invoice_date_val, 'date'):
                invoice_date_val = invoice_date_val.date()

            booking_rate = await self.get_rate(currency, invoice_date_val)
            if booking_rate is None:
                logger.warning(
                    "month_end_revaluation_no_booking_rate",
                    currency=currency,
                    invoice_date=str(invoice_date_val),
                    invoice_id=str(inv.id),
                )
                continue

            # Stichtagskurs
            current_rate = await self.get_rate(currency, revaluation_date)
            if current_rate is None:
                logger.warning(
                    "month_end_revaluation_no_current_rate",
                    currency=currency,
                    revaluation_date=str(revaluation_date),
                )
                continue

            # 3. Unrealisierten Gewinn/Verlust berechnen
            gl_result = fx_gl_service.calculate_unrealized_gain_loss(
                original_amount=outstanding,
                original_currency=currency,
                booking_rate=booking_rate,
                current_rate=current_rate,
            )

            # Nur buchen wenn Differenz nicht Null ist
            if gl_result.gain_loss_amount == Decimal("0.00"):
                continue

            # 4. GL-Buchung erstellen (System-User fuer automatische Bewertung)
            await fx_gl_service.post_fx_gain_loss(
                company_id=company_id,
                result=gl_result,
                realized=False,
                posted_by=company_id,  # System-User = company_id als Platzhalter
                reference_document_id=inv.document_id if hasattr(inv, 'document_id') else None,
            )

            entry = RevaluationEntry(
                invoice_tracking_id=inv.id,
                currency=currency,
                original_amount=Decimal(str(inv.amount or 0)),
                outstanding_amount=outstanding,
                booking_rate=booking_rate,
                current_rate=current_rate,
                gain_loss_eur=gl_result.gain_loss_amount if gl_result.is_gain else -gl_result.gain_loss_amount,
                is_gain=gl_result.is_gain,
            )
            entries.append(entry)

            if gl_result.is_gain:
                total_gain += gl_result.gain_loss_amount
            else:
                total_loss += gl_result.gain_loss_amount

            # Waehrungs-Aufschluesselung
            if currency not in currency_breakdown:
                currency_breakdown[currency] = {
                    "gain": Decimal("0.00"),
                    "loss": Decimal("0.00"),
                    "positions": Decimal("0"),
                }
            if gl_result.is_gain:
                currency_breakdown[currency]["gain"] += gl_result.gain_loss_amount
            else:
                currency_breakdown[currency]["loss"] += gl_result.gain_loss_amount
            currency_breakdown[currency]["positions"] += Decimal("1")

        # Breakdown-Werte zu Strings fuer Serialisierung
        breakdown_str: Dict[str, Dict[str, str]] = {}
        for cur, vals in currency_breakdown.items():
            breakdown_str[cur] = {
                "gain": str(vals["gain"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "loss": str(vals["loss"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "positions": str(int(vals["positions"])),
            }

        summary = RevaluationSummary(
            entries_processed=len(entries),
            total_gain=total_gain.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            total_loss=total_loss.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            currency_breakdown=breakdown_str,
            entries=entries,
        )

        logger.info(
            "month_end_revaluation_completed",
            company_id=str(company_id),
            entries_processed=summary.entries_processed,
            total_gain=str(summary.total_gain),
            total_loss=str(summary.total_loss),
        )

        return summary

    async def _get_open_fx_positions(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InvoiceTracking]:
        """
        Holt alle offenen Fremdwaehrungspositionen fuer eine Firma.

        Returns:
            Liste von InvoiceTracking mit currency != 'EUR' und offenen Betraegen.
        """
        result = await db.execute(
            select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.deleted_at.is_(None),
                    InvoiceTracking.currency != "EUR",
                    InvoiceTracking.status.notin_([
                        InvoiceStatus.PAID.value,
                        InvoiceStatus.CANCELLED.value,
                    ]),
                )
            )
        )
        return list(result.scalars().all())

    async def get_fx_exposure(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[Dict[str, str]]:
        """
        Berechnet aktuelle FX-Exposure pro Waehrung.

        Returns:
            Liste mit Waehrungs-Exposure: currency, amount, eur_equivalent
        """
        positions = await self._get_open_fx_positions(company_id, db)

        exposure_map: Dict[str, Decimal] = {}
        for inv in positions:
            currency = inv.currency
            outstanding = Decimal(str(inv.outstanding_amount or inv.amount or 0))
            paid = Decimal(str(inv.paid_amount or 0))
            if inv.outstanding_amount is None:
                outstanding = Decimal(str(inv.amount or 0)) - paid
            if outstanding <= Decimal("0"):
                continue
            exposure_map[currency] = exposure_map.get(currency, Decimal("0")) + outstanding

        exposures: List[Dict[str, str]] = []
        for currency, amount in sorted(exposure_map.items()):
            rate = await self.get_rate(currency)
            if rate and rate > Decimal("0"):
                eur_equivalent = (amount / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                eur_equivalent = Decimal("0.00")

            exposures.append({
                "currency": currency,
                "amount": str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "eur_equivalent": str(eur_equivalent),
            })

        return exposures


def get_fx_rate_service(db: AsyncSession) -> FXRateService:
    return FXRateService(db)

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
from app.db.models_fx import ExchangeRate, RateSource

logger = structlog.get_logger(__name__)

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


def get_fx_rate_service(db: AsyncSession) -> FXRateService:
    return FXRateService(db)

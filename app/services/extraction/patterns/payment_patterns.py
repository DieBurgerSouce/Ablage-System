"""
Payment term patterns for German documents.

Comprehensive patterns for extracting:
- Payment days (Zahlungsziel)
- Discount terms (Skonto)
- Due dates (Fälligkeitsdatum)
- Special payment conditions
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Pattern as RePattern

from app.services.extraction.base import DiscountTier, Pattern, PatternMatch


@dataclass
class PaymentPatterns:
    """Collection of payment-related regex patterns."""

    # ==========================================================================
    # BASIC PAYMENT DAYS
    # ==========================================================================

    # German/Dutch/English: "Zahlbar innerhalb von 30 Tagen", "Netto 10 dagen"
    PAYMENT_DAYS_BASIC: RePattern[str] = re.compile(
        r"(?:zahlbar|zahlungsziel|f[aä]llig(?:keit)?|netto)"
        r"[\s:]*(?:innerhalb\s*(?:von\s*)?)?"
        r"(?P<days>\d{1,4})\s*"  # Allow up to 4 digits for edge cases
        r"(?:tage?n?|werktage?n?|kalendertage?n?|dagen|days)",
        re.IGNORECASE,
    )

    # International: "NET 30", "Net 30 days", "Netto 10 dagen"
    PAYMENT_DAYS_NET: RePattern[str] = re.compile(
        r"(?:NET|net|netto)\s*(?P<days>\d{1,3})\s*(?:days?|tage?n?|dagen)?",
        re.IGNORECASE,
    )

    # Alternative: "30 Tage netto", "Zahlungsfrist 30 Tage", "30 dagen"
    PAYMENT_DAYS_ALT: RePattern[str] = re.compile(
        r"(?:zahlungsfrist|frist)\s*(?:von\s*)?"
        r"(?P<days>\d{1,3})\s*(?:tage?n?|werktage?n?|dagen|days)",
        re.IGNORECASE,
    )

    # Days from invoice/delivery: "30 Tage ab Rechnungsdatum"
    PAYMENT_DAYS_RELATIVE: RePattern[str] = re.compile(
        r"(?P<days>\d{1,3})\s*(?:tage?n?|werktage?n?|dagen|days)\s*"
        r"(?:ab|nach|from|after)\s*"
        r"(?P<reference>rechnungsdatum|rechnungseingang|lieferdatum|"
        r"erhalt|eingang|lieferung|versand|invoice|delivery|receipt)",
        re.IGNORECASE,
    )

    # ==========================================================================
    # IMMEDIATE PAYMENT
    # ==========================================================================

    # German immediate: "sofort fällig", "Zahlung bei Erhalt"
    PAYMENT_IMMEDIATE: RePattern[str] = re.compile(
        r"(?:sofort(?:\s*(?:zahlbar|f[aä]llig|bei\s*erhalt))?|"
        r"zahlung\s*(?:bei|nach)\s*(?:erhalt|eingang|empfang)|"
        r"zahlbar\s*sofort|"
        r"f[aä]llig\s*(?:bei|nach)\s*erhalt|"
        r"(?:due\s*)?(?:upon|on)\s*receipt)",
        re.IGNORECASE,
    )

    # Prepayment indicators
    PREPAYMENT: RePattern[str] = re.compile(
        r"(?:vor(?:aus)?kasse|vorauszahlung|vorab(?:zahlung)?|"
        r"prepaid|proforma|anzahlung\s*erforderlich|"
        r"zahlung\s*vor\s*(?:versand|lieferung)|"
        r"vorkasse\s*erforderlich|"
        r"bitte\s*(?:vorab|im\s*voraus)\s*(?:überweisen|zahlen))",
        re.IGNORECASE,
    )

    # Cash on delivery
    CASH_ON_DELIVERY: RePattern[str] = re.compile(
        r"(?:nachnahme|per\s*nachnahme|zahlung\s*bei\s*lieferung|"
        r"(?:cash|payment)\s*on\s*delivery|COD)",
        re.IGNORECASE,
    )

    # ==========================================================================
    # DISCOUNT / SKONTO
    # ==========================================================================

    # German Skonto: "2% Skonto bei Zahlung innerhalb 10 Tagen"
    SKONTO_GERMAN: RePattern[str] = re.compile(
        r"(?P<percent>\d{1,2}(?:[,\.]\d{1,2})?)\s*%?\s*"
        r"(?:skonto|rabatt|nachlass)\s*"
        r"(?:bei\s*(?:zahlung\s*)?)?(?:innerhalb\s*(?:von\s*)?)?"
        r"(?P<days>\d{1,3})\s*(?:tage?n?)",
        re.IGNORECASE,
    )

    # Alternative: "bei Zahlung innerhalb 10 Tagen 2% Skonto"
    SKONTO_GERMAN_ALT: RePattern[str] = re.compile(
        r"(?:bei\s*)?(?:zahlung\s*)?(?:innerhalb\s*(?:von\s*)?)?"
        r"(?P<days>\d{1,3})\s*(?:tage?n?)\s*"
        r"(?P<percent>\d{1,2}(?:[,\.]\d{1,2})?)\s*%?\s*"
        r"(?:skonto|rabatt|nachlass)",
        re.IGNORECASE,
    )

    # Flexibel: "Bei Zahlung innerhalb von 10 Tagen gewähren wir 2% Skonto"
    SKONTO_FLEXIBLE: RePattern[str] = re.compile(
        r"(?:bei\s+)?zahlung\s+innerhalb\s+(?:von\s+)?"
        r"(?P<days>\d{1,3})\s*(?:tage?n?)\s+"
        r"(?:(?:gew(?:ae|ä)hren|erhalten|gibt)\s+(?:wir|sie|es)\s+)?"
        r"(?P<percent>\d{1,2}(?:[,\.]\d{1,2})?)\s*%\s*"
        r"(?:skonto|rabatt|nachlass)?",
        re.IGNORECASE,
    )

    # International stepped: "2/10 net 30" (2% if paid within 10 days, net 30)
    STEPPED_DISCOUNT: RePattern[str] = re.compile(
        r"(?P<percent>\d{1,2})\s*[/%]\s*(?P<discount_days>\d{1,3})\s*"
        r"(?:net(?:to)?|netto)\s*(?P<net_days>\d{1,3})",
        re.IGNORECASE,
    )

    # Multi-tier: "3% bei 7 Tagen, 2% bei 14 Tagen, netto 30 Tage"
    MULTI_TIER_DISCOUNT: RePattern[str] = re.compile(
        r"(?P<percent>\d{1,2}(?:[,\.]\d{1,2})?)\s*%?\s*"
        r"(?:bei|innerhalb)\s*(?P<days>\d{1,3})\s*(?:tage?n?)",
        re.IGNORECASE,
    )

    # ==========================================================================
    # END OF MONTH / SPECIAL TERMS
    # ==========================================================================

    # End of month: "zahlbar zum Monatsende", "Zahlung bis Ende des Monats"
    END_OF_MONTH: RePattern[str] = re.compile(
        r"(?:zahlbar|zahlung)?\s*(?:zum|bis\s*zum?|per|bis)?\s*"
        r"(?:monatsende|ende\s*des?\s*monats?|month\s*end)",
        re.IGNORECASE,
    )

    # End of following month: "Monatsende folgender Monat"
    END_OF_FOLLOWING_MONTH: RePattern[str] = re.compile(
        r"(?:monatsende|ende)\s*(?:des?\s*)?"
        r"(?:folgenden?|n[aä]chsten?|kommenden?|laufenden?)\s*monats?|"
        r"(?:zahlbar\s*)?(?:zum|bis)\s*ende\s*"
        r"(?:des?\s*)?(?:folgenden?|n[aä]chsten?)\s*monats?",
        re.IGNORECASE,
    )

    # Fixed day of month: "zahlbar zum 15. des Folgemonats"
    FIXED_DAY_OF_MONTH: RePattern[str] = re.compile(
        r"(?:zahlbar\s*)?(?:zum|bis\s*zum?|per)\s*"
        r"(?P<day>\d{1,2})\.?\s*"
        r"(?:des?\s*)?(?P<month_ref>folgemonats?|"
        r"n[aä]chsten?\s*monats?|kommenden?\s*monats?|"
        r"(?:laufenden?\s*)?monats?)",
        re.IGNORECASE,
    )

    # ==========================================================================
    # DIRECT DUE DATE
    # ==========================================================================

    # Explicit due date: "Fällig am 15.02.2024", "Zahlbar bis 15.02.2024"
    DUE_DATE_EXPLICIT: RePattern[str] = re.compile(
        r"(?:f[aä]llig(?:keit)?|zahlbar|zu\s*zahlen)\s*"
        r"(?:am|bis|bis\s*zum|per|sp[aä]testens)?\s*"
        r"(?:den?\s*)?"
        r"(?P<day>\d{1,2})\.?\s*"
        r"(?P<month>\d{1,2}|"
        r"jan(?:uar)?|feb(?:ruar)?|m[aä]r(?:z)?|apr(?:il)?|"
        r"mai|jun(?:i)?|jul(?:i)?|aug(?:ust)?|sep(?:tember)?|"
        r"okt(?:ober)?|nov(?:ember)?|dez(?:ember)?)\.?\s*"
        r"(?P<year>\d{2,4})?",
        re.IGNORECASE,
    )

    # ==========================================================================
    # LATE PAYMENT INTEREST
    # ==========================================================================

    # Late interest: "Verzugszinsen 5% p.a."
    LATE_INTEREST: RePattern[str] = re.compile(
        r"(?:verzugszinsen|s[aä]umniszuschlag|zinsen\s*bei\s*verzug)\s*"
        r"(?:von\s*)?"
        r"(?P<rate>\d{1,2}(?:[,\.]\d{1,2})?)\s*%?\s*"
        r"(?:p\.?\s*a\.?|per\s*annum|j[aä]hrlich)?",
        re.IGNORECASE,
    )


class PaymentDaysPattern(Pattern[int]):
    """Pattern for extracting payment days."""

    def __init__(
        self,
        name: str,
        regex: RePattern[str],
        days_group: str = "days",
        base_confidence: float = 0.8,
    ) -> None:
        super().__init__(name, regex, base_confidence)
        self.days_group = days_group

    def normalize(self, value: str, groups: Dict[str, str]) -> int:
        """Extract days as integer."""
        days_str = groups.get(self.days_group, "")
        if not days_str:
            # Try to find any number in the value
            match = re.search(r"\d+", value)
            if match:
                return int(match.group())
            raise ValueError(f"Keine Tage gefunden in: {value}")
        return int(days_str)

    def calculate_confidence(
        self,
        value: str,
        context: str,
        groups: Dict[str, str],
    ) -> float:
        """Adjust confidence based on context."""
        confidence = self.base_confidence

        # Boost for clear payment context
        context_lower = context.lower()
        if any(kw in context_lower for kw in ["rechnung", "zahlung", "fällig"]):
            confidence += 0.1

        # Reduce for ambiguous context
        if any(kw in context_lower for kw in ["lieferzeit", "arbeits", "bearbeit"]):
            confidence -= 0.2

        return min(0.99, max(0.1, confidence))


class SkontoPattern(Pattern[DiscountTier]):
    """Pattern for extracting discount tiers."""

    def __init__(
        self,
        name: str,
        regex: RePattern[str],
        percent_group: str = "percent",
        days_group: str = "days",
        base_confidence: float = 0.85,
    ) -> None:
        super().__init__(name, regex, base_confidence)
        self.percent_group = percent_group
        self.days_group = days_group

    def normalize(self, value: str, groups: Dict[str, str]) -> DiscountTier:
        """Extract discount tier."""
        percent_str = groups.get(self.percent_group, "0")
        days_str = groups.get(self.days_group, "0")

        # Handle German decimal
        percent_str = percent_str.replace(",", ".")

        return DiscountTier(
            percent=Decimal(percent_str),
            days=int(days_str),
            raw_text=value,
        )


class SteppedDiscountPattern(Pattern[List[DiscountTier]]):
    """Pattern for stepped discounts like '2/10 net 30'."""

    def normalize(self, value: str, groups: Dict[str, str]) -> List[DiscountTier]:
        """Extract discount tier and net payment days."""
        percent = Decimal(groups.get("percent", "0"))
        discount_days = int(groups.get("discount_days", "0"))
        net_days = int(groups.get("net_days", "0"))

        return [
            DiscountTier(percent=percent, days=discount_days, raw_text=value),
            DiscountTier(percent=Decimal("0"), days=net_days, raw_text="netto"),
        ]


def get_payment_patterns() -> List[Pattern[Any]]:
    """Get all payment patterns for registration."""
    patterns = PaymentPatterns()

    return [
        # Payment days patterns
        PaymentDaysPattern(
            name="payment_days_basic",
            regex=patterns.PAYMENT_DAYS_BASIC,
            days_group="days",
            base_confidence=0.85,
        ),
        PaymentDaysPattern(
            name="payment_days_net",
            regex=patterns.PAYMENT_DAYS_NET,
            days_group="days",
            base_confidence=0.80,
        ),
        PaymentDaysPattern(
            name="payment_days_alt",
            regex=patterns.PAYMENT_DAYS_ALT,
            days_group="days",
            base_confidence=0.80,
        ),
        PaymentDaysPattern(
            name="payment_days_relative",
            regex=patterns.PAYMENT_DAYS_RELATIVE,
            days_group="days",
            base_confidence=0.85,
        ),
        # Skonto patterns
        SkontoPattern(
            name="skonto_german",
            regex=patterns.SKONTO_GERMAN,
            percent_group="percent",
            days_group="days",
            base_confidence=0.90,
        ),
        SkontoPattern(
            name="skonto_german_alt",
            regex=patterns.SKONTO_GERMAN_ALT,
            percent_group="percent",
            days_group="days",
            base_confidence=0.85,
        ),
        SteppedDiscountPattern(
            name="stepped_discount",
            regex=patterns.STEPPED_DISCOUNT,
            base_confidence=0.90,
        ),
        SkontoPattern(
            name="multi_tier_discount",
            regex=patterns.MULTI_TIER_DISCOUNT,
            percent_group="percent",
            days_group="days",
            base_confidence=0.75,  # Lower because it matches individual tiers
        ),
    ]


# Helper functions


def extract_all_discount_tiers(text: str) -> List[DiscountTier]:
    """Extract all discount tiers from text."""
    patterns = PaymentPatterns()
    tiers: List[DiscountTier] = []

    # Try stepped discount first (e.g., "2/10 net 30")
    stepped = patterns.STEPPED_DISCOUNT.search(text)
    if stepped:
        percent = Decimal(stepped.group("percent"))
        discount_days = int(stepped.group("discount_days"))
        net_days = int(stepped.group("net_days"))
        tiers.append(DiscountTier(percent=percent, days=discount_days, raw_text=stepped.group()))
        # Net days as 0% tier
        tiers.append(DiscountTier(percent=Decimal("0"), days=net_days, raw_text="netto"))
        return tiers

    # Try German Skonto patterns
    for match in patterns.SKONTO_GERMAN.finditer(text):
        percent_str = match.group("percent").replace(",", ".")
        tiers.append(DiscountTier(
            percent=Decimal(percent_str),
            days=int(match.group("days")),
            raw_text=match.group(),
        ))

    for match in patterns.SKONTO_GERMAN_ALT.finditer(text):
        percent_str = match.group("percent").replace(",", ".")
        tiers.append(DiscountTier(
            percent=Decimal(percent_str),
            days=int(match.group("days")),
            raw_text=match.group(),
        ))

    # Try flexible pattern (e.g., "Bei Zahlung innerhalb von 10 Tagen gewähren wir 2%")
    for match in patterns.SKONTO_FLEXIBLE.finditer(text):
        percent_str = match.group("percent").replace(",", ".")
        tiers.append(DiscountTier(
            percent=Decimal(percent_str),
            days=int(match.group("days")),
            raw_text=match.group(),
        ))

    # Try multi-tier pattern for remaining tiers
    if not tiers:
        for match in patterns.MULTI_TIER_DISCOUNT.finditer(text):
            percent_str = match.group("percent").replace(",", ".")
            tiers.append(DiscountTier(
                percent=Decimal(percent_str),
                days=int(match.group("days")),
                raw_text=match.group(),
            ))

    # Sort by days (shortest first)
    tiers.sort(key=lambda t: t.days)

    return tiers


def is_immediate_payment(text: str) -> bool:
    """Check if text indicates immediate payment."""
    patterns = PaymentPatterns()
    return bool(
        patterns.PAYMENT_IMMEDIATE.search(text) or
        patterns.CASH_ON_DELIVERY.search(text)
    )


def is_prepayment(text: str) -> bool:
    """Check if text indicates prepayment/proforma."""
    patterns = PaymentPatterns()
    return bool(patterns.PREPAYMENT.search(text))


def is_end_of_month(text: str) -> bool:
    """Check if text indicates end of month payment."""
    patterns = PaymentPatterns()
    return bool(
        patterns.END_OF_MONTH.search(text) or
        patterns.END_OF_FOLLOWING_MONTH.search(text)
    )


def calculate_end_of_month(reference_date: date, following: bool = False) -> date:
    """Calculate end of month date from reference."""
    import calendar

    year = reference_date.year
    month = reference_date.month

    if following:
        month += 1
        if month > 12:
            month = 1
            year += 1

    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def parse_explicit_due_date(
    text: str,
    reference_year: Optional[int] = None,
) -> Optional[date]:
    """Parse explicit due date from text."""
    patterns = PaymentPatterns()
    match = patterns.DUE_DATE_EXPLICIT.search(text)

    if not match:
        return None

    day = int(match.group("day"))
    month_str = match.group("month")
    year_str = match.group("year")

    # Parse month
    month_map = {
        "jan": 1, "januar": 1,
        "feb": 2, "februar": 2,
        "mär": 3, "mar": 3, "märz": 3, "maerz": 3,
        "apr": 4, "april": 4,
        "mai": 5,
        "jun": 6, "juni": 6,
        "jul": 7, "juli": 7,
        "aug": 8, "august": 8,
        "sep": 9, "september": 9,
        "okt": 10, "oktober": 10,
        "nov": 11, "november": 11,
        "dez": 12, "dezember": 12,
    }

    if month_str.isdigit():
        month = int(month_str)
    else:
        month = month_map.get(month_str.lower()[:3], 0)
        if month == 0:
            return None

    # Parse year
    if year_str:
        year = int(year_str)
        if year < 100:
            year += 2000
    else:
        year = reference_year or date.today().year

    try:
        return date(year, month, day)
    except ValueError:
        return None

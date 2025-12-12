"""
Date patterns for German documents.

Patterns for extracting:
- Invoice dates (Rechnungsdatum)
- Due dates (Fälligkeitsdatum)
- Order dates (Bestelldatum)
- Delivery dates (Lieferdatum)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Pattern as RePattern

from app.services.extraction.base import Pattern


@dataclass
class DatePatterns:
    """Collection of date-related regex patterns."""

    # ==========================================================================
    # GERMAN DATE FORMATS
    # ==========================================================================

    # Standard German: "15.02.2024", "15.2.24"
    GERMAN_DATE: RePattern[str] = re.compile(
        r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})",
    )

    # Date with month name: "15. Februar 2024", "15 Feb 2024", "6 April 2020"
    # Supports German, English, and Dutch month names
    GERMAN_DATE_NAMED: RePattern[str] = re.compile(
        r"(?P<day>\d{1,2})\.?\s*"
        r"(?P<month>"
        # Deutsch
        r"jan(?:uar)?|feb(?:ruar)?|m[aä]r(?:z)?|apr(?:il)?|mai|jun(?:i)?|jul(?:i)?|"
        r"aug(?:ust)?|sep(?:tember)?|okt(?:ober)?|nov(?:ember)?|dez(?:ember)?|"
        # Englisch
        r"january|february|march|april|may|june|july|august|"
        r"september|october|november|december|"
        # Niederlaendisch
        r"januari|februari|maart|mei|augustus|oktober"
        r")\s*"
        r"(?P<year>\d{2,4})?",
        re.IGNORECASE,
    )

    # ISO format: "2024-02-15"
    ISO_DATE: RePattern[str] = re.compile(
        r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})",
    )

    # Dashed format: "02-04-20", "6-4-2020" (European day-month-year)
    DASHED_DATE: RePattern[str] = re.compile(
        r"(?P<day>\d{1,2})-(?P<month>\d{1,2})-(?P<year>\d{2,4})",
    )

    # ==========================================================================
    # LABELED DATE PATTERNS
    # ==========================================================================

    # Invoice date: "Rechnungsdatum: 15.02.2024" or "Factuurdatum" (Dutch)
    INVOICE_DATE: RePattern[str] = re.compile(
        r"(?P<label>rechnungsdatum|rechnungs-?datum|invoice\s*date|"
        r"datum\s*der\s*rechnung|ausstellungsdatum|factuurdatum)"
        r"[\s:]*"
        r"(?P<day>\d{1,2})[.\-/](?P<month>\d{1,2})[.\-/](?P<year>\d{2,4})",
        re.IGNORECASE,
    )

    # Due date: "Fällig am 15.02.2024" or "Due Date: 16-04-20"
    DUE_DATE: RePattern[str] = re.compile(
        r"(?P<label>f[aä]llig(?:keit(?:sdatum)?)?|zahlbar\s*bis|"
        r"zu\s*zahlen\s*bis|due\s*date|payment\s*due|vervaldatum)"
        r"[\s:]*(?:am|bis|zum)?\s*"
        r"(?P<day>\d{1,2})[.\-/](?P<month>\d{1,2})[.\-/](?P<year>\d{2,4})",
        re.IGNORECASE,
    )

    # Order date: "Bestelldatum: 15.02.2024"
    ORDER_DATE: RePattern[str] = re.compile(
        r"(?P<label>bestelldatum|bestell-?datum|order\s*date|"
        r"auftragsdatum|auftrags-?datum)"
        r"[\s:]*"
        r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})",
        re.IGNORECASE,
    )

    # Delivery date: "Lieferdatum: 15.02.2024"
    DELIVERY_DATE: RePattern[str] = re.compile(
        r"(?P<label>lieferdatum|liefer-?datum|delivery\s*date|"
        r"versanddatum|versand-?datum|shipping\s*date)"
        r"[\s:]*"
        r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})",
        re.IGNORECASE,
    )

    # Service period: "Leistungszeitraum: 01.01.2024 - 31.01.2024"
    SERVICE_PERIOD: RePattern[str] = re.compile(
        r"(?P<label>leistungszeitraum|leistungs-?zeitraum|"
        r"abrechnungszeitraum|service\s*period)"
        r"[\s:]*"
        r"(?P<start_day>\d{1,2})\.(?P<start_month>\d{1,2})\.(?P<start_year>\d{2,4})"
        r"\s*[-–bis]+\s*"
        r"(?P<end_day>\d{1,2})\.(?P<end_month>\d{1,2})\.(?P<end_year>\d{2,4})",
        re.IGNORECASE,
    )

    # Generic "Datum:" label
    GENERIC_DATE: RePattern[str] = re.compile(
        r"(?P<label>datum)"
        r"[\s:]*"
        r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})",
        re.IGNORECASE,
    )


# Month name to number mapping (German, English, Dutch)
MONTH_MAP: Dict[str, int] = {
    # Januar/January/Januari
    "jan": 1, "januar": 1, "january": 1, "januari": 1,
    # Februar/February/Februari
    "feb": 2, "februar": 2, "february": 2, "februari": 2,
    # Maerz/March/Maart
    "mär": 3, "mar": 3, "märz": 3, "maerz": 3, "march": 3, "maart": 3,
    # April (same in all)
    "apr": 4, "april": 4,
    # Mai/May/Mei
    "mai": 5, "may": 5, "mei": 5,
    # Juni/June/Juni
    "jun": 6, "juni": 6, "june": 6,
    # Juli/July/Juli
    "jul": 7, "juli": 7, "july": 7,
    # August/August/Augustus
    "aug": 8, "august": 8, "augustus": 8,
    # September (same in all)
    "sep": 9, "september": 9,
    # Oktober/October/Oktober
    "okt": 10, "oktober": 10, "october": 10,
    # November (same in all)
    "nov": 11, "november": 11,
    # Dezember/December/December
    "dez": 12, "dezember": 12, "december": 12,
}


class GermanDatePattern(Pattern[date]):
    """Pattern for extracting German-format dates."""

    def __init__(
        self,
        name: str,
        regex: RePattern[str],
        base_confidence: float = 0.85,
        reference_year: Optional[int] = None,
    ) -> None:
        super().__init__(name, regex, base_confidence)
        self.reference_year = reference_year or date.today().year

    def normalize(self, value: str, groups: Dict[str, str]) -> date:
        """Parse date components to date object."""
        day = int(groups["day"])

        # Parse month (could be number or name)
        month_str = groups["month"]
        if month_str.isdigit():
            month = int(month_str)
        else:
            month = MONTH_MAP.get(month_str.lower()[:3], 0)
            if month == 0:
                raise ValueError(f"Unbekannter Monat: {month_str}")

        # Parse year
        year_str = groups.get("year", "")
        if year_str:
            year = int(year_str)
            if year < 100:
                # Two-digit year: assume 20xx for 00-30, 19xx for 31-99
                year = 2000 + year if year <= 30 else 1900 + year
        else:
            year = self.reference_year

        return date(year, month, day)

    def calculate_confidence(
        self,
        value: str,
        context: str,
        groups: Dict[str, str],
    ) -> float:
        """Adjust confidence based on context."""
        confidence = self.base_confidence
        context_lower = context.lower()

        # Boost for labeled dates
        if any(kw in context_lower for kw in ["datum", "date", "fällig", "rechnung"]):
            confidence += 0.1

        # Reduce for potential phone numbers or article numbers
        if re.search(r"tel|fax|art|nr\.", context_lower):
            confidence -= 0.3

        return min(0.99, max(0.1, confidence))


def get_date_patterns() -> List[Pattern[Any]]:
    """Get all date patterns for registration."""
    patterns = DatePatterns()

    return [
        GermanDatePattern(
            name="invoice_date",
            regex=patterns.INVOICE_DATE,
            base_confidence=0.95,
        ),
        GermanDatePattern(
            name="due_date",
            regex=patterns.DUE_DATE,
            base_confidence=0.95,
        ),
        GermanDatePattern(
            name="order_date",
            regex=patterns.ORDER_DATE,
            base_confidence=0.95,
        ),
        GermanDatePattern(
            name="delivery_date",
            regex=patterns.DELIVERY_DATE,
            base_confidence=0.90,
        ),
        GermanDatePattern(
            name="generic_date",
            regex=patterns.GENERIC_DATE,
            base_confidence=0.75,
        ),
        GermanDatePattern(
            name="german_date",
            regex=patterns.GERMAN_DATE,
            base_confidence=0.70,
        ),
        GermanDatePattern(
            name="german_date_named",
            regex=patterns.GERMAN_DATE_NAMED,
            base_confidence=0.80,
        ),
        GermanDatePattern(
            name="iso_date",
            regex=patterns.ISO_DATE,
            base_confidence=0.85,
        ),
        GermanDatePattern(
            name="dashed_date",
            regex=patterns.DASHED_DATE,
            base_confidence=0.75,
        ),
    ]


def parse_german_date(
    text: str,
    reference_year: Optional[int] = None,
) -> Optional[date]:
    """
    Parse a German date from text.

    Handles:
    - "15.02.2024"
    - "15.2.24"
    - "15. Februar 2024"

    Args:
        text: Text containing a date
        reference_year: Year to use if not specified

    Returns:
        Parsed date or None
    """
    patterns = DatePatterns()
    ref_year = reference_year or date.today().year

    # Try standard German format first
    match = patterns.GERMAN_DATE.search(text)
    if match:
        try:
            day = int(match.group("day"))
            month = int(match.group("month"))
            year = int(match.group("year"))
            if year < 100:
                year = 2000 + year if year <= 30 else 1900 + year
            return date(year, month, day)
        except ValueError:
            pass

    # Try named month format
    match = patterns.GERMAN_DATE_NAMED.search(text)
    if match:
        try:
            day = int(match.group("day"))
            month_str = match.group("month")
            month = MONTH_MAP.get(month_str.lower()[:3], 0)
            year_str = match.group("year")
            year = int(year_str) if year_str else ref_year
            if year < 100:
                year = 2000 + year if year <= 30 else 1900 + year
            return date(year, month, day)
        except (ValueError, KeyError):
            pass

    # Try ISO format
    match = patterns.ISO_DATE.search(text)
    if match:
        try:
            year = int(match.group("year"))
            month = int(match.group("month"))
            day = int(match.group("day"))
            return date(year, month, day)
        except ValueError:
            pass

    # Try dashed format: "02-04-20", "6-4-2020"
    match = patterns.DASHED_DATE.search(text)
    if match:
        try:
            day = int(match.group("day"))
            month = int(match.group("month"))
            year = int(match.group("year"))
            if year < 100:
                year = 2000 + year if year <= 30 else 1900 + year
            return date(year, month, day)
        except ValueError:
            pass

    return None


def extract_invoice_date(text: str) -> Optional[date]:
    """Extract invoice date from labeled pattern."""
    patterns = DatePatterns()

    match = patterns.INVOICE_DATE.search(text)
    if match:
        try:
            day = int(match.group("day"))
            month = int(match.group("month"))
            year = int(match.group("year"))
            if year < 100:
                year = 2000 + year
            return date(year, month, day)
        except ValueError:
            pass

    return None


def extract_due_date(text: str) -> Optional[date]:
    """Extract due date from labeled pattern."""
    patterns = DatePatterns()

    match = patterns.DUE_DATE.search(text)
    if match:
        try:
            day = int(match.group("day"))
            month = int(match.group("month"))
            year = int(match.group("year"))
            if year < 100:
                year = 2000 + year
            return date(year, month, day)
        except ValueError:
            pass

    return None

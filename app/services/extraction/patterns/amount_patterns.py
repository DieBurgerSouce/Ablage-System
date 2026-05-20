"""
Amount patterns for German documents.

Comprehensive patterns for extracting monetary amounts:
- Net amounts (Nettobetrag)
- Gross amounts (Bruttobetrag)
- VAT amounts (MwSt)
- Currency detection
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Pattern as RePattern

from app.services.extraction.base import (
    AmountType,
    Currency,
    ExtractedAmount,
    Pattern,
    detect_currency,
    get_line_position,
    parse_german_decimal,
)


class AmountPatterns:
    """Collection of amount-related regex patterns."""

    # ==========================================================================
    # GENERIC AMOUNT PATTERNS
    # ==========================================================================

    # German format amount: "1.234,56" or "1234,56"
    # Requires comma + 2 decimals OR dot-separated thousands with optional decimals
    GERMAN_AMOUNT: RePattern[str] = re.compile(
        r"(?P<amount>\d{1,3}(?:\.\d{3})+(?:,\d{2})?|"  # With thousands separators
        r"\d+,\d{2})"  # Without thousands, but with decimals
        r"\s*(?P<currency>€|EUR|Euro|CHF|SFr|USD|\$)?",
        re.IGNORECASE,
    )

    # Amount with currency prefix: "EUR 1.234,56", "€ 1.234,56"
    CURRENCY_PREFIX_AMOUNT: RePattern[str] = re.compile(
        r"(?P<currency>€|EUR|Euro|CHF|SFr|USD|\$)\s*"
        r"(?P<amount>\d{1,3}(?:\.\d{3})*(?:,\d{2})?|"
        r"\d+(?:[,\.]\d{2})?)",
        re.IGNORECASE,
    )

    # International format: "1,234.56" (for US documents)
    INTERNATIONAL_AMOUNT: RePattern[str] = re.compile(
        r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"
        r"\s*(?P<currency>€|EUR|USD|\$)?",
    )

    # ==========================================================================
    # LABELED AMOUNT PATTERNS
    # ==========================================================================

    # Net amount with label - requires proper decimal format
    NET_AMOUNT: RePattern[str] = re.compile(
        r"(?P<label>netto(?:betrag)?|zwischensumme|summe\s*netto|"
        r"net(?:\s*amount)?|subtotal)"
        r"[\s:]*"
        r"(?P<currency>€|EUR|CHF)?\s*"
        r"(?P<amount>\d{1,3}(?:\.\d{3})+(?:,\d{2})?|"  # With thousands
        r"\d+,\d{2})"  # Without thousands, must have decimals
        r"\s*(?P<currency2>€|EUR|CHF)?",
        re.IGNORECASE,
    )

    # Gross amount with label - requires proper decimal format
    GROSS_AMOUNT: RePattern[str] = re.compile(
        r"(?P<label>brutto(?:betrag)?|gesamt(?:betrag)?|endbetrag|"
        r"rechnungsbetrag|zu\s*zahlen(?:der?\s*betrag)?|"
        r"total(?:\s*amount)?|invoice\s*total|"
        r"summe\s*brutto|gesamtsumme)"
        r"[\s:]*"
        r"(?P<currency>€|EUR|CHF)?\s*"
        r"(?P<amount>\d{1,3}(?:\.\d{3})+(?:,\d{2})?|"  # With thousands
        r"\d+,\d{2})"  # Without thousands, must have decimals
        r"\s*(?P<currency2>€|EUR|CHF)?",
        re.IGNORECASE,
    )

    # VAT with rate: "19% MwSt 234,56" or "MwSt 19% 234,56"
    VAT_WITH_RATE: RePattern[str] = re.compile(
        r"(?:(?P<rate1>\d{1,2}(?:[,\.]\d)?)\s*%?\s*)?"
        r"(?P<label>mwst\.?|ust\.?|mehrwertsteuer|umsatzsteuer|"
        r"vat|tax|steuer(?:betrag)?)"
        r"(?:\s*(?P<rate2>\d{1,2}(?:[,\.]\d)?)\s*%)?"
        r"[\s:]*"
        r"(?P<currency>€|EUR|CHF)?\s*"
        r"(?P<amount>\d{1,3}(?:\.\d{3})*(?:,\d{2})?|"
        r"\d+(?:,\d{2})?)"
        r"\s*(?P<currency2>€|EUR|CHF)?",
        re.IGNORECASE,
    )

    # VAT amount only (no rate): "MwSt: 234,56"
    VAT_AMOUNT_ONLY: RePattern[str] = re.compile(
        r"(?P<label>mwst\.?|ust\.?|mehrwertsteuer|umsatzsteuer|vat|tax)"
        r"[\s:]*"
        r"(?P<currency>€|EUR|CHF)?\s*"
        r"(?P<amount>\d{1,3}(?:\.\d{3})*(?:,\d{2})?|"
        r"\d+(?:,\d{2})?)",
        re.IGNORECASE,
    )

    # VAT rate only: "MwSt 19%", "19% Steuer"
    VAT_RATE_ONLY: RePattern[str] = re.compile(
        r"(?:(?P<label>mwst\.?|ust\.?|mehrwertsteuer|umsatzsteuer|"
        r"vat|tax|steuer)\s*)?"
        r"(?P<rate>\d{1,2}(?:[,\.]\d)?)\s*%"
        r"(?:\s*(?P<label2>mwst\.?|ust\.?|steuer))?",
        re.IGNORECASE,
    )

    # ==========================================================================
    # CONTEXT INDICATORS
    # ==========================================================================

    # Indicators that suggest an amount is NET
    NET_INDICATORS: frozenset[str] = frozenset([
        "netto", "nettobetrag", "zwischensumme", "summe netto",
        "net", "subtotal", "net amount", "ohne mwst", "ohne steuer",
        "exkl", "excl", "exclusive", "exklusive",
    ])

    # Indicators that suggest an amount is GROSS
    GROSS_INDICATORS: frozenset[str] = frozenset([
        "brutto", "bruttobetrag", "gesamt", "gesamtbetrag",
        "endbetrag", "rechnungsbetrag", "zu zahlen", "zahlbetrag",
        "total", "grand total", "invoice total", "summe",
        "inkl", "incl", "inclusive", "inklusive", "inkl. mwst",
    ])

    # Indicators that suggest an amount is VAT
    VAT_INDICATORS: frozenset[str] = frozenset([
        "mwst", "ust", "mehrwertsteuer", "umsatzsteuer",
        "vat", "tax", "steuer", "steuerbetrag",
        "19%", "7%", "0%",
    ])


class GermanAmountPattern(Pattern[Decimal]):
    """Pattern for extracting German-format amounts."""

    def __init__(
        self,
        name: str,
        regex: RePattern[str],
        amount_group: str = "amount",
        base_confidence: float = 0.7,
    ) -> None:
        super().__init__(name, regex, base_confidence)
        self.amount_group = amount_group

    def normalize(self, value: str, groups: Dict[str, str]) -> Decimal:
        """Parse amount as Decimal."""
        amount_str = groups.get(self.amount_group, value)
        return parse_german_decimal(amount_str)

    def calculate_confidence(
        self,
        value: str,
        context: str,
        groups: Dict[str, str],
    ) -> float:
        """Adjust confidence based on context."""
        confidence = self.base_confidence
        context_lower = context.lower()

        # Boost for currency symbols
        if "€" in value or "eur" in value.lower():
            confidence += 0.1

        # Boost for clear amount context
        if any(kw in context_lower for kw in ["betrag", "summe", "preis", "total"]):
            confidence += 0.1

        # Reduce for dates or phone numbers
        if re.search(r"\d{2}\.\d{2}\.\d{2,4}", context):
            confidence -= 0.3

        # Reduce for percentages
        if "%" in context and "mwst" not in context_lower:
            confidence -= 0.2

        return min(0.99, max(0.1, confidence))


class LabeledAmountPattern(Pattern[ExtractedAmount]):
    """Pattern for extracting amounts with labels (Net, Gross, VAT)."""

    def __init__(
        self,
        name: str,
        regex: RePattern[str],
        amount_type: AmountType,
        amount_group: str = "amount",
        rate_group: Optional[str] = None,
        base_confidence: float = 0.85,
    ) -> None:
        super().__init__(name, regex, base_confidence)
        self.amount_type = amount_type
        self.amount_group = amount_group
        self.rate_group = rate_group

    def normalize(self, value: str, groups: Dict[str, str]) -> ExtractedAmount:
        """Extract amount with type classification."""
        amount_str = groups.get(self.amount_group, "")
        amount_value = parse_german_decimal(amount_str)

        # Detect currency
        currency_str = groups.get("currency") or groups.get("currency2") or ""
        currency = detect_currency(currency_str or value)

        # Extract VAT rate if present
        vat_rate = None
        if self.rate_group:
            rate_str = groups.get(self.rate_group) or groups.get("rate1") or groups.get("rate2")
            if rate_str:
                rate_str = rate_str.replace(",", ".")
                vat_rate = Decimal(rate_str)

        return ExtractedAmount(
            value=amount_value,
            currency=currency,
            amount_type=self.amount_type,
            confidence=self.base_confidence,
            raw_text=value,
            vat_rate=vat_rate,
        )


def get_amount_patterns() -> List[Pattern[Any]]:
    """Get all amount patterns for registration."""
    patterns = AmountPatterns()

    return [
        # Labeled patterns (highest confidence)
        LabeledAmountPattern(
            name="net_amount_labeled",
            regex=patterns.NET_AMOUNT,
            amount_type=AmountType.NET,
            base_confidence=0.90,
        ),
        LabeledAmountPattern(
            name="gross_amount_labeled",
            regex=patterns.GROSS_AMOUNT,
            amount_type=AmountType.GROSS,
            base_confidence=0.90,
        ),
        LabeledAmountPattern(
            name="vat_with_rate",
            regex=patterns.VAT_WITH_RATE,
            amount_type=AmountType.VAT,
            rate_group="rate1",
            base_confidence=0.92,
        ),
        LabeledAmountPattern(
            name="vat_amount_only",
            regex=patterns.VAT_AMOUNT_ONLY,
            amount_type=AmountType.VAT,
            base_confidence=0.85,
        ),
        # Generic patterns (lower confidence)
        GermanAmountPattern(
            name="german_amount",
            regex=patterns.GERMAN_AMOUNT,
            base_confidence=0.60,
        ),
        GermanAmountPattern(
            name="currency_prefix_amount",
            regex=patterns.CURRENCY_PREFIX_AMOUNT,
            base_confidence=0.70,
        ),
    ]


def extract_all_amounts(text: str, context_window: int = 30) -> List[ExtractedAmount]:
    """
    Extract all amounts from text with context analysis.

    Args:
        text: Source text
        context_window: Characters to capture around each amount

    Returns:
        List of ExtractedAmount objects sorted by position
    """
    patterns = AmountPatterns()
    amounts: List[ExtractedAmount] = []
    seen_positions: set[tuple[int, int]] = set()

    # First pass: Labeled amounts (highest confidence)
    for regex, amount_type in [
        (patterns.NET_AMOUNT, AmountType.NET),
        (patterns.GROSS_AMOUNT, AmountType.GROSS),
        (patterns.VAT_WITH_RATE, AmountType.VAT),
        (patterns.VAT_AMOUNT_ONLY, AmountType.VAT),
    ]:
        for match in regex.finditer(text):
            start, end = match.span()
            if (start, end) in seen_positions:
                continue
            seen_positions.add((start, end))

            try:
                amount_str = match.group("amount")
                amount_value = parse_german_decimal(amount_str)

                # Get context
                ctx_start = max(0, start - context_window)
                ctx_end = min(len(text), end + context_window)
                context_before = text[ctx_start:start]
                context_after = text[end:ctx_end]

                # Extract VAT rate if present
                vat_rate = None
                if amount_type == AmountType.VAT:
                    rate_str = (
                        match.groupdict().get("rate1") or
                        match.groupdict().get("rate2") or
                        match.groupdict().get("rate")
                    )
                    if rate_str:
                        vat_rate = Decimal(rate_str.replace(",", "."))

                amounts.append(ExtractedAmount(
                    value=amount_value,
                    currency=detect_currency(match.group()),
                    amount_type=amount_type,
                    confidence=0.90,
                    position=(start, end),
                    context_before=context_before,
                    context_after=context_after,
                    line_position=get_line_position(text, (start, end)),
                    raw_text=match.group(),
                    vat_rate=vat_rate,
                ))
            except (ValueError, TypeError):
                continue

    # Second pass: Generic amounts (classify by context)
    for match in patterns.GERMAN_AMOUNT.finditer(text):
        start, end = match.span()

        # Skip if already found as labeled amount
        if any(abs(start - pos[0]) < 5 for pos in seen_positions):
            continue
        seen_positions.add((start, end))

        try:
            amount_str = match.group("amount")
            amount_value = parse_german_decimal(amount_str)

            # Skip very small amounts (likely not financial)
            if amount_value < Decimal("0.01"):
                continue

            # Get context
            ctx_start = max(0, start - context_window)
            ctx_end = min(len(text), end + context_window)
            context_before = text[ctx_start:start]
            context_after = text[end:ctx_end]
            full_context = (context_before + context_after).lower()

            # Classify by context
            amount_type = _classify_amount_by_context(full_context)
            confidence = 0.60 if amount_type == AmountType.UNKNOWN else 0.75

            amounts.append(ExtractedAmount(
                value=amount_value,
                currency=detect_currency(match.group()),
                amount_type=amount_type,
                confidence=confidence,
                position=(start, end),
                context_before=context_before,
                context_after=context_after,
                line_position=get_line_position(text, (start, end)),
                raw_text=match.group(),
            ))
        except (ValueError, TypeError):
            continue

    # Sort by position
    amounts.sort(key=lambda a: a.position[0])

    return amounts


def _classify_amount_by_context(context: str) -> AmountType:
    """Classify amount type based on surrounding context."""
    context_lower = context.lower()
    patterns = AmountPatterns()

    # Check VAT indicators first (most specific)
    for indicator in patterns.VAT_INDICATORS:
        if indicator in context_lower:
            return AmountType.VAT

    # Check NET indicators
    for indicator in patterns.NET_INDICATORS:
        if indicator in context_lower:
            return AmountType.NET

    # Check GROSS indicators
    for indicator in patterns.GROSS_INDICATORS:
        if indicator in context_lower:
            return AmountType.GROSS

    return AmountType.UNKNOWN


def extract_vat_rate(text: str) -> Optional[Decimal]:
    """Extract VAT rate from text."""
    patterns = AmountPatterns()

    # Try VAT with rate first
    match = patterns.VAT_WITH_RATE.search(text)
    if match:
        rate_str = match.group("rate1") or match.group("rate2")
        if rate_str:
            return Decimal(rate_str.replace(",", "."))

    # Try rate-only pattern
    match = patterns.VAT_RATE_ONLY.search(text)
    if match:
        rate_str = match.group("rate")
        if rate_str:
            return Decimal(rate_str.replace(",", "."))

    return None

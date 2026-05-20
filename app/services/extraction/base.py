"""
Base classes for the extraction module.

Provides foundational abstractions for pattern matching and extraction.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, Pattern as RePattern, Tuple, TypeVar

import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class Currency(Enum):
    """Supported currencies."""
    EUR = "EUR"
    CHF = "CHF"
    USD = "USD"
    UNKNOWN = "UNKNOWN"


class AmountType(Enum):
    """Types of monetary amounts."""
    NET = "net"
    GROSS = "gross"
    VAT = "vat"
    DISCOUNT = "discount"
    TOTAL = "total"
    SUBTOTAL = "subtotal"
    UNKNOWN = "unknown"


class Severity(Enum):
    """Validation severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class PatternMatch:
    """Result of a pattern match with context information."""

    value: str
    """The raw matched text."""

    normalized_value: object
    """The normalized/parsed value (e.g., Decimal for amounts)."""

    confidence: float
    """Confidence score 0.0 - 1.0."""

    pattern_name: str
    """Name of the pattern that matched."""

    position: Tuple[int, int]
    """Start and end position in text (character indices)."""

    context: str
    """Surrounding context (typically 30 chars before/after)."""

    groups: Dict[str, str] = field(default_factory=dict)
    """Named capture groups from the regex match."""

    def __repr__(self) -> str:
        return (
            f"PatternMatch(value='{self.value}', "
            f"normalized={self.normalized_value}, "
            f"confidence={self.confidence:.2f}, "
            f"pattern='{self.pattern_name}')"
        )


@dataclass
class ExtractedAmount:
    """A monetary amount extracted with full context."""

    value: Decimal
    """The numeric amount value."""

    currency: Currency = Currency.EUR
    """The currency (defaults to EUR for German documents)."""

    amount_type: AmountType = AmountType.UNKNOWN
    """Classified type (net, gross, vat, etc.)."""

    confidence: float = 0.0
    """Extraction confidence 0.0 - 1.0."""

    position: Tuple[int, int] = (0, 0)
    """Position in source text."""

    context_before: str = ""
    """Text before the amount (for classification)."""

    context_after: str = ""
    """Text after the amount."""

    line_position: str = "unknown"
    """Position on line: 'left', 'center', 'right'."""

    vat_rate: Optional[Decimal] = None
    """If this is a VAT amount, the associated rate."""

    raw_text: str = ""
    """Original text representation."""


@dataclass
class DiscountTier:
    """A discount tier (e.g., 2% if paid within 10 days)."""

    percent: Decimal
    """Discount percentage."""

    days: int
    """Days to qualify for discount."""

    raw_text: str = ""
    """Original text."""


@dataclass
class DocumentAmounts:
    """Inferred document amounts (net, vat, gross)."""

    net_amount: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None

    net_confidence: float = 0.0
    gross_confidence: float = 0.0
    vat_confidence: float = 0.0

    all_amounts: List[ExtractedAmount] = field(default_factory=list)
    """All extracted amounts for reference."""

    def is_consistent(self, tolerance: Decimal = Decimal("0.10")) -> bool:
        """Check if net + vat = gross within tolerance."""
        if self.net_amount and self.vat_amount and self.gross_amount:
            expected = self.net_amount + self.vat_amount
            return abs(expected - self.gross_amount) <= tolerance
        return True  # Can't validate if missing values


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    """Whether the validation passed."""

    field_name: str
    """The field being validated."""

    validation_type: str
    """Type of validation (e.g., 'amount_consistency')."""

    message: str
    """Human-readable message (German for user-facing)."""

    severity: Severity
    """Error, warning, or info."""

    suggested_fix: Optional[str] = None
    """Optional suggestion for fixing the issue."""

    details: Dict[str, Any] = field(default_factory=dict)
    """Additional details for debugging."""


@dataclass
class ExtractionConfig:
    """Configuration for extraction behavior."""

    # Amount detection
    context_window: int = 30
    """Characters before/after to capture for context."""

    min_amount_confidence: float = 0.5
    """Minimum confidence to include an amount."""

    # Line items
    header_keyword_threshold: int = 2
    """Minimum header keywords to identify a header row."""

    header_search_depth: int = 5
    """How many rows to search for headers."""

    # Payment terms
    validate_due_date: bool = True
    """Whether to validate calculated vs explicit due dates."""

    due_date_tolerance_days: int = 3
    """Tolerance for due date validation."""

    # Validation
    amount_tolerance: Decimal = Decimal("0.10")
    """Tolerance for amount consistency (Net + VAT = Gross)."""

    line_item_sum_tolerance_percent: Decimal = Decimal("1.0")
    """Tolerance for line item sum vs net amount."""


T = TypeVar("T")


class Pattern(ABC, Generic[T]):
    """Abstract base class for extraction patterns."""

    def __init__(
        self,
        name: str,
        regex: RePattern[str],
        base_confidence: float = 0.8,
    ) -> None:
        self.name = name
        self.regex = regex
        self.base_confidence = base_confidence

    def find_all(self, text: str, context_window: int = 30) -> List[PatternMatch]:
        """Find all matches of this pattern in text."""
        matches: List[PatternMatch] = []

        for match in self.regex.finditer(text):
            start, end = match.span()

            # Extract context
            context_start = max(0, start - context_window)
            context_end = min(len(text), end + context_window)
            context = text[context_start:context_end]

            # Extract named groups
            groups = {k: v for k, v in match.groupdict().items() if v is not None}

            try:
                normalized = self.normalize(match.group(), groups)
                confidence = self.calculate_confidence(match.group(), context, groups)

                matches.append(PatternMatch(
                    value=match.group(),
                    normalized_value=normalized,
                    confidence=confidence,
                    pattern_name=self.name,
                    position=(start, end),
                    context=context,
                    groups=groups,
                ))
            except (ValueError, TypeError) as e:
                logger.debug(
                    "pattern_normalization_failed",
                    pattern=self.name,
                    value=match.group(),
                    **safe_error_log(e),
                )
                continue

        return matches

    @abstractmethod
    def normalize(self, value: str, groups: Dict[str, str]) -> T:
        """Normalize the matched value to the target type."""
        pass

    def calculate_confidence(
        self,
        value: str,
        context: str,
        groups: Dict[str, str],
    ) -> float:
        """Calculate confidence for this match. Override for custom logic."""
        return self.base_confidence


class PatternRegistry:
    """
    Central registry for extraction patterns.

    Organizes patterns by category (payment, amount, date, etc.)
    and provides unified matching interface.
    """

    def __init__(self) -> None:
        self._patterns: Dict[str, List[Pattern[Any]]] = {}
        self._config = ExtractionConfig()

    def register(self, category: str, pattern: Pattern[Any]) -> None:
        """Register a pattern in a category."""
        if category not in self._patterns:
            self._patterns[category] = []
        self._patterns[category].append(pattern)
        logger.debug(
            "pattern_registered",
            category=category,
            pattern_name=pattern.name,
        )

    def register_all(self, category: str, patterns: List[Pattern[Any]]) -> None:
        """Register multiple patterns in a category."""
        for pattern in patterns:
            self.register(category, pattern)

    def match_all(
        self,
        category: str,
        text: str,
        min_confidence: float = 0.0,
    ) -> List[PatternMatch]:
        """
        Match all patterns in category against text.

        Returns matches sorted by confidence (highest first).
        """
        results: List[PatternMatch] = []

        for pattern in self._patterns.get(category, []):
            matches = pattern.find_all(text, self._config.context_window)
            results.extend(matches)

        # Filter by minimum confidence
        results = [m for m in results if m.confidence >= min_confidence]

        # Sort by confidence descending
        return sorted(results, key=lambda m: m.confidence, reverse=True)

    def match_first(
        self,
        category: str,
        text: str,
        min_confidence: float = 0.0,
    ) -> Optional[PatternMatch]:
        """Get the highest confidence match, or None."""
        matches = self.match_all(category, text, min_confidence)
        return matches[0] if matches else None

    def get_patterns(self, category: str) -> List[Pattern[Any]]:
        """Get all patterns in a category."""
        return self._patterns.get(category, [])

    def categories(self) -> List[str]:
        """List all registered categories."""
        return list(self._patterns.keys())

    def set_config(self, config: ExtractionConfig) -> None:
        """Update configuration."""
        self._config = config


# Utility functions for German number parsing

def parse_german_decimal(text: str) -> Decimal:
    """
    Parse German-format decimal number.

    Handles:
    - "1.234,56" (German with thousands separator)
    - "1234,56" (German without thousands separator)
    - "1234.56" (International format)

    Args:
        text: The number string to parse

    Returns:
        Decimal value

    Raises:
        ValueError: If the text cannot be parsed
    """
    # Clean the text
    cleaned = text.strip()
    cleaned = re.sub(r"[€$CHF\s]", "", cleaned)
    cleaned = re.sub(r"EUR|USD|CHF", "", cleaned, flags=re.IGNORECASE)

    if not cleaned:
        raise ValueError(f"Leerer Betrag: '{text}'")

    # Count dots and commas
    dots = cleaned.count(".")
    commas = cleaned.count(",")

    if commas == 1 and dots == 0:
        # "1234,56" - German without thousands
        cleaned = cleaned.replace(",", ".")
    elif dots >= 1 and commas == 1:
        # "1.234,56" - German with thousands
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif dots == 1 and commas == 0:
        # "1234.56" - Could be international or German thousands
        # Check if exactly 3 digits after dot
        parts = cleaned.split(".")
        if len(parts[1]) == 3 and len(parts[0]) <= 3:
            # Likely German thousands separator: "123.456" -> 123456
            cleaned = cleaned.replace(".", "")
        # Otherwise assume decimal point
    elif dots > 1 and commas == 0:
        # "1.234.567" - German thousands only
        cleaned = cleaned.replace(".", "")

    # Handle negative
    is_negative = cleaned.startswith("-") or cleaned.endswith("-")
    cleaned = cleaned.replace("-", "")

    try:
        result = Decimal(cleaned)
        return -result if is_negative else result
    except Exception as e:
        raise ValueError(f"Kann '{text}' nicht als Betrag parsen: {e}") from e


def detect_currency(text: str) -> Currency:
    """Detect currency from text context."""
    text_lower = text.lower()

    if "€" in text or "eur" in text_lower:
        return Currency.EUR
    if "chf" in text_lower or "sfr" in text_lower:
        return Currency.CHF
    if "$" in text or "usd" in text_lower:
        return Currency.USD

    return Currency.EUR  # Default for German documents


def get_line_position(text: str, position: Tuple[int, int]) -> str:
    """
    Determine if a match is on the left, center, or right of its line.

    Useful for amount classification (totals are typically right-aligned).
    """
    start, end = position

    # Find line boundaries
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)

    line_length = line_end - line_start
    if line_length == 0:
        return "unknown"

    # Calculate relative position
    match_center = (start + end) / 2 - line_start
    relative_position = match_center / line_length

    if relative_position < 0.33:
        return "left"
    elif relative_position > 0.66:
        return "right"
    else:
        return "center"

"""Bank statement parsers for various formats.

Supported formats:
- MT940 (SWIFT) - Universal bank statement format
- CAMT.053 (ISO 20022) - Modern XML format
- CSV - Bank-specific CSV formats
"""

from .base import (
    BaseParser,
    ParsedTransaction,
    ParseResult,
    ParserRegistry,
    detect_format,
)
from .mt940_parser import MT940Parser
from .camt053_parser import CAMT053Parser
from .csv_parser import GenericCSVParser

__all__ = [
    "BaseParser",
    "ParsedTransaction",
    "ParseResult",
    "ParserRegistry",
    "detect_format",
    "MT940Parser",
    "CAMT053Parser",
    "GenericCSVParser",
]

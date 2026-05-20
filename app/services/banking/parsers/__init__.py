"""Bank statement parsers for various formats.

Supported formats:
- MT940 (SWIFT) - Universal bank statement format
- CAMT.053 (ISO 20022) - Modern XML format
- CSV - Bank-specific CSV formats
"""

import structlog
from typing import Optional, Type

from .base import (
    BaseParser,
    ParsedTransaction,
    ParseResult,
    ParserRegistry,
    detect_format,
)

logger = structlog.get_logger(__name__)

# Optional imports - not all dependencies may be installed
MT940Parser: Optional[Type[BaseParser]] = None
CAMT053Parser: Optional[Type[BaseParser]] = None
GenericCSVParser: Optional[Type[BaseParser]] = None

try:
    from .mt940_parser import MT940Parser as _MT940Parser
    MT940Parser = _MT940Parser
except ImportError as e:
    logger.warning(f"MT940Parser nicht verfügbar: {e}")

try:
    from .camt053_parser import CAMT053Parser as _CAMT053Parser
    CAMT053Parser = _CAMT053Parser
except ImportError as e:
    logger.warning(f"CAMT053Parser nicht verfügbar: {e}")

try:
    from .csv_parser import GenericCSVParser as _GenericCSVParser
    GenericCSVParser = _GenericCSVParser
except ImportError as e:
    logger.warning(f"GenericCSVParser nicht verfügbar: {e}")

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

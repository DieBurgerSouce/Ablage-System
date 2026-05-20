"""Bank-specific CSV parsers.

Spezialisierte Parser für CSV-Exporte verschiedener deutscher Banken.
Jede Bank hat eigene Spaltenbezeichnungen und Formate.
"""

from .sparkasse import SparkasseCSVParser
from .volksbank import VolksbankCSVParser
from .deutsche_bank import DeutscheBankCSVParser
from .commerzbank import CommerzbankCSVParser
from .ing import INGCSVParser
from .n26 import N26CSVParser
from .dkb import DKBCSVParser

__all__ = [
    "SparkasseCSVParser",
    "VolksbankCSVParser",
    "DeutscheBankCSVParser",
    "CommerzbankCSVParser",
    "INGCSVParser",
    "N26CSVParser",
    "DKBCSVParser",
]

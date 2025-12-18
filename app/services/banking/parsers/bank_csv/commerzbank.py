"""Commerzbank CSV Parser.

Parst CSV-Exporte der Commerzbank.
Format: Semikolon-separiert, UTF-8 mit BOM.
"""

from typing import Optional, Union, Dict, List

from ..csv_parser import GenericCSVParser
from ..base import ParserRegistry
from ...models import ImportFormat


@ParserRegistry.register
class CommerzbankCSVParser(GenericCSVParser):
    """Parser fuer Commerzbank CSV-Kontoauszuege."""

    FORMAT = ImportFormat.CSV_COMMERZBANK
    FORMAT_VARIANT = "commerzbank"

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Pruefe auf Commerzbank-Format."""
        text = cls._decode_content(content)
        if not text:
            return 0.0

        # Commerzbank CSV beginnt oft mit UTF-8 BOM
        if text.startswith("\ufeff"):
            text = text[1:]

        header = text.split("\n")[0].lower() if text else ""

        # Commerzbank-spezifische Spalten
        coba_markers = [
            "buchungstag",
            "wertstellung",
            "umsatzart",
            "buchungstext",
            "auftraggeber / begünstigter",
        ]

        if "auftraggeber / begünstigter" in header or "auftraggeber / beguenstigter" in header:
            return 0.95

        matches = sum(1 for m in coba_markers if m in header)

        if matches >= 3:
            return 0.85
        elif matches >= 2:
            return 0.6

        return 0.0

    def _map_columns(self, fieldnames: List[str]) -> Dict[str, str]:
        """Commerzbank-spezifisches Spalten-Mapping."""
        mapping = {}

        for field in fieldnames:
            field_lower = field.lower().strip()

            if "buchungstag" in field_lower:
                mapping["booking_date"] = field
            elif "wertstellung" in field_lower or "valuta" in field_lower:
                mapping["value_date"] = field
            elif "betrag" in field_lower and "urspr" not in field_lower:
                mapping["amount"] = field
            elif "waehrung" in field_lower or "währung" in field_lower:
                mapping["currency"] = field
            elif "auftraggeber" in field_lower or "begünstigter" in field_lower:
                mapping["counterparty_name"] = field
            elif "iban" in field_lower:
                mapping["counterparty_iban"] = field
            elif "bic" in field_lower:
                mapping["counterparty_bic"] = field
            elif "buchungstext" in field_lower:
                mapping["reference_text"] = field
            elif "umsatzart" in field_lower:
                mapping["booking_text"] = field

        return mapping

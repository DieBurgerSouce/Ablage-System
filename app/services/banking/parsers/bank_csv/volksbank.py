"""Volksbank/Raiffeisenbank CSV Parser.

Parst CSV-Exporte der Volks- und Raiffeisenbanken.
Format: Semikolon-separiert.
"""

from typing import Optional, Union, Dict, List

from ..csv_parser import GenericCSVParser
from ..base import ParserRegistry
from ...models import ImportFormat


@ParserRegistry.register
class VolksbankCSVParser(GenericCSVParser):
    """Parser für Volksbank/Raiffeisenbank CSV-Kontoauszuege."""

    FORMAT = ImportFormat.CSV_VOLKSBANK
    FORMAT_VARIANT = "volksbank"

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Prüfe auf Volksbank-Format."""
        text = cls._decode_content(content)
        if not text:
            return 0.0

        header = text.split("\n")[0].lower() if text else ""

        # Charakteristische VR-Spalten
        vr_markers = [
            "buchungstag",
            "empfänger/zahlungspflichtiger",
            "verwendungszweck",
            "kundenreferenz",
        ]

        # VR verwendet oft "Empfänger/Zahlungspflichtiger" statt "Begünstigter"
        if "empfänger/zahlungspflichtiger" in header or "empfaenger/zahlungspflichtiger" in header:
            return 0.9

        matches = sum(1 for m in vr_markers if m in header)

        if matches >= 3:
            return 0.85
        elif matches >= 2:
            return 0.6

        return 0.0

    def _map_columns(self, fieldnames: List[str]) -> Dict[str, str]:
        """Volksbank-spezifisches Spalten-Mapping."""
        mapping = {}

        for field in fieldnames:
            field_lower = field.lower().strip()

            if "buchungstag" in field_lower:
                mapping["booking_date"] = field
            elif "valuta" in field_lower or "wertstellung" in field_lower:
                mapping["value_date"] = field
            elif "betrag" in field_lower or "umsatz" in field_lower:
                mapping["amount"] = field
            elif "währung" in field_lower or "währung" in field_lower:
                mapping["currency"] = field
            elif "empfänger" in field_lower or "empfänger" in field_lower:
                mapping["counterparty_name"] = field
            elif "iban" in field_lower or "kontonummer" in field_lower:
                mapping["counterparty_iban"] = field
            elif "bic" in field_lower:
                mapping["counterparty_bic"] = field
            elif "verwendungszweck" in field_lower:
                mapping["reference_text"] = field
            elif "buchungstext" in field_lower or "umsatzart" in field_lower:
                mapping["booking_text"] = field

        return mapping

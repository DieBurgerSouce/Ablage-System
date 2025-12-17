"""ING (ING-DiBa) CSV Parser.

Parst CSV-Exporte der ING.
Format: Semikolon-separiert, UTF-8.
"""

from typing import Optional, Union

from ..csv_parser import GenericCSVParser
from ..base import ParserRegistry
from ...models import ImportFormat


@ParserRegistry.register
class INGCSVParser(GenericCSVParser):
    """Parser fuer ING CSV-Kontoauszuege."""

    FORMAT = ImportFormat.CSV_ING
    FORMAT_VARIANT = "ing"

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Pruefe auf ING-Format."""
        text = cls._decode_content(content)
        if not text:
            return 0.0

        header = text.split("\n")[0].lower() if text else ""

        # ING-spezifische Spalten
        ing_markers = [
            "buchung",
            "valuta",
            "auftraggeber/empfänger",
            "verwendungszweck",
            "saldo",
        ]

        # ING verwendet charakteristische Spaltenbezeichnung
        if "auftraggeber/empfänger" in header or "auftraggeber/empfaenger" in header:
            return 0.95

        matches = sum(1 for m in ing_markers if m in header)

        if matches >= 3:
            return 0.85
        elif matches >= 2:
            return 0.6

        return 0.0

    def _map_columns(self, fieldnames):
        """ING-spezifisches Spalten-Mapping."""
        mapping = {}

        for field in fieldnames:
            field_lower = field.lower().strip()

            if "buchung" in field_lower and "text" not in field_lower:
                mapping["booking_date"] = field
            elif "valuta" in field_lower:
                mapping["value_date"] = field
            elif "betrag" in field_lower:
                mapping["amount"] = field
            elif "waehrung" in field_lower or "währung" in field_lower:
                mapping["currency"] = field
            elif "auftraggeber" in field_lower or "empfänger" in field_lower:
                mapping["counterparty_name"] = field
            elif "iban" in field_lower:
                mapping["counterparty_iban"] = field
            elif "bic" in field_lower:
                mapping["counterparty_bic"] = field
            elif "verwendungszweck" in field_lower:
                mapping["reference_text"] = field
            elif "buchungstext" in field_lower:
                mapping["booking_text"] = field

        return mapping

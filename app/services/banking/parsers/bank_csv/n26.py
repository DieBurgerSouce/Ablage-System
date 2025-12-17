"""N26 CSV Parser.

Parst CSV-Exporte der N26 Bank.
Format: Komma-separiert, UTF-8, englische Spaltennamen.
"""

from typing import Optional, Union

from ..csv_parser import GenericCSVParser
from ..base import ParserRegistry
from ...models import ImportFormat


@ParserRegistry.register
class N26CSVParser(GenericCSVParser):
    """Parser fuer N26 CSV-Kontoauszuege."""

    FORMAT = ImportFormat.CSV_N26
    FORMAT_VARIANT = "n26"

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Pruefe auf N26-Format."""
        text = cls._decode_content(content)
        if not text:
            return 0.0

        header = text.split("\n")[0].lower() if text else ""

        # N26 verwendet englische Spalten und Komma als Delimiter
        n26_markers = [
            "date",
            "payee",
            "account number",
            "transaction type",
            "payment reference",
            "amount (eur)",
        ]

        # N26-charakteristisch: "Payee" + "Amount (EUR)"
        if "payee" in header and "amount (eur)" in header:
            return 0.95

        matches = sum(1 for m in n26_markers if m in header)

        if matches >= 4:
            return 0.9
        elif matches >= 2:
            return 0.7

        return 0.0

    def _map_columns(self, fieldnames):
        """N26-spezifisches Spalten-Mapping."""
        mapping = {}

        for field in fieldnames:
            field_lower = field.lower().strip()

            if field_lower == "date":
                mapping["booking_date"] = field
            elif "amount" in field_lower:
                mapping["amount"] = field
            elif field_lower == "payee":
                mapping["counterparty_name"] = field
            elif "account number" in field_lower:
                mapping["counterparty_iban"] = field
            elif "payment reference" in field_lower:
                mapping["reference_text"] = field
            elif "transaction type" in field_lower:
                mapping["booking_text"] = field

        # N26 hat keine separate Valuta-Spalte
        if "booking_date" in mapping and "value_date" not in mapping:
            mapping["value_date"] = mapping["booking_date"]

        return mapping

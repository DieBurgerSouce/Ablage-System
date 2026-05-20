"""Deutsche Bank CSV Parser.

Parst CSV-Exporte der Deutschen Bank.
Format: Semikolon-separiert, UTF-8.
"""

from typing import Optional, Union, Dict, List

from ..csv_parser import GenericCSVParser
from ..base import ParserRegistry
from ...models import ImportFormat


@ParserRegistry.register
class DeutscheBankCSVParser(GenericCSVParser):
    """Parser für Deutsche Bank CSV-Kontoauszuege."""

    FORMAT = ImportFormat.CSV_DEUTSCHE_BANK
    FORMAT_VARIANT = "deutsche_bank"

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Prüfe auf Deutsche Bank-Format."""
        text = cls._decode_content(content)
        if not text:
            return 0.0

        header = text.split("\n")[0].lower() if text else ""

        # Deutsche Bank-spezifische Spalten
        db_markers = [
            "booking date",
            "value date",
            "transaction type",
            "beneficiary / originator",
        ]

        # Deutsche Bank verwendet oft englische Spaltennamen
        if "beneficiary / originator" in header:
            return 0.95

        matches = sum(1 for m in db_markers if m in header)

        if matches >= 3:
            return 0.9
        elif matches >= 2:
            return 0.7

        return 0.0

    def _map_columns(self, fieldnames: List[str]) -> Dict[str, str]:
        """Deutsche Bank-spezifisches Spalten-Mapping."""
        mapping = {}

        for field in fieldnames:
            field_lower = field.lower().strip()

            if "booking date" in field_lower or "buchungstag" in field_lower:
                mapping["booking_date"] = field
            elif "value date" in field_lower or "valuta" in field_lower:
                mapping["value_date"] = field
            elif "amount" in field_lower or "betrag" in field_lower:
                mapping["amount"] = field
            elif "currency" in field_lower or "währung" in field_lower:
                mapping["currency"] = field
            elif "beneficiary" in field_lower or "originator" in field_lower:
                mapping["counterparty_name"] = field
            elif "iban" in field_lower:
                mapping["counterparty_iban"] = field
            elif "bic" in field_lower:
                mapping["counterparty_bic"] = field
            elif "payment reference" in field_lower or "verwendungszweck" in field_lower:
                mapping["reference_text"] = field
            elif "transaction type" in field_lower or "buchungstext" in field_lower:
                mapping["booking_text"] = field

        return mapping

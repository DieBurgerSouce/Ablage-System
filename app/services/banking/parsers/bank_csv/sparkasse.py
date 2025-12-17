"""Sparkasse CSV Parser.

Parst CSV-Exporte der Sparkassen-Banken.
Format: Semikolon-separiert, ISO-8859-1/Windows-1252 Encoding.
"""

from typing import Optional, Union

from ..csv_parser import GenericCSVParser
from ..base import ParserRegistry
from ...models import ImportFormat


@ParserRegistry.register
class SparkasseCSVParser(GenericCSVParser):
    """Parser fuer Sparkasse CSV-Kontoauszuege."""

    FORMAT = ImportFormat.CSV_SPARKASSE
    FORMAT_VARIANT = "sparkasse"

    # Sparkasse-spezifische Spalten
    SPARKASSE_COLUMNS = {
        "Auftragskonto", "Buchungstag", "Valutadatum", "Buchungstext",
        "Verwendungszweck", "Glaeubiger ID", "Mandatsreferenz",
        "Kundenreferenz (End-to-End)", "Sammlerreferenz",
        "Lastschrift Ursprungsbetrag", "Auslagenersatz Ruecklastschrift",
        "Beguenstigter/Zahlungspflichtiger", "Kontonummer/IBAN",
        "BIC (SWIFT-Code)", "Betrag", "Waehrung", "Info"
    }

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Pruefe auf Sparkasse-Format."""
        text = cls._decode_content(content)
        if not text:
            return 0.0

        header = text.split("\n")[0].lower() if text else ""

        # Charakteristische Sparkasse-Spalten
        sparkasse_markers = [
            "auftragskonto",
            "beguenstigter/zahlungspflichtiger",
            "glaeubiger id",
            "mandatsreferenz",
        ]

        matches = sum(1 for m in sparkasse_markers if m in header)

        if matches >= 3:
            return 0.95
        elif matches >= 2:
            return 0.8
        elif matches >= 1:
            return 0.5

        return 0.0

    def _map_columns(self, fieldnames):
        """Sparkasse-spezifisches Spalten-Mapping."""
        mapping = {}

        for field in fieldnames:
            field_lower = field.lower().strip()

            if "buchungstag" in field_lower:
                mapping["booking_date"] = field
            elif "valuta" in field_lower:
                mapping["value_date"] = field
            elif "betrag" in field_lower and "ursprung" not in field_lower:
                mapping["amount"] = field
            elif "waehrung" in field_lower or "währung" in field_lower:
                mapping["currency"] = field
            elif "beguenstigter" in field_lower or "begünstigter" in field_lower:
                mapping["counterparty_name"] = field
            elif "kontonummer" in field_lower or "iban" in field_lower:
                mapping["counterparty_iban"] = field
            elif "bic" in field_lower or "swift" in field_lower:
                mapping["counterparty_bic"] = field
            elif "verwendungszweck" in field_lower:
                mapping["reference_text"] = field
            elif "buchungstext" in field_lower:
                mapping["booking_text"] = field

        return mapping

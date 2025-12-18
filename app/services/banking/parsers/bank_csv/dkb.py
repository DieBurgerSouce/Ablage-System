"""DKB (Deutsche Kreditbank) CSV Parser.

Parst CSV-Exporte der DKB.
Format: Semikolon-separiert, Latin-1/ISO-8859-1 Encoding.
Besonderheit: Header beginnt oft mit Kontoinfo.
"""

from typing import Optional, Union, Dict, List
import re

from ..csv_parser import GenericCSVParser
from ..base import ParserRegistry, ParseResult
from ...models import ImportFormat


@ParserRegistry.register
class DKBCSVParser(GenericCSVParser):
    """Parser fuer DKB CSV-Kontoauszuege."""

    FORMAT = ImportFormat.CSV_DKB
    FORMAT_VARIANT = "dkb"

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Pruefe auf DKB-Format."""
        text = cls._decode_content(content)
        if not text:
            return 0.0

        lines = text.split("\n")[:15]  # DKB hat oft Metadaten vor Header
        header_line = ""

        # DKB CSV beginnt oft mit "Kontonummer:" oder aehnlich
        for i, line in enumerate(lines):
            if "buchungstag" in line.lower() and "wertstellung" in line.lower():
                header_line = line.lower()
                break

        if not header_line:
            # Fallback auf erste Zeile
            header_line = lines[0].lower() if lines else ""

        # DKB-spezifische Spalten
        dkb_markers = [
            "buchungstag",
            "wertstellung",
            "buchungstext",
            "auftraggeber / begünstigter",
            "verwendungszweck",
            "kontonummer",
            "blz",
            "betrag (eur)",
        ]

        matches = sum(1 for m in dkb_markers if m in header_line)

        # DKB hat charakteristische Spalte "Betrag (EUR)"
        if "betrag (eur)" in header_line:
            return 0.95

        if matches >= 4:
            return 0.85
        elif matches >= 2:
            return 0.6

        # DKB-Metadaten-Check
        if any("kontonummer" in line.lower() or "dkb" in line.lower() for line in lines[:5]):
            if any("buchungstag" in line.lower() for line in lines):
                return 0.7

        return 0.0

    def parse(self, content: Union[str, bytes]) -> ParseResult:
        """Parse DKB-CSV mit Metadaten-Header."""
        text = self._decode_content(content)
        if not text:
            return ParseResult(
                success=False,
                format=ImportFormat.CSV_DKB,
                errors=[{"type": "encoding_error", "message": "Konnte Datei nicht dekodieren"}]
            )

        lines = text.split("\n")

        # Finde den eigentlichen CSV-Header (DKB hat oft Metadaten davor)
        header_idx = 0
        for i, line in enumerate(lines):
            if "buchungstag" in line.lower() and "wertstellung" in line.lower():
                header_idx = i
                break

        # Kontoinfo aus Metadaten extrahieren
        account_iban = None
        for line in lines[:header_idx]:
            # Suche nach IBAN
            iban_match = re.search(r"([A-Z]{2}\d{2}\s?[0-9A-Z\s]{10,30})", line.upper())
            if iban_match:
                account_iban = self.normalize_iban(iban_match.group(1))
                break

        # Nur Daten ab Header weitergeben
        csv_content = "\n".join(lines[header_idx:])

        # Standard-Parsing
        result = super().parse(csv_content)

        # Account-Info hinzufuegen
        if account_iban:
            result.account_iban = account_iban

        result.format = ImportFormat.CSV_DKB
        result.format_variant = "dkb"

        return result

    def _map_columns(self, fieldnames: List[str]) -> Dict[str, str]:
        """DKB-spezifisches Spalten-Mapping."""
        mapping = {}

        for field in fieldnames:
            field_lower = field.lower().strip()

            if "buchungstag" in field_lower:
                mapping["booking_date"] = field
            elif "wertstellung" in field_lower:
                mapping["value_date"] = field
            elif "betrag" in field_lower:
                mapping["amount"] = field
            elif "auftraggeber" in field_lower or "begünstigter" in field_lower:
                mapping["counterparty_name"] = field
            elif "kontonummer" in field_lower or "iban" in field_lower:
                mapping["counterparty_iban"] = field
            elif "blz" in field_lower or "bic" in field_lower:
                mapping["counterparty_bic"] = field
            elif "verwendungszweck" in field_lower:
                mapping["reference_text"] = field
            elif "buchungstext" in field_lower:
                mapping["booking_text"] = field

        return mapping

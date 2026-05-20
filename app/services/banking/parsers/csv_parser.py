"""Generic CSV Bank Statement Parser.

Parst generische CSV-Kontoauszuege mit automatischer
Spaltenerkennung. Basis für bank-spezifische Parser.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Union, Dict, Any, Tuple
import structlog
import re
import csv
import io
from app.core.safe_errors import safe_error_detail, safe_error_log

from .base import BaseParser, ParsedTransaction, ParseResult, ParserRegistry
from ..models import ImportFormat, TransactionType

logger = structlog.get_logger(__name__)


# Bekannte Spaltenbezeichnungen (deutsch/englisch)
COLUMN_MAPPINGS = {
    "booking_date": [
        "buchungstag", "buchungsdatum", "datum", "date", "booking date",
        "valuta", "wertstellung", "bu-tag"
    ],
    "value_date": [
        "wertstellung", "valuta", "value date", "wert", "valutadatum"
    ],
    "amount": [
        "betrag", "amount", "umsatz", "soll/haben", "betrag (eur)",
        "betrag in eur", "buchungsbetrag"
    ],
    "currency": [
        "währung", "währung", "currency", "ccy"
    ],
    "counterparty_name": [
        "empfänger/auftraggeber", "empfänger/auftraggeber", "name",
        "auftraggeber/empfänger", "auftraggeber/empfänger",
        "begünstigter/zahlungspflichtiger", "begünstigter/zahlungspflichtiger",
        "kontoinhaber", "empfänger", "empfänger", "payee", "beneficiary"
    ],
    "counterparty_iban": [
        "iban", "kontonummer", "account number", "konto-nr",
        "gegenkonto iban", "iban/konto-nr."
    ],
    "counterparty_bic": [
        "bic", "swift", "blz", "bank code"
    ],
    "reference_text": [
        "verwendungszweck", "buchungstext", "beschreibung", "description",
        "purpose", "zahlungsgrund", "info", "kundenreferenz",
        "verwendungszweck/kundenreferenz"
    ],
    "booking_text": [
        "buchungstext", "umsatzart", "transaktionsart", "type", "art"
    ],
}


@ParserRegistry.register
class GenericCSVParser(BaseParser):
    """Parser für generische CSV-Kontoauszuege."""

    FORMAT = ImportFormat.CSV_GENERIC
    FORMAT_VARIANT = "generic"
    SUPPORTED_EXTENSIONS = [".csv", ".txt"]

    # CSV-Dialekt-Optionen
    DELIMITERS = [";", ",", "\t"]
    ENCODINGS = ["utf-8", "iso-8859-1", "cp1252", "utf-16"]

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Prüfe ob Inhalt CSV-Format ist."""
        # Konvertiere zu String
        text = cls._decode_content(content)
        if not text:
            return 0.0

        # CSV-typische Struktur prüfen
        lines = text.strip().split("\n")[:10]

        if len(lines) < 2:
            return 0.0

        # Prüfe Delimiter
        delimiter = cls._detect_delimiter(lines[0])
        if not delimiter:
            return 0.0

        # Prüfe auf Spaltenheader
        header_lower = lines[0].lower()

        # Bekannte Banking-Spalten
        banking_keywords = [
            "buchung", "datum", "betrag", "amount", "iban", "verwendungszweck",
            "umsatz", "empfänger", "empfänger", "valuta", "saldo"
        ]

        matches = sum(1 for kw in banking_keywords if kw in header_lower)

        if matches >= 3:
            return 0.75
        elif matches >= 2:
            return 0.5
        elif matches >= 1:
            return 0.3

        # Extension-Check
        if filename:
            ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
            if ext in cls.SUPPORTED_EXTENSIONS:
                return 0.2

        return 0.0

    @staticmethod
    def _decode_content(content: Union[str, bytes]) -> Optional[str]:
        """Dekodiere Bytes zu String."""
        if isinstance(content, str):
            return content

        for encoding in GenericCSVParser.ENCODINGS:
            try:
                return content.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue

        return None

    @staticmethod
    def _detect_delimiter(line: str) -> Optional[str]:
        """Erkenne CSV-Delimiter."""
        for delim in GenericCSVParser.DELIMITERS:
            if delim in line:
                # Mindestens 3 Felder
                if len(line.split(delim)) >= 3:
                    return delim
        return None

    def parse(self, content: Union[str, bytes]) -> ParseResult:
        """Parse CSV-Kontoauszug."""
        text = self._decode_content(content)
        if not text:
            return ParseResult(
                success=False,
                format=ImportFormat.CSV_GENERIC,
                errors=[{"type": "encoding_error", "message": "Konnte Datei nicht dekodieren"}]
            )

        result = ParseResult(
            success=False,
            format=ImportFormat.CSV_GENERIC,
            format_variant=self.FORMAT_VARIANT,
        )

        try:
            # Delimiter erkennen
            lines = text.strip().split("\n")
            delimiter = self._detect_delimiter(lines[0]) if lines else ";"

            # CSV parsen
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

            # Spaltenmapping erstellen
            column_map = self._map_columns(reader.fieldnames or [])

            if not column_map.get("booking_date") and not column_map.get("amount"):
                result.errors.append({
                    "type": "column_error",
                    "message": "Keine erkennbaren Datum- oder Betrag-Spalten gefunden",
                    "available_columns": reader.fieldnames,
                })
                return result

            # Transaktionen parsen
            for row_num, row in enumerate(reader, start=2):
                try:
                    parsed = self._parse_row(row, column_map)
                    if parsed:
                        result.transactions.append(parsed)

                        # Statistik
                        if parsed.amount > 0:
                            result.total_credits += parsed.amount
                        else:
                            result.total_debits += abs(parsed.amount)

                        # Zeitraum
                        if parsed.booking_date:
                            if not result.date_from or parsed.booking_date < result.date_from:
                                result.date_from = parsed.booking_date
                            if not result.date_to or parsed.booking_date > result.date_to:
                                result.date_to = parsed.booking_date

                except Exception as e:
                    result.warnings.append(f"Zeile {row_num}: {e}")

            if result.transactions:
                result.success = True
            else:
                result.errors.append({
                    "type": "parse_error",
                    "message": "Keine Transaktionen gefunden",
                })

        except Exception as e:
            logger.exception(f"Fehler beim Parsen des CSV: {e}")
            result.errors.append({
                "type": "parse_error",
                "message": safe_error_detail(e, "CSV"),
            })

        return result

    def _map_columns(self, fieldnames: List[str]) -> Dict[str, str]:
        """Mappe CSV-Spalten auf interne Felder."""
        mapping = {}
        fieldnames_lower = {f.lower().strip(): f for f in fieldnames}

        for internal_name, possible_names in COLUMN_MAPPINGS.items():
            for possible in possible_names:
                if possible in fieldnames_lower:
                    mapping[internal_name] = fieldnames_lower[possible]
                    break

        return mapping

    def _parse_row(self, row: Dict[str, str], column_map: Dict[str, str]) -> Optional[ParsedTransaction]:
        """Parse einzelne CSV-Zeile."""
        # Betrag (Pflichtfeld)
        amount_col = column_map.get("amount")
        if not amount_col or not row.get(amount_col):
            return None

        amount = self.parse_german_amount(row[amount_col])
        if amount == Decimal("0"):
            return None

        # Datum
        booking_date = None
        date_col = column_map.get("booking_date")
        if date_col and row.get(date_col):
            booking_date = self._parse_date(row[date_col])

        value_date = None
        val_col = column_map.get("value_date")
        if val_col and row.get(val_col):
            value_date = self._parse_date(row[val_col])
        else:
            value_date = booking_date

        # Wenn kein Datum, Skip
        if not booking_date:
            return None

        # Währung
        currency = "EUR"
        ccy_col = column_map.get("currency")
        if ccy_col and row.get(ccy_col):
            currency = row[ccy_col].strip().upper()[:3]

        # Gegenpartei
        counterparty_name = None
        cp_col = column_map.get("counterparty_name")
        if cp_col and row.get(cp_col):
            counterparty_name = row[cp_col].strip()

        counterparty_iban = None
        iban_col = column_map.get("counterparty_iban")
        if iban_col and row.get(iban_col):
            counterparty_iban = self.normalize_iban(row[iban_col])

        counterparty_bic = None
        bic_col = column_map.get("counterparty_bic")
        if bic_col and row.get(bic_col):
            counterparty_bic = row[bic_col].strip().upper()

        # Verwendungszweck
        reference_text = None
        ref_col = column_map.get("reference_text")
        if ref_col and row.get(ref_col):
            reference_text = row[ref_col].strip()

        # Buchungstext
        booking_text = None
        bt_col = column_map.get("booking_text")
        if bt_col and row.get(bt_col):
            booking_text = row[bt_col].strip()

        # Transaktionstyp
        transaction_type = self.detect_transaction_type(
            booking_text or "",
            amount
        )

        # Referenzen parsen
        parsed_refs = self.parse_reference_text(reference_text or "")

        # Transaction-ID
        transaction_id = self.generate_transaction_hash(
            booking_date,
            amount,
            counterparty_name or "",
            reference_text or ""
        )

        return ParsedTransaction(
            transaction_id=transaction_id,
            booking_date=booking_date,
            value_date=value_date,
            amount=amount,
            currency=currency,
            counterparty_name=counterparty_name,
            counterparty_iban=counterparty_iban,
            counterparty_bic=counterparty_bic,
            reference_text=reference_text,
            end_to_end_id=parsed_refs["end_to_end_ids"][0] if parsed_refs["end_to_end_ids"] else None,
            mandate_id=parsed_refs["mandate_ids"][0] if parsed_refs["mandate_ids"] else None,
            creditor_id=parsed_refs["creditor_ids"][0] if parsed_refs["creditor_ids"] else None,
            transaction_type=transaction_type,
            booking_text=booking_text,
            parsed_invoice_numbers=parsed_refs["invoice_numbers"],
            parsed_customer_numbers=parsed_refs["customer_numbers"],
            parsed_references=parsed_refs["order_numbers"],
            raw_data=dict(row),
        )

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse Datum in verschiedenen Formaten."""
        date_str = date_str.strip()
        if not date_str:
            return None

        # Bekannte Formate
        formats = [
            "%d.%m.%Y",  # 31.12.2024 (deutsch)
            "%d.%m.%y",  # 31.12.24
            "%Y-%m-%d",  # 2024-12-31 (ISO)
            "%d/%m/%Y",  # 31/12/2024
            "%m/%d/%Y",  # 12/31/2024 (US)
            "%d-%m-%Y",  # 31-12-2024
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        logger.warning(f"Konnte Datum nicht parsen: {date_str}")
        return None

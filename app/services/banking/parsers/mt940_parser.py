"""MT940 Bank Statement Parser.

Parst MT940 (SWIFT) Kontoauszuege, das universelle Format
das von fast allen deutschen Banken unterstuetzt wird.

Verwendet die mt-940 Bibliothek.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List, Union
import logging
import re

from mt940 import parse as mt940_parse
from mt940.models import Transaction as MT940Transaction

from .base import BaseParser, ParsedTransaction, ParseResult, ParserRegistry
from ..models import ImportFormat, TransactionType

logger = logging.getLogger(__name__)


@ParserRegistry.register
class MT940Parser(BaseParser):
    """Parser fuer MT940 (SWIFT) Kontoauszuege."""

    FORMAT = ImportFormat.MT940
    FORMAT_VARIANT = None
    SUPPORTED_EXTENSIONS = [".sta", ".mt940", ".940", ".txt"]

    @classmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Pruefe ob Inhalt MT940-Format ist."""
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8", errors="replace")
            except Exception:
                content = content.decode("latin-1", errors="replace")

        # MT940 beginnt typischerweise mit :20: oder :940:
        # und enthaelt charakteristische Feldkennungen
        content_start = content[:2000]

        # Starke Indikatoren
        if ":20:" in content_start and ":60" in content_start:
            return 0.95

        # MT940-typische Felder
        mt940_markers = [":25:", ":28C:", ":60F:", ":61:", ":62F:", ":86:"]
        matches = sum(1 for marker in mt940_markers if marker in content_start)

        if matches >= 4:
            return 0.9
        elif matches >= 2:
            return 0.7
        elif matches >= 1:
            return 0.4

        # Extension-basierte Erkennung
        if filename:
            ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
            if ext in cls.SUPPORTED_EXTENSIONS:
                return 0.3

        return 0.0

    def parse(self, content: Union[str, bytes]) -> ParseResult:
        """Parse MT940-Kontoauszug."""
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    content = content.decode("latin-1")
                except Exception:
                    content = content.decode("cp1252", errors="replace")

        result = ParseResult(
            success=False,
            format=ImportFormat.MT940,
        )

        try:
            # Parse mit mt-940 Bibliothek
            statements = mt940_parse(content)

            if not statements:
                result.errors.append({
                    "type": "parse_error",
                    "message": "Keine MT940-Statements gefunden",
                })
                return result

            # Verarbeite alle Statements
            for statement in statements:
                # Kontoinfo
                if hasattr(statement, "account_id") and statement.account_id:
                    account_id = statement.account_id
                    # Versuche IBAN zu extrahieren
                    if len(account_id) >= 15 and account_id[:2].isalpha():
                        result.account_iban = self.normalize_iban(account_id)
                    else:
                        result.account_number = account_id

                # BIC
                if hasattr(statement, "bic") and statement.bic:
                    result.account_bic = statement.bic

                # Salden
                if hasattr(statement, "opening_balance"):
                    ob = statement.opening_balance
                    if ob:
                        result.opening_balance = Decimal(str(ob.amount.amount))
                        result.date_from = ob.date

                if hasattr(statement, "final_closing_balance"):
                    cb = statement.final_closing_balance
                    if cb:
                        result.closing_balance = Decimal(str(cb.amount.amount))
                        result.balance_date = cb.date
                elif hasattr(statement, "closing_balance"):
                    cb = statement.closing_balance
                    if cb:
                        result.closing_balance = Decimal(str(cb.amount.amount))
                        result.balance_date = cb.date

                # Transaktionen
                if hasattr(statement, "transactions"):
                    for tx in statement.transactions:
                        parsed = self._parse_transaction(tx)
                        if parsed:
                            result.transactions.append(parsed)

                            # Statistik
                            if parsed.amount > 0:
                                result.total_credits += parsed.amount
                            else:
                                result.total_debits += abs(parsed.amount)

                            # Zeitraum aktualisieren
                            if parsed.booking_date:
                                if not result.date_from or parsed.booking_date < result.date_from:
                                    result.date_from = parsed.booking_date
                                if not result.date_to or parsed.booking_date > result.date_to:
                                    result.date_to = parsed.booking_date

            result.success = True

        except Exception as e:
            logger.exception(f"Fehler beim Parsen des MT940: {e}")
            result.errors.append({
                "type": "parse_error",
                "message": str(e),
            })

        return result

    def _parse_transaction(self, tx: MT940Transaction) -> Optional[ParsedTransaction]:
        """Parse einzelne MT940-Transaktion."""
        try:
            # Betrag
            amount = Decimal(str(tx.amount.amount)) if tx.amount else Decimal("0")

            # Datum
            booking_date = tx.date if hasattr(tx, "date") else None
            value_date = tx.entry_date if hasattr(tx, "entry_date") else booking_date

            # Verwendungszweck zusammenbauen
            reference_parts = []

            # :86: Feld - Verwendungszweck
            if hasattr(tx, "transaction_details") and tx.transaction_details:
                reference_parts.append(tx.transaction_details)

            # Strukturierte Felder aus :86:
            extra_details = getattr(tx, "extra_details", None) or {}

            # Empfaenger/Auftraggeber
            counterparty_name = None
            counterparty_iban = None
            counterparty_bic = None

            # Versuche strukturierte Daten zu extrahieren
            if isinstance(extra_details, dict):
                counterparty_name = extra_details.get("name") or extra_details.get("account_holder")
                counterparty_iban = extra_details.get("iban")
                counterparty_bic = extra_details.get("bic")

                # Weitere Referenzen
                if extra_details.get("purpose"):
                    reference_parts.append(extra_details["purpose"])

            # Wenn keine strukturierten Daten, parse :86: Feld
            if not counterparty_name and reference_parts:
                full_reference = " ".join(reference_parts)
                counterparty_name, counterparty_iban = self._extract_counterparty(full_reference)

            reference_text = " ".join(reference_parts) if reference_parts else None

            # Referenzen parsen
            parsed_refs = self.parse_reference_text(reference_text or "")

            # End-to-End-ID aus :86: extrahieren
            end_to_end_id = None
            mandate_id = None
            creditor_id = None

            if parsed_refs["end_to_end_ids"]:
                end_to_end_id = parsed_refs["end_to_end_ids"][0]
            if parsed_refs["mandate_ids"]:
                mandate_id = parsed_refs["mandate_ids"][0]
            if parsed_refs["creditor_ids"]:
                creditor_id = parsed_refs["creditor_ids"][0]

            # Transaktionstyp
            booking_text = getattr(tx, "id", None) or getattr(tx, "guvc", None) or ""
            transaction_type = self.detect_transaction_type(
                booking_text + " " + (reference_text or ""),
                amount
            )

            # Prima Nota
            prima_nota = getattr(tx, "bank_reference", None)

            # Transaction-ID generieren falls nicht vorhanden
            transaction_id = getattr(tx, "customer_reference", None)
            if not transaction_id:
                transaction_id = self.generate_transaction_hash(
                    booking_date or date.today(),
                    amount,
                    counterparty_name or "",
                    reference_text or ""
                )

            return ParsedTransaction(
                transaction_id=transaction_id,
                booking_date=booking_date,
                value_date=value_date,
                amount=amount,
                currency="EUR",  # MT940 in Deutschland meist EUR
                counterparty_name=counterparty_name,
                counterparty_iban=self.normalize_iban(counterparty_iban) if counterparty_iban else None,
                counterparty_bic=counterparty_bic,
                reference_text=reference_text,
                end_to_end_id=end_to_end_id,
                mandate_id=mandate_id,
                creditor_id=creditor_id,
                transaction_type=transaction_type,
                booking_text=booking_text,
                prima_nota=prima_nota,
                parsed_invoice_numbers=parsed_refs["invoice_numbers"],
                parsed_customer_numbers=parsed_refs["customer_numbers"],
                parsed_references=parsed_refs["order_numbers"],
                raw_data={
                    "mt940_id": getattr(tx, "id", None),
                    "mt940_guvc": getattr(tx, "guvc", None),
                    "mt940_extra": extra_details if isinstance(extra_details, dict) else {},
                },
            )

        except Exception as e:
            logger.warning(f"Fehler beim Parsen der MT940-Transaktion: {e}")
            return None

    def _extract_counterparty(self, reference: str) -> tuple:
        """Extrahiere Gegenpartei aus unstrukturiertem :86: Feld."""
        counterparty_name = None
        counterparty_iban = None

        # IBAN-Pattern
        iban_match = re.search(
            r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b",
            reference.upper()
        )
        if iban_match:
            counterparty_iban = iban_match.group(1)

        # Name extrahieren - oft nach bestimmten Kennungen
        # Pattern: Name steht oft am Anfang oder nach "NAME+" etc.
        name_patterns = [
            r"NAME\+([^\+]+)",
            r"AUFTRAGGEBER:\s*([^\n\+]+)",
            r"EMPFAENGER:\s*([^\n\+]+)",
            r"^([A-Za-z\s\-\.]{3,50})\s+(?:IBAN|DE\d{20})",
        ]

        for pattern in name_patterns:
            match = re.search(pattern, reference, re.IGNORECASE)
            if match:
                counterparty_name = match.group(1).strip()
                break

        # Fallback: Erste Zeile als Name (wenn keine IBAN/Nummer)
        if not counterparty_name:
            lines = reference.split("\n")
            if lines:
                first_line = lines[0].strip()
                # Nur wenn es wie ein Name aussieht
                if (len(first_line) > 3 and
                    not first_line.startswith("EREF+") and
                    not first_line.startswith("KREF+") and
                    not re.match(r"^[0-9\+\-]", first_line)):
                    counterparty_name = first_line[:100]

        return counterparty_name, counterparty_iban

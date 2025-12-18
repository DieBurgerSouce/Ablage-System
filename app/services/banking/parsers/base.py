"""Base parser classes and utilities for bank statement parsing.

Definiert die gemeinsame Schnittstelle fuer alle Bank-Parser.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional, List, Dict, Any, Type, BinaryIO, Union
import re
import hashlib
import structlog

from ..models import ImportFormat, TransactionType

logger = structlog.get_logger(__name__)


@dataclass
class ParsedTransaction:
    """Geparste Transaktion aus Kontoauszug.

    Gemeinsames Format fuer alle Parser.
    """
    # Identifikation
    transaction_id: Optional[str] = None

    # Datum
    booking_date: Optional[date] = None
    value_date: Optional[date] = None

    # Betrag (positiv = Gutschrift, negativ = Belastung)
    amount: Decimal = Decimal("0")
    currency: str = "EUR"

    # Gegenpartei
    counterparty_name: Optional[str] = None
    counterparty_iban: Optional[str] = None
    counterparty_bic: Optional[str] = None
    counterparty_bank_name: Optional[str] = None

    # Verwendungszweck
    reference_text: Optional[str] = None
    end_to_end_id: Optional[str] = None
    mandate_id: Optional[str] = None
    creditor_id: Optional[str] = None

    # Kategorisierung
    transaction_type: Optional[TransactionType] = None
    booking_text: Optional[str] = None
    prima_nota: Optional[str] = None

    # Geparste Referenzen
    parsed_invoice_numbers: List[str] = field(default_factory=list)
    parsed_customer_numbers: List[str] = None
    parsed_references: List[str] = None

    # Rohdaten
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialisiere Listen falls None."""
        if self.parsed_customer_numbers is None:
            self.parsed_customer_numbers = []
        if self.parsed_references is None:
            self.parsed_references = []

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary fuer DB-Speicherung."""
        return {
            "transaction_id": self.transaction_id,
            "booking_date": self.booking_date.isoformat() if self.booking_date else None,
            "value_date": self.value_date.isoformat() if self.value_date else None,
            "amount": str(self.amount),
            "currency": self.currency,
            "counterparty_name": self.counterparty_name,
            "counterparty_iban": self.counterparty_iban,
            "counterparty_bic": self.counterparty_bic,
            "counterparty_bank_name": self.counterparty_bank_name,
            "reference_text": self.reference_text,
            "end_to_end_id": self.end_to_end_id,
            "mandate_id": self.mandate_id,
            "creditor_id": self.creditor_id,
            "transaction_type": self.transaction_type.value if self.transaction_type else None,
            "booking_text": self.booking_text,
            "prima_nota": self.prima_nota,
            "parsed_invoice_numbers": self.parsed_invoice_numbers,
            "parsed_customer_numbers": self.parsed_customer_numbers,
            "parsed_references": self.parsed_references,
            "raw_data": self.raw_data,
        }


@dataclass
class ParseResult:
    """Ergebnis eines Parse-Vorgangs."""
    success: bool
    format: ImportFormat
    format_variant: Optional[str] = None

    # Transaktionen
    transactions: List[ParsedTransaction] = field(default_factory=list)

    # Kontoinfo
    account_iban: Optional[str] = None
    account_bic: Optional[str] = None
    account_number: Optional[str] = None
    bank_code: Optional[str] = None

    # Saldo
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    balance_date: Optional[date] = None

    # Zeitraum
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    # Statistik
    total_credits: Decimal = Decimal("0")
    total_debits: Decimal = Decimal("0")

    # Fehler/Warnungen
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def transaction_count(self) -> int:
        """Anzahl geparster Transaktionen."""
        return len(self.transactions)

    @property
    def error_count(self) -> int:
        """Anzahl Fehler."""
        return len(self.errors)


class BaseParser(ABC):
    """Abstrakte Basisklasse fuer Bank-Parser.

    Alle Parser muessen diese Schnittstelle implementieren.
    """

    # Parser-Metadaten (von Subklassen zu setzen)
    FORMAT: ImportFormat = None
    FORMAT_VARIANT: Optional[str] = None
    SUPPORTED_EXTENSIONS: List[str] = []

    def __init__(self):
        """Initialisiere Parser."""
        self._reference_patterns = self._compile_reference_patterns()

    @classmethod
    @abstractmethod
    def can_parse(cls, content: Union[str, bytes], filename: Optional[str] = None) -> float:
        """Pruefe ob dieser Parser den Inhalt verarbeiten kann.

        Args:
            content: Dateiinhalt als String oder Bytes
            filename: Optionaler Dateiname fuer Extension-Check

        Returns:
            Konfidenz 0.0-1.0 (0 = kann nicht parsen, 1 = sicher)
        """
        pass

    @abstractmethod
    def parse(self, content: Union[str, bytes]) -> ParseResult:
        """Parse den Kontoauszug.

        Args:
            content: Dateiinhalt

        Returns:
            ParseResult mit Transaktionen
        """
        pass

    def _compile_reference_patterns(self) -> Dict[str, re.Pattern]:
        """Kompiliere Regex-Patterns fuer Referenz-Extraktion."""
        return {
            # Rechnungsnummern
            "invoice_number": re.compile(
                r"(?:RE|RG|INV|RECHNUNG|INVOICE)[.\-/\s]?(?:NR\.?|NO\.?|NUM\.?)?[:\s]?\s*"
                r"([A-Z0-9][A-Z0-9\-/]{2,20})",
                re.IGNORECASE
            ),
            # Kundennummern
            "customer_number": re.compile(
                r"(?:KD|KUNDE|KUNDEN|CUSTOMER)[.\-/\s]?(?:NR\.?|NO\.?|NUM\.?)?[:\s]?\s*"
                r"([A-Z0-9]{3,15})",
                re.IGNORECASE
            ),
            # Bestellnummern
            "order_number": re.compile(
                r"(?:BEST|ORDER|AUFTRAG)[.\-/\s]?(?:NR\.?|NO\.?|NUM\.?)?[:\s]?\s*"
                r"([A-Z0-9][A-Z0-9\-/]{2,20})",
                re.IGNORECASE
            ),
            # SEPA End-to-End-ID
            "end_to_end_id": re.compile(
                r"(?:EREF\+|END-TO-END-ID:?|E2E:?)\s*([A-Z0-9\-]{1,35})",
                re.IGNORECASE
            ),
            # SEPA Mandatsreferenz
            "mandate_id": re.compile(
                r"(?:MREF\+|MANDATE-ID:?|MANDAT:?)\s*([A-Z0-9\-]{1,35})",
                re.IGNORECASE
            ),
            # SEPA Glaeubiger-ID
            "creditor_id": re.compile(
                r"(?:CRED\+|CREDITOR-ID:?|GLAUB-ID:?)\s*([A-Z]{2}\d{2}[A-Z0-9]{1,28})",
                re.IGNORECASE
            ),
        }

    def parse_reference_text(self, text: str) -> Dict[str, List[str]]:
        """Extrahiere strukturierte Referenzen aus Verwendungszweck.

        Args:
            text: Verwendungszweck-Text

        Returns:
            Dictionary mit Listen von gefundenen Referenzen
        """
        if not text:
            return {
                "invoice_numbers": [],
                "customer_numbers": [],
                "order_numbers": [],
                "end_to_end_ids": [],
                "mandate_ids": [],
                "creditor_ids": [],
            }

        result = {}

        # Rechnungsnummern
        matches = self._reference_patterns["invoice_number"].findall(text)
        result["invoice_numbers"] = list(set(m.strip() for m in matches if m.strip()))

        # Kundennummern
        matches = self._reference_patterns["customer_number"].findall(text)
        result["customer_numbers"] = list(set(m.strip() for m in matches if m.strip()))

        # Bestellnummern
        matches = self._reference_patterns["order_number"].findall(text)
        result["order_numbers"] = list(set(m.strip() for m in matches if m.strip()))

        # SEPA-Referenzen
        matches = self._reference_patterns["end_to_end_id"].findall(text)
        result["end_to_end_ids"] = list(set(m.strip() for m in matches if m.strip()))

        matches = self._reference_patterns["mandate_id"].findall(text)
        result["mandate_ids"] = list(set(m.strip() for m in matches if m.strip()))

        matches = self._reference_patterns["creditor_id"].findall(text)
        result["creditor_ids"] = list(set(m.strip() for m in matches if m.strip()))

        return result

    def detect_transaction_type(self, booking_text: str, amount: Decimal) -> TransactionType:
        """Erkenne Transaktionstyp aus Buchungstext.

        Args:
            booking_text: Buchungstext/GVC-Text
            amount: Betrag (positiv/negativ)

        Returns:
            TransactionType
        """
        if not booking_text:
            return TransactionType.OTHER

        text_lower = booking_text.lower()

        # Lastschrift
        if any(kw in text_lower for kw in ["lastschrift", "einzug", "direct debit", "dd"]):
            return TransactionType.DIRECT_DEBIT

        # Ueberweisung
        if any(kw in text_lower for kw in ["ueberweisung", "überweisung", "transfer", "gutschr"]):
            return TransactionType.TRANSFER

        # Kartenzahlung
        if any(kw in text_lower for kw in ["karte", "card", "ec", "giro", "visa", "master"]):
            return TransactionType.CARD

        # Bargeld
        if any(kw in text_lower for kw in ["bargeld", "cash", "auszahlung", "einzahlung", "gaa", "atm"]):
            return TransactionType.CASH

        # Gebuehr
        if any(kw in text_lower for kw in ["gebuehr", "gebühr", "fee", "entgelt", "provision"]):
            return TransactionType.FEE

        # Zinsen
        if any(kw in text_lower for kw in ["zins", "interest"]):
            return TransactionType.INTEREST

        return TransactionType.OTHER

    @staticmethod
    def normalize_iban(iban: str) -> Optional[str]:
        """Normalisiere IBAN (entferne Leerzeichen, uppercase)."""
        if not iban:
            return None
        return iban.replace(" ", "").upper()

    @staticmethod
    def parse_german_amount(amount_str: str) -> Decimal:
        """Parse deutschen Betrag (1.234,56) zu Decimal.

        Args:
            amount_str: Betrag als String

        Returns:
            Decimal
        """
        if not amount_str:
            return Decimal("0")

        # Entferne Waehrungssymbole und Leerzeichen
        cleaned = amount_str.strip()
        cleaned = re.sub(r"[€$£CHF\s]", "", cleaned)

        # Bestimme Format (deutsch vs. englisch)
        if "," in cleaned and "." in cleaned:
            # Deutsches Format: 1.234,56
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            # Englisches Format: 1,234.56
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            # Nur Komma: deutsches Format
            cleaned = cleaned.replace(",", ".")

        try:
            return Decimal(cleaned)
        except (ValueError, InvalidOperation):
            logger.warning(f"Konnte Betrag nicht parsen: {amount_str}")
            return Decimal("0")

    @staticmethod
    def generate_transaction_hash(
        booking_date: date,
        amount: Decimal,
        counterparty: str,
        reference: str
    ) -> str:
        """Generiere Hash fuer Duplikat-Erkennung."""
        data = f"{booking_date}|{amount}|{counterparty or ''}|{reference or ''}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]


class ParserRegistry:
    """Registry fuer Parser-Klassen."""

    _parsers: List[Type[BaseParser]] = []

    @classmethod
    def register(cls, parser_class: Type[BaseParser]) -> Type[BaseParser]:
        """Registriere Parser-Klasse (als Decorator verwendbar)."""
        if parser_class not in cls._parsers:
            cls._parsers.append(parser_class)
        return parser_class

    @classmethod
    def get_parsers(cls) -> List[Type[BaseParser]]:
        """Hole alle registrierten Parser."""
        return cls._parsers.copy()

    @classmethod
    def get_parser_for_format(cls, format: ImportFormat) -> Optional[Type[BaseParser]]:
        """Hole Parser fuer spezifisches Format."""
        for parser in cls._parsers:
            if parser.FORMAT == format:
                return parser
        return None


def detect_format(content: Union[str, bytes], filename: Optional[str] = None) -> List[tuple]:
    """Erkenne Format des Kontoauszugs.

    Args:
        content: Dateiinhalt
        filename: Optionaler Dateiname

    Returns:
        Liste von (Parser-Klasse, Konfidenz) sortiert nach Konfidenz
    """
    results = []

    for parser_class in ParserRegistry.get_parsers():
        try:
            confidence = parser_class.can_parse(content, filename)
            if confidence > 0:
                results.append((parser_class, confidence))
        except Exception as e:
            logger.warning(f"Fehler bei Format-Erkennung mit {parser_class.__name__}: {e}")

    # Sortiere nach Konfidenz (absteigend)
    results.sort(key=lambda x: x[1], reverse=True)

    return results

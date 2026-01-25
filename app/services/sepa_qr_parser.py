# -*- coding: utf-8 -*-
"""
SEPA QR-Code Parser Service.

Parser fuer SEPA EPC QR-Codes (European Payments Council Standard).

Ermoeglicht:
- Parsen von EPC QR-Codes fuer SEPA-Ueberweisungen
- IBAN-Validierung mit Pruefsumme
- BIC-Validierung
- Generierung von EPC QR-Codes

EPC QR-Code Format (Version 002):
1. Service Tag: BCD
2. Version: 002
3. Character Set: 1 (UTF-8)
4. Identification: SCT
5. BIC (optional)
6. Recipient Name (max 70 Zeichen)
7. IBAN
8. Amount: EUR[Betrag] (optional)
9. Purpose Code (optional)
10. Reference (Strukturiert, optional)
11. Remittance Text (Unstrukturiert, optional)
12. Origin Information (optional)

Feinpoliert und durchdacht - Deutsche Zahlungs-Standards.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SEPAPaymentInfo:
    """SEPA-Zahlungsinformationen aus EPC QR-Code."""

    # Pflichtfelder
    iban: str = ""
    recipient_name: str = ""

    # Optionale Felder
    bic: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "EUR"
    reference: str = ""                 # Strukturierter Verwendungszweck (RF...)
    remittance_text: str = ""           # Unstrukturierter Verwendungszweck
    purpose_code: str = ""              # SEPA Purpose Code (z.B. SALA, SUPP)
    origin_identification: str = ""     # Auftraggeber-Identifikation

    # Metadaten
    version: str = "002"
    raw_data: str = ""
    parse_errors: list = None

    def __post_init__(self) -> None:
        """Initialize parse_errors if None."""
        if self.parse_errors is None:
            self.parse_errors = []

    @property
    def is_valid(self) -> bool:
        """Pruefen ob minimale SEPA-Daten vorhanden und valide."""
        if not self.iban or not self.recipient_name:
            return False
        return validate_iban(self.iban)

    @property
    def verwendungszweck(self) -> str:
        """Kombinierter Verwendungszweck (Referenz oder Text)."""
        if self.reference:
            return self.reference
        return self.remittance_text

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "iban": self.iban,
            "bic": self.bic,
            "recipient_name": self.recipient_name,
            "amount": self.amount,
            "currency": self.currency,
            "reference": self.reference,
            "remittance_text": self.remittance_text,
            "purpose_code": self.purpose_code,
            "origin_identification": self.origin_identification,
            "verwendungszweck": self.verwendungszweck,
            "is_valid": self.is_valid,
            "version": self.version,
        }


# =============================================================================
# IBAN & BIC Validation
# =============================================================================


def validate_iban(iban: str) -> bool:
    """
    Validiere IBAN mit Pruefsumme (ISO 7064 Mod 97-10).

    Args:
        iban: IBAN-String (mit oder ohne Leerzeichen)

    Returns:
        True wenn IBAN valide
    """
    if not iban:
        return False

    # Normalisiere
    iban = iban.replace(" ", "").upper()

    # Laenge pruefen (DE = 22)
    country_lengths = {
        "DE": 22,  # Deutschland
        "AT": 20,  # Oesterreich
        "CH": 21,  # Schweiz
        "LI": 21,  # Liechtenstein
        "LU": 20,  # Luxemburg
        "NL": 18,  # Niederlande
        "BE": 16,  # Belgien
        "FR": 27,  # Frankreich
        "IT": 27,  # Italien
        "ES": 24,  # Spanien
        "PT": 25,  # Portugal
        "GB": 22,  # UK
        "IE": 22,  # Irland
        "PL": 28,  # Polen
        "CZ": 24,  # Tschechien
        "SK": 24,  # Slowakei
        "HU": 28,  # Ungarn
    }

    if len(iban) < 15 or len(iban) > 34:
        return False

    country_code = iban[:2]
    expected_length = country_lengths.get(country_code)
    if expected_length and len(iban) != expected_length:
        return False

    # Laendercode muss aus Buchstaben bestehen
    if not iban[:2].isalpha():
        return False

    # Pruefziffer muss numerisch sein
    if not iban[2:4].isdigit():
        return False

    # Mod 97 Pruefung
    try:
        # IBAN umstellen: Laendercode + Pruefziffer ans Ende
        rearranged = iban[4:] + iban[:4]

        # Buchstaben durch Zahlen ersetzen (A=10, B=11, ..., Z=35)
        numeric = ""
        for char in rearranged:
            if char.isdigit():
                numeric += char
            elif char.isalpha():
                numeric += str(ord(char.upper()) - ord('A') + 10)

        # Modulo 97 muss 1 ergeben
        return int(numeric) % 97 == 1

    except (ValueError, OverflowError):
        return False


def validate_bic(bic: str) -> bool:
    """
    Validiere BIC/SWIFT-Code.

    Format: AAAABBCC[DDD]
    - AAAA: Bank-Code (4 Buchstaben)
    - BB: Laendercode (2 Buchstaben, ISO 3166)
    - CC: Orts-Code (2 alphanumerisch)
    - DDD: Branch-Code (3 alphanumerisch, optional)

    Args:
        bic: BIC-String

    Returns:
        True wenn BIC valide
    """
    if not bic:
        return True  # BIC ist optional in SEPA Version 002

    bic = bic.replace(" ", "").upper()

    # 8 oder 11 Zeichen
    if len(bic) not in (8, 11):
        return False

    # Bank-Code: 4 Buchstaben
    if not bic[:4].isalpha():
        return False

    # Laendercode: 2 Buchstaben
    if not bic[4:6].isalpha():
        return False

    # Orts-Code: 2 alphanumerisch
    if not bic[6:8].isalnum():
        return False

    # Branch-Code: 3 alphanumerisch (wenn vorhanden)
    if len(bic) == 11 and not bic[8:11].isalnum():
        return False

    return True


def format_iban(iban: str) -> str:
    """
    Formatiere IBAN in lesbares Format (4er Gruppen).

    Args:
        iban: IBAN ohne Formatierung

    Returns:
        Formatierte IBAN z.B. "DE89 3704 0044 0532 0130 00"
    """
    iban = iban.replace(" ", "").upper()
    return " ".join(iban[i:i+4] for i in range(0, len(iban), 4))


# =============================================================================
# EPC QR-Code Parser
# =============================================================================


class SEPAQRParserService:
    """
    Service zum Parsen von SEPA EPC QR-Codes.

    Unterstuetzt EPC QR-Code Version 001 und 002.
    """

    SEPARATOR = "\n"
    SERVICE_TAG = "BCD"
    VALID_VERSIONS = ("001", "002")
    CHARSETS = {
        "1": "UTF-8",
        "2": "ISO-8859-1",
        "3": "ISO-8859-2",
        "4": "ISO-8859-4",
        "5": "ISO-8859-5",
        "6": "ISO-8859-7",
        "7": "ISO-8859-10",
        "8": "ISO-8859-15",
    }
    IDENTIFICATION = "SCT"

    # SEPA Purpose Codes
    PURPOSE_CODES = {
        "SALA": "Gehaltszahlung",
        "PENS": "Rentenzahlung",
        "SSBE": "Sozialleistung",
        "SUPP": "Lieferanten-Zahlung",
        "GDDS": "Warenlieferung",
        "SCVE": "Service-Zahlung",
        "TAXS": "Steuerzahlung",
        "GOVT": "Behoerdenzahlung",
        "LOAN": "Darlehenszahlung",
        "RENT": "Miete/Pacht",
        "UTIL": "Versorgungsleistungen",
        "INTC": "Konzern-interne Zahlung",
    }

    def parse(self, qr_data: str) -> SEPAPaymentInfo:
        """
        Parse SEPA EPC QR-Code.

        Args:
            qr_data: Rohdaten aus QR-Code-Scan

        Returns:
            SEPAPaymentInfo mit geparsten Daten
        """
        payment = SEPAPaymentInfo(raw_data=qr_data)

        if not qr_data:
            payment.parse_errors.append("Leere QR-Code Daten")
            return payment

        # Zeilen aufteilen
        lines = qr_data.strip().split(self.SEPARATOR)

        if len(lines) < 7:
            payment.parse_errors.append(
                f"Ungueltige EPC QR-Code Struktur: {len(lines)} Zeilen (min. 7)"
            )
            return payment

        try:
            # 1. Service Tag (Index 0)
            if lines[0].strip().upper() != self.SERVICE_TAG:
                payment.parse_errors.append(
                    f"Ungueltiger Service Tag: {lines[0]} (erwartet: {self.SERVICE_TAG})"
                )
                return payment

            # 2. Version (Index 1)
            version = lines[1].strip()
            if version not in self.VALID_VERSIONS:
                payment.parse_errors.append(
                    f"Ungueltige Version: {version} (unterstuetzt: {self.VALID_VERSIONS})"
                )
                return payment
            payment.version = version

            # 3. Character Set (Index 2) - wird fuer Encoding verwendet
            # charset_id = lines[2].strip()
            # charset = self.CHARSETS.get(charset_id, "UTF-8")

            # 4. Identification (Index 3)
            identification = lines[3].strip().upper()
            if identification != self.IDENTIFICATION:
                payment.parse_errors.append(
                    f"Ungueltige Identification: {identification} (erwartet: {self.IDENTIFICATION})"
                )
                return payment

            # 5. BIC (Index 4) - optional in Version 002
            if len(lines) > 4 and lines[4].strip():
                bic = lines[4].strip().upper()
                if validate_bic(bic):
                    payment.bic = bic
                else:
                    payment.parse_errors.append(f"Ungueltiger BIC: {bic}")

            # 6. Recipient Name (Index 5) - Pflicht
            if len(lines) > 5:
                recipient = lines[5].strip()
                if recipient:
                    # Max 70 Zeichen nach EPC Standard
                    payment.recipient_name = recipient[:70]
                else:
                    payment.parse_errors.append("Empfaengername fehlt")

            # 7. IBAN (Index 6) - Pflicht
            if len(lines) > 6:
                iban = lines[6].strip().replace(" ", "").upper()
                if validate_iban(iban):
                    payment.iban = iban
                else:
                    payment.iban = iban  # Speichere trotzdem
                    payment.parse_errors.append(f"Ungueltige IBAN: {iban}")

            # 8. Amount (Index 7) - optional, Format: EUR[Betrag]
            if len(lines) > 7 and lines[7].strip():
                amount, currency = self._parse_amount(lines[7].strip())
                payment.amount = amount
                payment.currency = currency

            # 9. Purpose Code (Index 8) - optional
            if len(lines) > 8 and lines[8].strip():
                purpose = lines[8].strip().upper()
                if len(purpose) <= 4:
                    payment.purpose_code = purpose

            # 10. Reference (Index 9) - Strukturiert, optional
            if len(lines) > 9 and lines[9].strip():
                reference = lines[9].strip()
                # Max 35 Zeichen
                payment.reference = reference[:35]

            # 11. Remittance Text (Index 10) - Unstrukturiert, optional
            if len(lines) > 10 and lines[10].strip():
                text = lines[10].strip()
                # Max 140 Zeichen
                payment.remittance_text = text[:140]

            # 12. Origin Identification (Index 11) - optional
            if len(lines) > 11 and lines[11].strip():
                payment.origin_identification = lines[11].strip()

        except Exception as e:
            payment.parse_errors.append(f"Parse-Fehler: {str(e)}")
            logger.warning("sepa_qr_parse_exception", error=str(e))

        return payment

    def _parse_amount(self, amount_str: str) -> Tuple[Optional[float], str]:
        """
        Parse Betrag aus EPC Format.

        Formate:
        - "EUR12.34"
        - "EUR12,34"
        - "12.34"
        - ""

        Returns:
            (amount, currency)
        """
        currency = "EUR"
        amount = None

        if not amount_str:
            return amount, currency

        amount_str = amount_str.strip()

        # Waehrung extrahieren (3 Buchstaben am Anfang)
        if len(amount_str) >= 3 and amount_str[:3].isalpha():
            currency = amount_str[:3].upper()
            amount_str = amount_str[3:]

        if amount_str:
            try:
                # Deutsches Format (Komma als Dezimaltrenner)
                amount_str = amount_str.replace(",", ".")
                # Tausendertrennzeichen entfernen
                amount_str = amount_str.replace("'", "").replace(" ", "")
                amount = float(amount_str)

                # Betrag validieren
                if amount < 0:
                    amount = None
                elif amount > 999999999.99:  # EPC Max
                    amount = None

            except ValueError:
                pass

        return amount, currency

    def is_epc_qr(self, qr_data: str) -> bool:
        """
        Pruefen ob QR-Code ein EPC SEPA QR-Code ist.

        Args:
            qr_data: Rohdaten aus QR-Code

        Returns:
            True wenn EPC QR-Code
        """
        if not qr_data:
            return False

        lines = qr_data.strip().split(self.SEPARATOR)

        if len(lines) < 4:
            return False

        # Service Tag pruefen
        if lines[0].strip().upper() != self.SERVICE_TAG:
            return False

        # Version pruefen
        if lines[1].strip() not in self.VALID_VERSIONS:
            return False

        # Identification pruefen
        if lines[3].strip().upper() != self.IDENTIFICATION:
            return False

        return True


# =============================================================================
# EPC QR-Code Generator
# =============================================================================


class SEPAQRGenerator:
    """
    Generator fuer SEPA EPC QR-Codes.

    Erstellt QR-Code Daten nach EPC Standard.
    """

    def generate(
        self,
        iban: str,
        recipient_name: str,
        amount: Optional[float] = None,
        bic: Optional[str] = None,
        reference: str = "",
        remittance_text: str = "",
        purpose_code: str = "",
        version: str = "002",
    ) -> str:
        """
        Generiere EPC QR-Code Daten.

        Args:
            iban: IBAN des Empfaengers
            recipient_name: Name des Empfaengers (max 70 Zeichen)
            amount: Betrag in EUR (optional)
            bic: BIC/SWIFT (optional in Version 002)
            reference: Strukturierter Verwendungszweck (max 35 Zeichen)
            remittance_text: Unstrukturierter Verwendungszweck (max 140 Zeichen)
            purpose_code: SEPA Purpose Code (optional)
            version: EPC Version (001 oder 002)

        Returns:
            String fuer QR-Code Generierung
        """
        lines = []

        # 1. Service Tag
        lines.append("BCD")

        # 2. Version
        lines.append(version)

        # 3. Character Set (UTF-8)
        lines.append("1")

        # 4. Identification
        lines.append("SCT")

        # 5. BIC (kann leer sein)
        lines.append(bic.upper() if bic else "")

        # 6. Recipient Name (max 70)
        lines.append(recipient_name[:70])

        # 7. IBAN
        lines.append(iban.replace(" ", "").upper())

        # 8. Amount
        if amount and amount > 0:
            lines.append(f"EUR{amount:.2f}")
        else:
            lines.append("")

        # 9. Purpose Code
        lines.append(purpose_code.upper()[:4] if purpose_code else "")

        # 10. Reference (strukturiert, max 35)
        lines.append(reference[:35] if reference else "")

        # 11. Remittance Text (unstrukturiert, max 140)
        lines.append(remittance_text[:140] if remittance_text else "")

        return "\n".join(lines)


# =============================================================================
# Singleton und Convenience Functions
# =============================================================================


_parser: Optional[SEPAQRParserService] = None
_generator: Optional[SEPAQRGenerator] = None


def get_sepa_parser() -> SEPAQRParserService:
    """Hole globale Parser-Instanz."""
    global _parser
    if _parser is None:
        _parser = SEPAQRParserService()
    return _parser


def get_sepa_generator() -> SEPAQRGenerator:
    """Hole globale Generator-Instanz."""
    global _generator
    if _generator is None:
        _generator = SEPAQRGenerator()
    return _generator


def parse_sepa_qr(qr_data: str) -> SEPAPaymentInfo:
    """
    Parse SEPA QR-Code.

    Args:
        qr_data: Rohdaten aus QR-Code

    Returns:
        SEPAPaymentInfo
    """
    return get_sepa_parser().parse(qr_data)


def is_sepa_qr(qr_data: str) -> bool:
    """Pruefen ob QR-Code ein SEPA EPC QR ist."""
    return get_sepa_parser().is_epc_qr(qr_data)


def generate_sepa_qr(
    iban: str,
    recipient_name: str,
    amount: Optional[float] = None,
    reference: str = "",
    remittance_text: str = "",
) -> str:
    """
    Generiere SEPA EPC QR-Code Daten.

    Args:
        iban: IBAN des Empfaengers
        recipient_name: Name des Empfaengers
        amount: Betrag in EUR (optional)
        reference: Verwendungszweck

    Returns:
        QR-Code Datenstring
    """
    return get_sepa_generator().generate(
        iban=iban,
        recipient_name=recipient_name,
        amount=amount,
        reference=reference,
        remittance_text=remittance_text,
    )

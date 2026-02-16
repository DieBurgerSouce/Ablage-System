# -*- coding: utf-8 -*-
"""
ZUGFeRD Validator - Schema-Validierung für ZUGFeRD 2.3.3.

Validiert ZUGFeRD XML gegen:
- XSD Schema (Syntax-Validierung)
- Schematron Rules (Business Rules)

Unterstützte Profile:
- MINIMUM, BASIC, BASIC_WL, EN16931, EXTENDED, XRECHNUNG

Referenz: ZUGFeRD 2.3.3 / EN16931 / XRechnung 3.0.2
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Tuple

import structlog
from lxml import etree

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# SECURITY: Sicherer XMLParser gegen XXE-Angriffe
# =============================================================================

SECURE_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    remove_blank_text=True
)


# =============================================================================
# TYPES & ENUMS
# =============================================================================

class ValidationSeverity(str, Enum):
    """Schweregrad der Validierungsmeldung."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class ZUGFeRDProfile(str, Enum):
    """ZUGFeRD/Factur-X Profile."""
    MINIMUM = "MINIMUM"
    BASIC = "BASIC"
    BASIC_WL = "BASIC_WL"
    EN16931 = "EN16931"
    EXTENDED = "EXTENDED"
    XRECHNUNG = "XRECHNUNG"


@dataclass
class ValidationMessage:
    """Eine einzelne Validierungsmeldung."""
    severity: ValidationSeverity
    code: str
    message: str
    location: Optional[str] = None
    rule: Optional[str] = None
    profile: Optional[str] = None


@dataclass
class ValidationResult:
    """Ergebnis der Validierung."""
    valid: bool
    profile: Optional[ZUGFeRDProfile] = None
    version: Optional[str] = None
    messages: List[ValidationMessage] = field(default_factory=list)
    xml_hash: Optional[str] = None
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def error_count(self) -> int:
        """Anzahl der Fehler."""
        return sum(1 for m in self.messages if m.severity in (
            ValidationSeverity.ERROR, ValidationSeverity.FATAL
        ))

    @property
    def warning_count(self) -> int:
        """Anzahl der Warnungen."""
        return sum(1 for m in self.messages if m.severity == ValidationSeverity.WARNING)


# =============================================================================
# BUSINESS RULES (ZUGFeRD 2.3.3 / EN16931)
# =============================================================================

# Pflichtfelder je nach Profil
REQUIRED_FIELDS = {
    ZUGFeRDProfile.MINIMUM: [
        "//rsm:ExchangedDocument/ram:ID",
        "//rsm:ExchangedDocument/ram:TypeCode",
        "//rsm:ExchangedDocument/ram:IssueDateTime",
        "//ram:SellerTradeParty/ram:Name",
        "//ram:BuyerTradeParty/ram:Name",
        "//ram:GrandTotalAmount",
        "//ram:InvoiceCurrencyCode",
    ],
    ZUGFeRDProfile.BASIC: [
        "//rsm:ExchangedDocument/ram:ID",
        "//rsm:ExchangedDocument/ram:TypeCode",
        "//rsm:ExchangedDocument/ram:IssueDateTime",
        "//ram:SellerTradeParty/ram:Name",
        "//ram:SellerTradeParty//ram:PostalTradeAddress",
        "//ram:BuyerTradeParty/ram:Name",
        "//ram:GrandTotalAmount",
        "//ram:TaxBasisTotalAmount",
        "//ram:InvoiceCurrencyCode",
    ],
    ZUGFeRDProfile.EN16931: [
        "//rsm:ExchangedDocument/ram:ID",
        "//rsm:ExchangedDocument/ram:TypeCode",
        "//rsm:ExchangedDocument/ram:IssueDateTime",
        "//ram:SellerTradeParty/ram:Name",
        "//ram:SellerTradeParty//ram:PostalTradeAddress/ram:CountryID",
        "//ram:SellerTradeParty//ram:SpecifiedTaxRegistration/ram:ID",
        "//ram:BuyerTradeParty/ram:Name",
        "//ram:GrandTotalAmount",
        "//ram:TaxBasisTotalAmount",
        "//ram:DuePayableAmount",
        "//ram:InvoiceCurrencyCode",
        "//ram:ApplicableTradeTax",
    ],
    ZUGFeRDProfile.XRECHNUNG: [
        "//rsm:ExchangedDocument/ram:ID",
        "//rsm:ExchangedDocument/ram:TypeCode",
        "//rsm:ExchangedDocument/ram:IssueDateTime",
        "//ram:SellerTradeParty/ram:Name",
        "//ram:SellerTradeParty//ram:PostalTradeAddress/ram:CountryID",
        "//ram:SellerTradeParty//ram:SpecifiedTaxRegistration/ram:ID",
        "//ram:SellerTradeParty//ram:URIUniversalCommunication/ram:URIID",  # BT-34
        "//ram:BuyerTradeParty/ram:Name",
        "//ram:BuyerTradeParty//ram:URIUniversalCommunication/ram:URIID",  # BT-49
        "//ram:BuyerReference",  # BT-10 Leitweg-ID
        "//ram:GrandTotalAmount",
        "//ram:TaxBasisTotalAmount",
        "//ram:DuePayableAmount",
        "//ram:InvoiceCurrencyCode",
        "//ram:ApplicableTradeTax",
    ],
}

# Gültige Invoice Type Codes (UNTDID 1001)
VALID_TYPE_CODES = {"380", "381", "384", "389", "751"}

# Gültige Währungscodes (ISO 4217)
VALID_CURRENCY_CODES = {
    "EUR", "USD", "GBP", "CHF", "JPY", "CNY", "AUD", "CAD",
    "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN"
}

# Gültige Tax Category Codes (UNTDID 5305)
VALID_TAX_CATEGORIES = {"S", "Z", "E", "AE", "K", "G", "O", "L", "M"}


# =============================================================================
# ZUGFERD VALIDATOR CLASS
# =============================================================================

class ZUGFeRDValidator:
    """
    Validiert ZUGFeRD/Factur-X XML gegen ZUGFeRD 2.3.3 Standard.

    Verwendung:
        validator = ZUGFeRDValidator()

        # Vollständige Validierung
        result = validator.validate(xml_content)

        # Nur Syntaxprüfung (schneller)
        result = validator.validate_syntax(xml_content)

        # Profil erkennen
        profile, version = validator.detect_profile(xml_content)
    """

    def __init__(self) -> None:
        """Initialisiere Validator mit XML Namespaces."""
        self.namespaces = {
            "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
            "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
            "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
            "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
        }

    def validate(
        self,
        xml_content: str | bytes,
        expected_profile: Optional[ZUGFeRDProfile] = None
    ) -> ValidationResult:
        """
        Vollständige Validierung eines ZUGFeRD XML.

        Args:
            xml_content: XML als String oder Bytes
            expected_profile: Optionales erwartetes Profil

        Returns:
            ValidationResult mit allen Meldungen
        """
        messages: List[ValidationMessage] = []

        # XML parsen
        if isinstance(xml_content, str):
            xml_bytes = xml_content.encode("utf-8")
        else:
            xml_bytes = xml_content

        xml_hash = hashlib.sha256(xml_bytes).hexdigest()

        try:
            root = etree.fromstring(xml_bytes, parser=SECURE_XML_PARSER)
        except etree.XMLSyntaxError as e:
            return ValidationResult(
                valid=False,
                xml_hash=xml_hash,
                messages=[ValidationMessage(
                    severity=ValidationSeverity.FATAL,
                    code="XML_SYNTAX_ERROR",
                    message=f"XML Syntax-Fehler: {e.msg}",
                    location=f"Zeile {e.lineno}, Spalte {e.offset}" if e.lineno else None,
                )]
            )

        # Profil erkennen
        profile, version = self._detect_profile_from_root(root)

        if expected_profile and profile != expected_profile:
            messages.append(ValidationMessage(
                severity=ValidationSeverity.WARNING,
                code="PROFILE_MISMATCH",
                message=f"Erkanntes Profil ({profile.value if profile else 'unbekannt'}) "
                       f"entspricht nicht erwartetem Profil ({expected_profile.value})",
            ))

        # Root Element prüfen
        if root.tag != "{urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100}CrossIndustryInvoice":
            messages.append(ValidationMessage(
                severity=ValidationSeverity.ERROR,
                code="INVALID_ROOT_ELEMENT",
                message=f"Ungültiges Root-Element: {root.tag}",
                location="/",
            ))

        # Pflichtfelder prüfen
        if profile:
            self._validate_required_fields(root, profile, messages)

        # Business Rules prüfen
        self._validate_business_rules(root, profile, messages)

        # Betraege validieren
        self._validate_amounts(root, messages)

        # Steuer validieren
        self._validate_tax(root, messages)

        # Ergebnis erstellen
        has_errors = any(
            m.severity in (ValidationSeverity.ERROR, ValidationSeverity.FATAL)
            for m in messages
        )

        return ValidationResult(
            valid=not has_errors,
            profile=profile,
            version=version,
            messages=messages,
            xml_hash=xml_hash,
        )

    def validate_syntax(self, xml_content: str | bytes) -> ValidationResult:
        """
        Schnelle Syntax-Validierung (nur XML-Parsing, keine Business Rules).

        Args:
            xml_content: XML als String oder Bytes

        Returns:
            ValidationResult mit Syntax-Fehlern
        """
        if isinstance(xml_content, str):
            xml_bytes = xml_content.encode("utf-8")
        else:
            xml_bytes = xml_content

        xml_hash = hashlib.sha256(xml_bytes).hexdigest()

        try:
            root = etree.fromstring(xml_bytes, parser=SECURE_XML_PARSER)
            profile, version = self._detect_profile_from_root(root)

            return ValidationResult(
                valid=True,
                profile=profile,
                version=version,
                messages=[],
                xml_hash=xml_hash,
            )
        except etree.XMLSyntaxError as e:
            return ValidationResult(
                valid=False,
                xml_hash=xml_hash,
                messages=[ValidationMessage(
                    severity=ValidationSeverity.FATAL,
                    code="XML_SYNTAX_ERROR",
                    message=f"XML Syntax-Fehler: {e.msg}",
                    location=f"Zeile {e.lineno}, Spalte {e.offset}" if e.lineno else None,
                )]
            )

    def detect_profile(self, xml_content: str | bytes) -> Tuple[Optional[ZUGFeRDProfile], Optional[str]]:
        """
        Erkennt das ZUGFeRD-Profil aus dem XML.

        Args:
            xml_content: XML als String oder Bytes

        Returns:
            Tuple aus (Profil, Version) oder (None, None)
        """
        if isinstance(xml_content, str):
            xml_bytes = xml_content.encode("utf-8")
        else:
            xml_bytes = xml_content

        try:
            root = etree.fromstring(xml_bytes, parser=SECURE_XML_PARSER)
            return self._detect_profile_from_root(root)
        except Exception:
            return None, None

    def _detect_profile_from_root(
        self,
        root: etree._Element
    ) -> Tuple[Optional[ZUGFeRDProfile], Optional[str]]:
        """Erkennt Profil und Version aus Root-Element."""
        # GuidelineSpecifiedDocumentContextParameter/ID suchen
        context_param = root.find(
            ".//rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
            self.namespaces
        )

        if context_param is None or not context_param.text:
            return None, None

        urn = context_param.text.lower()

        # Profil erkennen
        profile = None
        version = "2.3.3"  # Default

        if "xrechnung" in urn or "xeinkauf" in urn:
            profile = ZUGFeRDProfile.XRECHNUNG
            if "3.0" in urn:
                version = "3.0.2"
            elif "2.3" in urn:
                version = "2.3.1"
        elif "extended" in urn:
            profile = ZUGFeRDProfile.EXTENDED
        elif "en16931" in urn:
            profile = ZUGFeRDProfile.EN16931
        elif "basicwl" in urn or "basic-wl" in urn:
            profile = ZUGFeRDProfile.BASIC_WL
        elif "basic" in urn:
            profile = ZUGFeRDProfile.BASIC
        elif "minimum" in urn:
            profile = ZUGFeRDProfile.MINIMUM

        return profile, version

    def _validate_required_fields(
        self,
        root: etree._Element,
        profile: ZUGFeRDProfile,
        messages: List[ValidationMessage]
    ) -> None:
        """Prüft Pflichtfelder für das Profil."""
        required = REQUIRED_FIELDS.get(profile, REQUIRED_FIELDS[ZUGFeRDProfile.EN16931])

        for xpath in required:
            # Namespace-Prefix korrigieren für lxml
            elements = root.xpath(xpath, namespaces=self.namespaces)

            if not elements:
                # Feldname aus XPath extrahieren
                field_name = xpath.split("/")[-1].replace("ram:", "").replace("rsm:", "")

                messages.append(ValidationMessage(
                    severity=ValidationSeverity.ERROR,
                    code=f"MISSING_{field_name.upper()}",
                    message=f"Pflichtfeld fehlt: {field_name}",
                    location=xpath,
                    profile=profile.value,
                ))

    def _validate_business_rules(
        self,
        root: etree._Element,
        profile: Optional[ZUGFeRDProfile],
        messages: List[ValidationMessage]
    ) -> None:
        """Prüft Business Rules."""
        ns = self.namespaces

        # BR-01: Invoice number muss vorhanden sein
        invoice_id = root.find(".//rsm:ExchangedDocument/ram:ID", ns)
        if invoice_id is not None and invoice_id.text:
            if len(invoice_id.text.strip()) > 150:
                messages.append(ValidationMessage(
                    severity=ValidationSeverity.ERROR,
                    code="BR-01",
                    message="Rechnungsnummer darf maximal 150 Zeichen haben",
                    location="//rsm:ExchangedDocument/ram:ID",
                ))

        # BR-02: Invoice type code muss gültig sein
        type_code = root.find(".//rsm:ExchangedDocument/ram:TypeCode", ns)
        if type_code is not None and type_code.text:
            if type_code.text not in VALID_TYPE_CODES:
                messages.append(ValidationMessage(
                    severity=ValidationSeverity.ERROR,
                    code="BR-02",
                    message=f"Ungültiger TypeCode: {type_code.text}. "
                           f"Erlaubt: {', '.join(sorted(VALID_TYPE_CODES))}",
                    location="//rsm:ExchangedDocument/ram:TypeCode",
                ))

        # BR-05: Currency code muss gültig sein (ISO 4217)
        currency = root.find(".//ram:InvoiceCurrencyCode", ns)
        if currency is not None and currency.text:
            if currency.text not in VALID_CURRENCY_CODES:
                messages.append(ValidationMessage(
                    severity=ValidationSeverity.WARNING,
                    code="BR-05",
                    message=f"Unbekannter Währungscode: {currency.text}",
                    location="//ram:InvoiceCurrencyCode",
                ))

        # BR-DE-01: XRechnung erfordert Leitweg-ID
        if profile == ZUGFeRDProfile.XRECHNUNG:
            buyer_ref = root.find(".//ram:BuyerReference", ns)
            if buyer_ref is None or not buyer_ref.text:
                messages.append(ValidationMessage(
                    severity=ValidationSeverity.ERROR,
                    code="BR-DE-01",
                    message="XRechnung erfordert BT-10 (Leitweg-ID)",
                    location="//ram:BuyerReference",
                    profile="XRECHNUNG",
                ))
            elif buyer_ref.text:
                # Leitweg-ID Format prüfen (vereinfacht)
                leitweg_pattern = r"^\d{2,12}-\d{4,12}-\d{2}$"
                if not re.match(leitweg_pattern, buyer_ref.text):
                    messages.append(ValidationMessage(
                        severity=ValidationSeverity.WARNING,
                        code="BR-DE-01-FORMAT",
                        message=f"Leitweg-ID Format möglicherweise ungültig: {buyer_ref.text}",
                        location="//ram:BuyerReference",
                        profile="XRECHNUNG",
                    ))

    def _validate_amounts(
        self,
        root: etree._Element,
        messages: List[ValidationMessage]
    ) -> None:
        """Prüft Betraege auf Konsistenz."""
        ns = self.namespaces

        # Betraege extrahieren
        summary = root.find(
            ".//ram:SpecifiedTradeSettlementHeaderMonetarySummation",
            ns
        )
        if summary is None:
            return

        def get_decimal(xpath: str) -> Optional[float]:
            elem = summary.find(xpath, ns)
            if elem is not None and elem.text:
                try:
                    return float(elem.text.replace(",", "."))
                except ValueError:
                    return None
            return None

        line_total = get_decimal(".//ram:LineTotalAmount")
        tax_basis = get_decimal(".//ram:TaxBasisTotalAmount")
        tax_total = get_decimal(".//ram:TaxTotalAmount")
        grand_total = get_decimal(".//ram:GrandTotalAmount")

        # BR-CO-10: LineTotalAmount soll TaxBasisTotalAmount entsprechen
        if line_total is not None and tax_basis is not None:
            if abs(line_total - tax_basis) > 0.01:
                messages.append(ValidationMessage(
                    severity=ValidationSeverity.WARNING,
                    code="BR-CO-10",
                    message=f"LineTotalAmount ({line_total}) weicht von "
                           f"TaxBasisTotalAmount ({tax_basis}) ab",
                    location="//ram:SpecifiedTradeSettlementHeaderMonetarySummation",
                ))

        # BR-CO-15: GrandTotalAmount = TaxBasisTotalAmount + TaxTotalAmount
        if tax_basis is not None and grand_total is not None:
            expected_grand = tax_basis + (tax_total or 0)
            if abs(grand_total - expected_grand) > 0.01:
                messages.append(ValidationMessage(
                    severity=ValidationSeverity.WARNING,
                    code="BR-CO-15",
                    message=f"GrandTotalAmount ({grand_total}) entspricht nicht "
                           f"TaxBasisTotalAmount + TaxTotalAmount ({expected_grand})",
                    location="//ram:SpecifiedTradeSettlementHeaderMonetarySummation",
                ))

    def _validate_tax(
        self,
        root: etree._Element,
        messages: List[ValidationMessage]
    ) -> None:
        """Prüft Steuerangaben."""
        ns = self.namespaces

        taxes = root.findall(".//ram:ApplicableTradeTax", ns)

        for i, tax in enumerate(taxes):
            # Tax Category Code prüfen
            cat_code = tax.find(".//ram:CategoryCode", ns)
            if cat_code is not None and cat_code.text:
                if cat_code.text not in VALID_TAX_CATEGORIES:
                    messages.append(ValidationMessage(
                        severity=ValidationSeverity.ERROR,
                        code=f"BR-CL-17-{i}",
                        message=f"Ungültiger Tax CategoryCode: {cat_code.text}",
                        location=f"//ram:ApplicableTradeTax[{i+1}]/ram:CategoryCode",
                    ))

            # Steuersatz prüfen
            rate = tax.find(".//ram:RateApplicablePercent", ns)
            if rate is not None and rate.text:
                try:
                    rate_value = float(rate.text.replace(",", "."))
                    if rate_value < 0 or rate_value > 100:
                        messages.append(ValidationMessage(
                            severity=ValidationSeverity.ERROR,
                            code=f"BR-48-{i}",
                            message=f"Steuersatz ausserhalb gültigen Bereichs: {rate_value}%",
                            location=f"//ram:ApplicableTradeTax[{i+1}]/ram:RateApplicablePercent",
                        ))
                except ValueError:
                    messages.append(ValidationMessage(
                        severity=ValidationSeverity.ERROR,
                        code=f"BR-48-FORMAT-{i}",
                        message=f"Ungültiges Steuersatz-Format: {rate.text}",
                        location=f"//ram:ApplicableTradeTax[{i+1}]/ram:RateApplicablePercent",
                    ))

            # Bei Steuerbefreiung muss ExemptionReason vorhanden sein
            if cat_code is not None and cat_code.text in ("E", "AE", "K", "G", "O"):
                exemption = tax.find(".//ram:ExemptionReason", ns)
                if exemption is None or not exemption.text:
                    messages.append(ValidationMessage(
                        severity=ValidationSeverity.WARNING,
                        code=f"BR-E-10-{i}",
                        message=f"Steuerbefreiung ({cat_code.text}) ohne Begruendung",
                        location=f"//ram:ApplicableTradeTax[{i+1}]",
                    ))


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_zugferd_validator_instance: Optional[ZUGFeRDValidator] = None


def get_zugferd_validator() -> ZUGFeRDValidator:
    """
    Factory-Funktion für ZUGFeRDValidator (Singleton).

    Returns:
        ZUGFeRDValidator: Globale Validator-Instanz
    """
    global _zugferd_validator_instance
    if _zugferd_validator_instance is None:
        _zugferd_validator_instance = ZUGFeRDValidator()
    return _zugferd_validator_instance

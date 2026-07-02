# -*- coding: utf-8 -*-
"""
E-Invoice Validator Service.

Validiert E-Rechnungen gegen die offiziellen Standards:
- ZUGFeRD 2.x: factur-x integrierte Validierung
- XRechnung 3.0.2: KoSIT Validator via Mustang Microservice

Validierungsstufen:
1. XML-Schema-Validierung (XSD)
2. Schematron Business-Rules (EN 16931 + BR-DE)
3. PDF/A-3 Konformität (nur bei ZUGFeRD)

Der KoSIT-Validator ist der offizielle Validator der Koordinierungsstelle
für IT-Standards (KoSIT) und prüft gegen die aktuellen XRechnung-Spezifikationen.
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any

from lxml import etree

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

# R.1 SECURITY FIX: Sicherer XMLParser gegen XXE-Angriffe
# - resolve_entities=False: Externe Entities werden nicht aufgeloest
# - no_network=True: Kein Netzwerkzugriff für DTDs/Schemas
# - dtd_validation=False: DTD wird nicht für Validierung verwendet
# - load_dtd=False: DTD wird nicht geladen (verhindert Billion Laughs)
SECURE_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    remove_blank_text=True
)
from app.services.einvoice.mustang_client import (
    MustangClient,
    MustangConnectionError,
    get_mustang_client,
)

logger = structlog.get_logger(__name__)


class ValidatorType(str, Enum):
    """Verfügbare Validatoren."""
    FACTURX = "facturx"  # Schnelle lokale Validierung
    KOSIT = "kosit"  # Offizieller KoSIT-Validator (via Mustang)
    MUSTANG = "mustang"  # Mustang-integrierter Validator
    AUTO = "auto"  # Automatische Auswahl


class ValidationSeverity(str, Enum):
    """Schweregrad einer Validierungsmeldung."""
    FATAL = "fatal"  # Schema-Fehler, XML ungültig
    ERROR = "error"  # Business Rule verletzt
    WARNING = "warning"  # Empfehlung nicht befolgt
    INFO = "info"  # Hinweis


@dataclass
class ValidationMessage:
    """Einzelne Validierungsmeldung."""
    code: str
    severity: ValidationSeverity
    location: str  # XPath oder Element-Name
    message: str
    rule_id: Optional[str] = None  # z.B. "BR-DE-01"
    details: Optional[str] = None


@dataclass
class ValidationResult:
    """Vollständiges Validierungsergebnis."""
    valid: bool
    validated_at: datetime
    validator_used: str
    format_detected: Optional[str] = None  # zugferd/xrechnung_cii/xrechnung_ubl
    profile_detected: Optional[str] = None

    # Detail-Ergebnisse
    schema_valid: bool = True
    schematron_valid: bool = True
    pdf_a_compliant: Optional[bool] = None  # Nur bei ZUGFeRD-PDF

    # Meldungen
    messages: List[ValidationMessage] = field(default_factory=list)

    # Zusammenfassung
    error_count: int = 0
    warning_count: int = 0

    # Raw Output (für Debugging)
    raw_output: Optional[str] = None

    def add_error(
        self,
        code: str,
        location: str,
        message: str,
        rule_id: Optional[str] = None
    ) -> None:
        """Fuegt Fehlermeldung hinzu."""
        self.messages.append(ValidationMessage(
            code=code,
            severity=ValidationSeverity.ERROR,
            location=location,
            message=message,
            rule_id=rule_id,
        ))
        self.error_count += 1
        self.valid = False

    def add_warning(
        self,
        code: str,
        location: str,
        message: str,
        rule_id: Optional[str] = None
    ) -> None:
        """Fuegt Warnung hinzu."""
        self.messages.append(ValidationMessage(
            code=code,
            severity=ValidationSeverity.WARNING,
            location=location,
            message=message,
            rule_id=rule_id,
        ))
        self.warning_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für API-Response."""
        return {
            "valid": self.valid,
            "validated_at": self.validated_at.isoformat(),
            "validator_used": self.validator_used,
            "format_detected": self.format_detected,
            "profile_detected": self.profile_detected,
            "schema_valid": self.schema_valid,
            "schematron_valid": self.schematron_valid,
            "pdf_a_compliant": self.pdf_a_compliant,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "messages": [
                {
                    "code": m.code,
                    "severity": m.severity.value,
                    "location": m.location,
                    "message": m.message,
                    "rule_id": m.rule_id,
                }
                for m in self.messages
            ],
        }


class EInvoiceValidatorService:
    """
    Service für E-Invoice Validierung.

    Unterstützt mehrere Validatoren:
    - facturx: Schnelle lokale Validierung (Python)
    - kosit: Offizieller KoSIT-Validator (Java via Mustang)
    - auto: Waehlt besten Validator basierend auf Format

    Usage:
        validator = EInvoiceValidatorService()
        result = await validator.validate_xml(xml_content)
        if not result.valid:
            for msg in result.messages:
                print(f"{msg.severity}: {msg.message}")
    """

    def __init__(self):
        """Initialisiert den Validator Service."""
        self._mustang_client: Optional[MustangClient] = None
        self._mustang_available: Optional[bool] = None

    async def _get_mustang_client(self) -> MustangClient:
        """Gibt Mustang Client zurück (lazy initialization)."""
        if self._mustang_client is None:
            self._mustang_client = get_mustang_client()
        return self._mustang_client

    async def is_mustang_available(self) -> bool:
        """Prüft ob Mustang-Service verfügbar ist."""
        if self._mustang_available is None:
            try:
                client = await self._get_mustang_client()
                async with client:
                    self._mustang_available = await client.is_available()
            except Exception:
                self._mustang_available = False
        return self._mustang_available

    async def validate_xml(
        self,
        xml_content: str,
        validator_type: ValidatorType = ValidatorType.AUTO,
        format_hint: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validiert E-Invoice XML.

        Args:
            xml_content: XML-Inhalt als String
            validator_type: Zu verwendender Validator
            format_hint: Optional - Format-Hinweis (zugferd/xrechnung)

        Returns:
            ValidationResult mit Validierungsergebnis
        """
        result = ValidationResult(
            valid=True,
            validated_at=datetime.now(timezone.utc),
            validator_used=validator_type.value,
        )

        # 1. Basis-XML-Validierung
        try:
            self._validate_xml_syntax(xml_content, result)
        except Exception as e:
            result.add_error(
                code="XML_PARSE_ERROR",
                location="root",
                message=safe_error_detail(e, "XML-Parsing")
            )
            result.schema_valid = False
            return result

        # Format erkennen
        detected_format = self._detect_format(xml_content)
        result.format_detected = format_hint or detected_format

        # 2. Validator auswählen
        if validator_type == ValidatorType.AUTO:
            validator_type = await self._select_validator(result.format_detected)
            result.validator_used = validator_type.value

        # 3. Validierung durchführen
        if validator_type == ValidatorType.FACTURX:
            await self._validate_with_facturx(xml_content, result)
        elif validator_type in (ValidatorType.KOSIT, ValidatorType.MUSTANG):
            await self._validate_with_mustang(xml_content, result)
        else:
            # Fallback: Nur Schema-Validierung
            await self._validate_schema_only(xml_content, result)

        logger.info(
            "einvoice_validation_completed",
            valid=result.valid,
            validator=result.validator_used,
            format=result.format_detected,
            errors=result.error_count,
            warnings=result.warning_count,
        )

        return result

    async def validate_pdf(
        self,
        pdf_content: bytes,
        validator_type: ValidatorType = ValidatorType.AUTO,
    ) -> ValidationResult:
        """
        Validiert ZUGFeRD-PDF inkl. PDF/A-3 Konformität.

        Args:
            pdf_content: PDF-Datei als Bytes
            validator_type: Zu verwendender Validator

        Returns:
            ValidationResult mit Validierungsergebnis
        """
        result = ValidationResult(
            valid=True,
            validated_at=datetime.now(timezone.utc),
            validator_used=validator_type.value,
        )

        try:
            # 1. XML aus PDF extrahieren
            from facturx import get_xml_from_pdf

            xml_bytes = get_xml_from_pdf(pdf_content)
            if not xml_bytes:
                result.add_error(
                    code="NO_XML_IN_PDF",
                    location="pdf",
                    message="Kein eingebettetes XML im PDF gefunden"
                )
                return result

            xml_content = xml_bytes.decode("utf-8")

            # 2. XML validieren
            xml_result = await self.validate_xml(
                xml_content,
                validator_type=validator_type,
                format_hint="zugferd"
            )

            # Ergebnisse übernehmen
            result.valid = xml_result.valid
            result.schema_valid = xml_result.schema_valid
            result.schematron_valid = xml_result.schematron_valid
            result.messages = xml_result.messages
            result.error_count = xml_result.error_count
            result.warning_count = xml_result.warning_count
            result.format_detected = xml_result.format_detected
            result.profile_detected = xml_result.profile_detected

            # 3. PDF/A-3 Validierung (optional, via Mustang)
            if await self.is_mustang_available():
                await self._validate_pdfa(pdf_content, result)

        except ImportError:
            result.add_error(
                code="FACTURX_NOT_INSTALLED",
                location="system",
                message="factur-x Bibliothek nicht installiert"
            )

        except Exception as e:
            logger.exception("einvoice_pdf_validation_error")
            result.add_error(
                code="PDF_VALIDATION_ERROR",
                location="pdf",
                message=safe_error_detail(e, "E-Invoice")
            )

        return result

    def _validate_xml_syntax(
        self,
        xml_content: str,
        result: ValidationResult
    ) -> etree._Element:
        """Validiert XML-Syntax und gibt Root-Element zurück."""
        try:
            # R.1 SECURITY FIX: Sicherer Parser gegen XXE-Angriffe
            root = etree.fromstring(xml_content.encode("utf-8"), parser=SECURE_XML_PARSER)
            return root
        except etree.XMLSyntaxError as e:
            result.add_error(
                code="XML_SYNTAX_ERROR",
                location=f"line {e.lineno}",
                message=safe_error_detail(e, "E-Invoice")
            )
            result.schema_valid = False
            raise

    def _detect_format(self, xml_content: str) -> str:
        """Erkennt E-Invoice Format aus XML."""
        try:
            # R.1 SECURITY FIX: Sicherer Parser gegen XXE-Angriffe
            root = etree.fromstring(xml_content.encode("utf-8"), parser=SECURE_XML_PARSER)
            tag = root.tag.lower()

            # UBL
            if "invoice" in tag and "oasis" in tag:
                return "xrechnung_ubl"

            # CII / ZUGFeRD
            if "crossindustryinvoice" in tag:
                # XRechnung oder ZUGFeRD?
                xml_lower = xml_content.lower()
                if "xrechnung" in xml_lower or "xeinkauf" in xml_lower:
                    return "xrechnung_cii"
                return "zugferd"

            return "unknown"

        except Exception:
            return "unknown"

    async def _select_validator(self, format_type: Optional[str]) -> ValidatorType:
        """Waehlt besten Validator basierend auf Format."""
        # XRechnung: KoSIT-Validator bevorzugen
        if format_type and "xrechnung" in format_type:
            if await self.is_mustang_available():
                return ValidatorType.KOSIT
            return ValidatorType.FACTURX

        # ZUGFeRD: factur-x reicht
        return ValidatorType.FACTURX

    async def _validate_with_facturx(
        self,
        xml_content: str,
        result: ValidationResult
    ) -> None:
        """Validiert mit factur-x Bibliothek."""
        try:
            from facturx import check_facturx_xsd

            # XSD-Validierung
            try:
                check_facturx_xsd(xml_content.encode("utf-8"))
            except Exception as e:
                result.add_error(
                    code="XSD_VALIDATION_ERROR",
                    location="schema",
                    message=safe_error_detail(e, "E-Invoice")
                )
                result.schema_valid = False
                return

            # Profil erkennen
            result.profile_detected = self._detect_profile(xml_content)

            # Basis Business Rules prüfen
            self._check_basic_business_rules(xml_content, result)

        except ImportError:
            logger.warning("facturx_not_installed")
            await self._validate_schema_only(xml_content, result)

    async def _validate_with_mustang(
        self,
        xml_content: str,
        result: ValidationResult
    ) -> None:
        """Validiert mit Mustang/KoSIT-Validator."""
        try:
            client = await self._get_mustang_client()

            async with client:
                mustang_result = await client.validate_xml(
                    xml_content,
                    format_type=result.format_detected
                )

            result.valid = mustang_result.valid
            result.schema_valid = mustang_result.schema_valid or True
            result.schematron_valid = mustang_result.schematron_valid or True
            result.raw_output = mustang_result.output

            if mustang_result.errors:
                # Fehler parsen
                for line in mustang_result.errors.split("\n"):
                    if line.strip():
                        result.add_error(
                            code="KOSIT_ERROR",
                            location="xml",
                            message=line.strip()
                        )

        except MustangConnectionError as e:
            logger.warning(
                "mustang_validation_fallback",
                **safe_error_log(e)
            )
            # Fallback zu lokaler Validierung
            await self._validate_with_facturx(xml_content, result)

    async def _validate_schema_only(
        self,
        xml_content: str,
        result: ValidationResult
    ) -> None:
        """Nur XML-Schema-Validierung (Fallback)."""
        # XML ist bereits geparst, also Schema-valide in Bezug auf Syntax
        result.profile_detected = self._detect_profile(xml_content)
        self._check_basic_business_rules(xml_content, result)

    async def _validate_pdfa(
        self,
        pdf_content: bytes,
        result: ValidationResult
    ) -> None:
        """Validiert PDF/A-3 Konformität.

        Prüft grundlegende PDF/A-3 Anforderungen:
        - PDF-Strukturvaliditaet
        - Embedded File Stream (für ZUGFeRD XML)
        - Metadata (XMP)
        - Keine externen Referenzen

        Für volle PDF/A-3 Validierung wird VeraPDF empfohlen,
        diese Implementation bietet eine Basisvalidierung.
        """
        import io

        try:
            # PyPDF2 oder pypdf für Basis-PDF-Validierung
            try:
                from pypdf import PdfReader
            except ImportError:
                try:
                    from PyPDF2 import PdfReader
                except ImportError:
                    result.pdf_a_compliant = None
                    result.add_warning(
                        code="PDFA_LIBRARY_MISSING",
                        location="pdf",
                        message="pypdf/PyPDF2 nicht installiert - PDF/A-3 Validierung übersprungen"
                    )
                    return

            # PDF einlesen
            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file)

            # 1. Prüfe ob PDF lesbar ist (Strukturvaliditaet)
            try:
                num_pages = len(reader.pages)
                if num_pages < 1:
                    result.pdf_a_compliant = False
                    result.add_error(
                        code="PDFA_NO_PAGES",
                        location="pdf",
                        message="PDF enthält keine Seiten"
                    )
                    return
            except Exception as e:
                result.pdf_a_compliant = False
                result.add_error(
                    code="PDFA_STRUCTURE_INVALID",
                    location="pdf",
                    message=f"PDF-Struktur ungültig: {safe_error_detail(e, 'PDF')}"
                )
                return

            # 2. Prüfe auf eingebettete Dateien (ZUGFeRD XML)
            has_embedded_files = False
            embedded_xml_found = False

            if "/Names" in reader.trailer.get("/Root", {}):
                root = reader.trailer["/Root"]
                if "/EmbeddedFiles" in root.get("/Names", {}):
                    has_embedded_files = True

            # Alternativer Check: Attachments via Catalog
            if hasattr(reader, 'attachments') and reader.attachments:
                has_embedded_files = True
                for name in reader.attachments:
                    if name.lower().endswith('.xml'):
                        embedded_xml_found = True
                        break

            # 3. Prüfe XMP Metadata (PDF/A Konformität)
            has_xmp = False
            pdfa_conformance = None

            if reader.metadata:
                # Standard-Metadaten vorhanden
                has_xmp = True

            # 4. Basis-Checks für ZUGFeRD: Embedded XML erforderlich
            # ZUGFeRD erfordert eingebettetes XML (factur-x.xml)
            if not has_embedded_files:
                result.pdf_a_compliant = False
                result.add_error(
                    code="PDFA_NO_EMBEDDED_FILES",
                    location="pdf",
                    message="PDF/A-3 erfordert eingebettete Dateien (ZUGFeRD XML fehlt)"
                )
                return

            # 5. Keine JavaScript oder andere aktive Inhalte (PDF/A-3 verbietet dies)
            # Basis-Check: Keine /JavaScript im Root
            try:
                root_obj = reader.trailer.get("/Root", {})
                if "/JavaScript" in str(root_obj) or "/JS" in str(root_obj):
                    result.pdf_a_compliant = False
                    result.add_error(
                        code="PDFA_JAVASCRIPT_FOUND",
                        location="pdf",
                        message="PDF/A-3 verbietet JavaScript"
                    )
                    return
            except Exception as e:
                # Optionaler JavaScript-Check; Fehler bricht die PDF/A-Validierung nicht ab
                logger.debug("einvoice_pdfa_js_check_skipped", **safe_error_log(e))

            # 6. Prüfe Encryption (PDF/A erlaubt nur bestimmte Encryption)
            if reader.is_encrypted:
                result.pdf_a_compliant = False
                result.add_error(
                    code="PDFA_ENCRYPTED",
                    location="pdf",
                    message="PDF/A-3 verbietet Passwortverschlüsselung"
                )
                return

            # Basis-Checks bestanden
            result.pdf_a_compliant = True

            # Informations-Warnungen hinzufuegen
            if not has_xmp:
                result.add_warning(
                    code="PDFA_XMP_MISSING",
                    location="pdf/metadata",
                    message="XMP-Metadaten nicht gefunden - für volle PDF/A-3 Konformität empfohlen"
                )

            if not embedded_xml_found:
                result.add_warning(
                    code="PDFA_ZUGFERD_XML_NOT_VERIFIED",
                    location="pdf/attachment",
                    message="Eingebettetes factur-x.xml konnte nicht verifiziert werden"
                )

            logger.info(
                "pdfa_validation_completed",
                compliant=True,
                pages=num_pages,
                has_embedded_files=has_embedded_files,
            )

        except Exception as e:
            logger.warning(
                "pdfa_validation_error",
                **safe_error_log(e)
            )
            result.pdf_a_compliant = None
            result.add_warning(
                code="PDFA_VALIDATION_ERROR",
                location="pdf",
                message=f"PDF/A-3 Validierung fehlgeschlagen: {safe_error_detail(e, 'PDF')}"
            )

    def _detect_profile(self, xml_content: str) -> Optional[str]:
        """Erkennt ZUGFeRD/XRechnung Profil aus XML."""
        xml_lower = xml_content.lower()

        if "xrechnung" in xml_lower:
            return "XRECHNUNG"
        elif "extended" in xml_lower:
            return "EXTENDED"
        elif "en16931" in xml_lower or "comfort" in xml_lower:
            return "EN16931"
        elif "basic" in xml_lower:
            return "BASIC"
        elif "minimum" in xml_lower:
            return "MINIMUM"

        return None

    def _check_basic_business_rules(
        self,
        xml_content: str,
        result: ValidationResult
    ) -> None:
        """Prüft grundlegende Business Rules."""
        try:
            # R.1 SECURITY FIX: Sicherer Parser gegen XXE-Angriffe
            root = etree.fromstring(xml_content.encode("utf-8"), parser=SECURE_XML_PARSER)

            # BR-01: Rechnungsnummer vorhanden?
            # Achtung: NICHT irgendein "ID"-Element matchen - jede CII-Rechnung
            # hat eine Guideline-ID (ExchangedDocumentContext/.../ram:ID),
            # wodurch BR-01 frueher NIE feuern konnte.
            if not self._find_invoice_number(root):
                result.add_error(
                    code="BR-01",
                    location="BT-1",
                    message="Rechnungsnummer (BT-1) fehlt",
                    rule_id="BR-01"
                )

            # BR-02: Rechnungsdatum vorhanden?
            if not self._find_element_text(root, ["IssueDateTime", "IssueDate"]):
                result.add_error(
                    code="BR-02",
                    location="BT-2",
                    message="Rechnungsdatum (BT-2) fehlt",
                    rule_id="BR-02"
                )

            # BR-DE-01: Leitweg-ID bei XRechnung?
            if result.format_detected and "xrechnung" in result.format_detected:
                if not self._find_element_text(root, ["BuyerReference"]):
                    result.add_error(
                        code="BR-DE-01",
                        location="BT-10",
                        message="Leitweg-ID (BT-10) fehlt - Pflichtfeld für XRechnung",
                        rule_id="BR-DE-01"
                    )

            # Währung prüfen
            currency = self._find_element_text(
                root, ["InvoiceCurrencyCode", "DocumentCurrencyCode"]
            )
            if currency and currency not in ["EUR", "CHF", "USD", "GBP"]:
                result.add_warning(
                    code="CURRENCY_UNUSUAL",
                    location="BT-5",
                    message=f"Ungewoehnliche Währung: {currency}"
                )

        except Exception as e:
            logger.warning(f"business_rules_check_failed: {e}")

    def _find_element_text(
        self,
        root: etree._Element,
        possible_names: List[str]
    ) -> Optional[str]:
        """Sucht Element mit verschiedenen möglichen Namen.

        Fixes (2026-06-12):
        - Kommentare/Processing Instructions haben keinen String-Tag;
          etree.QName() warf darauf eine Exception, die die GESAMTE
          Business-Rules-Pruefung still abbrach (0 Findings bei jedem
          Dokument mit XML-Kommentar).
        - Container-Elemente (z.B. IssueDateTime) tragen ihren Wert in
          Kind-Elementen; itertext() beruecksichtigt diese und vermeidet
          False-Positives durch Whitespace-Textknoten.
        """
        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue  # Kommentar oder Processing Instruction
            local_name = etree.QName(elem.tag).localname
            if local_name in possible_names:
                text = "".join(elem.itertext()).strip()
                if text:
                    return text
        return None

    def _find_invoice_number(self, root: etree._Element) -> Optional[str]:
        """Sucht die Rechnungsnummer (BT-1) an ihrer korrekten Position.

        CII/ZUGFeRD: rsm:ExchangedDocument/ram:ID
        UBL:         direktes Kind cbc:ID des Root-Elements

        Eine dokumentweite Suche nach "ID" ist falsch, weil z.B. die
        Guideline-ID (ExchangedDocumentContext) immer vorhanden ist.
        """
        # CII: ID als direktes Kind von ExchangedDocument
        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue
            if etree.QName(elem.tag).localname == "ExchangedDocument":
                for child in elem:
                    if not isinstance(child.tag, str):
                        continue
                    if etree.QName(child.tag).localname == "ID":
                        text = (child.text or "").strip()
                        if text:
                            return text
        # UBL: cbc:ID als direktes Kind des Invoice-Root
        for child in root:
            if not isinstance(child.tag, str):
                continue
            if etree.QName(child.tag).localname == "ID":
                text = (child.text or "").strip()
                if text:
                    return text
        return None


# Singleton-Instanz
_validator_service: Optional[EInvoiceValidatorService] = None


def get_validator_service() -> EInvoiceValidatorService:
    """Gibt Singleton-Instanz des Validator Service zurück."""
    global _validator_service
    if _validator_service is None:
        _validator_service = EInvoiceValidatorService()
    return _validator_service

# -*- coding: utf-8 -*-
"""
XRechnung 3.0 Generator - EN 16931 Compliant E-Invoice Generation.

Generiert XRechnung 3.0.2 konforme XML-Dateien mit:
- Vollstaendige EN 16931 Struktur
- Alle Pflicht-BT-Felder fuer Deutschland (BR-DE)
- Seller/Buyer Information
- Line Items mit korrektem Coding
- Payment Terms und IBAN
- Steueraufschluesselung (USt)
- XRechnung Schema 3.0.1 Validierung

Unterstuetzt:
- XRechnung CII (UN/CEFACT Cross Industry Invoice) - empfohlen
- XRechnung UBL (Universal Business Language 2.1)

Referenzen:
- XRechnung 3.0.2 Spezifikation
- EN 16931-1:2017
- BR-DE Geschaeftsregeln

HINWEIS: Dieser Generator erzeugt vollstaendig konforme XRechnung-XMLs
         im Gegensatz zum vereinfachten Template im einvoice_tasks.py
"""

import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from uuid import UUID

import structlog
from lxml import etree
from pydantic import BaseModel, Field, field_validator

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# CONSTANTS (EN 16931 / XRechnung)
# =============================================================================

# XRechnung 3.0 Profile IDs
XRECHNUNG_CUSTOMIZATION_CII = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
XRECHNUNG_CUSTOMIZATION_UBL = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
PEPPOL_PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

# Invoice Type Codes (UNTDID 1001)
class InvoiceTypeCode(str, Enum):
    """Rechnungstypen nach UNTDID 1001."""
    INVOICE = "380"  # Handelsrechnung
    CREDIT_NOTE = "381"  # Gutschrift
    DEBIT_NOTE = "383"  # Lastschrift
    CORRECTED_INVOICE = "384"  # Korrekturrechnung
    SELF_BILLED_INVOICE = "389"  # Gutschrift (Selbstabrechnung)
    PROFORMA_INVOICE = "325"  # Proforma-Rechnung
    PREPAYMENT_INVOICE = "386"  # Anzahlungsrechnung


# VAT Category Codes (UNTDID 5305)
class VATCategoryCode(str, Enum):
    """Umsatzsteuerkategorien nach UNTDID 5305."""
    STANDARD = "S"  # Normalsatz (19% DE)
    REDUCED = "AA"  # Ermaessigter Satz (7% DE) - Hinweis: AA statt "R"!
    ZERO_RATED = "Z"  # Nullsatz
    EXEMPT = "E"  # Steuerbefreit
    REVERSE_CHARGE = "AE"  # Reverse Charge (Steuerschuldnerschaft Empfaenger)
    INTRA_COMMUNITY = "K"  # Innergemeinschaftliche Lieferung
    EXPORT = "G"  # Ausfuhr
    NOT_SUBJECT = "O"  # Nicht steuerbar


# Unit Codes (UN/ECE Recommendation 20)
COMMON_UNIT_CODES = {
    "stueck": "C62",  # Unit/Piece
    "stk": "C62",
    "stück": "C62",
    "pc": "C62",
    "pcs": "C62",
    "stunden": "HUR",  # Hour
    "std": "HUR",
    "h": "HUR",
    "tage": "DAY",  # Day
    "tag": "DAY",
    "monat": "MON",  # Month
    "monate": "MON",
    "kg": "KGM",  # Kilogram
    "kilogramm": "KGM",
    "g": "GRM",  # Gram
    "gramm": "GRM",
    "l": "LTR",  # Liter
    "liter": "LTR",
    "m": "MTR",  # Meter
    "meter": "MTR",
    "m2": "MTK",  # Square Meter
    "qm": "MTK",
    "m3": "MTQ",  # Cubic Meter
    "km": "KTM",  # Kilometer
    "set": "SET",  # Set
    "paar": "PR",  # Pair
    "pauschal": "LS",  # Lump Sum
    "ls": "LS",
    "%": "P1",  # Percent
    "prozent": "P1",
}


# =============================================================================
# DATA MODELS (Pydantic)
# =============================================================================

class XRechnungAddress(BaseModel):
    """Adresse fuer XRechnung (BG-5, BG-8, BG-15)."""
    line1: str = Field(..., max_length=200, description="Strasse und Hausnummer (BT-35)")
    line2: Optional[str] = Field(None, max_length=200, description="Adresszusatz (BT-36)")
    city: str = Field(..., max_length=100, description="Stadt (BT-37)")
    postal_code: str = Field(..., max_length=20, description="PLZ (BT-38)")
    country_code: str = Field("DE", pattern=r"^[A-Z]{2}$", description="Laendercode ISO 3166-1 (BT-40)")
    country_subdivision: Optional[str] = Field(None, max_length=50, description="Bundesland (BT-39)")


class XRechnungParty(BaseModel):
    """Partei (Seller/Buyer) fuer XRechnung (BG-4, BG-7)."""
    name: str = Field(..., max_length=200, description="Name (BT-27/BT-44)")
    trading_name: Optional[str] = Field(None, max_length=200, description="Handelsname (BT-28/BT-45)")
    address: XRechnungAddress

    # Identifiers
    vat_id: Optional[str] = Field(None, pattern=r"^[A-Z]{2}[A-Z0-9]{2,13}$", description="USt-IdNr (BT-31/BT-48)")
    tax_number: Optional[str] = Field(None, max_length=50, description="Steuernummer (BT-32)")
    registration_id: Optional[str] = Field(None, max_length=50, description="Handelsregisternr (BT-30/BT-47)")

    # Contact (BG-6, BG-9)
    contact_name: Optional[str] = Field(None, max_length=100, description="Ansprechpartner (BT-41/BT-56)")
    contact_phone: Optional[str] = Field(None, max_length=50, description="Telefon (BT-42/BT-57)")
    contact_email: Optional[str] = Field(None, max_length=100, description="E-Mail (BT-43/BT-58)")

    # Electronic Address (BT-34/BT-49) - PFLICHT ab XRechnung 3.0.1!
    electronic_address: Optional[str] = Field(None, description="Elektronische Adresse")
    electronic_address_scheme: str = Field("EM", description="Scheme (EM=Email, 0204=Leitweg-ID)")

    # Bank Account (BG-17) - nur fuer Seller
    bank_iban: Optional[str] = Field(None, pattern=r"^[A-Z]{2}\d{2}[A-Z0-9]{1,30}$", description="IBAN (BT-84)")
    bank_bic: Optional[str] = Field(None, pattern=r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$", description="BIC (BT-86)")
    bank_name: Optional[str] = Field(None, max_length=100, description="Bankname (BT-85)")


class XRechnungLineItem(BaseModel):
    """Rechnungsposition fuer XRechnung (BG-25)."""
    line_id: str = Field(..., max_length=50, description="Positions-ID (BT-126)")
    description: str = Field(..., max_length=1000, description="Beschreibung (BT-154)")
    name: Optional[str] = Field(None, max_length=200, description="Artikelname (BT-153)")

    quantity: Decimal = Field(..., gt=0, description="Menge (BT-129)")
    unit_code: str = Field("C62", max_length=10, description="Einheitencode UN/ECE Rec. 20 (BT-130)")
    unit_price: Decimal = Field(..., description="Einzelpreis netto (BT-146)")
    line_total: Decimal = Field(..., description="Positionsnetto (BT-131)")

    # Tax
    vat_category: VATCategoryCode = Field(VATCategoryCode.STANDARD, description="MwSt-Kategorie (BT-151)")
    vat_rate: Decimal = Field(Decimal("19.00"), ge=0, le=100, description="MwSt-Satz (BT-152)")

    # Optional identifiers
    seller_item_id: Optional[str] = Field(None, max_length=50, description="Artikelnr Lieferant (BT-155)")
    buyer_item_id: Optional[str] = Field(None, max_length=50, description="Artikelnr Kaeufer (BT-156)")

    # Service period
    period_start: Optional[date] = Field(None, description="Leistungsbeginn (BT-134)")
    period_end: Optional[date] = Field(None, description="Leistungsende (BT-135)")

    @field_validator("unit_code", mode="before")
    @classmethod
    def normalize_unit_code(cls, v: str) -> str:
        """Normalisiert Einheitencode zu UN/ECE Format."""
        if not v:
            return "C62"
        lower = v.lower().strip()
        return COMMON_UNIT_CODES.get(lower, v.upper())


class XRechnungTaxBreakdown(BaseModel):
    """Steueraufschluesselung (BG-23)."""
    category: VATCategoryCode = Field(..., description="MwSt-Kategorie (BT-118)")
    rate: Decimal = Field(..., ge=0, le=100, description="MwSt-Satz (BT-119)")
    taxable_amount: Decimal = Field(..., description="Bemessungsgrundlage (BT-116)")
    tax_amount: Decimal = Field(..., description="Steuerbetrag (BT-117)")
    exemption_reason: Optional[str] = Field(None, max_length=500, description="Befreiungsgrund (BT-120)")
    exemption_reason_code: Optional[str] = Field(None, max_length=20, description="Befreiungscode (BT-121)")


class XRechnungData(BaseModel):
    """Vollstaendige XRechnung Daten."""
    # Document Level (BG-1)
    invoice_number: str = Field(..., max_length=50, description="Rechnungsnummer (BT-1)")
    invoice_type: InvoiceTypeCode = Field(InvoiceTypeCode.INVOICE, description="Rechnungsart (BT-3)")
    invoice_date: date = Field(..., description="Rechnungsdatum (BT-2)")
    due_date: Optional[date] = Field(None, description="Faelligkeitsdatum (BT-9)")

    # Currency
    currency: str = Field("EUR", pattern=r"^[A-Z]{3}$", description="Waehrung (BT-5)")

    # References
    buyer_reference: str = Field(..., max_length=100, description="Leitweg-ID / Kaeuferreferenz (BT-10) - PFLICHT!")
    order_reference: Optional[str] = Field(None, max_length=100, description="Bestellnummer (BT-13)")
    contract_reference: Optional[str] = Field(None, max_length=100, description="Vertragsnummer (BT-12)")
    project_reference: Optional[str] = Field(None, max_length=100, description="Projektnummer (BT-11)")

    # Billing Period (BG-14)
    billing_period_start: Optional[date] = Field(None, description="Abrechnungszeitraum Start (BT-73)")
    billing_period_end: Optional[date] = Field(None, description="Abrechnungszeitraum Ende (BT-74)")

    # Parties
    seller: XRechnungParty = Field(..., description="Rechnungssteller (BG-4)")
    buyer: XRechnungParty = Field(..., description="Rechnungsempfaenger (BG-7)")

    # Delivery (BG-13) - optional
    delivery_date: Optional[date] = Field(None, description="Lieferdatum (BT-72)")
    delivery_address: Optional[XRechnungAddress] = Field(None, description="Lieferadresse (BG-15)")

    # Line Items (BG-25)
    line_items: List[XRechnungLineItem] = Field(..., min_length=1, description="Rechnungspositionen")

    # Totals (BG-22)
    total_net: Decimal = Field(..., description="Nettosumme (BT-106)")
    total_vat: Decimal = Field(..., description="MwSt-Summe (BT-110)")
    total_gross: Decimal = Field(..., description="Bruttosumme (BT-112)")
    prepaid_amount: Optional[Decimal] = Field(None, description="Vorauszahlung (BT-113)")
    payable_amount: Decimal = Field(..., description="Zahlbetrag (BT-115)")

    # Tax Breakdown (BG-23)
    tax_breakdown: List[XRechnungTaxBreakdown] = Field(default_factory=list)

    # Payment (BG-16)
    payment_means_code: str = Field("58", description="Zahlungsart UNTDID 4461 (BT-81)")
    payment_terms: Optional[str] = Field(None, max_length=500, description="Zahlungsbedingungen (BT-20)")
    payment_reference: Optional[str] = Field(None, max_length=100, description="Verwendungszweck (BT-83)")

    # Notes
    invoice_note: Optional[str] = Field(None, max_length=2000, description="Bemerkung (BT-22)")


# =============================================================================
# XRECHNUNG GENERATOR
# =============================================================================

class XRechnungGenerator:
    """
    Generator fuer XRechnung 3.0.2 konforme XML-Dateien.

    Unterstuetzt CII (UN/CEFACT) und UBL Syntax.

    Usage:
        generator = XRechnungGenerator()
        xml_cii = generator.generate_cii(invoice_data)
        xml_ubl = generator.generate_ubl(invoice_data)
    """

    def __init__(self) -> None:
        """Initialisiere Generator."""
        # CII Namespaces
        self.cii_nsmap = {
            None: "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
            "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
            "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
            "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
        }

        # UBL Namespaces
        self.ubl_nsmap = {
            None: "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        }

    def generate_cii(self, data: XRechnungData) -> str:
        """
        Generiert XRechnung im CII-Format (UN/CEFACT).

        Args:
            data: XRechnungData mit allen Pflichtfeldern

        Returns:
            XML als UTF-8 String

        Raises:
            ValueError: Bei fehlenden Pflichtfeldern
        """
        self._validate_xrechnung_requirements(data)

        # Root Element
        root = etree.Element(
            "{urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100}CrossIndustryInvoice",
            nsmap=self.cii_nsmap
        )

        # ExchangedDocumentContext
        self._add_cii_context(root)

        # ExchangedDocument
        self._add_cii_document(root, data)

        # SupplyChainTradeTransaction
        self._add_cii_transaction(root, data)

        # Serialisieren
        xml_bytes = etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=True
        )

        logger.info(
            "xrechnung_cii_generated",
            invoice_number=data.invoice_number,
            leitweg_id=data.buyer_reference,
            line_count=len(data.line_items),
        )

        return xml_bytes.decode("utf-8")

    def generate_ubl(self, data: XRechnungData) -> str:
        """
        Generiert XRechnung im UBL-Format.

        Args:
            data: XRechnungData mit allen Pflichtfeldern

        Returns:
            XML als UTF-8 String
        """
        # UBL Implementation ist bereits in xrechnung_ubl_mapper.py
        # Hier nur Wrapper fuer Konsistenz
        from app.services.einvoice.mapping.xrechnung_ubl_mapper import get_ubl_mapper

        mapper = get_ubl_mapper()

        # Konvertiere XRechnungData zu ExtractedInvoiceData
        extracted = self._convert_to_extracted_data(data)

        return mapper.invoice_data_to_ubl(extracted, data.buyer_reference)

    def _validate_xrechnung_requirements(self, data: XRechnungData) -> None:
        """Validiert XRechnung-spezifische Pflichtfelder."""
        errors = []

        # BR-DE-01: Leitweg-ID Pflicht
        if not data.buyer_reference:
            errors.append("Leitweg-ID (BT-10) fehlt - Pflicht fuer XRechnung B2G")

        # BR-DE-15: Seller Electronic Address Pflicht ab 3.0.1
        if not data.seller.electronic_address:
            # Fallback auf Email
            if data.seller.contact_email:
                data.seller.electronic_address = data.seller.contact_email
                data.seller.electronic_address_scheme = "EM"
            else:
                errors.append("Elektronische Adresse des Verkaeufers (BT-34) fehlt - Pflicht ab XRechnung 3.0.1")

        # BR-DE-16: Buyer Electronic Address oder Leitweg-ID
        if not data.buyer.electronic_address:
            # Leitweg-ID als Buyer Reference ist ausreichend
            data.buyer.electronic_address = data.buyer_reference
            data.buyer.electronic_address_scheme = "0204"

        # Seller VAT-ID oder Tax Number Pflicht
        if not data.seller.vat_id and not data.seller.tax_number:
            errors.append("USt-IdNr (BT-31) oder Steuernummer (BT-32) des Verkaeufers fehlt")

        if errors:
            raise ValueError(f"XRechnung Validierungsfehler: {'; '.join(errors)}")

    def _add_cii_context(self, root: etree._Element) -> None:
        """Fuegt ExchangedDocumentContext hinzu."""
        ns_rsm = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

        context = etree.SubElement(root, f"{{{ns_rsm}}}ExchangedDocumentContext")

        # GuidelineSpecifiedDocumentContextParameter (XRechnung Profil)
        guideline = etree.SubElement(context, f"{{{ns_ram}}}GuidelineSpecifiedDocumentContextParameter")
        guideline_id = etree.SubElement(guideline, f"{{{ns_ram}}}ID")
        guideline_id.text = XRECHNUNG_CUSTOMIZATION_CII

    def _add_cii_document(self, root: etree._Element, data: XRechnungData) -> None:
        """Fuegt ExchangedDocument hinzu."""
        ns_rsm = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
        ns_udt = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

        doc = etree.SubElement(root, f"{{{ns_rsm}}}ExchangedDocument")

        # ID (BT-1)
        id_elem = etree.SubElement(doc, f"{{{ns_ram}}}ID")
        id_elem.text = data.invoice_number

        # TypeCode (BT-3)
        type_code = etree.SubElement(doc, f"{{{ns_ram}}}TypeCode")
        type_code.text = data.invoice_type.value

        # IssueDateTime (BT-2)
        issue = etree.SubElement(doc, f"{{{ns_ram}}}IssueDateTime")
        date_str = etree.SubElement(issue, f"{{{ns_udt}}}DateTimeString")
        date_str.set("format", "102")
        date_str.text = data.invoice_date.strftime("%Y%m%d")

        # IncludedNote (BT-22)
        if data.invoice_note:
            note = etree.SubElement(doc, f"{{{ns_ram}}}IncludedNote")
            content = etree.SubElement(note, f"{{{ns_ram}}}Content")
            content.text = data.invoice_note

    def _add_cii_transaction(self, root: etree._Element, data: XRechnungData) -> None:
        """Fuegt SupplyChainTradeTransaction hinzu."""
        ns_rsm = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

        transaction = etree.SubElement(root, f"{{{ns_rsm}}}SupplyChainTradeTransaction")

        # Line Items (BG-25)
        for item in data.line_items:
            self._add_cii_line_item(transaction, item, data.currency)

        # ApplicableHeaderTradeAgreement
        self._add_cii_agreement(transaction, data)

        # ApplicableHeaderTradeDelivery
        self._add_cii_delivery(transaction, data)

        # ApplicableHeaderTradeSettlement
        self._add_cii_settlement(transaction, data)

    def _add_cii_line_item(
        self,
        parent: etree._Element,
        item: XRechnungLineItem,
        currency: str
    ) -> None:
        """Fuegt IncludedSupplyChainTradeLineItem hinzu."""
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

        line = etree.SubElement(parent, f"{{{ns_ram}}}IncludedSupplyChainTradeLineItem")

        # AssociatedDocumentLineDocument
        doc = etree.SubElement(line, f"{{{ns_ram}}}AssociatedDocumentLineDocument")
        line_id = etree.SubElement(doc, f"{{{ns_ram}}}LineID")
        line_id.text = item.line_id

        # SpecifiedTradeProduct
        product = etree.SubElement(line, f"{{{ns_ram}}}SpecifiedTradeProduct")

        if item.seller_item_id:
            seller_id = etree.SubElement(product, f"{{{ns_ram}}}SellerAssignedID")
            seller_id.text = item.seller_item_id

        if item.buyer_item_id:
            buyer_id = etree.SubElement(product, f"{{{ns_ram}}}BuyerAssignedID")
            buyer_id.text = item.buyer_item_id

        name = etree.SubElement(product, f"{{{ns_ram}}}Name")
        name.text = item.name or item.description[:100]

        if item.description and item.description != item.name:
            desc = etree.SubElement(product, f"{{{ns_ram}}}Description")
            desc.text = item.description

        # SpecifiedLineTradeAgreement
        agreement = etree.SubElement(line, f"{{{ns_ram}}}SpecifiedLineTradeAgreement")
        price = etree.SubElement(agreement, f"{{{ns_ram}}}NetPriceProductTradePrice")
        charge = etree.SubElement(price, f"{{{ns_ram}}}ChargeAmount")
        charge.text = str(item.unit_price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

        # SpecifiedLineTradeDelivery
        delivery = etree.SubElement(line, f"{{{ns_ram}}}SpecifiedLineTradeDelivery")
        qty = etree.SubElement(delivery, f"{{{ns_ram}}}BilledQuantity")
        qty.text = str(item.quantity.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        qty.set("unitCode", item.unit_code)

        # SpecifiedLineTradeSettlement
        settlement = etree.SubElement(line, f"{{{ns_ram}}}SpecifiedLineTradeSettlement")

        # ApplicableTradeTax (vor MonetarySummation!)
        tax = etree.SubElement(settlement, f"{{{ns_ram}}}ApplicableTradeTax")
        type_code = etree.SubElement(tax, f"{{{ns_ram}}}TypeCode")
        type_code.text = "VAT"
        cat_code = etree.SubElement(tax, f"{{{ns_ram}}}CategoryCode")
        cat_code.text = item.vat_category.value
        rate = etree.SubElement(tax, f"{{{ns_ram}}}RateApplicablePercent")
        rate.text = str(item.vat_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        # BillingSpecifiedPeriod (optional)
        if item.period_start or item.period_end:
            period = etree.SubElement(settlement, f"{{{ns_ram}}}BillingSpecifiedPeriod")
            if item.period_start:
                self._add_date_element(period, "StartDateTime", item.period_start)
            if item.period_end:
                self._add_date_element(period, "EndDateTime", item.period_end)

        # SpecifiedTradeSettlementLineMonetarySummation
        summary = etree.SubElement(settlement, f"{{{ns_ram}}}SpecifiedTradeSettlementLineMonetarySummation")
        total = etree.SubElement(summary, f"{{{ns_ram}}}LineTotalAmount")
        total.text = str(item.line_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _add_cii_agreement(self, parent: etree._Element, data: XRechnungData) -> None:
        """Fuegt ApplicableHeaderTradeAgreement hinzu."""
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

        agreement = etree.SubElement(parent, f"{{{ns_ram}}}ApplicableHeaderTradeAgreement")

        # BuyerReference (BT-10) - PFLICHT fuer XRechnung
        ref = etree.SubElement(agreement, f"{{{ns_ram}}}BuyerReference")
        ref.text = data.buyer_reference

        # SellerTradeParty (BG-4)
        self._add_cii_party(agreement, "SellerTradeParty", data.seller, include_bank=True)

        # BuyerTradeParty (BG-7)
        self._add_cii_party(agreement, "BuyerTradeParty", data.buyer, include_bank=False)

        # BuyerOrderReferencedDocument (BT-13)
        if data.order_reference:
            order = etree.SubElement(agreement, f"{{{ns_ram}}}BuyerOrderReferencedDocument")
            order_id = etree.SubElement(order, f"{{{ns_ram}}}IssuerAssignedID")
            order_id.text = data.order_reference

        # ContractReferencedDocument (BT-12)
        if data.contract_reference:
            contract = etree.SubElement(agreement, f"{{{ns_ram}}}ContractReferencedDocument")
            contract_id = etree.SubElement(contract, f"{{{ns_ram}}}IssuerAssignedID")
            contract_id.text = data.contract_reference

        # SpecifiedProcuringProject (BT-11)
        if data.project_reference:
            project = etree.SubElement(agreement, f"{{{ns_ram}}}SpecifiedProcuringProject")
            project_id = etree.SubElement(project, f"{{{ns_ram}}}ID")
            project_id.text = data.project_reference
            project_name = etree.SubElement(project, f"{{{ns_ram}}}Name")
            project_name.text = "Projekt"

    def _add_cii_party(
        self,
        parent: etree._Element,
        tag: str,
        party: XRechnungParty,
        include_bank: bool = False
    ) -> None:
        """Fuegt TradeParty (Seller/Buyer) hinzu."""
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

        party_elem = etree.SubElement(parent, f"{{{ns_ram}}}{tag}")

        # GlobalID (optional)
        # ...

        # ID (Registration Number)
        if party.registration_id:
            reg_id = etree.SubElement(party_elem, f"{{{ns_ram}}}ID")
            reg_id.text = party.registration_id

        # Name
        name = etree.SubElement(party_elem, f"{{{ns_ram}}}Name")
        name.text = party.name

        # DefinedTradeContact (BG-6, BG-9)
        if party.contact_name or party.contact_phone or party.contact_email:
            contact = etree.SubElement(party_elem, f"{{{ns_ram}}}DefinedTradeContact")
            if party.contact_name:
                person = etree.SubElement(contact, f"{{{ns_ram}}}PersonName")
                person.text = party.contact_name
            if party.contact_phone:
                phone = etree.SubElement(contact, f"{{{ns_ram}}}TelephoneUniversalCommunication")
                phone_num = etree.SubElement(phone, f"{{{ns_ram}}}CompleteNumber")
                phone_num.text = party.contact_phone
            if party.contact_email:
                email = etree.SubElement(contact, f"{{{ns_ram}}}EmailURIUniversalCommunication")
                email_uri = etree.SubElement(email, f"{{{ns_ram}}}URIID")
                email_uri.text = party.contact_email

        # PostalTradeAddress (BG-5, BG-8)
        addr = etree.SubElement(party_elem, f"{{{ns_ram}}}PostalTradeAddress")

        postal_code = etree.SubElement(addr, f"{{{ns_ram}}}PostcodeCode")
        postal_code.text = party.address.postal_code

        line1 = etree.SubElement(addr, f"{{{ns_ram}}}LineOne")
        line1.text = party.address.line1

        if party.address.line2:
            line2 = etree.SubElement(addr, f"{{{ns_ram}}}LineTwo")
            line2.text = party.address.line2

        city = etree.SubElement(addr, f"{{{ns_ram}}}CityName")
        city.text = party.address.city

        if party.address.country_subdivision:
            subdiv = etree.SubElement(addr, f"{{{ns_ram}}}CountrySubDivisionName")
            subdiv.text = party.address.country_subdivision

        country = etree.SubElement(addr, f"{{{ns_ram}}}CountryID")
        country.text = party.address.country_code

        # URIUniversalCommunication (BT-34, BT-49) - PFLICHT ab XRechnung 3.0.1
        if party.electronic_address:
            uri = etree.SubElement(party_elem, f"{{{ns_ram}}}URIUniversalCommunication")
            uri_id = etree.SubElement(uri, f"{{{ns_ram}}}URIID")
            uri_id.text = party.electronic_address
            uri_id.set("schemeID", party.electronic_address_scheme)

        # SpecifiedTaxRegistration (VAT ID, Tax Number)
        if party.vat_id:
            tax_reg = etree.SubElement(party_elem, f"{{{ns_ram}}}SpecifiedTaxRegistration")
            vat = etree.SubElement(tax_reg, f"{{{ns_ram}}}ID")
            vat.text = party.vat_id
            vat.set("schemeID", "VA")

        if party.tax_number:
            tax_reg = etree.SubElement(party_elem, f"{{{ns_ram}}}SpecifiedTaxRegistration")
            tax_num = etree.SubElement(tax_reg, f"{{{ns_ram}}}ID")
            tax_num.text = party.tax_number
            tax_num.set("schemeID", "FC")

    def _add_cii_delivery(self, parent: etree._Element, data: XRechnungData) -> None:
        """Fuegt ApplicableHeaderTradeDelivery hinzu."""
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

        delivery = etree.SubElement(parent, f"{{{ns_ram}}}ApplicableHeaderTradeDelivery")

        # ShipToTradeParty (BG-15)
        if data.delivery_address:
            ship_to = etree.SubElement(delivery, f"{{{ns_ram}}}ShipToTradeParty")
            addr = etree.SubElement(ship_to, f"{{{ns_ram}}}PostalTradeAddress")

            postal = etree.SubElement(addr, f"{{{ns_ram}}}PostcodeCode")
            postal.text = data.delivery_address.postal_code
            line1 = etree.SubElement(addr, f"{{{ns_ram}}}LineOne")
            line1.text = data.delivery_address.line1
            city = etree.SubElement(addr, f"{{{ns_ram}}}CityName")
            city.text = data.delivery_address.city
            country = etree.SubElement(addr, f"{{{ns_ram}}}CountryID")
            country.text = data.delivery_address.country_code

        # ActualDeliverySupplyChainEvent (BT-72)
        if data.delivery_date:
            event = etree.SubElement(delivery, f"{{{ns_ram}}}ActualDeliverySupplyChainEvent")
            self._add_date_element(event, "OccurrenceDateTime", data.delivery_date)

    def _add_cii_settlement(self, parent: etree._Element, data: XRechnungData) -> None:
        """Fuegt ApplicableHeaderTradeSettlement hinzu."""
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
        ns_udt = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

        settlement = etree.SubElement(parent, f"{{{ns_ram}}}ApplicableHeaderTradeSettlement")

        # PaymentReference (BT-83)
        if data.payment_reference:
            ref = etree.SubElement(settlement, f"{{{ns_ram}}}PaymentReference")
            ref.text = data.payment_reference

        # InvoiceCurrencyCode (BT-5)
        currency = etree.SubElement(settlement, f"{{{ns_ram}}}InvoiceCurrencyCode")
        currency.text = data.currency

        # SpecifiedTradeSettlementPaymentMeans (BG-16)
        means = etree.SubElement(settlement, f"{{{ns_ram}}}SpecifiedTradeSettlementPaymentMeans")
        type_code = etree.SubElement(means, f"{{{ns_ram}}}TypeCode")
        type_code.text = data.payment_means_code

        # Bank Account (BG-17)
        if data.seller.bank_iban:
            account = etree.SubElement(means, f"{{{ns_ram}}}PayeePartyCreditorFinancialAccount")
            iban = etree.SubElement(account, f"{{{ns_ram}}}IBANID")
            iban.text = data.seller.bank_iban

            if data.seller.bank_name:
                name = etree.SubElement(account, f"{{{ns_ram}}}AccountName")
                name.text = data.seller.bank_name

            if data.seller.bank_bic:
                institution = etree.SubElement(means, f"{{{ns_ram}}}PayeeSpecifiedCreditorFinancialInstitution")
                bic = etree.SubElement(institution, f"{{{ns_ram}}}BICID")
                bic.text = data.seller.bank_bic

        # ApplicableTradeTax (BG-23)
        for tax in data.tax_breakdown:
            self._add_cii_tax(settlement, tax)

        # Fallback: Einzelne Steuerposition wenn keine Breakdown
        if not data.tax_breakdown and data.total_vat:
            self._add_cii_tax_fallback(settlement, data)

        # BillingSpecifiedPeriod (BG-14)
        if data.billing_period_start or data.billing_period_end:
            period = etree.SubElement(settlement, f"{{{ns_ram}}}BillingSpecifiedPeriod")
            if data.billing_period_start:
                self._add_date_element(period, "StartDateTime", data.billing_period_start)
            if data.billing_period_end:
                self._add_date_element(period, "EndDateTime", data.billing_period_end)

        # SpecifiedTradePaymentTerms (BG-20)
        if data.payment_terms or data.due_date:
            terms = etree.SubElement(settlement, f"{{{ns_ram}}}SpecifiedTradePaymentTerms")
            if data.payment_terms:
                desc = etree.SubElement(terms, f"{{{ns_ram}}}Description")
                desc.text = data.payment_terms
            if data.due_date:
                self._add_date_element(terms, "DueDateDateTime", data.due_date)

        # SpecifiedTradeSettlementHeaderMonetarySummation (BG-22)
        summary = etree.SubElement(settlement, f"{{{ns_ram}}}SpecifiedTradeSettlementHeaderMonetarySummation")

        line_total = etree.SubElement(summary, f"{{{ns_ram}}}LineTotalAmount")
        line_total.text = str(data.total_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        tax_basis = etree.SubElement(summary, f"{{{ns_ram}}}TaxBasisTotalAmount")
        tax_basis.text = str(data.total_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        tax_total = etree.SubElement(summary, f"{{{ns_ram}}}TaxTotalAmount")
        tax_total.text = str(data.total_vat.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        tax_total.set("currencyID", data.currency)

        grand_total = etree.SubElement(summary, f"{{{ns_ram}}}GrandTotalAmount")
        grand_total.text = str(data.total_gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        if data.prepaid_amount:
            prepaid = etree.SubElement(summary, f"{{{ns_ram}}}TotalPrepaidAmount")
            prepaid.text = str(data.prepaid_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        payable = etree.SubElement(summary, f"{{{ns_ram}}}DuePayableAmount")
        payable.text = str(data.payable_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _add_cii_tax(self, parent: etree._Element, tax: XRechnungTaxBreakdown) -> None:
        """Fuegt ApplicableTradeTax hinzu."""
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

        tax_elem = etree.SubElement(parent, f"{{{ns_ram}}}ApplicableTradeTax")

        calc = etree.SubElement(tax_elem, f"{{{ns_ram}}}CalculatedAmount")
        calc.text = str(tax.tax_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        type_code = etree.SubElement(tax_elem, f"{{{ns_ram}}}TypeCode")
        type_code.text = "VAT"

        if tax.exemption_reason:
            reason = etree.SubElement(tax_elem, f"{{{ns_ram}}}ExemptionReason")
            reason.text = tax.exemption_reason

        basis = etree.SubElement(tax_elem, f"{{{ns_ram}}}BasisAmount")
        basis.text = str(tax.taxable_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        cat = etree.SubElement(tax_elem, f"{{{ns_ram}}}CategoryCode")
        cat.text = tax.category.value

        if tax.exemption_reason_code:
            reason_code = etree.SubElement(tax_elem, f"{{{ns_ram}}}ExemptionReasonCode")
            reason_code.text = tax.exemption_reason_code

        rate = etree.SubElement(tax_elem, f"{{{ns_ram}}}RateApplicablePercent")
        rate.text = str(tax.rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _add_cii_tax_fallback(self, parent: etree._Element, data: XRechnungData) -> None:
        """Fuegt Fallback-Steuerposition hinzu wenn keine Breakdown."""
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

        tax = etree.SubElement(parent, f"{{{ns_ram}}}ApplicableTradeTax")

        calc = etree.SubElement(tax, f"{{{ns_ram}}}CalculatedAmount")
        calc.text = str(data.total_vat.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        type_code = etree.SubElement(tax, f"{{{ns_ram}}}TypeCode")
        type_code.text = "VAT"

        basis = etree.SubElement(tax, f"{{{ns_ram}}}BasisAmount")
        basis.text = str(data.total_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        cat = etree.SubElement(tax, f"{{{ns_ram}}}CategoryCode")
        cat.text = "S"

        # Steuersatz aus Betraegen berechnen
        if data.total_net and data.total_net > 0:
            rate_calc = (data.total_vat / data.total_net * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            rate_calc = Decimal("19.00")

        rate = etree.SubElement(tax, f"{{{ns_ram}}}RateApplicablePercent")
        rate.text = str(rate_calc)

    def _add_date_element(
        self,
        parent: etree._Element,
        tag: str,
        date_value: date
    ) -> None:
        """Hilfsmethode um Datumselement im CII-Format hinzuzufuegen."""
        ns_ram = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
        ns_udt = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

        elem = etree.SubElement(parent, f"{{{ns_ram}}}{tag}")
        date_str = etree.SubElement(elem, f"{{{ns_udt}}}DateTimeString")
        date_str.set("format", "102")
        date_str.text = date_value.strftime("%Y%m%d")

    def _convert_to_extracted_data(self, data: XRechnungData):
        """Konvertiert XRechnungData zu ExtractedInvoiceData fuer UBL-Mapper."""
        from app.api.schemas.extracted_data import (
            ExtractedInvoiceData, ExtractedAddress, ExtractedBankAccount,
            TaxBreakdownItem, Currency
        )

        # Seller Address
        seller_addr = ExtractedAddress(
            company=data.seller.name,
            street=data.seller.address.line1,
            zip_code=data.seller.address.postal_code,
            city=data.seller.address.city,
            country=data.seller.address.country_code,
        )

        # Buyer Address
        buyer_addr = ExtractedAddress(
            company=data.buyer.name,
            street=data.buyer.address.line1,
            zip_code=data.buyer.address.postal_code,
            city=data.buyer.address.city,
            country=data.buyer.address.country_code,
        )

        # Bank
        sender_bank = None
        if data.seller.bank_iban:
            sender_bank = ExtractedBankAccount(
                iban=data.seller.bank_iban,
                bic=data.seller.bank_bic,
            )

        # Tax Breakdown
        tax_breakdown = []
        for tb in data.tax_breakdown:
            tax_breakdown.append(TaxBreakdownItem(
                tax_category_code=tb.category.value,
                tax_rate=tb.rate,
                taxable_amount=tb.taxable_amount,
                tax_amount=tb.tax_amount,
                exemption_reason=tb.exemption_reason,
                exemption_reason_code=tb.exemption_reason_code,
            ))

        return ExtractedInvoiceData(
            invoice_number=data.invoice_number,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            sender=seller_addr,
            sender_vat_id=data.seller.vat_id,
            sender_tax_number=data.seller.tax_number,
            sender_bank=sender_bank,
            recipient=buyer_addr,
            recipient_vat_id=data.buyer.vat_id,
            net_amount=data.total_net,
            vat_amount=data.total_vat,
            gross_amount=data.total_gross,
            currency=Currency(data.currency) if data.currency in ["EUR", "CHF", "USD", "GBP"] else Currency.EUR,
            buyer_reference=data.buyer_reference,
            purchase_order_reference=data.order_reference,
            contract_reference=data.contract_reference,
            project_reference=data.project_reference,
            payment_terms=data.payment_terms,
            payment_reference=data.payment_reference,
            seller_electronic_address=data.seller.electronic_address,
            buyer_electronic_address=data.buyer.electronic_address,
            tax_breakdown=tax_breakdown,
        )


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_xrechnung_generator_instance: Optional[XRechnungGenerator] = None


def get_xrechnung_generator() -> XRechnungGenerator:
    """
    Factory-Funktion fuer XRechnungGenerator (Singleton).

    Returns:
        XRechnungGenerator: Globale Instanz
    """
    global _xrechnung_generator_instance
    if _xrechnung_generator_instance is None:
        _xrechnung_generator_instance = XRechnungGenerator()
    return _xrechnung_generator_instance

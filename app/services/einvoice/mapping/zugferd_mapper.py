# -*- coding: utf-8 -*-
"""
ZUGFeRD Mapper - Bidirektionale Konvertierung.

Konvertiert zwischen:
- ExtractedInvoiceData (Pydantic) <-> ZUGFeRD XML (factur-x)

Unterstützte Profile:
- MINIMUM, BASIC, BASIC_WL, EN16931, EXTENDED, XRECHNUNG

Referenz: ZUGFeRD 2.3.3 / Factur-X 1.0
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import hashlib

import structlog

from lxml import etree

# R.1 SECURITY FIX: Sicherer XMLParser gegen XXE-Angriffe
# - resolve_entities=False: Externe Entities werden nicht aufgeloest
# - no_network=True: Kein Netzwerkzugriff für DTDs/Schemas
# - load_dtd=False: DTD wird nicht geladen (verhindert Billion Laughs)
SECURE_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    remove_blank_text=True
)

from app.api.schemas.extracted_data import (
    AmountSource,
    Currency,
    ExtractedAddress,
    ExtractedBankAccount,
    ExtractedInvoiceData,
    ExtractedLineItem,
    InvoiceDirection,
    TaxBreakdownItem,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# UN/CEFACT Invoice Type Codes
INVOICE_TYPE_CODES = {
    "380": "Commercial Invoice",
    "381": "Credit Note",
    "384": "Corrected Invoice",
    "389": "Self-billed Invoice",
    "751": "Invoice Information",
}

# Tax Category Codes (UNTDID 5305)
TAX_CATEGORY_CODES = {
    "S": "Standard Rate",
    "Z": "Zero Rated",
    "E": "Exempt",
    "AE": "Reverse Charge",
    "K": "Intra-Community Supply",
    "G": "Export",
    "O": "Not Subject to VAT",
    "L": "Canary Islands",
    "M": "Ceuta/Melilla",
}

# Payment Means Codes (UNTDID 4461)
PAYMENT_MEANS_CODES = {
    "1": "Instrument not defined",
    "10": "In cash",
    "20": "Cheque",
    "30": "Credit transfer",
    "31": "Debit transfer",
    "42": "Payment to bank account",
    "48": "Bank card",
    "49": "Direct debit",
    "57": "Standing agreement",
    "58": "SEPA credit transfer",
    "59": "SEPA direct debit",
}

# ZUGFeRD Profile URNs
PROFILE_URNS = {
    "MINIMUM": "urn:factur-x.eu:1p0:minimum",
    "BASIC": "urn:factur-x.eu:1p0:basicwl",
    "BASIC_WL": "urn:factur-x.eu:1p0:basicwl",
    "EN16931": "urn:cen.eu:en16931:2017",
    "EXTENDED": "urn:factur-x.eu:1p0:extended",
    "XRECHNUNG": "urn:cen.eu:en16931:2017#compliant#urn:xeink:spec:XRechnung:3.0",
}


# =============================================================================
# ZUGFERD MAPPER CLASS
# =============================================================================

class ZUGFeRDMapper:
    """
    Bidirektionaler Mapper zwischen ExtractedInvoiceData und ZUGFeRD XML.

    Verwendung:
        mapper = ZUGFeRDMapper()

        # Parsen (XML -> ExtractedInvoiceData)
        invoice_data, metadata = mapper.xml_to_invoice_data(xml_content)

        # Generieren (ExtractedInvoiceData -> XML)
        xml_content = mapper.invoice_data_to_xml(invoice_data, profile="EN16931")
    """

    def __init__(self) -> None:
        """Initialisiere Mapper mit XML Namespaces."""
        self.namespaces = {
            "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
            "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
            "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
            "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
        }

    # =========================================================================
    # PARSING: XML -> ExtractedInvoiceData
    # =========================================================================

    def xml_to_invoice_data(
        self,
        xml_content: str | bytes
    ) -> Tuple[ExtractedInvoiceData, Dict[str, Any]]:
        """
        Konvertiert ZUGFeRD/Factur-X XML zu ExtractedInvoiceData.

        Args:
            xml_content: XML als String oder Bytes

        Returns:
            Tuple aus:
            - ExtractedInvoiceData: Extrahierte Rechnungsdaten
            - Dict: Metadaten (format, profile, version, xml_hash)

        Raises:
            ValueError: Bei ungültigem XML
        """
        if isinstance(xml_content, str):
            xml_content = xml_content.encode("utf-8")

        try:
            # R.1 SECURITY FIX: Sicherer Parser gegen XXE-Angriffe
            root = etree.fromstring(xml_content, parser=SECURE_XML_PARSER)
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Ungültiges XML: {e}")

        # Metadaten extrahieren
        metadata = self._extract_metadata(root, xml_content)

        # Rechnungsdaten extrahieren
        invoice_data = self._parse_invoice(root)

        # E-Invoice Metadaten setzen
        invoice_data.einvoice_format = "zugferd"
        invoice_data.einvoice_profile = metadata.get("profile")
        invoice_data.einvoice_version = metadata.get("version")
        invoice_data.einvoice_xml_embedded = True

        return invoice_data, metadata

    def _extract_metadata(
        self,
        root: etree._Element,
        xml_content: bytes
    ) -> Dict[str, Any]:
        """Extrahiert Metadaten aus ZUGFeRD XML."""
        metadata: Dict[str, Any] = {
            "format": "zugferd",
            "profile": None,
            "version": None,
            "xml_hash": hashlib.sha256(xml_content).hexdigest(),
        }

        # Profil aus GuidelineSpecifiedDocumentContextParameter
        context_param = root.find(
            ".//rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
            self.namespaces
        )
        if context_param is not None and context_param.text:
            urn = context_param.text
            for profile, profile_urn in PROFILE_URNS.items():
                if profile_urn in urn or profile.lower() in urn.lower():
                    metadata["profile"] = profile
                    break

            # Version extrahieren
            if "xrechnung" in urn.lower():
                metadata["format"] = "xrechnung_cii"
                if "3.0" in urn:
                    metadata["version"] = "3.0.2"
                elif "2.3" in urn:
                    metadata["version"] = "2.3.1"
            else:
                metadata["version"] = "2.3.3"

        return metadata

    def _parse_invoice(self, root: etree._Element) -> ExtractedInvoiceData:
        """Parst ZUGFeRD XML zu ExtractedInvoiceData."""
        ns = self.namespaces

        # Header-Daten
        invoice_number = self._get_text(
            root, ".//rsm:ExchangedDocument/ram:ID"
        )
        invoice_type_code = self._get_text(
            root, ".//rsm:ExchangedDocument/ram:TypeCode"
        )
        invoice_date = self._parse_date(
            root, ".//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString"
        )
        invoice_note = self._get_text(
            root, ".//rsm:ExchangedDocument/ram:IncludedNote/ram:Content"
        )

        # Buyer Reference (Leitweg-ID)
        buyer_reference = self._get_text(
            root, ".//ram:ApplicableHeaderTradeAgreement/ram:BuyerReference"
        )

        # Vertragsreferenz
        contract_reference = self._get_text(
            root, ".//ram:ApplicableHeaderTradeAgreement/ram:ContractReferencedDocument/ram:IssuerAssignedID"
        )

        # Projektreferenz
        project_reference = self._get_text(
            root, ".//ram:ApplicableHeaderTradeAgreement/ram:SpecifiedProcuringProject/ram:ID"
        )

        # Bestellreferenz
        purchase_order_reference = self._get_text(
            root, ".//ram:ApplicableHeaderTradeAgreement/ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID"
        )

        # Seller (Absender)
        seller_party = root.find(
            ".//ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty",
            ns
        )
        sender = self._parse_party(seller_party) if seller_party is not None else None
        sender_vat_id = self._get_text(
            seller_party, ".//ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']"
        ) if seller_party is not None else None
        sender_tax_number = self._get_text(
            seller_party, ".//ram:SpecifiedTaxRegistration/ram:ID[@schemeID='FC']"
        ) if seller_party is not None else None
        seller_electronic_address = self._get_text(
            seller_party, ".//ram:URIUniversalCommunication/ram:URIID"
        ) if seller_party is not None else None

        # Seller Bank
        sender_bank = self._parse_bank_account(root.find(
            ".//ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount",
            ns
        ))

        # Buyer (Empfänger)
        buyer_party = root.find(
            ".//ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty",
            ns
        )
        recipient = self._parse_party(buyer_party) if buyer_party is not None else None
        recipient_vat_id = self._get_text(
            buyer_party, ".//ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']"
        ) if buyer_party is not None else None
        buyer_electronic_address = self._get_text(
            buyer_party, ".//ram:URIUniversalCommunication/ram:URIID"
        ) if buyer_party is not None else None

        # Betraege
        settlement = root.find(
            ".//ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeSettlementHeaderMonetarySummation",
            ns
        )
        net_amount = self._parse_decimal(
            settlement, ".//ram:LineTotalAmount"
        ) if settlement is not None else None
        vat_amount = self._parse_decimal(
            settlement, ".//ram:TaxTotalAmount"
        ) if settlement is not None else None
        gross_amount = self._parse_decimal(
            settlement, ".//ram:GrandTotalAmount"
        ) if settlement is not None else None

        # Währung
        currency_code = self._get_text(
            root, ".//ram:ApplicableHeaderTradeSettlement/ram:InvoiceCurrencyCode"
        )
        currency = Currency.EUR
        if currency_code:
            try:
                currency = Currency(currency_code)
            except ValueError as e:
                logger.debug(
                    "currency_code_parse_failed",
                    error_type=type(e).__name__,
                    currency_code=currency_code,
                )

        # MwSt-Aufschluesselung
        tax_breakdown = self._parse_tax_breakdown(root)

        # Hauptsteuersatz ermitteln
        vat_rate = None
        if tax_breakdown:
            # Hoechsten Betrag als Hauptsatz nehmen
            main_tax = max(tax_breakdown, key=lambda t: t.taxable_amount)
            vat_rate = main_tax.tax_rate

        # Fälligkeitsdatum
        due_date = self._parse_date(
            root, ".//ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString"
        )

        # Zahlungsmittel
        payment_means_code = self._get_text(
            root, ".//ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeSettlementPaymentMeans/ram:TypeCode"
        )
        payment_reference = self._get_text(
            root, ".//ram:ApplicableHeaderTradeSettlement/ram:PaymentReference"
        )

        # Zahlungsbedingungen
        payment_terms = self._get_text(
            root, ".//ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradePaymentTerms/ram:Description"
        )

        # Positionen
        line_items = self._parse_line_items(root)

        # Reverse Charge erkennen
        is_reverse_charge = False
        reverse_charge_note = None
        for tax in tax_breakdown:
            if tax.tax_category_code in ("AE", "K"):
                is_reverse_charge = True
                reverse_charge_note = tax.exemption_reason
                break

        return ExtractedInvoiceData(
            # Referenznummern
            invoice_number=invoice_number,
            order_number=purchase_order_reference,

            # Daten
            invoice_date=invoice_date,
            due_date=due_date,

            # Absender
            sender=sender,
            sender_vat_id=sender_vat_id,
            sender_tax_number=sender_tax_number,
            sender_bank=sender_bank,

            # Empfänger
            recipient=recipient,
            recipient_vat_id=recipient_vat_id,

            # Betraege
            net_amount=net_amount,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            vat_amount_source=AmountSource.DOCUMENT if vat_amount else AmountSource.NOT_FOUND,
            gross_amount=gross_amount,
            gross_amount_source=AmountSource.DOCUMENT if gross_amount else AmountSource.NOT_FOUND,
            currency=currency,

            # Positionen
            line_items=line_items,

            # Zahlungsinformationen
            payment_terms=payment_terms,
            payment_means_code=payment_means_code,
            payment_reference=payment_reference,

            # Reverse Charge
            is_reverse_charge=is_reverse_charge,
            reverse_charge_note=reverse_charge_note,

            # XRechnung-Felder
            buyer_reference=buyer_reference,
            invoice_type_code=invoice_type_code,
            invoice_note=invoice_note,
            contract_reference=contract_reference,
            project_reference=project_reference,
            purchase_order_reference=purchase_order_reference,
            seller_electronic_address=seller_electronic_address,
            buyer_electronic_address=buyer_electronic_address,

            # MwSt-Aufschluesselung
            tax_breakdown=tax_breakdown,

            # Meta
            extraction_confidence=0.95,  # XML ist strukturiert
        )

    def _parse_party(self, party: Optional[etree._Element]) -> Optional[ExtractedAddress]:
        """Parst TradeParty zu ExtractedAddress."""
        if party is None:
            return None

        ns = self.namespaces
        company = self._get_text(party, ".//ram:Name")
        person = self._get_text(party, ".//ram:DefinedTradeContact/ram:PersonName")

        address = party.find(".//ram:PostalTradeAddress", ns)
        if address is None:
            return ExtractedAddress(company=company, person=person)

        return ExtractedAddress(
            company=company,
            person=person,
            street=self._get_text(address, ".//ram:LineOne"),
            zip_code=self._get_text(address, ".//ram:PostcodeCode"),
            city=self._get_text(address, ".//ram:CityName"),
            country=self._get_text(address, ".//ram:CountryID") or "DE",
        )

    def _parse_bank_account(
        self,
        account: Optional[etree._Element]
    ) -> Optional[ExtractedBankAccount]:
        """Parst CreditorFinancialAccount zu ExtractedBankAccount."""
        if account is None:
            return None

        iban = self._get_text(account, ".//ram:IBANID")
        if not iban:
            return None

        return ExtractedBankAccount(
            iban=iban,
            account_holder=self._get_text(account, ".//ram:AccountName"),
        )

    def _parse_tax_breakdown(
        self,
        root: etree._Element
    ) -> List[TaxBreakdownItem]:
        """Parst ApplicableTradeTax zu TaxBreakdownItem Liste."""
        ns = self.namespaces
        items = []

        taxes = root.findall(
            ".//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax",
            ns
        )

        for tax in taxes:
            category_code = self._get_text(tax, ".//ram:CategoryCode") or "S"
            rate = self._parse_decimal(tax, ".//ram:RateApplicablePercent")
            taxable = self._parse_decimal(tax, ".//ram:BasisAmount")
            amount = self._parse_decimal(tax, ".//ram:CalculatedAmount")
            exemption_reason = self._get_text(tax, ".//ram:ExemptionReason")
            exemption_code = self._get_text(tax, ".//ram:ExemptionReasonCode")

            if rate is not None and taxable is not None and amount is not None:
                items.append(TaxBreakdownItem(
                    tax_category_code=category_code,
                    tax_rate=rate,
                    taxable_amount=taxable,
                    tax_amount=amount,
                    exemption_reason=exemption_reason,
                    exemption_reason_code=exemption_code,
                ))

        return items

    def _parse_line_items(self, root: etree._Element) -> List[ExtractedLineItem]:
        """Parst IncludedSupplyChainTradeLineItem zu ExtractedLineItem Liste."""
        ns = self.namespaces
        items = []

        lines = root.findall(
            ".//ram:IncludedSupplyChainTradeLineItem",
            ns
        )

        for i, line in enumerate(lines, 1):
            line_id = self._get_text(
                line, ".//ram:AssociatedDocumentLineDocument/ram:LineID"
            )
            description = self._get_text(
                line, ".//ram:SpecifiedTradeProduct/ram:Name"
            )
            article_number = self._get_text(
                line, ".//ram:SpecifiedTradeProduct/ram:SellerAssignedID"
            )

            quantity = self._parse_decimal(
                line, ".//ram:SpecifiedLineTradeDelivery/ram:BilledQuantity"
            )
            unit = self._get_attr(
                line, ".//ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", "unitCode"
            )
            unit_price = self._parse_decimal(
                line, ".//ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount"
            )
            total_price = self._parse_decimal(
                line, ".//ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount"
            )
            vat_rate = self._parse_decimal(
                line, ".//ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent"
            )

            if description:
                items.append(ExtractedLineItem(
                    position=int(line_id) if line_id and line_id.isdigit() else i,
                    article_number=article_number,
                    description=description,
                    quantity=quantity,
                    unit=unit,
                    unit_price=unit_price,
                    total_price=total_price,
                    vat_rate=vat_rate,
                ))

        return items

    # =========================================================================
    # GENERATION: ExtractedInvoiceData -> XML
    # =========================================================================

    def invoice_data_to_xml(
        self,
        invoice: ExtractedInvoiceData,
        profile: str = "EN16931"
    ) -> str:
        """
        Konvertiert ExtractedInvoiceData zu ZUGFeRD XML.

        Args:
            invoice: Rechnungsdaten
            profile: ZUGFeRD-Profil (MINIMUM, BASIC, EN16931, EXTENDED, XRECHNUNG)

        Returns:
            XML als String (UTF-8)

        Raises:
            ValueError: Bei fehlenden Pflichtfeldern
        """
        # Validierung
        self._validate_for_generation(invoice, profile)

        # XML aufbauen
        root = self._build_xml(invoice, profile)

        # Serialisieren (UTF-8 mit XML Declaration)
        xml_bytes = etree.tostring(
            root,
            encoding="UTF-8",
            pretty_print=True,
            xml_declaration=True
        )
        return xml_bytes.decode("utf-8")

    def _validate_for_generation(
        self,
        invoice: ExtractedInvoiceData,
        profile: str
    ) -> None:
        """Validiert ob alle Pflichtfelder vorhanden sind."""
        errors = []

        if not invoice.invoice_number:
            errors.append("Rechnungsnummer (invoice_number) fehlt")
        if not invoice.invoice_date:
            errors.append("Rechnungsdatum (invoice_date) fehlt")
        if invoice.gross_amount is None:
            errors.append("Bruttobetrag (gross_amount) fehlt")

        if profile == "XRECHNUNG" and not invoice.buyer_reference:
            errors.append("Leitweg-ID (buyer_reference) fehlt - Pflicht für XRechnung")

        if errors:
            raise ValueError(f"Validierungsfehler: {', '.join(errors)}")

    def _build_xml(
        self,
        invoice: ExtractedInvoiceData,
        profile: str
    ) -> etree._Element:
        """Baut ZUGFeRD XML-Struktur auf."""
        nsmap = {
            None: self.namespaces["rsm"],
            "ram": self.namespaces["ram"],
            "qdt": self.namespaces["qdt"],
            "udt": self.namespaces["udt"],
        }

        root = etree.Element(
            "{%s}CrossIndustryInvoice" % self.namespaces["rsm"],
            nsmap=nsmap
        )

        # ExchangedDocumentContext
        self._add_document_context(root, profile)

        # ExchangedDocument
        self._add_exchanged_document(root, invoice)

        # SupplyChainTradeTransaction
        self._add_trade_transaction(root, invoice)

        return root

    def _add_document_context(
        self,
        root: etree._Element,
        profile: str
    ) -> None:
        """Fuegt ExchangedDocumentContext hinzu."""
        rsm = self.namespaces["rsm"]
        ram = self.namespaces["ram"]

        context = etree.SubElement(root, f"{{{rsm}}}ExchangedDocumentContext")
        guideline = etree.SubElement(
            context, f"{{{ram}}}GuidelineSpecifiedDocumentContextParameter"
        )
        id_elem = etree.SubElement(guideline, f"{{{ram}}}ID")
        id_elem.text = PROFILE_URNS.get(profile, PROFILE_URNS["EN16931"])

    def _add_exchanged_document(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData
    ) -> None:
        """Fuegt ExchangedDocument hinzu."""
        rsm = self.namespaces["rsm"]
        ram = self.namespaces["ram"]
        udt = self.namespaces["udt"]

        doc = etree.SubElement(root, f"{{{rsm}}}ExchangedDocument")

        # ID (Rechnungsnummer)
        id_elem = etree.SubElement(doc, f"{{{ram}}}ID")
        id_elem.text = invoice.invoice_number

        # TypeCode
        type_code = etree.SubElement(doc, f"{{{ram}}}TypeCode")
        type_code.text = invoice.invoice_type_code or "380"

        # IssueDateTime
        issue = etree.SubElement(doc, f"{{{ram}}}IssueDateTime")
        date_elem = etree.SubElement(issue, f"{{{udt}}}DateTimeString")
        date_elem.set("format", "102")
        if invoice.invoice_date:
            date_elem.text = invoice.invoice_date.strftime("%Y%m%d")

        # IncludedNote (optional)
        if invoice.invoice_note:
            note = etree.SubElement(doc, f"{{{ram}}}IncludedNote")
            content = etree.SubElement(note, f"{{{ram}}}Content")
            content.text = invoice.invoice_note

    def _add_trade_transaction(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData
    ) -> None:
        """Fuegt SupplyChainTradeTransaction hinzu."""
        rsm = self.namespaces["rsm"]
        ram = self.namespaces["ram"]

        transaction = etree.SubElement(
            root, f"{{{rsm}}}SupplyChainTradeTransaction"
        )

        # Line Items
        for item in invoice.line_items:
            self._add_line_item(transaction, item)

        # ApplicableHeaderTradeAgreement
        self._add_trade_agreement(transaction, invoice)

        # ApplicableHeaderTradeDelivery
        self._add_trade_delivery(transaction, invoice)

        # ApplicableHeaderTradeSettlement
        self._add_trade_settlement(transaction, invoice)

    def _add_line_item(
        self,
        parent: etree._Element,
        item: ExtractedLineItem
    ) -> None:
        """Fuegt IncludedSupplyChainTradeLineItem hinzu."""
        ram = self.namespaces["ram"]

        line = etree.SubElement(parent, f"{{{ram}}}IncludedSupplyChainTradeLineItem")

        # AssociatedDocumentLineDocument
        doc = etree.SubElement(line, f"{{{ram}}}AssociatedDocumentLineDocument")
        line_id = etree.SubElement(doc, f"{{{ram}}}LineID")
        line_id.text = str(item.position)

        # SpecifiedTradeProduct
        product = etree.SubElement(line, f"{{{ram}}}SpecifiedTradeProduct")
        if item.article_number:
            seller_id = etree.SubElement(product, f"{{{ram}}}SellerAssignedID")
            seller_id.text = item.article_number
        name = etree.SubElement(product, f"{{{ram}}}Name")
        name.text = item.description or "Position"

        # Berechne fehlende Werte
        quantity = item.quantity if item.quantity is not None else Decimal("1")
        unit_price = item.unit_price
        total_price = item.total_price

        # Berechne unit_price wenn nicht vorhanden
        if unit_price is None:
            if total_price is not None and quantity:
                unit_price = total_price / quantity
            else:
                unit_price = total_price or Decimal("0")

        # Berechne total_price wenn nicht vorhanden
        if total_price is None:
            total_price = unit_price * quantity if unit_price else Decimal("0")

        # SpecifiedLineTradeAgreement - PFLICHT: NetPriceProductTradePrice
        agreement = etree.SubElement(line, f"{{{ram}}}SpecifiedLineTradeAgreement")
        price = etree.SubElement(agreement, f"{{{ram}}}NetPriceProductTradePrice")
        charge = etree.SubElement(price, f"{{{ram}}}ChargeAmount")
        charge.text = str(unit_price)

        # SpecifiedLineTradeDelivery - PFLICHT: BilledQuantity
        delivery = etree.SubElement(line, f"{{{ram}}}SpecifiedLineTradeDelivery")
        qty = etree.SubElement(delivery, f"{{{ram}}}BilledQuantity")
        qty.text = str(quantity)
        qty.set("unitCode", item.unit or "C62")

        # SpecifiedLineTradeSettlement
        settlement = etree.SubElement(line, f"{{{ram}}}SpecifiedLineTradeSettlement")

        # ApplicableTradeTax ist Pflicht und muss VOR SpecifiedTradeSettlementLineMonetarySummation kommen
        tax = etree.SubElement(settlement, f"{{{ram}}}ApplicableTradeTax")
        type_code = etree.SubElement(tax, f"{{{ram}}}TypeCode")
        type_code.text = "VAT"
        cat_code = etree.SubElement(tax, f"{{{ram}}}CategoryCode")
        cat_code.text = "S"  # Standard rate
        rate = etree.SubElement(tax, f"{{{ram}}}RateApplicablePercent")
        rate.text = str(item.vat_rate if item.vat_rate is not None else Decimal("19.00"))

        # SpecifiedTradeSettlementLineMonetarySummation - PFLICHT: LineTotalAmount
        summary = etree.SubElement(
            settlement, f"{{{ram}}}SpecifiedTradeSettlementLineMonetarySummation"
        )
        total = etree.SubElement(summary, f"{{{ram}}}LineTotalAmount")
        total.text = str(total_price)

    def _add_trade_agreement(
        self,
        parent: etree._Element,
        invoice: ExtractedInvoiceData
    ) -> None:
        """Fuegt ApplicableHeaderTradeAgreement hinzu."""
        ram = self.namespaces["ram"]

        agreement = etree.SubElement(
            parent, f"{{{ram}}}ApplicableHeaderTradeAgreement"
        )

        # BuyerReference (Leitweg-ID)
        if invoice.buyer_reference:
            ref = etree.SubElement(agreement, f"{{{ram}}}BuyerReference")
            ref.text = invoice.buyer_reference

        # SellerTradeParty
        if invoice.sender:
            self._add_trade_party(
                agreement, "SellerTradeParty", invoice.sender,
                invoice.sender_vat_id, invoice.sender_tax_number,
                invoice.seller_electronic_address
            )

        # BuyerTradeParty
        if invoice.recipient:
            self._add_trade_party(
                agreement, "BuyerTradeParty", invoice.recipient,
                invoice.recipient_vat_id, None,
                invoice.buyer_electronic_address
            )

        # ContractReferencedDocument
        if invoice.contract_reference:
            contract = etree.SubElement(
                agreement, f"{{{ram}}}ContractReferencedDocument"
            )
            id_elem = etree.SubElement(contract, f"{{{ram}}}IssuerAssignedID")
            id_elem.text = invoice.contract_reference

        # BuyerOrderReferencedDocument
        if invoice.purchase_order_reference:
            order = etree.SubElement(
                agreement, f"{{{ram}}}BuyerOrderReferencedDocument"
            )
            id_elem = etree.SubElement(order, f"{{{ram}}}IssuerAssignedID")
            id_elem.text = invoice.purchase_order_reference

    def _add_trade_party(
        self,
        parent: etree._Element,
        tag: str,
        address: ExtractedAddress,
        vat_id: Optional[str] = None,
        tax_number: Optional[str] = None,
        electronic_address: Optional[str] = None
    ) -> None:
        """Fuegt TradeParty hinzu."""
        ram = self.namespaces["ram"]

        party = etree.SubElement(parent, f"{{{ram}}}{tag}")

        # Name
        name = etree.SubElement(party, f"{{{ram}}}Name")
        name.text = address.company or address.person or "Unbekannt"

        # PostalTradeAddress
        postal = etree.SubElement(party, f"{{{ram}}}PostalTradeAddress")
        if address.zip_code:
            postcode = etree.SubElement(postal, f"{{{ram}}}PostcodeCode")
            postcode.text = address.zip_code
        if address.street:
            line = etree.SubElement(postal, f"{{{ram}}}LineOne")
            line.text = address.street
        if address.city:
            city = etree.SubElement(postal, f"{{{ram}}}CityName")
            city.text = address.city
        country = etree.SubElement(postal, f"{{{ram}}}CountryID")
        country.text = address.country or "DE"

        # URIUniversalCommunication (Electronic Address)
        if electronic_address:
            uri = etree.SubElement(party, f"{{{ram}}}URIUniversalCommunication")
            uri_id = etree.SubElement(uri, f"{{{ram}}}URIID")
            uri_id.text = electronic_address
            uri_id.set("schemeID", "EM")  # E-Mail

        # SpecifiedTaxRegistration
        if vat_id:
            tax_reg = etree.SubElement(party, f"{{{ram}}}SpecifiedTaxRegistration")
            tax_id = etree.SubElement(tax_reg, f"{{{ram}}}ID")
            tax_id.text = vat_id
            tax_id.set("schemeID", "VA")

        if tax_number:
            tax_reg = etree.SubElement(party, f"{{{ram}}}SpecifiedTaxRegistration")
            tax_id = etree.SubElement(tax_reg, f"{{{ram}}}ID")
            tax_id.text = tax_number
            tax_id.set("schemeID", "FC")

    def _add_trade_delivery(
        self,
        parent: etree._Element,
        invoice: ExtractedInvoiceData
    ) -> None:
        """Fuegt ApplicableHeaderTradeDelivery hinzu."""
        ram = self.namespaces["ram"]

        delivery = etree.SubElement(
            parent, f"{{{ram}}}ApplicableHeaderTradeDelivery"
        )

        # ShipToTradeParty (optional)
        if invoice.delivery_address:
            self._add_trade_party(
                delivery, "ShipToTradeParty", invoice.delivery_address
            )

    def _add_trade_settlement(
        self,
        parent: etree._Element,
        invoice: ExtractedInvoiceData
    ) -> None:
        """Fuegt ApplicableHeaderTradeSettlement hinzu."""
        ram = self.namespaces["ram"]
        udt = self.namespaces["udt"]

        settlement = etree.SubElement(
            parent, f"{{{ram}}}ApplicableHeaderTradeSettlement"
        )

        # PaymentReference
        if invoice.payment_reference:
            ref = etree.SubElement(settlement, f"{{{ram}}}PaymentReference")
            ref.text = invoice.payment_reference

        # InvoiceCurrencyCode
        currency = etree.SubElement(settlement, f"{{{ram}}}InvoiceCurrencyCode")
        currency.text = invoice.currency.value

        # SpecifiedTradeSettlementPaymentMeans
        if invoice.sender_bank or invoice.payment_means_code:
            means = etree.SubElement(
                settlement, f"{{{ram}}}SpecifiedTradeSettlementPaymentMeans"
            )
            type_code = etree.SubElement(means, f"{{{ram}}}TypeCode")
            type_code.text = invoice.payment_means_code or "58"  # SEPA

            if invoice.sender_bank and invoice.sender_bank.iban:
                account = etree.SubElement(
                    means, f"{{{ram}}}PayeePartyCreditorFinancialAccount"
                )
                iban_elem = etree.SubElement(account, f"{{{ram}}}IBANID")
                iban_elem.text = invoice.sender_bank.iban

        # ApplicableTradeTax
        if invoice.tax_breakdown:
            for tax in invoice.tax_breakdown:
                self._add_trade_tax(settlement, tax)
        elif invoice.vat_rate is not None and invoice.net_amount is not None:
            # Fallback: Einzelner Steuersatz
            tax_elem = etree.SubElement(settlement, f"{{{ram}}}ApplicableTradeTax")
            calc = etree.SubElement(tax_elem, f"{{{ram}}}CalculatedAmount")
            calc.text = str(invoice.vat_amount or Decimal("0"))
            type_code = etree.SubElement(tax_elem, f"{{{ram}}}TypeCode")
            type_code.text = "VAT"
            basis = etree.SubElement(tax_elem, f"{{{ram}}}BasisAmount")
            basis.text = str(invoice.net_amount)
            cat = etree.SubElement(tax_elem, f"{{{ram}}}CategoryCode")
            cat.text = "S"
            rate = etree.SubElement(tax_elem, f"{{{ram}}}RateApplicablePercent")
            rate.text = str(invoice.vat_rate)

        # SpecifiedTradePaymentTerms
        if invoice.payment_terms or invoice.due_date:
            terms = etree.SubElement(
                settlement, f"{{{ram}}}SpecifiedTradePaymentTerms"
            )
            if invoice.payment_terms:
                desc = etree.SubElement(terms, f"{{{ram}}}Description")
                desc.text = invoice.payment_terms
            if invoice.due_date:
                due = etree.SubElement(terms, f"{{{ram}}}DueDateDateTime")
                date_elem = etree.SubElement(due, f"{{{udt}}}DateTimeString")
                date_elem.set("format", "102")
                date_elem.text = invoice.due_date.strftime("%Y%m%d")

        # SpecifiedTradeSettlementHeaderMonetarySummation
        summary = etree.SubElement(
            settlement, f"{{{ram}}}SpecifiedTradeSettlementHeaderMonetarySummation"
        )
        if invoice.net_amount is not None:
            line_total = etree.SubElement(summary, f"{{{ram}}}LineTotalAmount")
            line_total.text = str(invoice.net_amount)
            tax_basis = etree.SubElement(summary, f"{{{ram}}}TaxBasisTotalAmount")
            tax_basis.text = str(invoice.net_amount)
        if invoice.vat_amount is not None:
            tax_total = etree.SubElement(summary, f"{{{ram}}}TaxTotalAmount")
            tax_total.text = str(invoice.vat_amount)
            tax_total.set("currencyID", invoice.currency.value)
        if invoice.gross_amount is not None:
            grand_total = etree.SubElement(summary, f"{{{ram}}}GrandTotalAmount")
            grand_total.text = str(invoice.gross_amount)
            due_payable = etree.SubElement(summary, f"{{{ram}}}DuePayableAmount")
            due_payable.text = str(invoice.gross_amount)

    def _add_trade_tax(
        self,
        parent: etree._Element,
        tax: TaxBreakdownItem
    ) -> None:
        """Fuegt ApplicableTradeTax hinzu."""
        ram = self.namespaces["ram"]

        tax_elem = etree.SubElement(parent, f"{{{ram}}}ApplicableTradeTax")

        calc = etree.SubElement(tax_elem, f"{{{ram}}}CalculatedAmount")
        calc.text = str(tax.tax_amount)

        type_code = etree.SubElement(tax_elem, f"{{{ram}}}TypeCode")
        type_code.text = "VAT"

        if tax.exemption_reason:
            reason = etree.SubElement(tax_elem, f"{{{ram}}}ExemptionReason")
            reason.text = tax.exemption_reason

        basis = etree.SubElement(tax_elem, f"{{{ram}}}BasisAmount")
        basis.text = str(tax.taxable_amount)

        cat = etree.SubElement(tax_elem, f"{{{ram}}}CategoryCode")
        cat.text = tax.tax_category_code

        if tax.exemption_reason_code:
            reason_code = etree.SubElement(tax_elem, f"{{{ram}}}ExemptionReasonCode")
            reason_code.text = tax.exemption_reason_code

        rate = etree.SubElement(tax_elem, f"{{{ram}}}RateApplicablePercent")
        rate.text = str(tax.tax_rate)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_text(
        self,
        element: Optional[etree._Element],
        xpath: str
    ) -> Optional[str]:
        """Extrahiert Text aus XPath."""
        if element is None:
            return None
        found = element.find(xpath, self.namespaces)
        if found is not None and found.text:
            return found.text.strip()
        return None

    def _get_attr(
        self,
        element: Optional[etree._Element],
        xpath: str,
        attr: str
    ) -> Optional[str]:
        """Extrahiert Attribut aus XPath."""
        if element is None:
            return None
        found = element.find(xpath, self.namespaces)
        if found is not None:
            return found.get(attr)
        return None

    def _parse_date(
        self,
        element: Optional[etree._Element],
        xpath: str
    ) -> Optional[date]:
        """Parst Datum aus XPath (Format 102: YYYYMMDD)."""
        text = self._get_text(element, xpath)
        if not text:
            return None
        try:
            if len(text) == 8:
                return datetime.strptime(text, "%Y%m%d").date()
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None

    def _parse_decimal(
        self,
        element: Optional[etree._Element],
        xpath: str
    ) -> Optional[Decimal]:
        """Parst Dezimalzahl aus XPath."""
        text = self._get_text(element, xpath)
        if not text:
            return None
        try:
            return Decimal(text.replace(",", "."))
        except (ValueError, ArithmeticError):
            return None


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_zugferd_mapper_instance: Optional[ZUGFeRDMapper] = None


def get_zugferd_mapper() -> ZUGFeRDMapper:
    """
    Factory-Funktion für ZUGFeRDMapper (Singleton).

    Returns:
        ZUGFeRDMapper: Globale Mapper-Instanz
    """
    global _zugferd_mapper_instance
    if _zugferd_mapper_instance is None:
        _zugferd_mapper_instance = ZUGFeRDMapper()
    return _zugferd_mapper_instance

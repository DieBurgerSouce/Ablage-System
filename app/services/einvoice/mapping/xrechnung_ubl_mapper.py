# -*- coding: utf-8 -*-
"""
XRechnung UBL Mapper.

Konvertiert ExtractedInvoiceData zu XRechnung 3.0.2 im UBL 2.1 Format.
UBL (Universal Business Language) ist neben CII eines der beiden
unterstützten Formate für XRechnung.

Unterschiede zu CII:
- Andere XML-Struktur und Namespaces
- Andere Element-Namen (z.B. cac:AccountingSupplierParty statt ram:SellerTradeParty)
- Wird von manchen Empfängern bevorzugt

Standards:
- UBL 2.1: ISO 19845
- XRechnung 3.0.2: EN 16931 Profil für DE
- BR-DE: Deutsche Business Rules
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from lxml import etree

from app.api.schemas.extracted_data import ExtractedInvoiceData, TaxBreakdownItem

logger = logging.getLogger(__name__)

# UBL 2.1 Namespaces
UBL_NAMESPACES = {
    "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ccts": "urn:un:unece:uncefact:documentation:2",
    "qdt": "urn:oasis:names:specification:ubl:schema:xsd:QualifiedDatatypes-2",
    "udt": "urn:oasis:names:specification:ubl:schema:xsd:UnqualifiedDatatypes-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
}

# XRechnung Profile ID
XRECHNUNG_PROFILE_ID = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"

# Invoice Type Codes (UNTDID 1001)
INVOICE_TYPE_CODES = {
    "commercial_invoice": "380",
    "credit_note": "381",
    "debit_note": "383",
    "corrective_invoice": "384",
    "self_billed_invoice": "389",
    "proforma_invoice": "325",
}

# Payment Means Codes (UNTDID 4461)
PAYMENT_MEANS_CODES = {
    "sepa_credit_transfer": "30",
    "sepa_direct_debit": "59",
    "credit_card": "54",
    "bank_transfer": "42",
    "cash": "10",
    "cheque": "20",
}


class XRechnungUBLMapper:
    """
    Mapper für XRechnung 3.0.2 im UBL 2.1 Format.

    Konvertiert ExtractedInvoiceData zu konformem UBL-XML.

    Usage:
        mapper = XRechnungUBLMapper()
        xml_str = mapper.invoice_data_to_ubl(invoice_data, leitweg_id="04011000-12345-67")
    """

    def __init__(self):
        """Initialisiert den UBL Mapper."""
        self.nsmap = {
            None: UBL_NAMESPACES["ubl"],  # Default namespace
            "cac": UBL_NAMESPACES["cac"],
            "cbc": UBL_NAMESPACES["cbc"],
        }

    def invoice_data_to_ubl(
        self,
        invoice: ExtractedInvoiceData,
        leitweg_id: str,
        invoice_type: str = "commercial_invoice",
    ) -> str:
        """
        Konvertiert ExtractedInvoiceData zu XRechnung UBL XML.

        Args:
            invoice: Extrahierte Rechnungsdaten
            leitweg_id: Leitweg-ID (BT-10) - PFLICHT für XRechnung
            invoice_type: Rechnungstyp (commercial_invoice, credit_note, etc.)

        Returns:
            UBL XML als String

        Raises:
            ValueError: Bei fehlenden Pflichtfeldern
        """
        if not leitweg_id:
            raise ValueError("Leitweg-ID (BT-10) ist Pflichtfeld für XRechnung")

        # Root Element
        root = etree.Element(
            "{%s}Invoice" % UBL_NAMESPACES["ubl"],
            nsmap=self.nsmap
        )

        # CustomizationID und ProfileID (XRechnung)
        self._add_element(root, "cbc:CustomizationID",
                         "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0")
        self._add_element(root, "cbc:ProfileID",
                         "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")

        # Rechnungsnummer (BT-1)
        invoice_id = invoice.invoice_number or str(uuid4())[:8]
        self._add_element(root, "cbc:ID", invoice_id)

        # Rechnungsdatum (BT-2)
        issue_date = invoice.invoice_date or date.today()
        if isinstance(issue_date, datetime):
            issue_date = issue_date.date()
        self._add_element(root, "cbc:IssueDate", issue_date.isoformat())

        # Fälligkeitsdatum (BT-9)
        if invoice.payment_due_date:
            due_date = invoice.payment_due_date
            if isinstance(due_date, datetime):
                due_date = due_date.date()
            self._add_element(root, "cbc:DueDate", due_date.isoformat())

        # Invoice Type Code (BT-3)
        type_code = INVOICE_TYPE_CODES.get(invoice_type, "380")
        self._add_element(root, "cbc:InvoiceTypeCode", type_code)

        # Währung (BT-5)
        currency = invoice.currency or "EUR"
        self._add_element(root, "cbc:DocumentCurrencyCode", currency)

        # Buyer Reference / Leitweg-ID (BT-10)
        self._add_element(root, "cbc:BuyerReference", leitweg_id)

        # Rechnungsperiode (BG-14) - optional
        if invoice.service_date_start or invoice.service_date_end:
            period = self._add_element(root, "cac:InvoicePeriod")
            if invoice.service_date_start:
                start = invoice.service_date_start
                if isinstance(start, datetime):
                    start = start.date()
                self._add_element(period, "cbc:StartDate", start.isoformat())
            if invoice.service_date_end:
                end = invoice.service_date_end
                if isinstance(end, datetime):
                    end = end.date()
                self._add_element(period, "cbc:EndDate", end.isoformat())

        # Order Reference (BT-13)
        if invoice.purchase_order_number:
            order_ref = self._add_element(root, "cac:OrderReference")
            self._add_element(order_ref, "cbc:ID", invoice.purchase_order_number)

        # Supplier / Seller (BG-4)
        self._add_supplier_party(root, invoice)

        # Customer / Buyer (BG-7)
        self._add_customer_party(root, invoice, leitweg_id)

        # Payment Means (BG-16)
        self._add_payment_means(root, invoice)

        # Payment Terms (BT-20)
        if invoice.payment_terms:
            terms = self._add_element(root, "cac:PaymentTerms")
            self._add_element(terms, "cbc:Note", invoice.payment_terms)

        # Tax Total (BG-22)
        self._add_tax_total(root, invoice, currency)

        # Document Totals (BG-22)
        self._add_monetary_total(root, invoice, currency)

        # Invoice Lines (BG-25)
        self._add_invoice_lines(root, invoice, currency)

        # XML String generieren
        xml_str = etree.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8"
        ).decode("utf-8")

        logger.info(
            "xrechnung_ubl_generated",
            extra={
                "invoice_id": invoice_id,
                "leitweg_id": leitweg_id,
                "line_count": len(invoice.line_items) if invoice.line_items else 0,
            }
        )

        return xml_str

    def _add_element(
        self,
        parent: etree._Element,
        tag: str,
        text: Optional[str] = None,
        **attributes
    ) -> etree._Element:
        """Hilfsmethode um Element mit Namespace hinzuzufuegen."""
        # Parse tag with namespace prefix
        if ":" in tag:
            prefix, local_name = tag.split(":", 1)
            ns = UBL_NAMESPACES.get(prefix, "")
            element = etree.SubElement(parent, "{%s}%s" % (ns, local_name))
        else:
            element = etree.SubElement(parent, tag)

        if text is not None:
            element.text = str(text)

        for attr_name, attr_value in attributes.items():
            element.set(attr_name, str(attr_value))

        return element

    def _add_supplier_party(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData
    ) -> None:
        """Fuegt Supplier/Seller Party (BG-4) hinzu."""
        supplier = self._add_element(root, "cac:AccountingSupplierParty")
        party = self._add_element(supplier, "cac:Party")

        # Endpoint ID (BT-34) - Elektronische Adresse
        if invoice.seller_electronic_address:
            endpoint = self._add_element(
                party, "cbc:EndpointID",
                invoice.seller_electronic_address,
                schemeID="EM"  # E-Mail als Default
            )

        # Party Name (BT-27)
        if invoice.sender:
            party_name = self._add_element(party, "cac:PartyName")
            self._add_element(party_name, "cbc:Name", invoice.sender)

        # Postal Address (BG-5)
        postal = self._add_element(party, "cac:PostalAddress")

        if invoice.sender_address:
            self._add_element(postal, "cbc:StreetName", invoice.sender_address)
        if invoice.sender_city:
            self._add_element(postal, "cbc:CityName", invoice.sender_city)
        if invoice.sender_postal_code:
            self._add_element(postal, "cbc:PostalZone", invoice.sender_postal_code)

        # Country (BT-40)
        country = self._add_element(postal, "cac:Country")
        country_code = invoice.sender_country or "DE"
        self._add_element(country, "cbc:IdentificationCode", country_code)

        # Tax Scheme (VAT ID)
        if invoice.sender_vat_id:
            tax_scheme = self._add_element(party, "cac:PartyTaxScheme")
            self._add_element(tax_scheme, "cbc:CompanyID", invoice.sender_vat_id)
            scheme = self._add_element(tax_scheme, "cac:TaxScheme")
            self._add_element(scheme, "cbc:ID", "VAT")

        # Legal Entity (BG-6)
        legal = self._add_element(party, "cac:PartyLegalEntity")
        self._add_element(legal, "cbc:RegistrationName", invoice.sender or "Unbekannt")

        # Contact (BG-6 optional)
        if invoice.sender_email or invoice.sender_phone:
            contact = self._add_element(party, "cac:Contact")
            if invoice.sender_phone:
                self._add_element(contact, "cbc:Telephone", invoice.sender_phone)
            if invoice.sender_email:
                self._add_element(contact, "cbc:ElectronicMail", invoice.sender_email)

    def _add_customer_party(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData,
        leitweg_id: str
    ) -> None:
        """Fuegt Customer/Buyer Party (BG-7) hinzu."""
        customer = self._add_element(root, "cac:AccountingCustomerParty")
        party = self._add_element(customer, "cac:Party")

        # Endpoint ID (BT-49) - Elektronische Adresse
        if invoice.buyer_electronic_address:
            self._add_element(
                party, "cbc:EndpointID",
                invoice.buyer_electronic_address,
                schemeID="EM"
            )

        # Party Identification mit Leitweg-ID
        party_id = self._add_element(party, "cac:PartyIdentification")
        self._add_element(party_id, "cbc:ID", leitweg_id, schemeID="0204")

        # Party Name (BT-44)
        if invoice.recipient:
            party_name = self._add_element(party, "cac:PartyName")
            self._add_element(party_name, "cbc:Name", invoice.recipient)

        # Postal Address (BG-8)
        postal = self._add_element(party, "cac:PostalAddress")

        if invoice.recipient_address:
            self._add_element(postal, "cbc:StreetName", invoice.recipient_address)
        if invoice.recipient_city:
            self._add_element(postal, "cbc:CityName", invoice.recipient_city)
        if invoice.recipient_postal_code:
            self._add_element(postal, "cbc:PostalZone", invoice.recipient_postal_code)

        # Country (BT-55)
        country = self._add_element(postal, "cac:Country")
        country_code = invoice.recipient_country or "DE"
        self._add_element(country, "cbc:IdentificationCode", country_code)

        # Tax Scheme (VAT ID)
        if invoice.recipient_vat_id:
            tax_scheme = self._add_element(party, "cac:PartyTaxScheme")
            self._add_element(tax_scheme, "cbc:CompanyID", invoice.recipient_vat_id)
            scheme = self._add_element(tax_scheme, "cac:TaxScheme")
            self._add_element(scheme, "cbc:ID", "VAT")

        # Legal Entity (BG-9)
        legal = self._add_element(party, "cac:PartyLegalEntity")
        self._add_element(legal, "cbc:RegistrationName", invoice.recipient or "Unbekannt")

    def _add_payment_means(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData
    ) -> None:
        """Fuegt Payment Means (BG-16) hinzu."""
        payment = self._add_element(root, "cac:PaymentMeans")

        # Payment Means Code (BT-81)
        code = "30"  # SEPA Credit Transfer als Default
        if invoice.sender_bank_iban:
            code = "30"  # Bank Transfer
        self._add_element(payment, "cbc:PaymentMeansCode", code)

        # Payment ID / Reference (BT-83)
        if invoice.payment_reference:
            self._add_element(payment, "cbc:PaymentID", invoice.payment_reference)

        # Payee Bank Account (BG-17)
        if invoice.sender_bank_iban:
            payee_account = self._add_element(payment, "cac:PayeeFinancialAccount")
            self._add_element(payee_account, "cbc:ID", invoice.sender_bank_iban)

            if invoice.sender_bank_name:
                self._add_element(payee_account, "cbc:Name", invoice.sender_bank_name)

            if invoice.sender_bank_bic:
                branch = self._add_element(payee_account, "cac:FinancialInstitutionBranch")
                self._add_element(branch, "cbc:ID", invoice.sender_bank_bic)

    def _add_tax_total(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData,
        currency: str
    ) -> None:
        """Fuegt Tax Total (BG-22) hinzu."""
        tax_total = self._add_element(root, "cac:TaxTotal")

        # Total Tax Amount (BT-110)
        vat_amount = invoice.vat_amount or Decimal("0.00")
        self._add_element(
            tax_total, "cbc:TaxAmount",
            f"{vat_amount:.2f}",
            currencyID=currency
        )

        # Tax Subtotals (BG-23)
        if invoice.tax_breakdown:
            for tax_item in invoice.tax_breakdown:
                self._add_tax_subtotal(tax_total, tax_item, currency)
        else:
            # Fallback: Einzelne Steuerposition
            subtotal = self._add_element(tax_total, "cac:TaxSubtotal")

            # Taxable Amount
            net = invoice.net_amount or Decimal("0.00")
            self._add_element(
                subtotal, "cbc:TaxableAmount",
                f"{net:.2f}",
                currencyID=currency
            )

            # Tax Amount
            self._add_element(
                subtotal, "cbc:TaxAmount",
                f"{vat_amount:.2f}",
                currencyID=currency
            )

            # Tax Category
            category = self._add_element(subtotal, "cac:TaxCategory")
            self._add_element(category, "cbc:ID", "S")  # Standard rate

            # Tax Rate
            rate = invoice.vat_rate or Decimal("19.00")
            self._add_element(category, "cbc:Percent", f"{rate:.2f}")

            # Tax Scheme
            scheme = self._add_element(category, "cac:TaxScheme")
            self._add_element(scheme, "cbc:ID", "VAT")

    def _add_tax_subtotal(
        self,
        parent: etree._Element,
        tax_item: TaxBreakdownItem,
        currency: str
    ) -> None:
        """Fuegt einzelne Tax Subtotal hinzu."""
        subtotal = self._add_element(parent, "cac:TaxSubtotal")

        self._add_element(
            subtotal, "cbc:TaxableAmount",
            f"{tax_item.taxable_amount:.2f}",
            currencyID=currency
        )

        self._add_element(
            subtotal, "cbc:TaxAmount",
            f"{tax_item.tax_amount:.2f}",
            currencyID=currency
        )

        category = self._add_element(subtotal, "cac:TaxCategory")
        self._add_element(category, "cbc:ID", tax_item.tax_category_code or "S")
        self._add_element(category, "cbc:Percent", f"{tax_item.tax_rate:.2f}")

        if tax_item.exemption_reason:
            self._add_element(category, "cbc:TaxExemptionReason", tax_item.exemption_reason)
        if tax_item.exemption_reason_code:
            self._add_element(category, "cbc:TaxExemptionReasonCode", tax_item.exemption_reason_code)

        scheme = self._add_element(category, "cac:TaxScheme")
        self._add_element(scheme, "cbc:ID", "VAT")

    def _add_monetary_total(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData,
        currency: str
    ) -> None:
        """Fuegt LegalMonetaryTotal (BG-22) hinzu."""
        total = self._add_element(root, "cac:LegalMonetaryTotal")

        net = invoice.net_amount or Decimal("0.00")
        gross = invoice.gross_amount or net + (invoice.vat_amount or Decimal("0.00"))

        # Line Extension Amount (BT-106)
        self._add_element(
            total, "cbc:LineExtensionAmount",
            f"{net:.2f}",
            currencyID=currency
        )

        # Tax Exclusive Amount (BT-109)
        self._add_element(
            total, "cbc:TaxExclusiveAmount",
            f"{net:.2f}",
            currencyID=currency
        )

        # Tax Inclusive Amount (BT-112)
        self._add_element(
            total, "cbc:TaxInclusiveAmount",
            f"{gross:.2f}",
            currencyID=currency
        )

        # Payable Amount (BT-115)
        payable = invoice.amount_due or gross
        self._add_element(
            total, "cbc:PayableAmount",
            f"{payable:.2f}",
            currencyID=currency
        )

    def _add_invoice_lines(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData,
        currency: str
    ) -> None:
        """Fuegt Invoice Lines (BG-25) hinzu."""
        if not invoice.line_items:
            # Mindestens eine Zeile erforderlich
            self._add_single_line(root, invoice, currency)
            return

        for idx, item in enumerate(invoice.line_items, start=1):
            line = self._add_element(root, "cac:InvoiceLine")

            # Line ID (BT-126)
            self._add_element(line, "cbc:ID", str(idx))

            # Quantity (BT-129)
            quantity = item.get("quantity", 1)
            unit_code = item.get("unit_code", "C62")  # C62 = unit/piece
            self._add_element(
                line, "cbc:InvoicedQuantity",
                str(quantity),
                unitCode=unit_code
            )

            # Line Extension Amount (BT-131)
            line_total = item.get("total_price", Decimal("0.00"))
            self._add_element(
                line, "cbc:LineExtensionAmount",
                f"{Decimal(str(line_total)):.2f}",
                currencyID=currency
            )

            # Item (BG-31)
            item_elem = self._add_element(line, "cac:Item")

            # Description (BT-154)
            description = item.get("description", "Artikel")
            self._add_element(item_elem, "cbc:Description", description)

            # Name (BT-153)
            name = item.get("name", description[:100] if description else "Artikel")
            self._add_element(item_elem, "cbc:Name", name)

            # Tax Category
            tax_cat = self._add_element(item_elem, "cac:ClassifiedTaxCategory")
            self._add_element(tax_cat, "cbc:ID", item.get("tax_category", "S"))
            self._add_element(tax_cat, "cbc:Percent",
                            f"{Decimal(str(item.get('tax_rate', 19))):.2f}")
            scheme = self._add_element(tax_cat, "cac:TaxScheme")
            self._add_element(scheme, "cbc:ID", "VAT")

            # Price (BG-29)
            price_elem = self._add_element(line, "cac:Price")
            unit_price = item.get("unit_price", Decimal("0.00"))
            self._add_element(
                price_elem, "cbc:PriceAmount",
                f"{Decimal(str(unit_price)):.2f}",
                currencyID=currency
            )

    def _add_single_line(
        self,
        root: etree._Element,
        invoice: ExtractedInvoiceData,
        currency: str
    ) -> None:
        """Fuegt eine einzelne Rechnungszeile hinzu (Fallback)."""
        line = self._add_element(root, "cac:InvoiceLine")

        # Line ID
        self._add_element(line, "cbc:ID", "1")

        # Quantity
        self._add_element(line, "cbc:InvoicedQuantity", "1", unitCode="C62")

        # Line Amount
        net = invoice.net_amount or Decimal("0.00")
        self._add_element(
            line, "cbc:LineExtensionAmount",
            f"{net:.2f}",
            currencyID=currency
        )

        # Item
        item = self._add_element(line, "cac:Item")
        subject = invoice.subject or "Rechnungsposition"
        self._add_element(item, "cbc:Description", subject)
        self._add_element(item, "cbc:Name", subject[:100])

        # Tax Category
        tax_cat = self._add_element(item, "cac:ClassifiedTaxCategory")
        self._add_element(tax_cat, "cbc:ID", "S")
        rate = invoice.vat_rate or Decimal("19.00")
        self._add_element(tax_cat, "cbc:Percent", f"{rate:.2f}")
        scheme = self._add_element(tax_cat, "cac:TaxScheme")
        self._add_element(scheme, "cbc:ID", "VAT")

        # Price
        price = self._add_element(line, "cac:Price")
        self._add_element(
            price, "cbc:PriceAmount",
            f"{net:.2f}",
            currencyID=currency
        )


# Singleton-Instanz
_ubl_mapper: Optional[XRechnungUBLMapper] = None


def get_ubl_mapper() -> XRechnungUBLMapper:
    """Gibt Singleton-Instanz des UBL Mappers zurück."""
    global _ubl_mapper
    if _ubl_mapper is None:
        _ubl_mapper = XRechnungUBLMapper()
    return _ubl_mapper

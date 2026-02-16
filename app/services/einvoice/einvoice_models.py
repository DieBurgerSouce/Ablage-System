"""
E-Invoice Schemas

Pydantic models for electronic invoice data representation.
Supports UBL 2.1, ZUGFeRD 2.1, and XRechnung formats.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class EInvoiceFormat(str, Enum):
    """Supported e-invoice formats."""
    UBL_21 = "ubl_2.1"  # Universal Business Language 2.1
    ZUGFERD_21 = "zugferd_2.1"  # ZUGFeRD 2.1 (German standard)
    XRECHNUNG_30 = "xrechnung_3.0"  # XRechnung 3.0 (German B2G)
    CII_D16B = "cii_d16b"  # Cross Industry Invoice


class InvoiceType(str, Enum):
    """Invoice type codes per EN 16931."""
    INVOICE = "380"  # Commercial invoice
    CREDIT_NOTE = "381"  # Credit note
    CORRECTED_INVOICE = "384"  # Corrected invoice
    SELF_BILLED_INVOICE = "389"  # Self-billed invoice
    PREPAYMENT_INVOICE = "386"  # Prepayment invoice


class TaxCategory(str, Enum):
    """VAT category codes."""
    STANDARD = "S"  # Standard rate (19% in Germany)
    REDUCED = "AA"  # Reduced rate (7% in Germany)
    ZERO_RATED = "Z"  # Zero rated
    EXEMPT = "E"  # Exempt from VAT
    REVERSE_CHARGE = "AE"  # Reverse charge
    INTRA_COMMUNITY = "K"  # Intra-community supply


class PaymentMeansCode(str, Enum):
    """Payment means codes per UN/EDIFACT 4461."""
    CASH = "10"
    CHEQUE = "20"
    CREDIT_TRANSFER = "30"  # Überweisung
    DEBIT_TRANSFER = "31"
    CARD_PAYMENT = "48"
    DIRECT_DEBIT = "49"  # Lastschrift
    STANDING_ORDER = "57"
    SEPA_CREDIT_TRANSFER = "58"
    SEPA_DIRECT_DEBIT = "59"


class Address(BaseModel):
    """Postal address for invoice parties."""
    street_name: str = Field(..., max_length=200, description="Strassenname")
    building_number: Optional[str] = Field(None, max_length=20, description="Hausnummer")
    additional_street: Optional[str] = Field(None, max_length=200, description="Adresszusatz")
    city: str = Field(..., max_length=100, description="Stadt")
    postal_code: str = Field(..., max_length=20, description="PLZ")
    country_code: str = Field("DE", pattern="^[A-Z]{2}$", description="ISO 3166-1 Alpha-2")
    country_subdivision: Optional[str] = Field(None, max_length=50, description="Bundesland")


class InvoiceParty(BaseModel):
    """Invoice party (seller or buyer) information."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., max_length=200, description="Firmenname")
    trading_name: Optional[str] = Field(None, max_length=200, description="Handelsname")

    # Address
    address: Address

    # Identifiers
    vat_id: Optional[str] = Field(None, pattern=r"^[A-Z]{2}[A-Z0-9]{2,13}$", description="USt-IdNr")
    tax_number: Optional[str] = Field(None, max_length=50, description="Steuernummer")
    registration_number: Optional[str] = Field(None, max_length=50, description="Handelsregisternummer")
    gln: Optional[str] = Field(None, pattern=r"^\d{13}$", description="GLN (Global Location Number)")
    lei: Optional[str] = Field(None, pattern=r"^[A-Z0-9]{20}$", description="LEI (Legal Entity Identifier)")

    # Contact
    contact_name: Optional[str] = Field(None, max_length=100, description="Ansprechpartner")
    phone: Optional[str] = Field(None, max_length=50, description="Telefon")
    email: Optional[str] = Field(None, max_length=100, description="E-Mail")

    # Bank details (for seller)
    bank_account_iban: Optional[str] = Field(None, pattern=r"^[A-Z]{2}\d{2}[A-Z0-9]{1,30}$", description="IBAN")
    bank_account_bic: Optional[str] = Field(None, pattern=r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$", description="BIC")
    bank_account_name: Optional[str] = Field(None, max_length=100, description="Kontoinhaber")


class TaxTotal(BaseModel):
    """Tax total information."""
    tax_amount: Decimal = Field(..., ge=0, decimal_places=2, description="Steuerbetrag")
    taxable_amount: Decimal = Field(..., ge=0, decimal_places=2, description="Bemessungsgrundlage")
    tax_category: TaxCategory = Field(TaxCategory.STANDARD, description="Steuerkategorie")
    tax_percent: Decimal = Field(..., ge=0, le=100, decimal_places=2, description="Steuersatz in %")


class InvoiceLineItem(BaseModel):
    """Single line item on an invoice."""
    model_config = ConfigDict(extra="forbid")

    line_id: str = Field(..., max_length=50, description="Positions-ID")
    description: str = Field(..., max_length=500, description="Beschreibung")

    # Quantity and unit
    quantity: Decimal = Field(..., gt=0, decimal_places=4, description="Menge")
    unit_code: str = Field("C62", max_length=10, description="Einheitencode (UN/ECE Rec. 20)")

    # Pricing
    unit_price: Decimal = Field(..., decimal_places=4, description="Einzelpreis")
    line_net_amount: Decimal = Field(..., decimal_places=2, description="Nettobetrag")

    # Tax
    tax_category: TaxCategory = Field(TaxCategory.STANDARD)
    tax_percent: Decimal = Field(Decimal("19.00"), ge=0, le=100, decimal_places=2)

    # Additional info
    item_number: Optional[str] = Field(None, max_length=50, description="Artikelnummer")
    buyer_item_number: Optional[str] = Field(None, max_length=50, description="Kunden-Artikelnummer")
    seller_item_number: Optional[str] = Field(None, max_length=50, description="Lieferanten-Artikelnummer")

    # Period (for services)
    period_start: Optional[date] = Field(None, description="Leistungsbeginn")
    period_end: Optional[date] = Field(None, description="Leistungsende")


class PaymentTerms(BaseModel):
    """Payment terms and instructions."""
    note: Optional[str] = Field(None, max_length=500, description="Zahlungsbedingungen Text")
    due_date: Optional[date] = Field(None, description="Fälligkeitsdatum")

    # Discount
    discount_percent: Optional[Decimal] = Field(None, ge=0, le=100, description="Skonto Prozent")
    discount_days: Optional[int] = Field(None, ge=0, description="Skontofrist in Tagen")
    discount_amount: Optional[Decimal] = Field(None, ge=0, description="Skontobetrag")


class InvoiceData(BaseModel):
    """Complete invoice data for e-invoice generation."""
    model_config = ConfigDict(extra="forbid")

    # Invoice identification
    invoice_number: str = Field(..., max_length=50, description="Rechnungsnummer")
    invoice_type: InvoiceType = Field(InvoiceType.INVOICE, description="Rechnungsart")
    issue_date: date = Field(..., description="Rechnungsdatum")
    due_date: Optional[date] = Field(None, description="Fälligkeitsdatum")

    # Currency
    currency_code: str = Field("EUR", pattern="^[A-Z]{3}$", description="ISO 4217 Währungscode")

    # Reference
    buyer_reference: Optional[str] = Field(None, max_length=100, description="Leitweg-ID / Käuferreferenz")
    contract_reference: Optional[str] = Field(None, max_length=100, description="Vertragsnummer")
    order_reference: Optional[str] = Field(None, max_length=100, description="Bestellnummer")
    project_reference: Optional[str] = Field(None, max_length=100, description="Projektreferenz")

    # Period
    billing_period_start: Optional[date] = Field(None, description="Abrechnungszeitraum Start")
    billing_period_end: Optional[date] = Field(None, description="Abrechnungszeitraum Ende")

    # Parties
    seller: InvoiceParty = Field(..., description="Rechnungssteller")
    buyer: InvoiceParty = Field(..., description="Rechnungsempfänger")

    # Delivery (if different from buyer)
    delivery_address: Optional[Address] = Field(None, description="Lieferadresse")
    delivery_date: Optional[date] = Field(None, description="Lieferdatum")

    # Line items
    line_items: List[InvoiceLineItem] = Field(..., min_length=1, description="Rechnungspositionen")

    # Totals
    total_net_amount: Decimal = Field(..., ge=0, decimal_places=2, description="Nettobetrag gesamt")
    total_tax_amount: Decimal = Field(..., ge=0, decimal_places=2, description="Steuerbetrag gesamt")
    total_gross_amount: Decimal = Field(..., ge=0, decimal_places=2, description="Bruttobetrag gesamt")
    prepaid_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2, description="Bereits gezahlt")
    payable_amount: Decimal = Field(..., ge=0, decimal_places=2, description="Zahlbetrag")

    # Tax breakdown
    tax_totals: List[TaxTotal] = Field(default_factory=list, description="Steueraufschluesselung")

    # Payment
    payment_means_code: PaymentMeansCode = Field(PaymentMeansCode.CREDIT_TRANSFER)
    payment_terms: Optional[PaymentTerms] = Field(None, description="Zahlungsbedingungen")

    # Notes
    note: Optional[str] = Field(None, max_length=2000, description="Hinweise/Bemerkungen")

    @field_validator("line_items")
    @classmethod
    def validate_line_items(cls, v: List[InvoiceLineItem]) -> List[InvoiceLineItem]:
        """Ensure unique line IDs."""
        line_ids = [item.line_id for item in v]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("Positions-IDs müssen eindeutig sein")
        return v


class EInvoiceRequest(BaseModel):
    """Request for e-invoice generation."""
    model_config = ConfigDict(extra="forbid")

    invoice_data: InvoiceData = Field(..., description="Rechnungsdaten")
    format: EInvoiceFormat = Field(EInvoiceFormat.UBL_21, description="Ausgabeformat")
    embed_in_pdf: bool = Field(False, description="XML in PDF/A-3 einbetten")
    document_id: Optional[UUID] = Field(None, description="Dokument-ID für PDF-Embedding")


class EInvoiceResponse(BaseModel):
    """Response from e-invoice generation."""
    success: bool
    format: EInvoiceFormat
    xml_content: str = Field(..., description="Generiertes XML")
    validation_passed: bool = Field(True, description="Validierung bestanden")
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    pdf_embedded: bool = Field(False, description="In PDF eingebettet")
    pdf_url: Optional[str] = Field(None, description="URL zum PDF mit eingebettetem XML")


class ValidationResult(BaseModel):
    """E-Invoice validation result."""
    is_valid: bool
    format_detected: Optional[EInvoiceFormat] = None
    schema_valid: bool = False
    schematron_valid: bool = False
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    invoice_number: Optional[str] = None
    seller_name: Optional[str] = None
    buyer_name: Optional[str] = None
    total_amount: Optional[Decimal] = None
    validation_timestamp: datetime = Field(default_factory=datetime.utcnow)

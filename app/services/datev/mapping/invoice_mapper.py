# -*- coding: utf-8 -*-
"""
DATEV Invoice Mapper.

Mappt ExtractedInvoiceData auf DATEV Buchungssätze.

Berücksichtigt:
- Eingangs-/Ausgangsrechnungen (invoice_direction)
- Steuersätze und -schluessel
- MwSt-Aufschluesselung (tax_breakdown)
- Reverse Charge / Innergemeinschaftlich
- Vendor-Mappings für individuelle Kontozuordnung
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import structlog

from app.api.schemas.extracted_data import (
    ExtractedInvoiceData,
    InvoiceDirection,
)
from app.db import models
from ..constants import is_third_country as is_third_country_code
from ..kontenrahmen.base import BaseKontenrahmen
from .tax_code_mapper import TaxCodeMapper

logger = structlog.get_logger(__name__)


@dataclass
class MappingResult:
    """Ergebnis einer Rechnungs-Mapping-Operation."""
    success: bool
    buchung: Optional["DATEVBuchung"] = None
    warnings: List[str] = field(default_factory=list)  # FIX: Mutable Default vermeiden
    error: Optional[str] = None


@dataclass
class DATEVBuchung:
    """
    Ein DATEV Buchungssatz.

    Entspricht einer Zeile im DATEV Buchungsstapel.
    """
    umsatz: Decimal
    soll_haben: str  # "S" oder "H"
    wkz_umsatz: str  # Währungscode (z.B. "EUR")
    konto: str       # Sachkonto
    gegenkonto: str  # Gegenkonto (Personenkonto)
    bu_schluessel: Optional[str]  # Steuerschluessel
    belegdatum: date
    belegfeld_1: str  # Rechnungsnummer
    belegfeld_2: Optional[str]  # Zusatzinfo
    buchungstext: str
    kostenstelle_1: Optional[str] = None
    kostenstelle_2: Optional[str] = None
    kostentraeger: Optional[str] = None
    skonto: Optional[Decimal] = None
    kurs: Optional[Decimal] = None  # Wechselkurs bei Fremdwährung


class DATEVInvoiceMapper:
    """
    Mappt ExtractedInvoiceData auf DATEV Buchungssätze.

    Verwendung:
        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=extracted_data,
            kontenrahmen=SKR03(),
            config=datev_config,
            vendor_mapping=optional_mapping
        )
        if result.success:
            buchung = result.buchung
    """

    def __init__(self) -> None:
        self.tax_mapper = TaxCodeMapper()

    def map_invoice(
        self,
        invoice: ExtractedInvoiceData,
        kontenrahmen: BaseKontenrahmen,
        config: models.DATEVConfiguration,
        vendor_mapping: Optional[models.DATEVVendorMapping] = None,
    ) -> MappingResult:
        """
        Konvertiert eine Rechnung zu einem DATEV-Buchungssatz.

        Args:
            invoice: Extrahierte Rechnungsdaten
            kontenrahmen: SKR03 oder SKR04 Instanz
            config: DATEV-Konfiguration
            vendor_mapping: Optionales Vendor-spezifisches Mapping

        Returns:
            MappingResult mit Buchung oder Fehlermeldung
        """
        warnings: List[str] = []

        # Pflichtfelder prüfen
        validation_error = self._validate_invoice(invoice)
        if validation_error:
            return MappingResult(
                success=False,
                error=validation_error
            )

        # Richtung bestimmen
        direction = invoice.invoice_direction
        if direction == InvoiceDirection.UNKNOWN:
            return MappingResult(
                success=False,
                error="Rechnungsrichtung (Eingang/Ausgang) nicht bestimmt"
            )

        # Betrag bestimmen (Brutto)
        betrag = self._get_amount(invoice)
        if betrag is None or betrag == 0:
            return MappingResult(
                success=False,
                error="Kein gültiger Rechnungsbetrag gefunden"
            )

        # Je nach Richtung mappen
        if direction == InvoiceDirection.INCOMING:
            buchung, mapping_warnings = self._map_incoming(
                invoice=invoice,
                betrag=betrag,
                kontenrahmen=kontenrahmen,
                config=config,
                vendor_mapping=vendor_mapping,
            )
        else:
            buchung, mapping_warnings = self._map_outgoing(
                invoice=invoice,
                betrag=betrag,
                kontenrahmen=kontenrahmen,
                config=config,
            )

        warnings.extend(mapping_warnings)

        return MappingResult(
            success=True,
            buchung=buchung,
            warnings=warnings
        )

    def _validate_invoice(self, invoice: ExtractedInvoiceData) -> Optional[str]:
        """Validiert Pflichtfelder der Rechnung."""
        if not invoice.invoice_date:
            return "Rechnungsdatum fehlt"

        if not invoice.gross_amount and not invoice.net_amount:
            return "Weder Brutto- noch Nettobetrag vorhanden"

        if not invoice.invoice_number:
            # Warnung, aber kein Fehler - generiere Ersatz
            pass

        return None

    def _get_amount(self, invoice: ExtractedInvoiceData) -> Optional[Decimal]:
        """Ermittelt den Buchungsbetrag (Brutto bevorzugt)."""
        if invoice.gross_amount:
            return Decimal(str(invoice.gross_amount))
        elif invoice.net_amount:
            # Berechne Brutto aus Netto + MwSt
            net = Decimal(str(invoice.net_amount))
            vat_rate = Decimal(str(invoice.vat_rate or 19))
            return net * (1 + vat_rate / 100)
        return None

    def _map_incoming(
        self,
        invoice: ExtractedInvoiceData,
        betrag: Decimal,
        kontenrahmen: BaseKontenrahmen,
        config: models.DATEVConfiguration,
        vendor_mapping: Optional[models.DATEVVendorMapping],
    ) -> Tuple[DATEVBuchung, List[str]]:
        """
        Mappt Eingangsrechnung (Kreditor/Lieferant).

        Buchungslogik:
        - Aufwand (Soll) an Kreditor (Haben)
        - Vorsteuer wird über BU-Schluessel automatisch gebucht
        """
        warnings: List[str] = []

        # Konten bestimmen
        if vendor_mapping:
            # Individuelle Kontozuordnung
            aufwandskonto = vendor_mapping.expense_account
            kreditorenkonto = vendor_mapping.creditor_account or config.incoming_creditor_account
            kostenstelle = vendor_mapping.cost_center
            kostentraeger = vendor_mapping.cost_object
        else:
            # Standard-Konten aus Config oder Kontenrahmen
            aufwandskonto = (
                config.incoming_expense_account or
                kontenrahmen.get_expense_account("waren", float(invoice.vat_rate or 19))
            )
            kreditorenkonto = (
                config.incoming_creditor_account or
                kontenrahmen.default_creditor_account
            )
            kostenstelle = None
            kostentraeger = None

        if not kreditorenkonto:
            kreditorenkonto = kontenrahmen.default_creditor_account
            warnings.append("Kein Kreditorenkonto konfiguriert - Standard verwendet")

        # Steuerschluessel
        bu_schluessel = self.tax_mapper.get_tax_code(
            vat_rate=invoice.vat_rate,
            direction=InvoiceDirection.INCOMING,
            is_reverse_charge=invoice.is_reverse_charge or False,
            is_intra_community=invoice.intra_community_supply or False,
            is_third_country=self._is_third_country(invoice),
            sender_country=invoice.sender.country if invoice.sender else None,
        )

        # Buchungstext generieren
        buchungstext = self._generate_buchungstext(invoice, config)

        # Skonto-Betrag ermitteln
        skonto_betrag = self._get_skonto_betrag(invoice)

        buchung = DATEVBuchung(
            umsatz=abs(betrag),
            soll_haben="S",  # Aufwand = Soll
            wkz_umsatz=invoice.currency or "EUR",
            konto=aufwandskonto,
            gegenkonto=kreditorenkonto,
            bu_schluessel=bu_schluessel,
            belegdatum=invoice.invoice_date,
            belegfeld_1=self._get_belegfeld_1(invoice),
            belegfeld_2=self._get_belegfeld_2(invoice),
            buchungstext=buchungstext,
            kostenstelle_1=kostenstelle,
            kostentraeger=kostentraeger,
            skonto=skonto_betrag,
        )

        return buchung, warnings

    def _map_outgoing(
        self,
        invoice: ExtractedInvoiceData,
        betrag: Decimal,
        kontenrahmen: BaseKontenrahmen,
        config: models.DATEVConfiguration,
    ) -> Tuple[DATEVBuchung, List[str]]:
        """
        Mappt Ausgangsrechnung (Debitor/Kunde).

        Buchungslogik:
        - Debitor (Soll) an Erloes (Haben)
        - Umsatzsteuer wird über BU-Schluessel automatisch gebucht
        """
        warnings: List[str] = []

        # Konten bestimmen
        debitorenkonto = (
            config.outgoing_debtor_account or
            kontenrahmen.default_debtor_account
        )
        erloeskonto = (
            config.outgoing_revenue_account or
            kontenrahmen.get_revenue_account("waren", float(invoice.vat_rate or 19))
        )

        if not debitorenkonto:
            debitorenkonto = kontenrahmen.default_debtor_account
            warnings.append("Kein Debitorenkonto konfiguriert - Standard verwendet")

        # Steuerschluessel
        bu_schluessel = self.tax_mapper.get_tax_code(
            vat_rate=invoice.vat_rate,
            direction=InvoiceDirection.OUTGOING,
            is_reverse_charge=invoice.is_reverse_charge or False,
            is_intra_community=invoice.intra_community_supply or False,
            is_third_country=self._is_third_country(invoice),
            recipient_country=invoice.recipient.country if invoice.recipient else None,
        )

        # Buchungstext generieren
        buchungstext = self._generate_buchungstext(invoice, config)

        # Skonto-Betrag ermitteln
        skonto_betrag = self._get_skonto_betrag(invoice)

        buchung = DATEVBuchung(
            umsatz=abs(betrag),
            soll_haben="S",  # Debitor = Soll (Forderung)
            wkz_umsatz=invoice.currency or "EUR",
            konto=debitorenkonto,
            gegenkonto=erloeskonto,
            bu_schluessel=bu_schluessel,
            belegdatum=invoice.invoice_date,
            belegfeld_1=self._get_belegfeld_1(invoice),
            belegfeld_2=self._get_belegfeld_2(invoice),
            buchungstext=buchungstext,
            skonto=skonto_betrag,
        )

        return buchung, warnings

    def _generate_buchungstext(
        self,
        invoice: ExtractedInvoiceData,
        config: models.DATEVConfiguration
    ) -> str:
        """
        Generiert Buchungstext (max 60 Zeichen).

        Verwendet das konfigurierte Format oder Fallback.
        """
        format_str = config.buchungstext_format or "{invoice_number}"

        # Verfügbare Platzhalter
        sender_name = ""
        if invoice.sender:
            sender_name = invoice.sender.company or invoice.sender.person or ""

        recipient_name = ""
        if invoice.recipient:
            recipient_name = invoice.recipient.company or invoice.recipient.person or ""

        try:
            text = format_str.format(
                invoice_number=invoice.invoice_number or "o.Nr.",
                sender=sender_name[:30],
                recipient=recipient_name[:30],
            )
        except (KeyError, ValueError):
            # Fallback bei ungültigem Format
            text = invoice.invoice_number or "Rechnung"

        # DATEV Limit: 60 Zeichen
        return text[:60]

    def _get_belegfeld_1(self, invoice: ExtractedInvoiceData) -> str:
        """
        Belegfeld 1 = Rechnungsnummer (max 36 Zeichen).
        """
        nummer = invoice.invoice_number or "OHNE-NR"
        return nummer[:36]

    def _get_belegfeld_2(self, invoice: ExtractedInvoiceData) -> Optional[str]:
        """
        Belegfeld 2 = Zusatzinfo (max 12 Zeichen).

        Optional: Kundennummer oder Bestellnummer.
        """
        if invoice.customer_number:
            return invoice.customer_number[:12]
        if invoice.order_number:
            return invoice.order_number[:12]
        return None

    def _is_third_country(self, invoice: ExtractedInvoiceData) -> bool:
        """
        Prüft ob es sich um ein Drittlandsgeschäft handelt.

        Verwendet zentrale EU_MEMBER_STATES aus constants.py.
        """
        # Prüfen des Absenders/Empfängers
        if invoice.sender and invoice.sender.country:
            if is_third_country_code(invoice.sender.country):
                return True

        if invoice.recipient and invoice.recipient.country:
            if is_third_country_code(invoice.recipient.country):
                return True

        return False

    def _get_skonto_betrag(self, invoice: ExtractedInvoiceData) -> Optional[Decimal]:
        """
        Ermittelt den Skonto-Betrag aus den extrahierten Rechnungsdaten.

        Priorität:
        1. Direkt extrahierter discount_amount
        2. Berechnung aus discount_percent und gross_amount

        Returns:
            Skonto-Betrag oder None wenn keine Skonto-Daten vorhanden
        """
        # Priorität 1: Direkt extrahierter Skonto-Betrag
        if invoice.discount_amount:
            return Decimal(str(invoice.discount_amount)).quantize(Decimal("0.01"))

        # Priorität 2: Berechnung aus Prozentsatz
        if invoice.discount_percent and invoice.gross_amount:
            skonto = (
                Decimal(str(invoice.gross_amount)) *
                Decimal(str(invoice.discount_percent)) /
                Decimal("100")
            ).quantize(Decimal("0.01"))
            return skonto

        return None

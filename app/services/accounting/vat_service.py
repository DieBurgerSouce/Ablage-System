# -*- coding: utf-8 -*-
"""
USt-Voranmeldung Service (VAT Pre-Registration).

Berechnet und erstellt USt-Voranmeldungen für:
- Monatliche Meldung
- Quartalsweise Meldung
- Jährliche Zusammenfassung

GoBD-konform mit ELSTER-Export-Format.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document

logger = structlog.get_logger(__name__)


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================


class VATRate(str, Enum):
    """Deutsche USt-Sätze."""
    STANDARD = "19"        # 19% Regelsatz
    REDUCED = "7"          # 7% Ermaessigt
    ZERO = "0"             # 0% Steuerbefreit
    INNER_EU = "inner_eu"  # Innergemeinschaftlich


class VATReportPeriod(str, Enum):
    """Meldezeitraum."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


# Deutsche USt-Kennziffern (Elster)
VAT_KENNZIFFERN = {
    # Umsätze
    "81": "Steuerpflichtige Umsätze 19%",
    "86": "Steuerpflichtige Umsätze 7%",
    "35": "Steuerpflichtige Umsätze andere Steuersätze",
    "36": "Steuer auf Umsätze zu Kennziffer 35",

    # Innergemeinschaftliche Erwerbe
    "89": "Innergemeinschaftliche Erwerbe 19%",
    "93": "Innergemeinschaftliche Erwerbe 7%",

    # Steuerfrei
    "41": "Innergemeinschaftliche Lieferungen",
    "43": "Ausfuhrlieferungen",
    "44": "Steuerfreie Umsätze Drittland",

    # Vorsteuer
    "66": "Vorsteuer aus Rechnungen",
    "61": "Vorsteuer innergem. Erwerb",
    "62": "Entstandene Einfuhr-USt",
    "67": "Vorsteuer Reverse Charge",

    # Berechnung
    "83": "USt-Zahllast / Erstattungsanspruch",
}


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class VATLineItem:
    """Einzelposition für USt-Berechnung."""
    document_id: uuid.UUID
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    counterparty: Optional[str]

    net_amount: Decimal
    vat_rate: str  # z.B. "19", "7", "0"
    vat_amount: Decimal
    gross_amount: Decimal

    is_input: bool  # True = Eingangsrechnung (Vorsteuer)
    vat_category: str  # Kennziffer
    description: Optional[str] = None


@dataclass
class VATSummary:
    """Zusammenfassung einer Kennziffer."""
    kennziffer: str
    label: str
    net_amount: Decimal = Decimal("0.00")
    vat_amount: Decimal = Decimal("0.00")
    count: int = 0


@dataclass
class VATReport:
    """USt-Voranmeldung."""
    company_id: uuid.UUID
    period_type: VATReportPeriod
    period_start: date
    period_end: date
    period_label: str  # z.B. "Januar 2026", "Q1/2026"

    generated_at: datetime
    status: str = "draft"  # draft, submitted, accepted

    # Umsätze (Output VAT)
    output_vat_19: VATSummary = field(default_factory=lambda: VATSummary("81", VAT_KENNZIFFERN["81"]))
    output_vat_7: VATSummary = field(default_factory=lambda: VATSummary("86", VAT_KENNZIFFERN["86"]))
    inner_eu_deliveries: VATSummary = field(default_factory=lambda: VATSummary("41", VAT_KENNZIFFERN["41"]))
    export_deliveries: VATSummary = field(default_factory=lambda: VATSummary("43", VAT_KENNZIFFERN["43"]))

    # Vorsteuer (Input VAT)
    input_vat: VATSummary = field(default_factory=lambda: VATSummary("66", VAT_KENNZIFFERN["66"]))
    input_vat_inner_eu: VATSummary = field(default_factory=lambda: VATSummary("61", VAT_KENNZIFFERN["61"]))
    input_vat_reverse_charge: VATSummary = field(default_factory=lambda: VATSummary("67", VAT_KENNZIFFERN["67"]))

    # Innergemeinschaftliche Erwerbe
    inner_eu_acquisition_19: VATSummary = field(default_factory=lambda: VATSummary("89", VAT_KENNZIFFERN["89"]))
    inner_eu_acquisition_7: VATSummary = field(default_factory=lambda: VATSummary("93", VAT_KENNZIFFERN["93"]))

    # Berechnung
    total_output_vat: Decimal = Decimal("0.00")
    total_input_vat: Decimal = Decimal("0.00")
    vat_payable: Decimal = Decimal("0.00")  # Positive = Zahllast, Negative = Erstattung

    # Details (optional)
    line_items: List[VATLineItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für JSON/API."""
        return {
            "company_id": str(self.company_id),
            "period_type": self.period_type.value,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "period_label": self.period_label,
            "generated_at": self.generated_at.isoformat(),
            "status": self.status,
            "output_vat": {
                "vat_19": {
                    "net": float(self.output_vat_19.net_amount),
                    "vat": float(self.output_vat_19.vat_amount),
                    "count": self.output_vat_19.count,
                },
                "vat_7": {
                    "net": float(self.output_vat_7.net_amount),
                    "vat": float(self.output_vat_7.vat_amount),
                    "count": self.output_vat_7.count,
                },
                "inner_eu": {
                    "net": float(self.inner_eu_deliveries.net_amount),
                    "count": self.inner_eu_deliveries.count,
                },
                "export": {
                    "net": float(self.export_deliveries.net_amount),
                    "count": self.export_deliveries.count,
                },
            },
            "input_vat": {
                "domestic": {
                    "net": float(self.input_vat.net_amount),
                    "vat": float(self.input_vat.vat_amount),
                    "count": self.input_vat.count,
                },
                "inner_eu": {
                    "vat": float(self.input_vat_inner_eu.vat_amount),
                    "count": self.input_vat_inner_eu.count,
                },
                "reverse_charge": {
                    "vat": float(self.input_vat_reverse_charge.vat_amount),
                    "count": self.input_vat_reverse_charge.count,
                },
            },
            "inner_eu_acquisition": {
                "vat_19": {
                    "net": float(self.inner_eu_acquisition_19.net_amount),
                    "vat": float(self.inner_eu_acquisition_19.vat_amount),
                    "count": self.inner_eu_acquisition_19.count,
                },
                "vat_7": {
                    "net": float(self.inner_eu_acquisition_7.net_amount),
                    "vat": float(self.inner_eu_acquisition_7.vat_amount),
                    "count": self.inner_eu_acquisition_7.count,
                },
            },
            "totals": {
                "total_output_vat": float(self.total_output_vat),
                "total_input_vat": float(self.total_input_vat),
                "vat_payable": float(self.vat_payable),
                "is_refund": self.vat_payable < 0,
            },
        }

    def to_elster_xml(
        self,
        steuernummer: Optional[str] = None,
    ) -> str:
        """
        Generiert ELSTER-kompatibles XML für UStVA.

        Erzeugt XML gemäß dem ELSTER-Schema v11 mit:
        - TransferHeader (Verfahren, DatenArt, Vorgang)
        - DatenTeil mit Nutzdatenblock
        - Anmeldungssteuern mit allen relevanten Kennziffern
        - Zeitraum-Codierung (Monat/Quartal/Jahr)

        Args:
            steuernummer: Steuernummer der Firma (optional).
                         Wenn None, wird Platzhalter verwendet.

        Returns:
            ELSTER-konformes XML als String (UTF-8).

        Hinweis: In Produktion ERiC-Library für Zertifikat/Signatur verwenden.
        """
        from xml.etree.ElementTree import Element, SubElement, tostring
        from xml.dom.minidom import parseString

        ns = "http://www.elster.de/elsterxml/schema/v11"
        version = f"{self.period_start.year}01"
        zeitraum = self._get_elster_period()
        stnr = steuernummer or "0000000000000"

        root = Element("Elster", xmlns=ns)

        # -- TransferHeader --
        header = SubElement(root, "TransferHeader")
        SubElement(header, "Verfahren").text = "ElsterAnmeldung"
        SubElement(header, "DatenArt").text = "UStVA"
        SubElement(header, "Vorgang").text = "send"
        SubElement(header, "Testmerker").text = "700000004"
        SubElement(header, "HerstellerID").text = "00000"

        # -- DatenTeil --
        daten_teil = SubElement(root, "DatenTeil")
        nutzdatenblock = SubElement(daten_teil, "Nutzdatenblock")

        # NutzdatenHeader
        nd_header = SubElement(nutzdatenblock, "NutzdatenHeader")
        SubElement(nd_header, "NutzdatenTicket").text = "1"
        empfaenger = SubElement(nd_header, "Empfänger", id="F")
        empfaenger.text = ""

        # Nutzdaten
        nutzdaten = SubElement(nutzdatenblock, "Nutzdaten")
        anmeldung = SubElement(
            nutzdaten, "Anmeldungssteuern",
            art="UStVA",
            version=version,
        )

        # Steuernummer (Kz09) und Zeitraum (Kz10)
        SubElement(anmeldung, "Kz09").text = stnr
        SubElement(anmeldung, "Kz10").text = zeitraum

        # Kennziffern nur wenn Betrag != 0
        kz_mapping: List[Tuple[str, Decimal]] = [
            ("Kz81", self.output_vat_19.net_amount),
            ("Kz86", self.output_vat_7.net_amount),
            ("Kz36", self.output_vat_19.vat_amount + self.output_vat_7.vat_amount),
            ("Kz41", self.inner_eu_deliveries.net_amount),
            ("Kz43", self.export_deliveries.net_amount),
            ("Kz89", self.inner_eu_acquisition_19.net_amount),
            ("Kz93", self.inner_eu_acquisition_7.net_amount),
            ("Kz66", self.input_vat.vat_amount),
            ("Kz61", self.input_vat_inner_eu.vat_amount),
            ("Kz67", self.input_vat_reverse_charge.vat_amount),
            ("Kz83", self.vat_payable),
        ]

        for kz_name, amount in kz_mapping:
            if amount != Decimal("0") and amount != Decimal("0.00"):
                SubElement(anmeldung, kz_name).text = str(
                    int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                )

        # Serialize
        raw_xml = tostring(root, encoding="unicode")
        pretty = parseString(raw_xml).toprettyxml(indent="  ", encoding="UTF-8")
        return pretty.decode("UTF-8")

    def _get_elster_period(self) -> str:
        """Gibt ELSTER-Zeitraumcode zurück."""
        if self.period_type == VATReportPeriod.MONTHLY:
            return f"{self.period_start.month:02d}"
        elif self.period_type == VATReportPeriod.QUARTERLY:
            quarter = (self.period_start.month - 1) // 3 + 1
            return f"Q{quarter}"
        else:
            return "00"  # Jährlich


# ============================================================================
# VAT SERVICE
# ============================================================================


class VATService:
    """
    Service für USt-Voranmeldung.

    Features:
    - Automatische Berechnung aus Dokumenten
    - USt-Sätze Erkennung
    - ELSTER-Export
    - Historische Berichte

    GoBD-konform.
    """

    # Mapping: Dokumenttyp zu Input/Output
    INPUT_DOCUMENT_TYPES = ["eingangsrechnung", "supplier_invoice", "purchase_invoice"]
    OUTPUT_DOCUMENT_TYPES = ["invoice", "ausgangsrechnung", "sales_invoice"]

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db

    # ========================================================================
    # REPORT GENERATION
    # ========================================================================

    async def generate_vat_report(
        self,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
        include_details: bool = True,
    ) -> VATReport:
        """
        Generiert USt-Voranmeldung für einen Zeitraum.

        Args:
            company_id: Firma
            period_start: Beginn des Meldezeitraums
            period_end: Ende des Meldezeitraums
            include_details: Einzelpositionen einbeziehen

        Returns:
            VATReport
        """
        # Periode bestimmen
        period_type, period_label = self._determine_period_type(period_start, period_end)

        report = VATReport(
            company_id=company_id,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            period_label=period_label,
            generated_at=datetime.now(timezone.utc),
        )

        # Ausgangsrechnungen (Output VAT)
        output_items = await self._get_output_vat_items(company_id, period_start, period_end)
        for item in output_items:
            self._add_output_item(report, item)
            if include_details:
                report.line_items.append(item)

        # Eingangsrechnungen (Input VAT)
        input_items = await self._get_input_vat_items(company_id, period_start, period_end)
        for item in input_items:
            self._add_input_item(report, item)
            if include_details:
                report.line_items.append(item)

        # Berechnungen
        report.total_output_vat = (
            report.output_vat_19.vat_amount +
            report.output_vat_7.vat_amount +
            report.inner_eu_acquisition_19.vat_amount +
            report.inner_eu_acquisition_7.vat_amount
        )

        report.total_input_vat = (
            report.input_vat.vat_amount +
            report.input_vat_inner_eu.vat_amount +
            report.input_vat_reverse_charge.vat_amount
        )

        report.vat_payable = report.total_output_vat - report.total_input_vat

        logger.info(
            "vat_report_generated",
            company_id=str(company_id),
            period=period_label,
            output_vat=float(report.total_output_vat),
            input_vat=float(report.total_input_vat),
            payable=float(report.vat_payable),
        )

        return report

    async def generate_monthly_report(
        self,
        company_id: uuid.UUID,
        year: int,
        month: int,
        include_details: bool = True,
    ) -> VATReport:
        """
        Generiert monatliche USt-Voranmeldung.

        Args:
            company_id: Firma
            year: Jahr
            month: Monat (1-12)
            include_details: Einzelpositionen

        Returns:
            VATReport
        """
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year, 12, 31)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)

        return await self.generate_vat_report(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            include_details=include_details,
        )

    async def generate_quarterly_report(
        self,
        company_id: uuid.UUID,
        year: int,
        quarter: int,
        include_details: bool = True,
    ) -> VATReport:
        """
        Generiert Quartals-USt-Voranmeldung.

        Args:
            company_id: Firma
            year: Jahr
            quarter: Quartal (1-4)
            include_details: Einzelpositionen

        Returns:
            VATReport
        """
        quarter_months = {
            1: (1, 3),
            2: (4, 6),
            3: (7, 9),
            4: (10, 12),
        }

        start_month, end_month = quarter_months[quarter]
        period_start = date(year, start_month, 1)

        if end_month == 12:
            period_end = date(year, 12, 31)
        else:
            period_end = date(year, end_month + 1, 1) - timedelta(days=1)

        return await self.generate_vat_report(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            include_details=include_details,
        )

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    def _determine_period_type(
        self,
        start: date,
        end: date,
    ) -> Tuple[VATReportPeriod, str]:
        """Bestimmt Periodentyp und Label."""
        days = (end - start).days + 1

        if days <= 31:
            # Monatlich
            month_names = [
                "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
                "Juli", "August", "September", "Oktober", "November", "Dezember"
            ]
            return VATReportPeriod.MONTHLY, f"{month_names[start.month]} {start.year}"
        elif days <= 92:
            # Quartalsweise
            quarter = (start.month - 1) // 3 + 1
            return VATReportPeriod.QUARTERLY, f"Q{quarter}/{start.year}"
        else:
            # Jährlich
            return VATReportPeriod.YEARLY, str(start.year)

    async def _get_output_vat_items(
        self,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[VATLineItem]:
        """Holt Ausgangsrechnungen für Output VAT."""
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type.in_(self.OUTPUT_DOCUMENT_TYPES),
                Document.upload_date >= period_start,
                Document.upload_date <= period_end,
            )
        )

        result = await self.db.execute(query)
        documents = result.scalars().all()

        items: List[VATLineItem] = []

        for doc in documents:
            extracted = doc.extracted_data or {}

            # Betraege extrahieren
            net = self._extract_amount(extracted, ["net_amount", "netto", "subtotal"])
            gross = self._extract_amount(extracted, ["total_amount", "brutto", "gross_amount", "amount"])
            vat = self._extract_amount(extracted, ["vat_amount", "tax_amount", "mwst", "ust"])

            if gross == Decimal("0"):
                continue

            # USt-Satz bestimmen
            vat_rate = self._detect_vat_rate(extracted, net, gross, vat)

            # Fehlende Werte berechnen
            if net == Decimal("0") and vat_rate != "0":
                net = gross / (1 + Decimal(vat_rate) / 100)
            if vat == Decimal("0") and vat_rate != "0":
                vat = gross - net

            item = VATLineItem(
                document_id=doc.id,
                invoice_number=extracted.get("invoice_number"),
                invoice_date=doc.upload_date,
                counterparty=extracted.get("customer_name") or extracted.get("recipient"),
                net_amount=net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                vat_rate=vat_rate,
                vat_amount=vat.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                gross_amount=gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                is_input=False,
                vat_category=self._get_vat_category(vat_rate, False, extracted),
            )
            items.append(item)

        return items

    async def _get_input_vat_items(
        self,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[VATLineItem]:
        """Holt Eingangsrechnungen für Input VAT (Vorsteuer)."""
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type.in_(self.INPUT_DOCUMENT_TYPES),
                Document.upload_date >= period_start,
                Document.upload_date <= period_end,
            )
        )

        result = await self.db.execute(query)
        documents = result.scalars().all()

        items: List[VATLineItem] = []

        for doc in documents:
            extracted = doc.extracted_data or {}

            # Betraege extrahieren
            net = self._extract_amount(extracted, ["net_amount", "netto", "subtotal"])
            gross = self._extract_amount(extracted, ["total_amount", "brutto", "gross_amount", "amount"])
            vat = self._extract_amount(extracted, ["vat_amount", "tax_amount", "mwst", "ust"])

            if gross == Decimal("0"):
                continue

            vat_rate = self._detect_vat_rate(extracted, net, gross, vat)

            if net == Decimal("0") and vat_rate != "0":
                net = gross / (1 + Decimal(vat_rate) / 100)
            if vat == Decimal("0") and vat_rate != "0":
                vat = gross - net

            item = VATLineItem(
                document_id=doc.id,
                invoice_number=extracted.get("invoice_number"),
                invoice_date=doc.document_date,
                counterparty=extracted.get("supplier_name") or extracted.get("creditor_name"),
                net_amount=net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                vat_rate=vat_rate,
                vat_amount=vat.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                gross_amount=gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                is_input=True,
                vat_category=self._get_vat_category(vat_rate, True, extracted),
            )
            items.append(item)

        return items

    def _extract_amount(self, data: Dict[str, Any], keys: List[str]) -> Decimal:
        """Extrahiert einen Betrag aus verschiedenen Feldnamen."""
        for key in keys:
            value = data.get(key)
            if value is not None:
                try:
                    return Decimal(str(value).replace(",", ".").replace(" ", ""))
                except (ValueError, InvalidOperation, TypeError) as e:
                    logger.debug(
                        "amount_parsing_skipped",
                        key=key,
                        value_type=type(value).__name__,
                        error_type=type(e).__name__,
                    )
        return Decimal("0")

    def _detect_vat_rate(
        self,
        data: Dict[str, Any],
        net: Decimal,
        gross: Decimal,
        vat: Decimal,
    ) -> str:
        """Erkennt den USt-Satz."""
        # Aus extrahierten Daten
        explicit_rate = data.get("vat_rate") or data.get("tax_rate") or data.get("mwst_satz")
        if explicit_rate:
            try:
                rate = float(str(explicit_rate).replace("%", "").replace(",", "."))
                if rate >= 18 and rate <= 20:
                    return "19"
                elif rate >= 6 and rate <= 8:
                    return "7"
                elif rate == 0:
                    return "0"
            except (ValueError, TypeError) as e:
                logger.debug(
                    "vat_rate_parsing_skipped",
                    explicit_rate=str(explicit_rate)[:50],
                    error_type=type(e).__name__,
                )

        # Aus Betraegen berechnen
        if net > 0 and gross > 0:
            calculated_rate = ((gross - net) / net * 100).quantize(Decimal("0.1"))
            if Decimal("18.5") <= calculated_rate <= Decimal("19.5"):
                return "19"
            elif Decimal("6.5") <= calculated_rate <= Decimal("7.5"):
                return "7"
            elif calculated_rate < Decimal("0.5"):
                return "0"

        # Aus VAT berechnen
        if vat > 0 and net > 0:
            calculated_rate = (vat / net * 100).quantize(Decimal("0.1"))
            if Decimal("18.5") <= calculated_rate <= Decimal("19.5"):
                return "19"
            elif Decimal("6.5") <= calculated_rate <= Decimal("7.5"):
                return "7"

        # Default
        return "19"

    def _get_vat_category(
        self,
        vat_rate: str,
        is_input: bool,
        data: Dict[str, Any],
    ) -> str:
        """Bestimmt die USt-Kennziffer."""
        # Innergemeinschaftlich?
        is_eu = data.get("is_inner_eu") or data.get("innergemeinschaftlich")
        is_export = data.get("is_export") or data.get("ausfuhr")
        is_reverse_charge = data.get("is_reverse_charge") or data.get("reverse_charge")

        if is_input:
            if is_eu:
                return "61"  # Vorsteuer innergem. Erwerb
            elif is_reverse_charge:
                return "67"  # Vorsteuer Reverse Charge
            else:
                return "66"  # Normale Vorsteuer
        else:
            if is_eu:
                return "41"  # Innergemeinschaftliche Lieferungen
            elif is_export:
                return "43"  # Ausfuhrlieferungen
            elif vat_rate == "19":
                return "81"  # Umsätze 19%
            elif vat_rate == "7":
                return "86"  # Umsätze 7%
            else:
                return "35"  # Andere Steuersätze

    def _add_output_item(self, report: VATReport, item: VATLineItem) -> None:
        """Fuegt Ausgangsrechnung zum Report hinzu."""
        if item.vat_category == "81":
            report.output_vat_19.net_amount += item.net_amount
            report.output_vat_19.vat_amount += item.vat_amount
            report.output_vat_19.count += 1
        elif item.vat_category == "86":
            report.output_vat_7.net_amount += item.net_amount
            report.output_vat_7.vat_amount += item.vat_amount
            report.output_vat_7.count += 1
        elif item.vat_category == "41":
            report.inner_eu_deliveries.net_amount += item.net_amount
            report.inner_eu_deliveries.count += 1
        elif item.vat_category == "43":
            report.export_deliveries.net_amount += item.net_amount
            report.export_deliveries.count += 1

    def _add_input_item(self, report: VATReport, item: VATLineItem) -> None:
        """Fuegt Eingangsrechnung zum Report hinzu."""
        if item.vat_category == "66":
            report.input_vat.net_amount += item.net_amount
            report.input_vat.vat_amount += item.vat_amount
            report.input_vat.count += 1
        elif item.vat_category == "61":
            report.input_vat_inner_eu.vat_amount += item.vat_amount
            report.input_vat_inner_eu.count += 1
        elif item.vat_category == "67":
            report.input_vat_reverse_charge.vat_amount += item.vat_amount
            report.input_vat_reverse_charge.count += 1


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def get_vat_service(db: AsyncSession) -> VATService:
    """Factory-Funktion für Dependency Injection."""
    return VATService(db)

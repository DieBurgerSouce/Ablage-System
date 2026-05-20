# -*- coding: utf-8 -*-
"""Unit tests fuer VAT Service - ELSTER XML Export.

Tests fuer:
- ELSTER XML Generierung (Pflichtfelder: Steuernummer, Zeitraum, USt-Positionen)
- USt-Kennziffer-Zuordnung fuer SKR03/04
- XML-Struktur/Schema Compliance
- Fehlerfaelle: fehlende Steuernummer, ungueltige Zeitraeume
- Nullbetraege (gueltige XML trotzdem)
- Periodentyp-Erkennung
- USt-Satz-Erkennung
- VATReport.to_dict() Serialisierung
"""

import pytest
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.accounting.vat_service import (
    VATService,
    VATReport,
    VATReportPeriod,
    VATLineItem,
    VATSummary,
    VATRate,
    VAT_KENNZIFFERN,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    return db


@pytest.fixture
def vat_service(mock_db):
    """VATService-Instanz mit Mock-DB."""
    return VATService(mock_db)


@pytest.fixture
def company_id():
    """Test-Firmen-ID."""
    return uuid.uuid4()


def _make_vat_report(
    company_id: uuid.UUID,
    period_type: VATReportPeriod = VATReportPeriod.MONTHLY,
    period_start: date = date(2026, 1, 1),
    period_end: date = date(2026, 1, 31),
    period_label: str = "Januar 2026",
    output_19_net: Decimal = Decimal("0.00"),
    output_19_vat: Decimal = Decimal("0.00"),
    output_7_net: Decimal = Decimal("0.00"),
    output_7_vat: Decimal = Decimal("0.00"),
    input_vat: Decimal = Decimal("0.00"),
    vat_payable: Decimal = Decimal("0.00"),
) -> VATReport:
    """Helfer: Erstellt VATReport mit gegebenen Werten."""
    report = VATReport(
        company_id=company_id,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        period_label=period_label,
        generated_at=datetime.now(timezone.utc),
    )
    report.output_vat_19.net_amount = output_19_net
    report.output_vat_19.vat_amount = output_19_vat
    report.output_vat_19.count = 1 if output_19_net > 0 else 0
    report.output_vat_7.net_amount = output_7_net
    report.output_vat_7.vat_amount = output_7_vat
    report.output_vat_7.count = 1 if output_7_net > 0 else 0
    report.input_vat.vat_amount = input_vat
    report.input_vat.count = 1 if input_vat > 0 else 0
    report.total_output_vat = output_19_vat + output_7_vat
    report.total_input_vat = input_vat
    report.vat_payable = vat_payable
    return report


ELSTER_NS = "http://www.elster.de/elsterxml/schema/v11"
_NS_PREFIX = f"{{{ELSTER_NS}}}"


def _parse_elster_xml(xml_string: str) -> ET.Element:
    """Helfer: Parst ELSTER XML-String zu ElementTree."""
    return ET.fromstring(xml_string)


def _find(element: ET.Element, path: str) -> ET.Element:
    """Findet Element mit ELSTER-Namespace (Kurzform)."""
    # Konvertiert z.B. ".//Anmeldungssteuern/Kz09" zu namespace-qualifiziertem Pfad
    parts = path.split("/")
    ns_parts = []
    for p in parts:
        if p == "." or p == "..":
            ns_parts.append(p)
        elif p == "":
            ns_parts.append("")
        else:
            ns_parts.append(f"{_NS_PREFIX}{p}")
    ns_path = "/".join(ns_parts)
    return element.find(ns_path)


# =============================================================================
# TESTS: ELSTER XML Generierung
# =============================================================================


class TestElsterXMLGeneration:
    """Tests fuer die ELSTER XML-Erzeugung."""

    def test_xml_enthaelt_transfer_header(self, company_id):
        """XML enthaelt TransferHeader mit Pflichtfeldern."""
        report = _make_vat_report(company_id)
        xml_str = report.to_elster_xml(steuernummer="1234567890123")

        root = _parse_elster_xml(xml_str)

        header = _find(root, "TransferHeader")
        assert header is not None
        assert _find(header, "Verfahren").text == "ElsterAnmeldung"
        assert _find(header, "DatenArt").text == "UStVA"
        assert _find(header, "Vorgang").text == "send"

    def test_xml_enthaelt_steuernummer(self, company_id):
        """Steuernummer wird als Kz09 in XML geschrieben."""
        report = _make_vat_report(company_id)
        xml_str = report.to_elster_xml(steuernummer="9876543210123")

        root = _parse_elster_xml(xml_str)

        anmeldung = _find(root, ".//Anmeldungssteuern")
        assert anmeldung is not None
        kz09 = _find(anmeldung, "Kz09")
        assert kz09 is not None
        assert kz09.text == "9876543210123"

    def test_xml_platzhalter_steuernummer_wenn_none(self, company_id):
        """Platzhalter-Steuernummer wenn keine angegeben."""
        report = _make_vat_report(company_id)
        xml_str = report.to_elster_xml(steuernummer=None)

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")
        kz09 = _find(anmeldung, "Kz09")
        assert kz09.text == "0000000000000"

    def test_xml_enthaelt_zeitraum_monatlich(self, company_id):
        """Monatlicher Zeitraum wird korrekt codiert (01-12)."""
        report = _make_vat_report(
            company_id,
            period_type=VATReportPeriod.MONTHLY,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        xml_str = report.to_elster_xml()

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")
        kz10 = _find(anmeldung, "Kz10")
        assert kz10 is not None
        assert kz10.text == "03"

    def test_xml_enthaelt_zeitraum_quartalsweise(self, company_id):
        """Quartalszeitraum wird als Q1-Q4 codiert."""
        report = _make_vat_report(
            company_id,
            period_type=VATReportPeriod.QUARTERLY,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 9, 30),
        )
        xml_str = report.to_elster_xml()

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")
        kz10 = _find(anmeldung, "Kz10")
        assert kz10.text == "Q3"

    def test_xml_enthaelt_zeitraum_jaehrlich(self, company_id):
        """Jaehrlicher Zeitraum wird als '00' codiert."""
        report = _make_vat_report(
            company_id,
            period_type=VATReportPeriod.YEARLY,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
        )
        xml_str = report.to_elster_xml()

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")
        kz10 = _find(anmeldung, "Kz10")
        assert kz10.text == "00"

    def test_xml_enthaelt_umsaetze_19_prozent(self, company_id):
        """Kz81 (Netto 19%) und Kz36 (Steuer) in XML."""
        report = _make_vat_report(
            company_id,
            output_19_net=Decimal("10000.00"),
            output_19_vat=Decimal("1900.00"),
            vat_payable=Decimal("1900.00"),
        )
        xml_str = report.to_elster_xml()

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")

        kz81 = _find(anmeldung, "Kz81")
        assert kz81 is not None
        assert kz81.text == "10000"  # Ganzzahl, gerundet

        kz36 = _find(anmeldung, "Kz36")
        assert kz36 is not None
        assert kz36.text == "1900"

    def test_xml_enthaelt_vorsteuer(self, company_id):
        """Kz66 (Vorsteuer) in XML."""
        report = _make_vat_report(
            company_id,
            output_19_net=Decimal("5000.00"),
            output_19_vat=Decimal("950.00"),
            input_vat=Decimal("400.00"),
            vat_payable=Decimal("550.00"),
        )
        xml_str = report.to_elster_xml()

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")

        kz66 = _find(anmeldung, "Kz66")
        assert kz66 is not None
        assert kz66.text == "400"

    def test_xml_zahllast_kz83(self, company_id):
        """Kz83 (Zahllast) in XML."""
        report = _make_vat_report(
            company_id,
            vat_payable=Decimal("1500.00"),
        )
        xml_str = report.to_elster_xml()

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")

        kz83 = _find(anmeldung, "Kz83")
        assert kz83 is not None
        assert kz83.text == "1500"

    def test_xml_nullbetraege_werden_ausgelassen(self, company_id):
        """Kennziffern mit 0-Betrag werden nicht ins XML geschrieben."""
        report = _make_vat_report(company_id)
        # Alle Betraege sind 0
        xml_str = report.to_elster_xml()

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")

        # Kz81, Kz86, etc. sollten NICHT vorhanden sein
        assert _find(anmeldung, "Kz81") is None
        assert _find(anmeldung, "Kz86") is None
        assert _find(anmeldung, "Kz66") is None
        # Kz09 und Kz10 muessen immer da sein
        assert _find(anmeldung, "Kz09") is not None
        assert _find(anmeldung, "Kz10") is not None

    def test_xml_ist_valides_utf8(self, company_id):
        """XML ist als UTF-8 codiert."""
        report = _make_vat_report(
            company_id,
            output_19_net=Decimal("1000.00"),
            output_19_vat=Decimal("190.00"),
            vat_payable=Decimal("190.00"),
        )
        xml_str = report.to_elster_xml()

        assert "UTF-8" in xml_str
        # Muss parsbar sein
        root = _parse_elster_xml(xml_str)
        # Tag includes namespace
        assert root.tag == f"{{{ELSTER_NS}}}Elster"

    def test_xml_erstattungsanspruch_negativ(self, company_id):
        """Negativer Betrag bei Erstattungsanspruch (Vorsteuerueberhang)."""
        report = _make_vat_report(
            company_id,
            input_vat=Decimal("3000.00"),
            output_19_vat=Decimal("500.00"),
            vat_payable=Decimal("-2500.00"),
        )
        xml_str = report.to_elster_xml()

        root = _parse_elster_xml(xml_str)
        anmeldung = _find(root, ".//Anmeldungssteuern")

        kz83 = _find(anmeldung, "Kz83")
        assert kz83 is not None
        assert kz83.text == "-2500"


# =============================================================================
# TESTS: Periodentyp-Erkennung
# =============================================================================


class TestPeriodTypDetection:
    """Tests fuer _determine_period_type."""

    def test_erkennt_monatlich(self, vat_service):
        """Zeitraum <= 31 Tage = monatlich."""
        period_type, label = vat_service._determine_period_type(
            date(2026, 6, 1), date(2026, 6, 30)
        )
        assert period_type == VATReportPeriod.MONTHLY
        assert "Juni" in label
        assert "2026" in label

    def test_erkennt_quartalsweise(self, vat_service):
        """Zeitraum 32-92 Tage = quartalsweise."""
        period_type, label = vat_service._determine_period_type(
            date(2026, 4, 1), date(2026, 6, 30)
        )
        assert period_type == VATReportPeriod.QUARTERLY
        assert "Q2" in label

    def test_erkennt_jaehrlich(self, vat_service):
        """Zeitraum > 92 Tage = jaehrlich."""
        period_type, label = vat_service._determine_period_type(
            date(2026, 1, 1), date(2026, 12, 31)
        )
        assert period_type == VATReportPeriod.YEARLY
        assert "2026" in label


# =============================================================================
# TESTS: USt-Satz-Erkennung
# =============================================================================


class TestVATRateDetection:
    """Tests fuer _detect_vat_rate."""

    def test_erkennt_19_prozent_explizit(self, vat_service):
        """Expliziter USt-Satz 19%."""
        data: Dict[str, Any] = {"vat_rate": "19%"}
        rate = vat_service._detect_vat_rate(data, Decimal("0"), Decimal("0"), Decimal("0"))
        assert rate == "19"

    def test_erkennt_7_prozent_explizit(self, vat_service):
        """Expliziter USt-Satz 7%."""
        data: Dict[str, Any] = {"tax_rate": "7"}
        rate = vat_service._detect_vat_rate(data, Decimal("0"), Decimal("0"), Decimal("0"))
        assert rate == "7"

    def test_erkennt_0_prozent_explizit(self, vat_service):
        """Expliziter USt-Satz 0%."""
        data: Dict[str, Any] = {"mwst_satz": "0"}
        rate = vat_service._detect_vat_rate(data, Decimal("0"), Decimal("0"), Decimal("0"))
        assert rate == "0"

    def test_berechnet_19_prozent_aus_betraegen(self, vat_service):
        """19% wird aus Netto/Brutto berechnet."""
        data: Dict[str, Any] = {}
        rate = vat_service._detect_vat_rate(
            data,
            net=Decimal("100.00"),
            gross=Decimal("119.00"),
            vat=Decimal("0"),
        )
        assert rate == "19"

    def test_berechnet_7_prozent_aus_betraegen(self, vat_service):
        """7% wird aus Netto/Brutto berechnet."""
        data: Dict[str, Any] = {}
        rate = vat_service._detect_vat_rate(
            data,
            net=Decimal("100.00"),
            gross=Decimal("107.00"),
            vat=Decimal("0"),
        )
        assert rate == "7"

    def test_default_19_prozent(self, vat_service):
        """Default ist 19% wenn nichts erkannt."""
        data: Dict[str, Any] = {}
        rate = vat_service._detect_vat_rate(
            data,
            net=Decimal("0"),
            gross=Decimal("0"),
            vat=Decimal("0"),
        )
        assert rate == "19"


# =============================================================================
# TESTS: USt-Kennziffer-Zuordnung
# =============================================================================


class TestVATCategoryMapping:
    """Tests fuer _get_vat_category."""

    def test_output_19_prozent_ist_kz81(self, vat_service):
        """Ausgangsrechnung 19% -> Kennziffer 81."""
        cat = vat_service._get_vat_category("19", False, {})
        assert cat == "81"

    def test_output_7_prozent_ist_kz86(self, vat_service):
        """Ausgangsrechnung 7% -> Kennziffer 86."""
        cat = vat_service._get_vat_category("7", False, {})
        assert cat == "86"

    def test_input_normal_ist_kz66(self, vat_service):
        """Eingangsrechnung normal -> Kennziffer 66."""
        cat = vat_service._get_vat_category("19", True, {})
        assert cat == "66"

    def test_innergemeinschaftlich_output_ist_kz41(self, vat_service):
        """Innergemeinschaftliche Lieferung -> Kennziffer 41."""
        cat = vat_service._get_vat_category("19", False, {"is_inner_eu": True})
        assert cat == "41"

    def test_ausfuhr_ist_kz43(self, vat_service):
        """Ausfuhrlieferung -> Kennziffer 43."""
        cat = vat_service._get_vat_category("19", False, {"is_export": True})
        assert cat == "43"

    def test_input_innergem_ist_kz61(self, vat_service):
        """Vorsteuer innergem. Erwerb -> Kennziffer 61."""
        cat = vat_service._get_vat_category("19", True, {"is_inner_eu": True})
        assert cat == "61"

    def test_input_reverse_charge_ist_kz67(self, vat_service):
        """Vorsteuer Reverse Charge -> Kennziffer 67."""
        cat = vat_service._get_vat_category("19", True, {"is_reverse_charge": True})
        assert cat == "67"


# =============================================================================
# TESTS: Betragsextraktion
# =============================================================================


class TestAmountExtraction:
    """Tests fuer _extract_amount."""

    def test_extrahiert_normalen_betrag(self, vat_service):
        """Normaler Dezimalbetrag wird korrekt extrahiert."""
        data: Dict[str, Any] = {"net_amount": "1234.56"}
        amount = vat_service._extract_amount(data, ["net_amount"])
        assert amount == Decimal("1234.56")

    def test_extrahiert_deutsches_format(self, vat_service):
        """Deutsches Zahlenformat (Komma als Dezimaltrennzeichen)."""
        data: Dict[str, Any] = {"netto": "1234,56"}
        amount = vat_service._extract_amount(data, ["netto"])
        assert amount == Decimal("1234.56")

    def test_null_bei_fehlendem_schluessel(self, vat_service):
        """0 wenn kein Schluessel gefunden."""
        data: Dict[str, Any] = {"other_field": "100"}
        amount = vat_service._extract_amount(data, ["net_amount", "netto"])
        assert amount == Decimal("0")

    def test_null_bei_ungueltigem_wert(self, vat_service):
        """0 bei nicht-parsearem Wert."""
        data: Dict[str, Any] = {"net_amount": "nicht-eine-zahl"}
        amount = vat_service._extract_amount(data, ["net_amount"])
        assert amount == Decimal("0")


# =============================================================================
# TESTS: VATReport.to_dict()
# =============================================================================


class TestVATReportToDict:
    """Tests fuer die JSON-Serialisierung."""

    def test_to_dict_enthaelt_pflichtfelder(self, company_id):
        """to_dict() enthaelt alle Pflichtfelder."""
        report = _make_vat_report(
            company_id,
            output_19_net=Decimal("5000.00"),
            output_19_vat=Decimal("950.00"),
            input_vat=Decimal("200.00"),
            vat_payable=Decimal("750.00"),
        )

        d = report.to_dict()

        assert d["company_id"] == str(company_id)
        assert d["period_type"] == "monthly"
        assert d["period_start"] == "2026-01-01"
        assert d["period_end"] == "2026-01-31"
        assert d["status"] == "draft"

        # Output VAT
        assert d["output_vat"]["vat_19"]["net"] == 5000.0
        assert d["output_vat"]["vat_19"]["vat"] == 950.0

        # Input VAT
        assert d["input_vat"]["domestic"]["vat"] == 200.0

        # Totals
        assert d["totals"]["vat_payable"] == 750.0
        assert d["totals"]["is_refund"] is False

    def test_to_dict_erstattung_is_refund_true(self, company_id):
        """is_refund ist True bei negativer Zahllast."""
        report = _make_vat_report(
            company_id,
            vat_payable=Decimal("-500.00"),
        )

        d = report.to_dict()
        assert d["totals"]["is_refund"] is True


# =============================================================================
# TESTS: Report-Generierung (async)
# =============================================================================


class TestReportGeneration:
    """Tests fuer generate_vat_report und Hilfsmethoden."""

    @pytest.mark.asyncio
    async def test_generate_report_ohne_dokumente(self, vat_service, company_id):
        """Report mit Nullwerten wenn keine Dokumente vorhanden."""
        # Interne Methoden mocken (umgeht Document.document_date Query)
        vat_service._get_output_vat_items = AsyncMock(return_value=[])
        vat_service._get_input_vat_items = AsyncMock(return_value=[])

        report = await vat_service.generate_vat_report(
            company_id=company_id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )

        assert isinstance(report, VATReport)
        assert report.total_output_vat == Decimal("0.00")
        assert report.total_input_vat == Decimal("0.00")
        assert report.vat_payable == Decimal("0.00")
        assert report.line_items == []

    @pytest.mark.asyncio
    async def test_generate_report_mit_ausgangsrechnung(self, vat_service, company_id):
        """Report berechnet korrekt fuer eine Ausgangsrechnung."""
        output_item = VATLineItem(
            document_id=uuid.uuid4(),
            invoice_number="R-2026-001",
            invoice_date=date(2026, 1, 15),
            counterparty="Testkunde GmbH",
            net_amount=Decimal("1000.00"),
            vat_rate="19",
            vat_amount=Decimal("190.00"),
            gross_amount=Decimal("1190.00"),
            is_input=False,
            vat_category="81",
        )

        vat_service._get_output_vat_items = AsyncMock(return_value=[output_item])
        vat_service._get_input_vat_items = AsyncMock(return_value=[])

        report = await vat_service.generate_vat_report(
            company_id=company_id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )

        assert report.output_vat_19.net_amount == Decimal("1000.00")
        assert report.output_vat_19.vat_amount == Decimal("190.00")
        assert report.output_vat_19.count == 1
        assert report.total_output_vat == Decimal("190.00")
        assert report.vat_payable == Decimal("190.00")
        assert len(report.line_items) == 1


# =============================================================================
# TESTS: VATReport Enums und Konstanten
# =============================================================================


class TestVATConstants:
    """Tests fuer Enums und Konstanten."""

    def test_vat_rate_werte(self):
        """VATRate hat erwartete Werte."""
        assert VATRate.STANDARD.value == "19"
        assert VATRate.REDUCED.value == "7"
        assert VATRate.ZERO.value == "0"

    def test_vat_kennziffern_vorhanden(self):
        """Alle wichtigen Kennziffern sind definiert."""
        assert "81" in VAT_KENNZIFFERN  # 19% Umsaetze
        assert "86" in VAT_KENNZIFFERN  # 7% Umsaetze
        assert "66" in VAT_KENNZIFFERN  # Vorsteuer
        assert "83" in VAT_KENNZIFFERN  # Zahllast
        assert "41" in VAT_KENNZIFFERN  # Innergem. Lieferungen

    def test_vat_report_period_werte(self):
        """VATReportPeriod hat erwartete Werte."""
        assert VATReportPeriod.MONTHLY.value == "monthly"
        assert VATReportPeriod.QUARTERLY.value == "quarterly"
        assert VATReportPeriod.YEARLY.value == "yearly"

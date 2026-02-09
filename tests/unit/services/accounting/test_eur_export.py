# -*- coding: utf-8 -*-
"""Unit tests fuer EUeR Service - Einnahmen-Ueberschuss-Rechnung.

Tests fuer:
- EUeR Report-Generierung (Einnahmen/Ausgaben)
- Einnahmen/Ausgaben-Kategorisierung (Betriebseinnahmen vs Betriebsausgaben)
- Gewinn/Verlust-Berechnung (Gewinn = Einnahmen - Ausgaben)
- Leerer Zeitraum (gueltiger Report mit Nullsummen)
- Gemischte Transaktionstypen
- HTML-Export (to_anlage_eur_html)
- Anlage EUeR Zeilen-Mapping
- to_dict() Serialisierung
"""

import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.accounting.eur_service import (
    EURService,
    EURReport,
    EURLineItem,
    EURCategorySummary,
    IncomeCategory,
    ExpenseCategory,
    CATEGORY_MAPPING,
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
def eur_service(mock_db):
    """EURService-Instanz mit Mock-DB."""
    return EURService(mock_db)


@pytest.fixture
def company_id():
    """Test-Firmen-ID."""
    return uuid.uuid4()


def _make_eur_report(
    company_id: uuid.UUID,
    fiscal_year: int = 2026,
    total_income: Decimal = Decimal("0.00"),
    total_expenses: Decimal = Decimal("0.00"),
    income_categories: List[EURCategorySummary] = None,
    expense_categories: List[EURCategorySummary] = None,
) -> EURReport:
    """Helfer: Erstellt EURReport mit gegebenen Werten."""
    report = EURReport(
        company_id=company_id,
        fiscal_year=fiscal_year,
        period_start=date(fiscal_year, 1, 1),
        period_end=date(fiscal_year, 12, 31),
        generated_at=datetime.now(timezone.utc),
    )
    report.total_income = total_income
    report.total_expenses = total_expenses
    report.profit_loss = total_income - total_expenses
    report.is_profit = report.profit_loss >= 0
    report.income_categories = income_categories or []
    report.expense_categories = expense_categories or []
    return report


def _make_mock_document(
    doc_type: str = "invoice",
    extracted_data: Dict[str, Any] = None,
    doc_date: date = None,
    filename: str = "Testdokument.pdf",
) -> MagicMock:
    """Helfer: Erstellt Mock-Dokument."""
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.document_type = doc_type
    doc.document_date = doc_date or date(2026, 6, 15)
    doc.original_filename = filename
    doc.created_at = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    doc.extracted_data = extracted_data or {}
    return doc


# =============================================================================
# TESTS: Report-Generierung (async)
# =============================================================================


class TestEURReportGeneration:
    """Tests fuer generate_eur_report."""

    @pytest.mark.asyncio
    async def test_leerer_zeitraum_ergibt_nullen(self, eur_service, company_id):
        """Report mit Nullsummen wenn keine Dokumente vorhanden."""
        # Interne Methoden mocken (umgeht Document.document_date Query)
        eur_service._get_income_items = AsyncMock(return_value=[])
        eur_service._get_expense_items = AsyncMock(return_value=[])

        report = await eur_service.generate_eur_report(
            company_id=company_id,
            fiscal_year=2026,
        )

        assert isinstance(report, EURReport)
        assert report.total_income == Decimal("0.00")
        assert report.total_expenses == Decimal("0.00")
        assert report.profit_loss == Decimal("0.00")
        assert report.is_profit is True  # 0 >= 0
        assert report.income_categories == []
        assert report.expense_categories == []
        assert report.fiscal_year == 2026

    @pytest.mark.asyncio
    async def test_report_mit_einnahme(self, eur_service, company_id):
        """Report mit einer Einnahme (Ausgangsrechnung)."""
        income_item = EURLineItem(
            document_id=uuid.uuid4(),
            category=IncomeCategory.SALES_SERVICES.value,
            description="Beratung",
            date=date(2026, 6, 15),
            net_amount=Decimal("5000.00"),
            vat_amount=Decimal("950.00"),
            gross_amount=Decimal("5950.00"),
            counterparty="Kunde GmbH",
            invoice_number="R-2026-001",
        )

        eur_service._get_income_items = AsyncMock(return_value=[income_item])
        eur_service._get_expense_items = AsyncMock(return_value=[])

        report = await eur_service.generate_eur_report(
            company_id=company_id,
            fiscal_year=2026,
        )

        assert report.total_income == Decimal("5000.00")
        assert report.total_expenses == Decimal("0.00")
        assert report.profit_loss == Decimal("5000.00")
        assert report.is_profit is True
        assert len(report.income_items) == 1

    @pytest.mark.asyncio
    async def test_report_mit_ausgabe(self, eur_service, company_id):
        """Report mit einer Ausgabe (Eingangsrechnung)."""
        expense_item = EURLineItem(
            document_id=uuid.uuid4(),
            category=ExpenseCategory.OTHER_EXPENSE.value,
            description="Bueroartikel",
            date=date(2026, 6, 15),
            net_amount=Decimal("2000.00"),
            vat_amount=Decimal("380.00"),
            gross_amount=Decimal("2380.00"),
            counterparty="Lieferant AG",
        )

        eur_service._get_income_items = AsyncMock(return_value=[])
        eur_service._get_expense_items = AsyncMock(return_value=[expense_item])

        report = await eur_service.generate_eur_report(
            company_id=company_id,
            fiscal_year=2026,
        )

        assert report.total_income == Decimal("0.00")
        assert report.total_expenses == Decimal("2000.00")
        assert report.profit_loss == Decimal("-2000.00")
        assert report.is_profit is False
        assert len(report.expense_items) == 1

    @pytest.mark.asyncio
    async def test_report_mit_gemischten_transaktionen(self, eur_service, company_id):
        """Report mit Einnahmen und Ausgaben berechnet Gewinn korrekt."""
        income_item = EURLineItem(
            document_id=uuid.uuid4(),
            category=IncomeCategory.SALES_SERVICES.value,
            description="Consulting",
            date=date(2026, 3, 1),
            net_amount=Decimal("10000.00"),
            vat_amount=Decimal("1900.00"),
            gross_amount=Decimal("11900.00"),
        )
        expense_item = EURLineItem(
            document_id=uuid.uuid4(),
            category=ExpenseCategory.GOODS_PURCHASE.value,
            description="Material",
            date=date(2026, 3, 15),
            net_amount=Decimal("3000.00"),
            vat_amount=Decimal("570.00"),
            gross_amount=Decimal("3570.00"),
        )

        eur_service._get_income_items = AsyncMock(return_value=[income_item])
        eur_service._get_expense_items = AsyncMock(return_value=[expense_item])

        report = await eur_service.generate_eur_report(
            company_id=company_id,
            fiscal_year=2026,
        )

        assert report.total_income == Decimal("10000.00")
        assert report.total_expenses == Decimal("3000.00")
        assert report.profit_loss == Decimal("7000.00")
        assert report.is_profit is True

    @pytest.mark.asyncio
    async def test_report_ohne_details(self, eur_service, company_id):
        """Report ohne include_details hat keine Einzelpositionen."""
        income_item = EURLineItem(
            document_id=uuid.uuid4(),
            category=IncomeCategory.SALES_SERVICES.value,
            description="Service",
            date=date(2026, 1, 1),
            net_amount=Decimal("1000.00"),
            vat_amount=Decimal("190.00"),
            gross_amount=Decimal("1190.00"),
        )

        eur_service._get_income_items = AsyncMock(return_value=[income_item])
        eur_service._get_expense_items = AsyncMock(return_value=[])

        report = await eur_service.generate_eur_report(
            company_id=company_id,
            fiscal_year=2026,
            include_details=False,
        )

        assert report.total_income == Decimal("1000.00")
        assert report.income_items == []


# =============================================================================
# TESTS: Kategorisierung
# =============================================================================


class TestCategorization:
    """Tests fuer Einnahmen/Ausgaben-Kategorisierung."""

    def test_einnahme_default_ist_dienstleistungen(self, eur_service):
        """Default-Einnahmekategorie ist Dienstleistungen."""
        doc = _make_mock_document(doc_type="invoice")
        category = eur_service._categorize_income(doc, {})
        assert category == IncomeCategory.SALES_SERVICES

    def test_einnahme_waren_aus_kategorie(self, eur_service):
        """Warenverkauf wird aus expliziter Kategorie erkannt."""
        doc = _make_mock_document(doc_type="invoice")
        category = eur_service._categorize_income(doc, {"category": "Warenverkauf"})
        assert category == IncomeCategory.SALES_GOODS

    def test_einnahme_waren_aus_dokumenttyp(self, eur_service):
        """Warenverkauf wird aus Dokumenttyp erkannt."""
        doc = _make_mock_document(doc_type="sales_invoice")
        category = eur_service._categorize_income(doc, {})
        assert category == IncomeCategory.SALES_GOODS

    def test_einnahme_zinsen(self, eur_service):
        """Zinsertraege werden erkannt."""
        doc = _make_mock_document(doc_type="invoice")
        category = eur_service._categorize_income(doc, {"category": "Zinsertraege"})
        assert category == IncomeCategory.INTEREST_INCOME

    def test_ausgabe_default_ist_sonstige(self, eur_service):
        """Default-Ausgabekategorie ist Sonstige Betriebsausgaben."""
        doc = _make_mock_document(doc_type="eingangsrechnung")
        category = eur_service._categorize_expense(doc, {})
        assert category == ExpenseCategory.OTHER_EXPENSE

    def test_ausgabe_miete_aus_kategorie(self, eur_service):
        """Miete wird aus expliziter Kategorie erkannt."""
        doc = _make_mock_document(doc_type="eingangsrechnung")
        category = eur_service._categorize_expense(doc, {"category": "Miete Buero"})
        assert category == ExpenseCategory.RENT

    def test_ausgabe_versicherung(self, eur_service):
        """Versicherung wird erkannt."""
        doc = _make_mock_document(doc_type="eingangsrechnung")
        category = eur_service._categorize_expense(doc, {"category": "Haftpflichtversicherung"})
        assert category == ExpenseCategory.INSURANCE

    def test_ausgabe_reisekosten(self, eur_service):
        """Reisekosten werden erkannt."""
        doc = _make_mock_document(doc_type="eingangsrechnung")
        category = eur_service._categorize_expense(doc, {"category": "Reisekosten"})
        assert category == ExpenseCategory.TRAVEL

    def test_ausgabe_software(self, eur_service):
        """Software-Kosten werden erkannt."""
        doc = _make_mock_document(doc_type="eingangsrechnung")
        category = eur_service._categorize_expense(doc, {"category": "Software-Abo"})
        assert category == ExpenseCategory.SOFTWARE

    def test_ausgabe_aus_lieferantenname(self, eur_service):
        """Kategorie wird aus Lieferantenname abgeleitet."""
        doc = _make_mock_document(doc_type="eingangsrechnung")
        category = eur_service._categorize_expense(doc, {"supplier_name": "Microsoft GmbH"})
        assert category == ExpenseCategory.SOFTWARE

    def test_ausgabe_telekom_ist_kommunikation(self, eur_service):
        """Telekom wird als Kommunikation kategorisiert."""
        doc = _make_mock_document(doc_type="eingangsrechnung")
        category = eur_service._categorize_expense(doc, {"supplier_name": "Deutsche Telekom AG"})
        assert category == ExpenseCategory.COMMUNICATION

    def test_ausgabe_tankstelle_ist_fahrzeug(self, eur_service):
        """Tankstelle wird als Fahrzeugkosten kategorisiert."""
        doc = _make_mock_document(doc_type="eingangsrechnung")
        category = eur_service._categorize_expense(doc, {"supplier_name": "Shell Deutschland"})
        assert category == ExpenseCategory.VEHICLE


# =============================================================================
# TESTS: Betragsextraktion
# =============================================================================


class TestEURAmountExtraction:
    """Tests fuer _extract_amount."""

    def test_extrahiert_normalen_betrag(self, eur_service):
        """Normaler Dezimalbetrag wird korrekt extrahiert."""
        data: Dict[str, Any] = {"net_amount": "1234.56"}
        amount = eur_service._extract_amount(data, ["net_amount"])
        assert amount == Decimal("1234.56")

    def test_extrahiert_deutsches_format(self, eur_service):
        """Deutsches Zahlenformat (Komma als Dezimaltrennzeichen)."""
        data: Dict[str, Any] = {"netto": "1234,56"}
        amount = eur_service._extract_amount(data, ["netto"])
        assert amount == Decimal("1234.56")

    def test_null_bei_fehlendem_schluessel(self, eur_service):
        """0.00 wenn kein Schluessel gefunden."""
        data: Dict[str, Any] = {}
        amount = eur_service._extract_amount(data, ["net_amount"])
        assert amount == Decimal("0.00")

    def test_null_bei_ungueltigem_wert(self, eur_service):
        """0.00 bei nicht-parsearem Wert."""
        data: Dict[str, Any] = {"net_amount": "N/A"}
        amount = eur_service._extract_amount(data, ["net_amount"])
        assert amount == Decimal("0.00")


# =============================================================================
# TESTS: to_dict() Serialisierung
# =============================================================================


class TestEURReportToDict:
    """Tests fuer die JSON-Serialisierung."""

    def test_to_dict_enthaelt_pflichtfelder(self, company_id):
        """to_dict() enthaelt alle Pflichtfelder."""
        report = _make_eur_report(
            company_id,
            total_income=Decimal("50000.00"),
            total_expenses=Decimal("20000.00"),
        )

        d = report.to_dict()

        assert d["company_id"] == str(company_id)
        assert d["fiscal_year"] == 2026
        assert d["period_start"] == "2026-01-01"
        assert d["period_end"] == "2026-12-31"
        assert d["status"] == "draft"
        assert d["income"]["total"] == 50000.0
        assert d["expenses"]["total"] == 20000.0
        assert d["profit_loss"] == 30000.0
        assert d["is_profit"] is True

    def test_to_dict_verlust(self, company_id):
        """to_dict() zeigt Verlust korrekt an."""
        report = _make_eur_report(
            company_id,
            total_income=Decimal("10000.00"),
            total_expenses=Decimal("25000.00"),
        )

        d = report.to_dict()
        assert d["profit_loss"] == -15000.0
        assert d["is_profit"] is False


# =============================================================================
# TESTS: Anlage EUeR
# =============================================================================


class TestAnlageEUR:
    """Tests fuer to_anlage_eur und to_anlage_eur_html."""

    def test_anlage_eur_zeilen_mapping(self, company_id):
        """Anlage EUeR hat korrekte Zeilen-Zuordnung."""
        report = _make_eur_report(
            company_id,
            total_income=Decimal("80000.00"),
            total_expenses=Decimal("30000.00"),
            income_categories=[
                EURCategorySummary(
                    category=IncomeCategory.SALES_SERVICES.value,
                    label="Dienstleistungen",
                    amount=Decimal("80000.00"),
                    count=10,
                ),
            ],
            expense_categories=[
                EURCategorySummary(
                    category=ExpenseCategory.RENT.value,
                    label="Miete/Pacht",
                    amount=Decimal("12000.00"),
                    count=12,
                ),
                EURCategorySummary(
                    category=ExpenseCategory.OTHER_EXPENSE.value,
                    label="Sonstige Betriebsausgaben",
                    amount=Decimal("18000.00"),
                    count=25,
                ),
            ],
        )

        anlage = report.to_anlage_eur()

        assert anlage["Jahr"] == 2026
        assert anlage["Zeile_12"] == 80000.0  # Dienstleistungen
        assert anlage["Zeile_18"] == 80000.0  # Summe Einnahmen
        assert anlage["Zeile_27"] == 12000.0  # Miete
        assert anlage["Zeile_40"] == 18000.0  # Sonstige
        assert anlage["Zeile_42"] == 30000.0  # Summe Ausgaben
        assert anlage["Zeile_43"] == 50000.0  # Gewinn

    def test_anlage_eur_leerer_report(self, company_id):
        """Leerer Report hat Nullwerte in allen Zeilen."""
        report = _make_eur_report(company_id)

        anlage = report.to_anlage_eur()

        assert anlage["Zeile_18"] == 0.0  # Summe Einnahmen
        assert anlage["Zeile_42"] == 0.0  # Summe Ausgaben
        assert anlage["Zeile_43"] == 0.0  # Gewinn/Verlust

    def test_html_export_enthaelt_pflichtfelder(self, company_id):
        """HTML-Export enthaelt Steuerjahr, Zeitraum und Betraege."""
        report = _make_eur_report(
            company_id,
            total_income=Decimal("100000.00"),
            total_expenses=Decimal("40000.00"),
            income_categories=[
                EURCategorySummary(
                    category=IncomeCategory.SALES_SERVICES.value,
                    label="Dienstleistungen",
                    amount=Decimal("100000.00"),
                    count=50,
                ),
            ],
        )

        html = report.to_anlage_eur_html()

        assert "2026" in html
        assert "Anlage E&Uuml;R" in html or "Anlage EUeR" in html
        assert "Betriebseinnahmen" in html
        assert "Betriebsausgaben" in html
        assert "Gewinn" in html or "Verlust" in html
        assert "EUR" in html
        assert "<!DOCTYPE html>" in html

    def test_html_export_zeigt_verlust(self, company_id):
        """HTML-Export zeigt 'Verlust' bei negativem Ergebnis."""
        report = _make_eur_report(
            company_id,
            total_income=Decimal("10000.00"),
            total_expenses=Decimal("30000.00"),
        )

        html = report.to_anlage_eur_html()

        assert "Verlust" in html

    def test_html_export_zeigt_gewinn(self, company_id):
        """HTML-Export zeigt 'Gewinn' bei positivem Ergebnis."""
        report = _make_eur_report(
            company_id,
            total_income=Decimal("50000.00"),
            total_expenses=Decimal("20000.00"),
        )

        html = report.to_anlage_eur_html()

        assert "Gewinn" in html

    def test_html_export_ist_druckbar(self, company_id):
        """HTML enthaelt Print-Styles und Druckbutton."""
        report = _make_eur_report(company_id)
        html = report.to_anlage_eur_html()

        assert "@media print" in html
        assert "window.print()" in html


# =============================================================================
# TESTS: Enums und Konstanten
# =============================================================================


class TestEURConstants:
    """Tests fuer Enums und Konstanten."""

    def test_income_category_werte(self):
        """IncomeCategory hat erwartete Werte."""
        assert IncomeCategory.SALES_GOODS.value == "sales_goods"
        assert IncomeCategory.SALES_SERVICES.value == "sales_services"
        assert IncomeCategory.OTHER_INCOME.value == "other_income"

    def test_expense_category_werte(self):
        """ExpenseCategory hat erwartete Werte."""
        assert ExpenseCategory.GOODS_PURCHASE.value == "goods_purchase"
        assert ExpenseCategory.RENT.value == "rent"
        assert ExpenseCategory.PERSONNEL.value == "personnel"
        assert ExpenseCategory.OTHER_EXPENSE.value == "other_expense"

    def test_category_mapping_vorhanden(self):
        """CATEGORY_MAPPING enthaelt Einnahmen und Ausgaben."""
        # Einnahmen
        assert "invoice" in CATEGORY_MAPPING
        assert "ausgangsrechnung" in CATEGORY_MAPPING

        # Ausgaben
        assert "eingangsrechnung" in CATEGORY_MAPPING
        assert "supplier_invoice" in CATEGORY_MAPPING
        assert "miete" in CATEGORY_MAPPING

    def test_eur_service_labels_deutsch(self):
        """Labels sind auf Deutsch."""
        assert EURService.INCOME_LABELS[IncomeCategory.SALES_GOODS] == "Warenverkauf"
        assert EURService.INCOME_LABELS[IncomeCategory.SALES_SERVICES] == "Dienstleistungen"
        assert EURService.EXPENSE_LABELS[ExpenseCategory.RENT] == "Miete/Pacht"
        assert EURService.EXPENSE_LABELS[ExpenseCategory.PERSONNEL] == "Personalkosten"


# =============================================================================
# TESTS: Datenklassen
# =============================================================================


class TestEURDataClasses:
    """Tests fuer die Datenstrukturen."""

    def test_eur_line_item_defaults(self):
        """EURLineItem hat sinnvolle Defaults."""
        item = EURLineItem(
            document_id=uuid.uuid4(),
            category="sales_services",
            description="Beratung",
            date=date(2026, 3, 1),
            net_amount=Decimal("1000.00"),
            vat_amount=Decimal("190.00"),
            gross_amount=Decimal("1190.00"),
        )
        assert item.counterparty is None
        assert item.invoice_number is None

    def test_eur_category_summary_defaults(self):
        """EURCategorySummary hat Null-Defaults."""
        summary = EURCategorySummary(
            category="rent",
            label="Miete/Pacht",
        )
        assert summary.amount == Decimal("0.00")
        assert summary.count == 0

    def test_eur_report_defaults(self):
        """EURReport hat sinnvolle Defaults."""
        report = EURReport(
            company_id=uuid.uuid4(),
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            generated_at=datetime.now(timezone.utc),
        )
        assert report.status == "draft"
        assert report.total_income == Decimal("0.00")
        assert report.total_expenses == Decimal("0.00")
        assert report.profit_loss == Decimal("0.00")
        assert report.is_profit is True
        assert report.deductible_vat == Decimal("0.00")
        assert report.income_items == []
        assert report.expense_items == []

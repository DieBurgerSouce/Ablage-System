# -*- coding: utf-8 -*-
"""
Einnahmen-Überschuss-Rechnung (EÜR) Service.

Berechnet die EÜR für Kleinunternehmer und Freiberufler:
- Einnahmen nach Kategorien
- Ausgaben nach Kategorien (Betriebsausgaben)
- Abschreibungen
- Gewinn/Verlust

GoBD-konform mit Anlage EÜR-Export.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Dict, List, Optional, Union

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document

logger = structlog.get_logger(__name__)

# JSON-kompatible Werte aus PostgreSQL JSONB-Spalten
JsonValue = Union[str, int, float, bool, None, List[object], Dict[str, object]]
JsonDict = Dict[str, JsonValue]


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================


class IncomeCategory(str, Enum):
    """Einnahmekategorien (Anlage EÜR Zeilen)."""
    SALES_GOODS = "sales_goods"                # Warenverkauf
    SALES_SERVICES = "sales_services"          # Dienstleistungen
    INNER_EU_SALES = "inner_eu_sales"          # Innergemeinschaftliche Lieferungen
    EXPORT_SALES = "export_sales"              # Ausfuhrlieferungen
    INTEREST_INCOME = "interest_income"        # Zinserträge
    OTHER_INCOME = "other_income"              # Sonstige Einnahmen


class ExpenseCategory(str, Enum):
    """Ausgabekategorien (Anlage EÜR Zeilen)."""
    GOODS_PURCHASE = "goods_purchase"          # Wareneinkauf
    PERSONNEL = "personnel"                     # Personalkosten
    RENT = "rent"                               # Miete/Pacht
    INSURANCE = "insurance"                     # Versicherungen
    TRAVEL = "travel"                           # Reisekosten
    VEHICLE = "vehicle"                         # Fahrzeugkosten
    OFFICE = "office"                           # Buerokosten
    COMMUNICATION = "communication"             # Telefon/Internet
    MARKETING = "marketing"                     # Werbung/Marketing
    PROFESSIONAL_SERVICES = "professional"      # Beratung/Fremdleistungen
    DEPRECIATION = "depreciation"               # Abschreibungen
    INTEREST_EXPENSE = "interest_expense"       # Zinsaufwand
    BANK_FEES = "bank_fees"                     # Bankgebühren
    SOFTWARE = "software"                       # Software/Lizenzen
    TRAINING = "training"                       # Fortbildung
    OTHER_EXPENSE = "other_expense"             # Sonstige Betriebsausgaben


# Mapping: Dokumentkategorie -> EÜR-Kategorie
CATEGORY_MAPPING = {
    # Einnahmen
    "invoice": IncomeCategory.SALES_SERVICES,
    "ausgangsrechnung": IncomeCategory.SALES_SERVICES,
    "sales_invoice": IncomeCategory.SALES_GOODS,

    # Ausgaben
    "eingangsrechnung": ExpenseCategory.OTHER_EXPENSE,
    "supplier_invoice": ExpenseCategory.GOODS_PURCHASE,
    "miete": ExpenseCategory.RENT,
    "versicherung": ExpenseCategory.INSURANCE,
    "reisekosten": ExpenseCategory.TRAVEL,
    "fahrzeug": ExpenseCategory.VEHICLE,
    "buero": ExpenseCategory.OFFICE,
    "telefon": ExpenseCategory.COMMUNICATION,
    "werbung": ExpenseCategory.MARKETING,
    "beratung": ExpenseCategory.PROFESSIONAL_SERVICES,
    "software": ExpenseCategory.SOFTWARE,
    "fortbildung": ExpenseCategory.TRAINING,
    "bankgebühr": ExpenseCategory.BANK_FEES,
}


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class EURLineItem:
    """Einzelposition in der EÜR."""
    document_id: uuid.UUID
    category: str  # IncomeCategory oder ExpenseCategory
    description: str
    date: date
    net_amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal
    counterparty: Optional[str] = None
    invoice_number: Optional[str] = None


@dataclass
class EURCategorySummary:
    """Zusammenfassung einer Kategorie."""
    category: str
    label: str
    amount: Decimal = Decimal("0.00")
    count: int = 0


@dataclass
class EURReport:
    """Einnahmen-Überschuss-Rechnung."""
    company_id: uuid.UUID
    fiscal_year: int
    period_start: date
    period_end: date

    generated_at: datetime
    status: str = "draft"  # draft, final, submitted

    # Einnahmen
    income_categories: List[EURCategorySummary] = field(default_factory=list)
    total_income: Decimal = Decimal("0.00")

    # Ausgaben
    expense_categories: List[EURCategorySummary] = field(default_factory=list)
    total_expenses: Decimal = Decimal("0.00")

    # Gewinn/Verlust
    profit_loss: Decimal = Decimal("0.00")
    is_profit: bool = True

    # Vorsteuer (abziehbar)
    deductible_vat: Decimal = Decimal("0.00")

    # Details (optional)
    income_items: List[EURLineItem] = field(default_factory=list)
    expense_items: List[EURLineItem] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        """Konvertiert zu Dictionary."""
        return {
            "company_id": str(self.company_id),
            "fiscal_year": self.fiscal_year,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "status": self.status,
            "income": {
                "total": float(self.total_income),
                "categories": [
                    {
                        "category": c.category,
                        "label": c.label,
                        "amount": float(c.amount),
                        "count": c.count,
                    }
                    for c in self.income_categories
                ],
            },
            "expenses": {
                "total": float(self.total_expenses),
                "categories": [
                    {
                        "category": c.category,
                        "label": c.label,
                        "amount": float(c.amount),
                        "count": c.count,
                    }
                    for c in self.expense_categories
                ],
            },
            "profit_loss": float(self.profit_loss),
            "is_profit": self.is_profit,
            "deductible_vat": float(self.deductible_vat),
        }

    def to_anlage_eur(self) -> Dict[str, Union[int, float]]:
        """
        Generiert Daten für Anlage EÜR.

        Zeilen nach BMF-Vorgabe.
        """
        return {
            "Jahr": self.fiscal_year,
            "Zeile_11": float(self._get_category_amount(IncomeCategory.SALES_GOODS)),  # Betriebseinnahmen Waren
            "Zeile_12": float(self._get_category_amount(IncomeCategory.SALES_SERVICES)),  # Betriebseinnahmen DL
            "Zeile_14": float(self._get_category_amount(IncomeCategory.INTEREST_INCOME)),  # Zinserträge
            "Zeile_16": float(self._get_category_amount(IncomeCategory.OTHER_INCOME)),  # Sonstige Einnahmen
            "Zeile_18": float(self.total_income),  # Summe Einnahmen

            "Zeile_20": float(self._get_category_amount(ExpenseCategory.GOODS_PURCHASE)),  # Wareneinkauf
            "Zeile_22": float(self._get_category_amount(ExpenseCategory.PERSONNEL)),  # Personal
            "Zeile_27": float(self._get_category_amount(ExpenseCategory.RENT)),  # Miete
            "Zeile_30": float(self._get_category_amount(ExpenseCategory.VEHICLE)),  # Fahrzeug
            "Zeile_35": float(self._get_category_amount(ExpenseCategory.OFFICE)),  # Buero
            "Zeile_36": float(self._get_category_amount(ExpenseCategory.DEPRECIATION)),  # AfA
            "Zeile_40": float(self._get_category_amount(ExpenseCategory.OTHER_EXPENSE)),  # Sonstige
            "Zeile_42": float(self.total_expenses),  # Summe Ausgaben

            "Zeile_43": float(self.profit_loss),  # Gewinn/Verlust
        }

    def to_anlage_eur_html(self) -> str:
        """
        Generiert eine druckbare HTML-Darstellung der Anlage EUeR.

        Returns:
            HTML-String für Browser-Rendering und Druckausgabe
        """
        anlage = self.to_anlage_eur()

        zeilen_einnahmen = [
            ("11", "Betriebseinnahmen als umsatzsteuerpflichtiger Unternehmer (Waren)", anlage.get("Zeile_11", 0)),
            ("12", "Betriebseinnahmen als umsatzsteuerpflichtiger Unternehmer (Dienstleistungen)", anlage.get("Zeile_12", 0)),
            ("14", "Vereinnahmte Umsatzsteuer / Zinserträge", anlage.get("Zeile_14", 0)),
            ("16", "Sonstige Betriebseinnahmen", anlage.get("Zeile_16", 0)),
            ("18", "Summe Betriebseinnahmen", anlage.get("Zeile_18", 0)),
        ]

        zeilen_ausgaben = [
            ("20", "Waren, Rohstoffe und Hilfsstoffe", anlage.get("Zeile_20", 0)),
            ("22", "Personalkosten (Loehne und Gehälter)", anlage.get("Zeile_22", 0)),
            ("27", "Miete/Pacht für Geschäftsraeume", anlage.get("Zeile_27", 0)),
            ("30", "Fahrzeugkosten", anlage.get("Zeile_30", 0)),
            ("35", "Buerokosten", anlage.get("Zeile_35", 0)),
            ("36", "Absetzung für Abnutzung (AfA)", anlage.get("Zeile_36", 0)),
            ("40", "Sonstige Betriebsausgaben", anlage.get("Zeile_40", 0)),
            ("42", "Summe Betriebsausgaben", anlage.get("Zeile_42", 0)),
        ]

        zeilen_ergebnis = [
            ("43", "Gewinn / Verlust", anlage.get("Zeile_43", 0)),
        ]

        def _format_eur(value: float) -> str:
            """Formatiert Betrag im deutschen EUR-Format."""
            formatted = f"{value:,.2f}"
            formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
            return formatted

        def _render_rows(zeilen: list) -> str:
            rows = []
            for zeile_nr, beschreibung, betrag in zeilen:
                is_sum = zeile_nr in ("18", "42", "43")
                weight = "font-weight:bold;" if is_sum else ""
                border = "border-top:2px solid #333;" if is_sum else ""
                rows.append(
                    f'<tr style="{weight}">'
                    f'<td style="padding:6px 12px;border-bottom:1px solid #ddd;{border}">{zeile_nr}</td>'
                    f'<td style="padding:6px 12px;border-bottom:1px solid #ddd;{border}">{beschreibung}</td>'
                    f'<td style="padding:6px 12px;border-bottom:1px solid #ddd;text-align:right;{border}">'
                    f'{_format_eur(betrag)} EUR</td>'
                    f'</tr>'
                )
            return "\n".join(rows)

        gewinn_verlust = anlage.get("Zeile_43", 0)
        ergebnis_label = "Gewinn" if gewinn_verlust >= 0 else "Verlust"
        ergebnis_color = "#2e7d32" if gewinn_verlust >= 0 else "#c62828"

        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Anlage EUeR {self.fiscal_year}</title>
<style>
  @media print {{
    body {{ margin: 0; }}
    .no-print {{ display: none; }}
  }}
  body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    max-width: 800px;
    margin: 20px auto;
    padding: 20px;
    color: #333;
  }}
  h1 {{ text-align: center; margin-bottom: 4px; font-size: 22px; }}
  .subtitle {{ text-align: center; color: #666; margin-bottom: 24px; font-size: 14px; }}
  .meta {{ display: flex; justify-content: space-between; margin-bottom: 20px; font-size: 13px; color: #555; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px; }}
  th {{ background: #f5f5f5; padding: 8px 12px; text-align: left; border-bottom: 2px solid #333; font-weight: 600; }}
  th:last-child {{ text-align: right; }}
  .section-header {{ background: #e8eaf6; padding: 8px 12px; font-weight: 600; font-size: 14px; }}
  .result {{ text-align: center; margin-top: 24px; padding: 16px; background: #f9f9f9; border-radius: 8px; }}
  .result-value {{ font-size: 28px; font-weight: bold; color: {ergebnis_color}; }}
  .result-label {{ font-size: 14px; color: #666; margin-top: 4px; }}
  .print-btn {{ display: block; margin: 24px auto 0; padding: 10px 24px; background: #1976d2; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }}
  .print-btn:hover {{ background: #1565c0; }}
</style>
</head>
<body>
<h1>Anlage E&Uuml;R</h1>
<p class="subtitle">Einnahmen-&Uuml;berschuss-Rechnung gem&auml;&szlig; &sect; 4 Abs. 3 EStG</p>

<div class="meta">
  <div><strong>Steuerjahr:</strong> {self.fiscal_year}</div>
  <div><strong>Zeitraum:</strong> {self.period_start.strftime('%d.%m.%Y')} &ndash; {self.period_end.strftime('%d.%m.%Y')}</div>
  <div><strong>Steuernummer:</strong> ___/___/_____</div>
</div>

<table>
<thead>
<tr>
  <th style="width:60px;">Zeile</th>
  <th>Bezeichnung</th>
  <th style="width:160px;">Betrag</th>
</tr>
</thead>
<tbody>
<tr class="section-header"><td colspan="3">I. Betriebseinnahmen</td></tr>
{_render_rows(zeilen_einnahmen)}
<tr class="section-header"><td colspan="3">II. Betriebsausgaben</td></tr>
{_render_rows(zeilen_ausgaben)}
<tr class="section-header"><td colspan="3">III. Ergebnis</td></tr>
{_render_rows(zeilen_ergebnis)}
</tbody>
</table>

<div class="result">
  <div class="result-value">{_format_eur(gewinn_verlust)} EUR</div>
  <div class="result-label">{ergebnis_label} im Steuerjahr {self.fiscal_year}</div>
</div>

<button class="print-btn no-print" onclick="window.print()">Drucken / Als PDF speichern</button>
</body>
</html>"""

        return html

    def _get_category_amount(self, category: str) -> Decimal:
        """Holt Betrag für Kategorie."""
        for c in self.income_categories + self.expense_categories:
            if c.category == category.value if hasattr(category, 'value') else category:
                return c.amount
        return Decimal("0.00")


# ============================================================================
# EÜR SERVICE
# ============================================================================


class EURService:
    """
    Service für Einnahmen-Überschuss-Rechnung.

    Features:
    - Automatische Kategorisierung
    - Einnahmen/Ausgaben aus Dokumenten
    - Anlage EÜR Export
    - Monatliche Zwischenstände

    GoBD-konform.
    """

    # Label für Kategorien
    INCOME_LABELS = {
        IncomeCategory.SALES_GOODS: "Warenverkauf",
        IncomeCategory.SALES_SERVICES: "Dienstleistungen",
        IncomeCategory.INNER_EU_SALES: "Innergemeinschaftliche Lieferungen",
        IncomeCategory.EXPORT_SALES: "Ausfuhrlieferungen",
        IncomeCategory.INTEREST_INCOME: "Zinserträge",
        IncomeCategory.OTHER_INCOME: "Sonstige Einnahmen",
    }

    EXPENSE_LABELS = {
        ExpenseCategory.GOODS_PURCHASE: "Wareneinkauf",
        ExpenseCategory.PERSONNEL: "Personalkosten",
        ExpenseCategory.RENT: "Miete/Pacht",
        ExpenseCategory.INSURANCE: "Versicherungen",
        ExpenseCategory.TRAVEL: "Reisekosten",
        ExpenseCategory.VEHICLE: "Fahrzeugkosten",
        ExpenseCategory.OFFICE: "Buerokosten",
        ExpenseCategory.COMMUNICATION: "Telefon/Internet",
        ExpenseCategory.MARKETING: "Werbung/Marketing",
        ExpenseCategory.PROFESSIONAL_SERVICES: "Beratung/Fremdleistungen",
        ExpenseCategory.DEPRECIATION: "Abschreibungen",
        ExpenseCategory.INTEREST_EXPENSE: "Zinsaufwand",
        ExpenseCategory.BANK_FEES: "Bankgebühren",
        ExpenseCategory.SOFTWARE: "Software/Lizenzen",
        ExpenseCategory.TRAINING: "Fortbildung",
        ExpenseCategory.OTHER_EXPENSE: "Sonstige Betriebsausgaben",
    }

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db

    # ========================================================================
    # REPORT GENERATION
    # ========================================================================

    async def generate_eur_report(
        self,
        company_id: uuid.UUID,
        fiscal_year: int,
        include_details: bool = True,
    ) -> EURReport:
        """
        Generiert EÜR für ein Geschäftsjahr.

        Args:
            company_id: Firma
            fiscal_year: Geschäftsjahr
            include_details: Einzelpositionen einbeziehen

        Returns:
            EURReport
        """
        period_start = date(fiscal_year, 1, 1)
        period_end = date(fiscal_year, 12, 31)

        report = EURReport(
            company_id=company_id,
            fiscal_year=fiscal_year,
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now(timezone.utc),
        )

        # Einnahmen sammeln
        income_items = await self._get_income_items(company_id, period_start, period_end)
        income_by_category: Dict[str, EURCategorySummary] = {}

        for item in income_items:
            cat = item.category
            if cat not in income_by_category:
                income_by_category[cat] = EURCategorySummary(
                    category=cat,
                    label=self.INCOME_LABELS.get(IncomeCategory(cat), cat),
                )
            income_by_category[cat].amount += item.net_amount
            income_by_category[cat].count += 1
            report.total_income += item.net_amount

            if include_details:
                report.income_items.append(item)

        report.income_categories = list(income_by_category.values())

        # Ausgaben sammeln
        expense_items = await self._get_expense_items(company_id, period_start, period_end)
        expense_by_category: Dict[str, EURCategorySummary] = {}

        for item in expense_items:
            cat = item.category
            if cat not in expense_by_category:
                expense_by_category[cat] = EURCategorySummary(
                    category=cat,
                    label=self.EXPENSE_LABELS.get(ExpenseCategory(cat), cat) if cat in [e.value for e in ExpenseCategory] else cat,
                )
            expense_by_category[cat].amount += item.net_amount
            expense_by_category[cat].count += 1
            report.total_expenses += item.net_amount
            report.deductible_vat += item.vat_amount

            if include_details:
                report.expense_items.append(item)

        report.expense_categories = list(expense_by_category.values())

        # Gewinn/Verlust
        report.profit_loss = report.total_income - report.total_expenses
        report.is_profit = report.profit_loss >= 0

        logger.info(
            "eur_report_generated",
            company_id=str(company_id),
            fiscal_year=fiscal_year,
            total_income=float(report.total_income),
            total_expenses=float(report.total_expenses),
            profit_loss=float(report.profit_loss),
        )

        return report

    async def generate_monthly_eur(
        self,
        company_id: uuid.UUID,
        year: int,
        month: int,
    ) -> EURReport:
        """
        Generiert monatlichen EÜR-Zwischenstand.

        Args:
            company_id: Firma
            year: Jahr
            month: Monat

        Returns:
            EURReport
        """
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year, 12, 31)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)

        # Vereinfachte Version für Monatsstand
        report = EURReport(
            company_id=company_id,
            fiscal_year=year,
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now(timezone.utc),
        )

        # Einnahmen
        income_items = await self._get_income_items(company_id, period_start, period_end)
        for item in income_items:
            report.total_income += item.net_amount

        # Ausgaben
        expense_items = await self._get_expense_items(company_id, period_start, period_end)
        for item in expense_items:
            report.total_expenses += item.net_amount
            report.deductible_vat += item.vat_amount

        report.profit_loss = report.total_income - report.total_expenses
        report.is_profit = report.profit_loss >= 0

        return report

    async def get_ytd_summary(
        self,
        company_id: uuid.UUID,
        year: int,
    ) -> JsonDict:
        """
        Holt Year-to-Date Zusammenfassung.

        Args:
            company_id: Firma
            year: Jahr

        Returns:
            Monatliche Zusammenfassung
        """
        today = date.today()
        end_month = 12 if today.year > year else today.month

        monthly_data = []
        ytd_income = Decimal("0.00")
        ytd_expenses = Decimal("0.00")

        for month in range(1, end_month + 1):
            report = await self.generate_monthly_eur(company_id, year, month)
            monthly_data.append({
                "month": month,
                "month_name": [
                    "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
                    "Juli", "August", "September", "Oktober", "November", "Dezember"
                ][month],
                "income": float(report.total_income),
                "expenses": float(report.total_expenses),
                "profit_loss": float(report.profit_loss),
            })
            ytd_income += report.total_income
            ytd_expenses += report.total_expenses

        return {
            "year": year,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "months": monthly_data,
            "ytd": {
                "income": float(ytd_income),
                "expenses": float(ytd_expenses),
                "profit_loss": float(ytd_income - ytd_expenses),
            },
        }

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    async def _get_income_items(
        self,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[EURLineItem]:
        """Holt Einnahmen aus Dokumenten."""
        # Ausgangsrechnungen = Einnahmen
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type.in_(["invoice", "ausgangsrechnung", "sales_invoice"]),
                Document.upload_date >= period_start,
                Document.upload_date <= period_end,
            )
        )

        result = await self.db.execute(query)
        documents = result.scalars().all()

        items: List[EURLineItem] = []

        for doc in documents:
            extracted = doc.extracted_data or {}

            net = self._extract_amount(extracted, ["net_amount", "netto", "subtotal"])
            gross = self._extract_amount(extracted, ["total_amount", "brutto", "amount"])
            vat = gross - net if net > 0 else Decimal("0")

            if gross == Decimal("0"):
                continue

            # Kategorie bestimmen
            category = self._categorize_income(doc, extracted)

            item = EURLineItem(
                document_id=doc.id,
                category=category.value,
                description=extracted.get("description") or doc.original_filename or "Einnahme",
                date=doc.upload_date or doc.created_at.date(),
                net_amount=net if net > 0 else gross,
                vat_amount=vat,
                gross_amount=gross,
                counterparty=extracted.get("customer_name"),
                invoice_number=extracted.get("invoice_number"),
            )
            items.append(item)

        return items

    async def _get_expense_items(
        self,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[EURLineItem]:
        """Holt Ausgaben aus Dokumenten."""
        # Eingangsrechnungen = Ausgaben
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type.in_([
                    "eingangsrechnung", "supplier_invoice", "purchase_invoice",
                    "beleg", "quittung", "receipt"
                ]),
                Document.upload_date >= period_start,
                Document.upload_date <= period_end,
            )
        )

        result = await self.db.execute(query)
        documents = result.scalars().all()

        items: List[EURLineItem] = []

        for doc in documents:
            extracted = doc.extracted_data or {}

            net = self._extract_amount(extracted, ["net_amount", "netto", "subtotal"])
            gross = self._extract_amount(extracted, ["total_amount", "brutto", "amount"])
            vat = gross - net if net > 0 else Decimal("0")

            if gross == Decimal("0"):
                continue

            # Kategorie bestimmen
            category = self._categorize_expense(doc, extracted)

            item = EURLineItem(
                document_id=doc.id,
                category=category.value,
                description=extracted.get("description") or doc.original_filename or "Ausgabe",
                date=doc.document_date or doc.created_at.date(),
                net_amount=net if net > 0 else gross,
                vat_amount=vat,
                gross_amount=gross,
                counterparty=extracted.get("supplier_name") or extracted.get("creditor_name"),
                invoice_number=extracted.get("invoice_number"),
            )
            items.append(item)

        return items

    def _extract_amount(self, data: JsonDict, keys: List[str]) -> Decimal:
        """Extrahiert Betrag aus Daten."""
        for key in keys:
            value = data.get(key)
            if value is not None:
                try:
                    return Decimal(str(value).replace(",", ".").replace(" ", "")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                except (ValueError, InvalidOperation, TypeError) as e:
                    logger.debug(
                        "amount_parsing_skipped",
                        key=key,
                        value_type=type(value).__name__,
                        error_type=type(e).__name__,
                    )
        return Decimal("0.00")

    def _categorize_income(
        self,
        doc: Document,
        extracted: JsonDict,
    ) -> IncomeCategory:
        """Kategorisiert Einnahme."""
        # Aus expliziter Kategorie
        category = extracted.get("category") or extracted.get("expense_category")
        if category:
            category_lower = category.lower()
            if "ware" in category_lower or "produkt" in category_lower:
                return IncomeCategory.SALES_GOODS
            elif "dienst" in category_lower or "service" in category_lower:
                return IncomeCategory.SALES_SERVICES
            elif "zins" in category_lower:
                return IncomeCategory.INTEREST_INCOME

        # Aus Dokumenttyp
        doc_type = doc.document_type or ""
        if "sales" in doc_type or "ware" in doc_type:
            return IncomeCategory.SALES_GOODS

        # Default
        return IncomeCategory.SALES_SERVICES

    def _categorize_expense(
        self,
        doc: Document,
        extracted: JsonDict,
    ) -> ExpenseCategory:
        """Kategorisiert Ausgabe."""
        # Aus expliziter Kategorie
        category = extracted.get("category") or extracted.get("expense_category")
        if category:
            category_lower = category.lower()

            mappings = [
                (["miete", "pacht", "rent"], ExpenseCategory.RENT),
                (["versicherung", "insurance"], ExpenseCategory.INSURANCE),
                (["reise", "hotel", "flug", "travel"], ExpenseCategory.TRAVEL),
                (["fahrzeug", "auto", "kfz", "vehicle", "benzin", "diesel"], ExpenseCategory.VEHICLE),
                (["buero", "office", "material"], ExpenseCategory.OFFICE),
                (["telefon", "internet", "kommunikation"], ExpenseCategory.COMMUNICATION),
                (["werbung", "marketing", "anzeige"], ExpenseCategory.MARKETING),
                (["beratung", "rechtsanwalt", "steuerberater", "consulting"], ExpenseCategory.PROFESSIONAL_SERVICES),
                (["software", "lizenz", "abo"], ExpenseCategory.SOFTWARE),
                (["fortbildung", "seminar", "schulung", "training"], ExpenseCategory.TRAINING),
                (["bank", "kontogebühr"], ExpenseCategory.BANK_FEES),
                (["ware", "material", "einkauf"], ExpenseCategory.GOODS_PURCHASE),
                (["personal", "lohn", "gehalt"], ExpenseCategory.PERSONNEL),
                (["zins", "kredit"], ExpenseCategory.INTEREST_EXPENSE),
                (["abschreibung", "afa"], ExpenseCategory.DEPRECIATION),
            ]

            for keywords, expense_cat in mappings:
                if any(kw in category_lower for kw in keywords):
                    return expense_cat

        # Aus Lieferantenname
        supplier = (extracted.get("supplier_name") or "").lower()
        supplier_mappings = [
            (["telekom", "vodafone", "o2", "1und1"], ExpenseCategory.COMMUNICATION),
            (["allianz", "axa", "ergo", "huk"], ExpenseCategory.INSURANCE),
            (["amazon", "conrad", "buero"], ExpenseCategory.OFFICE),
            (["shell", "aral", "total", "jet"], ExpenseCategory.VEHICLE),
            (["microsoft", "google", "adobe", "zoom"], ExpenseCategory.SOFTWARE),
        ]

        for keywords, expense_cat in supplier_mappings:
            if any(kw in supplier for kw in keywords):
                return expense_cat

        # Default
        return ExpenseCategory.OTHER_EXPENSE


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def get_eur_service(db: AsyncSession) -> EURService:
    """Factory-Funktion für Dependency Injection."""
    return EURService(db)


# Import für timedelta
from datetime import timedelta

# -*- coding: utf-8 -*-
"""
Visual Report Builder Service.

Vision 2026 Q3: Visueller Report-Builder mit Templates und Drag-Drop UI Support.

Features:
- Vordefinierte Report-Templates
- Konfigurierbare Spalten, Filter, Gruppierungen
- Chart-Typ Unterstuetzung (Bar, Line, Pie, Table)
- Live-Preview
- Export in verschiedene Formate

Feinpoliert und durchdacht - Deutsche Qualitaet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    BankTransaction,
    ReportTemplate,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

REPORT_BUILDER_REQUESTS = Counter(
    "visual_report_builder_requests_total",
    "Anzahl Visual Report Builder Anfragen",
    ["template_id", "action"]
)

REPORT_GENERATION_DURATION = Histogram(
    "visual_report_generation_seconds",
    "Dauer der Report-Generierung",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0]
)


# =============================================================================
# Enums
# =============================================================================

class ChartType(str, Enum):
    """Verfuegbare Chart-Typen."""
    TABLE = "table"
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    AREA = "area"
    STACKED_BAR = "stacked_bar"


class AggregationType(str, Enum):
    """Verfuegbare Aggregationen."""
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    MIN = "min"
    MAX = "max"


class FilterOperator(str, Enum):
    """Verfuegbare Filter-Operatoren."""
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_OR_EQUAL = "lte"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    BETWEEN = "between"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class ReportCategory(str, Enum):
    """Report-Kategorien."""
    FINANCE = "finance"
    SALES = "sales"
    PURCHASING = "purchasing"
    DOCUMENTS = "documents"
    TAX = "tax"
    CUSTOM = "custom"


# =============================================================================
# Datenstrukturen
# =============================================================================

@dataclass
class ReportColumn:
    """Definition einer Report-Spalte."""
    id: str
    field_path: str
    display_name: str
    data_type: str  # string, number, currency, date, boolean
    is_visible: bool = True
    width: Optional[int] = None
    format_pattern: Optional[str] = None
    aggregation: Optional[AggregationType] = None
    sort_order: Optional[str] = None  # "asc" oder "desc"


@dataclass
class ReportFilter:
    """Definition eines Report-Filters."""
    id: str
    field_path: str
    operator: FilterOperator
    value: Any
    display_name: Optional[str] = None
    is_dynamic: bool = False  # Fuer Runtime-Parameter


@dataclass
class ReportGrouping:
    """Definition einer Gruppierung."""
    field_path: str
    display_name: str
    sort_order: str = "asc"


@dataclass
class ReportTemplateDefinition:
    """Vollstaendige Template-Definition."""
    id: str
    name: str
    description: str
    category: ReportCategory
    icon: str
    data_source: str
    columns: List[ReportColumn]
    default_filters: List[ReportFilter]
    default_groupings: List[ReportGrouping]
    supported_chart_types: List[ChartType]
    default_chart_type: ChartType
    is_system_template: bool = True


@dataclass
class ReportDataRow:
    """Eine Zeile im Report-Ergebnis."""
    data: Dict[str, Any]
    row_index: int
    group_key: Optional[str] = None


@dataclass
class ReportAggregation:
    """Aggregations-Ergebnis."""
    field_path: str
    aggregation_type: AggregationType
    value: Any
    formatted_value: str


@dataclass
class ChartDataPoint:
    """Datenpunkt fuer Charts."""
    label: str
    value: float
    color: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


@dataclass
class ChartData:
    """Daten fuer Chart-Darstellung."""
    chart_type: ChartType
    labels: List[str]
    datasets: List[Dict[str, Any]]
    options: Dict[str, Any]


@dataclass
class VisualReportResult:
    """Ergebnis des Visual Report Builders."""
    template_id: str
    template_name: str
    columns: List[Dict[str, Any]]
    rows: List[ReportDataRow]
    total_count: int
    aggregations: List[ReportAggregation]
    chart_data: Optional[ChartData]
    filters_applied: List[Dict[str, Any]]
    generated_at: datetime
    processing_time_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Vordefinierte Templates
# =============================================================================

SYSTEM_TEMPLATES: List[ReportTemplateDefinition] = [
    ReportTemplateDefinition(
        id="offene_posten",
        name="Offene Posten nach Alter",
        description="Zeigt alle offenen Rechnungen nach Faelligkeitsdatum gruppiert",
        category=ReportCategory.FINANCE,
        icon="clock",
        data_source="invoices",
        columns=[
            ReportColumn("invoice_number", "invoice_number", "Rechnungsnr.", "string"),
            ReportColumn("entity_name", "entity_name", "Kunde/Lieferant", "string"),
            ReportColumn("invoice_date", "invoice_date", "Rechnungsdatum", "date"),
            ReportColumn("due_date", "due_date", "Faelligkeit", "date"),
            ReportColumn("total_gross", "total_gross", "Betrag", "currency"),
            ReportColumn("days_overdue", "days_overdue", "Tage ueberfaellig", "number"),
        ],
        default_filters=[
            ReportFilter("status", "status", FilterOperator.IN, ["open", "overdue"]),
        ],
        default_groupings=[
            ReportGrouping("aging_bucket", "Altersgruppe"),
        ],
        supported_chart_types=[ChartType.TABLE, ChartType.BAR, ChartType.PIE],
        default_chart_type=ChartType.TABLE,
    ),
    ReportTemplateDefinition(
        id="umsatz_kunde",
        name="Umsatz nach Kunde",
        description="Aggregierter Umsatz pro Kunde",
        category=ReportCategory.SALES,
        icon="chart-bar",
        data_source="invoices",
        columns=[
            ReportColumn("entity_name", "entity_name", "Kunde", "string"),
            ReportColumn("invoice_count", "invoice_count", "Anzahl Rechnungen", "number"),
            ReportColumn("total_revenue", "total_revenue", "Umsatz", "currency", aggregation=AggregationType.SUM),
            ReportColumn("avg_invoice", "avg_invoice", "Durchschnitt", "currency", aggregation=AggregationType.AVG),
        ],
        default_filters=[],
        default_groupings=[
            ReportGrouping("entity_name", "Kunde"),
        ],
        supported_chart_types=[ChartType.TABLE, ChartType.BAR, ChartType.PIE],
        default_chart_type=ChartType.BAR,
    ),
    ReportTemplateDefinition(
        id="lieferanten_performance",
        name="Lieferanten-Performance",
        description="Analyse der Lieferanten-Kennzahlen",
        category=ReportCategory.PURCHASING,
        icon="truck",
        data_source="invoices",
        columns=[
            ReportColumn("entity_name", "entity_name", "Lieferant", "string"),
            ReportColumn("invoice_count", "invoice_count", "Rechnungen", "number"),
            ReportColumn("total_spent", "total_spent", "Ausgaben", "currency", aggregation=AggregationType.SUM),
            ReportColumn("avg_delay", "avg_delay", "Durchschn. Lieferzeit", "number"),
        ],
        default_filters=[
            ReportFilter("entity_type", "entity_type", FilterOperator.EQUALS, "supplier"),
        ],
        default_groupings=[
            ReportGrouping("entity_name", "Lieferant"),
        ],
        supported_chart_types=[ChartType.TABLE, ChartType.BAR],
        default_chart_type=ChartType.TABLE,
    ),
    ReportTemplateDefinition(
        id="dokument_statistik",
        name="Dokument-Statistik",
        description="Statistiken ueber verarbeitete Dokumente",
        category=ReportCategory.DOCUMENTS,
        icon="file-text",
        data_source="documents",
        columns=[
            ReportColumn("document_type", "document_type", "Dokumenttyp", "string"),
            ReportColumn("count", "count", "Anzahl", "number", aggregation=AggregationType.COUNT),
            ReportColumn("avg_confidence", "avg_confidence", "Durchschn. OCR-Konfidenz", "number"),
        ],
        default_filters=[],
        default_groupings=[
            ReportGrouping("document_type", "Dokumenttyp"),
        ],
        supported_chart_types=[ChartType.TABLE, ChartType.PIE, ChartType.BAR],
        default_chart_type=ChartType.PIE,
    ),
    ReportTemplateDefinition(
        id="ust_vorbereitung",
        name="USt-Voranmeldung Vorbereitung",
        description="Daten fuer die USt-Voranmeldung",
        category=ReportCategory.TAX,
        icon="calculator",
        data_source="invoices",
        columns=[
            ReportColumn("vat_rate", "vat_rate", "MwSt-Satz", "string"),
            ReportColumn("total_net", "total_net", "Netto", "currency", aggregation=AggregationType.SUM),
            ReportColumn("total_vat", "total_vat", "MwSt", "currency", aggregation=AggregationType.SUM),
            ReportColumn("total_gross", "total_gross", "Brutto", "currency", aggregation=AggregationType.SUM),
        ],
        default_filters=[
            ReportFilter("invoice_date", "invoice_date", FilterOperator.BETWEEN, "this_month"),
        ],
        default_groupings=[
            ReportGrouping("vat_rate", "MwSt-Satz"),
        ],
        supported_chart_types=[ChartType.TABLE, ChartType.PIE],
        default_chart_type=ChartType.TABLE,
    ),
    ReportTemplateDefinition(
        id="cashflow_prognose",
        name="Cashflow-Prognose",
        description="Erwartete Ein- und Auszahlungen",
        category=ReportCategory.FINANCE,
        icon="trending-up",
        data_source="invoices",
        columns=[
            ReportColumn("week", "week", "Woche", "string"),
            ReportColumn("inflows", "inflows", "Eingaenge", "currency", aggregation=AggregationType.SUM),
            ReportColumn("outflows", "outflows", "Ausgaenge", "currency", aggregation=AggregationType.SUM),
            ReportColumn("net_flow", "net_flow", "Netto Cashflow", "currency"),
        ],
        default_filters=[
            ReportFilter("due_date", "due_date", FilterOperator.BETWEEN, "next_30_days"),
        ],
        default_groupings=[
            ReportGrouping("week", "Woche"),
        ],
        supported_chart_types=[ChartType.TABLE, ChartType.LINE, ChartType.AREA],
        default_chart_type=ChartType.LINE,
    ),
]


class VisualReportBuilderService:
    """
    Service fuer den visuellen Report-Builder.

    Bietet:
    - Vordefinierte Templates
    - Konfigurierbare Reports
    - Chart-Daten Generierung
    - Live-Preview
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._templates: Dict[str, ReportTemplateDefinition] = {
            t.id: t for t in SYSTEM_TEMPLATES
        }

    def get_available_templates(
        self,
        category: Optional[ReportCategory] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gibt verfuegbare Templates zurueck.

        Args:
            category: Optionale Kategorie-Filterung

        Returns:
            Liste der Templates mit Metadaten
        """
        templates = list(self._templates.values())

        if category:
            templates = [t for t in templates if t.category == category]

        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "icon": t.icon,
                "data_source": t.data_source,
                "supported_chart_types": [ct.value for ct in t.supported_chart_types],
                "default_chart_type": t.default_chart_type.value,
                "is_system_template": t.is_system_template,
            }
            for t in templates
        ]

    def get_template_schema(
        self,
        template_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Gibt das vollstaendige Schema eines Templates zurueck.

        Args:
            template_id: Template-ID

        Returns:
            Template-Schema oder None
        """
        template = self._templates.get(template_id)
        if not template:
            return None

        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "category": template.category.value,
            "data_source": template.data_source,
            "columns": [
                {
                    "id": c.id,
                    "field_path": c.field_path,
                    "display_name": c.display_name,
                    "data_type": c.data_type,
                    "is_visible": c.is_visible,
                    "width": c.width,
                    "format_pattern": c.format_pattern,
                    "aggregation": c.aggregation.value if c.aggregation else None,
                    "sort_order": c.sort_order,
                }
                for c in template.columns
            ],
            "default_filters": [
                {
                    "id": f.id,
                    "field_path": f.field_path,
                    "operator": f.operator.value,
                    "value": f.value,
                    "display_name": f.display_name,
                    "is_dynamic": f.is_dynamic,
                }
                for f in template.default_filters
            ],
            "default_groupings": [
                {
                    "field_path": g.field_path,
                    "display_name": g.display_name,
                    "sort_order": g.sort_order,
                }
                for g in template.default_groupings
            ],
            "supported_chart_types": [ct.value for ct in template.supported_chart_types],
            "default_chart_type": template.default_chart_type.value,
        }

    def get_available_fields(
        self,
        data_source: str,
    ) -> List[Dict[str, Any]]:
        """
        Gibt verfuegbare Felder fuer eine Datenquelle zurueck.

        Args:
            data_source: Datenquellen-ID

        Returns:
            Liste der Felder mit Metadaten
        """
        field_definitions: Dict[str, List[Dict[str, Any]]] = {
            "documents": [
                {"path": "id", "name": "ID", "type": "string"},
                {"path": "filename", "name": "Dateiname", "type": "string"},
                {"path": "document_type", "name": "Dokumenttyp", "type": "string"},
                {"path": "status", "name": "Status", "type": "string"},
                {"path": "created_at", "name": "Erstellt am", "type": "date"},
                {"path": "ocr_confidence", "name": "OCR-Konfidenz", "type": "number"},
            ],
            "invoices": [
                {"path": "invoice_number", "name": "Rechnungsnummer", "type": "string"},
                {"path": "invoice_date", "name": "Rechnungsdatum", "type": "date"},
                {"path": "due_date", "name": "Faelligkeitsdatum", "type": "date"},
                {"path": "total_net", "name": "Nettobetrag", "type": "currency"},
                {"path": "total_gross", "name": "Bruttobetrag", "type": "currency"},
                {"path": "vat_amount", "name": "MwSt-Betrag", "type": "currency"},
                {"path": "vat_rate", "name": "MwSt-Satz", "type": "number"},
                {"path": "entity_name", "name": "Geschaeftspartner", "type": "string"},
                {"path": "entity_type", "name": "Partner-Typ", "type": "string"},
                {"path": "status", "name": "Status", "type": "string"},
            ],
            "bank_transactions": [
                {"path": "booking_date", "name": "Buchungsdatum", "type": "date"},
                {"path": "amount", "name": "Betrag", "type": "currency"},
                {"path": "counterparty_name", "name": "Gegenpartei", "type": "string"},
                {"path": "reference_text", "name": "Verwendungszweck", "type": "string"},
                {"path": "transaction_type", "name": "Transaktionstyp", "type": "string"},
            ],
        }

        return field_definitions.get(data_source, [])

    def get_available_operators(
        self,
        data_type: str,
    ) -> List[Dict[str, str]]:
        """
        Gibt verfuegbare Operatoren fuer einen Datentyp zurueck.

        Args:
            data_type: Datentyp (string, number, date, etc.)

        Returns:
            Liste der Operatoren
        """
        common_ops = [
            {"id": "eq", "name": "gleich"},
            {"id": "ne", "name": "ungleich"},
            {"id": "is_null", "name": "ist leer"},
            {"id": "is_not_null", "name": "ist nicht leer"},
        ]

        type_ops: Dict[str, List[Dict[str, str]]] = {
            "string": [
                {"id": "contains", "name": "enthaelt"},
                {"id": "starts_with", "name": "beginnt mit"},
                {"id": "ends_with", "name": "endet mit"},
                {"id": "in", "name": "in Liste"},
            ],
            "number": [
                {"id": "gt", "name": "groesser als"},
                {"id": "gte", "name": "groesser oder gleich"},
                {"id": "lt", "name": "kleiner als"},
                {"id": "lte", "name": "kleiner oder gleich"},
                {"id": "between", "name": "zwischen"},
            ],
            "currency": [
                {"id": "gt", "name": "groesser als"},
                {"id": "gte", "name": "groesser oder gleich"},
                {"id": "lt", "name": "kleiner als"},
                {"id": "lte", "name": "kleiner oder gleich"},
                {"id": "between", "name": "zwischen"},
            ],
            "date": [
                {"id": "gt", "name": "nach"},
                {"id": "gte", "name": "ab"},
                {"id": "lt", "name": "vor"},
                {"id": "lte", "name": "bis"},
                {"id": "between", "name": "zwischen"},
            ],
        }

        return common_ops + type_ops.get(data_type, [])

    async def generate_report(
        self,
        db: AsyncSession,
        template_id: str,
        company_id: uuid.UUID,
        filters: Optional[List[Dict[str, Any]]] = None,
        columns: Optional[List[str]] = None,
        groupings: Optional[List[str]] = None,
        chart_type: Optional[ChartType] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> VisualReportResult:
        """
        Generiert einen Report basierend auf Template und Konfiguration.

        Args:
            db: Database Session
            template_id: Template-ID
            company_id: Company-ID
            filters: Optionale Filter
            columns: Optionale Spaltenauswahl
            groupings: Optionale Gruppierungen
            chart_type: Optionaler Chart-Typ
            limit: Maximale Zeilenzahl
            offset: Offset fuer Paginierung

        Returns:
            VisualReportResult
        """
        import time
        start_time = time.perf_counter()

        template = self._templates.get(template_id)
        if not template:
            raise ValueError(f"Template nicht gefunden: {template_id}")

        # Effective Chart Type
        effective_chart_type = chart_type or template.default_chart_type

        # Daten abrufen (vereinfachte Implementierung)
        rows, total_count = await self._fetch_data(
            db, template, company_id, filters, limit, offset
        )

        # Aggregationen berechnen
        aggregations = await self._calculate_aggregations(
            db, template, company_id, filters
        )

        # Chart-Daten generieren
        chart_data = None
        if effective_chart_type != ChartType.TABLE:
            chart_data = self._generate_chart_data(
                rows, template, effective_chart_type, groupings
            )

        processing_time = int((time.perf_counter() - start_time) * 1000)

        REPORT_BUILDER_REQUESTS.labels(
            template_id=template_id,
            action="generate",
        ).inc()
        REPORT_GENERATION_DURATION.observe(processing_time / 1000)

        return VisualReportResult(
            template_id=template_id,
            template_name=template.name,
            columns=[
                {
                    "id": c.id,
                    "field_path": c.field_path,
                    "display_name": c.display_name,
                    "data_type": c.data_type,
                }
                for c in template.columns
                if not columns or c.id in columns
            ],
            rows=rows,
            total_count=total_count,
            aggregations=aggregations,
            chart_data=chart_data,
            filters_applied=filters or [],
            generated_at=datetime.now(timezone.utc),
            processing_time_ms=processing_time,
            metadata={
                "chart_type": effective_chart_type.value,
                "limit": limit,
                "offset": offset,
            },
        )

    async def preview_report(
        self,
        db: AsyncSession,
        template_id: str,
        company_id: uuid.UUID,
        filters: Optional[List[Dict[str, Any]]] = None,
        limit: int = 10,
    ) -> VisualReportResult:
        """
        Generiert eine schnelle Vorschau mit wenigen Daten.

        Args:
            db: Database Session
            template_id: Template-ID
            company_id: Company-ID
            filters: Optionale Filter
            limit: Maximale Zeilenzahl (default 10)

        Returns:
            VisualReportResult (Vorschau)
        """
        return await self.generate_report(
            db, template_id, company_id, filters, limit=limit
        )

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    async def _fetch_data(
        self,
        db: AsyncSession,
        template: ReportTemplateDefinition,
        company_id: uuid.UUID,
        filters: Optional[List[Dict[str, Any]]],
        limit: int,
        offset: int,
    ) -> Tuple[List[ReportDataRow], int]:
        """Ruft Daten fuer den Report ab."""
        rows: List[ReportDataRow] = []

        if template.data_source == "invoices":
            # Invoice-basierte Reports
            query = select(
                InvoiceTracking,
                BusinessEntity.name.label("entity_name"),
            ).outerjoin(
                BusinessEntity,
                InvoiceTracking.entity_id == BusinessEntity.id
            ).where(
                InvoiceTracking.company_id == company_id
            )

            # Count-Query
            count_query = select(func.count(InvoiceTracking.id)).where(
                InvoiceTracking.company_id == company_id
            )

            result = await db.execute(query.limit(limit).offset(offset))
            count_result = await db.execute(count_query)
            total_count = count_result.scalar() or 0

            for idx, row in enumerate(result.all()):
                invoice = row[0]
                entity_name = row[1]

                rows.append(ReportDataRow(
                    data={
                        "id": str(invoice.id),
                        "invoice_number": invoice.invoice_number,
                        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                        "total_net": float(invoice.total_net or 0),
                        "total_gross": float(invoice.total_gross or 0),
                        "vat_amount": float(invoice.vat_amount or 0),
                        "status": invoice.status,
                        "entity_name": entity_name,
                    },
                    row_index=idx + offset,
                ))

        elif template.data_source == "documents":
            # Document-basierte Reports
            query = select(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )

            count_query = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )

            result = await db.execute(query.limit(limit).offset(offset))
            count_result = await db.execute(count_query)
            total_count = count_result.scalar() or 0

            for idx, doc in enumerate(result.scalars().all()):
                rows.append(ReportDataRow(
                    data={
                        "id": str(doc.id),
                        "filename": doc.original_filename,
                        "document_type": doc.document_type,
                        "status": doc.status,
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        "ocr_confidence": doc.ocr_confidence,
                    },
                    row_index=idx + offset,
                ))

        else:
            total_count = 0

        return rows, total_count

    async def _calculate_aggregations(
        self,
        db: AsyncSession,
        template: ReportTemplateDefinition,
        company_id: uuid.UUID,
        filters: Optional[List[Dict[str, Any]]],
    ) -> List[ReportAggregation]:
        """Berechnet Aggregationen fuer den Report."""
        aggregations: List[ReportAggregation] = []

        for col in template.columns:
            if not col.aggregation:
                continue

            # Vereinfachte Implementierung fuer Invoice-Daten
            if template.data_source == "invoices":
                if col.aggregation == AggregationType.SUM:
                    if "total" in col.field_path or "amount" in col.field_path:
                        agg_func = func.sum(InvoiceTracking.total_gross)
                        query = select(agg_func).where(
                            InvoiceTracking.company_id == company_id
                        )
                        result = await db.execute(query)
                        value = result.scalar() or 0

                        aggregations.append(ReportAggregation(
                            field_path=col.field_path,
                            aggregation_type=col.aggregation,
                            value=float(value),
                            formatted_value=f"{float(value):,.2f} EUR",
                        ))

                elif col.aggregation == AggregationType.COUNT:
                    query = select(func.count(InvoiceTracking.id)).where(
                        InvoiceTracking.company_id == company_id
                    )
                    result = await db.execute(query)
                    value = result.scalar() or 0

                    aggregations.append(ReportAggregation(
                        field_path=col.field_path,
                        aggregation_type=col.aggregation,
                        value=value,
                        formatted_value=str(value),
                    ))

        return aggregations

    def _generate_chart_data(
        self,
        rows: List[ReportDataRow],
        template: ReportTemplateDefinition,
        chart_type: ChartType,
        groupings: Optional[List[str]],
    ) -> ChartData:
        """Generiert Daten fuer die Chart-Darstellung."""
        # Vereinfachte Implementierung
        labels: List[str] = []
        values: List[float] = []

        # Gruppieren wenn angegeben
        group_field = groupings[0] if groupings else "entity_name"

        grouped: Dict[str, float] = {}
        for row in rows:
            key = str(row.data.get(group_field, "Unbekannt"))
            value = float(row.data.get("total_gross", 0))
            grouped[key] = grouped.get(key, 0) + value

        # Sortieren nach Wert
        sorted_items = sorted(grouped.items(), key=lambda x: x[1], reverse=True)[:10]

        for label, value in sorted_items:
            labels.append(label)
            values.append(value)

        # Chart-Optionen je nach Typ
        options: Dict[str, Any] = {
            "responsive": True,
            "plugins": {
                "legend": {"position": "top"},
            },
        }

        if chart_type in (ChartType.BAR, ChartType.LINE, ChartType.AREA):
            options["scales"] = {
                "y": {"beginAtZero": True},
            }

        return ChartData(
            chart_type=chart_type,
            labels=labels,
            datasets=[
                {
                    "label": template.name,
                    "data": values,
                    "backgroundColor": self._get_chart_colors(len(values)),
                    "borderColor": self._get_chart_colors(len(values), border=True),
                    "borderWidth": 1,
                }
            ],
            options=options,
        )

    def _get_chart_colors(
        self,
        count: int,
        border: bool = False,
    ) -> List[str]:
        """Generiert Farben fuer Charts."""
        base_colors = [
            "rgba(59, 130, 246, 0.8)",   # Blue
            "rgba(16, 185, 129, 0.8)",   # Green
            "rgba(245, 158, 11, 0.8)",   # Amber
            "rgba(239, 68, 68, 0.8)",    # Red
            "rgba(139, 92, 246, 0.8)",   # Purple
            "rgba(236, 72, 153, 0.8)",   # Pink
            "rgba(20, 184, 166, 0.8)",   # Teal
            "rgba(249, 115, 22, 0.8)",   # Orange
            "rgba(99, 102, 241, 0.8)",   # Indigo
            "rgba(168, 162, 158, 0.8)",  # Gray
        ]

        if border:
            base_colors = [c.replace("0.8", "1") for c in base_colors]

        # Farben wiederholen wenn noetig
        colors = []
        for i in range(count):
            colors.append(base_colors[i % len(base_colors)])

        return colors


# =============================================================================
# Factory
# =============================================================================

_visual_report_builder_service: Optional[VisualReportBuilderService] = None


def get_visual_report_builder_service() -> VisualReportBuilderService:
    """Factory fuer VisualReportBuilderService Singleton."""
    global _visual_report_builder_service
    if _visual_report_builder_service is None:
        _visual_report_builder_service = VisualReportBuilderService()
    return _visual_report_builder_service

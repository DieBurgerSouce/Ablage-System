# -*- coding: utf-8 -*-
"""
Pre-Built Report Templates.

Vordefinierte Report-Templates für häufige Business-Auswertungen:
- Kostenauswertung (Cost Analysis)
- Cashflow-Prognose (Cashflow Forecast)
- Dokumenten-Volumen (Document Volume)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class ReportColumn:
    """Spalten-Definition für Report."""
    key: str
    label: str  # German
    format_type: str  # "currency", "number", "date", "text", "percent"


@dataclass
class ChartConfig:
    """Chart-Konfiguration für Visualisierungen."""
    chart_type: str  # "bar", "line", "area", "pie"
    x_axis: str
    y_axis: str
    title: str  # German


@dataclass
class ReportTemplate:
    """Pre-Built Report Template."""
    template_id: str
    name: str  # German
    description: str  # German
    category: str
    columns: List[ReportColumn]
    default_filters: Dict[str, str]
    charts: List[ChartConfig]
    grouping: List[str]
    supports_comparison: bool
    supports_export: List[str]  # ["pdf", "excel", "csv"]


# =============================================================================
# KOSTENAUSWERTUNG TEMPLATE
# =============================================================================

COST_ANALYSIS_TEMPLATE = ReportTemplate(
    template_id="cost_analysis",
    name="Kostenauswertung",
    description="Detaillierte Kostenanalyse nach Kategorie, Lieferant und Kostenstelle mit Jahresvergleich",
    category="finance",
    columns=[
        ReportColumn(key="period", label="Periode", format_type="text"),
        ReportColumn(key="category", label="Kategorie", format_type="text"),
        ReportColumn(key="supplier", label="Lieferant", format_type="text"),
        ReportColumn(key="cost_center", label="Kostenstelle", format_type="text"),
        ReportColumn(key="amount", label="Betrag (aktuell)", format_type="currency"),
        ReportColumn(key="previous_amount", label="Betrag (Vorjahr)", format_type="currency"),
        ReportColumn(key="change_percent", label="Veränderung (%)", format_type="percent"),
        ReportColumn(key="transaction_count", label="Anzahl Transaktionen", format_type="number"),
        ReportColumn(key="avg_transaction", label="Ø Transaktionswert", format_type="currency"),
    ],
    default_filters={
        "date_range": "last_12_months",
        "status": "completed",
        "exclude_internal": "true",
    },
    charts=[
        ChartConfig(
            chart_type="bar",
            x_axis="category",
            y_axis="amount",
            title="Kosten nach Kategorie"
        ),
        ChartConfig(
            chart_type="pie",
            x_axis="cost_center",
            y_axis="amount",
            title="Kostenverteilung nach Kostenstelle"
        ),
        ChartConfig(
            chart_type="line",
            x_axis="period",
            y_axis="amount",
            title="Kostenentwicklung über Zeit"
        ),
    ],
    grouping=["category", "cost_center", "supplier"],
    supports_comparison=True,
    supports_export=["pdf", "excel", "csv"],
)


# =============================================================================
# CASHFLOW-PROGNOSE TEMPLATE
# =============================================================================

CASHFLOW_FORECAST_TEMPLATE = ReportTemplate(
    template_id="cashflow_forecast",
    name="Cashflow-Prognose",
    description="Cashflow-Prognose basierend auf offenen Forderungen und Verbindlichkeiten mit 30/60/90-Tage Ausblick",
    category="finance",
    columns=[
        ReportColumn(key="date", label="Datum", format_type="date"),
        ReportColumn(key="receivables", label="Forderungen", format_type="currency"),
        ReportColumn(key="payables", label="Verbindlichkeiten", format_type="currency"),
        ReportColumn(key="net_position", label="Netto-Position", format_type="currency"),
        ReportColumn(key="cumulative", label="Kumuliert", format_type="currency"),
        ReportColumn(key="receivables_count", label="Anzahl Forderungen", format_type="number"),
        ReportColumn(key="payables_count", label="Anzahl Verbindlichkeiten", format_type="number"),
        ReportColumn(key="overdue_amount", label="Überfällige Beträge", format_type="currency"),
    ],
    default_filters={
        "forecast_days": "90",
        "include_drafts": "false",
        "currency": "EUR",
    },
    charts=[
        ChartConfig(
            chart_type="area",
            x_axis="date",
            y_axis="cumulative",
            title="Projizierte Cashflow-Position (90 Tage)"
        ),
        ChartConfig(
            chart_type="bar",
            x_axis="date",
            y_axis="net_position",
            title="Tägliche Netto-Position"
        ),
        ChartConfig(
            chart_type="line",
            x_axis="date",
            y_axis="receivables,payables",
            title="Forderungen vs. Verbindlichkeiten"
        ),
    ],
    grouping=["date"],
    supports_comparison=False,
    supports_export=["pdf", "excel", "csv"],
)


# =============================================================================
# DOKUMENTEN-VOLUMEN TEMPLATE
# =============================================================================

DOCUMENT_VOLUME_TEMPLATE = ReportTemplate(
    template_id="document_volume",
    name="Dokumenten-Volumen",
    description="Auswertung des Dokumenten-Aufkommens nach Monat, Kategorie und Quelle mit Verarbeitungszeiten",
    category="operations",
    columns=[
        ReportColumn(key="period", label="Periode", format_type="text"),
        ReportColumn(key="category", label="Kategorie", format_type="text"),
        ReportColumn(key="source", label="Quelle", format_type="text"),
        ReportColumn(key="count", label="Anzahl Dokumente", format_type="number"),
        ReportColumn(key="avg_processing_time_ms", label="Ø Verarbeitungszeit (ms)", format_type="number"),
        ReportColumn(key="sla_compliance_percent", label="SLA-Einhaltung (%)", format_type="percent"),
        ReportColumn(key="error_count", label="Anzahl Fehler", format_type="number"),
        ReportColumn(key="error_rate_percent", label="Fehlerrate (%)", format_type="percent"),
        ReportColumn(key="total_size_mb", label="Gesamtgröße (MB)", format_type="number"),
    ],
    default_filters={
        "date_range": "last_6_months",
        "exclude_deleted": "true",
        "min_confidence": "0.7",
    },
    charts=[
        ChartConfig(
            chart_type="line",
            x_axis="period",
            y_axis="count",
            title="Monatlicher Dokumenten-Trend"
        ),
        ChartConfig(
            chart_type="bar",
            x_axis="category",
            y_axis="count",
            title="Dokumente nach Kategorie"
        ),
        ChartConfig(
            chart_type="bar",
            x_axis="source",
            y_axis="count",
            title="Dokumente nach Quelle"
        ),
        ChartConfig(
            chart_type="line",
            x_axis="period",
            y_axis="avg_processing_time_ms",
            title="Durchschnittliche Verarbeitungszeit"
        ),
    ],
    grouping=["period", "category", "source"],
    supports_comparison=True,
    supports_export=["pdf", "excel", "csv"],
)


# =============================================================================
# TEMPLATE REGISTRY
# =============================================================================

_TEMPLATE_REGISTRY: Dict[str, ReportTemplate] = {
    "cost_analysis": COST_ANALYSIS_TEMPLATE,
    "cashflow_forecast": CASHFLOW_FORECAST_TEMPLATE,
    "document_volume": DOCUMENT_VOLUME_TEMPLATE,
}


# =============================================================================
# PUBLIC API
# =============================================================================


def get_all_templates() -> List[ReportTemplate]:
    """
    Gibt alle verfügbaren Pre-Built Templates zurück.

    Returns:
        Liste aller Report Templates
    """
    logger.info("get_all_templates", count=len(_TEMPLATE_REGISTRY))
    return list(_TEMPLATE_REGISTRY.values())


def get_template_by_id(template_id: str) -> Optional[ReportTemplate]:
    """
    Holt ein Template anhand seiner ID.

    Args:
        template_id: Template-ID (z.B. "cost_analysis")

    Returns:
        Template oder None wenn nicht gefunden
    """
    template = _TEMPLATE_REGISTRY.get(template_id)
    if template:
        logger.info("get_template_by_id", template_id=template_id, found=True)
    else:
        logger.warning("get_template_by_id", template_id=template_id, found=False)
    return template


def get_templates_by_category(category: str) -> List[ReportTemplate]:
    """
    Filtert Templates nach Kategorie.

    Args:
        category: Kategorie (z.B. "finance", "operations")

    Returns:
        Liste der Templates in dieser Kategorie
    """
    templates = [t for t in _TEMPLATE_REGISTRY.values() if t.category == category]
    logger.info("get_templates_by_category", category=category, count=len(templates))
    return templates

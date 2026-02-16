# -*- coding: utf-8 -*-
"""
Report Catalog Service.

Stellt vordefinierte Report-Templates bereit, die Nutzer instanziieren können.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.reports.report_template_service import ReportTemplateService


logger = structlog.get_logger(__name__)


# =============================================================================
# PREDEFINED TEMPLATES
# =============================================================================

CATALOG_TEMPLATES: List[Dict[str, Any]] = [
    # 1. Monatliche Rechnungsübersicht
    {
        "id": "monthly-invoices",
        "name": "Monatliche Rechnungsübersicht",
        "description": "Alle Rechnungen eines Monats mit Betrag, Kunde und Status",
        "category": "Finanzen",
        "icon": "receipt",
        "report_type": "finance",
        "data_source": "invoices",
        "columns": [
            {"field_path": "invoice_number", "display_name": "Rechnungsnr.", "data_type": "string"},
            {"field_path": "invoice_date", "display_name": "Datum", "data_type": "date"},
            {"field_path": "customer_name", "display_name": "Kunde", "data_type": "string"},
            {"field_path": "total_amount", "display_name": "Betrag", "data_type": "currency"},
            {"field_path": "status", "display_name": "Status", "data_type": "string"},
        ],
        "filters": [
            {
                "field_path": "invoice_date",
                "operator": "between",
                "allow_user_input": True,
                "dynamic_source": "last_30_days",
            }
        ],
        "charts": [
            {
                "chart_type": "bar",
                "title": "Umsatz nach Kunde",
                "x_axis_field": "customer_name",
                "y_axis_field": "total_amount",
                "aggregation": "sum",
            }
        ],
    },
    # 2. Offene Forderungen nach Kunde
    {
        "id": "open-receivables",
        "name": "Offene Forderungen",
        "description": "Übersicht aller unbezahlten Rechnungen gruppiert nach Kunde",
        "category": "Finanzen",
        "icon": "alert-triangle",
        "report_type": "finance",
        "data_source": "invoices",
        "columns": [
            {"field_path": "customer_name", "display_name": "Kunde", "data_type": "string"},
            {"field_path": "invoice_number", "display_name": "Rechnungsnr.", "data_type": "string"},
            {"field_path": "invoice_date", "display_name": "Rechnungsdatum", "data_type": "date"},
            {"field_path": "due_date", "display_name": "Fälligkeit", "data_type": "date"},
            {"field_path": "total_amount", "display_name": "Offener Betrag", "data_type": "currency"},
            {"field_path": "days_overdue", "display_name": "Überfällig (Tage)", "data_type": "number"},
        ],
        "filters": [
            {"field_path": "status", "operator": "in", "value": ["open", "overdue"]},
        ],
        "enable_aggregations": True,
        "charts": [
            {
                "chart_type": "pie",
                "title": "Forderungen nach Kunde",
                "x_axis_field": "customer_name",
                "y_axis_field": "total_amount",
                "aggregation": "sum",
            }
        ],
    },
    # 3. Dokumentenstatistik nach Kategorie
    {
        "id": "document-stats",
        "name": "Dokumentenstatistik",
        "description": "Anzahl der Dokumente nach Typ, Status und Zeitraum",
        "category": "Dokumente",
        "icon": "file-text",
        "report_type": "document",
        "data_source": "documents",
        "columns": [
            {"field_path": "document_type", "display_name": "Dokumenttyp", "data_type": "string"},
            {"field_path": "status", "display_name": "Status", "data_type": "string"},
            {"field_path": "created_at", "display_name": "Erstellt", "data_type": "date"},
            {"field_path": "file_size", "display_name": "Größe", "data_type": "number"},
        ],
        "enable_aggregations": True,
        "charts": [
            {
                "chart_type": "bar",
                "title": "Dokumente nach Typ",
                "x_axis_field": "document_type",
                "aggregation": "count",
            },
            {
                "chart_type": "area",
                "title": "Dokumente über Zeit",
                "x_axis_field": "created_at",
                "aggregation": "count",
            },
        ],
    },
    # 4. OCR-Qualitätsreport
    {
        "id": "ocr-quality",
        "name": "OCR-Qualitätsreport",
        "description": "Auswertung der OCR-Erkennungsqualität und Fehlerquoten",
        "category": "Qualität",
        "icon": "scan",
        "report_type": "ocr",
        "data_source": "documents",
        "columns": [
            {"field_path": "filename", "display_name": "Dateiname", "data_type": "string"},
            {"field_path": "ocr_backend", "display_name": "OCR-Backend", "data_type": "string"},
            {"field_path": "ocr_confidence", "display_name": "Konfidenz", "data_type": "number"},
            {"field_path": "processing_time_ms", "display_name": "Dauer (ms)", "data_type": "number"},
            {"field_path": "created_at", "display_name": "Verarbeitet", "data_type": "date"},
        ],
        "filters": [
            {"field_path": "status", "operator": "eq", "value": "completed"},
        ],
        "charts": [
            {
                "chart_type": "bar",
                "title": "Konfidenz nach Backend",
                "x_axis_field": "ocr_backend",
                "y_axis_field": "ocr_confidence",
                "aggregation": "avg",
            },
            {
                "chart_type": "line",
                "title": "Verarbeitungszeit über Zeit",
                "x_axis_field": "created_at",
                "y_axis_field": "processing_time_ms",
                "aggregation": "avg",
            },
        ],
    },
    # 5. Kunden-Umsatzranking
    {
        "id": "customer-ranking",
        "name": "Kunden-Umsatzranking",
        "description": "Top-Kunden nach Umsatz mit Entwicklung",
        "category": "Finanzen",
        "icon": "trophy",
        "report_type": "finance",
        "data_source": "entities",
        "columns": [
            {"field_path": "name", "display_name": "Kundenname", "data_type": "string"},
            {"field_path": "customer_number", "display_name": "Kundennr.", "data_type": "string"},
            {"field_path": "total_revenue", "display_name": "Gesamtumsatz", "data_type": "currency"},
            {"field_path": "invoice_count", "display_name": "Rechnungen", "data_type": "number"},
            {"field_path": "avg_invoice_value", "display_name": "Ø Rechnungswert", "data_type": "currency"},
        ],
        "filters": [
            {"field_path": "entity_type", "operator": "in", "value": ["customer", "both"]},
        ],
        "enable_aggregations": True,
        "charts": [
            {
                "chart_type": "bar",
                "title": "Top 10 Kunden",
                "x_axis_field": "name",
                "y_axis_field": "total_revenue",
                "aggregation": "sum",
            }
        ],
    },
    # 6. Lieferanten-Übersicht
    {
        "id": "supplier-overview",
        "name": "Lieferanten-Übersicht",
        "description": "Alle Lieferanten mit Bestellvolumen und letzter Aktivität",
        "category": "Einkauf",
        "icon": "truck",
        "report_type": "custom",
        "data_source": "entities",
        "columns": [
            {"field_path": "name", "display_name": "Lieferant", "data_type": "string"},
            {"field_path": "supplier_number", "display_name": "Lieferantennr.", "data_type": "string"},
            {"field_path": "city", "display_name": "Stadt", "data_type": "string"},
            {"field_path": "document_count", "display_name": "Dokumente", "data_type": "number"},
            {"field_path": "last_activity", "display_name": "Letzte Aktivität", "data_type": "date"},
        ],
        "filters": [
            {"field_path": "entity_type", "operator": "in", "value": ["supplier", "both"]},
            {"field_path": "is_active", "operator": "eq", "value": True},
        ],
    },
    # 7. Dokumenten-Verarbeitungsprotokoll
    {
        "id": "processing-log",
        "name": "Verarbeitungsprotokoll",
        "description": "Protokoll aller verarbeiteten Dokumente mit Fehlern",
        "category": "System",
        "icon": "activity",
        "report_type": "document",
        "data_source": "documents",
        "columns": [
            {"field_path": "filename", "display_name": "Datei", "data_type": "string"},
            {"field_path": "status", "display_name": "Status", "data_type": "string"},
            {"field_path": "ocr_backend", "display_name": "Backend", "data_type": "string"},
            {"field_path": "error_message", "display_name": "Fehler", "data_type": "string"},
            {"field_path": "created_at", "display_name": "Erstellt", "data_type": "date"},
            {"field_path": "updated_at", "display_name": "Aktualisiert", "data_type": "date"},
        ],
        "filters": [
            {"field_path": "created_at", "operator": "between", "dynamic_source": "last_7_days"},
        ],
    },
    # 8. Zahlungseingaenge
    {
        "id": "payment-receipts",
        "name": "Zahlungseingaenge",
        "description": "Alle eingegangenen Zahlungen mit Zuordnung",
        "category": "Finanzen",
        "icon": "banknote",
        "report_type": "finance",
        "data_source": "bank_transactions",
        "columns": [
            {"field_path": "booking_date", "display_name": "Buchungsdatum", "data_type": "date"},
            {"field_path": "amount", "display_name": "Betrag", "data_type": "currency"},
            {"field_path": "counterparty_name", "display_name": "Absender", "data_type": "string"},
            {"field_path": "purpose", "display_name": "Verwendungszweck", "data_type": "string"},
            {"field_path": "matched_invoice", "display_name": "Rechnung", "data_type": "string"},
        ],
        "filters": [
            {"field_path": "amount", "operator": "gt", "value": 0},
            {"field_path": "booking_date", "operator": "between", "dynamic_source": "last_30_days"},
        ],
        "charts": [
            {
                "chart_type": "area",
                "title": "Zahlungseingaenge über Zeit",
                "x_axis_field": "booking_date",
                "y_axis_field": "amount",
                "aggregation": "sum",
            }
        ],
    },
    # 9. Spesenabrechnungen
    {
        "id": "expense-reports",
        "name": "Spesenabrechnungen",
        "description": "Übersicht aller Spesenabrechnungen nach Mitarbeiter",
        "category": "Personal",
        "icon": "wallet",
        "report_type": "custom",
        "data_source": "expenses",
        "columns": [
            {"field_path": "report_number", "display_name": "Belegnr.", "data_type": "string"},
            {"field_path": "employee_name", "display_name": "Mitarbeiter", "data_type": "string"},
            {"field_path": "total_amount", "display_name": "Gesamtbetrag", "data_type": "currency"},
            {"field_path": "status", "display_name": "Status", "data_type": "string"},
            {"field_path": "submitted_at", "display_name": "Eingereicht", "data_type": "date"},
        ],
        "enable_aggregations": True,
        "charts": [
            {
                "chart_type": "pie",
                "title": "Spesen nach Mitarbeiter",
                "x_axis_field": "employee_name",
                "y_axis_field": "total_amount",
                "aggregation": "sum",
            }
        ],
    },
    # 10. Firmenübersicht (Cross-Company)
    {
        "id": "company-overview",
        "name": "Firmenübersicht",
        "description": "Vergleich der Aktivitäten zwischen Folie und Messer",
        "category": "Management",
        "icon": "building",
        "report_type": "custom",
        "data_source": "entities",
        "columns": [
            {"field_path": "name", "display_name": "Geschäftspartner", "data_type": "string"},
            {"field_path": "entity_type", "display_name": "Typ", "data_type": "string"},
            {"field_path": "company_presence", "display_name": "Firmen", "data_type": "string"},
            {"field_path": "folie_docs", "display_name": "Folie Docs", "data_type": "number"},
            {"field_path": "messer_docs", "display_name": "Messer Docs", "data_type": "number"},
        ],
        "charts": [
            {
                "chart_type": "stacked_bar",
                "title": "Dokumente nach Firma",
                "x_axis_field": "entity_type",
                "group_by_field": "company_presence",
                "aggregation": "count",
            }
        ],
    },
]


# =============================================================================
# SERVICE
# =============================================================================

class ReportCatalogService:
    """
    Service für vordefinierte Report-Templates.
    """

    def __init__(self) -> None:
        self._templates = {t["id"]: t for t in CATALOG_TEMPLATES}

    def get_catalog(
        self,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gibt den Katalog aller vordefinierten Templates zurück.

        Args:
            category: Optional filter by category

        Returns:
            List of catalog entries with id, name, description, category, icon
        """
        templates = list(self._templates.values())

        if category:
            templates = [t for t in templates if t.get("category") == category]

        return [
            {
                "id": t["id"],
                "name": t["name"],
                "description": t["description"],
                "category": t.get("category", "Allgemein"),
                "icon": t.get("icon", "file"),
                "reportType": t.get("report_type", "custom"),
                "dataSource": t.get("data_source", "documents"),
                "columnCount": len(t.get("columns", [])),
                "hasCharts": len(t.get("charts", [])) > 0,
                "hasFilters": len(t.get("filters", [])) > 0,
            }
            for t in templates
        ]

    def get_categories(self) -> List[str]:
        """
        Gibt alle verfügbaren Kategorien zurück.
        """
        categories = set()
        for t in self._templates.values():
            if "category" in t:
                categories.add(t["category"])
        return sorted(categories)

    def get_template_preview(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Gibt die vollständige Vorschau eines Templates zurück.
        """
        template = self._templates.get(template_id)
        if not template:
            return None

        return {
            "id": template["id"],
            "name": template["name"],
            "description": template["description"],
            "category": template.get("category", "Allgemein"),
            "icon": template.get("icon", "file"),
            "reportType": template.get("report_type", "custom"),
            "dataSource": template.get("data_source", "documents"),
            "columns": [
                {
                    "fieldPath": c["field_path"],
                    "displayName": c["display_name"],
                    "dataType": c["data_type"],
                }
                for c in template.get("columns", [])
            ],
            "filters": [
                {
                    "fieldPath": f["field_path"],
                    "operator": f["operator"],
                    "value": f.get("value"),
                    "dynamicSource": f.get("dynamic_source"),
                    "allowUserInput": f.get("allow_user_input", False),
                }
                for f in template.get("filters", [])
            ],
            "charts": [
                {
                    "chartType": c["chart_type"],
                    "title": c.get("title", ""),
                    "xAxisField": c.get("x_axis_field"),
                    "yAxisField": c.get("y_axis_field"),
                    "groupByField": c.get("group_by_field"),
                    "aggregation": c.get("aggregation", "count"),
                }
                for c in template.get("charts", [])
            ],
            "enableAggregations": template.get("enable_aggregations", False),
        }

    async def instantiate_template(
        self,
        template_id: str,
        user_id: UUID,
        new_name: Optional[str],
        db: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """
        Erstellt eine Kopie eines Katalog-Templates für den Nutzer.

        Args:
            template_id: ID des Katalog-Templates
            user_id: ID des Nutzers
            new_name: Optionaler neuer Name
            db: Database session

        Returns:
            Erstelltes Template oder None wenn nicht gefunden
        """
        template = self._templates.get(template_id)
        if not template:
            return None

        # Erstelle neues Template
        template_service = ReportTemplateService(db)

        new_template = await template_service.create_template(
            user_id=user_id,
            name=new_name or f"{template['name']} (Kopie)",
            description=template.get("description"),
            report_type=template.get("report_type", "custom"),
            data_source=template.get("data_source", "documents"),
            default_format="excel",
            is_public=False,
            enable_aggregations=template.get("enable_aggregations", False),
        )

        # Fuege Spalten hinzu
        for col in template.get("columns", []):
            await template_service.add_column(
                template_id=new_template.id,
                field_path=col["field_path"],
                display_name=col["display_name"],
                data_type=col["data_type"],
                format_pattern=col.get("format_pattern"),
            )

        # Fuege Filter hinzu
        for flt in template.get("filters", []):
            await template_service.add_filter(
                template_id=new_template.id,
                field_path=flt["field_path"],
                operator=flt["operator"],
                value=flt.get("value"),
                value_type=flt.get("value_type", "string"),
                allow_user_input=flt.get("allow_user_input", False),
                dynamic_source=flt.get("dynamic_source"),
            )

        # Fuege Charts hinzu
        for chart in template.get("charts", []):
            await template_service.add_chart(
                template_id=new_template.id,
                chart_type=chart["chart_type"],
                title=chart.get("title"),
                x_axis_field=chart.get("x_axis_field"),
                y_axis_field=chart.get("y_axis_field"),
                group_by_field=chart.get("group_by_field"),
                aggregation=chart.get("aggregation", "count"),
            )

        logger.info(
            "catalog_template_instantiated",
            catalog_template_id=template_id,
            new_template_id=str(new_template.id),
            user_id=str(user_id),
        )

        return {
            "id": str(new_template.id),
            "name": new_template.name,
            "description": new_template.description,
            "catalogTemplateId": template_id,
        }


# Singleton instance
_catalog_service: Optional[ReportCatalogService] = None


def get_report_catalog_service() -> ReportCatalogService:
    """Returns singleton instance of ReportCatalogService."""
    global _catalog_service
    if _catalog_service is None:
        _catalog_service = ReportCatalogService()
    return _catalog_service

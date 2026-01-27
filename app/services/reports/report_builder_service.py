# -*- coding: utf-8 -*-
"""
Report Builder Service.

Baut SQL-Queries aus Report-Template-Konfigurationen und fuehrt Reports aus.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import structlog
from sqlalchemy import and_, cast, desc, func, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Document,
    BusinessEntity,
    ReportTemplate,
    ReportColumn,
    ReportFilter,
    User,
    BankAccount,
    BankTransaction,
    ExpenseReport,
    ExpenseItem,
)

logger = structlog.get_logger(__name__)


@dataclass
class ReportRow:
    """Eine Zeile im Report-Ergebnis."""
    data: Dict[str, Any]


@dataclass
class ReportResult:
    """Ergebnis einer Report-Ausfuehrung."""
    template_id: uuid.UUID
    template_name: str
    columns: List[Dict[str, Any]]
    rows: List[ReportRow]
    total_count: int
    aggregations: Optional[Dict[str, Any]] = None
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    filters_applied: Optional[List[Dict[str, Any]]] = None


@dataclass
class PreviewResult:
    """Vorschau-Ergebnis (limitierte Daten)."""
    template_id: uuid.UUID
    columns: List[Dict[str, Any]]
    sample_rows: List[ReportRow]
    total_count: int


# Mapping von data_source zu SQLAlchemy Model
DATA_SOURCE_MODELS: Dict[str, Type] = {
    "documents": Document,
    "invoices": Document,  # Gefiltert nach document_type
    "entities": BusinessEntity,
    "bank_accounts": BankAccount,
    "bank_transactions": BankTransaction,
    "expenses": ExpenseReport,
    "expense_items": ExpenseItem,
}

# Feld-Mappings pro Datenquelle
FIELD_DEFINITIONS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "documents": {
        "id": {"path": "id", "type": "string", "display": "ID"},
        "filename": {"path": "original_filename", "type": "string", "display": "Dateiname"},
        "status": {"path": "status", "type": "string", "display": "Status"},
        "document_type": {"path": "document_type", "type": "string", "display": "Dokumenttyp"},
        "created_at": {"path": "created_at", "type": "date", "display": "Erstellt am"},
        "updated_at": {"path": "updated_at", "type": "date", "display": "Aktualisiert am"},
        "ocr_confidence": {"path": "ocr_confidence", "type": "number", "display": "OCR-Konfidenz"},
        "extracted_data.invoice_number": {"path": "extracted_data", "json_key": "invoice_number", "type": "string", "display": "Rechnungsnummer"},
        "extracted_data.invoice_date": {"path": "extracted_data", "json_key": "invoice_date", "type": "date", "display": "Rechnungsdatum"},
        "extracted_data.due_date": {"path": "extracted_data", "json_key": "due_date", "type": "date", "display": "Faelligkeitsdatum"},
        "extracted_data.total_net": {"path": "extracted_data", "json_key": "total_net", "type": "currency", "display": "Nettobetrag"},
        "extracted_data.total_gross": {"path": "extracted_data", "json_key": "total_gross", "type": "currency", "display": "Bruttobetrag"},
        "extracted_data.vat_amount": {"path": "extracted_data", "json_key": "vat_amount", "type": "currency", "display": "MwSt-Betrag"},
        "extracted_data.supplier_name": {"path": "extracted_data", "json_key": "supplier_name", "type": "string", "display": "Lieferant"},
        "extracted_data.customer_name": {"path": "extracted_data", "json_key": "customer_name", "type": "string", "display": "Kunde"},
    },
    "invoices": {
        # Gleiche Felder wie documents, aber fuer Rechnungen
        "id": {"path": "id", "type": "string", "display": "ID"},
        "filename": {"path": "original_filename", "type": "string", "display": "Dateiname"},
        "status": {"path": "status", "type": "string", "display": "Status"},
        "created_at": {"path": "created_at", "type": "date", "display": "Erstellt am"},
        "invoice_number": {"path": "extracted_data", "json_key": "invoice_number", "type": "string", "display": "Rechnungsnummer"},
        "invoice_date": {"path": "extracted_data", "json_key": "invoice_date", "type": "date", "display": "Rechnungsdatum"},
        "due_date": {"path": "extracted_data", "json_key": "due_date", "type": "date", "display": "Faelligkeitsdatum"},
        "total_net": {"path": "extracted_data", "json_key": "total_net", "type": "currency", "display": "Nettobetrag"},
        "total_gross": {"path": "extracted_data", "json_key": "total_gross", "type": "currency", "display": "Bruttobetrag"},
        "vat_amount": {"path": "extracted_data", "json_key": "vat_amount", "type": "currency", "display": "MwSt-Betrag"},
        "supplier_name": {"path": "extracted_data", "json_key": "supplier_name", "type": "string", "display": "Lieferant"},
        "customer_name": {"path": "extracted_data", "json_key": "customer_name", "type": "string", "display": "Kunde"},
    },
    "entities": {
        "id": {"path": "id", "type": "string", "display": "ID"},
        "name": {"path": "name", "type": "string", "display": "Name"},
        "entity_type": {"path": "entity_type", "type": "string", "display": "Typ"},
        "vat_id": {"path": "vat_id", "type": "string", "display": "USt-IdNr."},
        "email": {"path": "email", "type": "string", "display": "E-Mail"},
        "city": {"path": "city", "type": "string", "display": "Stadt"},
        "country": {"path": "country", "type": "string", "display": "Land"},
        "created_at": {"path": "created_at", "type": "date", "display": "Erstellt am"},
    },
    "bank_accounts": {
        "id": {"path": "id", "type": "string", "display": "ID"},
        "account_name": {"path": "account_name", "type": "string", "display": "Kontoname"},
        "iban": {"path": "iban", "type": "string", "display": "IBAN"},
        "bic": {"path": "bic", "type": "string", "display": "BIC"},
        "bank_name": {"path": "bank_name", "type": "string", "display": "Bankname"},
        "account_holder": {"path": "account_holder", "type": "string", "display": "Kontoinhaber"},
        "account_type": {"path": "account_type", "type": "string", "display": "Kontotyp"},
        "current_balance": {"path": "current_balance", "type": "currency", "display": "Aktueller Saldo"},
        "balance_date": {"path": "balance_date", "type": "date", "display": "Saldo-Datum"},
        "currency": {"path": "currency", "type": "string", "display": "Waehrung"},
        "is_active": {"path": "is_active", "type": "boolean", "display": "Aktiv"},
        "last_sync_at": {"path": "last_sync_at", "type": "date", "display": "Letzte Synchronisierung"},
    },
    "bank_transactions": {
        "id": {"path": "id", "type": "string", "display": "ID"},
        "booking_date": {"path": "booking_date", "type": "date", "display": "Buchungsdatum"},
        "value_date": {"path": "value_date", "type": "date", "display": "Valuta"},
        "amount": {"path": "amount", "type": "currency", "display": "Betrag"},
        "currency": {"path": "currency", "type": "string", "display": "Waehrung"},
        "counterparty_name": {"path": "counterparty_name", "type": "string", "display": "Gegenpartei"},
        "counterparty_iban": {"path": "counterparty_iban", "type": "string", "display": "Gegenpartei-IBAN"},
        "reference_text": {"path": "reference_text", "type": "string", "display": "Verwendungszweck"},
        "transaction_type": {"path": "transaction_type", "type": "string", "display": "Transaktionstyp"},
        "booking_text": {"path": "booking_text", "type": "string", "display": "Buchungstext"},
        "reconciliation_status": {"path": "reconciliation_status", "type": "string", "display": "Abgleich-Status"},
        "match_confidence": {"path": "match_confidence", "type": "number", "display": "Match-Konfidenz"},
        "matched_invoice_number": {"path": "matched_invoice_number", "type": "string", "display": "Zugeordnete Rechnungsnr."},
    },
    "expenses": {
        "id": {"path": "id", "type": "string", "display": "ID"},
        "report_number": {"path": "report_number", "type": "string", "display": "Abrechnungsnummer"},
        "title": {"path": "title", "type": "string", "display": "Titel"},
        "period_start": {"path": "period_start", "type": "date", "display": "Zeitraum von"},
        "period_end": {"path": "period_end", "type": "date", "display": "Zeitraum bis"},
        "employee_name": {"path": "employee_name", "type": "string", "display": "Mitarbeiter"},
        "total_amount": {"path": "total_amount", "type": "currency", "display": "Gesamtbetrag"},
        "total_vat": {"path": "total_vat", "type": "currency", "display": "MwSt-Gesamt"},
        "total_deductible": {"path": "total_deductible", "type": "currency", "display": "Abzugsfaehig"},
        "travel_days": {"path": "travel_days", "type": "number", "display": "Reisetage"},
        "travel_allowance_total": {"path": "travel_allowance_total", "type": "currency", "display": "Verpflegungspauschale"},
        "total_kilometers": {"path": "total_kilometers", "type": "number", "display": "Gefahrene km"},
        "mileage_allowance_total": {"path": "mileage_allowance_total", "type": "currency", "display": "Kilometergeld"},
        "status": {"path": "status", "type": "string", "display": "Status"},
        "submitted_at": {"path": "submitted_at", "type": "date", "display": "Eingereicht am"},
        "approved_at": {"path": "approved_at", "type": "date", "display": "Genehmigt am"},
        "created_at": {"path": "created_at", "type": "date", "display": "Erstellt am"},
    },
    "expense_items": {
        "id": {"path": "id", "type": "string", "display": "ID"},
        "expense_type": {"path": "expense_type", "type": "string", "display": "Ausgabentyp"},
        "expense_date": {"path": "expense_date", "type": "date", "display": "Datum"},
        "amount": {"path": "amount", "type": "currency", "display": "Betrag"},
        "currency": {"path": "currency", "type": "string", "display": "Waehrung"},
        "tax_rate": {"path": "tax_rate", "type": "number", "display": "Steuersatz"},
        "tax_amount": {"path": "tax_amount", "type": "currency", "display": "Steuerbetrag"},
        "net_amount": {"path": "net_amount", "type": "currency", "display": "Nettobetrag"},
        "is_deductible": {"path": "is_deductible", "type": "boolean", "display": "Abzugsfaehig"},
        "deductible_percentage": {"path": "deductible_percentage", "type": "number", "display": "Abzugsfaehig %"},
        "deductible_amount": {"path": "deductible_amount", "type": "currency", "display": "Abzugsfaehiger Betrag"},
    },
}


class ReportBuilderService:
    """Service fuer Report-Query-Erstellung und Ausfuehrung."""

    _instance: Optional["ReportBuilderService"] = None

    def __new__(cls) -> "ReportBuilderService":
        """Singleton-Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_available_fields(self, data_source: str) -> List[Dict[str, Any]]:
        """Gibt verfuegbare Felder fuer eine Datenquelle zurueck."""
        fields = FIELD_DEFINITIONS.get(data_source, {})
        result = []

        for field_path, field_info in fields.items():
            result.append({
                "path": field_path,
                "display_name": field_info.get("display", field_path),
                "data_type": field_info.get("type", "string"),
                "category": self._get_field_category(field_path),
            })

        return sorted(result, key=lambda x: (x["category"], x["display_name"]))

    def get_available_data_sources(self) -> List[Dict[str, Any]]:
        """Gibt verfuegbare Datenquellen zurueck."""
        return [
            {"id": "documents", "name": "Alle Dokumente", "description": "Alle hochgeladenen Dokumente"},
            {"id": "invoices", "name": "Rechnungen", "description": "Nur Rechnungsdokumente"},
            {"id": "entities", "name": "Geschaeftspartner", "description": "Kunden und Lieferanten"},
            {"id": "bank_accounts", "name": "Bankkonten", "description": "Verknuepfte Bankkonten"},
            {"id": "bank_transactions", "name": "Kontobewegungen", "description": "Banktransaktionen und Buchungen"},
            {"id": "expenses", "name": "Spesenabrechnungen", "description": "Reisekosten und Spesenabrechnungen"},
            {"id": "expense_items", "name": "Spesenpositionen", "description": "Einzelne Positionen der Spesenabrechnungen"},
        ]

    def get_available_operators(self) -> List[Dict[str, Any]]:
        """Gibt verfuegbare Filter-Operatoren zurueck."""
        return [
            {"id": "eq", "name": "gleich", "types": ["string", "number", "date", "boolean"]},
            {"id": "ne", "name": "ungleich", "types": ["string", "number", "date", "boolean"]},
            {"id": "gt", "name": "groesser als", "types": ["number", "date", "currency"]},
            {"id": "gte", "name": "groesser oder gleich", "types": ["number", "date", "currency"]},
            {"id": "lt", "name": "kleiner als", "types": ["number", "date", "currency"]},
            {"id": "lte", "name": "kleiner oder gleich", "types": ["number", "date", "currency"]},
            {"id": "contains", "name": "enthaelt", "types": ["string"]},
            {"id": "starts_with", "name": "beginnt mit", "types": ["string"]},
            {"id": "ends_with", "name": "endet mit", "types": ["string"]},
            {"id": "in", "name": "in Liste", "types": ["string", "number"]},
            {"id": "between", "name": "zwischen", "types": ["number", "date", "currency"]},
            {"id": "is_null", "name": "ist leer", "types": ["string", "number", "date"]},
            {"id": "is_not_null", "name": "ist nicht leer", "types": ["string", "number", "date"]},
        ]

    def get_available_aggregations(self) -> List[Dict[str, Any]]:
        """Gibt verfuegbare Aggregationen zurueck."""
        return [
            {"id": "sum", "name": "Summe", "types": ["number", "currency"]},
            {"id": "avg", "name": "Durchschnitt", "types": ["number", "currency"]},
            {"id": "count", "name": "Anzahl", "types": ["string", "number", "date", "boolean"]},
            {"id": "min", "name": "Minimum", "types": ["number", "date", "currency"]},
            {"id": "max", "name": "Maximum", "types": ["number", "date", "currency"]},
        ]

    async def execute_report(
        self,
        db: AsyncSession,
        template: ReportTemplate,
        user_id: uuid.UUID,
        runtime_filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> ReportResult:
        """Fuehrt einen Report aus."""
        logger.info(
            "executing_report",
            template_id=str(template.id),
            template_name=template.name,
            data_source=template.data_source,
            user_id=str(user_id),
        )

        # Model fuer Datenquelle holen
        model = DATA_SOURCE_MODELS.get(template.data_source)
        if not model:
            raise ValueError(f"Unbekannte Datenquelle: {template.data_source}")

        # Basis-Query
        query = select(model)

        # Spezial-Filter fuer invoices
        if template.data_source == "invoices":
            query = query.where(model.document_type.in_(["invoice", "rechnung"]))

        # Filter anwenden
        filters_applied = []
        for filter_obj in template.filters:
            filter_condition = self._build_filter_condition(model, filter_obj, runtime_filters)
            if filter_condition is not None:
                query = query.where(filter_condition)
                filters_applied.append({
                    "field": filter_obj.field_path,
                    "operator": filter_obj.operator,
                    "value": filter_obj.value,
                })

        # Sortierung anwenden
        if template.sort_config:
            for sort_item in template.sort_config:
                sort_field = sort_item.get("field")
                direction = sort_item.get("direction", "asc")
                column = self._get_model_column(model, sort_field)
                if column is not None:
                    if direction == "desc":
                        query = query.order_by(desc(column))
                    else:
                        query = query.order_by(column)

        # Count Query fuer Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        # Pagination
        if limit:
            query = query.limit(limit)
        query = query.offset(offset)

        # Ausfuehren
        result = await db.execute(query)
        rows = list(result.scalars().all())

        # Spalten-Informationen
        columns = [
            {
                "field_path": col.field_path,
                "display_name": col.display_name,
                "data_type": col.data_type,
                "format_pattern": col.format_pattern,
                "aggregation": col.aggregation,
            }
            for col in template.columns
            if col.is_visible
        ]

        # Zeilen extrahieren
        report_rows = []
        for row in rows:
            row_data = {}
            for col in template.columns:
                if col.is_visible:
                    value = self._extract_field_value(row, col.field_path, template.data_source)
                    row_data[col.field_path] = value
            report_rows.append(ReportRow(data=row_data))

        # Aggregationen berechnen
        aggregations = await self._calculate_aggregations(
            db, model, template, runtime_filters
        )

        logger.info(
            "report_executed",
            template_id=str(template.id),
            row_count=len(report_rows),
            total_count=total_count,
        )

        return ReportResult(
            template_id=template.id,
            template_name=template.name,
            columns=columns,
            rows=report_rows,
            total_count=total_count,
            aggregations=aggregations,
            filters_applied=filters_applied,
        )

    async def preview_report(
        self,
        db: AsyncSession,
        template: ReportTemplate,
        limit: int = 10,
    ) -> PreviewResult:
        """Erstellt eine schnelle Vorschau mit limitierten Daten."""
        model = DATA_SOURCE_MODELS.get(template.data_source)
        if not model:
            raise ValueError(f"Unbekannte Datenquelle: {template.data_source}")

        # Einfache Query ohne Filter
        query = select(model)

        if template.data_source == "invoices":
            query = query.where(model.document_type.in_(["invoice", "rechnung"]))

        query = query.limit(limit)

        # Count Query
        count_query = select(func.count()).select_from(
            select(model).where(
                model.document_type.in_(["invoice", "rechnung"])
                if template.data_source == "invoices"
                else True
            ).subquery()
        )
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        result = await db.execute(query)
        rows = list(result.scalars().all())

        columns = [
            {
                "field_path": col.field_path,
                "display_name": col.display_name,
                "data_type": col.data_type,
            }
            for col in template.columns
            if col.is_visible
        ]

        sample_rows = []
        for row in rows:
            row_data = {}
            for col in template.columns:
                if col.is_visible:
                    value = self._extract_field_value(row, col.field_path, template.data_source)
                    row_data[col.field_path] = value
            sample_rows.append(ReportRow(data=row_data))

        return PreviewResult(
            template_id=template.id,
            columns=columns,
            sample_rows=sample_rows,
            total_count=total_count,
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_field_category(self, field_path: str) -> str:
        """Kategorisiert ein Feld."""
        if field_path.startswith("extracted_data."):
            return "Extrahierte Daten"
        elif field_path in ["created_at", "updated_at"]:
            return "Zeitstempel"
        elif field_path in ["id", "filename", "status", "document_type"]:
            return "Basis"
        else:
            return "Sonstige"

    def _get_model_column(self, model: Type, field_path: str) -> Optional[object]:
        """Holt die SQLAlchemy-Spalte fuer ein Feld.

        Returns:
            SQLAlchemy column object or None if not found
        """
        field_def = FIELD_DEFINITIONS.get("documents", {}).get(field_path, {})
        path = field_def.get("path", field_path)
        json_key = field_def.get("json_key")

        if json_key and hasattr(model, path):
            # JSONB-Feld
            return getattr(model, path)[json_key]
        elif hasattr(model, path):
            return getattr(model, path)
        elif hasattr(model, field_path):
            return getattr(model, field_path)

        return None

    def _build_filter_condition(
        self,
        model: Type,
        filter_obj: ReportFilter,
        runtime_filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[object]:
        """Baut eine Filter-Bedingung.

        Returns:
            SQLAlchemy filter condition or None if field not found
        """
        column = self._get_model_column(model, filter_obj.field_path)
        if column is None:
            logger.warning(f"Unknown filter field: {filter_obj.field_path}")
            return None

        # Dynamische Werte aufloesen
        value = filter_obj.value
        if filter_obj.is_dynamic and filter_obj.dynamic_source:
            value = self._resolve_dynamic_value(filter_obj.dynamic_source, runtime_filters)

        # Operator anwenden
        operator = filter_obj.operator

        if operator == "eq":
            return column == value
        elif operator == "ne":
            return column != value
        elif operator == "gt":
            return column > value
        elif operator == "gte":
            return column >= value
        elif operator == "lt":
            return column < value
        elif operator == "lte":
            return column <= value
        elif operator == "contains":
            return cast(column, String).ilike(f"%{value}%")
        elif operator == "starts_with":
            return cast(column, String).ilike(f"{value}%")
        elif operator == "ends_with":
            return cast(column, String).ilike(f"%{value}")
        elif operator == "in":
            if isinstance(value, list):
                return column.in_(value)
            return column == value
        elif operator == "between":
            if isinstance(value, list) and len(value) == 2:
                return and_(column >= value[0], column <= value[1])
            return None
        elif operator == "is_null":
            return column.is_(None)
        elif operator == "is_not_null":
            return column.isnot(None)

        return None

    def _resolve_dynamic_value(
        self,
        dynamic_source: str,
        runtime_filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[Union[date, List[date], Any]]:
        """Loest dynamische Werte auf.

        Returns:
            Resolved value (date, list of dates, or runtime filter value)
        """
        now = datetime.now(timezone.utc)
        today = now.date()

        if dynamic_source == "today":
            return today
        elif dynamic_source == "yesterday":
            return today - timedelta(days=1)
        elif dynamic_source == "last_7_days":
            return [today - timedelta(days=7), today]
        elif dynamic_source == "last_30_days":
            return [today - timedelta(days=30), today]
        elif dynamic_source == "this_month":
            start = today.replace(day=1)
            return [start, today]
        elif dynamic_source == "last_month":
            first_of_month = today.replace(day=1)
            last_month_end = first_of_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            return [last_month_start, last_month_end]
        elif dynamic_source == "this_year":
            start = today.replace(month=1, day=1)
            return [start, today]
        elif dynamic_source.startswith("param:") and runtime_filters:
            param_name = dynamic_source[6:]
            return runtime_filters.get(param_name)

        return None

    def _extract_field_value(
        self,
        row: Any,
        field_path: str,
        data_source: str,
    ) -> Union[str, int, float, bool, None]:
        """Extrahiert einen Feldwert aus einer Zeile.

        Returns:
            Extracted value (serializable types for JSON response)
        """
        field_defs = FIELD_DEFINITIONS.get(data_source, {})
        field_def = field_defs.get(field_path, {})

        path = field_def.get("path", field_path)
        json_key = field_def.get("json_key")

        try:
            if json_key:
                # JSONB-Feld
                json_data = getattr(row, path, None)
                if json_data and isinstance(json_data, dict):
                    return json_data.get(json_key)
                return None
            else:
                value = getattr(row, path, None)

                # Typ-Konvertierung
                if isinstance(value, datetime):
                    return value.isoformat()
                elif isinstance(value, date):
                    return value.isoformat()
                elif isinstance(value, Decimal):
                    return float(value)
                elif isinstance(value, uuid.UUID):
                    return str(value)

                return value
        except Exception as e:
            logger.warning(f"Error extracting field {field_path}: {e}")
            return None

    async def _calculate_aggregations(
        self,
        db: AsyncSession,
        model: Type,
        template: ReportTemplate,
        runtime_filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Berechnet Aggregationen fuer einen Report."""
        aggregations = {}

        for col in template.columns:
            if not col.aggregation or col.aggregation == "none":
                continue

            column = self._get_model_column(model, col.field_path)
            if column is None:
                continue

            agg_func = None
            if col.aggregation == "sum":
                agg_func = func.sum(column)
            elif col.aggregation == "avg":
                agg_func = func.avg(column)
            elif col.aggregation == "count":
                agg_func = func.count(column)
            elif col.aggregation == "min":
                agg_func = func.min(column)
            elif col.aggregation == "max":
                agg_func = func.max(column)

            if agg_func:
                query = select(agg_func)

                # Filter anwenden
                for filter_obj in template.filters:
                    filter_condition = self._build_filter_condition(model, filter_obj, runtime_filters)
                    if filter_condition is not None:
                        query = query.where(filter_condition)

                result = await db.execute(query)
                value = result.scalar()

                if isinstance(value, Decimal):
                    value = float(value)

                aggregations[col.field_path] = {
                    "type": col.aggregation,
                    "value": value,
                }

        return aggregations if aggregations else None

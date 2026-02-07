# -*- coding: utf-8 -*-
"""Condition Evaluator fuer Workflows.

Wiederverwendbare Bedingungsauswertung.
Erweitert ImportRuleService-Logik fuer Workflows.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Union, TYPE_CHECKING

# Type alias for field values returned from document context
FieldValue = Union[str, int, float, bool, list, dict, None]

import structlog

if TYPE_CHECKING:
    from app.services.workflow.workflow_execution_service import ExecutionContext


logger = structlog.get_logger(__name__)


class ConditionEvaluator:
    """Wiederverwendbare Bedingungsauswertung.

    Erweitert ImportRuleService-Logik fuer Workflows.
    Unterstuetzt AND/OR-Verschachtelung und 20+ Operatoren.
    """

    # Operatoren (wiederverwendet von ImportRuleService + Erweiterungen)
    OPERATORS = {
        # String-Operatoren
        "equals": lambda a, b: str(a).lower() == str(b).lower() if a is not None else False,
        "not_equals": lambda a, b: str(a).lower() != str(b).lower() if a is not None else True,
        "contains": lambda a, b: str(b).lower() in str(a).lower() if a is not None else False,
        "not_contains": lambda a, b: str(b).lower() not in str(a).lower() if a is not None else True,
        "starts_with": lambda a, b: str(a).lower().startswith(str(b).lower()) if a is not None else False,
        "ends_with": lambda a, b: str(a).lower().endswith(str(b).lower()) if a is not None else False,
        "regex": lambda a, b: bool(re.match(b, str(a), re.IGNORECASE)) if a is not None else False,

        # Numerische Operatoren
        "greater_than": lambda a, b: _safe_float(a) > _safe_float(b),
        "greater_equal": lambda a, b: _safe_float(a) >= _safe_float(b),
        "less_than": lambda a, b: _safe_float(a) < _safe_float(b),
        "less_equal": lambda a, b: _safe_float(a) <= _safe_float(b),

        # List-Operatoren
        "in_list": lambda a, b: a in (b if isinstance(b, list) else [b]),
        "not_in_list": lambda a, b: a not in (b if isinstance(b, list) else [b]),

        # Null-Operatoren
        "is_empty": lambda a, b: not a,
        "is_not_empty": lambda a, b: bool(a),
        "exists": lambda a, b: a is not None,
        "not_exists": lambda a, b: a is None,
        "is_null": lambda a, b: a is None,
        "is_not_null": lambda a, b: a is not None,

        # Boolean-Operatoren
        "is_true": lambda a, b: a is True or str(a).lower() in ("true", "1", "yes", "ja"),
        "is_false": lambda a, b: a is False or str(a).lower() in ("false", "0", "no", "nein"),

        # Workflow-spezifische Operatoren (fuer Feldaenderungen)
        "changed": lambda context, field: _check_changed(context, field),
        "changed_to": lambda a, b: a == b,  # Aktueller Wert == Zielwert
        "changed_from": lambda context, field_old_value: _check_changed_from(context, field_old_value),
    }

    # Verfuegbare Felder fuer Workflows
    AVAILABLE_FIELDS = {
        # Dokument-Felder
        "document.id": "Dokument-ID",
        "document.filename": "Dateiname",
        "document.file_extension": "Dateiendung",
        "document.file_size": "Dateigroesse (Bytes)",
        "document.mime_type": "MIME-Type",
        "document.status": "Status",
        "document.document_type": "Dokumenttyp",
        "document.folder_id": "Ordner-ID",
        "document.created_at": "Erstellt am",
        "document.processed_at": "Verarbeitet am",

        # Extrahierte Daten
        "extracted_data.invoice_number": "Rechnungsnummer",
        "extracted_data.order_number": "Bestellnummer",
        "extracted_data.total_gross": "Bruttobetrag",
        "extracted_data.total_net": "Nettobetrag",
        "extracted_data.tax_rate": "Steuersatz",
        "extracted_data.vendor_name": "Lieferant",
        "extracted_data.customer_name": "Kunde",
        "extracted_data.invoice_date": "Rechnungsdatum",
        "extracted_data.due_date": "Faelligkeitsdatum",

        # OCR-Felder
        "ocr.backend": "OCR-Backend",
        "ocr.confidence": "OCR-Konfidenz",
        "ocr.text_length": "Textlaenge",

        # AI-Felder
        "ai.confidence": "KI-Konfidenz",
        "ai.category": "KI-Kategorie",
        "ai.is_duplicate": "Ist Duplikat",

        # Workflow-Variablen
        "variable.*": "Workflow-Variable",

        # Trigger-Kontext
        "trigger.type": "Trigger-Typ",
        "trigger.source": "Trigger-Quelle",
        "trigger.user_id": "Trigger-User",
    }

    def __init__(self) -> None:
        """Initialisiert den ConditionEvaluator."""
        pass

    def evaluate(
        self,
        conditions: Dict[str, Any],
        context: "ExecutionContext",
    ) -> bool:
        """Evaluiert Bedingungen gegen den Ausfuehrungskontext.

        Args:
            conditions: Bedingungs-Struktur (AND/OR mit rules)
            context: Ausfuehrungskontext mit Dokument, Variablen, etc.

        Returns:
            True wenn alle Bedingungen erfuellt sind
        """
        if not conditions:
            return True

        operator = conditions.get("operator", "AND").upper()
        rules = conditions.get("rules", [])

        if not rules:
            # Einzelne Regel ohne Verschachtelung
            return self._evaluate_single_rule(conditions, context)

        results = []
        for rule in rules:
            if "operator" in rule and "rules" in rule:
                # Verschachtelte Gruppe
                results.append(self.evaluate(rule, context))
            else:
                # Einzelne Regel
                results.append(self._evaluate_single_rule(rule, context))

        if operator == "AND":
            return all(results)
        elif operator == "OR":
            return any(results)
        else:
            logger.warning("unknown_condition_operator", operator=operator)
            return False

    def _evaluate_single_rule(
        self,
        rule: Dict[str, Any],
        context: "ExecutionContext",
    ) -> bool:
        """Evaluiert eine einzelne Regel.

        Args:
            rule: Regel mit field, operator, value
            context: Ausfuehrungskontext

        Returns:
            True wenn Regel erfuellt
        """
        field = rule.get("field", "")
        operator = rule.get("operator", "equals")
        expected_value = rule.get("value")

        try:
            # Hole aktuellen Wert aus Kontext
            actual_value = self.get_field_value(field, context)

            # Hole Operator-Funktion
            op_func = self.OPERATORS.get(operator)
            if not op_func:
                logger.warning("unknown_operator", operator=operator, field=field)
                return False

            # Evaluiere
            result = op_func(actual_value, expected_value)

            logger.debug(
                "condition_evaluated",
                field=field,
                operator=operator,
                expected=expected_value,
                actual=actual_value,
                result=result,
            )

            return result

        except Exception as e:
            logger.error(
                "condition_evaluation_error",
                field=field,
                operator=operator,
                **safe_error_log(e),
            )
            return False

    def get_field_value(
        self,
        field: str,
        context: "ExecutionContext",
    ) -> FieldValue:
        """Holt den Wert eines Feldes aus dem Kontext.

        Args:
            field: Feldpfad (z.B. "document.filename", "extracted_data.total_gross")
            context: Ausfuehrungskontext

        Returns:
            Feldwert oder None
        """
        if not field:
            return None

        parts = field.split(".")

        if parts[0] == "document":
            return self._get_document_field(parts[1:], context)
        elif parts[0] == "extracted_data":
            return self._get_extracted_data_field(parts[1:], context)
        elif parts[0] == "ocr":
            return self._get_ocr_field(parts[1:], context)
        elif parts[0] == "ai":
            return self._get_ai_field(parts[1:], context)
        elif parts[0] == "variable":
            return self._get_variable(parts[1:], context)
        elif parts[0] == "trigger":
            return self._get_trigger_field(parts[1:], context)
        elif parts[0] == "step":
            return self._get_step_output(parts[1:], context)
        else:
            # Versuche direkten Zugriff auf context.data
            return _get_nested_value(context.data, parts)

    def _get_document_field(
        self,
        path: List[str],
        context: "ExecutionContext",
    ) -> FieldValue:
        """Holt Dokument-Feld aus Kontext."""
        if not context.document_data:
            return None

        if not path:
            return context.document_data

        return _get_nested_value(context.document_data, path)

    def _get_extracted_data_field(
        self,
        path: List[str],
        context: "ExecutionContext",
    ) -> FieldValue:
        """Holt extrahierte Daten aus Kontext."""
        extracted = context.document_data.get("extracted_data", {}) if context.document_data else {}
        if not path:
            return extracted
        return _get_nested_value(extracted, path)

    def _get_ocr_field(
        self,
        path: List[str],
        context: "ExecutionContext",
    ) -> FieldValue:
        """Holt OCR-Feld aus Kontext."""
        ocr_data = context.data.get("ocr", {})
        if not path:
            return ocr_data
        return _get_nested_value(ocr_data, path)

    def _get_ai_field(
        self,
        path: List[str],
        context: "ExecutionContext",
    ) -> FieldValue:
        """Holt AI-Feld aus Kontext."""
        ai_data = context.data.get("ai", {})
        if not path:
            return ai_data
        return _get_nested_value(ai_data, path)

    def _get_variable(
        self,
        path: List[str],
        context: "ExecutionContext",
    ) -> FieldValue:
        """Holt Workflow-Variable aus Kontext."""
        if not path:
            return context.variables
        return _get_nested_value(context.variables, path)

    def _get_trigger_field(
        self,
        path: List[str],
        context: "ExecutionContext",
    ) -> FieldValue:
        """Holt Trigger-Feld aus Kontext."""
        trigger_data = context.trigger_data or {}
        if not path:
            return trigger_data
        return _get_nested_value(trigger_data, path)

    def _get_step_output(
        self,
        path: List[str],
        context: "ExecutionContext",
    ) -> FieldValue:
        """Holt Output eines vorherigen Steps."""
        if not path:
            return context.step_outputs
        step_name = path[0]
        remaining = path[1:]
        step_output = context.step_outputs.get(step_name, {})
        if not remaining:
            return step_output
        return _get_nested_value(step_output, remaining)

    def get_available_operators(self) -> List[Dict[str, str]]:
        """Gibt verfuegbare Operatoren zurueck.

        Returns:
            Liste von Operatoren mit Name und Beschreibung
        """
        return [
            {"id": "equals", "name": "Gleich", "description": "Wert ist gleich"},
            {"id": "not_equals", "name": "Ungleich", "description": "Wert ist ungleich"},
            {"id": "contains", "name": "Enthaelt", "description": "Text enthaelt Wert"},
            {"id": "not_contains", "name": "Enthaelt nicht", "description": "Text enthaelt Wert nicht"},
            {"id": "starts_with", "name": "Beginnt mit", "description": "Text beginnt mit Wert"},
            {"id": "ends_with", "name": "Endet mit", "description": "Text endet mit Wert"},
            {"id": "regex", "name": "Regex", "description": "Regulaerer Ausdruck"},
            {"id": "greater_than", "name": "Groesser als", "description": "Zahl ist groesser"},
            {"id": "greater_equal", "name": "Groesser gleich", "description": "Zahl ist groesser oder gleich"},
            {"id": "less_than", "name": "Kleiner als", "description": "Zahl ist kleiner"},
            {"id": "less_equal", "name": "Kleiner gleich", "description": "Zahl ist kleiner oder gleich"},
            {"id": "in_list", "name": "In Liste", "description": "Wert ist in Liste enthalten"},
            {"id": "not_in_list", "name": "Nicht in Liste", "description": "Wert ist nicht in Liste"},
            {"id": "is_empty", "name": "Ist leer", "description": "Feld ist leer"},
            {"id": "is_not_empty", "name": "Ist nicht leer", "description": "Feld hat Wert"},
            {"id": "is_null", "name": "Ist null", "description": "Feld existiert nicht"},
            {"id": "is_not_null", "name": "Ist nicht null", "description": "Feld existiert"},
            {"id": "is_true", "name": "Ist wahr", "description": "Boolean ist true"},
            {"id": "is_false", "name": "Ist falsch", "description": "Boolean ist false"},
        ]

    def get_available_fields(self) -> Dict[str, str]:
        """Gibt verfuegbare Felder zurueck.

        Returns:
            Dictionary mit Feldpfad -> Beschreibung
        """
        return self.AVAILABLE_FIELDS.copy()


# =============================================================================
# Hilfsfunktionen
# =============================================================================


def _safe_float(value: object) -> float:
    """Konvertiert Wert sicher zu Float."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _get_nested_value(data: Dict[str, FieldValue], path: List[str]) -> FieldValue:
    """Holt verschachtelten Wert aus Dictionary.

    Args:
        data: Dictionary
        path: Pfad als Liste von Keys

    Returns:
        Wert oder None
    """
    if not data or not path:
        return data

    current = data
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
        if current is None:
            return None

    return current


def _check_changed(context: "ExecutionContext", field: str) -> bool:
    """Prueft ob ein Feld geaendert wurde."""
    old_value = context.data.get("_old_values", {}).get(field)
    new_value = context.data.get(field)
    return old_value != new_value


def _check_changed_from(context: "ExecutionContext", field_old_value: tuple) -> bool:
    """Prueft ob ein Feld von einem bestimmten Wert geaendert wurde."""
    if not isinstance(field_old_value, (list, tuple)) or len(field_old_value) < 2:
        return False
    field, old_value = field_old_value[0], field_old_value[1]
    actual_old = context.data.get("_old_values", {}).get(field)
    return actual_old == old_value

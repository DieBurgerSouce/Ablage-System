# -*- coding: utf-8 -*-
"""
Business Rules Engine für Ablage-System.

Ermöglicht flexible, konfigurierbare Geschäftsregeln:
- Einfache Bedingungen (field > value)
- Komplexe AND/OR Logik
- Zeitbasierte Regeln (Monatsende, Quartalsende)
- ML-unterstützte Regeln (Fraud Score, Confidence)
- Aktionen: Genehmigung, Flags, Benachrichtigungen, Workflows

Phase 4 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Union, Callable
from uuid import UUID, uuid4
from enum import Enum
import re
import structlog
import operator
from app.core.safe_errors import safe_error_detail, safe_error_log
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from pydantic import BaseModel, Field, field_validator, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, User
from app.core.types import NestedValue, RuleContextDict, ConditionEvaluationDetails

logger = structlog.get_logger(__name__)

# =============================================================================
# Security: ReDoS Prevention Constants (CWE-95)
# =============================================================================

# Maximum length for regex patterns to prevent resource exhaustion
MAX_REGEX_LENGTH: int = 200

# Maximum time (seconds) for regex matching
REGEX_TIMEOUT_SECONDS: float = 1.0

# Dangerous regex patterns that can cause ReDoS
DANGEROUS_REGEX_PATTERNS: tuple[str, ...] = (
    r"\(\.\*\)\+",      # (.*)+
    r"\(\.\+\)\+",      # (.+)+
    r"\(\.\*\)\*",      # (.*)*
    r"\(\.\+\)\*",      # (.+)*
    r"\+\+",            # ++
    r"\*\*",            # **
    r"\{\d+,\}\+",      # {n,}+
    r"\(\[.+\]\+\)\+",  # ([...]+)+
    r"\(\w\+\)\+",      # (\w+)+
    r"\(\d\+\)\+",      # (\d+)+
    r"\(\s\+\)\+",      # (\s+)+
    # Allgemein: Gruppe, deren Inhalt mit *|+ endet, gefolgt von *|+ aussen.
    # Faengt (a+)+, (a*)*, (a+)*, (.*)+, ([a-z]*)+, (\w+)*, ((a+)+)+ etc. ab.
    r"\([^()]*[*+]\)[*+]",
    # Char-Klasse mit verschachteltem Quantifier: ([...]*)+ / ([...]+)+
    r"\(\[[^\]]*\][*+]\)[*+]",
    # Ueberlappende Alternation mit Quantifier: (a|a)+ / (a|aa)+
    r"\([^)]*\|[^)]*\)[*+]",
    # Gruppe mit innerem *|+ und {n,}-Wiederholung: (.*a){10,}
    r"\([^()]*[*+][^()]*\)\{\d+,?\d*\}",
)


def _is_regex_safe(pattern: str) -> tuple[bool, str]:
    """
    Validates regex pattern against ReDoS attacks.

    Args:
        pattern: The regex pattern to validate

    Returns:
        Tuple of (is_safe, error_message)
    """
    if len(pattern) > MAX_REGEX_LENGTH:
        return False, f"Regex zu lang (max {MAX_REGEX_LENGTH} Zeichen)"

    for dangerous in DANGEROUS_REGEX_PATTERNS:
        if re.search(dangerous, pattern):
            return False, "Gefährliches Regex-Pattern erkannt (ReDoS-Risiko)"

    # Try to compile to catch syntax errors
    try:
        re.compile(pattern)
    except re.error as e:
        return False, f"Ungültiges Regex-Pattern: {e}"

    return True, ""


def _safe_regex_match(
    pattern: str,
    text: str,
    flags: int = 0,
    timeout: float = REGEX_TIMEOUT_SECONDS,
) -> Optional[re.Match[str]]:
    """
    Performs regex match with timeout protection.

    Args:
        pattern: Regex pattern
        text: Text to match against
        flags: Regex flags
        timeout: Maximum execution time in seconds

    Returns:
        Match object or None if no match or timeout
    """
    def _do_match() -> Optional[re.Match[str]]:
        return re.match(pattern, text, flags)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_match)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            logger.warning(
                "regex_timeout",
                pattern_length=len(pattern),
                text_length=len(text),
            )
            return None
        except re.error:
            return None


# =============================================================================
# Enums & Types
# =============================================================================


class ConditionOperator(str, Enum):
    """Operatoren für Regel-Bedingungen."""
    # Vergleich
    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_EQUALS = ">="
    LESS_THAN = "<"
    LESS_EQUALS = "<="

    # String
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"  # Regex

    # Collection
    IN = "in"
    NOT_IN = "not_in"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"

    # Existence
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"

    # Time
    IN_PERIOD = "in_period"  # month_end, quarter_end, year_end
    BEFORE = "before"
    AFTER = "after"
    BETWEEN = "between"

    # Special
    HAS_TAG = "has_tag"
    HAS_ANY_TAG = "has_any_tag"
    HAS_ALL_TAGS = "has_all_tags"


class ActionType(str, Enum):
    """Typen von Regel-Aktionen."""
    # Genehmigung
    REQUIRE_APPROVAL = "require_approval"
    REQUIRE_CFO_APPROVAL = "require_cfo_approval"
    REQUIRE_MANAGER_APPROVAL = "require_manager_approval"

    # Flags & Status
    SET_FLAG = "set_flag"
    REMOVE_FLAG = "remove_flag"
    SET_STATUS = "set_status"
    SET_PRIORITY = "set_priority"

    # Benachrichtigung
    NOTIFY_USER = "notify_user"
    NOTIFY_TEAM = "notify_team"
    NOTIFY_ADMIN = "notify_admin"
    SEND_EMAIL = "send_email"
    SEND_SLACK = "send_slack"

    # Workflow
    START_WORKFLOW = "start_workflow"
    ASSIGN_TO_USER = "assign_to_user"
    ASSIGN_TO_TEAM = "assign_to_team"

    # Daten
    SET_FIELD = "set_field"
    ADD_TAG = "add_tag"
    REMOVE_TAG = "remove_tag"
    ADD_COMMENT = "add_comment"

    # Verarbeitung
    TRIGGER_OCR = "trigger_ocr"
    FLAG_FOR_REVIEW = "flag_for_review"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    BLOCK_PROCESSING = "block_processing"

    # Archivierung
    FLAG_FOR_ARCHIVE = "flag_for_archive"
    FLAG_FOR_PERIOD_CLOSE = "flag_for_period_close"


class RulePriority(int, Enum):
    """Priorität für Regeln."""
    CRITICAL = 100
    HIGH = 75
    NORMAL = 50
    LOW = 25
    BACKGROUND = 10


class RuleCategory(str, Enum):
    """Kategorien für Regeln."""
    APPROVAL = "approval"
    COMPLIANCE = "compliance"
    FRAUD = "fraud"
    WORKFLOW = "workflow"
    NOTIFICATION = "notification"
    DATA_QUALITY = "data_quality"
    CUSTOM = "custom"


# =============================================================================
# Models
# =============================================================================


class RuleCondition(BaseModel):
    """Eine einzelne Bedingung einer Regel."""
    field: str = Field(..., description="Feld-Pfad (z.B. 'amount', 'supplier.is_new')")
    op: ConditionOperator = Field(..., description="Operator")
    value: NestedValue = Field(default=None, description="Vergleichswert")

    # Optionale Konfiguration
    case_sensitive: bool = Field(default=False, description="Gross-/Kleinschreibung")
    negate: bool = Field(default=False, description="Bedingung negieren")

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        """Validiert Feldname gegen Injection."""
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_\.]*$", v):
            raise ValueError("Ungültiger Feldname")
        if len(v) > 100:
            raise ValueError("Feldname zu lang")
        return v


class CompositeCondition(BaseModel):
    """Kombinierte Bedingung mit AND/OR Logik."""
    and_conditions: Optional[List[Union["RuleCondition", "CompositeCondition"]]] = Field(
        default=None, alias="and"
    )
    or_conditions: Optional[List[Union["RuleCondition", "CompositeCondition"]]] = Field(
        default=None, alias="or"
    )
    not_condition: Optional[Union["RuleCondition", "CompositeCondition"]] = Field(
        default=None, alias="not"
    )

    model_config = ConfigDict(populate_by_name=True)


class RuleAction(BaseModel):
    """Eine Aktion die bei Regelerfuellung ausgeführt wird."""
    type: ActionType = Field(..., description="Aktions-Typ")
    params: Dict[str, NestedValue] = Field(default_factory=dict, description="Parameter")

    # Beispiele:
    # {"type": "require_approval", "params": {"approver_role": "cfo"}}
    # {"type": "notify_user", "params": {"user_id": "...", "message": "..."}}
    # {"type": "set_flag", "params": {"flag": "high_risk"}}
    # {"type": "add_tag", "params": {"tag": "needs_review"}}


class BusinessRule(BaseModel):
    """Eine vollständige Geschäftsregel."""
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)

    # Bedingung (einfach oder komplex)
    condition: Union[RuleCondition, CompositeCondition] = Field(
        ..., description="Regel-Bedingung"
    )

    # Aktionen bei Erfuellung
    actions: List[RuleAction] = Field(
        ..., min_length=1, description="Aktionen bei Regelerfuellung"
    )

    # Optionale Else-Aktionen
    else_actions: Optional[List[RuleAction]] = Field(
        default=None, description="Aktionen wenn Regel NICHT erfuellt"
    )

    # Konfiguration
    priority: RulePriority = Field(default=RulePriority.NORMAL)
    category: RuleCategory = Field(default=RuleCategory.CUSTOM)
    is_active: bool = Field(default=True)
    stop_on_match: bool = Field(
        default=False, description="Weitere Regeln nach Match stoppen"
    )

    # Anwendungsbereich
    applies_to_document_types: Optional[List[str]] = Field(
        default=None, description="Nur für bestimmte Dokumenttypen"
    )
    applies_to_sources: Optional[List[str]] = Field(
        default=None, description="Nur für bestimmte Quellen"
    )

    # Zeitliche Einschränkung
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by_id: Optional[UUID] = None

    # Multi-Tenant
    company_id: Optional[UUID] = None


class RuleEvaluationResult(BaseModel):
    """Ergebnis einer Regel-Auswertung."""
    rule_id: UUID
    rule_name: str
    matched: bool
    condition_details: Dict[str, object] = Field(default_factory=dict)
    triggered_actions: List[RuleAction] = Field(default_factory=list)
    execution_errors: List[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class RuleSetEvaluationResult(BaseModel):
    """Ergebnis der Auswertung aller Regeln."""
    document_id: Optional[UUID] = None
    context_snapshot: Dict[str, object] = Field(default_factory=dict)
    total_rules_evaluated: int = 0
    rules_matched: int = 0
    rule_results: List[RuleEvaluationResult] = Field(default_factory=list)
    all_triggered_actions: List[RuleAction] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Business Rules Engine
# =============================================================================


class BusinessRulesEngine:
    """Engine für Auswertung und Ausführung von Geschäftsregeln.

    Features:
    - Flexible Bedingungen mit Operatoren
    - AND/OR/NOT Logik
    - Zeitbasierte Regeln
    - Priorisierung
    - Trockenlaeufe (Dry-Run)
    - Ausführliche Ergebnisse
    """

    # Operatoren-Map
    OPERATORS: Dict[ConditionOperator, Callable[[object, object], bool]] = {
        ConditionOperator.EQUALS: operator.eq,
        ConditionOperator.NOT_EQUALS: operator.ne,
        ConditionOperator.GREATER_THAN: operator.gt,
        ConditionOperator.GREATER_EQUALS: operator.ge,
        ConditionOperator.LESS_THAN: operator.lt,
        ConditionOperator.LESS_EQUALS: operator.le,
    }

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self._custom_functions: Dict[str, Callable[..., object]] = {}
        self._action_handlers: Dict[ActionType, Callable[..., object]] = {}

    def register_function(self, name: str, func: Callable[..., object]) -> None:
        """Registriert eine benutzerdefinierte Funktion für Bedingungen."""
        self._custom_functions[name] = func

    def register_action_handler(
        self,
        action_type: ActionType,
        handler: Callable[..., object],
    ) -> None:
        """Registriert einen Handler für einen Aktionstyp."""
        self._action_handlers[action_type] = handler

    # =========================================================================
    # Rule Evaluation
    # =========================================================================

    async def evaluate_rules(
        self,
        context: Dict[str, NestedValue],
        rules: List[BusinessRule],
        dry_run: bool = False,
        document_id: Optional[UUID] = None,
    ) -> RuleSetEvaluationResult:
        """Wertet alle Regeln gegen einen Kontext aus.

        Args:
            context: Daten gegen die geprüft wird (Dokument-Felder, etc.)
            rules: Liste der zu prüfenden Regeln
            dry_run: Wenn True, werden Aktionen nicht ausgeführt
            document_id: Optional Dokument-ID für Logging

        Returns:
            RuleSetEvaluationResult mit allen Ergebnissen
        """
        result = RuleSetEvaluationResult(
            document_id=document_id,
            context_snapshot=self._sanitize_context_for_logging(context),
        )

        # Regeln nach Priorität sortieren
        sorted_rules = sorted(
            [r for r in rules if r.is_active and self._is_rule_valid(r)],
            key=lambda r: r.priority.value,
            reverse=True,
        )

        for rule in sorted_rules:
            rule_result = await self._evaluate_rule(context, rule, dry_run)
            result.rule_results.append(rule_result)
            result.total_rules_evaluated += 1

            if rule_result.matched:
                result.rules_matched += 1
                result.all_triggered_actions.extend(rule_result.triggered_actions)

                if rule.stop_on_match:
                    break

        return result

    async def evaluate_single_rule(
        self,
        context: Dict[str, NestedValue],
        rule: BusinessRule,
        dry_run: bool = True,
    ) -> RuleEvaluationResult:
        """Wertet eine einzelne Regel aus (für Tests)."""
        return await self._evaluate_rule(context, rule, dry_run)

    async def _evaluate_rule(
        self,
        context: Dict[str, NestedValue],
        rule: BusinessRule,
        dry_run: bool,
    ) -> RuleEvaluationResult:
        """Interne Methode zur Regel-Auswertung."""
        result = RuleEvaluationResult(
            rule_id=rule.id,
            rule_name=rule.name,
            matched=False,
        )

        try:
            # Bedingung auswerten
            matched, details = self._evaluate_condition(context, rule.condition)
            result.matched = matched
            result.condition_details = details

            # Aktionen bestimmen
            if matched:
                result.triggered_actions = rule.actions
            elif rule.else_actions:
                result.triggered_actions = rule.else_actions

            # Aktionen ausführen (wenn nicht dry_run)
            if not dry_run and result.triggered_actions:
                errors = await self._execute_actions(
                    context, result.triggered_actions
                )
                result.execution_errors = errors

        except Exception as e:
            logger.error(f"Fehler bei Regel-Auswertung '{rule.name}': {e}")
            result.execution_errors.append(safe_error_detail(e, "Regel"))

        return result

    def _evaluate_condition(
        self,
        context: Dict[str, NestedValue],
        condition: Union[RuleCondition, CompositeCondition],
    ) -> tuple[bool, Dict[str, NestedValue]]:
        """Wertet eine Bedingung rekursiv aus."""
        if isinstance(condition, RuleCondition):
            return self._evaluate_simple_condition(context, condition)
        elif isinstance(condition, CompositeCondition):
            return self._evaluate_composite_condition(context, condition)
        else:
            # Fallback für dict-Struktur
            if isinstance(condition, dict):
                if "and" in condition:
                    return self._evaluate_composite_condition(
                        context,
                        CompositeCondition(and_conditions=condition["and"])
                    )
                elif "or" in condition:
                    return self._evaluate_composite_condition(
                        context,
                        CompositeCondition(or_conditions=condition["or"])
                    )
                elif "field" in condition:
                    return self._evaluate_simple_condition(
                        context,
                        RuleCondition(**condition)
                    )
            return False, {"error": "Unbekannter Bedingungstyp"}

    def _evaluate_simple_condition(
        self,
        context: Dict[str, NestedValue],
        condition: RuleCondition,
    ) -> tuple[bool, Dict[str, NestedValue]]:
        """Wertet eine einfache Bedingung aus."""
        details = {
            "field": condition.field,
            "operator": condition.op.value,
            "expected": condition.value,
        }

        # Feldwert holen
        field_value = self._get_nested_value(context, condition.field)
        details["actual"] = field_value

        # Operator anwenden
        result = self._apply_operator(
            condition.op,
            field_value,
            condition.value,
            condition.case_sensitive,
        )

        # Negieren falls gewünscht
        if condition.negate:
            result = not result

        details["matched"] = result
        return result, details

    def _evaluate_composite_condition(
        self,
        context: Dict[str, NestedValue],
        condition: CompositeCondition,
    ) -> tuple[bool, Dict[str, NestedValue]]:
        """Wertet eine zusammengesetzte Bedingung aus."""
        details: Dict[str, NestedValue] = {"type": "composite", "sub_conditions": []}

        if condition.and_conditions:
            details["logic"] = "AND"
            all_matched = True
            for sub in condition.and_conditions:
                matched, sub_details = self._evaluate_condition(context, sub)
                details["sub_conditions"].append(sub_details)
                if not matched:
                    all_matched = False
                    # Bei AND: Frühzeitiger Abbruch möglich
            details["matched"] = all_matched
            return all_matched, details

        elif condition.or_conditions:
            details["logic"] = "OR"
            any_matched = False
            for sub in condition.or_conditions:
                matched, sub_details = self._evaluate_condition(context, sub)
                details["sub_conditions"].append(sub_details)
                if matched:
                    any_matched = True
                    # Bei OR: Frühzeitiger Abbruch möglich
            details["matched"] = any_matched
            return any_matched, details

        elif condition.not_condition:
            details["logic"] = "NOT"
            matched, sub_details = self._evaluate_condition(
                context, condition.not_condition
            )
            details["sub_conditions"].append(sub_details)
            details["matched"] = not matched
            return not matched, details

        return False, {"error": "Leere Composite-Bedingung"}

    def _apply_operator(
        self,
        op: ConditionOperator,
        actual: NestedValue,
        expected: NestedValue,
        case_sensitive: bool = False,
    ) -> bool:
        """Wendet einen Operator auf Werte an."""
        # None-Handling
        if op == ConditionOperator.IS_NULL:
            return actual is None
        if op == ConditionOperator.IS_NOT_NULL:
            return actual is not None

        # Wenn actual None ist, schlagen die meisten Operatoren fehl
        if actual is None:
            return False

        # Leere Collection Checks
        if op == ConditionOperator.IS_EMPTY:
            return len(actual) == 0 if hasattr(actual, "__len__") else False
        if op == ConditionOperator.IS_NOT_EMPTY:
            return len(actual) > 0 if hasattr(actual, "__len__") else bool(actual)

        # Standard-Vergleiche
        if op in self.OPERATORS:
            try:
                # Numerische Konvertierung versuchen
                if isinstance(expected, (int, float, Decimal)):
                    actual = self._to_number(actual)
                return self.OPERATORS[op](actual, expected)
            except (TypeError, ValueError):
                return False

        # String-Operatoren
        if op in [
            ConditionOperator.CONTAINS,
            ConditionOperator.NOT_CONTAINS,
            ConditionOperator.STARTS_WITH,
            ConditionOperator.ENDS_WITH,
            ConditionOperator.MATCHES,
        ]:
            return self._apply_string_operator(
                op, str(actual), str(expected), case_sensitive
            )

        # Collection-Operatoren
        if op == ConditionOperator.IN:
            if isinstance(expected, (list, tuple, set)):
                return actual in expected
            return str(actual) in str(expected)

        if op == ConditionOperator.NOT_IN:
            if isinstance(expected, (list, tuple, set)):
                return actual not in expected
            return str(actual) not in str(expected)

        # Zeit-Operatoren
        if op == ConditionOperator.IN_PERIOD:
            return self._check_time_period(actual, expected)

        if op in [ConditionOperator.BEFORE, ConditionOperator.AFTER]:
            return self._compare_dates(op, actual, expected)

        if op == ConditionOperator.BETWEEN:
            return self._check_between(actual, expected)

        # Tag-Operatoren
        if op == ConditionOperator.HAS_TAG:
            tags = actual if isinstance(actual, list) else []
            return expected in tags

        if op == ConditionOperator.HAS_ANY_TAG:
            tags = actual if isinstance(actual, list) else []
            expected_tags = expected if isinstance(expected, list) else [expected]
            return any(t in tags for t in expected_tags)

        if op == ConditionOperator.HAS_ALL_TAGS:
            tags = actual if isinstance(actual, list) else []
            expected_tags = expected if isinstance(expected, list) else [expected]
            return all(t in tags for t in expected_tags)

        return False

    def _apply_string_operator(
        self,
        op: ConditionOperator,
        actual: str,
        expected: str,
        case_sensitive: bool,
    ) -> bool:
        """Wendet String-Operatoren an."""
        if not case_sensitive:
            actual = actual.lower()
            expected = expected.lower()

        if op == ConditionOperator.CONTAINS:
            return expected in actual
        if op == ConditionOperator.NOT_CONTAINS:
            return expected not in actual
        if op == ConditionOperator.STARTS_WITH:
            return actual.startswith(expected)
        if op == ConditionOperator.ENDS_WITH:
            return actual.endswith(expected)
        if op == ConditionOperator.MATCHES:
            # Security: Validate regex pattern against ReDoS (CWE-95)
            is_safe, error_msg = _is_regex_safe(expected)
            if not is_safe:
                logger.warning(
                    "unsafe_regex_pattern_rejected",
                    reason=error_msg,
                    pattern_length=len(expected),
                )
                return False

            # Execute with timeout protection
            flags = 0 if case_sensitive else re.IGNORECASE
            match = _safe_regex_match(expected, actual, flags)
            return match is not None

        return False

    def _check_time_period(self, actual: NestedValue, period: str) -> bool:
        """Prüft ob Datum in einer Zeitperiode liegt."""
        try:
            if isinstance(actual, str):
                actual = datetime.fromisoformat(actual.replace("Z", "+00:00"))
            elif isinstance(actual, date) and not isinstance(actual, datetime):
                actual = datetime.combine(actual, datetime.min.time())

            if not isinstance(actual, datetime):
                return False

            if period == "month_end":
                # Letzte 3 Tage des Monats
                next_month = actual.replace(day=28) + timedelta(days=4)
                last_day = next_month - timedelta(days=next_month.day)
                return actual.day >= last_day.day - 2

            if period == "quarter_end":
                # Letzter Monat des Quartals
                return actual.month in [3, 6, 9, 12] and actual.day >= 25

            if period == "year_end":
                # Dezember
                return actual.month == 12 and actual.day >= 25

            if period == "week_start":
                return actual.weekday() == 0  # Montag

            if period == "weekend":
                return actual.weekday() >= 5  # Samstag oder Sonntag

        except Exception as e:
            logger.debug("time_period_check_failed: %s", type(e).__name__)

        return False

    def _compare_dates(
        self,
        op: ConditionOperator,
        actual: NestedValue,
        expected: NestedValue,
    ) -> bool:
        """Vergleicht Datumsangaben."""
        try:
            if isinstance(actual, str):
                actual = datetime.fromisoformat(actual.replace("Z", "+00:00"))
            if isinstance(expected, str):
                expected = datetime.fromisoformat(expected.replace("Z", "+00:00"))

            if op == ConditionOperator.BEFORE:
                return actual < expected
            if op == ConditionOperator.AFTER:
                return actual > expected

        except Exception as e:
            logger.debug("date_comparison_failed: %s", type(e).__name__)

        return False

    def _check_between(self, actual: NestedValue, expected: NestedValue) -> bool:
        """Prüft ob Wert zwischen zwei Grenzen liegt."""
        try:
            if isinstance(expected, (list, tuple)) and len(expected) == 2:
                lower, upper = expected
                actual = self._to_number(actual)
                return lower <= actual <= upper
        except Exception as e:
            logger.debug("between_check_failed: %s", type(e).__name__)
        return False

    # =========================================================================
    # Action Execution
    # =========================================================================

    async def _execute_actions(
        self,
        context: Dict[str, NestedValue],
        actions: List[RuleAction],
    ) -> List[str]:
        """Führt Aktionen aus und sammelt Fehler."""
        errors = []

        for action in actions:
            try:
                handler = self._action_handlers.get(action.type)
                if handler:
                    await handler(context, action.params)
                else:
                    logger.warning(
                        f"Kein Handler für Aktionstyp '{action.type}' registriert"
                    )
            except Exception as e:
                error_msg = f"Fehler bei Aktion '{action.type}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return errors

    # =========================================================================
    # Helpers
    # =========================================================================

    def _get_nested_value(self, data: Dict[str, NestedValue], path: str) -> NestedValue:
        """Holt verschachtelten Wert über Punkt-Notation.

        Beispiel: 'supplier.is_new' -> data['supplier']['is_new']
        """
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

            if current is None:
                return None

        return current

    def _to_number(self, value: NestedValue) -> Union[int, float, Decimal]:
        """Konvertiert Wert zu Zahl."""
        if isinstance(value, (int, float, Decimal)):
            return value
        if isinstance(value, str):
            # Deutsche Zahlenformate
            value = value.replace(".", "").replace(",", ".")
            value = re.sub(r"[^\d.-]", "", value)
            if "." in value:
                return float(value)
            return int(value)
        raise ValueError(f"Kann '{value}' nicht in Zahl konvertieren")

    def _is_rule_valid(self, rule: BusinessRule) -> bool:
        """Prüft ob Regel zeitlich gültig ist."""
        now = datetime.utcnow()

        if rule.valid_from and now < rule.valid_from:
            return False
        if rule.valid_until and now > rule.valid_until:
            return False

        return True

    def _sanitize_context_for_logging(self, context: Dict[str, NestedValue]) -> Dict[str, NestedValue]:
        """Entfernt sensible Daten aus Kontext für Logging."""
        sanitized = {}
        sensitive_keys = {"password", "token", "secret", "api_key", "iban", "credit_card"}

        for key, value in context.items():
            if any(s in key.lower() for s in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_context_for_logging(value)
            else:
                sanitized[key] = value

        return sanitized

    # =========================================================================
    # Document-spezifische Methoden
    # =========================================================================

    async def evaluate_for_document(
        self,
        document_id: UUID,
        rules: List[BusinessRule],
        additional_context: Optional[Dict[str, NestedValue]] = None,
        dry_run: bool = False,
    ) -> RuleSetEvaluationResult:
        """Wertet Regeln für ein Dokument aus.

        Laedt automatisch Dokument-Daten als Kontext.

        Args:
            document_id: Dokument-ID
            rules: Regeln
            additional_context: Zusätzliche Kontext-Daten
            dry_run: Trocknenlauf

        Returns:
            Auswertungs-Ergebnis
        """
        if not self.db:
            raise ValueError("Database session erforderlich für Dokument-Auswertung")

        # Dokument laden
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        # Kontext aufbauen
        context = self._build_document_context(document)

        if additional_context:
            context.update(additional_context)

        # Regeln filtern (nach Dokumenttyp falls definiert)
        applicable_rules = [
            r for r in rules
            if self._rule_applies_to_document(r, document)
        ]

        return await self.evaluate_rules(
            context=context,
            rules=applicable_rules,
            dry_run=dry_run,
            document_id=document_id,
        )

    def _build_document_context(self, document: Document) -> Dict[str, NestedValue]:
        """Baut Kontext-Dict aus Dokument."""
        context = {
            "id": str(document.id),
            "filename": document.original_filename,
            "document_type": document.document_type,
            "status": document.status,
            "tags": document.tags or [],
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "company_id": str(document.company_id),
        }

        # Extrahierte Daten hinzufuegen
        if document.extracted_data:
            for key, value in document.extracted_data.items():
                context[key] = value

        # Spezielle Felder
        if hasattr(document, "amount"):
            context["amount"] = document.amount
        if hasattr(document, "confidence"):
            context["confidence"] = document.confidence

        return context

    def _rule_applies_to_document(
        self,
        rule: BusinessRule,
        document: Document,
    ) -> bool:
        """Prüft ob Regel auf Dokument anwendbar ist."""
        # Dokumenttyp-Filter
        if rule.applies_to_document_types:
            if document.document_type not in rule.applies_to_document_types:
                return False

        # Quellen-Filter
        if rule.applies_to_sources and hasattr(document, "source"):
            if document.source not in rule.applies_to_sources:
                return False

        return True


# Import für timedelta (wurde oben vergessen)
from datetime import timedelta

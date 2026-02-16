"""
JSONB Field Validators for Enterprise Features.

Security-critical validators for JSONB columns to prevent:
- SQL Injection via malicious keys (CWE-89)
- Schema violations in approval_chain, conditions, actions
- Invalid nested structures

Feinpoliert und durchdacht - Enterprise-grade JSONB validation.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class JSONBValidationError(ValueError):
    """Fehler bei JSONB-Validierung."""

    def __init__(self, message: str, field: str, invalid_keys: Optional[List[str]] = None):
        self.field = field
        self.invalid_keys = invalid_keys or []
        super().__init__(f"JSONB-Validierungsfehler in '{field}': {message}")


# =============================================================================
# WHITELIST DEFINITIONS
# =============================================================================

# Erlaubte Keys für approval_chain Steps
APPROVAL_CHAIN_ALLOWED_KEYS: Set[str] = {
    "step",
    "type",
    "value",
    "required",
    "threshold",
    "condition",
    "timeout_hours",
    "delegate_to",
    "notify_on_complete",
    "allow_delegation",
    "auto_approve_if",
}

# Erlaubte Typen für approval_chain.type
APPROVAL_CHAIN_ALLOWED_TYPES: Set[str] = {
    "user",
    "role",
    "group",
    "department",
    "any",
    "all",
}

# Erlaubte Keys für conditions (Approval Rules)
APPROVAL_CONDITIONS_ALLOWED_KEYS: Set[str] = {
    # Betragsbedingungen
    "amount_greater_than",
    "amount_less_than",
    "amount_equals",
    "amount_between",
    # Kategorie-Bedingungen
    "category_in",
    "category_not_in",
    "category_equals",
    # Dokumenttyp-Bedingungen
    "document_type_in",
    "document_type_equals",
    # Entity-Bedingungen
    "entity_type_in",
    "entity_risk_score_above",
    "entity_risk_score_below",
    "supplier_id_in",
    "customer_id_in",
    # Zeitbedingungen
    "created_after",
    "created_before",
    "due_date_within_days",
    # Logische Operatoren
    "and",
    "or",
    "not",
    # Sonstige
    "company_presence_in",
    "has_attachment",
    "priority_in",
    "status_in",
    "custom_field",
}

# Erlaubte Keys für notification actions
NOTIFICATION_ACTIONS_ALLOWED_KEYS: Set[str] = {
    "type",
    "title",
    "body",
    "template",
    "subject",
    "url",
    "action_url",
    "priority",
    "data",
    "recipients",
    "delay_minutes",
    "condition",
    "headers",
    "method",
}

# Erlaubte action types
NOTIFICATION_ACTION_TYPES: Set[str] = {
    "in_app",
    "push",
    "email",
    "webhook",
    "sms",
    "slack",
    "teams",
}

# Erlaubte Keys für workflow definitions
WORKFLOW_DEFINITION_ALLOWED_KEYS: Set[str] = {
    "name",
    "description",
    "version",
    "trigger",
    "steps",
    "variables",
    "on_error",
    "on_complete",
    "timeout_minutes",
    "retry_policy",
}

# Erlaubte Keys für workflow steps
WORKFLOW_STEP_ALLOWED_KEYS: Set[str] = {
    "id",
    "name",
    "type",
    "action",
    "condition",
    "next",
    "on_success",
    "on_failure",
    "timeout_seconds",
    "retry_count",
    "parameters",
    "output_mapping",
}

# Regex für sichere Key-Namen (alphanumerisch + underscore, max 64 Zeichen)
SAFE_KEY_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")


# =============================================================================
# SCHEMA DEFINITIONS (für Dokumentation und OpenAPI)
# =============================================================================

APPROVAL_CHAIN_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["step", "type", "value"],
        "properties": {
            "step": {"type": "integer", "minimum": 1},
            "type": {"type": "string", "enum": list(APPROVAL_CHAIN_ALLOWED_TYPES)},
            "value": {"type": "string"},
            "required": {"type": "boolean", "default": True},
            "threshold": {"type": "number", "minimum": 0},
            "timeout_hours": {"type": "integer", "minimum": 1},
        },
    },
}

APPROVAL_CONDITIONS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        key: {"type": ["string", "number", "array", "boolean"]}
        for key in APPROVAL_CONDITIONS_ALLOWED_KEYS
    },
}

NOTIFICATION_ACTIONS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["type"],
        "properties": {
            "type": {"type": "string", "enum": list(NOTIFICATION_ACTION_TYPES)},
            "title": {"type": "string", "maxLength": 200},
            "body": {"type": "string", "maxLength": 2000},
            "template": {"type": "string", "maxLength": 100},
            "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
        },
    },
}


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def _validate_key_safety(key: str, field_name: str) -> bool:
    """Prüft ob ein Key sicher ist (keine SQL Injection).

    Args:
        key: Der zu prüfende Key
        field_name: Name des JSONB-Feldes (für Fehlermeldungen)

    Returns:
        True wenn sicher

    Raises:
        JSONBValidationError: Bei unsicherem Key
    """
    if not SAFE_KEY_PATTERN.match(key):
        logger.warning(
            "jsonb_unsafe_key_detected",
            field=field_name,
            key=key[:50],  # Truncate für Logging
        )
        raise JSONBValidationError(
            f"Ungültiger Key-Name: '{key[:50]}'. Keys müssen alphanumerisch sein.",
            field=field_name,
            invalid_keys=[key],
        )
    return True


def _validate_keys_against_whitelist(
    data: Dict[str, Any],
    allowed_keys: Set[str],
    field_name: str,
    strict: bool = True,
) -> List[str]:
    """Validiert Keys gegen Whitelist.

    Args:
        data: Das zu validierende Dict
        allowed_keys: Erlaubte Keys
        field_name: Name des Feldes
        strict: Wenn True, wirft Exception bei unbekannten Keys

    Returns:
        Liste der unbekannten Keys

    Raises:
        JSONBValidationError: Bei unbekannten Keys (wenn strict=True)
    """
    invalid_keys = []

    for key in data.keys():
        # Erst Sicherheits-Check
        _validate_key_safety(key, field_name)

        # Dann Whitelist-Check
        if key not in allowed_keys:
            invalid_keys.append(key)

    if invalid_keys and strict:
        logger.warning(
            "jsonb_unknown_keys_detected",
            field=field_name,
            invalid_keys=invalid_keys[:10],  # Max 10 loggen
        )
        raise JSONBValidationError(
            f"Unbekannte Keys: {', '.join(invalid_keys[:5])}. "
            f"Erlaubt: {', '.join(sorted(allowed_keys)[:10])}...",
            field=field_name,
            invalid_keys=invalid_keys,
        )

    return invalid_keys


def validate_approval_chain(
    approval_chain: List[Dict[str, Any]],
    strict: bool = True,
) -> bool:
    """Validiert eine approval_chain JSONB-Struktur.

    Args:
        approval_chain: Liste von Approval-Schritten
        strict: Wenn True, wirft Exception bei Fehlern

    Returns:
        True wenn valide

    Raises:
        JSONBValidationError: Bei Validierungsfehlern
    """
    if not isinstance(approval_chain, list):
        raise JSONBValidationError(
            "approval_chain muss eine Liste sein",
            field="approval_chain",
        )

    if not approval_chain:
        # Leere Liste ist erlaubt
        return True

    seen_steps = set()

    for idx, step in enumerate(approval_chain):
        if not isinstance(step, dict):
            raise JSONBValidationError(
                f"Schritt {idx} muss ein Objekt sein",
                field="approval_chain",
            )

        # Keys validieren
        _validate_keys_against_whitelist(
            step,
            APPROVAL_CHAIN_ALLOWED_KEYS,
            f"approval_chain[{idx}]",
            strict=strict,
        )

        # Pflichtfelder prüfen
        if "step" not in step:
            raise JSONBValidationError(
                f"Schritt {idx}: 'step' ist erforderlich",
                field="approval_chain",
            )

        if "type" not in step:
            raise JSONBValidationError(
                f"Schritt {idx}: 'type' ist erforderlich",
                field="approval_chain",
            )

        if "value" not in step:
            raise JSONBValidationError(
                f"Schritt {idx}: 'value' ist erforderlich",
                field="approval_chain",
            )

        # Type validieren
        step_type = step.get("type")
        if step_type not in APPROVAL_CHAIN_ALLOWED_TYPES:
            raise JSONBValidationError(
                f"Schritt {idx}: Ungültiger Typ '{step_type}'. "
                f"Erlaubt: {', '.join(APPROVAL_CHAIN_ALLOWED_TYPES)}",
                field="approval_chain",
            )

        # Step-Nummer validieren (muss positiv und eindeutig sein)
        step_num = step.get("step")
        if not isinstance(step_num, int) or step_num < 1:
            raise JSONBValidationError(
                f"Schritt {idx}: 'step' muss eine positive Zahl sein",
                field="approval_chain",
            )

        if step_num in seen_steps:
            raise JSONBValidationError(
                f"Schritt {idx}: Doppelte Schrittnummer {step_num}",
                field="approval_chain",
            )
        seen_steps.add(step_num)

        # Value validieren (darf nicht leer sein)
        value = step.get("value")
        if not value or not isinstance(value, str) or not value.strip():
            raise JSONBValidationError(
                f"Schritt {idx}: 'value' darf nicht leer sein",
                field="approval_chain",
            )

    return True


def validate_approval_conditions(
    conditions: Dict[str, Any],
    strict: bool = True,
) -> bool:
    """Validiert conditions JSONB-Struktur für Approval Rules.

    Args:
        conditions: Bedingungs-Dict
        strict: Wenn True, wirft Exception bei Fehlern

    Returns:
        True wenn valide

    Raises:
        JSONBValidationError: Bei Validierungsfehlern
    """
    if not isinstance(conditions, dict):
        raise JSONBValidationError(
            "conditions muss ein Objekt sein",
            field="conditions",
        )

    if not conditions:
        # Leeres Dict ist erlaubt (keine Bedingungen = immer wahr)
        return True

    # Keys validieren
    _validate_keys_against_whitelist(
        conditions,
        APPROVAL_CONDITIONS_ALLOWED_KEYS,
        "conditions",
        strict=strict,
    )

    # Wert-Validierung
    for key, value in conditions.items():
        # Betrags-Bedingungen müssen numerisch sein
        if key.startswith("amount_"):
            if key == "amount_between":
                if not isinstance(value, (list, tuple)) or len(value) != 2:
                    raise JSONBValidationError(
                        f"'{key}' muss eine Liste mit 2 Werten sein [min, max]",
                        field="conditions",
                    )
            elif not isinstance(value, (int, float)):
                raise JSONBValidationError(
                    f"'{key}' muss eine Zahl sein",
                    field="conditions",
                )

        # _in Bedingungen müssen Listen sein
        if key.endswith("_in"):
            if not isinstance(value, list):
                raise JSONBValidationError(
                    f"'{key}' muss eine Liste sein",
                    field="conditions",
                )

        # risk_score Bedingungen müssen zwischen 0-100 sein
        if "risk_score" in key:
            if not isinstance(value, (int, float)) or value < 0 or value > 100:
                raise JSONBValidationError(
                    f"'{key}' muss zwischen 0 und 100 liegen",
                    field="conditions",
                )

    return True


def validate_notification_actions(
    actions: List[Dict[str, Any]],
    strict: bool = True,
) -> bool:
    """Validiert notification actions JSONB-Struktur.

    Args:
        actions: Liste von Aktionen
        strict: Wenn True, wirft Exception bei Fehlern

    Returns:
        True wenn valide

    Raises:
        JSONBValidationError: Bei Validierungsfehlern
    """
    if not isinstance(actions, list):
        raise JSONBValidationError(
            "actions muss eine Liste sein",
            field="actions",
        )

    if not actions:
        raise JSONBValidationError(
            "actions darf nicht leer sein (mindestens eine Aktion erforderlich)",
            field="actions",
        )

    for idx, action in enumerate(actions):
        if not isinstance(action, dict):
            raise JSONBValidationError(
                f"Aktion {idx} muss ein Objekt sein",
                field="actions",
            )

        # Keys validieren
        _validate_keys_against_whitelist(
            action,
            NOTIFICATION_ACTIONS_ALLOWED_KEYS,
            f"actions[{idx}]",
            strict=strict,
        )

        # Type ist Pflicht
        if "type" not in action:
            raise JSONBValidationError(
                f"Aktion {idx}: 'type' ist erforderlich",
                field="actions",
            )

        action_type = action.get("type")
        if action_type not in NOTIFICATION_ACTION_TYPES:
            raise JSONBValidationError(
                f"Aktion {idx}: Ungültiger Typ '{action_type}'. "
                f"Erlaubt: {', '.join(NOTIFICATION_ACTION_TYPES)}",
                field="actions",
            )

        # URL-Validierung für webhooks
        if action_type == "webhook":
            url = action.get("url")
            if not url or not isinstance(url, str):
                raise JSONBValidationError(
                    f"Aktion {idx}: Webhook erfordert 'url'",
                    field="actions",
                )
            if not url.startswith(("http://", "https://")):
                raise JSONBValidationError(
                    f"Aktion {idx}: URL muss mit http:// oder https:// beginnen",
                    field="actions",
                )

        # Template-Validierung für email
        if action_type == "email":
            if "template" not in action and "body" not in action:
                raise JSONBValidationError(
                    f"Aktion {idx}: Email erfordert 'template' oder 'body'",
                    field="actions",
                )

    return True


def validate_workflow_definition(
    definition: Dict[str, Any],
    strict: bool = True,
) -> bool:
    """Validiert workflow definition JSONB-Struktur.

    Args:
        definition: Workflow-Definition
        strict: Wenn True, wirft Exception bei Fehlern

    Returns:
        True wenn valide

    Raises:
        JSONBValidationError: Bei Validierungsfehlern
    """
    if not isinstance(definition, dict):
        raise JSONBValidationError(
            "definition muss ein Objekt sein",
            field="definition",
        )

    # Top-Level Keys validieren
    _validate_keys_against_whitelist(
        definition,
        WORKFLOW_DEFINITION_ALLOWED_KEYS,
        "definition",
        strict=strict,
    )

    # Steps validieren (falls vorhanden)
    steps = definition.get("steps", [])
    if steps:
        if not isinstance(steps, list):
            raise JSONBValidationError(
                "'steps' muss eine Liste sein",
                field="definition",
            )

        seen_ids = set()
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                raise JSONBValidationError(
                    f"Step {idx} muss ein Objekt sein",
                    field="definition.steps",
                )

            _validate_keys_against_whitelist(
                step,
                WORKFLOW_STEP_ALLOWED_KEYS,
                f"definition.steps[{idx}]",
                strict=strict,
            )

            # ID muss eindeutig sein
            step_id = step.get("id")
            if step_id:
                if step_id in seen_ids:
                    raise JSONBValidationError(
                        f"Step {idx}: Doppelte ID '{step_id}'",
                        field="definition.steps",
                    )
                seen_ids.add(step_id)

    return True


# =============================================================================
# SANITIZATION FUNCTIONS
# =============================================================================

def sanitize_jsonb_keys(
    data: Dict[str, Any],
    allowed_keys: Set[str],
) -> Dict[str, Any]:
    """Entfernt unbekannte Keys aus einem Dict.

    Args:
        data: Das zu bereinigende Dict
        allowed_keys: Erlaubte Keys

    Returns:
        Bereinigtes Dict (nur erlaubte Keys)
    """
    return {k: v for k, v in data.items() if k in allowed_keys}

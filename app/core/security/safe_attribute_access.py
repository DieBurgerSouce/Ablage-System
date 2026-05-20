"""Safe Attribute Access.

Provides controlled model attribute updates with explicit whitelists.
Prevents mass assignment vulnerabilities (CWE-915) and privilege escalation.

Features:
- Model-specific field whitelists
- Global forbidden fields
- Type-safe update operations
- Audit logging of field changes

Example:
    from app.core.security import safe_update

    # Only allowed fields will be updated
    updated_user = safe_update(user, {"name": "New Name", "is_admin": True})
    # is_admin is forbidden and will be ignored/logged
"""

from typing import Any, Dict, FrozenSet, Optional, Set, TypeVar, Type
import structlog

logger = structlog.get_logger(__name__)

# Type variable for models
T = TypeVar("T")


# ============================================================================
# Field Configuration
# ============================================================================

# Fields that should NEVER be updated via API (security-critical)
FORBIDDEN_FIELDS: FrozenSet[str] = frozenset({
    # Primary keys
    "id",
    "uuid",

    # Timestamps (managed by system)
    "created_at",
    "updated_at",

    # Authentication/Authorization
    "password",
    "password_hash",
    "hashed_password",
    "is_admin",
    "is_superuser",
    "is_active",
    "is_verified",
    "is_deleted",
    "role",
    "roles",
    "permissions",

    # Security tokens
    "api_key",
    "api_key_hash",
    "refresh_token",
    "mfa_secret",
    "mfa_secret_encrypted",
    "backup_codes",

    # Audit fields
    "created_by",
    "created_by_id",
    "modified_by",
    "modified_by_id",
    "deleted_by",
    "deleted_by_id",

    # Multi-tenancy
    "company_id",
    "tenant_id",
    "organization_id",
    "owner_id",

    # Soft delete
    "deleted_at",

    # System fields
    "_sa_instance_state",
    "__tablename__",
})

# Fields that can be updated per model (whitelist approach)
MODEL_UPDATABLE_FIELDS: Dict[str, FrozenSet[str]] = {
    "User": frozenset({
        "first_name",
        "last_name",
        "email",
        "phone",
        "preferences",
        "settings",
        "avatar_url",
        "language",
        "timezone",
    }),
    "Company": frozenset({
        "name",
        "display_name",
        "address",
        "city",
        "postal_code",
        "country",
        "phone",
        "email",
        "website",
        "tax_number",
        "vat_id",
        "settings",
        "metadata",
    }),
    "Document": frozenset({
        "title",
        "description",
        "tags",
        "metadata",
        "folder_id",
        "category",
        "status",
        "notes",
        "custom_fields",
    }),
    "BusinessEntity": frozenset({
        "name",
        "display_name",
        "entity_type",
        "address",
        "city",
        "postal_code",
        "country",
        "phone",
        "email",
        "website",
        "notes",
        "metadata",
        "tags",
        "risk_score",
        "risk_factors",
    }),
    "InvoiceTracking": frozenset({
        "invoice_number",
        "invoice_date",
        "due_date",
        "amount",
        "currency",
        "status",
        "dunning_level",
        "notes",
        "metadata",
        "skonto_percentage",
        "skonto_days",
        "skonto_deadline",
        "skonto_amount",
        "skonto_used",
        "outstanding_amount",
        "payment_reference",
    }),
    "Alert": frozenset({
        "status",
        "acknowledged_at",
        "acknowledged_by_id",
        "resolved_at",
        "resolved_by_id",
        "resolution_notes",
        "assigned_to_id",
        "escalated_to_id",
        "escalation_level",
    }),
    "ApprovalRequest": frozenset({
        "status",
        "notes",
        "priority",
        "due_date",
        "assigned_to_id",
    }),
    "ProcessTask": frozenset({
        "status",
        "assignee_id",
        "due_date",
        "priority",
        "notes",
        "task_variables",
    }),
    "ImportRule": frozenset({
        "name",
        "description",
        "priority",
        "conditions",
        "actions",
        "enabled",
        "apply_to_email",
        "apply_to_folder",
    }),
}


class SafeAttributeAccessError(Exception):
    """Raised when attribute access is denied."""
    pass


class SafeAttributeAccess:
    """Safe attribute access controller for models.

    Enforces field whitelists and prevents updates to forbidden fields.
    """

    def __init__(
        self,
        forbidden_fields: Optional[FrozenSet[str]] = None,
        model_fields: Optional[Dict[str, FrozenSet[str]]] = None,
        strict_mode: bool = True,
    ):
        """Initialize the controller.

        Args:
            forbidden_fields: Fields that can never be updated
            model_fields: Allowed fields per model class
            strict_mode: If True, only whitelisted fields are allowed.
                        If False, any field not in forbidden list is allowed.
        """
        self.forbidden_fields = forbidden_fields or FORBIDDEN_FIELDS
        self.model_fields = model_fields or MODEL_UPDATABLE_FIELDS
        self.strict_mode = strict_mode

    def is_field_allowed(
        self,
        model_name: str,
        field_name: str,
    ) -> bool:
        """Check if a field can be updated for a model.

        Args:
            model_name: Name of the model class
            field_name: Name of the field to check

        Returns:
            True if field update is allowed
        """
        # Always deny forbidden fields
        if field_name in self.forbidden_fields:
            return False

        # Deny private/dunder attributes
        if field_name.startswith("_"):
            return False

        if self.strict_mode:
            # In strict mode, field must be in whitelist
            allowed = self.model_fields.get(model_name, frozenset())
            return field_name in allowed
        else:
            # In permissive mode, allow if not forbidden
            return True

    def filter_fields(
        self,
        model_name: str,
        data: Dict[str, Any],
        log_denied: bool = True,
    ) -> Dict[str, Any]:
        """Filter a dict to only include allowed fields.

        Args:
            model_name: Name of the model class
            data: Dict of field names to values
            log_denied: Whether to log denied fields

        Returns:
            Filtered dict with only allowed fields
        """
        allowed = {}
        denied = []

        for field, value in data.items():
            if self.is_field_allowed(model_name, field):
                allowed[field] = value
            else:
                denied.append(field)

        if denied and log_denied:
            logger.warning(
                "fields_denied_for_update",
                model=model_name,
                denied_fields=denied,
                allowed_count=len(allowed),
            )

        return allowed

    def validate_update(
        self,
        model_name: str,
        data: Dict[str, Any],
        raise_on_denied: bool = False,
    ) -> tuple[Dict[str, Any], list[str]]:
        """Validate and filter update data.

        Args:
            model_name: Name of the model class
            data: Dict of field names to values
            raise_on_denied: Whether to raise exception if any field is denied

        Returns:
            Tuple of (allowed_fields, denied_fields)

        Raises:
            SafeAttributeAccessError: If raise_on_denied and fields were denied
        """
        allowed = {}
        denied = []

        for field, value in data.items():
            if self.is_field_allowed(model_name, field):
                allowed[field] = value
            else:
                denied.append(field)

        if denied:
            logger.warning(
                "update_validation_denied_fields",
                model=model_name,
                denied_fields=denied,
            )

            if raise_on_denied:
                raise SafeAttributeAccessError(
                    f"Folgende Felder können nicht aktualisiert werden: {', '.join(denied)}"
                )

        return allowed, denied


# ============================================================================
# Convenience Functions
# ============================================================================

_default_controller: Optional[SafeAttributeAccess] = None


def get_default_controller() -> SafeAttributeAccess:
    """Get the default attribute access controller.

    Returns:
        Default SafeAttributeAccess instance
    """
    global _default_controller
    if _default_controller is None:
        _default_controller = SafeAttributeAccess(strict_mode=True)
    return _default_controller


def safe_update(
    model: T,
    data: Dict[str, Any],
    strict: bool = True,
    log_changes: bool = True,
) -> T:
    """Safely update a model instance with filtered data.

    Only updates fields that are in the whitelist for the model type.
    Forbidden fields are always ignored.

    Args:
        model: The model instance to update
        data: Dict of field names to new values
        strict: If True, only whitelisted fields are updated
        log_changes: Whether to log the changes

    Returns:
        The updated model instance
    """
    model_name = type(model).__name__
    controller = get_default_controller()

    # Filter data
    allowed_data, denied_fields = controller.validate_update(
        model_name,
        data,
        raise_on_denied=False,
    )

    # Track changes for logging
    changes: Dict[str, Dict[str, Any]] = {}

    # Apply allowed updates
    for field, new_value in allowed_data.items():
        old_value = getattr(model, field, None)

        # Only update if value actually changed
        if old_value != new_value:
            setattr(model, field, new_value)
            changes[field] = {"old": old_value, "new": new_value}

    if log_changes and changes:
        # Don't log actual values for security
        logger.info(
            "model_updated_safely",
            model=model_name,
            model_id=getattr(model, "id", None),
            changed_fields=list(changes.keys()),
            denied_fields=denied_fields,
        )

    return model


def get_allowed_fields(model_name: str) -> Set[str]:
    """Get the set of allowed fields for a model.

    Args:
        model_name: Name of the model class

    Returns:
        Set of allowed field names
    """
    return set(MODEL_UPDATABLE_FIELDS.get(model_name, frozenset()))


def is_forbidden_field(field_name: str) -> bool:
    """Check if a field is globally forbidden.

    Args:
        field_name: Field name to check

    Returns:
        True if field is forbidden
    """
    return field_name in FORBIDDEN_FIELDS


def register_model_fields(
    model_name: str,
    fields: Set[str],
) -> None:
    """Register allowed fields for a model at runtime.

    This should only be called during application startup.

    Args:
        model_name: Name of the model class
        fields: Set of allowed field names
    """
    global _default_controller

    # Validate no forbidden fields
    forbidden_in_list = fields & FORBIDDEN_FIELDS
    if forbidden_in_list:
        raise ValueError(
            f"Cannot register forbidden fields: {forbidden_in_list}"
        )

    MODEL_UPDATABLE_FIELDS[model_name] = frozenset(fields)

    # Reset controller to pick up changes
    _default_controller = None

    logger.info(
        "model_fields_registered",
        model=model_name,
        field_count=len(fields),
    )

"""Safe Module Loader.

Provides secure module and function loading with explicit whitelists.
Prevents CWE-470 (Use of Externally-Controlled Input to Select Classes or Code).

Only modules and functions explicitly whitelisted can be loaded.
This replaces dangerous patterns like:
    module = importlib.import_module(user_input)
    func = getattr(module, user_input)

Example:
    loader = SafeModuleLoader()
    func = loader.load_function("app.services.bpmn.notifications.send_approval_email")
    await func(instance_id=..., variables=...)

Security Note (Phase 2 Enterprise Quality):
    The module registration is locked after application startup to prevent
    runtime whitelist modification attacks. Call lock_bpmn_registration()
    in your application startup sequence.
"""

import importlib
import threading
from types import ModuleType
from typing import Callable, Dict, Optional, FrozenSet
import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# =============================================================================
# Security: Registration Lock (CWE-470 Prevention)
# =============================================================================

# Thread-safe lock for registration operations
_registration_lock = threading.Lock()

# Flag to permanently lock registration after startup
_registration_locked: bool = False


class RegistrationLockedError(Exception):
    """Raised when attempting to modify whitelists after registration is locked."""
    pass


def lock_bpmn_registration() -> None:
    """
    Permanently locks BPMN function registration after application startup.

    This should be called in the application startup sequence (e.g., in main.py)
    after all legitimate registrations are complete. Once locked, no new modules
    or functions can be registered, preventing runtime whitelist modification attacks.

    This is a one-way operation and cannot be undone without restarting the application.

    Example in main.py:
        @app.on_event("startup")
        async def startup():
            # ... other startup code ...
            lock_bpmn_registration()
    """
    global _registration_locked
    with _registration_lock:
        _registration_locked = True
        logger.info(
            "bpmn_registration_locked",
            message="BPMN function registration permanently locked",
        )


def is_registration_locked() -> bool:
    """Check if BPMN registration is currently locked."""
    return _registration_locked


class ModuleLoadingError(Exception):
    """Raised when module or function loading fails."""
    pass


class ModuleNotAllowedError(ModuleLoadingError):
    """Raised when module is not in whitelist."""
    pass


class FunctionNotAllowedError(ModuleLoadingError):
    """Raised when function is not in whitelist."""
    pass


# ============================================================================
# BPMN Service Task Whitelist
# ============================================================================

# Allowed modules for BPMN Service Tasks
ALLOWED_BPMN_MODULES: FrozenSet[str] = frozenset({
    # Internal BPMN service functions
    "app.services.bpmn.service_tasks",
    "app.services.bpmn.notifications",
    "app.services.bpmn.integrations",

    # Document processing
    "app.services.document_services.batch_service",
    "app.services.document_services.export_service",

    # Workflow services
    "app.services.approval.approval_service",
    "app.services.workflow.workflow_service",

    # Notification services
    "app.services.notification_service",
    "app.services.slack_service",

    # Entity services
    "app.services.entity_search_service",
    "app.services.document_entity_linker_service",

    # Banking services
    "app.services.banking.dunning_service",
    "app.services.banking.skonto_service",

    # Alert services
    "app.services.alert_center_service",
})

# Allowed functions per module
ALLOWED_BPMN_FUNCTIONS: Dict[str, FrozenSet[str]] = {
    "app.services.bpmn.service_tasks": frozenset({
        "send_notification",
        "update_document_status",
        "trigger_ocr",
        "generate_report",
        "archive_document",
    }),
    "app.services.bpmn.notifications": frozenset({
        "send_approval_email",
        "send_rejection_email",
        "send_reminder_email",
        "send_escalation_email",
        "send_slack_notification",
    }),
    "app.services.bpmn.integrations": frozenset({
        "export_to_datev",
        "export_to_lexware",
        "sync_with_erp",
        "call_external_api",
    }),
    "app.services.document_services.batch_service": frozenset({
        "process_batch",
        "validate_batch",
        "finalize_batch",
    }),
    "app.services.document_services.export_service": frozenset({
        "export_document",
        "export_batch",
        "generate_archive",
    }),
    "app.services.approval.approval_service": frozenset({
        "create_approval_request",
        "escalate_approval",
        "auto_approve",
        "auto_reject",
    }),
    "app.services.workflow.workflow_service": frozenset({
        "execute_workflow_step",
        "complete_workflow",
        "cancel_workflow",
    }),
    "app.services.notification_service": frozenset({
        "send_email",
        "send_push_notification",
        "send_in_app_notification",
    }),
    "app.services.slack_service": frozenset({
        "send_message",
        "send_notification",
        "post_to_channel",
    }),
    "app.services.entity_search_service": frozenset({
        "search_entities",
        "find_by_identifier",
    }),
    "app.services.document_entity_linker_service": frozenset({
        "link_document_to_entity",
        "auto_link_document",
    }),
    "app.services.banking.dunning_service": frozenset({
        "create_dunning",
        "escalate_dunning",
        "send_dunning_letter",
    }),
    "app.services.banking.skonto_service": frozenset({
        "check_skonto_deadline",
        "apply_skonto",
        "send_skonto_reminder",
    }),
    "app.services.alert_center_service": frozenset({
        "create_alert",
        "escalate_alert",
        "resolve_alert",
    }),
}


class SafeModuleLoader:
    """Safe module and function loader with whitelists.

    Only loads modules and functions that are explicitly allowed.

    Attributes:
        allowed_modules: Set of allowed module paths
        allowed_functions: Dict of module -> allowed function names
    """

    def __init__(
        self,
        allowed_modules: Optional[FrozenSet[str]] = None,
        allowed_functions: Optional[Dict[str, FrozenSet[str]]] = None,
    ):
        """Initialize the loader.

        Args:
            allowed_modules: Set of allowed module paths (default: BPMN whitelist)
            allowed_functions: Dict of allowed functions per module
        """
        self.allowed_modules = allowed_modules or ALLOWED_BPMN_MODULES
        self.allowed_functions = allowed_functions or ALLOWED_BPMN_FUNCTIONS

    def is_module_allowed(self, module_path: str) -> bool:
        """Check if a module is in the whitelist.

        Args:
            module_path: Full module path (e.g., "app.services.bpmn.notifications")

        Returns:
            True if module is allowed
        """
        return module_path in self.allowed_modules

    def is_function_allowed(self, module_path: str, function_name: str) -> bool:
        """Check if a function is in the whitelist.

        Args:
            module_path: Full module path
            function_name: Function name

        Returns:
            True if function is allowed in that module
        """
        if module_path not in self.allowed_functions:
            return False
        return function_name in self.allowed_functions[module_path]

    def load_module(self, module_path: str) -> ModuleType:
        """Safely load a whitelisted module.

        Args:
            module_path: Full module path

        Returns:
            The loaded module

        Raises:
            ModuleNotAllowedError: If module is not whitelisted
            ModuleLoadingError: If module cannot be loaded
        """
        if not self.is_module_allowed(module_path):
            logger.warning(
                "module_not_allowed",
                module_path=module_path,
                allowed_modules=list(self.allowed_modules)[:5],  # Sample
            )
            raise ModuleNotAllowedError(
                f"Modul nicht erlaubt: {module_path}"
            )

        try:
            return importlib.import_module(module_path)
        except ImportError as e:
            logger.error(
                "module_import_failed",
                module_path=module_path,
                **safe_error_log(e),
            )
            raise ModuleLoadingError(
                f"Modul konnte nicht geladen werden: {module_path}"
            ) from e

    def load_function(self, full_path: str) -> Callable[..., object]:
        """Safely load a whitelisted function.

        Args:
            full_path: Full function path (e.g., "app.services.module.function")

        Returns:
            The loaded function

        Raises:
            ModuleNotAllowedError: If module is not whitelisted
            FunctionNotAllowedError: If function is not whitelisted
            ModuleLoadingError: If loading fails
        """
        # Validate path format
        if not full_path or "." not in full_path:
            raise ModuleLoadingError(
                f"Ungültiger Funktionspfad: {full_path}"
            )

        # Split into module and function
        try:
            module_path, function_name = full_path.rsplit(".", 1)
        except ValueError:
            raise ModuleLoadingError(
                f"Kann Funktionspfad nicht parsen: {full_path}"
            )

        # Validate function name (prevent injection)
        if not function_name.isidentifier():
            raise ModuleLoadingError(
                f"Ungültiger Funktionsname: {function_name}"
            )

        # Check module whitelist
        if not self.is_module_allowed(module_path):
            logger.warning(
                "module_not_allowed_for_function",
                module_path=module_path,
                function_name=function_name,
            )
            raise ModuleNotAllowedError(
                f"Modul nicht erlaubt: {module_path}"
            )

        # Check function whitelist
        if not self.is_function_allowed(module_path, function_name):
            logger.warning(
                "function_not_allowed",
                module_path=module_path,
                function_name=function_name,
                allowed_functions=list(
                    self.allowed_functions.get(module_path, set())
                )[:5],
            )
            raise FunctionNotAllowedError(
                f"Funktion nicht erlaubt: {function_name} in {module_path}"
            )

        # Load the module
        module = self.load_module(module_path)

        # Get the function
        try:
            func = getattr(module, function_name)
        except AttributeError:
            raise ModuleLoadingError(
                f"Funktion nicht gefunden: {function_name} in {module_path}"
            )

        if not callable(func):
            raise ModuleLoadingError(
                f"Ist keine Funktion: {function_name}"
            )

        logger.debug(
            "function_loaded_safely",
            full_path=full_path,
        )

        return func


# ============================================================================
# Convenience Functions
# ============================================================================

# Default loader instance for BPMN
_default_loader: Optional[SafeModuleLoader] = None


def get_default_loader() -> SafeModuleLoader:
    """Get the default BPMN module loader.

    Returns:
        Default SafeModuleLoader instance
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = SafeModuleLoader()
    return _default_loader


def safe_load_function(full_path: str) -> Callable[..., object]:
    """Safely load a function using the default loader.

    Args:
        full_path: Full function path

    Returns:
        The loaded function

    Raises:
        ModuleNotAllowedError: If module is not whitelisted
        FunctionNotAllowedError: If function is not whitelisted
        ModuleLoadingError: If loading fails
    """
    return get_default_loader().load_function(full_path)


def is_function_allowed(full_path: str) -> bool:
    """Check if a function is allowed without loading it.

    Args:
        full_path: Full function path

    Returns:
        True if function would be allowed
    """
    if "." not in full_path:
        return False

    try:
        module_path, function_name = full_path.rsplit(".", 1)
    except ValueError:
        return False

    loader = get_default_loader()
    return (
        loader.is_module_allowed(module_path) and
        loader.is_function_allowed(module_path, function_name)
    )


def register_bpmn_function(module_path: str, function_name: str) -> None:
    """Register an additional BPMN function at runtime.

    This should only be called during application startup, BEFORE
    lock_bpmn_registration() is called.

    Args:
        module_path: Module path to register
        function_name: Function name to allow

    Raises:
        RegistrationLockedError: If registration has been locked

    Note:
        This modifies the global whitelist. Use with caution.
        After lock_bpmn_registration() is called, this function will raise.
    """
    global ALLOWED_BPMN_MODULES, ALLOWED_BPMN_FUNCTIONS, _default_loader

    # Security: Check if registration is locked (CWE-470)
    with _registration_lock:
        if _registration_locked:
            logger.warning(
                "bpmn_registration_blocked",
                module_path=module_path,
                function_name=function_name,
                reason="Registration locked after startup",
            )
            raise RegistrationLockedError(
                "BPMN-Registrierung ist nach Anwendungsstart gesperrt. "
                "Neue Funktionen können nicht mehr hinzugefügt werden."
            )

        # Add to module whitelist
        ALLOWED_BPMN_MODULES = frozenset(ALLOWED_BPMN_MODULES | {module_path})

        # Add to function whitelist
        existing = ALLOWED_BPMN_FUNCTIONS.get(module_path, frozenset())
        ALLOWED_BPMN_FUNCTIONS[module_path] = frozenset(existing | {function_name})

        # Reset default loader to pick up changes
        _default_loader = None

    logger.info(
        "bpmn_function_registered",
        module_path=module_path,
        function_name=function_name,
    )

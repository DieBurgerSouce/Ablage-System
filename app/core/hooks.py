"""
Hook System for Agent Extensibility.

Provides pre/post/error hooks for agent execution:
- PreProcessingHooks: Validation, authentication, rate limiting
- PostProcessingHooks: Logging, metrics, notifications
- ErrorHooks: Error handling, alerting, fallback
- LifecycleHooks: Startup, shutdown, resource management
"""

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import structlog
from slowapi.errors import RateLimitExceeded

logger = structlog.get_logger(__name__)


class HookType(str, Enum):
    """Hook execution types."""

    PRE_PROCESS = "pre_process"
    POST_PROCESS = "post_process"
    ERROR = "error"
    LIFECYCLE = "lifecycle"
    CUSTOM = "custom"


class HookPriority(int, Enum):
    """Hook execution priority."""

    CRITICAL = 0  # Execute first
    HIGH = 10
    NORMAL = 50
    LOW = 100


class BaseHook(ABC):
    """
    Abstract base class for all hooks.

    Hooks can modify input/output or trigger side effects.
    """

    def __init__(
        self,
        name: str,
        hook_type: HookType,
        priority: HookPriority = HookPriority.NORMAL,
        enabled: bool = True,
    ):
        """
        Initialize hook.

        Args:
            name: Hook name
            hook_type: Hook type
            priority: Execution priority (lower = earlier)
            enabled: Whether hook is enabled
        """
        self.name = name
        self.hook_type = hook_type
        self.priority = priority
        self.enabled = enabled
        self.logger = logger.bind(hook=name, hook_type=hook_type.value)

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute hook.

        Args:
            context: Execution context

        Returns:
            Modified context (can be same as input or modified)

        Raises:
            Exception: Hook execution failed
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, priority={self.priority})>"


# =============================================================================
# PRE-PROCESSING HOOKS
# =============================================================================


class ValidationHook(BaseHook):
    """Validate input data before processing."""

    def __init__(self, validator: Callable):
        super().__init__(
            name="validation_hook",
            hook_type=HookType.PRE_PROCESS,
            priority=HookPriority.CRITICAL,
        )
        self.validator = validator

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate input data."""
        input_data = context.get("input_data", {})

        self.logger.debug("validating_input", input_data_keys=list(input_data.keys()))

        try:
            # Run validation
            if asyncio.iscoroutinefunction(self.validator):
                is_valid = await self.validator(input_data)
            else:
                is_valid = self.validator(input_data)

            if not is_valid:
                raise ValueError("Input validation failed")

            self.logger.info("validation_passed")
            return context

        except Exception as e:
            self.logger.error("validation_failed", **safe_error_log(e))
            raise


class AuthenticationHook(BaseHook):
    """Check authentication before processing."""

    def __init__(self, auth_check: Callable):
        super().__init__(
            name="authentication_hook",
            hook_type=HookType.PRE_PROCESS,
            priority=HookPriority.CRITICAL,
        )
        self.auth_check = auth_check

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Check authentication."""
        user = context.get("user")

        self.logger.debug("checking_authentication", user_id=user.get("id") if user else None)

        if asyncio.iscoroutinefunction(self.auth_check):
            authenticated = await self.auth_check(context)
        else:
            authenticated = self.auth_check(context)

        if not authenticated:
            raise PermissionError("Authentication failed")

        return context


class RateLimitHook(BaseHook):
    """Rate limiting hook."""

    def __init__(self, rate_limiter: Callable):
        super().__init__(
            name="rate_limit_hook",
            hook_type=HookType.PRE_PROCESS,
            priority=HookPriority.HIGH,
        )
        self.rate_limiter = rate_limiter

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Check rate limit."""
        user_id = context.get("user", {}).get("id")

        if asyncio.iscoroutinefunction(self.rate_limiter):
            allowed = await self.rate_limiter(user_id)
        else:
            allowed = self.rate_limiter(user_id)

        if not allowed:
            raise RateLimitExceeded("Rate-Limit ueberschritten")

        return context


# =============================================================================
# POST-PROCESSING HOOKS
# =============================================================================


class LoggingHook(BaseHook):
    """Log execution results."""

    def __init__(self):
        super().__init__(
            name="logging_hook",
            hook_type=HookType.POST_PROCESS,
            priority=HookPriority.NORMAL,
        )

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Log execution details."""
        result = context.get("result", {})
        metadata = context.get("metadata", {})

        self.logger.info(
            "execution_logged",
            agent=metadata.get("agent"),
            status=metadata.get("status"),
            duration=metadata.get("duration_seconds"),
        )

        return context


class MetricsHook(BaseHook):
    """Collect metrics."""

    def __init__(self):
        super().__init__(
            name="metrics_hook",
            hook_type=HookType.POST_PROCESS,
            priority=HookPriority.HIGH,
        )

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Collect execution metrics."""
        # Metrics are already collected in BaseAgent
        # This hook can add custom business metrics

        result = context.get("result", {})
        metadata = context.get("metadata", {})

        # Example: Track OCR confidence
        if "confidence" in result:
            self.logger.debug(
                "metric_collected",
                metric="ocr_confidence",
                value=result["confidence"],
            )

        return context


class NotificationHook(BaseHook):
    """Send notifications on completion."""

    def __init__(self, notifier: Callable):
        super().__init__(
            name="notification_hook",
            hook_type=HookType.POST_PROCESS,
            priority=HookPriority.LOW,
        )
        self.notifier = notifier

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Send notification."""
        if asyncio.iscoroutinefunction(self.notifier):
            await self.notifier(context)
        else:
            self.notifier(context)

        return context


# =============================================================================
# ERROR HOOKS
# =============================================================================


class ErrorLoggingHook(BaseHook):
    """Log errors with context."""

    def __init__(self):
        super().__init__(
            name="error_logging_hook",
            hook_type=HookType.ERROR,
            priority=HookPriority.CRITICAL,
        )

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Log error details."""
        error = context.get("error")
        metadata = context.get("metadata", {})

        self.logger.error(
            "error_logged",
            agent=metadata.get("agent"),
            error=str(error),
            error_type=type(error).__name__,
            input_data=context.get("input_data", {}),
        )

        return context


class AlertingHook(BaseHook):
    """Send alerts on errors."""

    def __init__(self, alerter: Callable):
        super().__init__(
            name="alerting_hook",
            hook_type=HookType.ERROR,
            priority=HookPriority.HIGH,
        )
        self.alerter = alerter

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Send alert."""
        if asyncio.iscoroutinefunction(self.alerter):
            await self.alerter(context)
        else:
            self.alerter(context)

        return context


# =============================================================================
# LIFECYCLE HOOKS
# =============================================================================


class StartupHook(BaseHook):
    """Execute on agent startup."""

    def __init__(self, startup_func: Callable):
        super().__init__(
            name="startup_hook",
            hook_type=HookType.LIFECYCLE,
            priority=HookPriority.CRITICAL,
        )
        self.startup_func = startup_func

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run startup tasks."""
        if asyncio.iscoroutinefunction(self.startup_func):
            await self.startup_func(context)
        else:
            self.startup_func(context)

        return context


class CleanupHook(BaseHook):
    """Execute on agent shutdown."""

    def __init__(self, cleanup_func: Callable):
        super().__init__(
            name="cleanup_hook",
            hook_type=HookType.LIFECYCLE,
            priority=HookPriority.HIGH,
        )
        self.cleanup_func = cleanup_func

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run cleanup tasks."""
        if asyncio.iscoroutinefunction(self.cleanup_func):
            await self.cleanup_func(context)
        else:
            self.cleanup_func(context)

        return context


# =============================================================================
# HOOK REGISTRY
# =============================================================================


class HookRegistry:
    """
    Global registry for managing hooks.

    Singleton pattern - use get_instance().
    """

    _instance: Optional["HookRegistry"] = None
    _lock: asyncio.Lock = asyncio.Lock()  # Thread-safe singleton creation

    def __init__(self):
        self._hooks: Dict[HookType, List[BaseHook]] = {
            hook_type: [] for hook_type in HookType
        }
        self.logger = logger.bind(component="hook_registry")

    @classmethod
    def get_instance(cls) -> "HookRegistry":
        """Get singleton instance (thread-safe with double-checked locking)."""
        # First check without lock (fast path)
        if cls._instance is not None:
            return cls._instance

        # Second check with lock (slow path, only on first access)
        # Note: In async context, proper async lock should be used
        # For sync access, this provides basic protection
        if cls._instance is None:
            # Import threading for sync lock
            import threading

            if not hasattr(cls, '_sync_lock'):
                cls._sync_lock = threading.Lock()

            with cls._sync_lock:
                # Double-check after acquiring lock
                if cls._instance is None:
                    cls._instance = cls()

        return cls._instance

    def register(self, hook: BaseHook) -> None:
        """Register a hook."""
        self._hooks[hook.hook_type].append(hook)

        # Sort by priority
        self._hooks[hook.hook_type].sort(key=lambda h: h.priority)

        self.logger.info(
            "hook_registered",
            hook_name=hook.name,
            hook_type=hook.hook_type.value,
            priority=hook.priority,
        )

    def unregister(self, hook_name: str, hook_type: HookType) -> None:
        """Unregister a hook."""
        self._hooks[hook_type] = [
            h for h in self._hooks[hook_type] if h.name != hook_name
        ]

        self.logger.info("hook_unregistered", hook_name=hook_name)

    def get_hooks(self, hook_type: HookType) -> List[BaseHook]:
        """Get all hooks for a type."""
        return [h for h in self._hooks[hook_type] if h.enabled]

    async def execute_hooks(
        self, hook_type: HookType, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute all hooks of a given type.

        Args:
            hook_type: Type of hooks to execute
            context: Execution context

        Returns:
            Modified context
        """
        hooks = self.get_hooks(hook_type)

        self.logger.debug(
            "executing_hooks",
            hook_type=hook_type.value,
            hook_count=len(hooks),
        )

        for hook in hooks:
            try:
                context = await hook.execute(context)
            except Exception as e:
                self.logger.error(
                    "hook_execution_failed",
                    hook_name=hook.name,
                    **safe_error_log(e),
                )
                # Continue or stop based on hook type
                if hook_type == HookType.PRE_PROCESS:
                    raise  # Pre-process failures should stop execution

        return context

    async def execute_hook_by_name(
        self, hook_name: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a specific hook by name.

        Args:
            hook_name: Name of the hook to execute
            context: Execution context

        Returns:
            Modified context

        Raises:
            ValueError: If hook not found
        """
        # Search for hook across all types
        for hook_type in HookType:
            for hook in self._hooks[hook_type]:
                if hook.name == hook_name and hook.enabled:
                    self.logger.debug(
                        "executing_hook_by_name",
                        hook_name=hook_name,
                        hook_type=hook_type.value,
                    )
                    try:
                        context = await hook.execute(context)
                        return context
                    except Exception as e:
                        self.logger.error(
                            "hook_execution_failed",
                            hook_name=hook_name,
                            **safe_error_log(e),
                        )
                        raise

        # Hook not found
        self.logger.warning("hook_not_found", hook_name=hook_name)
        raise ValueError(f"Hook not found: {hook_name}")

    def clear_all(self) -> None:
        """Clear all registered hooks."""
        self._hooks = {hook_type: [] for hook_type in HookType}
        self.logger.warning("all_hooks_cleared")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def register_hook(hook: BaseHook) -> None:
    """Register a hook in global registry."""
    registry = HookRegistry.get_instance()
    registry.register(hook)


async def execute_pre_hooks(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute all pre-processing hooks."""
    registry = HookRegistry.get_instance()
    return await registry.execute_hooks(HookType.PRE_PROCESS, context)


async def execute_post_hooks(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute all post-processing hooks."""
    registry = HookRegistry.get_instance()
    return await registry.execute_hooks(HookType.POST_PROCESS, context)


async def execute_error_hooks(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute all error hooks."""
    registry = HookRegistry.get_instance()
    return await registry.execute_hooks(HookType.ERROR, context)

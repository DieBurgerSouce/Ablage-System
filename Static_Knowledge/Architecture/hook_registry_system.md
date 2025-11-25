# Hook Registry & Management System
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Hook System Overview](#hook-system-overview)
2. [Hook Registry Architecture](#hook-registry-architecture)
3. [Hook Types & Lifecycle](#hook-types--lifecycle)
4. [Hook Implementation](#hook-implementation)
5. [Hook Configuration](#hook-configuration)
6. [Hook Execution Order](#hook-execution-order)
7. [Built-in Hooks](#built-in-hooks)
8. [Custom Hook Development](#custom-hook-development)
9. [Hook Testing](#hook-testing)
10. [Hook Monitoring](#hook-monitoring)

---

## Hook System Overview

Das Hook-System ermöglicht **event-driven cross-cutting concerns** durch automatisches Ausführen von Code bei bestimmten Ereignissen.

### Warum Hooks?

```
┌──────────────────────────────────────────────────────────┐
│                  WITHOUT HOOKS                            │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  Every Agent:                                             │
│  - Duplicates logging code                                │
│  - Duplicates metrics collection                          │
│  - Duplicates error handling                              │
│  - Hard to maintain consistency                           │
│  - Hard to add new cross-cutting concerns                 │
│                                                           │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                   WITH HOOKS                              │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  Centralized:                                             │
│  - Single logging hook for all agents                     │
│  - Single metrics hook for all agents                     │
│  - Single error handling hook                             │
│  - Easy to maintain                                       │
│  - Easy to add new functionality                          │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Hook Flow

```
Agent Process Task
      ↓
[PRE_PROCESS Hooks]
   → Logging Hook
   → Validation Hook
   → Rate Limit Hook
      ↓
[ACTUAL PROCESSING]
      ↓
[POST_PROCESS Hooks]  ←── Success
   → Metrics Hook
   → Notification Hook
   → Cache Update Hook
      ↓
   OR
      ↓
[ON_ERROR Hooks]      ←── Error
   → Error Logging Hook
   → Alert Hook
   → Retry Hook
```

---

## Hook Registry Architecture

### Components

```python
# Execution_Layer/Hooks/hook_registry.py
from typing import Dict, List, Any, Optional, Type
from enum import Enum
import structlog
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger

logger = structlog.get_logger(__name__)


class HookRegistry:
    """
    Central registry for all hooks in the system.

    Manages hook registration, discovery, and execution.
    """

    _instance = None
    _hooks: Dict[HookTrigger, List[BaseHook]] = {}
    _hook_classes: Dict[str, Type[BaseHook]] = {}

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._hooks = {
                HookTrigger.PRE_PROCESS: [],
                HookTrigger.POST_PROCESS: [],
                HookTrigger.ON_ERROR: [],
                HookTrigger.ON_STARTUP: [],
                HookTrigger.ON_SHUTDOWN: []
            }
            cls._instance._hook_classes = {}
        return cls._instance

    def register_hook_class(
        self,
        hook_id: str,
        hook_class: Type[BaseHook]
    ) -> None:
        """
        Register a hook class for later instantiation.

        Args:
            hook_id: Unique identifier for hook
            hook_class: Hook class to register
        """
        self._hook_classes[hook_id] = hook_class
        logger.info(
            "hook_class_registered",
            hook_id=hook_id,
            hook_class=hook_class.__name__
        )

    def register_hook(
        self,
        trigger: HookTrigger,
        hook: BaseHook
    ) -> None:
        """
        Register a hook instance for a specific trigger.

        Args:
            trigger: When to execute hook
            hook: Hook instance
        """
        if hook not in self._hooks[trigger]:
            self._hooks[trigger].append(hook)

            # Sort by priority (lower = higher priority)
            self._hooks[trigger].sort(key=lambda h: h.priority)

            logger.info(
                "hook_registered",
                hook_id=hook.hook_id,
                trigger=trigger.value,
                priority=hook.priority,
                total_hooks=len(self._hooks[trigger])
            )

    def unregister_hook(
        self,
        trigger: HookTrigger,
        hook_id: str
    ) -> None:
        """
        Unregister a hook.

        Args:
            trigger: Hook trigger type
            hook_id: Hook identifier
        """
        self._hooks[trigger] = [
            h for h in self._hooks[trigger]
            if h.hook_id != hook_id
        ]

        logger.info(
            "hook_unregistered",
            hook_id=hook_id,
            trigger=trigger.value
        )

    def get_hooks(self, trigger: HookTrigger) -> List[BaseHook]:
        """
        Get all hooks for a specific trigger.

        Args:
            trigger: Hook trigger type

        Returns:
            List of hooks (sorted by priority)
        """
        return self._hooks[trigger].copy()

    def get_hook_class(self, hook_id: str) -> Optional[Type[BaseHook]]:
        """
        Get registered hook class by ID.

        Args:
            hook_id: Hook identifier

        Returns:
            Hook class or None if not found
        """
        return self._hook_classes.get(hook_id)

    def create_hook(
        self,
        hook_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[BaseHook]:
        """
        Create hook instance from registered class.

        Args:
            hook_id: Hook identifier
            config: Optional hook configuration

        Returns:
            Hook instance or None if class not found
        """
        hook_class = self.get_hook_class(hook_id)

        if hook_class is None:
            logger.error(
                "hook_class_not_found",
                hook_id=hook_id
            )
            return None

        try:
            if config:
                hook = hook_class(**config)
            else:
                hook = hook_class()

            logger.info(
                "hook_created",
                hook_id=hook_id,
                hook_class=hook_class.__name__
            )

            return hook

        except Exception as e:
            logger.exception(
                "hook_creation_failed",
                hook_id=hook_id,
                error=str(e)
            )
            return None

    def load_hooks_from_config(self, config: Dict[str, Any]) -> None:
        """
        Load and register hooks from configuration.

        Args:
            config: Configuration dict with hooks definition
        """
        hooks_config = config.get("hooks", [])

        for hook_config in hooks_config:
            hook_id = hook_config["hook_id"]
            enabled = hook_config.get("enabled", True)

            if not enabled:
                logger.info(
                    "hook_disabled",
                    hook_id=hook_id
                )
                continue

            # Create hook
            hook = self.create_hook(
                hook_id=hook_id,
                config=hook_config.get("config")
            )

            if hook is None:
                continue

            # Register for specified triggers
            triggers = hook_config.get("triggers", [])
            for trigger_str in triggers:
                try:
                    trigger = HookTrigger(trigger_str)
                    self.register_hook(trigger, hook)
                except ValueError:
                    logger.error(
                        "invalid_hook_trigger",
                        hook_id=hook_id,
                        trigger=trigger_str
                    )

        logger.info(
            "hooks_loaded_from_config",
            total_hooks=sum(len(hooks) for hooks in self._hooks.values())
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get hook registry statistics."""
        return {
            "registered_classes": len(self._hook_classes),
            "hooks_by_trigger": {
                trigger.value: len(hooks)
                for trigger, hooks in self._hooks.items()
            },
            "total_hooks": sum(len(hooks) for hooks in self._hooks.values()),
            "hook_details": {
                trigger.value: [
                    {
                        "hook_id": hook.hook_id,
                        "priority": hook.priority,
                        "enabled": hook.enabled
                    }
                    for hook in hooks
                ]
                for trigger, hooks in self._hooks.items()
            }
        }


# Global hook registry instance
hook_registry = HookRegistry()
```

---

## Hook Types & Lifecycle

### Hook Trigger Types

```python
# Execution_Layer/Hooks/base_hook.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class HookTrigger(str, Enum):
    """Hook trigger types."""
    PRE_PROCESS = "pre_process"      # Before task processing
    POST_PROCESS = "post_process"    # After successful processing
    ON_ERROR = "on_error"            # When error occurs
    ON_STARTUP = "on_startup"        # Agent initialization
    ON_SHUTDOWN = "on_shutdown"      # Agent shutdown


class HookExecutionContext:
    """Context passed to hooks during execution."""

    def __init__(
        self,
        trigger: HookTrigger,
        agent_id: str,
        task: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.trigger = trigger
        self.agent_id = agent_id
        self.task = task or {}
        self.result = result or {}
        self.error = error
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dict for logging."""
        return {
            "trigger": self.trigger.value,
            "agent_id": self.agent_id,
            "task_id": self.task.get("id"),
            "has_error": self.error is not None,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class BaseHook(ABC):
    """Base class for all hooks."""

    def __init__(
        self,
        hook_id: str,
        priority: int = 100,
        enabled: bool = True
    ):
        """
        Initialize hook.

        Args:
            hook_id: Unique hook identifier
            priority: Execution priority (lower = higher priority)
            enabled: Whether hook is enabled
        """
        self.hook_id = hook_id
        self.priority = priority
        self.enabled = enabled
        self.execution_count = 0
        self.error_count = 0
        self.total_execution_time_ms = 0

    @abstractmethod
    async def execute(
        self,
        context: HookExecutionContext
    ) -> Optional[Dict[str, Any]]:
        """
        Execute hook logic.

        Args:
            context: Execution context

        Returns:
            Optional result (can modify context)
        """
        pass

    def should_execute(self, context: HookExecutionContext) -> bool:
        """
        Determine if hook should execute.

        Override for conditional execution.

        Args:
            context: Execution context

        Returns:
            True if hook should execute
        """
        return self.enabled

    async def on_error(self, error: Exception, context: HookExecutionContext) -> None:
        """
        Handle hook execution error.

        Override for custom error handling.

        Args:
            error: Exception that occurred
            context: Execution context
        """
        self.error_count += 1

        logger.error(
            "hook_execution_error",
            hook_id=self.hook_id,
            error=str(error),
            context=context.to_dict()
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get hook statistics."""
        avg_time = (
            self.total_execution_time_ms / self.execution_count
            if self.execution_count > 0 else 0
        )

        return {
            "hook_id": self.hook_id,
            "priority": self.priority,
            "enabled": self.enabled,
            "execution_count": self.execution_count,
            "error_count": self.error_count,
            "avg_execution_time_ms": avg_time,
            "error_rate": (
                self.error_count / self.execution_count
                if self.execution_count > 0 else 0
            )
        }
```

---

## Hook Implementation

### Built-in Hooks

#### 1. Logging Hook

```python
# Execution_Layer/Hooks/logging_hook.py
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger, HookExecutionContext
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class LoggingHook(BaseHook):
    """
    Log all agent task processing.

    Priority: 10 (high priority, execute first)
    """

    def __init__(self):
        super().__init__(
            hook_id="logging",
            priority=10  # High priority
        )

    async def execute(self, context: HookExecutionContext) -> None:
        """Log based on trigger type."""
        self.execution_count += 1
        start = datetime.utcnow()

        try:
            if context.trigger == HookTrigger.PRE_PROCESS:
                self._log_pre_process(context)

            elif context.trigger == HookTrigger.POST_PROCESS:
                self._log_post_process(context)

            elif context.trigger == HookTrigger.ON_ERROR:
                self._log_error(context)

            elif context.trigger == HookTrigger.ON_STARTUP:
                self._log_startup(context)

            elif context.trigger == HookTrigger.ON_SHUTDOWN:
                self._log_shutdown(context)

        finally:
            execution_time = int(
                (datetime.utcnow() - start).total_seconds() * 1000
            )
            self.total_execution_time_ms += execution_time

    def _log_pre_process(self, context: HookExecutionContext) -> None:
        """Log task start."""
        logger.info(
            "task_started",
            agent_id=context.agent_id,
            task_id=context.task.get("id"),
            task_type=context.task.get("type"),
            timestamp=context.timestamp.isoformat()
        )

    def _log_post_process(self, context: HookExecutionContext) -> None:
        """Log task completion."""
        logger.info(
            "task_completed",
            agent_id=context.agent_id,
            task_id=context.task.get("id"),
            success=context.result.get("success"),
            processing_time_ms=context.result.get("processing_time_ms"),
            timestamp=context.timestamp.isoformat()
        )

    def _log_error(self, context: HookExecutionContext) -> None:
        """Log task error."""
        logger.error(
            "task_failed",
            agent_id=context.agent_id,
            task_id=context.task.get("id"),
            error=str(context.error),
            error_type=type(context.error).__name__,
            timestamp=context.timestamp.isoformat()
        )

    def _log_startup(self, context: HookExecutionContext) -> None:
        """Log agent startup."""
        logger.info(
            "agent_started",
            agent_id=context.agent_id,
            timestamp=context.timestamp.isoformat()
        )

    def _log_shutdown(self, context: HookExecutionContext) -> None:
        """Log agent shutdown."""
        logger.info(
            "agent_shutdown",
            agent_id=context.agent_id,
            timestamp=context.timestamp.isoformat(),
            metadata=context.metadata
        )
```

#### 2. Metrics Hook

```python
# Execution_Layer/Hooks/metrics_hook.py
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger, HookExecutionContext
from prometheus_client import Counter, Histogram, Gauge
from datetime import datetime


# Prometheus metrics
task_counter = Counter(
    'agent_tasks_total',
    'Total tasks processed',
    ['agent_id', 'status']
)

task_duration = Histogram(
    'agent_task_duration_seconds',
    'Task processing duration',
    ['agent_id']
)

active_tasks = Gauge(
    'agent_active_tasks',
    'Currently active tasks',
    ['agent_id']
)


class MetricsHook(BaseHook):
    """
    Collect Prometheus metrics for agent tasks.

    Priority: 20 (high priority)
    """

    def __init__(self):
        super().__init__(
            hook_id="metrics",
            priority=20
        )

    async def execute(self, context: HookExecutionContext) -> None:
        """Collect metrics based on trigger."""
        self.execution_count += 1

        if context.trigger == HookTrigger.PRE_PROCESS:
            # Increment active tasks
            active_tasks.labels(agent_id=context.agent_id).inc()

        elif context.trigger == HookTrigger.POST_PROCESS:
            # Task completed successfully
            status = "success" if context.result.get("success") else "failed"

            # Increment counter
            task_counter.labels(
                agent_id=context.agent_id,
                status=status
            ).inc()

            # Record duration
            if "processing_time_ms" in context.result:
                duration_sec = context.result["processing_time_ms"] / 1000
                task_duration.labels(
                    agent_id=context.agent_id
                ).observe(duration_sec)

            # Decrement active tasks
            active_tasks.labels(agent_id=context.agent_id).dec()

        elif context.trigger == HookTrigger.ON_ERROR:
            # Task failed
            task_counter.labels(
                agent_id=context.agent_id,
                status="error"
            ).inc()

            # Decrement active tasks
            active_tasks.labels(agent_id=context.agent_id).dec()
```

#### 3. Notification Hook

```python
# Execution_Layer/Hooks/notification_hook.py
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger, HookExecutionContext
from typing import Any, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class NotificationHook(BaseHook):
    """
    Send notifications on task completion or errors.

    Priority: 50 (medium priority)
    """

    def __init__(self, notification_service_url: str):
        super().__init__(
            hook_id="notification",
            priority=50
        )
        self.notification_service_url = notification_service_url

    async def execute(self, context: HookExecutionContext) -> None:
        """Send notifications based on trigger."""
        self.execution_count += 1

        if context.trigger == HookTrigger.POST_PROCESS:
            await self._handle_success_notification(context)

        elif context.trigger == HookTrigger.ON_ERROR:
            await self._handle_error_notification(context)

    async def _handle_success_notification(
        self,
        context: HookExecutionContext
    ) -> None:
        """Send success notification if requested."""
        task = context.task
        result = context.result

        # Only send if task requested notification
        if not task.get("notify_user"):
            return

        user_id = task.get("user_id")
        if not user_id:
            return

        message = self._build_success_message(task, result)

        await self._send_notification(
            user_id=user_id,
            message=message,
            severity="info"
        )

    async def _handle_error_notification(
        self,
        context: HookExecutionContext
    ) -> None:
        """Send error notification to admins."""
        error = context.error
        task = context.task

        message = self._build_error_message(task, error)

        # Send to admin channel
        await self._send_notification(
            user_id="admin",
            message=message,
            severity="error"
        )

    def _build_success_message(
        self,
        task: Dict[str, Any],
        result: Dict[str, Any]
    ) -> str:
        """Build success notification message."""
        document_id = task.get("document_id", "unknown")
        processing_time = result.get("processing_time_ms", 0) / 1000

        return (
            f"Dokument {document_id} erfolgreich verarbeitet "
            f"({processing_time:.2f}s)"
        )

    def _build_error_message(
        self,
        task: Dict[str, Any],
        error: Exception
    ) -> str:
        """Build error notification message."""
        task_id = task.get("id", "unknown")
        error_type = type(error).__name__

        return (
            f"Aufgabe {task_id} fehlgeschlagen: "
            f"{error_type}: {str(error)}"
        )

    async def _send_notification(
        self,
        user_id: str,
        message: str,
        severity: str
    ) -> None:
        """Send notification via notification service."""
        # Implementation would use actual notification service
        logger.info(
            "notification_sent",
            user_id=user_id,
            message=message,
            severity=severity
        )
```

#### 4. Cache Invalidation Hook

```python
# Execution_Layer/Hooks/cache_invalidation_hook.py
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger, HookExecutionContext
from app.services.cache_service import CacheService
import structlog

logger = structlog.get_logger(__name__)


class CacheInvalidationHook(BaseHook):
    """
    Invalidate cache entries after task completion.

    Priority: 60 (lower priority, execute after core operations)
    """

    def __init__(self):
        super().__init__(
            hook_id="cache_invalidation",
            priority=60
        )
        self.cache_service = CacheService()

    async def execute(self, context: HookExecutionContext) -> None:
        """Invalidate cache on post-process."""
        self.execution_count += 1

        if context.trigger != HookTrigger.POST_PROCESS:
            return

        result = context.result
        if not result.get("success"):
            return

        # Determine which cache keys to invalidate
        cache_keys = self._determine_cache_keys(context)

        if cache_keys:
            await self._invalidate_cache_keys(cache_keys)

    def _determine_cache_keys(
        self,
        context: HookExecutionContext
    ) -> List[str]:
        """Determine which cache keys to invalidate."""
        keys = []

        task = context.task
        result = context.result

        # Invalidate document cache
        if "document_id" in task:
            doc_id = task["document_id"]
            keys.extend([
                f"doc:{doc_id}",
                f"doc_metadata:{doc_id}",
                f"doc_ocr_result:{doc_id}"
            ])

        # Invalidate user cache
        if "user_id" in task:
            user_id = task["user_id"]
            keys.append(f"user_documents:{user_id}")

        return keys

    async def _invalidate_cache_keys(self, keys: List[str]) -> None:
        """Invalidate cache keys."""
        for key in keys:
            await self.cache_service.delete(key)

        logger.info(
            "cache_invalidated",
            hook_id=self.hook_id,
            invalidated_keys=len(keys)
        )
```

---

## Hook Configuration

### Configuration File

```yaml
# config/hooks.yaml
hooks:
  # Logging Hook (highest priority)
  - hook_id: "logging"
    class: "Execution_Layer.Hooks.logging_hook.LoggingHook"
    enabled: true
    priority: 10
    triggers:
      - "pre_process"
      - "post_process"
      - "on_error"
      - "on_startup"
      - "on_shutdown"

  # Metrics Hook
  - hook_id: "metrics"
    class: "Execution_Layer.Hooks.metrics_hook.MetricsHook"
    enabled: true
    priority: 20
    triggers:
      - "pre_process"
      - "post_process"
      - "on_error"

  # Notification Hook
  - hook_id: "notification"
    class: "Execution_Layer.Hooks.notification_hook.NotificationHook"
    enabled: true
    priority: 50
    triggers:
      - "post_process"
      - "on_error"
    config:
      notification_service_url: "http://localhost:8080/notifications"

  # Cache Invalidation Hook
  - hook_id: "cache_invalidation"
    class: "Execution_Layer.Hooks.cache_invalidation_hook.CacheInvalidationHook"
    enabled: true
    priority: 60
    triggers:
      - "post_process"

  # Rate Limiting Hook (conditional execution)
  - hook_id: "rate_limiting"
    class: "Execution_Layer.Hooks.rate_limiting_hook.RateLimitingHook"
    enabled: true
    priority: 5  # Very high priority (before processing)
    triggers:
      - "pre_process"
    config:
      max_requests_per_minute: 100
      per_user_limit: true

  # Audit Logging Hook
  - hook_id: "audit_logging"
    class: "Execution_Layer.Hooks.audit_logging_hook.AuditLoggingHook"
    enabled: true
    priority: 15
    triggers:
      - "pre_process"
      - "post_process"
    config:
      audit_log_path: "/var/log/ablage/audit.log"
      sensitive_fields: ["password", "api_key", "token"]
```

### Loading Configuration

```python
# app/core/config.py
import yaml
from Execution_Layer.Hooks.hook_registry import hook_registry


def load_hook_configuration(config_path: str = "config/hooks.yaml") -> None:
    """
    Load hook configuration from YAML file.

    Args:
        config_path: Path to hooks configuration file
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Register hook classes first
    _register_hook_classes()

    # Load hooks from configuration
    hook_registry.load_hooks_from_config(config)


def _register_hook_classes() -> None:
    """Register all available hook classes."""
    from Execution_Layer.Hooks.logging_hook import LoggingHook
    from Execution_Layer.Hooks.metrics_hook import MetricsHook
    from Execution_Layer.Hooks.notification_hook import NotificationHook
    from Execution_Layer.Hooks.cache_invalidation_hook import CacheInvalidationHook

    hook_registry.register_hook_class("logging", LoggingHook)
    hook_registry.register_hook_class("metrics", MetricsHook)
    hook_registry.register_hook_class("notification", NotificationHook)
    hook_registry.register_hook_class("cache_invalidation", CacheInvalidationHook)
```

---

## Hook Execution Order

Hooks werden in **Priority-Reihenfolge** ausgeführt (niedrigerer Wert = höhere Priorität):

```
Priority    Hook                    Purpose
--------    --------------------    ------------------------
5           Rate Limiting Hook      Block excessive requests
10          Logging Hook            Log all operations
15          Audit Logging Hook      Compliance logging
20          Metrics Hook            Collect metrics
30          Validation Hook         Validate inputs
40          Auth Check Hook         Verify permissions
50          Notification Hook       Send notifications
60          Cache Invalidation      Clear stale cache
70          Cleanup Hook            Resource cleanup
```

### Execution Example

```
Task: Process Document

1. PRE_PROCESS Hooks (in priority order):
   [5]  Rate Limiting Hook    → Check rate limits
   [10] Logging Hook          → Log task start
   [15] Audit Logging Hook    → Audit log entry
   [20] Metrics Hook          → Increment active tasks
   [30] Validation Hook       → Validate document
   [40] Auth Check Hook       → Verify permissions

2. ACTUAL PROCESSING:
   → OCR Processing Agent executes

3. POST_PROCESS Hooks (in priority order):
   [10] Logging Hook          → Log task completion
   [15] Audit Logging Hook    → Audit log completion
   [20] Metrics Hook          → Record metrics
   [50] Notification Hook     → Notify user
   [60] Cache Invalidation    → Invalidate cache
```

---

## Custom Hook Development

### Creating a Custom Hook

```python
# Execution_Layer/Hooks/custom_hook_example.py
from Execution_Layer.Hooks.base_hook import BaseHook, HookTrigger, HookExecutionContext
from typing import Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class CustomProcessingHook(BaseHook):
    """
    Example custom hook.

    This hook demonstrates:
    - Conditional execution
    - Configuration usage
    - Error handling
    - State management
    """

    def __init__(
        self,
        max_processing_time_ms: int = 5000,
        alert_threshold_ms: int = 3000
    ):
        super().__init__(
            hook_id="custom_processing",
            priority=45  # Medium-low priority
        )
        self.max_processing_time_ms = max_processing_time_ms
        self.alert_threshold_ms = alert_threshold_ms
        self.slow_tasks = []

    def should_execute(self, context: HookExecutionContext) -> bool:
        """Only execute for specific task types."""
        # Only execute on POST_PROCESS for OCR tasks
        if context.trigger != HookTrigger.POST_PROCESS:
            return False

        task_type = context.task.get("type")
        return task_type == "ocr_processing"

    async def execute(self, context: HookExecutionContext) -> Dict[str, Any]:
        """Check processing time and alert if slow."""
        self.execution_count += 1

        result = context.result
        processing_time_ms = result.get("processing_time_ms", 0)

        # Check if task was slow
        if processing_time_ms > self.alert_threshold_ms:
            self._handle_slow_task(context, processing_time_ms)

        # Check if task exceeded max time
        if processing_time_ms > self.max_processing_time_ms:
            self._handle_timeout_task(context, processing_time_ms)

        # Return modified context (optional)
        return {
            "processing_time_category": self._categorize_processing_time(
                processing_time_ms
            )
        }

    def _handle_slow_task(
        self,
        context: HookExecutionContext,
        processing_time_ms: int
    ) -> None:
        """Handle slow task detection."""
        task_id = context.task.get("id")

        self.slow_tasks.append({
            "task_id": task_id,
            "agent_id": context.agent_id,
            "processing_time_ms": processing_time_ms,
            "timestamp": context.timestamp.isoformat()
        })

        logger.warning(
            "slow_task_detected",
            hook_id=self.hook_id,
            task_id=task_id,
            processing_time_ms=processing_time_ms,
            threshold_ms=self.alert_threshold_ms
        )

    def _handle_timeout_task(
        self,
        context: HookExecutionContext,
        processing_time_ms: int
    ) -> None:
        """Handle task timeout."""
        task_id = context.task.get("id")

        logger.error(
            "task_timeout",
            hook_id=self.hook_id,
            task_id=task_id,
            processing_time_ms=processing_time_ms,
            max_time_ms=self.max_processing_time_ms
        )

        # Could trigger alert here
        # await self.send_alert(...)

    def _categorize_processing_time(self, time_ms: int) -> str:
        """Categorize processing time."""
        if time_ms < 1000:
            return "fast"
        elif time_ms < 3000:
            return "normal"
        elif time_ms < 5000:
            return "slow"
        else:
            return "very_slow"

    def get_stats(self) -> Dict[str, Any]:
        """Get hook statistics including slow tasks."""
        stats = super().get_stats()
        stats["slow_tasks_count"] = len(self.slow_tasks)
        stats["recent_slow_tasks"] = self.slow_tasks[-10:]  # Last 10
        return stats
```

### Registering Custom Hook

```python
# In app startup
from Execution_Layer.Hooks.hook_registry import hook_registry
from Execution_Layer.Hooks.custom_hook_example import CustomProcessingHook

# Register hook class
hook_registry.register_hook_class(
    "custom_processing",
    CustomProcessingHook
)

# Create and register hook instance
custom_hook = CustomProcessingHook(
    max_processing_time_ms=5000,
    alert_threshold_ms=3000
)

hook_registry.register_hook(
    HookTrigger.POST_PROCESS,
    custom_hook
)
```

---

## Hook Testing

### Test Template

```python
# tests/unit/hooks/test_custom_hook.py
import pytest
from datetime import datetime
from Execution_Layer.Hooks.custom_hook_example import CustomProcessingHook
from Execution_Layer.Hooks.base_hook import HookTrigger, HookExecutionContext


@pytest.mark.asyncio
async def test_custom_hook_slow_task_detection():
    """Test slow task detection."""
    hook = CustomProcessingHook(alert_threshold_ms=1000)

    context = HookExecutionContext(
        trigger=HookTrigger.POST_PROCESS,
        agent_id="test_agent",
        task={"id": "task_123", "type": "ocr_processing"},
        result={"success": True, "processing_time_ms": 2000}
    )

    # Execute hook
    result = await hook.execute(context)

    # Should detect as slow
    assert hook.execution_count == 1
    assert len(hook.slow_tasks) == 1
    assert hook.slow_tasks[0]["task_id"] == "task_123"
    assert result["processing_time_category"] == "slow"


@pytest.mark.asyncio
async def test_custom_hook_conditional_execution():
    """Test conditional execution based on task type."""
    hook = CustomProcessingHook()

    # Context with wrong task type
    context = HookExecutionContext(
        trigger=HookTrigger.POST_PROCESS,
        agent_id="test_agent",
        task={"id": "task_456", "type": "other_processing"},
        result={"success": True, "processing_time_ms": 2000}
    )

    # Should not execute
    assert not hook.should_execute(context)


@pytest.mark.asyncio
async def test_custom_hook_timeout_handling():
    """Test timeout handling."""
    hook = CustomProcessingHook(max_processing_time_ms=3000)

    context = HookExecutionContext(
        trigger=HookTrigger.POST_PROCESS,
        agent_id="test_agent",
        task={"id": "task_789", "type": "ocr_processing"},
        result={"success": True, "processing_time_ms": 5000}
    )

    # Execute hook
    result = await hook.execute(context)

    # Should categorize as very_slow
    assert result["processing_time_category"] == "very_slow"


@pytest.mark.asyncio
async def test_custom_hook_stats():
    """Test hook statistics."""
    hook = CustomProcessingHook(alert_threshold_ms=1000)

    # Execute multiple tasks
    for i in range(5):
        context = HookExecutionContext(
            trigger=HookTrigger.POST_PROCESS,
            agent_id="test_agent",
            task={"id": f"task_{i}", "type": "ocr_processing"},
            result={"success": True, "processing_time_ms": 1500}  # Slow
        )
        await hook.execute(context)

    # Get stats
    stats = hook.get_stats()

    assert stats["execution_count"] == 5
    assert stats["slow_tasks_count"] == 5
    assert stats["error_count"] == 0
```

---

## Hook Monitoring

### Metrics for Hooks

```python
# Prometheus metrics for hooks
from prometheus_client import Counter, Histogram

hook_executions = Counter(
    'hook_executions_total',
    'Total hook executions',
    ['hook_id', 'trigger', 'status']
)

hook_execution_duration = Histogram(
    'hook_execution_duration_seconds',
    'Hook execution duration',
    ['hook_id']
)

hook_errors = Counter(
    'hook_errors_total',
    'Total hook errors',
    ['hook_id', 'error_type']
)
```

### Dashboard Queries

```promql
# Hook execution rate
rate(hook_executions_total[5m])

# Hook error rate
rate(hook_errors_total[5m]) / rate(hook_executions_total[5m])

# Slow hooks
hook_execution_duration_seconds{quantile="0.95"} > 0.1

# Most executed hooks
topk(5, sum by (hook_id) (hook_executions_total))
```

---

**Document Status:** ✅ **COMPLETE**

Das Hook Registry System ist vollständig dokumentiert mit:
- ✅ Vollständige Registry-Implementierung
- ✅ Hook-Lifecycle Management
- ✅ 4 Built-in Hooks mit Code
- ✅ Custom Hook Development Guide
- ✅ Testing Strategies
- ✅ Monitoring & Metrics

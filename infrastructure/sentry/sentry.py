"""
Sentry Integration - Ablage-System OCR
Error tracking and performance monitoring
"""

import os
import logging
from typing import Optional, Dict, Any
from functools import wraps

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

logger = logging.getLogger(__name__)


def init_sentry(
    dsn: Optional[str] = None,
    environment: Optional[str] = None,
    release: Optional[str] = None,
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.1,
    enable_tracing: bool = True
) -> None:
    """
    Initialize Sentry SDK with all integrations.

    Args:
        dsn: Sentry DSN (Data Source Name)
        environment: Environment name (dev, staging, production)
        release: Release version
        traces_sample_rate: Percentage of transactions to trace (0.0-1.0)
        profiles_sample_rate: Percentage of transactions to profile (0.0-1.0)
        enable_tracing: Enable performance tracing
    """
    # Get configuration from environment if not provided
    dsn = dsn or os.getenv('SENTRY_DSN')
    environment = environment or os.getenv('ENVIRONMENT', 'development')
    release = release or os.getenv('VERSION', 'unknown')

    if not dsn:
        logger.warning("Sentry DSN not configured - error tracking disabled")
        return

    # Configure logging integration
    logging_integration = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Send errors as events
    )

    # Initialize Sentry
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,

        # Integrations
        integrations=[
            FastApiIntegration(
                transaction_style="endpoint",  # Use endpoint name as transaction
                # Sprint 0 / G10 (2026-05-05): failed_request_status_codes existiert erst
                # ab sentry-sdk 1.45+. Wir laufen auf 1.40.6 - Parameter entfernt.
                # 5xx werden trotzdem als Errors getrackt (Sentry-Default).
            ),
            SqlalchemyIntegration(),
            RedisIntegration(),
            CeleryIntegration(
                monitor_beat_tasks=True,  # Track Celery beat scheduled tasks
            ),
            logging_integration,
        ],

        # Performance monitoring
        traces_sample_rate=traces_sample_rate if enable_tracing else 0.0,
        profiles_sample_rate=profiles_sample_rate if enable_tracing else 0.0,

        # Additional options
        send_default_pii=False,  # Don't send personally identifiable information
        attach_stacktrace=True,  # Attach stack traces to all messages
        max_breadcrumbs=50,      # Keep last 50 breadcrumbs

        # Filter sensitive data
        before_send=before_send_filter,
        before_breadcrumb=before_breadcrumb_filter,
    )

    logger.info(
        f"Sentry initialized - Environment: {environment}, "
        f"Release: {release}, Traces: {traces_sample_rate*100}%"
    )


def before_send_filter(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Filter and scrub sensitive data before sending to Sentry.

    Args:
        event: Sentry event dictionary
        hint: Additional context

    Returns:
        Filtered event or None to drop event
    """
    # Don't send events for certain exceptions
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']

        # Ignore specific exceptions
        ignored_exceptions = [
            'fastapi.exceptions.RequestValidationError',
            'starlette.exceptions.HTTPException',
        ]

        if any(exc.__class__.__name__ == name for name in ignored_exceptions for exc in [exc_type]):
            return None

    # Scrub sensitive data from request
    if 'request' in event:
        request = event['request']

        # Remove sensitive headers
        if 'headers' in request:
            sensitive_headers = ['authorization', 'cookie', 'x-api-key']
            for header in sensitive_headers:
                if header in request['headers']:
                    request['headers'][header] = '[Filtered]'

        # Remove sensitive query parameters
        if 'query_string' in request:
            sensitive_params = ['token', 'api_key', 'password']
            # Simple scrubbing - in production, use proper URL parsing
            for param in sensitive_params:
                if param in request['query_string']:
                    request['query_string'] = '[Filtered]'

        # Remove sensitive POST data
        if 'data' in request:
            sensitive_fields = ['password', 'token', 'api_key', 'secret']
            if isinstance(request['data'], dict):
                for field in sensitive_fields:
                    if field in request['data']:
                        request['data'][field] = '[Filtered]'

    return event


def before_breadcrumb_filter(crumb: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Filter breadcrumbs before adding to event.

    Args:
        crumb: Breadcrumb dictionary
        hint: Additional context

    Returns:
        Filtered breadcrumb or None to drop
    """
    # Don't log health check requests
    if crumb.get('category') == 'http' and '/health' in crumb.get('data', {}).get('url', ''):
        return None

    # Scrub sensitive data from logs
    if crumb.get('category') == 'log':
        message = crumb.get('message', '')

        # Filter patterns
        sensitive_patterns = [
            'password=',
            'token=',
            'api_key=',
            'Authorization:',
        ]

        for pattern in sensitive_patterns:
            if pattern in message:
                crumb['message'] = '[Sensitive data filtered]'
                break

    return crumb


def set_user_context(user_id: str, email: Optional[str] = None, username: Optional[str] = None) -> None:
    """
    Set user context for error tracking.

    Args:
        user_id: User ID
        email: User email (will be filtered if send_default_pii=False)
        username: Username
    """
    sentry_sdk.set_user({
        'id': user_id,
        'email': email,
        'username': username,
    })


def set_context(name: str, context: Dict[str, Any]) -> None:
    """
    Add custom context to events.

    Args:
        name: Context name
        context: Context data
    """
    sentry_sdk.set_context(name, context)


def add_breadcrumb(message: str, category: str, level: str = 'info', data: Optional[Dict[str, Any]] = None) -> None:
    """
    Add breadcrumb for debugging.

    Args:
        message: Breadcrumb message
        category: Category (e.g., 'auth', 'query', 'ocr')
        level: Level (debug, info, warning, error, critical)
        data: Additional data
    """
    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data or {}
    )


def capture_exception(error: Exception, extra: Optional[Dict[str, Any]] = None) -> str:
    """
    Manually capture an exception.

    Args:
        error: Exception to capture
        extra: Additional context

    Returns:
        Event ID
    """
    if extra:
        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_exception(error)

    return sentry_sdk.capture_exception(error)


def capture_message(message: str, level: str = 'info', extra: Optional[Dict[str, Any]] = None) -> str:
    """
    Capture a message.

    Args:
        message: Message to capture
        level: Level (debug, info, warning, error, critical)
        extra: Additional context

    Returns:
        Event ID
    """
    if extra:
        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_message(message, level=level)

    return sentry_sdk.capture_message(message, level=level)


def trace_function(name: Optional[str] = None, op: Optional[str] = None):
    """
    Decorator to trace function execution.

    Args:
        name: Transaction name (defaults to function name)
        op: Operation name (e.g., 'ocr.process', 'db.query')

    Usage:
        @trace_function(op='ocr.process')
        async def process_document(doc_id: str) -> str:
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            transaction_name = name or func.__name__
            operation = op or f'function.{func.__name__}'

            with sentry_sdk.start_transaction(op=operation, name=transaction_name):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            transaction_name = name or func.__name__
            operation = op or f'function.{func.__name__}'

            with sentry_sdk.start_transaction(op=operation, name=transaction_name):
                return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def trace_span(op: str, description: Optional[str] = None):
    """
    Decorator to create a span within a transaction.

    Args:
        op: Operation name
        description: Span description

    Usage:
        @trace_span(op='db.query', description='Fetch documents')
        async def fetch_documents():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with sentry_sdk.start_span(op=op, description=description or func.__name__):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with sentry_sdk.start_span(op=op, description=description or func.__name__):
                return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Context manager for custom transactions
class SentryTransaction:
    """
    Context manager for custom transactions.

    Usage:
        with SentryTransaction('ocr.batch_process', op='ocr') as transaction:
            # Your code here
            transaction.set_tag('backend', 'deepseek')
            transaction.set_data('batch_size', 32)
    """

    def __init__(self, name: str, op: str = 'custom'):
        self.name = name
        self.op = op
        self._transaction = None

    def __enter__(self):
        self._transaction = sentry_sdk.start_transaction(op=self.op, name=self.name)
        self._transaction.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._transaction:
            self._transaction.__exit__(exc_type, exc_val, exc_tb)

    def set_tag(self, key: str, value: str) -> None:
        """Set a tag on the transaction."""
        if self._transaction:
            self._transaction.set_tag(key, value)

    def set_data(self, key: str, value: Any) -> None:
        """Set data on the transaction."""
        if self._transaction:
            self._transaction.set_data(key, value)

    def set_status(self, status: str) -> None:
        """Set transaction status."""
        if self._transaction:
            self._transaction.set_status(status)


# GPU-specific monitoring
def track_gpu_operation(operation: str, backend: str):
    """
    Track GPU operation with Sentry.

    Args:
        operation: Operation name (e.g., 'ocr', 'inference')
        backend: Backend name (e.g., 'deepseek', 'got_ocr')

    Usage:
        with track_gpu_operation('ocr', 'deepseek'):
            result = model.process(image)
    """
    return SentryTransaction(
        name=f'gpu.{operation}',
        op=f'gpu.{backend}'
    )

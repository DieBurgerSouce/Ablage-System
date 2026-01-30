"""
Logging middleware for request/response tracking.

Provides automatic logging of all HTTP requests with timing and context.
"""
import time
import uuid
from typing import Callable, Optional
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Context variables for request tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
request_var: ContextVar[Optional[Request]] = ContextVar('request', default=None)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request/response logging.

    Features:
    - Correlation ID generation and tracking
    - Request/response timing
    - User context tracking
    - Error logging
    - German language logging
    """

    def __init__(
        self,
        app,
        skip_paths: Optional[list] = None,
        log_request_body: bool = False,
        log_response_body: bool = False
    ):
        """
        Initialize logging middleware.

        Args:
            app: FastAPI application
            skip_paths: Paths to skip logging (e.g., /health)
            log_request_body: Whether to log request bodies
            log_response_body: Whether to log response bodies
        """
        super().__init__(app)
        self.skip_paths = skip_paths or ['/health', '/metrics', '/favicon.ico']
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and response with logging.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response
        """
        # Skip logging for certain paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        # Generate/Extract Request ID (consolidated approach)
        # Priority: 1. request.state (set by security_headers), 2. X-Request-ID, 3. X-Correlation-ID, 4. Generate
        correlation_id = (
            getattr(request.state, 'request_id', None) or
            request.headers.get('X-Request-ID') or
            request.headers.get('X-Correlation-ID') or
            str(uuid.uuid4())
        )
        # Store in request.state for other middleware
        request.state.request_id = correlation_id

        # Set context variables
        correlation_id_var.set(correlation_id)
        request_var.set(request)

        # Start timing
        start_time = time.time()

        # Extract user context if available
        user_id = None
        user_email = None
        try:
            # Try to get user from JWT if present
            if hasattr(request.state, 'user'):
                user_id = str(request.state.user.id)
                user_email = request.state.user.email
        except (AttributeError, TypeError) as e:
            logger.debug(
                "user_context_extraction_failed",
                error_type=type(e).__name__,
            )

        # Log request (German)
        client_host = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")
        logger.info(
            "eingehende_anfrage",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            client=client_host,
            user_id=user_id
        )

        # Log request body if enabled and not too large
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                content_length = request.headers.get("content-length", "0")
                if int(content_length) < 10000:  # Only log bodies under 10KB
                    body = await request.body()
                    logger.debug(
                        "anfrage_koerper",
                        correlation_id=correlation_id,
                        size_bytes=len(body)
                    )
                    # Reset body for downstream processing
                    request._body = body
            except Exception as e:
                logger.warning(
                    "fehler_beim_lesen_anfrage_koerper",
                    correlation_id=correlation_id,
                    **safe_error_log(e)
                )

        # Process request
        response = None
        error_occurred = False
        error_message = None

        try:
            response = await call_next(request)
        except Exception as e:
            error_occurred = True
            error_message = safe_error_detail(e, "Request")

            # Log error
            logger.error(
                "anfrage_fehlgeschlagen",
                correlation_id=correlation_id,
                method=request.method,
                path=request.url.path,
                error=error_message,
                user_id=user_id,
                exc_info=True
            )

            # Re-raise the exception
            raise

        finally:
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            if response:
                # Log successful response
                log_func = logger.info
                if 400 <= response.status_code < 500:
                    log_func = logger.warning
                elif response.status_code >= 500:
                    log_func = logger.error

                log_func(
                    "ausgehende_antwort",
                    correlation_id=correlation_id,
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code,
                    duration_ms=duration_ms,
                    user_id=user_id
                )

                # Add request/correlation ID to response headers (both for compatibility)
                response.headers["X-Request-ID"] = correlation_id
                response.headers["X-Correlation-ID"] = correlation_id  # Backwards compatibility
                response.headers["X-Response-Time-ms"] = str(duration_ms)

                # Log response body if enabled and small
                if self.log_response_body and response.status_code != 200:
                    try:
                        if hasattr(response, 'body'):
                            body_size = len(response.body) if response.body else 0
                            if body_size < 10000:  # Under 10KB
                                logger.debug(
                                    "antwort_koerper",
                                    correlation_id=correlation_id,
                                    size_bytes=body_size
                                )
                    except Exception as e:
                        logger.warning(
                            "fehler_beim_lesen_antwort_koerper",
                            correlation_id=correlation_id,
                            **safe_error_log(e)
                        )

            # Log slow requests
            if duration_ms > 5000:
                logger.warning(
                    "langsame_anfrage_erkannt",
                    correlation_id=correlation_id,
                    method=request.method,
                    path=request.url.path,
                    duration_ms=duration_ms,
                    threshold_ms=5000
                )

            # Clear context variables
            correlation_id_var.set(None)
            request_var.set(None)

        return response


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    """
    Specialized middleware for error logging with German messages.
    """

    def __init__(self, app):
        """
        Initialize error logging middleware.

        Args:
            app: FastAPI application
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Catch and log all unhandled exceptions.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response or error response
        """
        try:
            response = await call_next(request)
            return response
        except ValueError as e:
            logger.error(
                "validierungsfehler",
                path=request.url.path,
                **safe_error_log(e),
                error_type="validierung",
                exc_info=True
            )
            raise
        except PermissionError as e:
            logger.error(
                "berechtigungsfehler",
                path=request.url.path,
                **safe_error_log(e),
                error_type="berechtigung",
                exc_info=True
            )
            raise
        except ConnectionError as e:
            logger.error(
                "verbindungsfehler",
                path=request.url.path,
                **safe_error_log(e),
                error_type="verbindung",
                exc_info=True
            )
            raise
        except TimeoutError as e:
            logger.error(
                "zeitueberschreitung",
                path=request.url.path,
                **safe_error_log(e),
                error_type="timeout",
                exc_info=True
            )
            raise
        except Exception as e:
            logger.critical(
                "unerwarteter_fehler",
                path=request.url.path,
                **safe_error_log(e),
                error_type="unbekannt",
                exc_info=True
            )
            raise


def get_correlation_id() -> Optional[str]:
    """
    Get current correlation/request ID from context.

    Use this when dispatching Celery tasks or making external calls
    to propagate the request ID for distributed tracing.

    Returns:
        Current correlation ID or None if not in request context
    """
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """
    Set correlation ID in current context.

    Use this in Celery tasks to restore correlation ID from headers.

    Args:
        correlation_id: The correlation ID to set
    """
    correlation_id_var.set(correlation_id)


# Export components
__all__ = [
    'LoggingMiddleware',
    'ErrorLoggingMiddleware',
    'correlation_id_var',
    'request_var',
    'get_correlation_id',
    'set_correlation_id',
]

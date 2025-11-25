"""
Sentry Middleware - Ablage-System OCR
FastAPI middleware for enhanced Sentry tracking
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import sentry_sdk


class SentryMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for Sentry integration.

    Features:
    - Set user context from authentication
    - Add request context (method, path, headers)
    - Track request duration
    - Tag slow requests
    """

    def __init__(
        self,
        app: ASGIApp,
        slow_request_threshold_ms: float = 1000.0
    ):
        super().__init__(app)
        self.slow_request_threshold_ms = slow_request_threshold_ms

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        # Start timing
        start_time = time.time()

        # Set request context
        with sentry_sdk.push_scope() as scope:
            # Add request details
            scope.set_tag('http.method', request.method)
            scope.set_tag('http.url', str(request.url.path))

            # Set user context if authenticated
            if hasattr(request.state, 'user'):
                user = request.state.user
                sentry_sdk.set_user({
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                })

            # Add request data as context
            scope.set_context('request', {
                'method': request.method,
                'url': str(request.url),
                'path': request.url.path,
                'query_params': dict(request.query_params),
                'headers': {
                    key: value
                    for key, value in request.headers.items()
                    if key.lower() not in ['authorization', 'cookie']
                },
            })

            # Process request
            try:
                response = await call_next(request)

                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000

                # Add response context
                scope.set_context('response', {
                    'status_code': response.status_code,
                    'duration_ms': duration_ms,
                })

                # Tag slow requests
                if duration_ms > self.slow_request_threshold_ms:
                    scope.set_tag('slow_request', 'true')
                    sentry_sdk.add_breadcrumb(
                        message='Slow request detected',
                        category='performance',
                        level='warning',
                        data={
                            'duration_ms': duration_ms,
                            'threshold_ms': self.slow_request_threshold_ms,
                            'path': request.url.path,
                        }
                    )

                # Tag errors
                if response.status_code >= 500:
                    scope.set_tag('error', 'true')
                    scope.set_level('error')
                elif response.status_code >= 400:
                    scope.set_tag('client_error', 'true')
                    scope.set_level('warning')

                return response

            except Exception as exc:
                # Capture exception with request context
                sentry_sdk.capture_exception(exc)
                raise


class SentryContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add application-specific context to Sentry events.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        with sentry_sdk.push_scope() as scope:
            # Add Ablage-System specific context

            # Document context (if processing a document)
            if document_id := request.path_params.get('document_id'):
                scope.set_context('document', {
                    'id': document_id,
                })

            # OCR context (if OCR endpoint)
            if '/ocr/' in request.url.path:
                scope.set_tag('feature', 'ocr')
                scope.set_context('ocr', {
                    'backend': request.query_params.get('backend', 'auto'),
                    'language': request.query_params.get('language', 'de'),
                })

            # GPU context
            if '/gpu/' in request.url.path:
                scope.set_tag('feature', 'gpu')

            # Execute request
            return await call_next(request)

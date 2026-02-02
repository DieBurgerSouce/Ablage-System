# -*- coding: utf-8 -*-
"""
i18n Middleware for FastAPI

Automatically detects language from Accept-Language header
and sets it for the request context.

Usage:
    from app.core.i18n import I18nMiddleware

    app = FastAPI()
    app.add_middleware(I18nMiddleware)
"""

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog

from .i18n import detect_language_from_header, set_language, get_language

logger = structlog.get_logger(__name__)


class I18nMiddleware(BaseHTTPMiddleware):
    """
    Middleware that detects language from Accept-Language header.

    Sets the language for the request context, allowing all subsequent
    code to use t() for translations in the correct language.

    Priority:
    1. X-Language header (explicit override)
    2. Accept-Language header
    3. Default language (German)
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        # Check for explicit language override
        explicit_lang = request.headers.get("X-Language")

        if explicit_lang:
            set_language(explicit_lang)
        else:
            # Parse Accept-Language header
            accept_language = request.headers.get("Accept-Language")
            detected_lang = detect_language_from_header(accept_language)
            set_language(detected_lang)

        # Process request
        response = await call_next(request)

        # Add Content-Language header to response
        response.headers["Content-Language"] = get_language()

        return response


def get_language_from_request(request: Request) -> str:
    """
    Get language for a specific request.

    Useful when you need to determine language outside middleware context.

    Args:
        request: FastAPI Request object

    Returns:
        Language code
    """
    explicit_lang = request.headers.get("X-Language")
    if explicit_lang:
        return explicit_lang

    accept_language = request.headers.get("Accept-Language")
    return detect_language_from_header(accept_language)

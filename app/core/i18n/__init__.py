# -*- coding: utf-8 -*-
"""
Internationalization (i18n) Module for Ablage-System

Provides multi-language support for backend messages:
- German (de) as primary/source language
- English (en) as secondary language
- Accept-Language header detection
- Thread-safe translation context

Usage:
    from app.core.i18n import t, get_language, set_language

    # Get translated message
    message = t("document.uploaded_successfully")

    # With interpolation
    message = t("document.page_count", count=5)

    # Set language for request
    set_language("en")
"""

from .i18n import (
    t,
    tn,
    get_language,
    set_language,
    get_available_languages,
    detect_language_from_header,
    TranslationContext,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
    FALLBACK_LANGUAGE,
)

from .middleware import I18nMiddleware

__all__ = [
    "t",
    "tn",
    "get_language",
    "set_language",
    "get_available_languages",
    "detect_language_from_header",
    "TranslationContext",
    "I18nMiddleware",
    "SUPPORTED_LANGUAGES",
    "DEFAULT_LANGUAGE",
    "FALLBACK_LANGUAGE",
]

"""
Middleware package for Ablage-System OCR API.

Available middleware:
- RateLimitMiddleware: Rate limiting with user tiers and German error messages
- DevelopmentRateLimitBypass: Bypass rate limiting in development mode
- SecurityHeadersMiddleware: HTTP security headers (CSP, HSTS, X-Frame-Options, etc.)
- PrometheusMiddleware: HTTP metrics collection for Prometheus
- CSRFMiddleware: CSRF protection with Double-Submit-Cookie pattern
"""

from app.middleware.rate_limit import (
    RateLimitMiddleware,
    DevelopmentRateLimitBypass,
    RoleBasedRateLimitChecker,
    get_rate_limit_stats
)

from app.middleware.security_headers import (
    SecurityHeadersMiddleware,
    create_security_headers_middleware
)

from app.middleware.prometheus_middleware import (
    PrometheusMiddleware,
    create_prometheus_middleware,
    http_requests_total,
    http_request_duration_seconds,
    http_requests_in_progress,
    http_errors_total,
    http_slow_requests_total
)

from app.middleware.request_size import (
    RequestSizeLimitMiddleware,
    create_request_size_middleware
)

from app.middleware.csrf import (
    CSRFMiddleware,
    create_csrf_middleware,
    get_csrf_token_response,
    CSRF_HEADER_NAME,
    CSRF_COOKIE_NAME,
)

from app.middleware.ip_blocking import (
    IPBlockingMiddleware,
    create_ip_blocking_middleware,
)

from app.middleware.request_logging import (
    RequestLoggingMiddleware,
    PIIFilterConfig,
    filter_pii_from_dict,
    filter_pii_from_text,
    get_request_logging_stats,
)

from app.middleware.company_context import (
    CompanyContextMiddleware,
    get_current_company,
    get_current_company_id,
    get_user_current_company,
    require_company,
    require_cash_permission,
    require_expense_approval_permission,
    set_company_context,
    switch_company,
)

__all__ = [
    "RateLimitMiddleware",
    "DevelopmentRateLimitBypass",
    "RoleBasedRateLimitChecker",
    "get_rate_limit_stats",
    "SecurityHeadersMiddleware",
    "create_security_headers_middleware",
    "PrometheusMiddleware",
    "create_prometheus_middleware",
    "http_requests_total",
    "http_request_duration_seconds",
    "http_requests_in_progress",
    "http_errors_total",
    "http_slow_requests_total",
    "RequestSizeLimitMiddleware",
    "create_request_size_middleware",
    "CSRFMiddleware",
    "create_csrf_middleware",
    "get_csrf_token_response",
    "CSRF_HEADER_NAME",
    "CSRF_COOKIE_NAME",
    "IPBlockingMiddleware",
    "create_ip_blocking_middleware",
    "RequestLoggingMiddleware",
    "PIIFilterConfig",
    "filter_pii_from_dict",
    "filter_pii_from_text",
    "get_request_logging_stats",
    # Company Context (Multi-Mandanten)
    "CompanyContextMiddleware",
    "get_current_company",
    "get_current_company_id",
    "get_user_current_company",
    "require_company",
    "require_cash_permission",
    "require_expense_approval_permission",
    "set_company_context",
    "switch_company",
]

"""
Middleware package for Ablage-System OCR API.

Available middleware:
- RateLimitMiddleware: Rate limiting with user tiers and German error messages
- DevelopmentRateLimitBypass: Bypass rate limiting in development mode
- SecurityHeadersMiddleware: HTTP security headers (CSP, HSTS, X-Frame-Options, etc.)
- PrometheusMiddleware: HTTP metrics collection for Prometheus
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
]

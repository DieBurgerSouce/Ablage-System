"""
Security Headers Middleware für Ablage-System OCR.

Fügt wichtige HTTP-Sicherheitsheader zu allen Responses hinzu.

Sicherheitsfeatures:
- X-Content-Type-Options: Verhindert MIME-Sniffing
- X-Frame-Options: Verhindert Clickjacking
- X-XSS-Protection: Legacy XSS-Schutz
- Strict-Transport-Security: HTTPS-Enforcement
- Content-Security-Policy: Script/Resource-Kontrolle
- Referrer-Policy: Referrer-Informationskontrolle
- Permissions-Policy: Feature-Kontrolle

Feinpoliert und durchdacht - Enterprise-grade Sicherheit.
"""

from typing import Optional, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog
import uuid

from app.core.config import settings

logger = structlog.get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware für HTTP Security Headers.

    Fügt Sicherheitsheader zu allen HTTP-Responses hinzu.
    Konfigurierbar über Settings.
    """

    def __init__(
        self,
        app,
        enable_hsts: bool = True,
        hsts_max_age: int = 31536000,  # 1 Jahr
        enable_csp: bool = True,
        csp_report_only: bool = False,
        frame_options: str = "DENY",
        content_type_options: str = "nosniff",
        referrer_policy: str = "strict-origin-when-cross-origin",
    ):
        """
        Initialisiere Security Headers Middleware.

        Args:
            app: ASGI Application
            enable_hsts: HSTS Header aktivieren (nur für Production mit HTTPS!)
            hsts_max_age: HSTS Max-Age in Sekunden
            enable_csp: Content-Security-Policy aktivieren
            csp_report_only: CSP nur im Report-Modus (nicht enforced)
            frame_options: X-Frame-Options Wert (DENY, SAMEORIGIN)
            content_type_options: X-Content-Type-Options Wert
            referrer_policy: Referrer-Policy Wert
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts and not settings.DEBUG
        self.hsts_max_age = hsts_max_age
        self.enable_csp = enable_csp
        self.csp_report_only = csp_report_only
        self.frame_options = frame_options
        self.content_type_options = content_type_options
        self.referrer_policy = referrer_policy

        logger.info(
            "security_headers_middleware_initialized",
            hsts_enabled=self.enable_hsts,
            csp_enabled=self.enable_csp,
            frame_options=self.frame_options,
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Verarbeite Request und füge Security Headers hinzu.

        Args:
            request: Eingehender Request
            call_next: Nächste Middleware/Handler

        Returns:
            Response mit Security Headers
        """
        # Generiere Request-ID für Tracking
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Füge Request-ID zum Request State hinzu
        request.state.request_id = request_id

        # Rufe nächsten Handler auf
        response: Response = await call_next(request)

        # Füge Security Headers hinzu
        self._add_security_headers(response, request_id)

        return response

    def _add_security_headers(self, response: Response, request_id: str) -> None:
        """
        Füge alle Security Headers zur Response hinzu.

        Args:
            response: HTTP Response
            request_id: Request ID für Tracking
        """
        # Request ID für Tracking
        response.headers["X-Request-ID"] = request_id

        # Verhindert MIME-Type Sniffing
        response.headers["X-Content-Type-Options"] = self.content_type_options

        # Clickjacking-Schutz
        response.headers["X-Frame-Options"] = self.frame_options

        # Legacy XSS-Schutz (für ältere Browser)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy
        response.headers["Referrer-Policy"] = self.referrer_policy

        # DNS Prefetch Control
        response.headers["X-DNS-Prefetch-Control"] = "off"

        # Download Options für IE
        response.headers["X-Download-Options"] = "noopen"

        # Permitted Cross-Domain Policies
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # HSTS (nur in Production mit HTTPS!)
        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={self.hsts_max_age}; includeSubDomains; preload"
            )

        # Content-Security-Policy
        if self.enable_csp:
            csp_header = "Content-Security-Policy-Report-Only" if self.csp_report_only else "Content-Security-Policy"
            response.headers[csp_header] = self._build_csp()

        # Permissions-Policy (Feature-Policy replacement)
        response.headers["Permissions-Policy"] = self._build_permissions_policy()

        # Cross-Origin Policies
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

    def _build_csp(self) -> str:
        """
        Baue Content-Security-Policy Header.

        Returns:
            CSP Header String
        """
        # Basis-CSP für API-Backend
        directives = [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",  # Für Swagger UI
            "img-src 'self' data: blob:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
            "upgrade-insecure-requests",
        ]

        # Für Development: Erlaube localhost
        if settings.DEBUG:
            directives = [
                d.replace("'self'", "'self' http://localhost:* ws://localhost:*")
                for d in directives
            ]

        return "; ".join(directives)

    def _build_permissions_policy(self) -> str:
        """
        Baue Permissions-Policy Header.

        Deaktiviert nicht benötigte Browser-Features.

        Returns:
            Permissions-Policy Header String
        """
        # Deaktiviere Features die nicht benötigt werden
        policies = [
            "accelerometer=()",
            "autoplay=()",
            "camera=()",
            "cross-origin-isolated=()",
            "display-capture=()",
            "encrypted-media=()",
            "fullscreen=()",
            "geolocation=()",
            "gyroscope=()",
            "keyboard-map=()",
            "magnetometer=()",
            "microphone=()",
            "midi=()",
            "payment=()",
            "picture-in-picture=()",
            "publickey-credentials-get=()",
            "screen-wake-lock=()",
            "sync-xhr=()",
            "usb=()",
            "web-share=()",
            "xr-spatial-tracking=()",
        ]

        return ", ".join(policies)


def create_security_headers_middleware(
    enable_hsts: bool = True,
    enable_csp: bool = True,
) -> type:
    """
    Factory für Security Headers Middleware mit Konfiguration.

    Args:
        enable_hsts: HSTS aktivieren
        enable_csp: CSP aktivieren

    Returns:
        Konfigurierte Middleware-Klasse
    """
    class ConfiguredSecurityHeadersMiddleware(SecurityHeadersMiddleware):
        def __init__(self, app):
            super().__init__(
                app,
                enable_hsts=enable_hsts,
                enable_csp=enable_csp,
            )

    return ConfiguredSecurityHeadersMiddleware

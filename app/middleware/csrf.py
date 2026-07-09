"""
CSRF-Schutz Middleware für Ablage-System OCR.

Implementiert Double-Submit-Cookie-Pattern für CSRF-Schutz.

Sicherheitsfeatures:
- CSRF-Token-Generierung mit kryptographisch sicheren Zufallswerten
- Token-Validierung für state-changing Requests (POST, PUT, DELETE, PATCH)
- Token-Rotation nach erfolgreichen state-changing Requests (verhindert Token-Reuse)
- Neues Token wird im 'X-New-CSRF-Token' Response-Header für JS-Clients bereitgestellt
- Sichere Cookie-Konfiguration (HttpOnly, SameSite, Secure)
- Graceful Degradation für API-Clients mit Bearer-Token-Authentifizierung

Token-Rotation:
Nach jedem erfolgreichen POST/PUT/DELETE/PATCH wird automatisch ein neues Token
generiert. JavaScript-Clients sollten den 'X-New-CSRF-Token' Header auslesen und
für nachfolgende Requests verwenden.

Feinpoliert und durchdacht - Enterprise-grade Sicherheit.
"""

import secrets
from typing import Callable, Optional, Set
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import status
import structlog

from app.core.config import settings
from app.core.german_messages import HTTPErrors

logger = structlog.get_logger(__name__)

# CSRF Token Konfiguration
CSRF_TOKEN_LENGTH = 32  # 256 bits
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"

# Methoden die CSRF-Schutz benötigen
CSRF_PROTECTED_METHODS: Set[str] = {"POST", "PUT", "DELETE", "PATCH"}

# Pfade die vom CSRF-Schutz ausgenommen sind (z.B. Login, da noch kein Token existiert)
CSRF_EXEMPT_PATHS: Set[str] = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/health",
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/metrics",  # Prometheus scraping
}

# Pfad-Präfixe die ausgenommen sind
CSRF_EXEMPT_PREFIXES: tuple = (
    "/api/v1/webhooks/",  # Webhook-Callbacks von externen Services
)


class CSRFError(Exception):
    """CSRF-Validierungsfehler."""
    pass


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Middleware für CSRF-Schutz mit Double-Submit-Cookie-Pattern.

    Das Pattern funktioniert so:
    1. Server generiert CSRF-Token und setzt es als Cookie
    2. Client liest Token aus Cookie und sendet es im Header
    3. Server vergleicht Cookie-Wert mit Header-Wert

    Dies funktioniert, weil:
    - Ein Angreifer kann keine Cookies von einer anderen Domain lesen (Same-Origin-Policy)
    - Der Angreifer kann also das Token nicht im Header senden
    """

    def __init__(
        self,
        app,
        enabled: bool = True,
        cookie_secure: bool = True,
        cookie_samesite: str = "strict",
        cookie_httponly: bool = False,  # False damit JS das Token lesen kann
        cookie_max_age: int = 86400,  # 24 Stunden
        exempt_paths: Optional[Set[str]] = None,
        exempt_prefixes: Optional[tuple] = None,
        bearer_token_bypass: bool = True,  # API-Clients mit Bearer Token überspringen
    ):
        """
        Initialisiere CSRF Middleware.

        Args:
            app: ASGI Application
            enabled: CSRF-Schutz aktivieren
            cookie_secure: Cookie nur über HTTPS senden
            cookie_samesite: SameSite-Attribut (strict, lax, none)
            cookie_httponly: HttpOnly-Attribut (False damit JS Token lesen kann)
            cookie_max_age: Cookie-Lebensdauer in Sekunden
            exempt_paths: Zusätzliche Pfade die ausgenommen werden
            exempt_prefixes: Zusätzliche Pfad-Präfixe die ausgenommen werden
            bearer_token_bypass: Bei Authorization: Bearer Header CSRF überspringen
        """
        super().__init__(app)
        self.enabled = enabled
        self.cookie_secure = cookie_secure and not settings.DEBUG
        self.cookie_samesite = cookie_samesite
        self.cookie_httponly = cookie_httponly
        self.cookie_max_age = cookie_max_age
        self.bearer_token_bypass = bearer_token_bypass

        # Kombiniere Standard- und benutzerdefinierte Ausnahmen
        self.exempt_paths = CSRF_EXEMPT_PATHS.copy()
        if exempt_paths:
            self.exempt_paths.update(exempt_paths)

        self.exempt_prefixes = CSRF_EXEMPT_PREFIXES
        if exempt_prefixes:
            self.exempt_prefixes = CSRF_EXEMPT_PREFIXES + exempt_prefixes

        # W1-Harness: Der Test-Harness-Router (/api/v1/test/) ist NUR im
        # TESTING-Betrieb gemountet (app/main.py, doppelt gegated im Handler).
        # Cookie-lose E2E-/Agent-Aufrufe (curl POST /test/reset-state) duerfen
        # dann nicht am CSRF-Double-Submit scheitern. In Produktion existiert
        # weder Mount noch Ausnahme.
        if settings.TESTING and not settings.is_production:
            self.exempt_prefixes = self.exempt_prefixes + ("/api/v1/test/",)

        logger.info(
            "csrf_middleware_initialized",
            enabled=self.enabled,
            cookie_secure=self.cookie_secure,
            cookie_samesite=self.cookie_samesite,
            bearer_bypass=self.bearer_token_bypass,
            exempt_paths_count=len(self.exempt_paths),
        )

    def _generate_csrf_token(self) -> str:
        """
        Generiere kryptographisch sicheres CSRF-Token.

        Returns:
            Hexadezimales Token mit CSRF_TOKEN_LENGTH Bytes
        """
        return secrets.token_hex(CSRF_TOKEN_LENGTH)

    def _is_exempt(self, request: Request) -> bool:
        """
        Prüfe ob der Request vom CSRF-Schutz ausgenommen ist.

        Args:
            request: Eingehender Request

        Returns:
            True wenn ausgenommen
        """
        path = request.url.path

        # Exakte Pfad-Übereinstimmung
        if path in self.exempt_paths:
            return True

        # Pfad-Präfix-Übereinstimmung
        if path.startswith(self.exempt_prefixes):
            return True

        return False

    def _has_bearer_token(self, request: Request) -> bool:
        """
        Prüfe ob Request einen Bearer Token hat.

        Bei API-Clients die Authorization: Bearer verwenden
        ist CSRF-Schutz nicht notwendig, da der Angreifer
        den Authorization-Header nicht von einer anderen Domain setzen kann.

        Args:
            request: Eingehender Request

        Returns:
            True wenn Bearer Token vorhanden
        """
        auth_header = request.headers.get("Authorization", "")
        return auth_header.lower().startswith("bearer ")

    def _get_csrf_from_cookie(self, request: Request) -> Optional[str]:
        """
        Hole CSRF-Token aus Cookie.

        Args:
            request: Eingehender Request

        Returns:
            Token oder None
        """
        return request.cookies.get(CSRF_COOKIE_NAME)

    def _get_csrf_from_header(self, request: Request) -> Optional[str]:
        """
        Hole CSRF-Token aus Header.

        Args:
            request: Eingehender Request

        Returns:
            Token oder None
        """
        return request.headers.get(CSRF_HEADER_NAME)

    async def _get_csrf_from_form(self, request: Request) -> Optional[str]:
        """
        Hole CSRF-Token aus Form-Daten.

        Für traditionelle HTML-Formulare ohne JavaScript.

        Args:
            request: Eingehender Request

        Returns:
            Token oder None
        """
        content_type = request.headers.get("content-type", "")

        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                form = await request.form()
                return form.get(CSRF_FORM_FIELD)
            except Exception as e:
                logger.debug(
                    "csrf_form_parsing_failed",
                    error_type=type(e).__name__,
                )

        return None

    def _validate_csrf_token(self, cookie_token: Optional[str], submitted_token: Optional[str]) -> bool:
        """
        Validiere CSRF-Token mit konstantem Zeitvergleich.

        Verwendet secrets.compare_digest um Timing-Angriffe zu verhindern.

        Args:
            cookie_token: Token aus Cookie
            submitted_token: Token aus Header/Form

        Returns:
            True wenn Token übereinstimmen
        """
        if not cookie_token or not submitted_token:
            return False

        # Konstanter Zeitvergleich verhindert Timing-Angriffe
        return secrets.compare_digest(cookie_token, submitted_token)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Verarbeite Request mit CSRF-Validierung.

        Args:
            request: Eingehender Request
            call_next: Nächste Middleware/Handler

        Returns:
            Response (mit CSRF-Cookie bei Bedarf)
        """
        # Wenn CSRF deaktiviert, direkt weiterleiten
        if not self.enabled:
            return await call_next(request)

        method = request.method.upper()

        # Für GET/HEAD/OPTIONS: Token generieren wenn nicht vorhanden
        if method not in CSRF_PROTECTED_METHODS:
            response = await call_next(request)

            # Setze CSRF-Cookie wenn noch nicht vorhanden
            if not self._get_csrf_from_cookie(request):
                csrf_token = self._generate_csrf_token()
                response.set_cookie(
                    key=CSRF_COOKIE_NAME,
                    value=csrf_token,
                    max_age=self.cookie_max_age,
                    httponly=self.cookie_httponly,
                    secure=self.cookie_secure,
                    samesite=self.cookie_samesite,
                    path="/",
                )
                logger.debug("csrf_token_generated", path=request.url.path)

            return response

        # Für state-changing Methoden: Validierung erforderlich

        # Prüfe Ausnahmen
        if self._is_exempt(request):
            logger.debug("csrf_exempt_path", path=request.url.path)
            return await call_next(request)

        # Prüfe Bearer Token Bypass
        if self.bearer_token_bypass and self._has_bearer_token(request):
            logger.debug("csrf_bearer_bypass", path=request.url.path)
            return await call_next(request)

        # CSRF-Validierung
        cookie_token = self._get_csrf_from_cookie(request)
        header_token = self._get_csrf_from_header(request)

        # Fallback auf Form-Token wenn kein Header-Token
        submitted_token = header_token
        if not submitted_token:
            submitted_token = await self._get_csrf_from_form(request)

        if not self._validate_csrf_token(cookie_token, submitted_token):
            logger.warning(
                "csrf_validation_failed",
                path=request.url.path,
                method=method,
                has_cookie=cookie_token is not None,
                has_header=header_token is not None,
                client_ip=request.client.host if request.client else "unknown",
            )

            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "fehler": "CSRF-Validierung fehlgeschlagen",
                    "nachricht": "CSRF-Validierung fehlgeschlagen. Bitte laden Sie die Seite neu.",
                    "status_code": 403,
                    "fehler_code": "CSRF_VALIDATION_FAILED",
                    "hinweis": f"Senden Sie das CSRF-Token im '{CSRF_HEADER_NAME}' Header",
                }
            )

        logger.debug("csrf_validation_passed", path=request.url.path)

        # Request verarbeiten
        response = await call_next(request)

        # Token-Rotation nach erfolgreichem state-changing Request
        # Verhindert Token-Reuse-Angriffe.
        # WICHTIG: NUR bei echten 2xx-Erfolgen rotieren, NICHT bei 3xx-Redirects.
        # Ein Trailing-Slash-Redirect (FastAPI 307 /documents -> /documents/) wird
        # vom Browser mit demselben (alten) X-CSRF-Token-Header WIEDERHOLT. Wuerde
        # der 307 den Cookie rotieren, traefe der Folge-Request den neuen Cookie
        # gegen den alten Header -> 403 (genau der Upload-Bug). 2xx-Grenze schuetzt
        # den Redirect-Follow, ohne den Reuse-Schutz fuer echte Erfolge aufzugeben.
        if 200 <= response.status_code < 300:
            new_csrf_token = self._generate_csrf_token()
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=new_csrf_token,
                max_age=self.cookie_max_age,
                httponly=self.cookie_httponly,
                secure=self.cookie_secure,
                samesite=self.cookie_samesite,
                path="/",
            )
            # Neues Token auch im Response-Header für JavaScript-Clients
            response.headers["X-New-CSRF-Token"] = new_csrf_token
            logger.debug(
                "csrf_token_rotated",
                path=request.url.path,
                method=method,
            )

        return response


def create_csrf_middleware(
    enabled: bool = True,
    bearer_bypass: bool = True,
    **kwargs
) -> CSRFMiddleware:
    """
    Factory-Funktion für CSRF Middleware.

    Args:
        enabled: CSRF-Schutz aktivieren
        bearer_bypass: Bei Bearer Token überspringen
        **kwargs: Weitere Parameter für CSRFMiddleware

    Returns:
        Konfigurierte CSRFMiddleware-Klasse
    """
    def middleware(app):
        return CSRFMiddleware(
            app,
            enabled=enabled,
            bearer_token_bypass=bearer_bypass,
            **kwargs
        )
    return middleware


# CSRF Token Endpoint Helper
def get_csrf_token_response() -> dict:
    """
    Generiere Response für CSRF-Token-Endpoint.

    Dieser Endpoint kann verwendet werden, wenn der Client
    das Token aus dem Cookie nicht lesen kann (z.B. bei HttpOnly).

    Returns:
        Dict mit neuem CSRF-Token
    """
    return {
        "csrf_token": secrets.token_hex(CSRF_TOKEN_LENGTH),
        "header_name": CSRF_HEADER_NAME,
        "cookie_name": CSRF_COOKIE_NAME,
    }

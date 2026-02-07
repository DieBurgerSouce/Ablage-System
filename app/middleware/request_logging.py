# -*- coding: utf-8 -*-
"""
Request/Response Logging Middleware mit PII-Filter.

Protokolliert alle API-Requests und -Responses fuer:
- Debugging und Troubleshooting
- Security Auditing
- Performance Monitoring
- Compliance (DSGVO-konform durch PII-Filterung)

Feinpoliert und durchdacht - Enterprise-grade Logging.
"""

import json
import re
import time
from typing import Callable, Dict, List, Optional, Set
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class PIIFilterConfig:
    """Konfiguration fuer PII-Filterung."""

    # Felder die komplett ausgeblendet werden (nur "[REDACTED]")
    REDACTED_FIELDS: Set[str] = {
        "password",
        "passwort",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "credential",
        "private_key",
        "privatekey",
        "totp_secret",
        "otp",
        "pin",
    }

    # Felder die maskiert werden (letzte 4 Zeichen sichtbar)
    MASKED_FIELDS: Set[str] = {
        "email",
        "e-mail",
        "phone",
        "telefon",
        "mobile",
        "handy",
        "iban",
        "credit_card",
        "kreditkarte",
        "ssn",
        "sozialversicherung",
    }

    # Felder die gekuerzt werden (nur erste 3 Zeichen)
    TRUNCATED_FIELDS: Set[str] = {
        "name",
        "vorname",
        "nachname",
        "firstname",
        "lastname",
        "username",
        "benutzername",
        "address",
        "adresse",
        "strasse",
        "street",
    }

    # Regex-Patterns fuer sensitive Daten im Text
    SENSITIVE_PATTERNS: List[tuple] = [
        # Email
        (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL-REDACTED]'),
        # IBAN (DE)
        (r'DE\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}', '[IBAN-REDACTED]'),
        # Telefon (DE)
        (r'(\+49|0049|0)\s?[\d\s\-/]{8,15}', '[PHONE-REDACTED]'),
        # Kreditkarte (16 Ziffern)
        (r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b', '[CARD-REDACTED]'),
        # JWT Token
        (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*', '[JWT-REDACTED]'),
        # UUID (User IDs bleiben sichtbar fuer Debugging)
        # (r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '[UUID]'),
    ]

    # Maximale Laenge fuer geloggte Body-Inhalte
    MAX_BODY_LOG_LENGTH: int = 2000

    # Pfade die nicht geloggt werden sollen
    EXCLUDED_PATHS: Set[str] = {
        "/health",
        "/metrics",
        "/favicon.ico",
        "/docs",
        "/redoc",
        "/openapi.json",
    }


def redact_value(value: object) -> str:
    """Entfernt sensitiven Wert komplett."""
    return "[REDACTED]"


def mask_value(value: object) -> str:
    """Maskiert Wert, zeigt nur letzte 4 Zeichen."""
    if not isinstance(value, str):
        value = str(value)
    if len(value) <= 4:
        return "[MASKED]"
    return f"***{value[-4:]}"


def truncate_value(value: object) -> str:
    """Kuerzt Wert auf erste 3 Zeichen."""
    if not isinstance(value, str):
        value = str(value)
    if len(value) <= 3:
        return f"{value}***"
    return f"{value[:3]}***"


def filter_pii_from_dict(data: Dict[str, object], depth: int = 0) -> Dict[str, object]:
    """
    Filtert PII aus einem Dictionary.

    Args:
        data: Dictionary mit potentiell sensitiven Daten
        depth: Aktuelle Verschachtelungstiefe (max 5)

    Returns:
        Gefiltertes Dictionary
    """
    if depth > 5:
        return {"_truncated": "max_depth_reached"}

    filtered = {}
    for key, value in data.items():
        key_lower = key.lower()

        # Komplett redacted
        if any(f in key_lower for f in PIIFilterConfig.REDACTED_FIELDS):
            filtered[key] = redact_value(value)
        # Maskiert
        elif any(f in key_lower for f in PIIFilterConfig.MASKED_FIELDS):
            filtered[key] = mask_value(value)
        # Gekuerzt
        elif any(f in key_lower for f in PIIFilterConfig.TRUNCATED_FIELDS):
            filtered[key] = truncate_value(value)
        # Nested dict
        elif isinstance(value, dict):
            filtered[key] = filter_pii_from_dict(value, depth + 1)
        # Liste
        elif isinstance(value, list):
            filtered[key] = [
                filter_pii_from_dict(item, depth + 1) if isinstance(item, dict) else item
                for item in value[:10]  # Max 10 Items loggen
            ]
            if len(value) > 10:
                filtered[key].append(f"... und {len(value) - 10} weitere")
        else:
            filtered[key] = value

    return filtered


def filter_pii_from_text(text: str) -> str:
    """
    Filtert PII aus Freitext.

    Args:
        text: Text mit potentiell sensitiven Daten

    Returns:
        Gefilterter Text
    """
    result = text
    for pattern, replacement in PIIFilterConfig.SENSITIVE_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def truncate_body(body: str, max_length: int = None) -> str:
    """Kuerzt Body auf maximale Laenge."""
    max_len = max_length or PIIFilterConfig.MAX_BODY_LOG_LENGTH
    if len(body) <= max_len:
        return body
    return f"{body[:max_len]}... [truncated, total {len(body)} bytes]"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware fuer umfassendes Request/Response Logging.

    Features:
    - Automatische PII-Filterung
    - Performance-Metriken (Dauer, Body-Groesse)
    - Request-ID-Tracking
    - Konfigurierbare Ausschluss-Pfade
    """

    def __init__(
        self,
        app,
        log_request_body: bool = True,
        log_response_body: bool = False,
        log_headers: bool = True,
        excluded_paths: Optional[Set[str]] = None,
    ):
        """
        Initialisiere Logging Middleware.

        Args:
            app: ASGI Application
            log_request_body: Request-Body loggen (PII-gefiltert)
            log_response_body: Response-Body loggen (PII-gefiltert)
            log_headers: Request-Header loggen (PII-gefiltert)
            excluded_paths: Pfade die nicht geloggt werden
        """
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.log_headers = log_headers
        self.excluded_paths = excluded_paths or PIIFilterConfig.EXCLUDED_PATHS

        logger.info(
            "request_logging_middleware_initialized",
            log_request_body=log_request_body,
            log_response_body=log_response_body,
            log_headers=log_headers,
            excluded_paths=len(self.excluded_paths),
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Verarbeite Request und logge Details.

        Args:
            request: Eingehender Request
            call_next: Naechste Middleware/Handler

        Returns:
            Response
        """
        # Pfad pruefen
        path = request.url.path
        if any(path.startswith(excluded) for excluded in self.excluded_paths):
            return await call_next(request)

        # Request-ID
        request_id = getattr(request.state, "request_id", None) or str(uuid4())

        # Start-Zeit
        start_time = time.perf_counter()

        # Request-Details sammeln
        request_log = await self._collect_request_info(request, request_id)

        # Log Request (vor Verarbeitung)
        logger.info(
            "http_request_received",
            **request_log
        )

        # Request verarbeiten
        try:
            response = await call_next(request)

            # Response-Details
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            response_log = self._collect_response_info(response, request_id, duration_ms)

            # Log-Level basierend auf Status-Code
            if response.status_code >= 500:
                logger.error("http_request_completed", **response_log, **request_log)
            elif response.status_code >= 400:
                logger.warning("http_request_completed", **response_log, **request_log)
            else:
                logger.info("http_request_completed", **response_log)

            return response

        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "http_request_failed",
                request_id=request_id,
                error_type=type(e).__name__,
                **safe_error_log(e),
                duration_ms=duration_ms,
                **request_log
            )
            raise

    async def _collect_request_info(
        self,
        request: Request,
        request_id: str
    ) -> Dict[str, object]:
        """Sammelt und filtert Request-Informationen."""
        info = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query_string": filter_pii_from_text(str(request.query_params)),
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent", "")[:100],
        }

        # Headers (gefiltert)
        if self.log_headers:
            headers = dict(request.headers)
            filtered_headers = filter_pii_from_dict(headers)
            # Nur relevante Headers
            relevant_headers = {
                k: v for k, v in filtered_headers.items()
                if k.lower() in {
                    "content-type", "content-length", "accept",
                    "x-request-id", "x-forwarded-for", "x-priority"
                }
            }
            info["headers"] = relevant_headers

        # Body (nur bei POST/PUT/PATCH und wenn aktiviert)
        if self.log_request_body and request.method in {"POST", "PUT", "PATCH"}:
            try:
                body = await request.body()
                if body:
                    content_type = request.headers.get("content-type", "")
                    if "application/json" in content_type:
                        try:
                            body_dict = json.loads(body)
                            filtered_body = filter_pii_from_dict(body_dict)
                            info["body"] = truncate_body(json.dumps(filtered_body))
                        except json.JSONDecodeError:
                            info["body"] = truncate_body(filter_pii_from_text(body.decode("utf-8", errors="replace")))
                    elif "multipart/form-data" in content_type:
                        info["body"] = "[MULTIPART-FORM-DATA, files not logged]"
                    else:
                        info["body"] = f"[{len(body)} bytes, type: {content_type}]"
            except Exception as e:
                info["body_error"] = safe_error_detail(e, "Body-Parsing")

        return info

    def _collect_response_info(
        self,
        response: Response,
        request_id: str,
        duration_ms: int
    ) -> Dict[str, object]:
        """Sammelt Response-Informationen."""
        return {
            "request_id": request_id,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "content_length": response.headers.get("content-length", "unknown"),
            "content_type": response.headers.get("content-type", "unknown"),
        }

    def _get_client_ip(self, request: Request) -> str:
        """Ermittelt Client-IP (inklusive Proxy-Support)."""
        # X-Forwarded-For Header (bei Proxy/Load Balancer)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Erste IP in der Liste ist der Client
            return forwarded.split(",")[0].strip()

        # X-Real-IP Header (Nginx)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Direkte Client-IP
        if request.client:
            return request.client.host

        return "unknown"


def get_request_logging_stats() -> Dict[str, object]:
    """Gibt Statistiken ueber Request Logging zurueck."""
    return {
        "pii_redacted_fields": len(PIIFilterConfig.REDACTED_FIELDS),
        "pii_masked_fields": len(PIIFilterConfig.MASKED_FIELDS),
        "pii_truncated_fields": len(PIIFilterConfig.TRUNCATED_FIELDS),
        "sensitive_patterns": len(PIIFilterConfig.SENSITIVE_PATTERNS),
        "max_body_log_length": PIIFilterConfig.MAX_BODY_LOG_LENGTH,
        "excluded_paths": list(PIIFilterConfig.EXCLUDED_PATHS),
    }

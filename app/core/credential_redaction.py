# -*- coding: utf-8 -*-
"""
Credential Redaction Modul fuer Ablage-System.

Umfassende Redaktion von Credentials in Logs und Outputs:
- API Keys und Tokens
- Passwörter und Secrets
- Connection Strings
- JWT Tokens
- SSH Keys
- Umgebungsvariablen

Art. 32 DSGVO - Sicherheit der Verarbeitung:
Technische Massnahmen zum Schutz sensibler Credentials.

Feinpoliert und durchdacht - Enterprise-grade Security.
"""

import re
import json
from typing import Any, Dict, List, Optional, Pattern, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuration
# ============================================================================


class RedactionLevel(Enum):
    """Redaktion-Stufen."""

    MINIMAL = "minimal"      # Nur bekannte sensitive Feldnamen
    STANDARD = "standard"    # + Pattern-basierte Erkennung
    PARANOID = "paranoid"    # + Alle potentiell sensitiven Daten


@dataclass
class RedactionConfig:
    """Konfiguration fuer Credential-Redaktion."""

    level: RedactionLevel = RedactionLevel.STANDARD
    redaction_text: str = "[REDACTED]"
    redaction_text_de: str = "[ZENSIERT]"
    show_partial: bool = False  # Zeige ersten/letzten Buchstaben
    log_redactions: bool = False  # Logge wenn redaktiert wird


# Default Konfiguration
DEFAULT_CONFIG = RedactionConfig()


# ============================================================================
# Sensitive Field Names
# ============================================================================


# Feldnamen die immer redaktiert werden (case-insensitive)
SENSITIVE_FIELD_NAMES = frozenset({
    # Englisch
    "password", "passwd", "pwd", "pass",
    "secret", "secret_key", "secretkey",
    "api_key", "apikey", "api-key",
    "access_key", "accesskey", "access-key",
    "access_token", "accesstoken", "access-token",
    "refresh_token", "refreshtoken", "refresh-token",
    "auth_token", "authtoken", "auth-token",
    "bearer_token", "bearertoken", "bearer-token",
    "token", "jwt", "session_token",
    "private_key", "privatekey", "private-key",
    "public_key", "publickey", "public-key",
    "ssh_key", "sshkey", "ssh-key",
    "encryption_key", "encryptionkey",
    "signing_key", "signingkey",
    "client_secret", "clientsecret", "client-secret",
    "client_id", "clientid",
    "credential", "credentials", "cred",
    "authorization", "auth",
    "x-api-key", "x-auth-token",
    "cookie", "session", "sid",

    # Deutsch
    "passwort", "kennwort", "geheimnis",
    "schluessel", "zugangsschluessel",
    "authentifizierung", "berechtigung",

    # Datenbank
    "db_password", "database_password",
    "db_pass", "mysql_password", "postgres_password",
    "redis_password", "mongo_password",
    "connection_string", "connectionstring",
    "dsn",

    # Cloud/Services
    "aws_secret", "aws_access_key",
    "azure_key", "azure_secret",
    "gcp_key", "google_key",
    "minio_secret", "minio_access_key",
    "vault_token", "vault_secret",

    # Finanz/PII
    "credit_card", "creditcard", "cc_number",
    "cvv", "cvc", "card_number",
    "iban", "bic", "swift",
    "ssn", "social_security",
    "tax_id", "steuer_id",
    "bank_account", "kontonummer",
})


# Headers die redaktiert werden sollen
SENSITIVE_HEADERS = frozenset({
    "authorization",
    "x-api-key",
    "x-auth-token",
    "x-access-token",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "www-authenticate",
})


# ============================================================================
# Regex Patterns
# ============================================================================


@dataclass
class CredentialPattern:
    """Pattern fuer Credential-Erkennung."""

    name: str
    pattern: Pattern[str]
    description: str
    replacement: Optional[str] = None


# Kompilierte Regex Patterns fuer verschiedene Credential-Typen
CREDENTIAL_PATTERNS: List[CredentialPattern] = [
    # JWT Tokens
    CredentialPattern(
        name="jwt",
        pattern=re.compile(
            r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
            re.IGNORECASE
        ),
        description="JSON Web Token"
    ),

    # API Keys (generisch)
    CredentialPattern(
        name="api_key_generic",
        pattern=re.compile(
            r'(?i)(?:api[_-]?key|apikey)["\s:=]+["\']?([a-zA-Z0-9_-]{20,})["\']?',
            re.IGNORECASE
        ),
        description="Generic API Key"
    ),

    # Bearer Token
    CredentialPattern(
        name="bearer",
        pattern=re.compile(
            r'[Bb]earer\s+[A-Za-z0-9_-]+\.?[A-Za-z0-9_-]*\.?[A-Za-z0-9_-]*',
            re.IGNORECASE
        ),
        description="Bearer Token"
    ),

    # Basic Auth
    CredentialPattern(
        name="basic_auth",
        pattern=re.compile(
            r'[Bb]asic\s+[A-Za-z0-9+/]+=*',
            re.IGNORECASE
        ),
        description="Basic Auth Header"
    ),

    # Connection Strings
    CredentialPattern(
        name="connection_string",
        pattern=re.compile(
            r'(?:postgres(?:ql)?|mysql|mongodb|redis|amqp)(?:\+\w+)?://[^@\s]+:[^@\s]+@[^\s]+',
            re.IGNORECASE
        ),
        description="Database Connection String",
        replacement="[DB_CONNECTION_REDACTED]"
    ),

    # AWS Access Key
    CredentialPattern(
        name="aws_access_key",
        pattern=re.compile(r'AKIA[0-9A-Z]{16}'),
        description="AWS Access Key ID"
    ),

    # AWS Secret Key
    CredentialPattern(
        name="aws_secret",
        pattern=re.compile(r'(?i)aws[_-]?secret[_-]?(?:access)?[_-]?key["\s:=]+["\']?([A-Za-z0-9/+=]{40})["\']?'),
        description="AWS Secret Access Key"
    ),

    # GitHub Token
    CredentialPattern(
        name="github_token",
        pattern=re.compile(r'gh[pousr]_[A-Za-z0-9_]{36,}'),
        description="GitHub Token"
    ),

    # Slack Token
    CredentialPattern(
        name="slack_token",
        pattern=re.compile(r'xox[baprs]-[0-9]+-[0-9A-Za-z]+'),
        description="Slack Token"
    ),

    # Private Key Block
    CredentialPattern(
        name="private_key",
        pattern=re.compile(
            r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]+?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
            re.IGNORECASE
        ),
        description="Private Key",
        replacement="[PRIVATE_KEY_REDACTED]"
    ),

    # Password in URLs
    CredentialPattern(
        name="url_password",
        pattern=re.compile(r'://[^:]+:([^@]+)@'),
        description="Password in URL"
    ),

    # Generic Password Fields
    CredentialPattern(
        name="password_field",
        pattern=re.compile(
            r'(?i)(?:password|passwd|pwd|passwort)["\s:=]+["\']?([^\s"\'}{,\]]+)["\']?'
        ),
        description="Password Field"
    ),

    # Generic Secret Fields
    CredentialPattern(
        name="secret_field",
        pattern=re.compile(
            r'(?i)(?:secret|api_key|token)["\s:=]+["\']?([A-Za-z0-9_-]{16,})["\']?'
        ),
        description="Secret Field"
    ),

    # Email (partial redaction)
    CredentialPattern(
        name="email",
        pattern=re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
        description="Email Address",
        replacement="[EMAIL_REDACTED]"
    ),

    # Credit Card Numbers
    CredentialPattern(
        name="credit_card",
        pattern=re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'),
        description="Credit Card Number"
    ),

    # IBAN
    CredentialPattern(
        name="iban",
        pattern=re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4,}[0-9]{7}([A-Z0-9]?){0,16}\b'),
        description="IBAN"
    ),

    # IPv4 with Port (might contain credentials)
    CredentialPattern(
        name="ip_credentials",
        pattern=re.compile(r'(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3}):([^@\s]+)@'),
        description="IP with Credentials"
    ),
]


# ============================================================================
# Redaction Functions
# ============================================================================


def _partial_redact(value: str, show_chars: int = 4) -> str:
    """Zeige nur ersten und letzten Zeichen."""
    if len(value) <= show_chars * 2:
        return "[REDACTED]"
    return f"{value[:show_chars]}...{value[-show_chars:]}"


def redact_value(
    value: str,
    config: RedactionConfig = DEFAULT_CONFIG,
    context: Optional[str] = None
) -> str:
    """
    Redaktiere einen einzelnen Wert basierend auf Patterns.

    Args:
        value: Zu pruefender Wert
        config: Redaktions-Konfiguration
        context: Optionaler Kontext (z.B. Feldname)

    Returns:
        Redaktierter Wert oder Original
    """
    if not isinstance(value, str):
        return value

    redacted = value

    for cred_pattern in CREDENTIAL_PATTERNS:
        if cred_pattern.pattern.search(redacted):
            replacement = cred_pattern.replacement or config.redaction_text
            redacted = cred_pattern.pattern.sub(replacement, redacted)

            if config.log_redactions:
                logger.debug(
                    "credential_redacted",
                    pattern=cred_pattern.name,
                    context=context
                )

    return redacted


def redact_dict(
    data: Dict[str, Any],
    config: RedactionConfig = DEFAULT_CONFIG,
    path: str = ""
) -> Dict[str, Any]:
    """
    Redaktiere alle sensitiven Felder in einem Dictionary.

    Args:
        data: Dictionary mit potentiell sensitiven Daten
        config: Redaktions-Konfiguration
        path: Aktueller Pfad (fuer verschachtelte Dicts)

    Returns:
        Redaktiertes Dictionary
    """
    result = {}

    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key
        key_lower = key.lower()

        # Prüfe ob Feldname sensitiv ist (nur fuer Nicht-Container-Typen)
        is_sensitive_field = any(
            sensitive in key_lower
            for sensitive in SENSITIVE_FIELD_NAMES
        )

        # Bei Container-Typen (dict, list) rekursiv verarbeiten statt komplett redaktieren
        if isinstance(value, dict):
            # Rekursiv verarbeiten (auch wenn Feldname sensitiv ist)
            result[key] = redact_dict(value, config, current_path)
        elif isinstance(value, list):
            # Liste verarbeiten
            result[key] = [
                redact_dict(item, config, f"{current_path}[{i}]")
                if isinstance(item, dict)
                else redact_value(str(item), config, current_path)
                if isinstance(item, str)
                else item
                for i, item in enumerate(value)
            ]
        elif is_sensitive_field:
            # Feld komplett redaktieren (nur primitive Typen)
            if config.show_partial and isinstance(value, str) and len(value) > 8:
                result[key] = _partial_redact(value)
            else:
                result[key] = config.redaction_text_de
        elif isinstance(value, str):
            # String auf Patterns pruefen
            if config.level in [RedactionLevel.STANDARD, RedactionLevel.PARANOID]:
                result[key] = redact_value(value, config, current_path)
            else:
                result[key] = value
        else:
            result[key] = value

    return result


def redact_headers(
    headers: Dict[str, str],
    config: RedactionConfig = DEFAULT_CONFIG
) -> Dict[str, str]:
    """
    Redaktiere sensitive HTTP Headers.

    Args:
        headers: HTTP Headers Dictionary
        config: Redaktions-Konfiguration

    Returns:
        Redaktierte Headers
    """
    result = {}

    for key, value in headers.items():
        key_lower = key.lower()

        if key_lower in SENSITIVE_HEADERS:
            if config.show_partial and len(value) > 8:
                result[key] = _partial_redact(value)
            else:
                result[key] = config.redaction_text_de
        else:
            result[key] = value

    return result


def redact_url(
    url: str,
    config: RedactionConfig = DEFAULT_CONFIG
) -> str:
    """
    Redaktiere Credentials in URLs.

    Args:
        url: URL String
        config: Redaktions-Konfiguration

    Returns:
        Redaktierte URL
    """
    # Pattern 1: protocol://user:password@host (mit User)
    password_pattern = re.compile(r'(://[^:]+:)([^@]+)(@)')

    def replace_password(match: re.Match) -> str:
        return f"{match.group(1)}{config.redaction_text}{match.group(3)}"

    result = password_pattern.sub(replace_password, url)

    # Pattern 2: protocol://:password@host (ohne User, z.B. Redis)
    empty_user_pattern = re.compile(r'(://:)([^@]+)(@)')

    def replace_empty_user_password(match: re.Match) -> str:
        return f"{match.group(1)}{config.redaction_text}{match.group(3)}"

    result = empty_user_pattern.sub(replace_empty_user_password, result)

    return result


def redact_json_string(
    json_str: str,
    config: RedactionConfig = DEFAULT_CONFIG
) -> str:
    """
    Redaktiere sensitiven Inhalt in JSON String.

    Args:
        json_str: JSON String
        config: Redaktions-Konfiguration

    Returns:
        Redaktierter JSON String
    """
    try:
        data = json.loads(json_str)
        redacted = redact_dict(data, config)
        return json.dumps(redacted, ensure_ascii=False)
    except json.JSONDecodeError:
        # Nicht-JSON, wende Pattern-basierte Redaktion an
        return redact_value(json_str, config)


# ============================================================================
# Structlog Processor
# ============================================================================


class CredentialRedactionProcessor:
    """
    Structlog Processor fuer umfassende Credential-Redaktion.

    Ersetzt den einfachen SensitiveDataFilter mit erweiterter
    Pattern-basierter Erkennung.
    """

    def __init__(self, config: RedactionConfig = DEFAULT_CONFIG):
        self.config = config

    def __call__(
        self,
        logger: Any,
        method_name: str,
        event_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Redaktiere alle sensitiven Daten im Log Event."""
        return redact_dict(event_dict, self.config)


# ============================================================================
# FastAPI Middleware
# ============================================================================


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CredentialRedactionMiddleware(BaseHTTPMiddleware):
    """
    FastAPI Middleware fuer Credential-Redaktion in Request/Response Logs.

    Stellt sicher, dass keine Credentials in Request/Response Logs erscheinen.
    """

    def __init__(self, app: Any, config: RedactionConfig = DEFAULT_CONFIG):
        super().__init__(app)
        self.config = config
        self.logger = structlog.get_logger("credential_redaction")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Verarbeite Request und redaktiere Logs."""

        # Redaktiere Request-Daten fuer Logging
        safe_headers = redact_headers(dict(request.headers), self.config)
        safe_url = redact_url(str(request.url), self.config)

        # Log Request mit redaktierten Daten
        self.logger.debug(
            "http_request",
            method=request.method,
            url=safe_url,
            headers=safe_headers,
            client_ip=request.client.host if request.client else None
        )

        # Verarbeite Request
        response = await call_next(request)

        # Log Response mit redaktierten Daten
        safe_response_headers = redact_headers(
            dict(response.headers),
            self.config
        )

        self.logger.debug(
            "http_response",
            status_code=response.status_code,
            headers=safe_response_headers
        )

        return response


# ============================================================================
# Convenience Functions
# ============================================================================


def get_redaction_processor(
    level: RedactionLevel = RedactionLevel.STANDARD
) -> CredentialRedactionProcessor:
    """Erstelle konfigurierten Redaction Processor."""
    config = RedactionConfig(level=level)
    return CredentialRedactionProcessor(config)


def setup_credential_redaction(app: Any, level: RedactionLevel = RedactionLevel.STANDARD) -> None:
    """
    Richte Credential-Redaktion fuer FastAPI App ein.

    Args:
        app: FastAPI Application
        level: Redaktions-Level
    """
    config = RedactionConfig(level=level)
    app.add_middleware(CredentialRedactionMiddleware, config=config)

    logger.info(
        "credential_redaction_configured",
        level=level.value
    )


def is_sensitive_key(key: str) -> bool:
    """Pruefe ob ein Key als sensitiv gilt."""
    key_lower = key.lower()
    return any(sensitive in key_lower for sensitive in SENSITIVE_FIELD_NAMES)


def redact_for_logging(data: Any) -> Any:
    """
    Convenience Function fuer schnelle Redaktion.

    Args:
        data: Beliebige Daten (dict, str, etc.)

    Returns:
        Redaktierte Daten
    """
    if isinstance(data, dict):
        return redact_dict(data)
    elif isinstance(data, str):
        return redact_value(data)
    elif isinstance(data, list):
        return [redact_for_logging(item) for item in data]
    else:
        return data


# ============================================================================
# Module Exports
# ============================================================================


__all__ = [
    # Enums and Config
    "RedactionLevel",
    "RedactionConfig",
    "DEFAULT_CONFIG",

    # Constants
    "SENSITIVE_FIELD_NAMES",
    "SENSITIVE_HEADERS",
    "CREDENTIAL_PATTERNS",

    # Functions
    "redact_value",
    "redact_dict",
    "redact_headers",
    "redact_url",
    "redact_json_string",
    "redact_for_logging",
    "is_sensitive_key",
    "get_redaction_processor",
    "setup_credential_redaction",

    # Classes
    "CredentialPattern",
    "CredentialRedactionProcessor",
    "CredentialRedactionMiddleware",
]

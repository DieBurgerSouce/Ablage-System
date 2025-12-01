# -*- coding: utf-8 -*-
"""
Webhook Signature Utilities für Ablage-System OCR.

Implementiert sichere HMAC-SHA256 Webhook-Signaturen:
- Timestamp-basierte Signaturen (Replay-Attack-Schutz)
- Versioniertes Signaturformat (t=<timestamp>,v1=<signature>)
- Timing-safe Vergleich
- Toleranzfenster für Zeitstempel

Format: X-Webhook-Signature: t=<unix_timestamp>,v1=<hmac_sha256_hex>

Feinpoliert und durchdacht - Enterprise-grade Webhook Security.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


class SignatureVersion(str, Enum):
    """Unterstützte Signatur-Versionen."""
    V1 = "v1"  # HMAC-SHA256


# Standard-Toleranzfenster: 5 Minuten (300 Sekunden)
DEFAULT_TOLERANCE_SECONDS = 300

# Maximales Toleranzfenster: 1 Stunde
MAX_TOLERANCE_SECONDS = 3600


@dataclass(frozen=True)
class SignatureComponents:
    """Geparste Signatur-Komponenten."""
    timestamp: int
    signatures: dict[str, str]  # version -> signature

    @property
    def v1_signature(self) -> Optional[str]:
        """Gibt v1-Signatur zurück (HMAC-SHA256)."""
        return self.signatures.get(SignatureVersion.V1.value)


class WebhookSignatureError(Exception):
    """Basis-Exception für Signatur-Fehler."""
    pass


class InvalidSignatureError(WebhookSignatureError):
    """Signatur ist ungültig oder stimmt nicht überein."""
    pass


class SignatureExpiredError(WebhookSignatureError):
    """Signatur ist abgelaufen (außerhalb des Toleranzfensters)."""
    pass


class InvalidSignatureFormatError(WebhookSignatureError):
    """Signaturformat ist ungültig."""
    pass


def generate_signature(
    payload: bytes,
    secret: str,
    timestamp: Optional[int] = None
) -> Tuple[str, int]:
    """
    Generiert eine signierte Webhook-Signatur.

    Args:
        payload: Der Webhook-Payload (bytes)
        secret: Das Webhook-Secret
        timestamp: Unix-Timestamp (optional, default: aktuelle Zeit)

    Returns:
        Tuple von (Signatur-Header-Wert, verwendeter Timestamp)

    Example:
        >>> payload = b'{"event": "test"}'
        >>> sig, ts = generate_signature(payload, "whsec_abc123")
        >>> sig
        't=1701234567,v1=abc123def456...'
    """
    if timestamp is None:
        timestamp = int(time.time())

    # Erstelle signierte Payload: timestamp.payload
    signed_payload = f"{timestamp}.".encode("utf-8") + payload

    # HMAC-SHA256 Signatur
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256
    ).hexdigest()

    # Formatiere Header-Wert
    header_value = f"t={timestamp},{SignatureVersion.V1.value}={signature}"

    return header_value, timestamp


def generate_signature_header(
    payload: bytes,
    secret: str,
    timestamp: Optional[int] = None
) -> str:
    """
    Generiert nur den Signatur-Header-Wert.

    Convenience-Funktion für generate_signature().
    """
    header_value, _ = generate_signature(payload, secret, timestamp)
    return header_value


def parse_signature_header(header: str) -> SignatureComponents:
    """
    Parst den Signatur-Header in seine Komponenten.

    Args:
        header: Der X-Webhook-Signature Header-Wert

    Returns:
        SignatureComponents mit Timestamp und Signaturen

    Raises:
        InvalidSignatureFormatError: Bei ungültigem Format
    """
    if not header:
        raise InvalidSignatureFormatError("Signatur-Header ist leer")

    timestamp: Optional[int] = None
    signatures: dict[str, str] = {}

    # Parse key=value Paare
    parts = header.split(",")
    for part in parts:
        part = part.strip()
        if "=" not in part:
            continue

        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()

        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                raise InvalidSignatureFormatError(
                    f"Ungültiger Timestamp-Wert: {value}"
                )
        elif key.startswith("v"):
            # Version (v1, v2, etc.)
            signatures[key] = value

    if timestamp is None:
        raise InvalidSignatureFormatError(
            "Timestamp (t=...) fehlt in Signatur"
        )

    if not signatures:
        raise InvalidSignatureFormatError(
            "Keine Signatur-Version (v1=...) gefunden"
        )

    return SignatureComponents(timestamp=timestamp, signatures=signatures)


def _compute_expected_signature(
    payload: bytes,
    secret: str,
    timestamp: int
) -> str:
    """Berechnet die erwartete HMAC-SHA256 Signatur."""
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    return hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256
    ).hexdigest()


def verify_signature(
    payload: bytes,
    header: str,
    secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS
) -> bool:
    """
    Verifiziert eine Webhook-Signatur.

    Args:
        payload: Der empfangene Webhook-Payload (bytes)
        header: Der X-Webhook-Signature Header-Wert
        secret: Das Webhook-Secret
        tolerance_seconds: Maximales Alter der Signatur in Sekunden

    Returns:
        True wenn Signatur gültig

    Raises:
        InvalidSignatureError: Signatur stimmt nicht überein
        SignatureExpiredError: Signatur ist abgelaufen
        InvalidSignatureFormatError: Ungültiges Signaturformat

    Example:
        >>> payload = b'{"event": "test"}'
        >>> sig_header = "t=1701234567,v1=abc123..."
        >>> verify_signature(payload, sig_header, "whsec_abc123")
        True
    """
    # Validiere Toleranzfenster
    if tolerance_seconds > MAX_TOLERANCE_SECONDS:
        tolerance_seconds = MAX_TOLERANCE_SECONDS

    # Parse Signatur-Header
    components = parse_signature_header(header)

    # Prüfe Timestamp (Replay-Attack-Schutz)
    current_time = int(time.time())
    timestamp_age = abs(current_time - components.timestamp)

    if timestamp_age > tolerance_seconds:
        logger.warning(
            "webhook_signature_expired",
            timestamp=components.timestamp,
            current_time=current_time,
            age_seconds=timestamp_age,
            tolerance_seconds=tolerance_seconds
        )
        raise SignatureExpiredError(
            f"Signatur ist abgelaufen. Alter: {timestamp_age}s, "
            f"Toleranz: {tolerance_seconds}s"
        )

    # Berechne erwartete Signatur
    expected_signature = _compute_expected_signature(
        payload, secret, components.timestamp
    )

    # Timing-safe Vergleich für v1 Signatur
    v1_signature = components.v1_signature
    if v1_signature is None:
        raise InvalidSignatureFormatError(
            "v1-Signatur fehlt (HMAC-SHA256 wird benötigt)"
        )

    # WICHTIG: Verwende timing-safe Vergleich!
    if not hmac.compare_digest(expected_signature, v1_signature):
        logger.warning(
            "webhook_signature_mismatch",
            timestamp=components.timestamp
        )
        raise InvalidSignatureError(
            "Signatur stimmt nicht überein"
        )

    return True


def verify_signature_safe(
    payload: bytes,
    header: str,
    secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS
) -> Tuple[bool, Optional[str]]:
    """
    Sichere Signaturverifizierung ohne Exceptions.

    Args:
        payload: Der empfangene Webhook-Payload (bytes)
        header: Der X-Webhook-Signature Header-Wert
        secret: Das Webhook-Secret
        tolerance_seconds: Maximales Alter der Signatur in Sekunden

    Returns:
        Tuple von (is_valid: bool, error_message: Optional[str])

    Example:
        >>> is_valid, error = verify_signature_safe(payload, header, secret)
        >>> if not is_valid:
        ...     print(f"Verification failed: {error}")
    """
    try:
        verify_signature(payload, header, secret, tolerance_seconds)
        return True, None
    except InvalidSignatureError as e:
        return False, f"Ungültige Signatur: {str(e)}"
    except SignatureExpiredError as e:
        return False, f"Signatur abgelaufen: {str(e)}"
    except InvalidSignatureFormatError as e:
        return False, f"Ungültiges Format: {str(e)}"
    except Exception as e:
        return False, f"Unbekannter Fehler: {str(e)}"


# ==================== Header-Konstanten ====================

# Standard-Header-Name für Webhook-Signaturen
SIGNATURE_HEADER_NAME = "X-Webhook-Signature"

# Alternative Header-Namen (für Kompatibilität)
SIGNATURE_HEADER_ALIASES = [
    "X-Hub-Signature-256",  # GitHub-Style
    "Stripe-Signature",      # Stripe-Style
]


def get_signature_header_value(headers: dict[str, str]) -> Optional[str]:
    """
    Extrahiert Signatur-Header aus verschiedenen Header-Formaten.

    Args:
        headers: Request-Headers (case-insensitive)

    Returns:
        Signatur-Header-Wert oder None
    """
    # Normalisiere Header-Keys zu lowercase
    normalized = {k.lower(): v for k, v in headers.items()}

    # Prüfe Standard-Header
    header_name_lower = SIGNATURE_HEADER_NAME.lower()
    if header_name_lower in normalized:
        return normalized[header_name_lower]

    # Prüfe Aliase
    for alias in SIGNATURE_HEADER_ALIASES:
        if alias.lower() in normalized:
            return normalized[alias.lower()]

    return None


# ==================== Utility-Funktionen ====================

def create_signed_webhook_payload(
    payload: bytes,
    secret: str,
    delivery_id: str,
    event_type: str
) -> Tuple[bytes, dict[str, str]]:
    """
    Erstellt signierte Webhook-Payload mit allen Standard-Headers.

    Args:
        payload: Der Webhook-Payload (bytes)
        secret: Das Webhook-Secret
        delivery_id: Eindeutige Delivery-ID
        event_type: Event-Typ (z.B. "document.processed")

    Returns:
        Tuple von (payload, headers_dict)

    Example:
        >>> payload = b'{"event": "test"}'
        >>> content, headers = create_signed_webhook_payload(
        ...     payload, "whsec_abc", "evt_123", "test.event"
        ... )
    """
    timestamp = int(time.time())
    signature_header, _ = generate_signature(payload, secret, timestamp)

    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER_NAME: signature_header,
        "X-Webhook-Delivery-ID": delivery_id,
        "X-Webhook-Event": event_type,
        "X-Webhook-Timestamp": str(timestamp),
        "User-Agent": "Ablage-Webhook/1.0"
    }

    return payload, headers


def is_webhook_secret_valid(secret: str) -> bool:
    """
    Prüft ob ein Webhook-Secret gültig ist.

    Args:
        secret: Das zu prüfende Secret

    Returns:
        True wenn Secret gültig (mindestens 32 Zeichen)
    """
    if not secret:
        return False

    # Mindestlänge: 32 Zeichen (256 bit Entropie bei base64)
    if len(secret) < 32:
        return False

    return True


def mask_webhook_secret(secret: str) -> str:
    """
    Maskiert ein Webhook-Secret für sichere Anzeige.

    Args:
        secret: Das zu maskierende Secret

    Returns:
        Maskiertes Secret (z.B. "whsec_abc...xyz")
    """
    if not secret or len(secret) < 10:
        return "***"

    # Zeige Prefix und letzte 4 Zeichen
    if secret.startswith("whsec_"):
        return f"whsec_...{secret[-4:]}"

    return f"{secret[:4]}...{secret[-4:]}"

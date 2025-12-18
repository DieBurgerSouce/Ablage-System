"""
Security validation functions for configuration.

Provides:
- Secret entropy calculation
- Secret quality validation
- Weak pattern detection

Feinpoliert und durchdacht - Sichere Validierung.
"""

import math
from typing import Tuple


def calculate_entropy_bits(secret: str) -> float:
    """
    Berechne die Entropie eines Secrets in Bits.

    Entropie = log2(Anzahl_einzigartiger_Zeichen ^ Laenge)

    Args:
        secret: Der zu pruefende String

    Returns:
        Entropie in Bits
    """
    if not secret:
        return 0.0

    unique_chars = len(set(secret))
    length = len(secret)

    if unique_chars <= 1:
        return 0.0

    # Entropie = log2(unique_chars) * length
    return math.log2(unique_chars) * length


def validate_secret_entropy(
    secret: str,
    min_entropy_bits: float = 128.0,
    min_unique_ratio: float = 0.3
) -> Tuple[bool, str]:
    """
    Validiere Entropie und Qualitaet eines Secrets.

    Args:
        secret: Der zu pruefende String
        min_entropy_bits: Mindest-Entropie in Bits (default: 128 fuer AES-128 Sicherheit)
        min_unique_ratio: Mindest-Verhaeltnis einzigartiger Zeichen (default: 30%)

    Returns:
        Tuple von (is_valid, error_message)
    """
    if not secret:
        return False, "Secret darf nicht leer sein"

    length = len(secret)
    unique_chars = len(set(secret))
    entropy = calculate_entropy_bits(secret)
    unique_ratio = unique_chars / length if length > 0 else 0

    # Pruefe Entropie
    if entropy < min_entropy_bits:
        return False, (
            f"Secret hat zu wenig Entropie ({entropy:.0f} Bits). "
            f"Mindestens {min_entropy_bits:.0f} Bits erforderlich. "
            f"Verwende mehr einzigartige Zeichen oder eine laengere Zeichenkette."
        )

    # Pruefe Einzigartigkeit (verhindert "aaaaaaa...")
    if unique_ratio < min_unique_ratio:
        return False, (
            f"Secret hat zu wenig einzigartige Zeichen ({unique_ratio*100:.0f}%). "
            f"Mindestens {min_unique_ratio*100:.0f}% einzigartige Zeichen erforderlich."
        )

    # Pruefe auf offensichtlich schwache Muster
    weak_patterns = [
        "12345", "password", "secret", "admin", "test",
        "qwerty", "asdfgh", "00000", "11111", "abcde"
    ]
    secret_lower = secret.lower()
    for pattern in weak_patterns:
        if pattern in secret_lower:
            return False, (
                f"Secret enthaelt schwaches Muster: '{pattern}'. "
                "Verwende einen sicher generierten Schluessel: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )

    return True, ""


# Common weak passwords for production validation
WEAK_PASSWORDS = ["changeme", "postgres", "password", "secret", "admin"]
MINIO_DEFAULT_USERS = ["minioadmin", "admin", "minio", "root"]
MINIO_DEFAULT_PASSWORDS = ["minioadmin", "minioadmin123", "minio123", "admin", "password", "123456"]

"""
Encryption Service für Ablage-System.

Implementiert sichere Verschlüsselung für sensible Daten wie:
- TOTP-Secrets (2FA)
- API-Keys
- Andere sensible Konfigurationsdaten

Verwendet AES-256-GCM für authentifizierte Verschlüsselung.

Feinpoliert und durchdacht - Enterprise-grade Encryption.
"""

import base64
import hashlib
import os
import secrets
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Konfiguration
AES_KEY_SIZE = 32  # 256 bits
NONCE_SIZE = 12  # 96 bits (recommended for GCM)
TAG_SIZE = 16  # 128 bits (standard for GCM)

# Encryption Key (muss in Umgebungsvariable gesetzt sein)
_encryption_key: Optional[bytes] = None


class EncryptionError(Exception):
    """Fehler bei Verschlüsselungsoperationen."""

    def __init__(self, message: str, user_message_de: str):
        super().__init__(message)
        self.user_message_de = user_message_de


class KeyNotConfiguredError(EncryptionError):
    """Verschlüsselungs-Key ist nicht konfiguriert."""

    def __init__(self):
        super().__init__(
            "Encryption key not configured",
            "Verschlüsselung nicht konfiguriert. Bitte Administrator kontaktieren."
        )


class DecryptionError(EncryptionError):
    """Fehler bei der Entschlüsselung."""

    def __init__(self, reason: str = ""):
        super().__init__(
            f"Decryption failed: {reason}",
            "Entschlüsselung fehlgeschlagen. Daten möglicherweise beschädigt."
        )


def _get_encryption_key() -> bytes:
    """
    Holt den Verschlüsselungs-Key aus den Settings.

    Der Key wird aus ENCRYPTION_KEY (Base64) oder SECRET_KEY abgeleitet.

    Returns:
        32-byte AES-256 Key

    Raises:
        KeyNotConfiguredError: Wenn kein Key konfiguriert ist
    """
    global _encryption_key

    if _encryption_key is not None:
        return _encryption_key

    # Versuche dedizierten Encryption Key
    encryption_key_b64 = getattr(settings, 'ENCRYPTION_KEY', None)
    if encryption_key_b64:
        try:
            _encryption_key = base64.b64decode(encryption_key_b64)
            if len(_encryption_key) == AES_KEY_SIZE:
                logger.info("encryption_key_loaded", source="ENCRYPTION_KEY")
                return _encryption_key
        except Exception as e:
            logger.warning(
                "encryption_key_decode_failed",
                error=str(e)
            )

    # Fallback: Ableitung aus SECRET_KEY
    secret_key = getattr(settings, 'SECRET_KEY', None)
    if not secret_key:
        raise KeyNotConfiguredError()

    # SECURITY FIX: SECRET_KEY ist jetzt SecretStr - verwende get_secret_value()
    secret_key_value = secret_key.get_secret_value() if hasattr(secret_key, 'get_secret_value') else secret_key

    # Derive 256-bit key using SHA-256
    _encryption_key = hashlib.sha256(secret_key_value.encode()).digest()

    logger.info("encryption_key_loaded", source="SECRET_KEY_DERIVED")
    return _encryption_key


def generate_encryption_key() -> str:
    """
    Generiert einen neuen Verschlüsselungs-Key.

    Nützlich für initiale Konfiguration.

    Returns:
        Base64-encoded 256-bit Key
    """
    key = secrets.token_bytes(AES_KEY_SIZE)
    return base64.b64encode(key).decode('utf-8')


def encrypt_data(plaintext: str, associated_data: Optional[str] = None) -> str:
    """
    Verschlüsselt Daten mit AES-256-GCM.

    Args:
        plaintext: Zu verschlüsselnde Daten
        associated_data: Optionale zusätzliche authentifizierte Daten (AAD)

    Returns:
        Base64-encoded verschlüsselte Daten (Format: nonce:ciphertext:tag)

    Raises:
        KeyNotConfiguredError: Wenn kein Key konfiguriert ist
        EncryptionError: Bei Verschlüsselungsfehlern
    """
    try:
        key = _get_encryption_key()
        aesgcm = AESGCM(key)

        # Generiere zufällige Nonce
        nonce = os.urandom(NONCE_SIZE)

        # Verschlüssele
        aad = associated_data.encode() if associated_data else None
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), aad)

        # Kombiniere nonce + ciphertext und encode als Base64
        combined = nonce + ciphertext
        encoded = base64.b64encode(combined).decode('utf-8')

        logger.debug(
            "data_encrypted",
            plaintext_length=len(plaintext),
            ciphertext_length=len(encoded)
        )

        return encoded

    except KeyNotConfiguredError:
        raise
    except Exception as e:
        logger.error("encryption_failed", error=str(e))
        raise EncryptionError(
            f"Encryption failed: {e}",
            "Verschlüsselung fehlgeschlagen"
        )


def decrypt_data(ciphertext: str, associated_data: Optional[str] = None) -> str:
    """
    Entschlüsselt mit AES-256-GCM verschlüsselte Daten.

    Args:
        ciphertext: Base64-encoded verschlüsselte Daten
        associated_data: Optionale zusätzliche authentifizierte Daten (AAD)

    Returns:
        Entschlüsselte Daten

    Raises:
        KeyNotConfiguredError: Wenn kein Key konfiguriert ist
        DecryptionError: Bei Entschlüsselungsfehlern
    """
    try:
        key = _get_encryption_key()
        aesgcm = AESGCM(key)

        # Decode Base64
        combined = base64.b64decode(ciphertext)

        # Extrahiere Nonce und Ciphertext
        if len(combined) < NONCE_SIZE + TAG_SIZE:
            raise DecryptionError("Data too short")

        nonce = combined[:NONCE_SIZE]
        encrypted_data = combined[NONCE_SIZE:]

        # Entschlüssele
        aad = associated_data.encode() if associated_data else None
        plaintext = aesgcm.decrypt(nonce, encrypted_data, aad)

        logger.debug(
            "data_decrypted",
            ciphertext_length=len(ciphertext),
            plaintext_length=len(plaintext)
        )

        return plaintext.decode('utf-8')

    except KeyNotConfiguredError:
        raise
    except InvalidTag:
        logger.warning("decryption_failed_invalid_tag")
        raise DecryptionError("Invalid authentication tag")
    except Exception as e:
        logger.error("decryption_failed", error=str(e))
        raise DecryptionError(str(e))


def is_encrypted(data: str) -> bool:
    """
    Prüft ob Daten verschlüsselt zu sein scheinen.

    Heuristik basierend auf:
    - Base64-Dekodierbarkeit
    - Mindestlänge (Nonce + Tag)

    Args:
        data: Zu prüfende Daten

    Returns:
        True wenn Daten verschlüsselt erscheinen
    """
    try:
        decoded = base64.b64decode(data)
        # Mindestens Nonce + Tag
        return len(decoded) >= NONCE_SIZE + TAG_SIZE
    except Exception:
        return False


def encrypt_totp_secret(secret: str, user_id: str) -> str:
    """
    Verschlüsselt einen TOTP-Secret.

    Verwendet User-ID als AAD für zusätzliche Sicherheit
    (verhindert das Übertragen verschlüsselter Secrets zwischen Benutzern).

    Args:
        secret: Base32-encoded TOTP Secret
        user_id: Benutzer-ID als AAD

    Returns:
        Verschlüsselter Secret
    """
    return encrypt_data(secret, associated_data=f"totp:{user_id}")


def decrypt_totp_secret(encrypted_secret: str, user_id: str) -> str:
    """
    Entschlüsselt einen TOTP-Secret.

    Args:
        encrypted_secret: Verschlüsselter Secret
        user_id: Benutzer-ID als AAD

    Returns:
        Base32-encoded TOTP Secret

    Raises:
        DecryptionError: Wenn Entschlüsselung fehlschlägt
    """
    return decrypt_data(encrypted_secret, associated_data=f"totp:{user_id}")


def rotate_encryption_key(
    old_key: bytes,
    new_key: bytes,
    ciphertext: str,
    associated_data: Optional[str] = None
) -> str:
    """
    Re-verschlüsselt Daten mit neuem Key (für Key-Rotation).

    Args:
        old_key: Alter Verschlüsselungs-Key
        new_key: Neuer Verschlüsselungs-Key
        ciphertext: Verschlüsselte Daten
        associated_data: Optionale AAD

    Returns:
        Mit neuem Key verschlüsselte Daten
    """
    # Entschlüssele mit altem Key
    old_aesgcm = AESGCM(old_key)
    combined = base64.b64decode(ciphertext)
    nonce = combined[:NONCE_SIZE]
    encrypted_data = combined[NONCE_SIZE:]
    aad = associated_data.encode() if associated_data else None

    plaintext = old_aesgcm.decrypt(nonce, encrypted_data, aad)

    # Verschlüssele mit neuem Key
    new_aesgcm = AESGCM(new_key)
    new_nonce = os.urandom(NONCE_SIZE)
    new_ciphertext = new_aesgcm.encrypt(new_nonce, plaintext, aad)

    new_combined = new_nonce + new_ciphertext
    return base64.b64encode(new_combined).decode('utf-8')


# Für Tests: Temporärer Key-Override
_test_key: Optional[bytes] = None


def set_test_key(key: Optional[bytes]) -> None:
    """Setzt temporären Key für Tests."""
    global _encryption_key, _test_key
    _test_key = key
    _encryption_key = key


def clear_key_cache() -> None:
    """Löscht gecachten Key (für Tests und Key-Rotation)."""
    global _encryption_key
    _encryption_key = None

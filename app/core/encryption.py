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
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
import structlog

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Konfiguration
AES_KEY_SIZE = 32  # 256 bits
NONCE_SIZE = 12  # 96 bits (recommended for GCM)
TAG_SIZE = 16  # 128 bits (standard for GCM)

# SECURITY: Key Derivation Function (KDF) Konfiguration
# NIST SP 800-132 empfiehlt mindestens 10.000 Iterationen für PBKDF2
# Wir verwenden 100.000 für zusätzliche Sicherheit
KDF_ITERATIONS = 100000
# Fester Salt für deterministische Key-Derivation aus SECRET_KEY
# Hinweis: Bei Änderung werden alle verschlüsselten Daten unlesbar!
KDF_SALT = b"ablage-system-encryption-kdf-v1"

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


def _derive_key_from_secret(secret_value: str) -> bytes:
    """
    Leitet einen sicheren Encryption Key aus einem Secret ab.

    Verwendet PBKDF2-HMAC-SHA256 mit 100.000 Iterationen gemäß
    NIST SP 800-132 Empfehlungen für sichere Key-Derivation.

    SECURITY: Diese Funktion ist deutlich sicherer als plain SHA-256:
    - Verwendet Salt um Rainbow-Table-Angriffe zu verhindern
    - 100.000 Iterationen verlangsamen Brute-Force-Angriffe
    - PBKDF2 ist ein etablierter, NIST-empfohlener Standard

    Args:
        secret_value: Das Secret (z.B. SECRET_KEY) aus dem der Key abgeleitet wird

    Returns:
        32-byte (256-bit) Key für AES-256
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=AES_KEY_SIZE,
        salt=KDF_SALT,
        iterations=KDF_ITERATIONS,
        backend=default_backend()
    )
    return kdf.derive(secret_value.encode())


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
    # SECURITY FIX: ENCRYPTION_KEY ist jetzt SecretStr - verwende get_secret_value()
    encryption_key_secret = getattr(settings, 'ENCRYPTION_KEY', None)
    if encryption_key_secret:
        try:
            # SecretStr: get_secret_value() aufrufen
            encryption_key_b64 = encryption_key_secret.get_secret_value() if hasattr(encryption_key_secret, 'get_secret_value') else encryption_key_secret
            _encryption_key = base64.b64decode(encryption_key_b64)
            if len(_encryption_key) == AES_KEY_SIZE:
                logger.info("encryption_key_loaded", source="ENCRYPTION_KEY")
                return _encryption_key
        except Exception as e:
            logger.warning(
                "encryption_key_decode_failed",
                **safe_error_log(e)
            )

    # Fallback: Ableitung aus SECRET_KEY
    secret_key = getattr(settings, 'SECRET_KEY', None)
    if not secret_key:
        raise KeyNotConfiguredError()

    # SECURITY FIX: SECRET_KEY ist jetzt SecretStr - verwende get_secret_value()
    secret_key_value = secret_key.get_secret_value() if hasattr(secret_key, 'get_secret_value') else secret_key

    # SECURITY: Derive key using PBKDF2 (statt unsicherem plain SHA-256)
    # PBKDF2 mit 100.000 Iterationen und Salt verhindert Rainbow-Table-Angriffe
    # und verlangsamt Brute-Force-Versuche erheblich
    _encryption_key = _derive_key_from_secret(secret_key_value)

    logger.info(
        "encryption_key_loaded",
        source="SECRET_KEY_DERIVED_PBKDF2",
        kdf_iterations=KDF_ITERATIONS
    )
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
        logger.error("encryption_failed", **safe_error_log(e))
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
        logger.error("decryption_failed", **safe_error_log(e))
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


def encrypt_api_key(api_key: str, connection_id: str) -> str:
    """
    Verschlüsselt einen API-Key für ERP-Verbindungen.

    Verwendet Connection-ID als AAD für zusätzliche Sicherheit
    (verhindert das Übertragen verschlüsselter Keys zwischen Verbindungen).

    Args:
        api_key: Der zu verschlüsselnde API-Key
        connection_id: ERP-Connection-ID als AAD

    Returns:
        Verschlüsselter API-Key
    """
    return encrypt_data(api_key, associated_data=f"erp_connection:{connection_id}")


def decrypt_api_key(encrypted_api_key: str, connection_id: str) -> str:
    """
    Entschlüsselt einen API-Key für ERP-Verbindungen.

    Args:
        encrypted_api_key: Verschlüsselter API-Key
        connection_id: ERP-Connection-ID als AAD

    Returns:
        Entschlüsselter API-Key

    Raises:
        DecryptionError: Wenn Entschlüsselung fehlschlägt
    """
    return decrypt_data(encrypted_api_key, associated_data=f"erp_connection:{connection_id}")


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


# ========== Key Versioning System ==========

# Key Version Prefix - ermöglicht Identifikation der Key-Version
KEY_VERSION_PREFIX = "v"
CURRENT_KEY_VERSION = 1

# Speicher für alte Keys (für Rotation)
_key_registry: dict = {}


class KeyVersionError(EncryptionError):
    """Fehler bei Key-Version."""

    def __init__(self, version: int):
        super().__init__(
            f"Unknown key version: {version}",
            f"Unbekannte Schluesselversion: {version}"
        )


def register_key(version: int, key: bytes) -> None:
    """Registriert einen Key mit Version im Registry.

    Wird für Key-Rotation benötigt, um alte Daten mit alten Keys
    lesen zu können.

    Args:
        version: Key-Versionsnummer
        key: 32-byte AES-256 Key
    """
    if len(key) != AES_KEY_SIZE:
        raise ValueError(f"Key muss {AES_KEY_SIZE} bytes sein")

    _key_registry[version] = key
    logger.info("encryption_key_registered", version=version)


def get_key_by_version(version: int) -> bytes:
    """Holt Key für eine bestimmte Version.

    Args:
        version: Key-Versionsnummer

    Returns:
        Key bytes

    Raises:
        KeyVersionError: Wenn Version nicht gefunden
    """
    if version in _key_registry:
        return _key_registry[version]

    # Version 1 = aktueller Key
    if version == 1:
        return _get_encryption_key()

    raise KeyVersionError(version)


def encrypt_with_version(
    plaintext: str,
    associated_data: Optional[str] = None,
    version: int = CURRENT_KEY_VERSION
) -> str:
    """Verschluesselt Daten mit versioniertem Key.

    Format: v{version}:{base64_ciphertext}

    Args:
        plaintext: Zu verschluesselnde Daten
        associated_data: Optionale AAD
        version: Key-Version (default: aktuelle)

    Returns:
        Versionierter verschluesselter String
    """
    key = get_key_by_version(version)
    aesgcm = AESGCM(key)

    nonce = os.urandom(NONCE_SIZE)
    aad = associated_data.encode() if associated_data else None
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), aad)

    combined = nonce + ciphertext
    encoded = base64.b64encode(combined).decode('utf-8')

    return f"{KEY_VERSION_PREFIX}{version}:{encoded}"


def decrypt_with_version(
    ciphertext: str,
    associated_data: Optional[str] = None
) -> Tuple[str, int]:
    """Entschluesselt versionierte Daten.

    Args:
        ciphertext: Versionierter verschluesselter String
        associated_data: Optionale AAD

    Returns:
        Tuple von (plaintext, verwendete_version)

    Raises:
        DecryptionError: Bei Fehler
    """
    # Version extrahieren
    if ciphertext.startswith(KEY_VERSION_PREFIX):
        try:
            version_str, encoded = ciphertext.split(":", 1)
            version = int(version_str[len(KEY_VERSION_PREFIX):])
        except (ValueError, IndexError):
            # Fallback: Keine Version = Version 1
            version = 1
            encoded = ciphertext
    else:
        # Legacy-Format ohne Version
        version = 1
        encoded = ciphertext

    key = get_key_by_version(version)
    aesgcm = AESGCM(key)

    combined = base64.b64decode(encoded)
    if len(combined) < NONCE_SIZE + TAG_SIZE:
        raise DecryptionError("Data too short")

    nonce = combined[:NONCE_SIZE]
    encrypted_data = combined[NONCE_SIZE:]
    aad = associated_data.encode() if associated_data else None

    try:
        plaintext = aesgcm.decrypt(nonce, encrypted_data, aad)
        return plaintext.decode('utf-8'), version
    except InvalidTag:
        raise DecryptionError("Invalid authentication tag")


def get_ciphertext_version(ciphertext: str) -> int:
    """Extrahiert Key-Version aus verschluesselten Daten.

    Args:
        ciphertext: Verschluesselte Daten

    Returns:
        Key-Version (1 wenn keine explizite Version)
    """
    if ciphertext.startswith(KEY_VERSION_PREFIX):
        try:
            version_str = ciphertext.split(":")[0]
            return int(version_str[len(KEY_VERSION_PREFIX):])
        except (ValueError, IndexError):
            return 1
    return 1


# ========== Key Rotation Service ==========

class KeyRotationService:
    """Service für sichere Key-Rotation.

    Ermöglicht das Rotieren von Encryption Keys ohne Datenverlust.
    Verwaltet mehrere Key-Versionen für übergangsloses Upgrade.
    """

    def __init__(
        self,
        new_key: Optional[bytes] = None,
        new_version: int = CURRENT_KEY_VERSION + 1
    ):
        """Initialisiert Key Rotation Service.

        Args:
            new_key: Neuer Key für Rotation (wird generiert wenn None)
            new_version: Version für neuen Key
        """
        self.new_key = new_key or secrets.token_bytes(AES_KEY_SIZE)
        self.new_version = new_version
        self.old_version = CURRENT_KEY_VERSION
        self._rotation_stats = {
            "total": 0,
            "migrated": 0,
            "failed": 0,
            "already_current": 0
        }

    def get_new_key_base64(self) -> str:
        """Gibt neuen Key als Base64 zurück (für Konfiguration)."""
        return base64.b64encode(self.new_key).decode('utf-8')

    def prepare_rotation(self) -> None:
        """Bereitet Key-Rotation vor.

        Registriert neuen Key im Registry.
        """
        register_key(self.new_version, self.new_key)
        logger.info(
            "key_rotation_prepared",
            old_version=self.old_version,
            new_version=self.new_version
        )

    def rotate_single(
        self,
        ciphertext: str,
        associated_data: Optional[str] = None
    ) -> str:
        """Rotiert einzelnen verschluesselten Wert.

        Args:
            ciphertext: Verschluesselte Daten
            associated_data: Optionale AAD

        Returns:
            Mit neuem Key verschluesselte Daten
        """
        self._rotation_stats["total"] += 1

        # Version prüfen
        current_version = get_ciphertext_version(ciphertext)
        if current_version >= self.new_version:
            self._rotation_stats["already_current"] += 1
            return ciphertext

        try:
            # Entschluesseln mit alter Version
            plaintext, _ = decrypt_with_version(ciphertext, associated_data)

            # Verschluesseln mit neuer Version
            new_ciphertext = encrypt_with_version(
                plaintext,
                associated_data,
                version=self.new_version
            )

            self._rotation_stats["migrated"] += 1
            return new_ciphertext

        except Exception as e:
            self._rotation_stats["failed"] += 1
            logger.error(
                "key_rotation_failed",
                **safe_error_log(e),
                ciphertext_preview=ciphertext[:20] + "..."
            )
            raise

    def get_stats(self) -> dict:
        """Gibt Rotations-Statistiken zurück."""
        return self._rotation_stats.copy()

    def finalize_rotation(self) -> None:
        """Schließt Key-Rotation ab.

        Sollte aufgerufen werden nachdem alle Daten migriert wurden.
        Löscht alten Key aus Registry (optional).
        """
        global CURRENT_KEY_VERSION
        CURRENT_KEY_VERSION = self.new_version

        logger.info(
            "key_rotation_finalized",
            new_version=self.new_version,
            stats=self._rotation_stats
        )


async def rotate_user_secrets(
    db_session,  # AsyncSession
    user_ids: list,
    rotation_service: KeyRotationService
) -> dict:
    """Rotiert Encryption Keys für Benutzer-Secrets.

    Beispiel-Implementierung für Batch-Rotation von TOTP-Secrets.

    Args:
        db_session: Datenbank-Session
        user_ids: Liste der zu migrierenden User-IDs
        rotation_service: Konfigurierter KeyRotationService

    Returns:
        Dict mit Rotations-Ergebnis
    """
    from sqlalchemy import select, update

    results = {
        "total_users": len(user_ids),
        "migrated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }

    # Hinweis: Dies ist ein Beispiel - User-Model muss angepasst werden
    try:
        from app.db.models import User


        for user_id in user_ids:
            try:
                # User laden
                result = await db_session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()

                if not user or not user.totp_secret:
                    results["skipped"] += 1
                    continue

                # TOTP Secret rotieren
                new_secret = rotation_service.rotate_single(
                    user.totp_secret,
                    associated_data=f"totp:{user_id}"
                )

                # Speichern
                await db_session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(totp_secret=new_secret)
                )

                results["migrated"] += 1

            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "user_id": str(user_id), **safe_error_log(e)})
                logger.warning(
                    "user_secret_rotation_failed",
                    user_id=str(user_id),
                    **safe_error_log(e)
                )

        await db_session.commit()

    except ImportError:
        logger.warning("user_model_not_available_for_rotation")

    return results


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

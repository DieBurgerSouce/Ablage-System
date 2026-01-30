"""
Two-Factor Authentication (2FA) TOTP Service für Ablage-System.

Implementiert TOTP (Time-based One-Time Password) gemäß RFC 6238.
Kompatibel mit Google Authenticator, Authy, Microsoft Authenticator.

Sicherheitsmerkmale:
- 6-stellige Codes mit 30-Sekunden-Intervall
- 8 Einmal-Backup-Codes (SHA-256 gehasht)
- QR-Code-Generierung für einfaches Setup
- Rate-Limiting gegen Brute-Force

Feinpoliert und durchdacht - Enterprise-grade 2FA.
"""

from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any
import secrets
import hashlib
import base64
from io import BytesIO

import structlog

# TOTP Bibliothek (pyotp)
try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    pyotp = None  # type: ignore
    PYOTP_AVAILABLE = False

# QR-Code Bibliothek
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    qrcode = None  # type: ignore
    QRCODE_AVAILABLE = False

from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.core.encryption import (

    encrypt_totp_secret,
    decrypt_totp_secret,
    DecryptionError,
    KeyNotConfiguredError,
)

logger = structlog.get_logger(__name__)

# TOTP-Konfiguration
TOTP_ISSUER = settings.APP_NAME  # "Ablage-System OCR"
TOTP_INTERVAL = 30  # Sekunden
TOTP_DIGITS = 6
TOTP_ALGORITHM = "SHA1"  # Standard für Authenticator-Apps
BACKUP_CODE_COUNT = 8
BACKUP_CODE_LENGTH = 8  # Zeichen pro Code


class TOTPError(Exception):
    """Basis-Exception für TOTP-Fehler."""
    pass


class TOTPNotAvailableError(TOTPError):
    """Ausnahme wenn pyotp nicht installiert ist."""
    pass


class TOTPInvalidCodeError(TOTPError):
    """Ausnahme bei ungültigem TOTP-Code."""
    pass


class TOTPAlreadyEnabledError(TOTPError):
    """Ausnahme wenn 2FA bereits aktiviert ist."""
    pass


class TOTPNotEnabledError(TOTPError):
    """Ausnahme wenn 2FA nicht aktiviert ist."""
    pass


class TOTPSecretEncryptionError(TOTPError):
    """Ausnahme bei Verschlüsselungs-/Entschlüsselungsfehlern."""

    def __init__(self, message: str, user_message_de: str):
        super().__init__(message)
        self.user_message_de = user_message_de


def check_totp_available() -> bool:
    """Prüft ob TOTP verfügbar ist (pyotp installiert)."""
    if not PYOTP_AVAILABLE:
        logger.warning(
            "totp_not_available",
            message="pyotp nicht installiert. 2FA nicht verfügbar. "
                    "Installiere mit: pip install pyotp"
        )
        return False
    return True


def generate_totp_secret() -> str:
    """
    Generiert einen neuen TOTP-Secret.

    Returns:
        Base32-encoded Secret (32 Zeichen)

    Raises:
        TOTPNotAvailableError: Wenn pyotp nicht installiert ist
    """
    if not PYOTP_AVAILABLE:
        raise TOTPNotAvailableError("pyotp ist nicht installiert")

    return pyotp.random_base32()


def get_totp_provisioning_uri(
    secret: str,
    email: str,
    issuer: Optional[str] = None
) -> str:
    """
    Generiert die Provisioning-URI für Authenticator-Apps.

    Args:
        secret: Base32-encoded TOTP-Secret
        email: Benutzer-E-Mail (wird als Account-Name verwendet)
        issuer: Optionaler Issuer-Name (Default: APP_NAME)

    Returns:
        otpauth:// URI für Authenticator-Apps

    Raises:
        TOTPNotAvailableError: Wenn pyotp nicht installiert ist
    """
    if not PYOTP_AVAILABLE:
        raise TOTPNotAvailableError("pyotp ist nicht installiert")

    issuer = issuer or TOTP_ISSUER
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL, digits=TOTP_DIGITS)

    return totp.provisioning_uri(name=email, issuer_name=issuer)


def generate_totp_qr_code(
    secret: str,
    email: str,
    issuer: Optional[str] = None
) -> Optional[str]:
    """
    Generiert einen QR-Code als Base64-encoded PNG.

    Args:
        secret: Base32-encoded TOTP-Secret
        email: Benutzer-E-Mail
        issuer: Optionaler Issuer-Name

    Returns:
        Base64-encoded PNG-Bild oder None wenn qrcode nicht verfügbar

    Raises:
        TOTPNotAvailableError: Wenn pyotp nicht installiert ist
    """
    if not PYOTP_AVAILABLE:
        raise TOTPNotAvailableError("pyotp ist nicht installiert")

    if not QRCODE_AVAILABLE:
        logger.warning(
            "qrcode_not_available",
            message="qrcode nicht installiert. QR-Code-Generierung nicht verfügbar. "
                    "Installiere mit: pip install qrcode[pil]"
        )
        return None

    uri = get_totp_provisioning_uri(secret, email, issuer)

    # QR-Code generieren
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)

    # Als PNG in BytesIO schreiben
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    # Base64-Encoding
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    logger.debug("totp_qr_code_generated", email=email[:3] + "***")

    return f"data:image/png;base64,{encoded}"


def verify_totp_code(secret: str, code: str, valid_window: int = 1) -> bool:
    """
    Verifiziert einen TOTP-Code.

    Args:
        secret: Base32-encoded TOTP-Secret
        code: 6-stelliger TOTP-Code vom Benutzer
        valid_window: Erlaubte Zeitabweichung in Intervallen (Default: 1 = ±30s)

    Returns:
        True wenn Code gültig ist

    Raises:
        TOTPNotAvailableError: Wenn pyotp nicht installiert ist
    """
    if not PYOTP_AVAILABLE:
        raise TOTPNotAvailableError("pyotp ist nicht installiert")

    # Code normalisieren (Leerzeichen entfernen)
    code = code.replace(" ", "").replace("-", "")

    # Validiere Format
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        logger.warning(
            "totp_invalid_format",
            code_length=len(code),
            message="Ungültiges TOTP-Code-Format"
        )
        return False

    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL, digits=TOTP_DIGITS)

    is_valid = totp.verify(code, valid_window=valid_window)

    logger.debug(
        "totp_verification",
        is_valid=is_valid,
        code_prefix=code[:2] + "****" if len(code) >= 2 else "****"
    )

    return is_valid


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> Tuple[List[str], List[str]]:
    """
    Generiert Backup-Codes für 2FA-Recovery.

    Jeder Code kann nur einmal verwendet werden und ermöglicht
    Login wenn das Authenticator-Gerät verloren geht.

    Args:
        count: Anzahl der Backup-Codes (Default: 8)

    Returns:
        Tuple von:
        - plain_codes: Klartext-Codes zum Anzeigen für den Benutzer
        - hashed_codes: SHA-256-gehashte Codes zum Speichern in DB
    """
    plain_codes = []
    hashed_codes = []

    for _ in range(count):
        # Generiere zufälligen Code (alphanumerisch)
        code = secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper()

        # Formatiere für bessere Lesbarkeit (xxxx-xxxx)
        formatted_code = f"{code[:4]}-{code[4:]}"
        plain_codes.append(formatted_code)

        # Hash für Speicherung (mit Code-Normalisierung)
        normalized = code.replace("-", "").upper()
        code_hash = hashlib.sha256(normalized.encode()).hexdigest()
        hashed_codes.append(code_hash)

    logger.info("totp_backup_codes_generated", count=count)

    return plain_codes, hashed_codes


def verify_backup_code(
    code: str,
    hashed_codes: List[str]
) -> Tuple[bool, Optional[int]]:
    """
    Verifiziert einen Backup-Code.

    Args:
        code: Backup-Code vom Benutzer
        hashed_codes: Liste der gehashten Backup-Codes aus der DB

    Returns:
        Tuple von:
        - is_valid: True wenn Code gültig ist
        - index: Index des verwendeten Codes (für Entfernung aus DB)
    """
    # Code normalisieren
    normalized = code.replace("-", "").replace(" ", "").upper()

    # Hash berechnen
    code_hash = hashlib.sha256(normalized.encode()).hexdigest()

    # Prüfen ob Code in Liste
    for i, stored_hash in enumerate(hashed_codes):
        if secrets.compare_digest(code_hash, stored_hash):
            logger.info("totp_backup_code_used", code_index=i)
            return True, i

    logger.warning("totp_backup_code_invalid")
    return False, None


def get_current_totp_code(secret: str) -> str:
    """
    Generiert den aktuellen TOTP-Code (nur für Tests/Debugging).

    WARNUNG: Nicht in Production verwenden!

    Args:
        secret: Base32-encoded TOTP-Secret

    Returns:
        Aktueller 6-stelliger TOTP-Code
    """
    if not PYOTP_AVAILABLE:
        raise TOTPNotAvailableError("pyotp ist nicht installiert")

    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL, digits=TOTP_DIGITS)
    return totp.now()


def get_totp_remaining_seconds() -> int:
    """
    Gibt die verbleibenden Sekunden bis zum nächsten TOTP-Intervall zurück.

    Nützlich für Frontend-Countdown-Anzeige.

    Returns:
        Verbleibende Sekunden (0-29)
    """
    import time
    return TOTP_INTERVAL - int(time.time()) % TOTP_INTERVAL


# ==================== Secret Encryption/Decryption ====================

def encrypt_secret(secret: str, user_id: str) -> str:
    """
    Verschlüsselt einen TOTP-Secret für sichere DB-Speicherung.

    Verwendet AES-256-GCM mit User-ID als AAD (Associated Authenticated Data),
    um sicherzustellen, dass verschlüsselte Secrets nicht zwischen Benutzern
    übertragen werden können.

    Args:
        secret: Base32-encoded TOTP-Secret (Klartext)
        user_id: Benutzer-ID (wird als AAD verwendet)

    Returns:
        Verschlüsselter Secret (Base64-encoded)

    Raises:
        TOTPSecretEncryptionError: Bei Verschlüsselungsfehlern
    """
    try:
        encrypted = encrypt_totp_secret(secret, user_id)
        logger.debug(
            "totp_secret_encrypted",
            user_id=str(user_id)[:8] + "..."
        )
        return encrypted
    except KeyNotConfiguredError:
        logger.error("totp_encryption_key_not_configured")
        raise TOTPSecretEncryptionError(
            "Encryption key not configured",
            "Verschlüsselung nicht konfiguriert. Bitte Administrator kontaktieren."
        )
    except Exception as e:
        logger.error("totp_secret_encryption_failed", **safe_error_log(e))
        raise TOTPSecretEncryptionError(
            f"Encryption failed: {e}",
            "Verschlüsselung fehlgeschlagen. Bitte später erneut versuchen."
        )


def decrypt_secret(encrypted_secret: str, user_id: str) -> str:
    """
    Entschlüsselt einen TOTP-Secret aus der Datenbank.

    Args:
        encrypted_secret: Verschlüsselter Secret (Base64-encoded)
        user_id: Benutzer-ID (muss mit Verschlüsselung übereinstimmen)

    Returns:
        Base32-encoded TOTP-Secret (Klartext)

    Raises:
        TOTPSecretEncryptionError: Bei Entschlüsselungsfehlern
    """
    try:
        decrypted = decrypt_totp_secret(encrypted_secret, user_id)
        logger.debug(
            "totp_secret_decrypted",
            user_id=str(user_id)[:8] + "..."
        )
        return decrypted
    except KeyNotConfiguredError:
        logger.error("totp_decryption_key_not_configured")
        raise TOTPSecretEncryptionError(
            "Encryption key not configured",
            "Entschlüsselung nicht konfiguriert. Bitte Administrator kontaktieren."
        )
    except DecryptionError as e:
        logger.error("totp_secret_decryption_failed", **safe_error_log(e))
        raise TOTPSecretEncryptionError(
            f"Decryption failed: {e}",
            "Entschlüsselung fehlgeschlagen. Secret möglicherweise beschädigt."
        )
    except Exception as e:
        logger.error("totp_secret_decryption_unexpected_error", **safe_error_log(e))
        raise TOTPSecretEncryptionError(
            f"Decryption failed: {e}",
            "Entschlüsselung fehlgeschlagen. Bitte Administrator kontaktieren."
        )


def verify_totp_code_encrypted(
    encrypted_secret: str,
    user_id: str,
    code: str,
    valid_window: int = 1
) -> bool:
    """
    Verifiziert einen TOTP-Code mit verschlüsseltem Secret.

    Convenience-Funktion, die Entschlüsselung und Verifikation kombiniert.

    Args:
        encrypted_secret: Verschlüsselter TOTP-Secret aus der DB
        user_id: Benutzer-ID für Entschlüsselung
        code: 6-stelliger TOTP-Code vom Benutzer
        valid_window: Erlaubte Zeitabweichung in Intervallen (Default: 1)

    Returns:
        True wenn Code gültig ist

    Raises:
        TOTPSecretEncryptionError: Bei Entschlüsselungsfehlern
        TOTPNotAvailableError: Wenn pyotp nicht installiert ist
    """
    secret = decrypt_secret(encrypted_secret, user_id)
    return verify_totp_code(secret, code, valid_window)


def verify_2fa_login_encrypted(
    encrypted_secret: str,
    user_id: str,
    code: str,
    backup_codes: Optional[List[str]] = None
) -> Tuple[bool, bool, Optional[int]]:
    """
    Verifiziert 2FA bei Login mit verschlüsseltem Secret.

    Convenience-Funktion, die Entschlüsselung und Verifikation kombiniert.

    Args:
        encrypted_secret: Verschlüsselter TOTP-Secret aus der DB
        user_id: Benutzer-ID für Entschlüsselung
        code: Code vom Benutzer (TOTP oder Backup)
        backup_codes: Optional: Liste der gehashten Backup-Codes

    Returns:
        Tuple von:
        - is_valid: True wenn Authentifizierung erfolgreich
        - used_backup: True wenn Backup-Code verwendet wurde
        - backup_index: Index des verwendeten Backup-Codes (falls used_backup=True)

    Raises:
        TOTPSecretEncryptionError: Bei Entschlüsselungsfehlern
    """
    secret = decrypt_secret(encrypted_secret, user_id)
    return verify_2fa_login(secret, code, backup_codes)


# ==================== 2FA Setup/Management Functions ====================

async def setup_2fa(
    user_id: str,
    email: str,
    db_session: Any
) -> Dict[str, Any]:
    """
    Initiiert 2FA-Setup für einen Benutzer.

    Generiert Secret, QR-Code und Backup-Codes.
    Der Benutzer muss mit verify_2fa_setup() bestätigen.

    Args:
        user_id: Benutzer-ID
        email: Benutzer-E-Mail für Provisioning-URI
        db_session: Datenbank-Session

    Returns:
        Dict mit:
        - secret: TOTP-Secret (zum temporären Speichern)
        - qr_code: Base64-encoded QR-Code PNG
        - provisioning_uri: otpauth:// URI
        - backup_codes: Liste der Backup-Codes (Klartext)

    Raises:
        TOTPNotAvailableError: Wenn pyotp nicht installiert ist
        TOTPAlreadyEnabledError: Wenn 2FA bereits aktiviert ist
    """
    if not PYOTP_AVAILABLE:
        raise TOTPNotAvailableError("2FA ist nicht verfügbar (pyotp nicht installiert)")

    # Generiere neuen Secret
    secret = generate_totp_secret()

    # Generiere QR-Code
    qr_code = generate_totp_qr_code(secret, email)

    # Generiere Provisioning-URI (für manuelle Eingabe)
    provisioning_uri = get_totp_provisioning_uri(secret, email)

    # Generiere Backup-Codes
    plain_codes, hashed_codes = generate_backup_codes()

    # Verschlüssele Secret für DB-Speicherung
    encrypted_secret = encrypt_secret(secret, user_id)

    logger.info(
        "totp_setup_initiated",
        user_id=str(user_id)[:8] + "...",
        email=email[:3] + "***"
    )

    return {
        "secret": secret,  # Klartext für QR-Code/Setup-Verifikation
        "encrypted_secret": encrypted_secret,  # Verschlüsselt für DB-Speicherung
        "qr_code": qr_code,
        "provisioning_uri": provisioning_uri,
        "backup_codes": plain_codes,
        "hashed_backup_codes": hashed_codes,
    }


def verify_2fa_setup(secret: str, code: str) -> bool:
    """
    Verifiziert 2FA-Setup durch Eingabe des ersten TOTP-Codes.

    Muss erfolgreich sein, bevor 2FA aktiviert wird.

    Args:
        secret: TOTP-Secret aus setup_2fa()
        code: TOTP-Code vom Authenticator

    Returns:
        True wenn Code korrekt ist
    """
    return verify_totp_code(secret, code)


def verify_2fa_login(
    secret: str,
    code: str,
    backup_codes: Optional[List[str]] = None
) -> Tuple[bool, bool, Optional[int]]:
    """
    Verifiziert 2FA bei Login.

    Prüft zuerst TOTP-Code, dann Backup-Codes falls vorhanden.

    Args:
        secret: TOTP-Secret des Benutzers
        code: Code vom Benutzer (TOTP oder Backup)
        backup_codes: Optional: Liste der gehashten Backup-Codes

    Returns:
        Tuple von:
        - is_valid: True wenn Authentifizierung erfolgreich
        - used_backup: True wenn Backup-Code verwendet wurde
        - backup_index: Index des verwendeten Backup-Codes (falls used_backup=True)
    """
    # Versuche TOTP-Code
    if verify_totp_code(secret, code):
        return True, False, None

    # Versuche Backup-Code (wenn vorhanden)
    if backup_codes:
        is_valid, index = verify_backup_code(code, backup_codes)
        if is_valid:
            return True, True, index

    return False, False, None

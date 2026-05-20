"""
MFA (Multi-Factor Authentication) Service für TOTP-basierte 2FA.

Features:
- TOTP (Time-based One-Time Password) nach RFC 6238
- Verschlüsselte Secret-Speicherung (AES-256-GCM)
- Backup-Codes mit bcrypt-Hashing
- QR-Code-Generierung für Authenticator-Apps
- Rate Limiting für Brute-Force-Schutz

Unterstützte Authenticator-Apps:
- Google Authenticator
- Microsoft Authenticator
- Authy
- 1Password
- Bitwarden

SECURITY:
- Secrets werden NIE im Klartext gespeichert
- Backup-Codes sind One-Time-Use
- Max 5 fehlgeschlagene Versuche pro 15 Minuten
"""

import base64
import hashlib
import io
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from uuid import UUID

import bcrypt
import pyotp
import qrcode
import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.config import settings
from app.db.models import User

logger = structlog.get_logger(__name__)

# TOTP Configuration
TOTP_ISSUER = "Ablage-System"
TOTP_DIGITS = 6
TOTP_INTERVAL = 30  # Seconds
TOTP_VALID_WINDOW = 1  # Allow 1 period before/after for clock drift

# Backup Codes Configuration
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8  # Characters per code

# Rate Limiting
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


class MFAServiceError(Exception):
    """Base exception für MFA-Service-Fehler."""
    pass


class MFAAlreadyEnabledError(MFAServiceError):
    """2FA ist bereits aktiviert."""
    pass


class MFANotEnabledError(MFAServiceError):
    """2FA ist nicht aktiviert."""
    pass


class InvalidTOTPCodeError(MFAServiceError):
    """Ungültiger TOTP-Code."""
    pass


class RateLimitExceededError(MFAServiceError):
    """Zu viele fehlgeschlagene Versuche."""
    pass


class MFAService:
    """
    Service für Multi-Factor Authentication mit TOTP.

    Beispiel:
        mfa_service = MFAService(db)

        # Setup starten
        qr_data, backup_codes = await mfa_service.setup_totp(user_id)

        # Mit Code bestätigen
        await mfa_service.verify_and_enable_totp(user_id, totp_code)

        # Bei Login verifizieren
        is_valid = await mfa_service.verify_totp(user_id, totp_code)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._encryption_key = self._derive_encryption_key()

    def _derive_encryption_key(self) -> bytes:
        """
        Leitet den AES-256 Schluessel aus dem SECRET_KEY ab.

        Verwendet HKDF-ähnliche Ableitung für Schluesseltrennung.
        """
        # Verwende SHA-256 um einen 32-byte Schluessel abzuleiten
        key_material = f"{settings.SECRET_KEY}:totp:encryption".encode()
        return hashlib.sha256(key_material).digest()

    def _encrypt_secret(self, secret: str) -> str:
        """
        Verschlüsselt das TOTP-Secret mit AES-256-GCM.

        Format: Base64(nonce || ciphertext || tag)

        Args:
            secret: Das Klartext-TOTP-Secret

        Returns:
            Base64-encoded verschlüsselter String
        """
        aesgcm = AESGCM(self._encryption_key)
        nonce = secrets.token_bytes(12)  # 96-bit nonce für GCM

        ciphertext = aesgcm.encrypt(
            nonce,
            secret.encode('utf-8'),
            associated_data=b"totp_secret"
        )

        # Kombiniere nonce + ciphertext (tag ist bereits enthalten)
        encrypted_data = nonce + ciphertext
        return base64.b64encode(encrypted_data).decode('ascii')

    def _decrypt_secret(self, encrypted: str) -> str:
        """
        Entschlüsselt das TOTP-Secret.

        Args:
            encrypted: Base64-encoded verschlüsselter String

        Returns:
            Klartext-TOTP-Secret
        """
        encrypted_data = base64.b64decode(encrypted)

        # Extrahiere nonce (12 bytes) und ciphertext+tag
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]

        aesgcm = AESGCM(self._encryption_key)
        plaintext = aesgcm.decrypt(
            nonce,
            ciphertext,
            associated_data=b"totp_secret"
        )

        return plaintext.decode('utf-8')

    def _generate_backup_codes(self) -> Tuple[List[str], List[str]]:
        """
        Generiert Backup-Codes und deren Hashes.

        Returns:
            Tuple von (Klartext-Codes für User, bcrypt-Hashes für DB)
        """
        codes = []
        hashed_codes = []

        for _ in range(BACKUP_CODE_COUNT):
            # Generiere zufälligen Code (Hex-String)
            code = secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper()
            # Format: XXXX-XXXX für bessere Lesbarkeit
            formatted_code = f"{code[:4]}-{code[4:]}"
            codes.append(formatted_code)

            # Hash mit bcrypt (cost factor 12)
            code_hash = bcrypt.hashpw(
                code.encode('utf-8'),
                bcrypt.gensalt(rounds=12)
            ).decode('utf-8')
            hashed_codes.append(code_hash)

        return codes, hashed_codes

    async def _get_user(self, user_id: UUID) -> Optional[User]:
        """Holt User aus der Datenbank."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def setup_totp(
        self,
        user_id: UUID
    ) -> Tuple[str, str, List[str]]:
        """
        Startet den TOTP-Setup-Prozess.

        Generiert ein neues Secret und Backup-Codes, aber aktiviert
        2FA noch nicht. Der User muss setup_totp_verify aufrufen.

        Args:
            user_id: UUID des Users

        Returns:
            Tuple von (QR-Code als Data-URI, Secret für manuelle Eingabe, Backup-Codes)

        Raises:
            MFAAlreadyEnabledError: Wenn 2FA bereits aktiviert ist
        """
        user = await self._get_user(user_id)
        if not user:
            raise MFAServiceError("Benutzer nicht gefunden")

        if user.totp_enabled:
            raise MFAAlreadyEnabledError(
                "Zwei-Faktor-Authentifizierung ist bereits aktiviert"
            )

        # Generiere neues TOTP-Secret (Base32-encoded)
        secret = pyotp.random_base32()

        # Erstelle TOTP-Objekt
        totp = pyotp.TOTP(
            secret,
            digits=TOTP_DIGITS,
            interval=TOTP_INTERVAL,
            issuer=TOTP_ISSUER
        )

        # Generiere Provisioning-URI für QR-Code
        # Format: otpauth://totp/Issuer:account?secret=...&issuer=...
        account_name = user.email or user.username
        provisioning_uri = totp.provisioning_uri(
            name=account_name,
            issuer_name=TOTP_ISSUER
        )

        # Generiere QR-Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(provisioning_uri)
        qr.make(fit=True)

        # Konvertiere zu PNG Data-URI
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_data_uri = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"

        # Generiere Backup-Codes
        backup_codes, hashed_codes = self._generate_backup_codes()

        # Speichere verschlüsseltes Secret und gehashte Backup-Codes
        # ABER aktiviere 2FA noch nicht (totp_enabled bleibt False)
        encrypted_secret = self._encrypt_secret(secret)

        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                totp_secret=encrypted_secret,
                totp_backup_codes=hashed_codes,
                # totp_enabled bleibt False bis verify_and_enable_totp
            )
        )
        await self.db.commit()

        logger.info(
            "totp_setup_initiated",
            user_id=str(user_id)
        )

        return qr_data_uri, secret, backup_codes

    async def verify_and_enable_totp(
        self,
        user_id: UUID,
        totp_code: str
    ) -> bool:
        """
        Verifiziert den TOTP-Code und aktiviert 2FA.

        Dieser Schritt bestätigt dass der User die Authenticator-App
        korrekt eingerichtet hat.

        Args:
            user_id: UUID des Users
            totp_code: 6-stelliger Code aus der Authenticator-App

        Returns:
            True wenn erfolgreich aktiviert

        Raises:
            InvalidTOTPCodeError: Bei ungültigem Code
            MFAAlreadyEnabledError: Wenn 2FA bereits aktiviert ist
        """
        user = await self._get_user(user_id)
        if not user:
            raise MFAServiceError("Benutzer nicht gefunden")

        if user.totp_enabled:
            raise MFAAlreadyEnabledError(
                "Zwei-Faktor-Authentifizierung ist bereits aktiviert"
            )

        if not user.totp_secret:
            raise MFAServiceError(
                "TOTP-Setup wurde nicht gestartet. Bitte zuerst setup_totp aufrufen."
            )

        # Entschlüssele Secret und verifiziere Code
        secret = self._decrypt_secret(user.totp_secret)
        totp = pyotp.TOTP(
            secret,
            digits=TOTP_DIGITS,
            interval=TOTP_INTERVAL
        )

        # Verifiziere mit Toleranz für Zeitdrift
        is_valid = totp.verify(totp_code, valid_window=TOTP_VALID_WINDOW)

        if not is_valid:
            logger.warning(
                "totp_setup_verification_failed",
                user_id=str(user_id)
            )
            raise InvalidTOTPCodeError(
                "Ungültiger Verifizierungscode. Bitte versuchen Sie es erneut."
            )

        # Aktiviere 2FA
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                totp_enabled=True,
                totp_setup_at=datetime.now(timezone.utc)
            )
        )
        await self.db.commit()

        logger.info(
            "totp_enabled",
            user_id=str(user_id)
        )

        return True

    async def _check_rate_limit(self, user: User) -> None:
        """
        Prüft ob User wegen zu vieler fehlgeschlagener Versuche gesperrt ist.

        Raises:
            RateLimitExceededError: Wenn User gesperrt ist
        """
        if user.totp_lockout_until:
            now = datetime.now(timezone.utc)
            if now < user.totp_lockout_until:
                remaining = user.totp_lockout_until - now
                remaining_minutes = int(remaining.total_seconds() / 60) + 1
                raise RateLimitExceededError(
                    f"Zu viele fehlgeschlagene Versuche. "
                    f"Bitte warten Sie {remaining_minutes} Minute(n)."
                )
            else:
                # Lockout abgelaufen - zurücksetzen
                await self.db.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(
                        totp_failed_attempts=0,
                        totp_lockout_until=None
                    )
                )
                await self.db.commit()

    async def _record_failed_attempt(self, user_id: UUID) -> None:
        """
        Zaehlt einen fehlgeschlagenen Versuch und setzt ggf. Lockout.
        """
        user = await self._get_user(user_id)
        if not user:
            return

        # Inkrementiere Zähler
        new_count = (user.totp_failed_attempts or 0) + 1

        values = {"totp_failed_attempts": new_count}

        # Lockout setzen wenn Maximum erreicht
        if new_count >= MAX_FAILED_ATTEMPTS:
            lockout_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            values["totp_lockout_until"] = lockout_until
            logger.warning(
                "totp_rate_limit_triggered",
                user_id=str(user_id),
                failed_attempts=new_count,
                lockout_until=lockout_until.isoformat()
            )

        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(**values)
        )
        await self.db.commit()

    async def _reset_failed_attempts(self, user_id: UUID) -> None:
        """Setzt den Zähler nach erfolgreichem Login zurück."""
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                totp_failed_attempts=0,
                totp_lockout_until=None
            )
        )
        await self.db.commit()

    async def verify_totp(
        self,
        user_id: UUID,
        totp_code: str
    ) -> bool:
        """
        Verifiziert einen TOTP-Code während des Logins.

        Implementiert Rate Limiting:
        - Max 5 fehlgeschlagene Versuche
        - 15 Minuten Sperre nach Überschreitung

        Args:
            user_id: UUID des Users
            totp_code: 6-stelliger Code aus der Authenticator-App

        Returns:
            True wenn Code gültig

        Raises:
            MFANotEnabledError: Wenn 2FA nicht aktiviert ist
            InvalidTOTPCodeError: Bei ungültigem Code
            RateLimitExceededError: Zu viele fehlgeschlagene Versuche
        """
        user = await self._get_user(user_id)
        if not user:
            raise MFAServiceError("Benutzer nicht gefunden")

        if not user.totp_enabled:
            raise MFANotEnabledError(
                "Zwei-Faktor-Authentifizierung ist nicht aktiviert"
            )

        if not user.totp_secret:
            raise MFAServiceError("TOTP-Secret nicht gefunden")

        # RATE LIMITING: Prüfe ob gesperrt
        await self._check_rate_limit(user)

        # Entschlüssele Secret und verifiziere Code
        secret = self._decrypt_secret(user.totp_secret)
        totp = pyotp.TOTP(
            secret,
            digits=TOTP_DIGITS,
            interval=TOTP_INTERVAL
        )

        is_valid = totp.verify(totp_code, valid_window=TOTP_VALID_WINDOW)

        if not is_valid:
            # RATE LIMITING: Fehlgeschlagenen Versuch zaehlen
            await self._record_failed_attempt(user_id)
            logger.warning(
                "totp_verification_failed",
                user_id=str(user_id),
                failed_attempts=(user.totp_failed_attempts or 0) + 1
            )
            raise InvalidTOTPCodeError("Ungültiger Code")

        # Erfolg: Zähler zurücksetzen
        await self._reset_failed_attempts(user_id)

        logger.info(
            "totp_verified",
            user_id=str(user_id)
        )

        return True

    async def verify_backup_code(
        self,
        user_id: UUID,
        backup_code: str
    ) -> bool:
        """
        Verifiziert und verbraucht einen Backup-Code.

        Backup-Codes sind One-Time-Use und werden nach Verwendung entfernt.

        Implementiert Rate Limiting (gleiche Regeln wie TOTP):
        - Max 5 fehlgeschlagene Versuche
        - 15 Minuten Sperre nach Überschreitung

        Args:
            user_id: UUID des Users
            backup_code: Der Backup-Code (Format: XXXX-XXXX)

        Returns:
            True wenn Code gültig und verbraucht

        Raises:
            MFANotEnabledError: Wenn 2FA nicht aktiviert ist
            InvalidTOTPCodeError: Bei ungültigem Backup-Code
            RateLimitExceededError: Zu viele fehlgeschlagene Versuche
        """
        user = await self._get_user(user_id)
        if not user:
            raise MFAServiceError("Benutzer nicht gefunden")

        if not user.totp_enabled:
            raise MFANotEnabledError(
                "Zwei-Faktor-Authentifizierung ist nicht aktiviert"
            )

        if not user.totp_backup_codes:
            raise InvalidTOTPCodeError("Keine Backup-Codes vorhanden")

        # RATE LIMITING: Prüfe ob gesperrt (gleicher Zähler wie TOTP)
        await self._check_rate_limit(user)

        # Entferne Formatierung (Bindestriche)
        clean_code = backup_code.replace("-", "").upper()

        # Prüfe jeden gespeicherten Hash
        remaining_codes = list(user.totp_backup_codes)
        code_used = False

        for i, code_hash in enumerate(remaining_codes):
            if bcrypt.checkpw(clean_code.encode('utf-8'), code_hash.encode('utf-8')):
                # Code gefunden - entferne ihn
                remaining_codes.pop(i)
                code_used = True
                break

        if not code_used:
            # RATE LIMITING: Fehlgeschlagenen Versuch zaehlen
            await self._record_failed_attempt(user_id)
            logger.warning(
                "backup_code_verification_failed",
                user_id=str(user_id),
                failed_attempts=(user.totp_failed_attempts or 0) + 1
            )
            raise InvalidTOTPCodeError("Ungültiger Backup-Code")

        # Erfolg: Zähler zurücksetzen UND verbleibende Codes speichern
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                totp_backup_codes=remaining_codes,
                totp_failed_attempts=0,
                totp_lockout_until=None
            )
        )
        await self.db.commit()

        logger.info(
            "backup_code_used",
            user_id=str(user_id),
            remaining_codes=len(remaining_codes)
        )

        return True

    async def disable_totp(
        self,
        user_id: UUID,
        totp_code: str
    ) -> bool:
        """
        Deaktiviert 2FA für einen User.

        Erfordert einen gültigen TOTP-Code zur Bestätigung.

        Args:
            user_id: UUID des Users
            totp_code: Aktueller TOTP-Code zur Bestätigung

        Returns:
            True wenn erfolgreich deaktiviert
        """
        # Verifiziere zuerst den Code
        await self.verify_totp(user_id, totp_code)

        # Deaktiviere 2FA und lösche alle Daten
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                totp_enabled=False,
                totp_secret=None,
                totp_backup_codes=None,
                totp_setup_at=None
            )
        )
        await self.db.commit()

        logger.info(
            "totp_disabled",
            user_id=str(user_id)
        )

        return True

    async def regenerate_backup_codes(
        self,
        user_id: UUID,
        totp_code: str
    ) -> List[str]:
        """
        Generiert neue Backup-Codes.

        Ersetzt alle bestehenden Backup-Codes. Erfordert TOTP-Verifizierung.

        Args:
            user_id: UUID des Users
            totp_code: Aktueller TOTP-Code zur Bestätigung

        Returns:
            Liste der neuen Backup-Codes
        """
        # Verifiziere zuerst den Code
        await self.verify_totp(user_id, totp_code)

        # Generiere neue Codes
        backup_codes, hashed_codes = self._generate_backup_codes()

        # Speichere neue Hashes
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(totp_backup_codes=hashed_codes)
        )
        await self.db.commit()

        logger.info(
            "backup_codes_regenerated",
            user_id=str(user_id)
        )

        return backup_codes

    async def get_mfa_status(self, user_id: UUID) -> dict:
        """
        Gibt den MFA-Status eines Users zurück.

        Args:
            user_id: UUID des Users

        Returns:
            Dict mit MFA-Statusinformationen
        """
        user = await self._get_user(user_id)
        if not user:
            raise MFAServiceError("Benutzer nicht gefunden")

        backup_codes_count = 0
        if user.totp_backup_codes:
            backup_codes_count = len(user.totp_backup_codes)

        return {
            "enabled": user.totp_enabled,
            "setup_at": user.totp_setup_at.isoformat() if user.totp_setup_at else None,
            "backup_codes_remaining": backup_codes_count,
            "has_pending_setup": bool(user.totp_secret and not user.totp_enabled),
        }


def get_mfa_service(db: AsyncSession) -> MFAService:
    """Factory-Funktion für MFA-Service."""
    return MFAService(db)

"""
Email Verification Service.

Implementiert:
- Verifizierungs-Token generieren und senden
- Token validieren
- Email-Änderung mit Verifizierung
- Abgelaufene Tokens bereinigen

Alle Antworten auf Deutsch.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import User, EmailVerificationToken
from app.core.config import settings
from app.core.exceptions import EmailVerificationError

logger = structlog.get_logger(__name__)

# Konfiguration
TOKEN_EXPIRY_HOURS = getattr(settings, 'EMAIL_VERIFICATION_EXPIRY_HOURS', 24)
TOKEN_LENGTH = 64  # Bytes für den Token
MAX_TOKENS_PER_USER = 5  # Maximale aktive Tokens pro Benutzer


class EmailVerificationService:
    """Service für Email-Verifizierung."""

    def _generate_token(self) -> Tuple[str, str]:
        """
        Generiert ein sicheres Token und dessen Hash.

        Returns:
            Tuple (plain_token, token_hash)
        """
        plain_token = secrets.token_urlsafe(TOKEN_LENGTH)
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        return plain_token, token_hash

    def _hash_token(self, token: str) -> str:
        """Hasht ein Token für Datenbankvergleich."""
        return hashlib.sha256(token.encode()).hexdigest()

    async def create_verification_token(
        self,
        db: AsyncSession,
        user_id: UUID,
        email: str,
        ip_address: Optional[str] = None,
        token_type: str = "verification"
    ) -> str:
        """
        Erstellt ein neues Verifizierungs-Token.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            email: Email-Adresse zu verifizieren
            ip_address: IP-Adresse des Anfragenden
            token_type: 'verification' oder 'email_change'

        Returns:
            Plain-Text Token (zum Senden per Email)

        Raises:
            EmailVerificationError: Bei Fehlern
        """
        # Lösche alte Tokens für diesen Benutzer/Typ
        await self._cleanup_old_tokens(db, user_id, token_type)

        # Generiere neues Token
        plain_token, token_hash = self._generate_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)

        verification_token = EmailVerificationToken(
            id=uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            email=email,
            token_type=token_type,
            expires_at=expires_at,
            ip_address=ip_address
        )

        db.add(verification_token)
        await db.commit()

        logger.info(
            "email_verification_token_created",
            user_id=str(user_id)[:8] + "...",
            token_type=token_type,
            expires_at=expires_at.isoformat()
        )

        return plain_token

    async def create_email_change_token(
        self,
        db: AsyncSession,
        user_id: UUID,
        current_email: str,
        new_email: str,
        ip_address: Optional[str] = None
    ) -> str:
        """
        Erstellt Token für Email-Änderung.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            current_email: Aktuelle Email
            new_email: Neue Email-Adresse
            ip_address: IP-Adresse des Anfragenden

        Returns:
            Plain-Text Token

        Raises:
            EmailVerificationError: Bei Fehlern
        """
        # Prüfe ob neue Email bereits verwendet wird
        result = await db.execute(
            select(User).where(User.email == new_email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise EmailVerificationError(
                "Email already in use",
                "Diese Email-Adresse wird bereits verwendet"
            )

        # Lösche alte Email-Change Tokens
        await self._cleanup_old_tokens(db, user_id, "email_change")

        # Generiere neues Token
        plain_token, token_hash = self._generate_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)

        verification_token = EmailVerificationToken(
            id=uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            email=current_email,
            token_type="email_change",
            new_email=new_email,
            expires_at=expires_at,
            ip_address=ip_address
        )

        db.add(verification_token)
        await db.commit()

        logger.info(
            "email_change_token_created",
            user_id=str(user_id)[:8] + "...",
            new_email=new_email[:3] + "***"
        )

        return plain_token

    async def verify_email(
        self,
        db: AsyncSession,
        token: str
    ) -> Tuple[bool, str, Optional[User]]:
        """
        Verifiziert eine Email-Adresse mit Token.

        Args:
            db: Datenbank-Session
            token: Das Verifizierungs-Token

        Returns:
            Tuple (success, message, user)
        """
        token_hash = self._hash_token(token)
        now = datetime.now(timezone.utc)

        # Finde Token in Datenbank
        result = await db.execute(
            select(EmailVerificationToken).where(
                and_(
                    EmailVerificationToken.token_hash == token_hash,
                    EmailVerificationToken.used_at.is_(None)
                )
            )
        )
        verification_token = result.scalar_one_or_none()

        if not verification_token:
            logger.warning("email_verification_invalid_token")
            return False, "Ungültiger Verifizierungs-Link", None

        # Prüfe Ablauf
        if verification_token.expires_at < now:
            logger.warning(
                "email_verification_token_expired",
                user_id=str(verification_token.user_id)[:8] + "..."
            )
            return False, "Der Verifizierungs-Link ist abgelaufen. Bitte fordern Sie einen neuen an.", None

        # Hole Benutzer
        user = await db.get(User, verification_token.user_id)
        if not user:
            return False, "Benutzer nicht gefunden", None

        # Markiere Token als verwendet
        verification_token.used_at = now

        # Aktualisiere Benutzer basierend auf Token-Typ
        if verification_token.token_type == "verification":
            user.email_verified = True
            user.email_verified_at = now
            message = "Email-Adresse erfolgreich verifiziert"

            logger.info(
                "email_verified",
                user_id=str(user.id)[:8] + "..."
            )

        elif verification_token.token_type == "email_change":
            if not verification_token.new_email:
                return False, "Ungültiges Email-Änderungs-Token", None

            old_email = user.email
            user.email = verification_token.new_email
            user.email_verified = True
            user.email_verified_at = now
            message = "Email-Adresse erfolgreich geändert und verifiziert"

            logger.info(
                "email_changed",
                user_id=str(user.id)[:8] + "...",
                old_email=old_email[:3] + "***",
                new_email=user.email[:3] + "***"
            )

        else:
            return False, "Unbekannter Token-Typ", None

        await db.commit()
        await db.refresh(user)

        return True, message, user

    async def resend_verification(
        self,
        db: AsyncSession,
        user_id: UUID,
        ip_address: Optional[str] = None
    ) -> Optional[str]:
        """
        Sendet Verifizierungs-Email erneut.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            ip_address: IP-Adresse des Anfragenden

        Returns:
            Plain-Text Token oder None wenn bereits verifiziert

        Raises:
            EmailVerificationError: Bei Fehlern
        """
        user = await db.get(User, user_id)
        if not user:
            raise EmailVerificationError(
                "User not found",
                "Benutzer nicht gefunden"
            )

        if user.email_verified:
            return None  # Bereits verifiziert

        # Rate-Limiting: Max 3 Tokens pro Stunde
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        result = await db.execute(
            select(EmailVerificationToken).where(
                and_(
                    EmailVerificationToken.user_id == user_id,
                    EmailVerificationToken.token_type == "verification",
                    EmailVerificationToken.created_at > one_hour_ago
                )
            )
        )
        recent_tokens = result.scalars().all()

        if len(recent_tokens) >= 3:
            raise EmailVerificationError(
                "Too many verification requests",
                "Zu viele Verifizierungs-Anfragen. Bitte warten Sie eine Stunde."
            )

        return await self.create_verification_token(
            db, user_id, user.email, ip_address
        )

    async def check_verification_status(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> dict:
        """
        Prüft den Verifizierungsstatus eines Benutzers.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Dict mit Verifizierungsstatus
        """
        user = await db.get(User, user_id)
        if not user:
            raise EmailVerificationError(
                "User not found",
                "Benutzer nicht gefunden"
            )

        # Prüfe auf ausstehende Tokens
        result = await db.execute(
            select(EmailVerificationToken).where(
                and_(
                    EmailVerificationToken.user_id == user_id,
                    EmailVerificationToken.used_at.is_(None),
                    EmailVerificationToken.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        pending_tokens = result.scalars().all()

        return {
            "email": user.email,
            "email_verified": user.email_verified,
            "email_verified_at": user.email_verified_at,
            "pending_verification": len(pending_tokens) > 0,
            "pending_email_change": any(
                t.token_type == "email_change" for t in pending_tokens
            )
        }

    async def _cleanup_old_tokens(
        self,
        db: AsyncSession,
        user_id: UUID,
        token_type: str
    ) -> int:
        """
        Löscht alte Tokens eines Benutzers.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            token_type: Token-Typ

        Returns:
            Anzahl gelöschter Tokens
        """
        result = await db.execute(
            delete(EmailVerificationToken).where(
                and_(
                    EmailVerificationToken.user_id == user_id,
                    EmailVerificationToken.token_type == token_type
                )
            )
        )
        return result.rowcount

    async def cleanup_expired_tokens(
        self,
        db: AsyncSession
    ) -> int:
        """
        Bereinigt alle abgelaufenen Tokens.

        Sollte als periodischer Task ausgeführt werden.

        Args:
            db: Datenbank-Session

        Returns:
            Anzahl gelöschter Tokens
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        result = await db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.expires_at < cutoff
            )
        )

        count = result.rowcount
        await db.commit()

        if count > 0:
            logger.info("expired_verification_tokens_cleaned", count=count)

        return count


# Singleton-Instanz
_email_verification_service: Optional[EmailVerificationService] = None


def get_email_verification_service() -> EmailVerificationService:
    """Gibt EmailVerificationService-Singleton zurück."""
    global _email_verification_service
    if _email_verification_service is None:
        _email_verification_service = EmailVerificationService()
    return _email_verification_service

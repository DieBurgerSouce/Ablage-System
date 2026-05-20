"""
Password Reset Service.

Implementiert sicheren Password-Reset-Flow gemäß OWASP-Empfehlungen:
- Sichere Token-Generierung mit secrets
- Token-Hashing in Datenbank (kein Klartext)
- Zeitlich begrenzte Gültigkeit (1 Stunde)
- Rate-Limiting für Anfragen
- Email-basierte Verifizierung

Art. 32 DSGVO - Sicherheit der Verarbeitung
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
import secrets
import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_
from pydantic import EmailStr
import structlog

from app.db.models import User, PasswordResetToken
from app.services.notification_service import NotificationService
from app.core.config import settings
from app.core.security import get_password_hash
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Token-Konfiguration
TOKEN_BYTES = 32  # 256-bit Token
TOKEN_EXPIRY_HOURS = 1
MAX_ACTIVE_TOKENS_PER_USER = 3


class PasswordResetService:
    """Service für Password-Reset-Operationen."""

    @staticmethod
    def _generate_token() -> str:
        """
        Generiert ein sicheres Reset-Token.

        Verwendet secrets.token_urlsafe für kryptografisch sichere Token.
        """
        return secrets.token_urlsafe(TOKEN_BYTES)

    @staticmethod
    def _hash_token(token: str) -> str:
        """
        Hasht ein Token für sichere Speicherung.

        Nur der Hash wird in der Datenbank gespeichert.
        Das Original-Token wird per Email gesendet.
        """
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @classmethod
    async def request_password_reset(
        cls,
        db: AsyncSession,
        email: str,
        notification_service: Optional[NotificationService] = None,
    ) -> Tuple[bool, str]:
        """
        Initiiert Password-Reset-Anfrage.

        Args:
            db: Database session
            email: E-Mail-Adresse des Benutzers
            notification_service: Service für E-Mail-Versand

        Returns:
            Tuple[bool, str]: (Erfolg, Nachricht)

        Sicherheitshinweise:
        - Gibt immer die gleiche Nachricht zurück (Enumeration-Schutz)
        - Prüft Rate-Limiting intern
        - Token wird nur per E-Mail gesendet, nie in Response
        """
        # Standard-Antwort (immer gleich für Enumeration-Schutz)
        standard_message = (
            "Falls ein Konto mit dieser E-Mail existiert, "
            "wurde eine E-Mail mit Anweisungen zum Zurücksetzen gesendet."
        )

        try:
            # Benutzer suchen
            result = await db.execute(
                select(User).where(
                    and_(
                        User.email == email.lower(),
                        User.is_active == True
                    )
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                # Benutzer nicht gefunden - gleiche Antwort (Enumeration-Schutz)
                logger.info("password_reset_user_not_found", email=email[:3] + "***")
                return True, standard_message

            # Prüfe ob zu viele aktive Tokens existieren
            active_tokens = await db.execute(
                select(PasswordResetToken).where(
                    and_(
                        PasswordResetToken.user_id == user.id,
                        PasswordResetToken.used_at == None,
                        PasswordResetToken.expires_at > datetime.now(timezone.utc)
                    )
                )
            )
            token_count = len(active_tokens.scalars().all())

            if token_count >= MAX_ACTIVE_TOKENS_PER_USER:
                logger.warning(
                    "password_reset_rate_limit",
                    user_id=str(user.id),
                    active_tokens=token_count
                )
                # Trotzdem Standard-Antwort
                return True, standard_message

            # Generiere Token
            raw_token = cls._generate_token()
            hashed_token = cls._hash_token(raw_token)

            # Erstelle Token-Eintrag
            reset_token = PasswordResetToken(
                user_id=user.id,
                token_hash=hashed_token,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
            )
            db.add(reset_token)
            await db.commit()

            # Sende E-Mail
            if notification_service:
                reset_url = f"{settings.API_HOST}:{settings.API_PORT}/api/v1/auth/reset-password?token={raw_token}"

                email_sent = await notification_service.send_email(
                    to_email=user.email,
                    subject="Passwort zurücksetzen - Ablage-System",
                    body=f"""
Guten Tag {user.full_name or user.username},

Sie haben angefordert, Ihr Passwort für das Ablage-System zurückzusetzen.

Klicken Sie auf folgenden Link, um Ihr Passwort zurückzusetzen:
{reset_url}

Dieser Link ist 1 Stunde gültig.

Falls Sie diese Anfrage nicht gestellt haben, können Sie diese E-Mail ignorieren.
Ihr Passwort wird nicht geändert, solange Sie den Link nicht nutzen.

Mit freundlichen Grüßen,
Ablage-System Team

---
Diese E-Mail wurde automatisch generiert. Bitte antworten Sie nicht darauf.
                    """.strip(),
                    html_body=f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #333;">Passwort zurücksetzen</h2>
    <p>Guten Tag {user.full_name or user.username},</p>
    <p>Sie haben angefordert, Ihr Passwort für das <strong>Ablage-System</strong> zurückzusetzen.</p>
    <p style="margin: 30px 0;">
        <a href="{reset_url}"
           style="background-color: #007bff; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 4px; display: inline-block;">
            Passwort zurücksetzen
        </a>
    </p>
    <p><small>Dieser Link ist <strong>1 Stunde</strong> gültig.</small></p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <p style="color: #666; font-size: 12px;">
        Falls Sie diese Anfrage nicht gestellt haben, können Sie diese E-Mail ignorieren.<br>
        Ihr Passwort wird nicht geändert, solange Sie den Link nicht nutzen.
    </p>
</body>
</html>
                    """.strip()
                )

                if email_sent:
                    logger.info(
                        "password_reset_email_sent",
                        user_id=str(user.id),
                        token_id=str(reset_token.id),
                    )
                else:
                    logger.error(
                        "password_reset_email_failed",
                        user_id=str(user.id),
                    )
            else:
                logger.warning(
                    "password_reset_no_notification_service",
                    user_id=str(user.id),
                )

            return True, standard_message

        except Exception as e:
            logger.error("password_reset_request_failed", **safe_error_log(e))
            await db.rollback()
            # Trotzdem Standard-Antwort (keine Fehlerdetails preisgeben)
            return True, standard_message

    @classmethod
    async def validate_reset_token(
        cls,
        db: AsyncSession,
        token: str,
    ) -> Tuple[bool, Optional[User], str]:
        """
        Validiert ein Reset-Token.

        Args:
            db: Database session
            token: Das zu validierende Token (Klartext)

        Returns:
            Tuple[bool, Optional[User], str]: (Gültig, Benutzer, Nachricht)
        """
        try:
            hashed_token = cls._hash_token(token)

            result = await db.execute(
                select(PasswordResetToken).where(
                    and_(
                        PasswordResetToken.token_hash == hashed_token,
                        PasswordResetToken.used_at == None,
                        PasswordResetToken.expires_at > datetime.now(timezone.utc)
                    )
                )
            )
            reset_token = result.scalar_one_or_none()

            if not reset_token:
                logger.warning("password_reset_invalid_token")
                return False, None, "Ungültiger oder abgelaufener Link"

            # Hole Benutzer
            user_result = await db.execute(
                select(User).where(User.id == reset_token.user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user or not user.is_active:
                logger.warning(
                    "password_reset_user_invalid",
                    token_id=str(reset_token.id),
                )
                return False, None, "Benutzer nicht gefunden oder deaktiviert"

            return True, user, "Token gültig"

        except Exception as e:
            logger.error("password_reset_validation_failed", **safe_error_log(e))
            return False, None, "Validierung fehlgeschlagen"

    @classmethod
    async def reset_password(
        cls,
        db: AsyncSession,
        token: str,
        new_password: str,
        notification_service: Optional[NotificationService] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Setzt das Passwort mit einem gültigen Token zurück.

        Args:
            db: Database session
            token: Das Reset-Token (Klartext)
            new_password: Das neue Passwort
            notification_service: Service für Bestätigungs-Email
            ip_address: IP-Adresse für Sicherheits-Email
            user_agent: User-Agent für Sicherheits-Email

        Returns:
            Tuple[bool, str]: (Erfolg, Nachricht)
        """
        try:
            # Validiere Token
            is_valid, user, message = await cls.validate_reset_token(db, token)

            if not is_valid or not user:
                return False, message

            hashed_token = cls._hash_token(token)

            # Hash neues Passwort
            hashed_password = get_password_hash(new_password)

            # Update Benutzer-Passwort
            await db.execute(
                update(User)
                .where(User.id == user.id)
                .values(
                    hashed_password=hashed_password,
                    password_reset_required=False,
                    updated_at=datetime.now(timezone.utc)
                )
            )

            # Markiere Token als verwendet
            await db.execute(
                update(PasswordResetToken)
                .where(PasswordResetToken.token_hash == hashed_token)
                .values(used_at=datetime.now(timezone.utc))
            )

            # Invalidiere alle anderen aktiven Tokens des Benutzers
            await db.execute(
                update(PasswordResetToken)
                .where(
                    and_(
                        PasswordResetToken.user_id == user.id,
                        PasswordResetToken.used_at == None,
                        PasswordResetToken.token_hash != hashed_token
                    )
                )
                .values(used_at=datetime.now(timezone.utc))
            )

            await db.commit()

            logger.info(
                "password_reset_successful",
                user_id=str(user.id),
            )

            # Sende Bestätigungs-Email (Sicherheit: Benutzer über Änderung informieren)
            if notification_service and user.email:
                try:
                    timestamp = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")

                    # Plain text Email
                    body = f"""
Guten Tag {user.full_name or user.username},

Ihr Passwort für das Ablage-System wurde erfolgreich geändert.

Zeitpunkt: {timestamp}
IP-Adresse: {ip_address or "Unbekannt"}
Gerät: {user_agent or "Unbekannt"}

Falls Sie diese Änderung NICHT vorgenommen haben, ergreifen Sie bitte sofort folgende Maßnahmen:
1. Kontaktieren Sie umgehend den Administrator
2. Versuchen Sie, Ihr Passwort erneut zurückzusetzen
3. Überprüfen Sie Ihre anderen Konten auf verdächtige Aktivitäten

Mit freundlichen Grüßen,
Ablage-System Team

---
Diese E-Mail wurde automatisch generiert. Bitte antworten Sie nicht darauf.
                    """.strip()

                    # HTML Email
                    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #333;">Passwort erfolgreich geändert</h2>
    <p>Guten Tag {user.full_name or user.username},</p>
    <p>Ihr Passwort für das <strong>Ablage-System</strong> wurde erfolgreich geändert.</p>

    <table style="background-color: #f5f5f5; padding: 15px; border-radius: 4px; width: 100%;">
        <tr><td><strong>Zeitpunkt:</strong></td><td>{timestamp}</td></tr>
        <tr><td><strong>IP-Adresse:</strong></td><td>{ip_address or "Unbekannt"}</td></tr>
        <tr><td><strong>Gerät:</strong></td><td>{user_agent or "Unbekannt"}</td></tr>
    </table>

    <div style="background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 4px;">
        <strong style="color: #856404;">⚠️ Wichtig:</strong>
        <p style="color: #856404; margin: 10px 0 0 0;">
            Falls Sie diese Änderung <strong>NICHT</strong> vorgenommen haben, ergreifen Sie bitte sofort folgende Maßnahmen:
        </p>
        <ol style="color: #856404;">
            <li>Kontaktieren Sie umgehend den Administrator</li>
            <li>Versuchen Sie, Ihr Passwort erneut zurückzusetzen</li>
            <li>Überprüfen Sie Ihre anderen Konten auf verdächtige Aktivitäten</li>
        </ol>
    </div>

    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <p style="color: #666; font-size: 12px;">
        Diese E-Mail wurde automatisch generiert. Bitte antworten Sie nicht darauf.
    </p>
</body>
</html>
                    """.strip()

                    email_sent = await notification_service.send_email(
                        to_email=user.email,
                        subject="Passwort erfolgreich geändert - Ablage-System",
                        body=body,
                        html_body=html_body,
                    )

                    if email_sent:
                        logger.info(
                            "password_reset_confirmation_sent",
                            user_id=str(user.id),
                        )
                    else:
                        logger.warning(
                            "password_reset_confirmation_email_failed",
                            user_id=str(user.id),
                        )
                except Exception as email_error:
                    # Email-Fehler sollte Reset nicht rückgängig machen
                    logger.error(
                        "password_reset_confirmation_email_error",
                        user_id=str(user.id),
                        error=str(email_error),
                    )

            return True, "Passwort erfolgreich zurückgesetzt"

        except Exception as e:
            logger.error("password_reset_failed", **safe_error_log(e))
            await db.rollback()
            return False, "Passwort konnte nicht zurückgesetzt werden"

    @classmethod
    async def cleanup_expired_tokens(cls, db: AsyncSession) -> int:
        """
        Entfernt abgelaufene Tokens aus der Datenbank.

        Sollte regelmäßig durch Celery-Task ausgeführt werden.

        Returns:
            Anzahl der gelöschten Tokens
        """
        try:
            # Lösche Tokens die älter als 24 Stunden sind (auch genutzte)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

            result = await db.execute(
                delete(PasswordResetToken).where(
                    PasswordResetToken.created_at < cutoff
                )
            )
            await db.commit()

            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(
                    "password_reset_tokens_cleaned",
                    deleted_count=deleted_count,
                )

            return deleted_count

        except Exception as e:
            logger.error("password_reset_cleanup_failed", **safe_error_log(e))
            await db.rollback()
            return 0


# Singleton-Instanz
_password_reset_service: Optional[PasswordResetService] = None


def get_password_reset_service() -> PasswordResetService:
    """Get Password Reset Service instance."""
    global _password_reset_service
    if _password_reset_service is None:
        _password_reset_service = PasswordResetService()
    return _password_reset_service

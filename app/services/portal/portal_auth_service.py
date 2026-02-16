"""
Portal-Authentifizierungsservice.

Separate Authentifizierung für Kunden/Lieferanten-Portal.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from uuid import UUID
import secrets
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from passlib.context import CryptContext
import structlog

from app.db.models_portal import (
    PortalUser, PortalSession, PortalUserStatus
)
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token-Konstanten
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
INVITATION_EXPIRE_DAYS = 7
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


class PortalAuthError(Exception):
    """Basis-Exception für Portal-Auth-Fehler."""
    pass


class PortalUserNotFoundError(PortalAuthError):
    """Portal-Benutzer nicht gefunden."""
    pass


class PortalUserInactiveError(PortalAuthError):
    """Portal-Benutzer ist nicht aktiv."""
    pass


class InvalidPortalCredentialsError(PortalAuthError):
    """Ungültige Anmeldedaten."""
    pass


class PortalAccountLockedError(PortalAuthError):
    """Account ist gesperrt."""
    pass


class PortalAuthService:
    """Service für Portal-Authentifizierung."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _hash_token(self, token: str) -> str:
        """Hash ein Token für sichere Speicherung."""
        return hashlib.sha256(token.encode()).hexdigest()

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verifiziere Passwort gegen Hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def _hash_password(self, password: str) -> str:
        """Hash ein Passwort."""
        return pwd_context.hash(password)

    async def create_invitation(
        self,
        entity_id: UUID,
        company_id: UUID,
        email: str,
        invited_by_id: UUID,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        permissions: Optional[dict] = None,
    ) -> Tuple[PortalUser, str]:
        """
        Erstelle eine Einladung für einen Portal-Benutzer.

        Returns:
            Tuple aus PortalUser und Einladungs-Token (Klartext).
        """
        # Prüfe ob bereits eingeladen
        existing = await self.db.execute(
            select(PortalUser).where(
                and_(
                    PortalUser.company_id == company_id,
                    PortalUser.email == email.lower()
                )
            )
        )
        if existing.scalar_one_or_none():
            raise PortalAuthError("E-Mail-Adresse bereits registriert")

        # Generiere Einladungs-Token
        invitation_token = secrets.token_urlsafe(32)

        # Default-Berechtigungen
        perms = permissions or {}

        portal_user = PortalUser(
            entity_id=entity_id,
            company_id=company_id,
            email=email.lower(),
            hashed_password="",  # Wird bei Aktivierung gesetzt
            first_name=first_name,
            last_name=last_name,
            status=PortalUserStatus.PENDING,
            can_view_invoices=perms.get("can_view_invoices", True),
            can_confirm_payments=perms.get("can_confirm_payments", True),
            can_submit_complaints=perms.get("can_submit_complaints", True),
            can_upload_documents=perms.get("can_upload_documents", True),
            can_view_all_entity_data=perms.get("can_view_all_entity_data", False),
            invitation_token=self._hash_token(invitation_token),
            invitation_sent_at=datetime.now(timezone.utc),
            invitation_expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_EXPIRE_DAYS),
            invited_by_id=invited_by_id,
        )

        self.db.add(portal_user)
        await self.db.commit()
        await self.db.refresh(portal_user)

        logger.info(
            "portal_invitation_created",
            portal_user_id=str(portal_user.id),
            entity_id=str(entity_id),
        )

        return portal_user, invitation_token

    async def activate_account(
        self,
        invitation_token: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> PortalUser:
        """
        Aktiviere einen Portal-Account mit Einladungs-Token.
        """
        token_hash = self._hash_token(invitation_token)

        result = await self.db.execute(
            select(PortalUser).where(
                and_(
                    PortalUser.invitation_token == token_hash,
                    PortalUser.status == PortalUserStatus.PENDING
                )
            )
        )
        portal_user = result.scalar_one_or_none()

        if not portal_user:
            raise PortalUserNotFoundError("Ungültige oder abgelaufene Einladung")

        # Prüfe Ablauf
        if portal_user.invitation_expires_at and portal_user.invitation_expires_at < datetime.now(timezone.utc):
            raise PortalAuthError("Einladung ist abgelaufen")

        # Aktiviere Account
        portal_user.hashed_password = self._hash_password(password)
        portal_user.status = PortalUserStatus.ACTIVE
        portal_user.invitation_token = None
        portal_user.password_changed_at = datetime.now(timezone.utc)

        if first_name:
            portal_user.first_name = first_name
        if last_name:
            portal_user.last_name = last_name

        await self.db.commit()
        await self.db.refresh(portal_user)

        logger.info(
            "portal_account_activated",
            portal_user_id=str(portal_user.id),
        )

        return portal_user

    async def authenticate(
        self,
        email: str,
        password: str,
        company_id: UUID,
    ) -> PortalUser:
        """
        Authentifiziere einen Portal-Benutzer.
        """
        result = await self.db.execute(
            select(PortalUser).where(
                and_(
                    PortalUser.company_id == company_id,
                    PortalUser.email == email.lower()
                )
            )
        )
        portal_user = result.scalar_one_or_none()

        if not portal_user:
            raise PortalUserNotFoundError("Benutzer nicht gefunden")

        # Prüfe Lock
        if portal_user.locked_until and portal_user.locked_until > datetime.now(timezone.utc):
            remaining = (portal_user.locked_until - datetime.now(timezone.utc)).seconds // 60
            raise PortalAccountLockedError(
                f"Account ist gesperrt. Bitte versuchen Sie es in {remaining} Minuten erneut."
            )

        # Prüfe Status
        if portal_user.status != PortalUserStatus.ACTIVE:
            raise PortalUserInactiveError("Account ist nicht aktiv")

        # Verifiziere Passwort
        if not self._verify_password(password, portal_user.hashed_password):
            # Erhöhe Fehlversuche
            portal_user.failed_login_attempts += 1

            if portal_user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                portal_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                logger.warning(
                    "portal_account_locked",
                    portal_user_id=str(portal_user.id),
                    failed_attempts=portal_user.failed_login_attempts,
                )

            await self.db.commit()
            raise InvalidPortalCredentialsError("Ungültige Anmeldedaten")

        # Reset bei erfolgreichem Login
        portal_user.failed_login_attempts = 0
        portal_user.locked_until = None
        portal_user.last_login_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(portal_user)

        logger.info(
            "portal_login_success",
            portal_user_id=str(portal_user.id),
        )

        return portal_user

    async def create_session(
        self,
        portal_user_id: UUID,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[str, str, PortalSession]:
        """
        Erstelle eine neue Session für einen Portal-Benutzer.

        Returns:
            Tuple aus Access-Token, Refresh-Token und Session.
        """
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)

        session = PortalSession(
            portal_user_id=portal_user_id,
            session_token_hash=self._hash_token(access_token),
            refresh_token_hash=self._hash_token(refresh_token),
            user_agent=user_agent[:500] if user_agent else None,
            ip_address=ip_address[:45] if ip_address else None,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            refresh_expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )

        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        return access_token, refresh_token, session

    async def validate_session(self, access_token: str) -> Optional[PortalUser]:
        """
        Validiere einen Access-Token und gebe den Benutzer zurück.
        """
        token_hash = self._hash_token(access_token)

        result = await self.db.execute(
            select(PortalSession).where(
                and_(
                    PortalSession.session_token_hash == token_hash,
                    PortalSession.expires_at > datetime.now(timezone.utc),
                    PortalSession.revoked_at.is_(None)
                )
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        # Update last activity
        session.last_activity_at = datetime.now(timezone.utc)
        await self.db.commit()

        # Lade Benutzer
        result = await self.db.execute(
            select(PortalUser).where(
                and_(
                    PortalUser.id == session.portal_user_id,
                    PortalUser.status == PortalUserStatus.ACTIVE
                )
            )
        )
        return result.scalar_one_or_none()

    async def refresh_session(
        self,
        refresh_token: str,
    ) -> Tuple[str, str, PortalSession]:
        """
        Erneuere eine Session mit Refresh-Token.

        Returns:
            Tuple aus neuem Access-Token, neuem Refresh-Token und Session.
        """
        token_hash = self._hash_token(refresh_token)

        result = await self.db.execute(
            select(PortalSession).where(
                and_(
                    PortalSession.refresh_token_hash == token_hash,
                    PortalSession.refresh_expires_at > datetime.now(timezone.utc),
                    PortalSession.revoked_at.is_(None)
                )
            )
        )
        old_session = result.scalar_one_or_none()

        if not old_session:
            raise PortalAuthError("Ungültige oder abgelaufene Session")

        # Revoke alte Session
        old_session.revoked_at = datetime.now(timezone.utc)
        old_session.revoked_reason = "token_refresh"

        # Erstelle neue Session
        return await self.create_session(
            portal_user_id=old_session.portal_user_id,
            user_agent=old_session.user_agent,
            ip_address=old_session.ip_address,
        )

    async def revoke_session(
        self,
        access_token: str,
        reason: str = "user_logout",
    ) -> bool:
        """
        Widerrufe eine Session (Logout).
        """
        token_hash = self._hash_token(access_token)

        result = await self.db.execute(
            select(PortalSession).where(
                PortalSession.session_token_hash == token_hash
            )
        )
        session = result.scalar_one_or_none()

        if session:
            session.revoked_at = datetime.now(timezone.utc)
            session.revoked_reason = reason
            await self.db.commit()
            return True

        return False

    async def revoke_all_sessions(
        self,
        portal_user_id: UUID,
        reason: str = "security_reset",
    ) -> int:
        """
        Widerrufe alle Sessions eines Benutzers.

        Returns:
            Anzahl der widerrufenen Sessions.
        """
        result = await self.db.execute(
            select(PortalSession).where(
                and_(
                    PortalSession.portal_user_id == portal_user_id,
                    PortalSession.revoked_at.is_(None)
                )
            )
        )
        sessions = result.scalars().all()

        count = 0
        for session in sessions:
            session.revoked_at = datetime.now(timezone.utc)
            session.revoked_reason = reason
            count += 1

        await self.db.commit()

        logger.info(
            "portal_all_sessions_revoked",
            portal_user_id=str(portal_user_id),
            count=count,
        )

        return count

    async def change_password(
        self,
        portal_user_id: UUID,
        current_password: str,
        new_password: str,
    ) -> bool:
        """
        Ändere das Passwort eines Portal-Benutzers.
        """
        result = await self.db.execute(
            select(PortalUser).where(PortalUser.id == portal_user_id)
        )
        portal_user = result.scalar_one_or_none()

        if not portal_user:
            raise PortalUserNotFoundError("Benutzer nicht gefunden")

        if not self._verify_password(current_password, portal_user.hashed_password):
            raise InvalidPortalCredentialsError("Aktuelles Passwort ist falsch")

        portal_user.hashed_password = self._hash_password(new_password)
        portal_user.password_changed_at = datetime.now(timezone.utc)

        # Revoke alle bestehenden Sessions
        await self.revoke_all_sessions(portal_user_id, "password_change")

        await self.db.commit()

        logger.info(
            "portal_password_changed",
            portal_user_id=str(portal_user_id),
        )

        return True

    async def get_portal_user_by_id(self, portal_user_id: UUID) -> Optional[PortalUser]:
        """Hole Portal-Benutzer nach ID."""
        result = await self.db.execute(
            select(PortalUser).where(PortalUser.id == portal_user_id)
        )
        return result.scalar_one_or_none()

    async def get_portal_user_by_email(
        self,
        email: str,
        company_id: UUID,
    ) -> Optional[PortalUser]:
        """Hole Portal-Benutzer nach E-Mail."""
        result = await self.db.execute(
            select(PortalUser).where(
                and_(
                    PortalUser.company_id == company_id,
                    PortalUser.email == email.lower()
                )
            )
        )
        return result.scalar_one_or_none()


def get_portal_auth_service(db: AsyncSession) -> PortalAuthService:
    """Factory-Funktion für PortalAuthService."""
    return PortalAuthService(db)

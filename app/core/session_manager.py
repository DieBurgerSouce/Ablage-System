"""
Session Manager - Zentrale Session-Verwaltung.

Implementiert:
- Session-Tracking pro Benutzer
- Geräte-Identifizierung
- Session-Widerruf (einzeln/alle)
- Aktivitäts-Tracking

Alle Antworten auf Deutsch.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from uuid import UUID, uuid4

from sqlalchemy import select, and_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from user_agents import parse as parse_user_agent

from app.db.models import UserSession
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Session-Konfiguration aus Settings
SESSION_EXPIRY_HOURS = settings.SESSION_EXPIRY_HOURS
MAX_SESSIONS_PER_USER = settings.MAX_SESSIONS_PER_USER
SESSION_LIMIT_MODE = settings.SESSION_LIMIT_MODE  # "soft" oder "hard"


class SessionError(Exception):
    """Fehler bei Session-Operationen."""

    def __init__(self, message: str, user_message_de: str):
        super().__init__(message)
        self.user_message_de = user_message_de


class SessionLimitReachedError(SessionError):
    """Fehler wenn Session-Limit erreicht und Hard-Modus aktiv."""

    def __init__(self, current_sessions: int, max_sessions: int):
        super().__init__(
            f"Session limit reached: {current_sessions}/{max_sessions}",
            settings.SESSION_LIMIT_HARD_MESSAGE
        )
        self.current_sessions = current_sessions
        self.max_sessions = max_sessions


class SessionManager:
    """Verwaltet Benutzer-Sessions."""

    async def create_session(
        self,
        db: AsyncSession,
        user_id: UUID,
        token_jti: str,
        ip_address: str,
        user_agent: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Erstellt eine neue Session beim Login.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            token_jti: JWT Token ID (jti claim)
            ip_address: IP-Adresse des Clients
            user_agent: User-Agent String
            location: Optionaler Standort

        Returns:
            Dict mit:
            - session: Erstellte UserSession
            - revoked_sessions: Liste der widerrufenen Session-IDs (bei soft mode)
            - warning: Warnhinweis wenn Sessions widerrufen wurden

        Raises:
            SessionLimitReachedError: Bei Hard-Mode wenn Limit erreicht
            SessionError: Bei anderen Fehlern
        """
        # Prüfe aktuelle Session-Anzahl
        active_sessions = await self.get_active_sessions(db, user_id)
        current_count = len(active_sessions)

        # Hard-Mode: Blockiere wenn Limit erreicht
        if SESSION_LIMIT_MODE == "hard" and current_count >= MAX_SESSIONS_PER_USER:
            logger.warning(
                "session_limit_reached_hard_mode",
                user_id=str(user_id)[:8] + "...",
                current_sessions=current_count,
                max_sessions=MAX_SESSIONS_PER_USER
            )
            raise SessionLimitReachedError(current_count, MAX_SESSIONS_PER_USER)

        # Parse User-Agent für Geräteinformationen
        device_name, device_type = self._parse_device_info(user_agent)

        # Berechne Ablaufzeit
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRY_HOURS)

        # Setze alle anderen Sessions auf is_current=False
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(is_current=False)
        )

        # Erstelle neue Session
        session = UserSession(
            id=uuid4(),
            user_id=user_id,
            token_jti=token_jti,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
            location=location,
            expires_at=expires_at,
            is_current=True,
            revoked=False
        )

        db.add(session)

        # Soft-Mode: Bereinige alte Sessions wenn Maximum überschritten
        revoked_sessions = await self._cleanup_old_sessions(db, user_id)

        await db.commit()
        await db.refresh(session)

        # Log-Info mit Details
        logger.info(
            "session_created",
            user_id=str(user_id)[:8] + "...",
            device_type=device_type,
            ip_address=self._mask_ip(ip_address),
            sessions_revoked=len(revoked_sessions) if revoked_sessions else 0
        )

        # Erstelle Response-Dict
        result: Dict[str, any] = {
            "session": session,
            "revoked_sessions": revoked_sessions,
            "warning": None
        }

        # Setze Warnung wenn Sessions widerrufen wurden
        if revoked_sessions:
            result["warning"] = (
                f"{len(revoked_sessions)} ältere Session(s) wurden automatisch beendet, "
                f"da das Maximum von {MAX_SESSIONS_PER_USER} Sessions erreicht wurde."
            )

        return result

    async def get_active_sessions(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> List[UserSession]:
        """
        Listet alle aktiven Sessions eines Benutzers auf.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Liste aktiver Sessions
        """
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(UserSession)
            .where(
                and_(
                    UserSession.user_id == user_id,
                    UserSession.revoked == False,
                    UserSession.expires_at > now
                )
            )
            .order_by(UserSession.last_activity_at.desc())
        )

        return list(result.scalars().all())

    async def get_session_by_jti(
        self,
        db: AsyncSession,
        token_jti: str
    ) -> Optional[UserSession]:
        """
        Findet Session anhand JWT Token ID.

        Args:
            db: Datenbank-Session
            token_jti: JWT Token ID

        Returns:
            UserSession oder None
        """
        result = await db.execute(
            select(UserSession).where(UserSession.token_jti == token_jti)
        )
        return result.scalar_one_or_none()

    async def is_session_valid(
        self,
        db: AsyncSession,
        token_jti: str
    ) -> bool:
        """
        Prüft ob Session gültig ist (nicht widerrufen, nicht abgelaufen).

        Args:
            db: Datenbank-Session
            token_jti: JWT Token ID

        Returns:
            True wenn Session gültig
        """
        session = await self.get_session_by_jti(db, token_jti)

        if not session:
            return False

        if session.revoked:
            return False

        if session.expires_at < datetime.now(timezone.utc):
            return False

        return True

    async def update_activity(
        self,
        db: AsyncSession,
        token_jti: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Aktualisiert letzten Aktivitätszeitpunkt einer Session.

        Args:
            db: Datenbank-Session
            token_jti: JWT Token ID
            ip_address: Optionale neue IP-Adresse

        Returns:
            True wenn erfolgreich aktualisiert
        """
        now = datetime.now(timezone.utc)

        values: Dict[str, datetime | str] = {"last_activity_at": now}
        if ip_address:
            values["ip_address"] = ip_address

        result = await db.execute(
            update(UserSession)
            .where(
                and_(
                    UserSession.token_jti == token_jti,
                    UserSession.revoked == False
                )
            )
            .values(**values)
        )

        if result.rowcount > 0:
            await db.commit()
            return True

        return False

    async def revoke_session(
        self,
        db: AsyncSession,
        session_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Widerruft eine einzelne Session.

        Args:
            db: Datenbank-Session
            session_id: Session-ID
            user_id: Benutzer-ID (für Berechtigungsprüfung)

        Returns:
            True wenn Session widerrufen wurde

        Raises:
            SessionError: Bei ungültiger Session oder fehlender Berechtigung
        """
        session = await db.get(UserSession, session_id)

        if not session:
            raise SessionError(
                f"Session {session_id} not found",
                "Session nicht gefunden"
            )

        if session.user_id != user_id:
            raise SessionError(
                f"User {user_id} not authorized to revoke session {session_id}",
                "Sie haben keine Berechtigung, diese Session zu beenden"
            )

        if session.revoked:
            raise SessionError(
                f"Session {session_id} already revoked",
                "Session wurde bereits beendet"
            )

        session.revoked = True
        session.revoked_at = datetime.now(timezone.utc)
        session.is_current = False

        await db.commit()

        logger.info(
            "session_revoked",
            session_id=str(session_id)[:8] + "...",
            user_id=str(user_id)[:8] + "..."
        )

        return True

    async def revoke_all_sessions(
        self,
        db: AsyncSession,
        user_id: UUID,
        except_current: bool = False,
        current_jti: Optional[str] = None
    ) -> int:
        """
        Widerruft alle Sessions eines Benutzers.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            except_current: Aktuelle Session ausschließen
            current_jti: JWT Token ID der aktuellen Session

        Returns:
            Anzahl widerrufener Sessions
        """
        now = datetime.now(timezone.utc)

        conditions = [
            UserSession.user_id == user_id,
            UserSession.revoked == False
        ]

        if except_current and current_jti:
            conditions.append(UserSession.token_jti != current_jti)

        result = await db.execute(
            update(UserSession)
            .where(and_(*conditions))
            .values(
                revoked=True,
                revoked_at=now,
                is_current=False
            )
        )

        await db.commit()

        count = result.rowcount

        logger.info(
            "all_sessions_revoked",
            user_id=str(user_id)[:8] + "...",
            count=count,
            except_current=except_current
        )

        return count

    async def revoke_session_by_jti(
        self,
        db: AsyncSession,
        token_jti: str
    ) -> bool:
        """
        Widerruft Session anhand JWT Token ID (für Logout).

        Args:
            db: Datenbank-Session
            token_jti: JWT Token ID

        Returns:
            True wenn Session widerrufen wurde
        """
        now = datetime.now(timezone.utc)

        result = await db.execute(
            update(UserSession)
            .where(
                and_(
                    UserSession.token_jti == token_jti,
                    UserSession.revoked == False
                )
            )
            .values(
                revoked=True,
                revoked_at=now,
                is_current=False
            )
        )

        await db.commit()

        return result.rowcount > 0

    async def cleanup_expired_sessions(
        self,
        db: AsyncSession
    ) -> int:
        """
        Bereinigt abgelaufene Sessions aus der Datenbank.

        Sollte als periodischer Task ausgeführt werden.

        Args:
            db: Datenbank-Session

        Returns:
            Anzahl gelöschter Sessions
        """
        # Lösche Sessions die älter als 30 Tage sind
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = await db.execute(
            delete(UserSession).where(
                UserSession.expires_at < cutoff
            )
        )

        await db.commit()

        count = result.rowcount

        if count > 0:
            logger.info("expired_sessions_cleaned", count=count)

        return count

    async def _cleanup_old_sessions(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> List[UUID]:
        """
        Bereinigt alte Sessions wenn Maximum überschritten.

        Behält die neuesten MAX_SESSIONS_PER_USER Sessions.

        Returns:
            Liste der widerrufenen Session-IDs
        """
        # Hole alle aktiven Sessions sortiert nach Aktivität
        result = await db.execute(
            select(UserSession)
            .where(
                and_(
                    UserSession.user_id == user_id,
                    UserSession.revoked == False
                )
            )
            .order_by(UserSession.last_activity_at.desc())
        )

        sessions = list(result.scalars().all())
        revoked_ids: List[UUID] = []

        # Wenn mehr als Maximum, widerrufe die ältesten
        if len(sessions) > MAX_SESSIONS_PER_USER:
            sessions_to_revoke = sessions[MAX_SESSIONS_PER_USER:]
            now = datetime.now(timezone.utc)

            for old_session in sessions_to_revoke:
                old_session.revoked = True
                old_session.revoked_at = now
                revoked_ids.append(old_session.id)

            logger.info(
                "old_sessions_cleaned",
                user_id=str(user_id)[:8] + "...",
                count=len(sessions_to_revoke),
                session_ids=[str(sid)[:8] for sid in revoked_ids]
            )

        return revoked_ids

    def _parse_device_info(
        self,
        user_agent: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Extrahiert Geräteinformationen aus User-Agent.

        Args:
            user_agent: User-Agent String

        Returns:
            Tuple (device_name, device_type)
        """
        if not user_agent:
            return None, None

        try:
            ua = parse_user_agent(user_agent)

            # Device Name: Browser + OS
            browser = ua.browser.family
            os_name = ua.os.family
            device_name = f"{browser} auf {os_name}"

            # Device Type
            if ua.is_mobile:
                device_type = "mobile"
            elif ua.is_tablet:
                device_type = "tablet"
            elif ua.is_pc:
                device_type = "desktop"
            elif ua.is_bot:
                device_type = "bot"
            else:
                device_type = "unknown"

            return device_name, device_type

        except Exception as e:
            logger.warning("user_agent_parse_failed", error=str(e))
            return None, None

    def _mask_ip(self, ip_address: str) -> str:
        """Maskiert IP-Adresse für Logging (DSGVO)."""
        if "." in ip_address:
            # IPv4: Letztes Oktett maskieren
            parts = ip_address.split(".")
            parts[-1] = "xxx"
            return ".".join(parts)
        elif ":" in ip_address:
            # IPv6: Letzte 4 Gruppen maskieren
            parts = ip_address.split(":")
            return ":".join(parts[:4] + ["xxxx"] * 4)
        return ip_address


# Singleton-Instanz
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Gibt SessionManager-Singleton zurück."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager

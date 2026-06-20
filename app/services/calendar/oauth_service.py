# -*- coding: utf-8 -*-
"""
OAuth2-Service für Kalender-Provider (Google Calendar, Microsoft Outlook).

Folgt dem Pattern aus datev_auth_service.py:
- State-Cache mit CSRF-Schutz (15 Minuten Ablauf)
- Token-Verschlüsselung via encrypt_data() / decrypt_data()
- Automatischer Token-Refresh
- httpx.AsyncClient für Token-Exchange

Feinpoliert und durchdacht - Sichere Kalender-Authentifizierung.
"""

import json
import secrets
import threading
from datetime import timedelta
from typing import Dict, Optional, Tuple
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.encryption import encrypt_data, decrypt_data
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# OAuth2 Konfiguration
# =============================================================================

STATE_EXPIRY_SECONDS = 900  # 15 Minuten
"""CSRF-State ist maximal 15 Minuten gültig."""

TOKEN_REFRESH_BUFFER_MINUTES = 5
"""Token wird erneuert wenn weniger als 5 Minuten gültig."""

PROVIDER_CONFIG: Dict[str, Dict[str, str]] = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "scope": "https://www.googleapis.com/auth/calendar.events",
    },
    "outlook": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "Calendars.ReadWrite offline_access User.Read",
    },
}
"""Provider-spezifische OAuth2-Endpunkte und Scopes."""


# =============================================================================
# State-Cache Typen
# =============================================================================

class _StateEntry:
    """Typ-sichere State-Cache-Einträge."""

    __slots__ = ("company_id", "provider", "created_at")

    def __init__(self, company_id: str, provider: str) -> None:
        self.company_id = company_id
        self.provider = provider
        self.created_at = utc_now()

    def is_expired(self) -> bool:
        """Prüft ob State abgelaufen ist."""
        return utc_now() - self.created_at > timedelta(seconds=STATE_EXPIRY_SECONDS)

    def to_dict(self) -> Dict[str, str]:
        """Konvertiert in Dict für Rückgabe."""
        return {
            "company_id": self.company_id,
            "provider": self.provider,
        }


# =============================================================================
# OAuth Service
# =============================================================================

class CalendarOAuthService:
    """
    OAuth2-Service für Kalender-Provider.

    Verwaltet den kompletten OAuth2-Flow für Google Calendar
    und Microsoft Outlook:
    - Authorization URL für User-Consent
    - Code-Exchange nach Redirect
    - Token-Refresh bei Ablauf
    - Token-Widerruf
    - Sichere Token-Speicherung (AES-256-GCM)

    Usage:
        oauth = get_calendar_oauth_service()

        # 1. OAuth-Flow starten
        auth_url, state = oauth.get_authorization_url(
            provider="google",
            client_id="...",
            redirect_uri="https://app/callback",
            company_id=company_uuid,
        )

        # 2. User wird zu auth_url geleitet
        # 3. Nach Redirect: Code austauschen
        success = await oauth.exchange_code(
            db=session,
            company_id=company_uuid,
            provider="google",
            code="auth_code_from_callback",
            client_id="...",
            client_secret="...",
            redirect_uri="https://app/callback",
        )
    """

    def __init__(self) -> None:
        """Initialisiert den OAuth Service."""
        self._http_timeout = httpx.Timeout(30.0)
        # State-Cache für CSRF-Schutz (In-Memory, für Production Redis verwenden)
        self._state_cache: Dict[str, _StateEntry] = {}
        self._state_lock = threading.Lock()

    # =========================================================================
    # Authorization URL
    # =========================================================================

    def get_authorization_url(
        self,
        provider: str,
        client_id: str,
        redirect_uri: str,
        company_id: UUID,
    ) -> Tuple[str, str]:
        """
        Generiert OAuth2 Authorization URL für einen Kalender-Provider.

        Args:
            provider: Provider-Name ("google" oder "outlook")
            client_id: OAuth2 Client ID
            redirect_uri: Callback URL nach Authorization
            company_id: Firmen-ID für State-Zuordnung

        Returns:
            Tuple aus (Authorization URL, State-Token)

        Raises:
            ValueError: Wenn Provider unbekannt ist
        """
        config = PROVIDER_CONFIG.get(provider)
        if not config:
            raise ValueError(f"Unbekannter Kalender-Provider: {provider}")

        # Abgelaufene States aufraeumen
        self._cleanup_expired_states()

        # CSRF-sicheren State generieren
        state = secrets.token_urlsafe(32)

        # State mit Metadaten cachen
        with self._state_lock:
            self._state_cache[state] = _StateEntry(
                company_id=str(company_id),
                provider=provider,
            )

        # URL-Parameter zusammenbauen
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": config["scope"],
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        auth_url = f"{config['auth_url']}?{query}"

        logger.info(
            "calendar_auth_url_generated",
            provider=provider,
            company_id=str(company_id),
        )

        return auth_url, state

    # =========================================================================
    # State Validation
    # =========================================================================

    def validate_state(self, state: str) -> Optional[Dict[str, str]]:
        """
        Validiert State-Token nach OAuth-Callback.

        Args:
            state: State-Token aus Callback

        Returns:
            State-Metadaten (company_id, provider) oder None wenn ungültig
        """
        with self._state_lock:
            entry = self._state_cache.get(state)

            if not entry:
                logger.warning("calendar_invalid_state", state_hash=hash(state))
                return None

            # State verbrauchen (einmalig verwendbar)
            del self._state_cache[state]

            # Timeout prüfen
            if entry.is_expired():
                logger.warning("calendar_state_expired")
                return None

            return entry.to_dict()

    # =========================================================================
    # Code Exchange
    # =========================================================================

    async def exchange_code(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> bool:
        """
        Tauscht Authorization Code gegen Tokens.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            provider: Provider-Name ("google" oder "outlook")
            code: Authorization Code
            client_id: OAuth2 Client ID
            client_secret: OAuth2 Client Secret
            redirect_uri: Redirect URI (muss mit Authorization übereinstimmen)

        Returns:
            True wenn erfolgreich
        """
        config = PROVIDER_CONFIG.get(provider)
        if not config:
            logger.error("calendar_exchange_unknown_provider", provider=provider)
            return False

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(
                    config["token_url"],
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": redirect_uri,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        "calendar_code_exchange_failed",
                        provider=provider,
                        status=response.status_code,
                        error=response.text[:500],
                    )
                    return False

                token_data = response.json()

                # Token-Daten extrahieren
                access_token = token_data.get("access_token", "")
                refresh_token = token_data.get("refresh_token", "")
                expires_in = token_data.get("expires_in", 3600)
                token_expires_at = utc_now() + timedelta(seconds=expires_in)

                # Verschlüsseln und in DB speichern
                await self._store_oauth_tokens(
                    db=db,
                    company_id=company_id,
                    provider=provider,
                    tokens_data={
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "expires_at": token_expires_at.isoformat(),
                    },
                )

                logger.info(
                    "calendar_code_exchanged",
                    provider=provider,
                    company_id=str(company_id),
                    expires_in=expires_in,
                )
                return True

        except Exception as e:
            logger.error(
                "calendar_code_exchange_error",
                provider=provider,
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return False

    # =========================================================================
    # Token Refresh
    # =========================================================================

    async def refresh_token(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
        client_id: str,
        client_secret: str,
    ) -> Optional[str]:
        """
        Aktualisiert Access Token via Refresh Token.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            provider: Provider-Name
            client_id: OAuth2 Client ID
            client_secret: OAuth2 Client Secret

        Returns:
            Neuer Access Token oder None bei Fehler
        """
        config = PROVIDER_CONFIG.get(provider)
        if not config:
            return None

        tokens = await self._get_oauth_tokens(db, company_id, provider)
        if not tokens or not tokens.get("refresh_token"):
            logger.error(
                "calendar_no_refresh_token",
                provider=provider,
                company_id=str(company_id),
            )
            return None

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(
                    config["token_url"],
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": tokens["refresh_token"],
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        "calendar_token_refresh_failed",
                        provider=provider,
                        status=response.status_code,
                    )
                    return None

                token_data = response.json()

                access_token = token_data.get("access_token", "")
                new_refresh = token_data.get("refresh_token", tokens["refresh_token"])
                expires_in = token_data.get("expires_in", 3600)
                token_expires_at = utc_now() + timedelta(seconds=expires_in)

                await self._store_oauth_tokens(
                    db=db,
                    company_id=company_id,
                    provider=provider,
                    tokens_data={
                        "access_token": access_token,
                        "refresh_token": new_refresh,
                        "expires_at": token_expires_at.isoformat(),
                    },
                )

                logger.info(
                    "calendar_tokens_refreshed",
                    provider=provider,
                    company_id=str(company_id),
                    expires_in=expires_in,
                )
                return access_token

        except Exception as e:
            logger.error(
                "calendar_token_refresh_error",
                provider=provider,
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return None

    # =========================================================================
    # Get Valid Token (auto-refresh)
    # =========================================================================

    async def get_valid_token(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
        client_id: str,
        client_secret: str,
    ) -> Optional[str]:
        """
        Gibt einen gültigen Access Token zurück, mit automatischem Refresh.

        Prüft ob der gespeicherte Token noch gültig ist. Falls nicht,
        wird automatisch ein Refresh durchgeführt.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            provider: Provider-Name
            client_id: OAuth2 Client ID
            client_secret: OAuth2 Client Secret

        Returns:
            Gültiger Access Token oder None
        """
        tokens = await self._get_oauth_tokens(db, company_id, provider)
        if not tokens:
            return None

        # Prüfen ob Token noch gültig ist
        expires_at_str = tokens.get("expires_at", "")
        if expires_at_str:
            from app.core.datetime_utils import parse_iso_datetime
            expires_at = parse_iso_datetime(expires_at_str)
            if expires_at:
                buffer = timedelta(minutes=TOKEN_REFRESH_BUFFER_MINUTES)
                if utc_now() + buffer < expires_at:
                    # Token ist noch gültig
                    return tokens.get("access_token")

        # Token abgelaufen oder bald ablaufend - Refresh durchführen
        return await self.refresh_token(
            db=db,
            company_id=company_id,
            provider=provider,
            client_id=client_id,
            client_secret=client_secret,
        )

    # =========================================================================
    # Token Revocation
    # =========================================================================

    async def revoke_token(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
        client_id: str,
        client_secret: str,
    ) -> bool:
        """
        Widerruft OAuth-Tokens beim Provider und löscht sie lokal.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            provider: Provider-Name
            client_id: OAuth2 Client ID
            client_secret: OAuth2 Client Secret

        Returns:
            True wenn erfolgreich (auch wenn Provider-Widerruf fehlschlaegt)
        """
        tokens = await self._get_oauth_tokens(db, company_id, provider)

        # Tokens beim Provider widerrufen (best-effort)
        if tokens and tokens.get("access_token"):
            try:
                config = PROVIDER_CONFIG.get(provider, {})
                revoke_url = config.get("revoke_url")

                if revoke_url:
                    async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                        await client.post(
                            revoke_url,
                            data={
                                "token": tokens["access_token"],
                                "client_id": client_id,
                                "client_secret": client_secret,
                            },
                        )
            except Exception as e:
                # Revocation beim Provider ist best-effort
                logger.warning(
                    "calendar_revoke_api_warning",
                    provider=provider,
                    **safe_error_log(e),
                )

        # Lokal immer löschen
        await self._clear_oauth_tokens(db, company_id, provider)

        logger.info(
            "calendar_tokens_revoked",
            provider=provider,
            company_id=str(company_id),
        )
        return True

    # =========================================================================
    # Private: State Cleanup
    # =========================================================================

    def _cleanup_expired_states(self) -> None:
        """Entfernt abgelaufene State-Einträge aus dem Cache."""
        with self._state_lock:
            expired_keys = [
                key for key, entry in self._state_cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._state_cache[key]

            if expired_keys:
                logger.debug(
                    "calendar_states_cleaned",
                    removed=len(expired_keys),
                )

    # =========================================================================
    # Private: Token Storage (CompanySettings JSONB)
    # =========================================================================

    async def get_token_status(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
    ) -> Optional[Dict[str, str]]:
        """Öffentliche Methode: Gibt Token-Metadaten zurück (ohne Secrets).

        Returns:
            Dict mit 'connected' und 'expires_at' oder None
        """
        tokens = await self._get_oauth_tokens(db, company_id, provider)
        if not tokens:
            return None
        return {
            "connected": "true",
            "expires_at": tokens.get("expires_at", ""),
        }

    async def _get_oauth_tokens(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
    ) -> Optional[Dict[str, str]]:
        """
        Liest und entschlüsselt OAuth-Tokens aus CompanySettings.

        Token-Speicherstruktur in CompanySettings.calendar_oauth_tokens:
        {
            "google": "<encrypted_json_blob>",
            "outlook": "<encrypted_json_blob>"
        }

        Returns:
            Dict mit access_token, refresh_token, expires_at oder None
        """
        from app.db.models import CompanySettings

        stmt = select(CompanySettings).limit(1)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            return None

        oauth_tokens = getattr(settings, "calendar_oauth_tokens", None)
        if not oauth_tokens or not isinstance(oauth_tokens, dict):
            return None

        encrypted_blob = oauth_tokens.get(provider)
        if not encrypted_blob or not isinstance(encrypted_blob, str):
            return None

        try:
            decrypted_json = decrypt_data(
                encrypted_blob,
                associated_data=f"calendar_oauth:{company_id}:{provider}",
            )
            token_dict = json.loads(decrypted_json)
            if isinstance(token_dict, dict):
                return token_dict
            return None
        except Exception as e:
            logger.error(
                "calendar_token_decrypt_failed",
                provider=provider,
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return None

    async def _store_oauth_tokens(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
        tokens_data: Dict[str, str],
    ) -> None:
        """
        Verschlüsselt und speichert OAuth-Tokens in CompanySettings.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            provider: Provider-Name
            tokens_data: Dict mit access_token, refresh_token, expires_at
        """
        from app.db.models import CompanySettings

        stmt = select(CompanySettings).limit(1)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            logger.error(
                "calendar_store_no_settings",
                company_id=str(company_id),
            )
            return

        # Token-Daten verschlüsseln
        token_json = json.dumps(tokens_data)
        encrypted_blob = encrypt_data(
            token_json,
            associated_data=f"calendar_oauth:{company_id}:{provider}",
        )

        # Bestehende OAuth-Tokens laden oder leeres Dict
        oauth_tokens = getattr(settings, "calendar_oauth_tokens", None)
        if not oauth_tokens or not isinstance(oauth_tokens, dict):
            oauth_tokens = {}

        # Provider-Eintrag aktualisieren
        oauth_tokens[provider] = encrypted_blob
        settings.calendar_oauth_tokens = oauth_tokens

        await db.commit()

        logger.debug(
            "calendar_tokens_stored",
            provider=provider,
            company_id=str(company_id),
        )

    async def _clear_oauth_tokens(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
    ) -> None:
        """Löscht OAuth-Tokens für einen Provider aus CompanySettings."""
        from app.db.models import CompanySettings

        stmt = select(CompanySettings).limit(1)
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            return

        oauth_tokens = getattr(settings, "calendar_oauth_tokens", None)
        if oauth_tokens and isinstance(oauth_tokens, dict) and provider in oauth_tokens:
            del oauth_tokens[provider]
            settings.calendar_oauth_tokens = oauth_tokens
            await db.commit()


# =============================================================================
# Singleton
# =============================================================================

_oauth_service: Optional[CalendarOAuthService] = None
_service_lock = threading.Lock()


def get_calendar_oauth_service() -> CalendarOAuthService:
    """
    Factory für CalendarOAuthService (Thread-Safe Singleton).

    Returns:
        CalendarOAuthService Instanz
    """
    global _oauth_service
    if _oauth_service is None:
        with _service_lock:
            if _oauth_service is None:
                _oauth_service = CalendarOAuthService()
    return _oauth_service

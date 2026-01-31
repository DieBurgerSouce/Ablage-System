# -*- coding: utf-8 -*-
"""
DATEV OAuth2 Authentifizierungs-Service.

Verwaltet OAuth2-Flow fuer DATEVconnect:
- Authorization URL Generation
- Code Exchange
- Token Refresh
- Credential Encryption

Feinpoliert und durchdacht - Sichere DATEV Authentifizierung.
"""

import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.core.encryption import encrypt_value, decrypt_value

logger = structlog.get_logger(__name__)


# =============================================================================
# OAuth2 Konfiguration
# =============================================================================

DATEV_AUTH_URLS = {
    "production": "https://login.datev.de/openidsandbox",
    "sandbox": "https://login.sandbox.datev.de/openidsandbox",
}

DATEV_SCOPES = [
    "openid",
    "datev:accounting",
    "datev:master-data",
    "datev:documents",
    "offline_access",
]

TOKEN_REFRESH_BUFFER_MINUTES = 5
"""Token wird erneuert wenn weniger als 5 Minuten gueltig."""


# =============================================================================
# Auth Service
# =============================================================================

class DATEVAuthService:
    """
    DATEV OAuth2 Authentifizierungs-Service.

    Verwaltet den kompletten OAuth2-Flow:
    - Authorization URL fuer User-Consent
    - Code-Exchange nach Redirect
    - Token-Refresh
    - Sichere Credential-Speicherung

    Usage:
        auth_service = DATEVAuthService()

        # 1. OAuth-Flow starten
        auth_url, state = auth_service.get_authorization_url(
            client_id="...",
            redirect_uri="https://app.example.com/callback"
        )

        # 2. User wird zu auth_url geleitet
        # 3. Nach Redirect: Code austauschen
        tokens = await auth_service.exchange_code(
            db=session,
            connection_id=conn_uuid,
            code="auth_code_from_callback"
        )

        # 4. Tokens werden verschluesselt gespeichert
    """

    def __init__(self) -> None:
        """Initialisiert den Auth Service."""
        self._http_timeout = httpx.Timeout(30.0)
        # State-Cache fuer CSRF-Schutz (In-Memory, fuer Production Redis verwenden)
        self._state_cache: dict[str, dict] = {}
        self._state_lock = threading.Lock()

    def get_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        environment: str = "production",
        connection_id: Optional[UUID] = None,
    ) -> Tuple[str, str]:
        """
        Generiert OAuth2 Authorization URL.

        Args:
            client_id: DATEVconnect Client ID
            redirect_uri: Callback URL nach Authorization
            environment: API-Umgebung (production/sandbox)
            connection_id: Optional Connection ID fuer State-Zuordnung

        Returns:
            Tuple aus (Authorization URL, State-Token)
        """
        # CSRF-sicheren State generieren
        state = secrets.token_urlsafe(32)

        # State mit Metadaten cachen
        with self._state_lock:
            self._state_cache[state] = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "connection_id": str(connection_id) if connection_id else None,
                "created_at": utc_now(),
            }

        # Base URL
        auth_base = DATEV_AUTH_URLS.get(environment, DATEV_AUTH_URLS["production"])

        # Scopes zusammenbauen
        scope = " ".join(DATEV_SCOPES)

        # URL bauen
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        auth_url = f"{auth_base}/authorize?{query}"

        logger.info(
            "datev_auth_url_generated",
            environment=environment,
            has_connection_id=connection_id is not None,
        )

        return auth_url, state

    def validate_state(self, state: str) -> Optional[dict]:
        """
        Validiert State-Token nach OAuth-Callback.

        Args:
            state: State-Token aus Callback

        Returns:
            State-Metadaten oder None wenn ungueltig
        """
        with self._state_lock:
            state_data = self._state_cache.get(state)

            if not state_data:
                logger.warning("datev_invalid_state", state_hash=hash(state))
                return None

            # State verbrauchen (einmalig verwendbar)
            del self._state_cache[state]

            # Timeout pruefen (15 Minuten)
            created_at = state_data.get("created_at")
            if created_at and utc_now() - created_at > timedelta(minutes=15):
                logger.warning("datev_state_expired")
                return None

            return state_data

    async def exchange_code(
        self,
        db: AsyncSession,
        connection_id: UUID,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        environment: str = "production",
    ) -> bool:
        """
        Tauscht Authorization Code gegen Tokens.

        Args:
            db: Datenbank-Session
            connection_id: ID der DATEV-Verbindung
            code: Authorization Code
            client_id: Client ID
            client_secret: Client Secret
            redirect_uri: Redirect URI (muss mit Authorization uebereinstimmen)
            environment: API-Umgebung

        Returns:
            True wenn erfolgreich
        """
        auth_base = DATEV_AUTH_URLS.get(environment, DATEV_AUTH_URLS["production"])

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(
                    f"{auth_base}/token",
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
                        "datev_code_exchange_failed",
                        status=response.status_code,
                        error=response.text[:500],
                    )
                    return False

                token_data = response.json()

                # Tokens verschluesseln und speichern
                access_token = token_data.get("access_token", "")
                refresh_token = token_data.get("refresh_token", "")
                expires_in = token_data.get("expires_in", 3600)
                token_expires_at = utc_now() + timedelta(seconds=expires_in)

                # In DB speichern
                await self._save_tokens(
                    db=db,
                    connection_id=connection_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_expires_at=token_expires_at,
                )

                logger.info(
                    "datev_code_exchanged",
                    connection_id=str(connection_id),
                    expires_in=expires_in,
                )
                return True

        except Exception as e:
            logger.error(
                "datev_code_exchange_error",
                connection_id=str(connection_id),
                **safe_error_log(e)
            )
            return False

    async def refresh_tokens(
        self,
        db: AsyncSession,
        connection_id: UUID,
        refresh_token_encrypted: str,
        client_id: str,
        client_secret: str,
        environment: str = "production",
    ) -> bool:
        """
        Aktualisiert Access Token via Refresh Token.

        Args:
            db: Datenbank-Session
            connection_id: ID der DATEV-Verbindung
            refresh_token_encrypted: Verschluesselter Refresh Token
            client_id: Client ID
            client_secret: Client Secret
            environment: API-Umgebung

        Returns:
            True wenn erfolgreich
        """
        auth_base = DATEV_AUTH_URLS.get(environment, DATEV_AUTH_URLS["production"])

        try:
            # Refresh Token entschluesseln
            refresh_token = decrypt_value(refresh_token_encrypted)
            if not refresh_token:
                logger.error(
                    "datev_refresh_token_decrypt_failed",
                    connection_id=str(connection_id),
                )
                return False

            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(
                    f"{auth_base}/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        "datev_token_refresh_failed",
                        status=response.status_code,
                    )
                    return False

                token_data = response.json()

                # Neue Tokens speichern
                access_token = token_data.get("access_token", "")
                new_refresh_token = token_data.get("refresh_token", refresh_token)
                expires_in = token_data.get("expires_in", 3600)
                token_expires_at = utc_now() + timedelta(seconds=expires_in)

                await self._save_tokens(
                    db=db,
                    connection_id=connection_id,
                    access_token=access_token,
                    refresh_token=new_refresh_token,
                    token_expires_at=token_expires_at,
                )

                logger.info(
                    "datev_tokens_refreshed",
                    connection_id=str(connection_id),
                    expires_in=expires_in,
                )
                return True

        except Exception as e:
            logger.error(
                "datev_token_refresh_error",
                connection_id=str(connection_id),
                **safe_error_log(e)
            )
            return False

    async def token_needs_refresh(
        self,
        token_expires_at: Optional[datetime],
    ) -> bool:
        """
        Prueft ob Token-Refresh noetig ist.

        Args:
            token_expires_at: Ablaufzeitpunkt des Tokens

        Returns:
            True wenn Refresh noetig
        """
        if not token_expires_at:
            return True

        buffer = timedelta(minutes=TOKEN_REFRESH_BUFFER_MINUTES)
        return utc_now() + buffer >= token_expires_at

    async def revoke_tokens(
        self,
        db: AsyncSession,
        connection_id: UUID,
        access_token_encrypted: str,
        client_id: str,
        client_secret: str,
        environment: str = "production",
    ) -> bool:
        """
        Widerruft OAuth-Tokens bei DATEV.

        Args:
            db: Datenbank-Session
            connection_id: ID der DATEV-Verbindung
            access_token_encrypted: Verschluesselter Access Token
            client_id: Client ID
            client_secret: Client Secret
            environment: API-Umgebung

        Returns:
            True wenn erfolgreich
        """
        auth_base = DATEV_AUTH_URLS.get(environment, DATEV_AUTH_URLS["production"])

        try:
            access_token = decrypt_value(access_token_encrypted)
            if not access_token:
                return False

            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(
                    f"{auth_base}/revoke",
                    data={
                        "token": access_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )

                # Tokens in DB loeschen
                await self._clear_tokens(db, connection_id)

                if response.status_code in (200, 204):
                    logger.info(
                        "datev_tokens_revoked",
                        connection_id=str(connection_id),
                    )
                    return True
                else:
                    # Trotzdem lokal loeschen
                    logger.warning(
                        "datev_revoke_api_failed",
                        status=response.status_code,
                    )
                    return True  # Lokal geloescht

        except Exception as e:
            logger.error(
                "datev_token_revoke_error",
                **safe_error_log(e)
            )
            return False

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _save_tokens(
        self,
        db: AsyncSession,
        connection_id: UUID,
        access_token: str,
        refresh_token: str,
        token_expires_at: datetime,
    ) -> None:
        """Speichert verschluesselte Tokens in der DB."""
        from app.db import models

        # Tokens verschluesseln
        access_encrypted = encrypt_value(access_token)
        refresh_encrypted = encrypt_value(refresh_token)

        # Update durchfuehren
        await db.execute(
            update(models.DATEVConnection)
            .where(models.DATEVConnection.id == connection_id)
            .values(
                access_token_encrypted=access_encrypted,
                refresh_token_encrypted=refresh_encrypted,
                token_expires_at=token_expires_at,
                connection_status="connected",
                last_connection_at=utc_now(),
                last_error=None,
            )
        )
        await db.commit()

    async def _clear_tokens(
        self,
        db: AsyncSession,
        connection_id: UUID,
    ) -> None:
        """Loescht Tokens aus der DB."""
        from app.db import models

        await db.execute(
            update(models.DATEVConnection)
            .where(models.DATEVConnection.id == connection_id)
            .values(
                access_token_encrypted=None,
                refresh_token_encrypted=None,
                token_expires_at=None,
                connection_status="disconnected",
            )
        )
        await db.commit()


# =============================================================================
# Singleton
# =============================================================================

_auth_service: Optional[DATEVAuthService] = None
_service_lock = threading.Lock()


def get_datev_auth_service() -> DATEVAuthService:
    """
    Factory fuer DATEVAuthService (Thread-Safe Singleton).
    """
    global _auth_service
    if _auth_service is None:
        with _service_lock:
            if _auth_service is None:
                _auth_service = DATEVAuthService()
    return _auth_service
